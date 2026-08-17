"""Strict, task-neutral capability registry for reusable Corridor mechanics.

A capability describes a bounded operation that a task Builder may select and bind
to one or more work rows.  Registry membership is not permission to run an operation,
proof that it applies, or evidence that its output is correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any

from .core import CorridorKitError, load_json, sha256_json


CAPABILITY_SCHEMA = "charting-loop/capability-registry/v1"
CAPABILITY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SIDE_EFFECT_LEVELS = frozenset({"none", "read_only", "mutating"})
REGISTRY_STATES = frozenset({"compiled", "uncompiled"})


@dataclass
class CapabilityReport:
    """Structural findings; never a runtime authorization result."""

    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, location: str, message: str) -> None:
        self.errors.append({"code": code, "location": location, "message": message})

    def warning(self, code: str, location: str, message: str) -> None:
        self.warnings.append({"code": code, "location": location, "message": message})

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


def _nonempty(value: Any, report: CapabilityReport, location: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        report.error("NONEMPTY_STRING_REQUIRED", location, "must be a non-empty string")
        return None
    return value.strip()


def _strings(value: Any, report: CapabilityReport, location: str) -> list[str]:
    if not isinstance(value, list):
        report.error("STRING_LIST_REQUIRED", location, "must be a list of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _nonempty(item, report, f"{location}[{index}]")
        if text is not None:
            result.append(text)
    if len(result) != len(set(result)):
        report.error("DUPLICATE_LIST_VALUE", location, "values must be unique")
    return result


def validate_capability_registry(
    value: Any,
    *,
    allow_draft: bool = False,
) -> CapabilityReport:
    """Validate a registry and expose its stable IDs and digest."""

    report = CapabilityReport()
    expected_top = {"schema_version", "state", "registry_version", "capabilities"}
    if not isinstance(value, dict):
        report.error("OBJECT_REQUIRED", "$", "must be an object")
        return report
    if set(value) != expected_top:
        report.error(
            "EXACT_FIELDS_REQUIRED",
            "$",
            f"must contain exactly {sorted(expected_top)}; got {sorted(value)}",
        )
    if value.get("schema_version") != CAPABILITY_SCHEMA:
        report.error("SCHEMA_VERSION", "$.schema_version", f"must equal {CAPABILITY_SCHEMA!r}")
    state = value.get("state")
    if state not in REGISTRY_STATES:
        report.error("REGISTRY_STATE", "$.state", f"must be one of {sorted(REGISTRY_STATES)}")
    registry_version = _nonempty(value.get("registry_version"), report, "$.registry_version")
    if registry_version is not None and not VERSION_RE.fullmatch(registry_version):
        report.error("REGISTRY_VERSION", "$.registry_version", "must be a semantic version")

    capabilities_value = value.get("capabilities")
    if not isinstance(capabilities_value, list):
        report.error("CAPABILITY_LIST_REQUIRED", "$.capabilities", "must be a list")
        capabilities_value = []
    if state == "uncompiled" and capabilities_value:
        report.error(
            "UNCOMPILED_REGISTRY_HAS_CAPABILITIES",
            "$.capabilities",
            "the uncompiled starter must not imply capability selection",
        )
    if state == "uncompiled" and not allow_draft:
        report.error("UNCOMPILED_REGISTRY", "$.state", "final registry must be compiled")

    fields = {
        "capability_id",
        "version",
        "digest",
        "summary",
        "entrypoint",
        "input_contract",
        "output_contract",
        "side_effects",
        "applicability",
    }
    ids: list[str] = []
    mutating_ids: list[str] = []
    for index, item in enumerate(capabilities_value):
        location = f"$.capabilities[{index}]"
        if not isinstance(item, dict):
            report.error("CAPABILITY_OBJECT_REQUIRED", location, "must be an object")
            continue
        if set(item) != fields:
            report.error(
                "EXACT_CAPABILITY_FIELDS",
                location,
                f"must contain exactly {sorted(fields)}; got {sorted(item)}",
            )
        capability_id = _nonempty(item.get("capability_id"), report, f"{location}.capability_id")
        if capability_id is not None:
            if not CAPABILITY_ID_RE.fullmatch(capability_id):
                report.error("CAPABILITY_ID_FORMAT", f"{location}.capability_id", "must be a stable token")
            ids.append(capability_id)
        version = _nonempty(item.get("version"), report, f"{location}.version")
        if version is not None and not VERSION_RE.fullmatch(version):
            report.error("CAPABILITY_VERSION", f"{location}.version", "must be a semantic version")
        digest = _nonempty(item.get("digest"), report, f"{location}.digest")
        if digest is not None and not SHA256_RE.fullmatch(digest):
            report.error("CAPABILITY_DIGEST", f"{location}.digest", "must be sha256:<64 lowercase hex>")
        _nonempty(item.get("summary"), report, f"{location}.summary")
        _nonempty(item.get("entrypoint"), report, f"{location}.entrypoint")
        for field_name in ("input_contract", "output_contract"):
            contract = item.get(field_name)
            if not isinstance(contract, dict) or not contract:
                report.error("NONEMPTY_CONTRACT", f"{location}.{field_name}", "must be a non-empty object")
        side_effects = item.get("side_effects")
        if side_effects not in SIDE_EFFECT_LEVELS:
            report.error(
                "SIDE_EFFECT_LEVEL",
                f"{location}.side_effects",
                f"must be one of {sorted(SIDE_EFFECT_LEVELS)}",
            )
        elif side_effects == "mutating" and capability_id is not None:
            mutating_ids.append(capability_id)
        applicability = item.get("applicability")
        if not isinstance(applicability, dict) or set(applicability) != {"domains", "signals"}:
            report.error(
                "APPLICABILITY_FIELDS",
                f"{location}.applicability",
                "must contain exactly domains and signals",
            )
        else:
            _strings(applicability.get("domains"), report, f"{location}.applicability.domains")
            _strings(applicability.get("signals"), report, f"{location}.applicability.signals")

    if len(ids) != len(set(ids)):
        report.error("DUPLICATE_CAPABILITY_ID", "$.capabilities", "capability IDs must be unique")
    if allow_draft and state == "uncompiled":
        report.warning(
            "UNCOMPILED_CAPABILITY_SURFACE",
            "$.state",
            "Builder must select and bind capabilities before Corridor freeze",
        )
    report.facts = {
        "schema_version": value.get("schema_version"),
        "state": state,
        "registry_version": registry_version,
        "capability_ids": ids,
        "mutating_capability_ids": mutating_ids,
        "registry_digest": sha256_json(value) if not report.errors else None,
        "advisory_only": True,
        "authorizes_mutation": False,
    }
    return report


def validate_capability_file(path: Path, *, allow_draft: bool = False) -> CapabilityReport:
    try:
        value = load_json(path)
    except CorridorKitError as exc:
        report = CapabilityReport()
        report.error("JSON_INPUT", str(path), str(exc))
        return report
    return validate_capability_registry(value, allow_draft=allow_draft)


def starter_capability_registry() -> dict[str, Any]:
    """Return an honest empty surface; no capability is selected by default."""

    return {
        "schema_version": CAPABILITY_SCHEMA,
        "state": "uncompiled",
        "registry_version": "0.0.0",
        "capabilities": [],
    }
