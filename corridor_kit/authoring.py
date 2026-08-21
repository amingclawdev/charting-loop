"""Task-neutral Builder authoring contracts and aggregate validation.

This module validates structure and byte identity only.  It is advisory, read-only,
and deliberately incapable of deciding a task answer or official deliverability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from .acceptance import (
    ACCEPTANCE_SCHEMA,
    VERIFICATION_OBLIGATION_KINDS,
    validate_acceptance_file,
)
from .capabilities import CAPABILITY_SCHEMA, validate_capability_file
from .core import KIT_VERSION, CorridorKitError, file_sha256, load_json, sha256_json
from .runtime import WORK_BACKLOG_SCHEMA, validate_work_files


AUTHORING_SCHEMA = "charting-loop/corridor-authoring-contract/v1"
WITNESSES_SCHEMA = "charting-loop/corridor-coupled-witnesses/v2"
AUTHORING_REPORT_SCHEMA = "charting-loop/corridor-authoring-validation/v1"
METHOD_CAPSULE_SCHEMA = "charting-loop/method-capsule/v1"
KIT_SCHEMA = "charting-loop/corridor-kit-scaffold/v1"
WITNESS_DISPOSITIONS = frozenset({"pass", "deny", "hold", "refusal"})
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
MAX_WITNESSES = 1024
MAX_WITNESS_ACCEPTANCE_IDS = 256
MAX_WITNESS_PARTITIONS = len(VERIFICATION_OBLIGATION_KINDS)
MAX_REPLAY_ARGV = 256
MAX_REPLAY_INPUT_REFS = 256
MAX_REPLAY_STRING = 65536


BUILDER_SURFACES = (
    ("acceptance", "ACCEPTANCE.json", ACCEPTANCE_SCHEMA),
    ("work_items", "WORK_ITEMS.json", WORK_BACKLOG_SCHEMA),
    ("capabilities", "CAPABILITIES.json", CAPABILITY_SCHEMA),
    ("method_capsule", "METHOD-CAPSULE.json", METHOD_CAPSULE_SCHEMA),
    ("authoring_contract", "AUTHORING.json", AUTHORING_SCHEMA),
    ("coupled_witnesses", "WITNESSES.json", WITNESSES_SCHEMA),
    ("evidence_records", "EVIDENCE.json", "charting-loop/behavior-evidence/v1"),
    ("source_map", "SOURCE-MAP.json", "charting-loop/source-map/v1"),
    ("replay_commands", "REPLAY.json", "charting-loop/unprivileged-replay/v1"),
)
RUNNER_SURFACES = (
    ("position_timeline", "external:POSITION.jsonl", "charting-loop/position-event/v1"),
    ("frozen_corridor_manifest", "external:FREEZE.json", "runner-defined"),
    ("submission_custody", "external:submission-manifests", "runner-defined"),
)
EVALUATOR_SURFACES = (
    ("official_deliverability", "external:official-deliverability", "evaluator-defined"),
)


GENERATED_FILES = [
    "ACCEPTANCE.json",
    "WORK_ITEMS.json",
    "CAPABILITIES.json",
    "METHOD-CAPSULE.json",
    "AUTHORING.json",
    "WITNESSES.json",
    "EVIDENCE.json",
    "SOURCE-MAP.json",
    "REPLAY.json",
    "README.md",
    "task_adapter.py",
    "fixtures/README.md",
    "evidence/README.md",
]


@dataclass
class AuthoringReport:
    """Deterministic structural findings, never an authorization decision."""

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


def _surface_descriptor(
    name: str,
    location: str,
    schema_version: str,
    *,
    owner: str,
    materialized_by_scaffold: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "location": location,
        "schema_version": schema_version,
        "owner": owner,
        "materialized_by_scaffold": materialized_by_scaffold,
    }


def starter_authoring_contract() -> dict[str, Any]:
    """Return the exact solution-free contract emitted by every scaffold."""

    surfaces = [
        _surface_descriptor(*surface, owner="builder", materialized_by_scaffold=True)
        for surface in BUILDER_SURFACES
    ]
    surfaces.extend(
        _surface_descriptor(*surface, owner="runner", materialized_by_scaffold=False)
        for surface in RUNNER_SURFACES
    )
    surfaces.extend(
        _surface_descriptor(
            *surface,
            owner="external_evaluator",
            materialized_by_scaffold=False,
        )
        for surface in EVALUATOR_SURFACES
    )
    return {
        "schema_version": AUTHORING_SCHEMA,
        "contract_state": "active",
        "surfaces": surfaces,
        "identity_joins": [
            {
                "name": "work_to_acceptance",
                "left": "WORK_ITEMS.json.acceptance_ledger_digest",
                "right": "sha256(canonical ACCEPTANCE.json)",
                "required_when": "WORK_ITEMS.json.state=compiled",
            },
            {
                "name": "witnesses_to_acceptance",
                "left": "WITNESSES.json.acceptance_ledger_digest",
                "right": "sha256(canonical ACCEPTANCE.json)",
                "required_when": "WITNESSES.json.state=compiled",
            },
            {
                "name": "kit_to_method_capsule",
                "left": "KIT.json.method_capsule_digest",
                "right": "sha256(canonical METHOD-CAPSULE.json)",
                "required_when": "always",
            },
        ],
        "boundaries": {
            "advisory_only": True,
            "read_only_validation": True,
            "authorizes_mutation": False,
            "blocking_gate": False,
            "task_solution_present": False,
            "evaluator_material_present": False,
            "infers_task_answer": False,
            "officially_deliverable": {
                "owner": "external_evaluator",
                "authority": "external",
                "status": "not_assessed",
            },
        },
    }


def starter_witnesses() -> dict[str, Any]:
    """Return an empty witness surface that honestly makes no task claim."""

    return {
        "schema_version": WITNESSES_SCHEMA,
        "state": "uncompiled",
        "acceptance_ledger_digest": None,
        "witnesses": [],
        "boundaries": {
            "advisory_only": True,
            "read_only": True,
            "authorizes_mutation": False,
            "blocking_gate": False,
            "infers_task_answer": False,
            "infers_pass": False,
            "officially_deliverable": {
                "owner": "external_evaluator",
                "authority": "external",
                "status": "not_assessed",
            },
        },
    }


def validate_authoring_contract(value: Any) -> AuthoringReport:
    """Require the exact task-neutral ownership and boundary contract."""

    report = AuthoringReport()
    expected = starter_authoring_contract()
    if not isinstance(value, dict):
        report.error("OBJECT_REQUIRED", "$", "AUTHORING.json must be an object")
        return report
    if set(value) != set(expected):
        report.error(
            "EXACT_FIELDS_REQUIRED",
            "$",
            f"must contain exactly {sorted(expected)}; got {sorted(value)}",
        )
    for key in ("schema_version", "contract_state", "surfaces", "identity_joins", "boundaries"):
        if value.get(key) != expected[key]:
            report.error(
                "AUTHORING_CONTRACT_MISMATCH",
                f"$.{key}",
                "must equal the frozen task-neutral authoring contract",
            )
    report.facts = {
        "schema_version": value.get("schema_version"),
        "contract_digest": sha256_json(value) if not report.errors else None,
        "builder_surface_count": len(BUILDER_SURFACES),
        "runner_surface_count": len(RUNNER_SURFACES),
        "evaluator_surface_count": len(EVALUATOR_SURFACES),
        "advisory_only": True,
        "authorizes_mutation": False,
        "blocking_gate": False,
    }
    return report


def _bounded_string(
    value: Any,
    report: AuthoringReport,
    location: str,
    *,
    token: bool = False,
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        report.error("NONEMPTY_STRING_REQUIRED", location, "must be a non-empty string")
        return None
    text = value.strip()
    if len(text.encode("utf-8")) > MAX_REPLAY_STRING:
        report.error("STRING_TOO_LARGE", location, f"must be at most {MAX_REPLAY_STRING} bytes")
        return None
    if "\x00" in text:
        report.error("NUL_FORBIDDEN", location, "must not contain a NUL byte")
    if token and not TOKEN_RE.fullmatch(text):
        report.error("TOKEN_FORMAT", location, "must be a stable token")
    return text


def _string_list(
    value: Any,
    report: AuthoringReport,
    location: str,
    *,
    maximum: int,
    nonempty: bool,
    token: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        report.error("STRING_LIST_REQUIRED", location, "must be a list of strings")
        return []
    if len(value) > maximum:
        report.error("LIST_TOO_LARGE", location, f"must contain at most {maximum} values")
    result: list[str] = []
    for index, item in enumerate(value[:maximum]):
        text = _bounded_string(item, report, f"{location}[{index}]", token=token)
        if text is not None:
            result.append(text)
    if nonempty and not result:
        report.error("NONEMPTY_LIST_REQUIRED", location, "must contain at least one value")
    if len(result) != len(set(result)):
        report.error("DUPLICATE_LIST_VALUE", location, "values must be unique")
    return result


def _digest_ref(
    value: Any,
    report: AuthoringReport,
    location: str,
    *,
    with_label: bool,
) -> None:
    expected = {"label", "ref", "sha256"} if with_label else {"ref", "sha256"}
    if not isinstance(value, dict):
        report.error("REFERENCE_OBJECT_REQUIRED", location, "must be an object")
        return
    if set(value) != expected:
        report.error(
            "EXACT_REFERENCE_FIELDS",
            location,
            f"must contain exactly {sorted(expected)}; got {sorted(value)}",
        )
    if with_label:
        _bounded_string(value.get("label"), report, f"{location}.label", token=True)
    _bounded_string(value.get("ref"), report, f"{location}.ref")
    digest = value.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        report.error("REFERENCE_DIGEST", f"{location}.sha256", "must be sha256:<64 lowercase hex>")


def validate_witnesses(
    value: Any,
    *,
    known_acceptance_ids: set[str],
    expected_acceptance_digest: str,
    allow_draft: bool = False,
) -> AuthoringReport:
    """Validate bounded replay references and report coverage without judging results."""

    report = AuthoringReport()
    expected_keys = {
        "schema_version",
        "state",
        "acceptance_ledger_digest",
        "witnesses",
        "boundaries",
    }
    if not isinstance(value, dict):
        report.error("OBJECT_REQUIRED", "$", "WITNESSES.json must be an object")
        return report
    if set(value) != expected_keys:
        report.error(
            "EXACT_FIELDS_REQUIRED",
            "$",
            f"must contain exactly {sorted(expected_keys)}; got {sorted(value)}",
        )
    if value.get("schema_version") != WITNESSES_SCHEMA:
        report.error("SCHEMA_VERSION", "$.schema_version", f"must equal {WITNESSES_SCHEMA!r}")
    if value.get("boundaries") != starter_witnesses()["boundaries"]:
        report.error(
            "WITNESS_BOUNDARY_MISMATCH",
            "$.boundaries",
            "must retain the read-only advisory and external-deliverability boundary",
        )

    state = value.get("state")
    if state not in {"compiled", "uncompiled"}:
        report.error("WITNESS_STATE", "$.state", "must be 'compiled' or 'uncompiled'")
    digest = value.get("acceptance_ledger_digest")
    witnesses_value = value.get("witnesses")
    if not isinstance(witnesses_value, list):
        report.error("WITNESS_LIST_REQUIRED", "$.witnesses", "must be a list")
        witnesses_value = []
    if len(witnesses_value) > MAX_WITNESSES:
        report.error("WITNESS_LIST_TOO_LARGE", "$.witnesses", f"must contain at most {MAX_WITNESSES} witnesses")

    if state == "uncompiled":
        if digest is not None:
            report.error("UNCOMPILED_WITNESS_DIGEST", "$.acceptance_ledger_digest", "must be null until compiled")
        if witnesses_value:
            report.error("UNCOMPILED_WITNESSES_NONEMPTY", "$.witnesses", "must be empty until compiled")
        if allow_draft:
            report.warning("UNCOMPILED_WITNESSES", "$.state", "Builder has not compiled coupled witnesses")
        else:
            report.error("UNCOMPILED_WITNESSES", "$.state", "final witness surface must be compiled")
    elif state == "compiled":
        if not witnesses_value:
            report.error(
                "COMPILED_WITNESSES_NONEMPTY",
                "$.witnesses",
                "compiled witness surface must contain at least one witness",
            )
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            report.error("ACCEPTANCE_DIGEST_REQUIRED", "$.acceptance_ledger_digest", "must bind canonical ACCEPTANCE.json")
        elif digest != expected_acceptance_digest:
            report.error("ACCEPTANCE_DIGEST_MISMATCH", "$.acceptance_ledger_digest", "does not bind the supplied ACCEPTANCE.json")

    witness_ids: list[str] = []
    witnessed_ids: set[str] = set()
    witnessed_partitions: set[tuple[str, str]] = set()
    by_disposition = {disposition: set() for disposition in sorted(WITNESS_DISPOSITIONS)}
    witness_fields = {
        "witness_id",
        "acceptance_ids",
        "obligation_partitions",
        "disposition",
        "replay",
    }
    replay_fields = {"argv", "input_refs", "result_ref", "shell"}
    for index, witness_value in enumerate(witnesses_value[:MAX_WITNESSES]):
        location = f"$.witnesses[{index}]"
        if not isinstance(witness_value, dict):
            report.error("WITNESS_OBJECT_REQUIRED", location, "must be an object")
            continue
        if set(witness_value) != witness_fields:
            report.error("EXACT_WITNESS_FIELDS", location, f"must contain exactly {sorted(witness_fields)}; got {sorted(witness_value)}")
        witness_id = _bounded_string(witness_value.get("witness_id"), report, f"{location}.witness_id", token=True)
        if witness_id is not None:
            witness_ids.append(witness_id)
        acceptance_ids = _string_list(
            witness_value.get("acceptance_ids"),
            report,
            f"{location}.acceptance_ids",
            maximum=MAX_WITNESS_ACCEPTANCE_IDS,
            nonempty=True,
            token=True,
        )
        for acceptance_id in acceptance_ids:
            if acceptance_id not in known_acceptance_ids:
                report.error("UNKNOWN_ACCEPTANCE_ID", f"{location}.acceptance_ids", f"unknown acceptance ID {acceptance_id!r}")
            else:
                witnessed_ids.add(acceptance_id)
        partitions = _string_list(
            witness_value.get("obligation_partitions"),
            report,
            f"{location}.obligation_partitions",
            maximum=MAX_WITNESS_PARTITIONS,
            nonempty=True,
            token=True,
        )
        for partition in partitions:
            if partition not in VERIFICATION_OBLIGATION_KINDS:
                report.error(
                    "UNKNOWN_OBLIGATION_PARTITION",
                    f"{location}.obligation_partitions",
                    f"must be one of {list(VERIFICATION_OBLIGATION_KINDS)}",
                )
                continue
            for acceptance_id in acceptance_ids:
                if acceptance_id in known_acceptance_ids:
                    witnessed_partitions.add((acceptance_id, partition))
        disposition = witness_value.get("disposition")
        if disposition not in WITNESS_DISPOSITIONS:
            report.error("WITNESS_DISPOSITION", f"{location}.disposition", f"must be one of {sorted(WITNESS_DISPOSITIONS)}")
        else:
            by_disposition[disposition].update(
                acceptance_id for acceptance_id in acceptance_ids if acceptance_id in known_acceptance_ids
            )

        replay = witness_value.get("replay")
        if not isinstance(replay, dict):
            report.error("REPLAY_OBJECT_REQUIRED", f"{location}.replay", "must be an object")
            continue
        if set(replay) != replay_fields:
            report.error("EXACT_REPLAY_FIELDS", f"{location}.replay", f"must contain exactly {sorted(replay_fields)}; got {sorted(replay)}")
        _string_list(
            replay.get("argv"),
            report,
            f"{location}.replay.argv",
            maximum=MAX_REPLAY_ARGV,
            nonempty=True,
        )
        if replay.get("shell") is not False:
            report.error("REPLAY_SHELL_FORBIDDEN", f"{location}.replay.shell", "must be false")
        input_refs = replay.get("input_refs")
        if not isinstance(input_refs, list):
            report.error("INPUT_REFERENCE_LIST_REQUIRED", f"{location}.replay.input_refs", "must be a list")
            input_refs = []
        if not input_refs:
            report.error(
                "INPUT_REFERENCE_REQUIRED",
                f"{location}.replay.input_refs",
                "must contain at least one replayable input reference",
            )
        if len(input_refs) > MAX_REPLAY_INPUT_REFS:
            report.error("INPUT_REFERENCE_LIST_TOO_LARGE", f"{location}.replay.input_refs", f"must contain at most {MAX_REPLAY_INPUT_REFS} references")
        labels: list[str] = []
        for ref_index, reference in enumerate(input_refs[:MAX_REPLAY_INPUT_REFS]):
            ref_location = f"{location}.replay.input_refs[{ref_index}]"
            _digest_ref(reference, report, ref_location, with_label=True)
            if isinstance(reference, dict) and isinstance(reference.get("label"), str):
                labels.append(reference["label"])
        if len(labels) != len(set(labels)):
            report.error("DUPLICATE_INPUT_LABEL", f"{location}.replay.input_refs", "labels must be unique")
        _digest_ref(replay.get("result_ref"), report, f"{location}.replay.result_ref", with_label=False)

    if len(witness_ids) != len(set(witness_ids)):
        report.error("DUPLICATE_WITNESS_ID", "$.witnesses", "witness IDs must be unique")
    known_sorted = sorted(known_acceptance_ids)
    witnessed_sorted = sorted(witnessed_ids)
    required_partitions = {
        (acceptance_id, partition)
        for acceptance_id in known_acceptance_ids
        for partition in VERIFICATION_OBLIGATION_KINDS
    }
    missing_partitions = sorted(required_partitions - witnessed_partitions)
    report.facts = {
        "schema_version": value.get("schema_version"),
        "state": state,
        "witness_count": len(witnesses_value),
        "witness_ids": witness_ids,
        "known_acceptance_ids": known_sorted,
        "witnessed_acceptance_ids": witnessed_sorted,
        "unwitnessed_acceptance_ids": sorted(known_acceptance_ids - witnessed_ids),
        "coverage_complete": bool(required_partitions) and not missing_partitions,
        "covered_obligation_partitions": [
            {"acceptance_id": acceptance_id, "partition": partition}
            for acceptance_id, partition in sorted(witnessed_partitions)
        ],
        "missing_obligation_partitions": [
            {"acceptance_id": acceptance_id, "partition": partition}
            for acceptance_id, partition in missing_partitions
        ],
        "coverage_by_disposition": {
            disposition: sorted(acceptance_ids)
            for disposition, acceptance_ids in by_disposition.items()
        },
        "witness_digest": sha256_json(value) if not report.errors else None,
        "advisory_only": True,
        "read_only": True,
        "authorizes_mutation": False,
        "blocking_gate": False,
        "task_answer": "not_inferred",
        "pass_inferred": False,
        "officially_deliverable": {
            "owner": "external_evaluator",
            "authority": "external",
            "status": "not_assessed",
        },
    }
    return report


def _validate_kit(value: Any, method_capsule: Any) -> AuthoringReport:
    report = AuthoringReport()
    expected_keys = {
        "schema_version",
        "kit_version",
        "state",
        "task_specific",
        "authorizes_mutation",
        "worker_and_qa_shared_after_freeze",
        "method_capsule_digest",
        "method_capsule_binding_state",
        "starter_digest",
        "generated_files",
    }
    if not isinstance(value, dict):
        report.error("OBJECT_REQUIRED", "$", "KIT.json must be an object")
        return report
    if set(value) != expected_keys:
        report.error("EXACT_FIELDS_REQUIRED", "$", f"must contain exactly {sorted(expected_keys)}; got {sorted(value)}")
    checks = {
        "schema_version": KIT_SCHEMA,
        "kit_version": KIT_VERSION,
        "state": "uncompiled",
        "task_specific": False,
        "authorizes_mutation": False,
        "worker_and_qa_shared_after_freeze": True,
        "generated_files": GENERATED_FILES,
    }
    for key, expected in checks.items():
        if value.get(key) != expected:
            report.error("KIT_IDENTITY_MISMATCH", f"$.{key}", f"must equal {expected!r}")
    starter_digest = value.get("starter_digest")
    if not isinstance(starter_digest, str) or not SHA256_RE.fullmatch(starter_digest):
        report.error("KIT_STARTER_DIGEST", "$.starter_digest", "must be sha256:<64 lowercase hex>")
    if isinstance(method_capsule, dict):
        if value.get("method_capsule_binding_state") != method_capsule.get("binding_state"):
            report.error("METHOD_CAPSULE_BINDING_STATE_MISMATCH", "$.method_capsule_binding_state", "does not match METHOD-CAPSULE.json")
    report.facts = {
        "schema_version": value.get("schema_version"),
        "kit_version": value.get("kit_version"),
        "generated_files": value.get("generated_files"),
        "advisory_only": True,
        "authorizes_mutation": False,
    }
    return report


def _report_errors(report: Any) -> list[dict[str, str]]:
    return list(report.errors) if hasattr(report, "errors") else []


def _surface_result(
    path: Path,
    value: Any,
    *,
    owner: str,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    facts: dict[str, Any],
    loaded: bool,
    inspect_file: bool,
) -> dict[str, Any]:
    raw_digest = None
    if inspect_file:
        try:
            raw_digest = file_sha256(path)
        except (CorridorKitError, OSError):
            pass
    try:
        canonical_digest = sha256_json(value) if loaded else None
    except CorridorKitError:
        canonical_digest = None
    return {
        "owner": owner,
        "file_sha256": raw_digest,
        "canonical_json_sha256": canonical_digest,
        "structurally_valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "facts": facts,
    }


def _identity_join(
    name: str,
    *,
    left: str,
    right: str,
    actual: Any,
    expected: Any,
    required: bool,
) -> dict[str, Any]:
    if not required and actual is None:
        status = "unbound"
    else:
        status = "matched" if actual == expected else "mismatch"
    return {
        "name": name,
        "left": left,
        "right": right,
        "actual": actual,
        "expected": expected,
        "required": required,
        "status": status,
    }


def validate_authoring_directory(
    root: Path,
    *,
    allow_draft: bool = False,
    expected_method_version: str | None = None,
    expected_method_digest: str | None = None,
    expected_method_scope_digest: str | None = None,
) -> dict[str, Any]:
    """Validate all authoring surfaces and their exact joins in one read-only pass."""

    root = Path(root)
    aggregate_errors: list[dict[str, str]] = []
    if root.is_symlink() or not root.is_dir():
        aggregate_errors.append({
            "code": "ROOT_DIRECTORY_REQUIRED",
            "location": "$",
            "message": "authoring root must be a real non-symlink directory",
        })
    names = (
        "ACCEPTANCE.json",
        "WORK_ITEMS.json",
        "CAPABILITIES.json",
        "METHOD-CAPSULE.json",
        "AUTHORING.json",
        "WITNESSES.json",
        "KIT.json",
    )
    values: dict[str, Any] = {}
    load_errors: dict[str, list[dict[str, str]]] = {name: [] for name in names}
    root_valid = not aggregate_errors
    if root_valid:
        for name in names:
            try:
                values[name] = load_json(root / name)
            except CorridorKitError as exc:
                load_errors[name].append({"code": "JSON_INPUT", "location": name, "message": str(exc)})
        acceptance_report = validate_acceptance_file(
            root / "ACCEPTANCE.json", allow_draft=allow_draft
        )
        capability_report = validate_capability_file(
            root / "CAPABILITIES.json", allow_draft=allow_draft
        )
        work_report = validate_work_files(
            root / "WORK_ITEMS.json",
            acceptance_path=root / "ACCEPTANCE.json",
            capability_path=root / "CAPABILITIES.json",
            allow_draft=allow_draft,
        )
    else:
        for name in names:
            load_errors[name].append({
                "code": "ROOT_DIRECTORY_REQUIRED",
                "location": name,
                "message": "surface was not read through an invalid authoring root",
            })
        acceptance_report = AuthoringReport()
        capability_report = AuthoringReport()
        work_report = AuthoringReport()
    acceptance = values.get("ACCEPTANCE.json")
    capabilities = values.get("CAPABILITIES.json")
    work = values.get("WORK_ITEMS.json")
    capsule = values.get("METHOD-CAPSULE.json")
    authoring = values.get("AUTHORING.json")
    witnesses = values.get("WITNESSES.json")
    kit = values.get("KIT.json")

    expected_values = (expected_method_version, expected_method_digest, expected_method_scope_digest)
    if any(value is not None for value in expected_values) and not all(value is not None for value in expected_values):
        aggregate_errors.append({
            "code": "EXPECTED_METHOD_IDENTITY_INCOMPLETE",
            "location": "$",
            "message": "expected Method version, digest, and scope digest must be supplied together",
        })
    method_errors: list[str] = []
    if isinstance(capsule, dict) and isinstance(kit, dict):
        from .scaffold import validate_method_capsule

        method_errors = validate_method_capsule(
            capsule,
            expected_method_version=(
                expected_method_version
                if expected_method_version is not None
                else capsule.get("method_version", "")
            ),
            expected_method_digest=(
                expected_method_digest
                if expected_method_digest is not None
                else capsule.get("method_digest", "")
            ),
            expected_method_scope_digest=(
                expected_method_scope_digest
                if expected_method_scope_digest is not None
                else capsule.get("method_scope_digest", "")
            ),
            expected_capsule_digest=kit.get("method_capsule_digest", ""),
        )
    elif "METHOD-CAPSULE.json" in values and not isinstance(capsule, dict):
        method_errors = ["METHOD_CAPSULE_OBJECT_REQUIRED"]
    method_structural_errors = [error for error in method_errors if not (allow_draft and error == "METHOD_CAPSULE_BOUND_REQUIRED")]
    method_warnings = [
        {"code": "METHOD_CAPSULE_UNBOUND", "location": "$.binding_state", "message": "Builder has not bound the frozen Method identity"}
    ] if allow_draft and "METHOD_CAPSULE_BOUND_REQUIRED" in method_errors else []

    authoring_report = (
        validate_authoring_contract(authoring)
        if "AUTHORING.json" in values
        else AuthoringReport()
    )
    acceptance_digest = (
        sha256_json(acceptance) if "ACCEPTANCE.json" in values else ""
    )
    known_acceptance_ids = set(acceptance_report.facts.get("acceptance_ids", []))
    witness_report = (
        validate_witnesses(
            witnesses,
            known_acceptance_ids=known_acceptance_ids,
            expected_acceptance_digest=acceptance_digest,
            allow_draft=allow_draft,
        )
        if "WITNESSES.json" in values
        else AuthoringReport()
    )
    kit_report = (
        _validate_kit(kit, capsule) if "KIT.json" in values else AuthoringReport()
    )

    report_map: dict[str, tuple[Any, str]] = {
        "ACCEPTANCE.json": (acceptance_report, "builder"),
        "WORK_ITEMS.json": (work_report, "builder"),
        "CAPABILITIES.json": (capability_report, "builder"),
        "AUTHORING.json": (authoring_report, "builder"),
        "WITNESSES.json": (witness_report, "builder"),
        "KIT.json": (kit_report, "runner"),
    }
    surfaces: dict[str, Any] = {}
    for name, (surface_report, owner) in report_map.items():
        errors = load_errors[name] + _report_errors(surface_report)
        surfaces[name] = _surface_result(
            root / name,
            values.get(name),
            owner=owner,
            errors=errors,
            warnings=list(getattr(surface_report, "warnings", [])),
            facts=dict(getattr(surface_report, "facts", {})),
            loaded=name in values,
            inspect_file=root_valid,
        )
    method_surface_errors = load_errors["METHOD-CAPSULE.json"] + [
        {"code": error, "location": "METHOD-CAPSULE.json", "message": error}
        for error in method_structural_errors
    ]
    surfaces["METHOD-CAPSULE.json"] = _surface_result(
        root / "METHOD-CAPSULE.json",
        capsule,
        owner="builder",
        errors=method_surface_errors,
        warnings=method_warnings,
        facts={
            "binding_state": capsule.get("binding_state") if isinstance(capsule, dict) else None,
            "method_version": capsule.get("method_version") if isinstance(capsule, dict) else None,
            "advisory_only": True,
            "authorizes_mutation": False,
        },
        loaded="METHOD-CAPSULE.json" in values,
        inspect_file=root_valid,
    )

    work_state = work.get("state") if isinstance(work, dict) else None
    witness_state = witnesses.get("state") if isinstance(witnesses, dict) else None
    capsule_digest = (
        sha256_json(capsule) if "METHOD-CAPSULE.json" in values else None
    )
    joins = [
        _identity_join(
            "work_to_acceptance",
            left="WORK_ITEMS.json.acceptance_ledger_digest",
            right="sha256(canonical ACCEPTANCE.json)",
            actual=work.get("acceptance_ledger_digest") if isinstance(work, dict) else None,
            expected=acceptance_digest or None,
            required=work_state == "compiled",
        ),
        _identity_join(
            "witnesses_to_acceptance",
            left="WITNESSES.json.acceptance_ledger_digest",
            right="sha256(canonical ACCEPTANCE.json)",
            actual=witnesses.get("acceptance_ledger_digest") if isinstance(witnesses, dict) else None,
            expected=acceptance_digest or None,
            required=witness_state == "compiled",
        ),
        _identity_join(
            "kit_to_method_capsule",
            left="KIT.json.method_capsule_digest",
            right="sha256(canonical METHOD-CAPSULE.json)",
            actual=kit.get("method_capsule_digest") if isinstance(kit, dict) else None,
            expected=capsule_digest,
            required=True,
        ),
    ]
    joins_valid = all(join["status"] in {"matched", "unbound"} for join in joins)
    structurally_valid = bool(
        not aggregate_errors
        and joins_valid
        and all(surface["structurally_valid"] for surface in surfaces.values())
    )
    witness_facts = witness_report.facts
    task_ready = bool(
        structurally_valid
        and acceptance_report.facts.get("task_ready")
        and work_report.facts.get("task_ready")
        and isinstance(capabilities, dict)
        and capabilities.get("state") == "compiled"
        and isinstance(capsule, dict)
        and capsule.get("binding_state") == "bound"
        and witness_state == "compiled"
        and witness_facts.get("coverage_complete")
    )
    return {
        "schema_version": AUTHORING_REPORT_SCHEMA,
        "kit_version": KIT_VERSION,
        "structurally_valid": structurally_valid,
        "task_ready": task_ready,
        "officially_deliverable": {
            "owner": "external_evaluator",
            "authority": "external",
            "status": "not_assessed",
        },
        "identity_joins": joins,
        "surfaces": surfaces,
        "errors": aggregate_errors,
        "boundaries": {
            "advisory_only": True,
            "read_only": True,
            "authorizes_mutation": False,
            "blocking_gate": False,
            "task_answer": "not_inferred",
            "pass_inferred": False,
        },
    }
