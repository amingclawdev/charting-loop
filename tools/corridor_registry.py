#!/usr/bin/env python3
"""Validate corridor artifacts and build the immutable registry index.

The validator deliberately uses only the Python standard library. It checks submitted
structure and evidence links; it does not execute corridor code or claim that a captured
conversation is semantically complete.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit


CORRIDOR_SCHEMA = "charting-loop/corridor/v1"
CANDIDATE_SCHEMA = "charting-loop/candidate/v2"
AUTHORITY_SCHEMA = "charting-loop/authority/v1"
EVALUATION_SCHEMA = "charting-loop/evaluation-result/v1"
REGISTRY_SCHEMA = "charting-loop/registry-entry/v1"
INDEX_SCHEMA = "charting-loop/registry-index/v1"
LEGACY_THEORY_INDEX_SCHEMA = "charting-loop/theory-index/v1"
THEORY_INDEX_SCHEMA = "charting-loop/theory-index/v2"
INPUT_BUNDLE_SCHEMA = "charting-loop/input-bundle/v1"
TASK_INDEX_SCHEMA = "charting-loop/task-index/v1"
LEGACY_METHOD_INDEX_SCHEMA = "charting-loop/method-index/v1"
METHOD_INDEX_SCHEMA = "charting-loop/method-index/v2"
METHOD_CLAIMS_SCHEMA = "charting-loop/method-claims/v1"
METHOD_SOURCES_SCHEMA = "charting-loop/method-sources/v1"
METHOD_EVIDENCE_INDEX_SCHEMA = "charting-loop/method-evidence-index/v1"
PUBLISHED_THEORY_VERSION_ID = "zenodo-v1"
PUBLISHED_THEORY_RECORD_DOI = "10.5281/zenodo.21844624"
PUBLISHED_THEORY_CONCEPT_DOI = "10.5281/zenodo.21844623"
PUBLISHED_THEORY_PUBLICATION_VERSION = "v1"
PUBLISHED_THEORY_SOURCE_COMMIT = "cf5ac479e208a2401b9358527d58df48e22c0670"
PUBLISHED_THEORY_REPRESENTATIONS = {
    (
        "pdf",
        "paper/charting-loop-zenodo.pdf",
        "083ca2c18dbbb44804208d081b70e7a161df1187",
        "sha256:f557af476441e814e4d86041969c18fde2299a6a47d28658bdeb8cec2d7296c1",
    ),
    (
        "source-archive",
        "paper/charting-loop-arxiv.tar.gz",
        "6bae14bbb194c604004adad2ac391fdda34901db",
        "sha256:1c7b2fafa1569809ca6923fc1682e44188c93a0e19cdd81b9746ecc7ad4de026",
    ),
}
ALLOWED_THEORY_PROVENANCE_ROLES = {"published-primary", "consulted-drafting"}
ALLOWED_METHOD_SOURCE_KINDS = {
    "primary-theory",
    "drafting-provenance",
    "repository-experience",
}
FIRST_TRAVERSAL_EVIDENCE_SCHEMA = "charting-loop/first-traversal-evidence/v1"
SCENARIO_EVIDENCE_SCHEMA = "charting-loop/scenario-evidence/v1"

ALLOWED_CORRIDOR_STATUS = {
    "candidate",
    "provisionally-charted",
    "currently-charted",
    "expired",
    "withdrawn",
}
ALLOWED_REGISTRY_STATUS = {"candidate", "evaluated", "invalid", "withdrawn"}
ALLOWED_TRACKS = {"reference", "domain"}
ALLOWED_KNOWLEDGE_ARMS = {
    "methodology",
    "theory-only",
    "control-none",
    "control-other",
    "not-applicable",
}
ALLOWED_SYSTEM_CONDITIONS = {"corridor", "no-corridor", "external-system"}
ALLOWED_COMPARISON_INTENTS = {
    "knowledge-effect",
    "system-effect",
    "authority-effect",
    "observational",
}
ALLOWED_WEB_ACCESS = {"disabled", "enabled", "unknown"}
ALLOWED_ARTIFACT_VERIFICATION = {"unresolved"}
ALLOWED_PUBLICATION_STATUS = {"public-complete", "public-redacted", "private"}
ALLOWED_AUTHORITY_ACTS = {
    "provision",
    "reframe",
    "redirect",
    "ratify",
    "repeal",
    "delegate",
}
ALLOWED_AUTHORITY_CONDITIONS = {
    "bootstrap-only",
    "standardized-interactive",
    "observational",
}
ALLOWED_CAPTURE_STATUS = {"complete", "partial", "unavailable"}
ALLOWED_CHANNELS = {"user", "assistant"}
ALLOWED_EFFECTS = {"issued", "approved", "rejected", "revoked", "delegated"}
AUTHORITY_ACT_MATRIX = {
    "provision": ({"issued"}, {"input-bundle"}),
    "reframe": ({"issued"}, {"position-representation"}),
    "redirect": ({"issued"}, {"direction"}),
    "ratify": ({"approved", "rejected"}, {"corridor-revision", "rule"}),
    "repeal": ({"revoked"}, {"corridor-revision", "rule", "authority-scope"}),
    "delegate": ({"delegated"}, {"authority-scope"}),
}
ALLOWED_AUTHORITY_TARGETS = {
    "input-bundle",
    "position-representation",
    "direction",
    "corridor-revision",
    "rule",
    "authority-scope",
}
ALLOWED_EVALUATION_STATUS = {"not-run", "passed", "failed", "blocked", "invalid"}
ALLOWED_SCENARIO_STATUS = {"passed", "failed", "blocked", "not-run"}
SCENARIO_IDS = tuple(f"S{number}" for number in range(1, 7))
ALLOWED_FAILURE_FACTORS = {"P", "D", "E"}
ALLOWED_CLASSIFICATION_STATUS = {"classified", "not-classifiable", "not-assessed"}
ALLOWED_INPUT_ROLES = {
    "builder-task",
    "theory",
    "methodology",
    "generic-control",
    "other-framework",
    "instrumentation",
    "attachment",
}
ALLOWED_ASSESSMENT_ROLES = {"subject-diagnosis", "evaluator-assessment"}
ALLOWED_DIAGNOSIS_VERDICTS = {"drift", "no-drift", "abstain"}

CANONICAL_CORRIDOR_PATHS = {
    "authority_design_path": "authority/DESIGN.md",
    "condition_protocol_path": "authority/CONDITION.md",
    "input_manifest_path": "inputs/INPUTS.json",
    "manifest_path": "authority/AUTHORITY.json",
    "interaction_log_path": "authority/interactions.jsonl",
    "event_log_path": "authority/events.jsonl",
    "corridor_path": "corridor",
    "trace_path": "trace",
    "evaluation_path": "evaluation",
    "assessment_log_path": "evaluation/ASSESSMENTS.jsonl",
}

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
PLACEHOLDER_RE = re.compile(r"(?:__[^_]+__|\bREPLACE\b|\bTODO\b)", re.IGNORECASE)
GITHUB_REPOSITORY_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_JSONL_BYTES = 20 * 1024 * 1024
MAX_TREE_FILE_BYTES = 50 * 1024 * 1024
MAX_TREE_TOTAL_BYTES = 500 * 1024 * 1024
MAX_TREE_FILES = 10_000


@dataclass
class Report:
    subject: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, location: str, message: str) -> None:
        self.errors.append(f"{code} {location} {message}")

    def warn(self, code: str, location: str, message: str) -> None:
        self.warnings.append(f"{code} {location} {message}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "structurally_valid": self.ok,
            "indexable": (
                self.ok
                and not self.facts.get("template", False)
                and self.facts.get("registry_eligible", True)
            ),
            "authority_evidence_structurally_complete": (
                self.ok
                and not self.facts.get("template", False)
                and self.facts.get("authority_capture") == "complete"
                and self.facts.get("authority_condition") != "observational"
                and self.facts.get("redacted_interactions", 0) == 0
                and self.facts.get("redacted_authority_sources", 0) == 0
            ),
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _find_surrogate(value: Any, location: str = "$") -> str | None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            return location
    elif isinstance(value, dict):
        for key, child in value.items():
            found = _find_surrogate(key, f"{location}.<key>") or _find_surrogate(
                child, f"{location}.{key}"
            )
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_surrogate(child, f"{location}[{index}]")
            if found:
                return found
    return None


def load_json(path: Path, report: Report, label: str) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            report.error("FILE_SIZE", str(path), f"JSON exceeds {MAX_JSON_BYTES} bytes")
            return None
        raw = path.read_bytes()
    except OSError as exc:
        report.error("FILE_READ", str(path), str(exc))
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        report.error("JSON_BOM", str(path), "UTF-8 BOM is forbidden")
        return None
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        report.error("JSON_PARSE", str(path), f"invalid {label}: {exc}")
        return None
    if not isinstance(value, dict):
        report.error("JSON_TYPE", str(path), f"{label} must be a JSON object")
        return None
    try:
        surrogate = _find_surrogate(value)
    except RecursionError as exc:
        report.error("JSON_DEPTH", str(path), f"JSON nesting is too deep: {exc}")
        return None
    if surrogate:
        report.error("JSON_SURROGATE", str(path), f"unpaired Unicode surrogate at {surrogate}")
        return None
    return value


def load_jsonl(path: Path, report: Report, label: str) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > MAX_JSONL_BYTES:
            report.error("FILE_SIZE", str(path), f"JSONL exceeds {MAX_JSONL_BYTES} bytes")
            return []
        raw = path.read_bytes()
    except OSError as exc:
        report.error("FILE_READ", str(path), str(exc))
        return []
    if raw.startswith(b"\xef\xbb\xbf"):
        report.error("JSONL_BOM", str(path), "UTF-8 BOM is forbidden")
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.error("JSONL_UTF8", str(path), str(exc))
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            report.error("JSONL_BLANK", f"{path}:{line_number}", "blank lines are forbidden")
            continue
        try:
            value = json.loads(
                line,
                object_pairs_hook=_strict_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            report.error("JSONL_PARSE", f"{path}:{line_number}", f"invalid {label}: {exc}")
            continue
        if not isinstance(value, dict):
            report.error("JSONL_TYPE", f"{path}:{line_number}", "record must be an object")
            continue
        try:
            surrogate = _find_surrogate(value)
        except RecursionError as exc:
            report.error("JSONL_DEPTH", f"{path}:{line_number}", f"JSON nesting is too deep: {exc}")
            continue
        if surrogate:
            report.error("JSONL_SURROGATE", f"{path}:{line_number}", f"unpaired Unicode surrogate at {surrogate}")
            continue
        records.append(value)
    return records


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def sha256_json_value(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def authority_boundary_design_digest(actors: Any) -> str:
    """Hash the authority roles and powers without run-local identities or treatment.

    Actor IDs, timestamps, and the assigned condition belong to an individual run.
    Omitting them here lets otherwise identical authority boundaries be matched across
    an authority-effect experiment while the exact assignment remains independently
    pinned by ``assignment_sha256``.
    """
    normalized: list[dict[str, Any]] = []
    if isinstance(actors, list):
        for actor in actors:
            if not isinstance(actor, dict):
                continue
            acts = actor.get("authorized_acts")
            scopes = actor.get("authority_scope")
            normalized.append(
                {
                    "role": actor.get("role"),
                    "actor_type": actor.get("actor_type"),
                    "authorized_acts": sorted(
                        value for value in acts if isinstance(value, str)
                    )
                    if isinstance(acts, list)
                    else acts,
                    "authority_scope": sorted(
                        value for value in scopes if isinstance(value, str)
                    )
                    if isinstance(scopes, list)
                    else scopes,
                }
            )
    normalized.sort(
        key=lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    )
    return sha256_json_value(
        {"schema_version": AUTHORITY_SCHEMA, "actors": normalized}
    )


def digest_tree_records(records: Iterable[dict[str, Any]]) -> str:
    canonical = json.dumps(
        sorted(records, key=lambda item: item["path"]),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def hash_tree(
    root: Path, include_roots: Iterable[str] | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Hash a file tree through a canonical path/size/content-digest manifest."""
    root = root.resolve()
    bases = [root / value for value in include_roots] if include_roots else [root]
    records: list[dict[str, Any]] = []
    total_size = 0
    for base in bases:
        if not base.exists():
            raise ValueError(f"tree member is missing: {base}")
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"symbolic links are forbidden: {path}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"non-regular tree member is forbidden: {path}")
            stat_result = path.stat()
            size = stat_result.st_size
            if size > MAX_TREE_FILE_BYTES:
                raise ValueError(f"tree file exceeds {MAX_TREE_FILE_BYTES} bytes: {path}")
            total_size += size
            if total_size > MAX_TREE_TOTAL_BYTES:
                raise ValueError(f"tree exceeds {MAX_TREE_TOTAL_BYTES} total bytes")
            if len(records) >= MAX_TREE_FILES:
                raise ValueError(f"tree exceeds {MAX_TREE_FILES} files")
            records.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "mode": "100755" if stat_result.st_mode & 0o111 else "100644",
                    "size": size,
                    "sha256": sha256_file(path),
                }
            )
    records.sort(key=lambda item: item["path"])
    return digest_tree_records(records), records


def _require_string(
    obj: dict[str, Any], key: str, report: Report, location: str
) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        report.error("REQUIRED_STRING", f"{location}.{key}", "must be a non-empty string")
        return None
    return value


def _require_list(
    obj: dict[str, Any], key: str, report: Report, location: str
) -> list[Any] | None:
    value = obj.get(key)
    if not isinstance(value, list):
        report.error("REQUIRED_LIST", f"{location}.{key}", "must be an array")
        return None
    return value


def _require_string_list(
    obj: dict[str, Any], key: str, report: Report, location: str
) -> list[str]:
    values = _require_list(obj, key, report, location)
    if values is None:
        return []
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            report.error(
                "STRING_LIST",
                f"{location}.{key}[{index}]",
                "must be a non-empty string",
            )
        else:
            result.append(value)
    return result


def _require_object(
    obj: dict[str, Any], key: str, report: Report, location: str
) -> dict[str, Any] | None:
    value = obj.get(key)
    if not isinstance(value, dict):
        report.error("REQUIRED_OBJECT", f"{location}.{key}", "must be an object")
        return None
    return value


def _check_datetime(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, str):
        report.error("DATETIME", location, "must be an ISO-8601 datetime string")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        report.error("DATETIME", location, "must be an ISO-8601 datetime string")
        return
    if parsed.tzinfo is None:
        report.error("DATETIME_TZ", location, "must include a timezone offset")


def _check_date(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, str):
        report.error("DATE", location, "must be an ISO date")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        report.error("DATE", location, "must be an ISO date")


def _safe_member(root: Path, value: Any, report: Report, location: str) -> Path | None:
    if not isinstance(value, str) or not value:
        report.error("PATH", location, "must be a non-empty relative path")
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        report.error("PATH_CONTROL", location, "control characters are forbidden in paths")
        return None
    candidate_text = Path(value)
    if candidate_text.is_absolute() or ".." in candidate_text.parts or "\\" in value:
        report.error("PATH_ESCAPE", location, "absolute, parent, and backslash paths are forbidden")
        return None
    cursor = root
    for part in candidate_text.parts:
        cursor = cursor / part
        try:
            is_symlink = cursor.is_symlink()
        except (OSError, ValueError) as exc:
            report.error("PATH", location, f"cannot inspect path safely: {exc}")
            return None
        if is_symlink:
            report.error("PATH_SYMLINK", location, f"symbolic links are forbidden: {cursor}")
            return None
    try:
        candidate = (root / candidate_text).resolve()
        resolved_root = root.resolve()
    except (OSError, ValueError) as exc:
        report.error("PATH", location, f"cannot resolve path safely: {exc}")
        return None
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        report.error("PATH_ESCAPE", location, "path escapes the corridor root")
        return None
    return candidate


def _check_digest(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        report.error("SHA256", location, "must be sha256:<64 lowercase hex characters>")
    elif value == "sha256:" + ("0" * 64):
        report.error("SHA256_SENTINEL", location, "all-zero placeholder digests are forbidden")


def _check_registry_relative_path(
    value: Any, report: Report, location: str
) -> str | None:
    if not isinstance(value, str) or not value:
        report.error("ARTIFACT_ROOT", location, "must be a non-empty relative POSIX path")
        return None
    if (
        value.startswith("/")
        or "\\" in value
        or value.endswith("/")
        or "//" in value
        or re.fullmatch(r"[A-Za-z0-9._/-]+", value) is None
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        report.error(
            "ARTIFACT_ROOT",
            location,
            "must be canonical, relative, slash-separated, and contain no . or .. segments",
        )
        return None
    return value


def _escape_markdown_cell(value: Any) -> str:
    text = html.escape(str(value or "").replace("\n", " "), quote=True)
    for character in ("\\", "|", "[", "]", "(", ")", "`"):
        text = text.replace(character, "\\" + character)
    return text


def _check_enum(
    value: Any,
    allowed: set[str],
    report: Report,
    location: str,
) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        report.error("ENUM", location, f"must be one of {sorted(allowed)}")
        return None
    return value


def _comparison_key(entry: dict[str, Any]) -> str:
    """Derive an axis-specific matching key for the declared comparison intent.

    Exactly the nominated treatment axis is omitted. Model, runtime, and date remain
    explicit stratification columns rather than being silently baked into the key.
    """
    experiment = entry.get("experiment", {})
    authority = entry.get("authority_evidence", {})
    analysis_theory = entry.get("analysis_theory_ref", {})
    intent = experiment.get("comparison_intent")
    payload: dict[str, Any] = {
        "comparison_intent": intent,
        "track": experiment.get("track"),
        "task_sha256": experiment.get("task_sha256"),
        "evaluation_protocol_sha256": experiment.get("evaluation_protocol_sha256"),
        "analysis_theory_version_id": analysis_theory.get("version_id"),
        "analysis_theory_source_commit": analysis_theory.get("source_commit"),
        "analysis_theory_representation": analysis_theory.get("representation"),
        "analysis_theory_content_sha256": analysis_theory.get("content_sha256"),
        "authority_design_sha256": authority.get("design_sha256"),
        "authority_boundary_design_sha256": authority.get("boundary_design_sha256"),
        "common_inputs_sha256": experiment.get("common_inputs_sha256"),
    }
    if intent == "knowledge-effect":
        payload.update(
            {
                "system_condition": experiment.get("system_condition"),
                "authority_input_condition": authority.get("input_condition"),
                "authority_condition_protocol_sha256": authority.get("condition_protocol_sha256"),
            }
        )
    elif intent == "system-effect":
        payload.update(
            {
                "knowledge_arm": experiment.get("knowledge_arm"),
                "treatment_inputs_sha256": experiment.get("treatment_inputs_sha256"),
                "authority_input_condition": authority.get("input_condition"),
                "authority_condition_protocol_sha256": authority.get("condition_protocol_sha256"),
            }
        )
    elif intent == "authority-effect":
        payload.update(
            {
                "knowledge_arm": experiment.get("knowledge_arm"),
                "system_condition": experiment.get("system_condition"),
                "treatment_inputs_sha256": experiment.get("treatment_inputs_sha256"),
            }
        )
    else:
        payload.update(
            {
                "knowledge_arm": experiment.get("knowledge_arm"),
                "system_condition": experiment.get("system_condition"),
                "treatment_inputs_sha256": experiment.get("treatment_inputs_sha256"),
                "authority_input_condition": authority.get("input_condition"),
                "authority_condition_protocol_sha256": authority.get("condition_protocol_sha256"),
            }
        )
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def validate_theory_index(path: Path) -> tuple[Report, list[dict[str, Any]]]:
    report = Report(subject=str(path.resolve()))
    document = load_json(path, report, "theory index")
    if document is None:
        return report, []
    schema_version = document.get("schema_version")
    if not isinstance(schema_version, str) or (
        schema_version != LEGACY_THEORY_INDEX_SCHEMA
        and schema_version != THEORY_INDEX_SCHEMA
    ):
        report.error(
            "SCHEMA_VERSION",
            str(path),
            f"expected {LEGACY_THEORY_INDEX_SCHEMA} or {THEORY_INDEX_SCHEMA}",
        )
    strict_publication_schema = schema_version == THEORY_INDEX_SCHEMA
    if strict_publication_schema and set(document) != {"schema_version", "artifacts"}:
        report.error(
            "THEORY_INDEX_FIELDS",
            path.name,
            "must contain exactly schema_version and artifacts",
        )
    artifacts = _require_list(document, "artifacts", report, path.name) or []
    valid: list[dict[str, Any]] = []
    seen_versions: set[str] = set()
    seen_representations: set[tuple[str, str, str]] = set()
    published_primary_count = 0
    published_primary: dict[str, Any] | None = None
    for index, artifact in enumerate(artifacts):
        location = f"{path.name}.artifacts[{index}]"
        error_count = len(report.errors)
        if not isinstance(artifact, dict):
            report.error("THEORY_ARTIFACT", location, "must be an object")
            continue
        allowed_artifact = {
            "version_id",
            "artifact_id",
            "version_labels",
            "source",
            "representations",
            "notes",
        }
        if strict_publication_schema:
            allowed_artifact.update({"provenance_role", "publication"})
        if strict_publication_schema and set(artifact) != allowed_artifact:
            report.error(
                "THEORY_ARTIFACT_FIELDS",
                location,
                f"must contain exactly {sorted(allowed_artifact)}",
            )
        version_id = _require_string(artifact, "version_id", report, location)
        artifact_id = _require_string(artifact, "artifact_id", report, location)
        if version_id in seen_versions:
            report.error("DUPLICATE_VERSION", location, f"duplicate version_id {version_id!r}")
        elif version_id:
            seen_versions.add(version_id)
        labels = _require_object(artifact, "version_labels", report, location)
        if labels is not None:
            for key, value in labels.items():
                if not isinstance(key, str) or not isinstance(value, str) or not value:
                    report.error("VERSION_LABEL", f"{location}.version_labels", "labels must map strings to non-empty strings")
        provenance_role = artifact.get("provenance_role")
        publication = artifact.get("publication")
        if strict_publication_schema:
            _check_enum(
                provenance_role,
                ALLOWED_THEORY_PROVENANCE_ROLES,
                report,
                f"{location}.provenance_role",
            )
        if strict_publication_schema and provenance_role == "published-primary":
            published_primary_count += 1
            published_primary = artifact
            publication_fields = {
                "provider",
                "record_doi",
                "concept_doi",
                "record_url",
                "version",
                "publication_date",
                "resource_type",
                "license",
            }
            if not isinstance(publication, dict):
                report.error(
                    "THEORY_PUBLICATION",
                    f"{location}.publication",
                    "published-primary requires a publication object",
                )
            else:
                if set(publication) != publication_fields:
                    report.error(
                        "THEORY_PUBLICATION_FIELDS",
                        f"{location}.publication",
                        f"must contain exactly {sorted(publication_fields)}",
                    )
                expected_publication = {
                    "provider": "zenodo",
                    "record_doi": PUBLISHED_THEORY_RECORD_DOI,
                    "concept_doi": PUBLISHED_THEORY_CONCEPT_DOI,
                    "record_url": "https://zenodo.org/records/21844624",
                    "version": PUBLISHED_THEORY_PUBLICATION_VERSION,
                    "publication_date": "2026-08-08",
                    "resource_type": "publication-preprint",
                    "license": "cc-by-4.0",
                }
                if publication != expected_publication:
                    report.error(
                        "THEORY_PUBLICATION_IDENTITY",
                        f"{location}.publication",
                        "must match the exact published Theory v1 Zenodo record",
                    )
            if version_id != PUBLISHED_THEORY_VERSION_ID or artifact_id != "charting-loop-theory":
                report.error(
                    "THEORY_PUBLICATION_VERSION",
                    location,
                    "published-primary must be charting-loop-theory zenodo-v1",
                )
        elif strict_publication_schema and publication is not None:
            report.error(
                "THEORY_PUBLICATION",
                f"{location}.publication",
                "consulted drafting artifacts must declare publication as null",
            )
        source = _require_object(artifact, "source", report, location)
        commit: str | None = None
        if source is not None:
            source_fields = {
                "repository_id",
                "repository_url",
                "commit",
                "tag",
                "tag_signature",
            }
            if strict_publication_schema and set(source) != source_fields:
                report.error(
                    "THEORY_SOURCE_FIELDS",
                    f"{location}.source",
                    f"must contain exactly {sorted(source_fields)}",
                )
            _require_string(source, "repository_id", report, f"{location}.source")
            repository_url = source.get("repository_url")
            if repository_url is not None and (
                not isinstance(repository_url, str) or not repository_url.startswith("https://")
            ):
                report.error("REPOSITORY_URL", f"{location}.source.repository_url", "must be HTTPS or null")
            commit = source.get("commit")
            if not isinstance(commit, str) or not GIT_SHA1_RE.fullmatch(commit):
                report.error("GIT_COMMIT", f"{location}.source.commit", "must be a full lowercase SHA-1 commit")
            tag = source.get("tag")
            tag_signature = source.get("tag_signature")
            if not strict_publication_schema:
                _require_string(source, "tag", report, f"{location}.source")
                _check_enum(
                    tag_signature,
                    {"verified", "unverified"},
                    report,
                    f"{location}.source.tag_signature",
                )
            elif tag is None:
                if tag_signature != "not-applicable":
                    report.error(
                        "THEORY_TAG",
                        f"{location}.source.tag_signature",
                        "an untagged commit must use not-applicable",
                    )
            else:
                if not isinstance(tag, str) or not tag:
                    report.error(
                        "THEORY_TAG",
                        f"{location}.source.tag",
                        "must be a non-empty string or null",
                    )
                _check_enum(
                    tag_signature,
                    {"verified", "unverified"},
                    report,
                    f"{location}.source.tag_signature",
                )
        representations = _require_list(artifact, "representations", report, location) or []
        if not representations:
            report.error("THEORY_REPRESENTATION", f"{location}.representations", "must not be empty")
        for rep_index, representation in enumerate(representations):
            rep_location = f"{location}.representations[{rep_index}]"
            if not isinstance(representation, dict):
                report.error("THEORY_REPRESENTATION", rep_location, "must be an object")
                continue
            representation_fields = {"kind", "path", "git_blob_sha1", "sha256"}
            if strict_publication_schema and set(representation) != representation_fields:
                report.error(
                    "THEORY_REPRESENTATION_FIELDS",
                    rep_location,
                    f"must contain exactly {sorted(representation_fields)}",
                )
            kind = _require_string(representation, "kind", report, rep_location)
            _require_string(representation, "path", report, rep_location)
            blob = representation.get("git_blob_sha1")
            if not isinstance(blob, str) or not GIT_SHA1_RE.fullmatch(blob):
                report.error("GIT_BLOB", f"{rep_location}.git_blob_sha1", "must be a full lowercase SHA-1 object id")
            _check_digest(representation.get("sha256"), report, f"{rep_location}.sha256")
            key = (str(artifact_id), str(commit), str(kind))
            if key in seen_representations:
                report.error("DUPLICATE_REPRESENTATION", rep_location, f"duplicate catalog key {key!r}")
            else:
                seen_representations.add(key)
        if strict_publication_schema and provenance_role == "published-primary":
            actual_representations: set[tuple[str, str, str, str]] = set()
            for representation in representations:
                if not isinstance(representation, dict):
                    continue
                identity = (
                    representation.get("kind"),
                    representation.get("path"),
                    representation.get("git_blob_sha1"),
                    representation.get("sha256"),
                )
                if all(isinstance(value, str) for value in identity):
                    actual_representations.add(identity)  # type: ignore[arg-type]
            if commit != PUBLISHED_THEORY_SOURCE_COMMIT:
                report.error(
                    "THEORY_PUBLICATION_COMMIT",
                    f"{location}.source.commit",
                    "must match the Git commit containing the deposited v1 bytes",
                )
            if actual_representations != PUBLISHED_THEORY_REPRESENTATIONS:
                report.error(
                    "THEORY_PUBLICATION_BYTES",
                    f"{location}.representations",
                    "must match the exact deposited v1 PDF and source archive identities",
                )
        notes = (
            _require_string_list(artifact, "notes", report, location)
            if strict_publication_schema
            else []
        )
        if strict_publication_schema and not notes:
            report.error(
                "THEORY_NOTES",
                f"{location}.notes",
                "must be a non-empty string list",
            )
        if len(report.errors) == error_count:
            valid.append(artifact)
    if strict_publication_schema and published_primary_count != 1:
        report.error(
            "THEORY_PRIMARY_COUNT",
            f"{path.name}.artifacts",
            "must contain exactly one published-primary theory artifact",
        )
    report.facts["version_count"] = len(valid)
    report.facts["schema_version"] = schema_version
    report.facts["published_primary_count"] = published_primary_count
    report.facts["published_theory_record_doi"] = (
        published_primary.get("publication", {}).get("record_doi")
        if isinstance(published_primary, dict)
        and isinstance(published_primary.get("publication"), dict)
        else None
    )
    return report, valid


def _read_git_object(
    source_root: Path,
    arguments: list[str],
    report: Report,
    location: str,
) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report.error("THEORY_SOURCE_GIT", location, f"cannot run Git resolver: {exc}")
        return None
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        report.error(
            "THEORY_SOURCE_GIT",
            location,
            detail or f"Git command failed with exit {completed.returncode}",
        )
        return None
    if len(completed.stdout) > MAX_TREE_FILE_BYTES:
        report.error(
            "THEORY_SOURCE_SIZE",
            location,
            f"resolved Git object exceeds {MAX_TREE_FILE_BYTES} bytes",
        )
        return None
    return completed.stdout


def validate_theory_source_checkout(
    source_root: Path,
    versions: list[dict[str, Any]],
    report: Report,
) -> None:
    """Resolve catalog entries against exact objects in a trusted local Git checkout."""
    source_root = source_root.resolve()
    if not source_root.is_dir():
        report.error("THEORY_SOURCE_ROOT", str(source_root), "must be a directory")
        return
    inside = _read_git_object(
        source_root,
        ["rev-parse", "--is-inside-work-tree"],
        report,
        str(source_root),
    )
    if inside is None or inside.strip() != b"true":
        if inside is not None:
            report.error("THEORY_SOURCE_ROOT", str(source_root), "is not a Git work tree")
        return

    resolved_count = 0
    for version_index, version in enumerate(versions):
        location = f"theory.artifacts[{version_index}]"
        source = version.get("source") if isinstance(version, dict) else None
        representations = version.get("representations") if isinstance(version, dict) else None
        if not isinstance(source, dict) or not isinstance(representations, list):
            continue
        commit = source.get("commit")
        if not isinstance(commit, str):
            continue
        resolved_commit = _read_git_object(
            source_root,
            ["rev-parse", "--verify", f"{commit}^{{commit}}"],
            report,
            f"{location}.source.commit",
        )
        if resolved_commit is not None and resolved_commit.decode("ascii", errors="replace").strip() != commit:
            report.error(
                "THEORY_SOURCE_COMMIT",
                f"{location}.source.commit",
                "does not resolve to the declared commit",
            )
        tag = source.get("tag")
        if isinstance(tag, str):
            resolved_tag = _read_git_object(
                source_root,
                ["rev-list", "-n", "1", tag],
                report,
                f"{location}.source.tag",
            )
            if resolved_tag is not None and resolved_tag.decode("ascii", errors="replace").strip() != commit:
                report.error(
                    "THEORY_SOURCE_TAG",
                    f"{location}.source.tag",
                    "does not point to the declared commit",
                )
        for representation_index, representation in enumerate(representations):
            rep_location = f"{location}.representations[{representation_index}]"
            if not isinstance(representation, dict):
                continue
            path_value = representation.get("path")
            if (
                not isinstance(path_value, str)
                or not path_value
                or Path(path_value).is_absolute()
                or "\\" in path_value
                or ".." in Path(path_value).parts
            ):
                report.error(
                    "THEORY_SOURCE_PATH",
                    f"{rep_location}.path",
                    "must be a safe relative POSIX path",
                )
                continue
            object_spec = f"{commit}:{path_value}"
            resolved_blob = _read_git_object(
                source_root,
                ["rev-parse", object_spec],
                report,
                f"{rep_location}.git_blob_sha1",
            )
            if resolved_blob is not None and resolved_blob.decode("ascii", errors="replace").strip() != representation.get("git_blob_sha1"):
                report.error(
                    "THEORY_SOURCE_BLOB",
                    f"{rep_location}.git_blob_sha1",
                    "does not match the blob at the declared commit and path",
                )
            content = _read_git_object(
                source_root,
                ["cat-file", "blob", object_spec],
                report,
                f"{rep_location}.sha256",
            )
            if content is not None:
                actual_digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
                if actual_digest != representation.get("sha256"):
                    report.error(
                        "THEORY_SOURCE_SHA256",
                        f"{rep_location}.sha256",
                        "does not match the bytes at the declared commit and path",
                    )
                else:
                    resolved_count += 1
    report.facts["resolved_representation_count"] = resolved_count


def _validate_theory_reference(
    reference: dict[str, Any],
    versions: list[dict[str, Any]],
    report: Report,
    location: str,
) -> None:
    matches = []
    for version in versions:
        if not isinstance(version, dict):
            continue
        source = version.get("source")
        representations = version.get("representations")
        if not isinstance(source, dict) or not isinstance(representations, list):
            continue
        for representation in representations:
            if not isinstance(representation, dict):
                continue
            if (
                version.get("version_id") == reference.get("version_id")
                and version.get("artifact_id") == reference.get("artifact_id")
                and source.get("commit") == reference.get("source_commit")
                and representation.get("kind") == reference.get("representation")
                and representation.get("sha256") == reference.get("content_sha256")
            ):
                matches.append(version)
    if len(matches) != 1:
        report.error(
            "THEORY_CATALOG_REF",
            location,
            "must match exactly one cataloged artifact/commit/representation/digest",
        )


def validate_task_index(path: Path) -> tuple[Report, list[dict[str, Any]]]:
    report = Report(subject=str(path.resolve()))
    document = load_json(path, report, "task index")
    if document is None:
        return report, []
    if document.get("schema_version") != TASK_INDEX_SCHEMA:
        report.error("SCHEMA_VERSION", str(path), f"expected {TASK_INDEX_SCHEMA}")
    tasks = _require_list(document, "tasks", report, path.name) or []
    project_root = path.resolve().parents[1]
    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        location = f"{path.name}.tasks[{index}]"
        error_count = len(report.errors)
        if not isinstance(task, dict):
            report.error("TASK_RECORD", location, "must be an object")
            continue
        task_id = _require_string(task, "task_id", report, location)
        if task_id in seen:
            report.error("DUPLICATE_TASK", location, f"duplicate task_id {task_id!r}")
        elif task_id:
            seen.add(task_id)
        builder_brief = _require_object(task, "builder_brief", report, location)
        if builder_brief is not None:
            brief_path = _safe_member(project_root, builder_brief.get("path"), report, f"{location}.builder_brief.path")
            brief_digest = builder_brief.get("sha256")
            _check_digest(brief_digest, report, f"{location}.builder_brief.sha256")
            if brief_path is not None:
                if not brief_path.is_file():
                    report.error("REQUIRED_FILE", str(brief_path), "builder brief is missing")
                elif SHA256_RE.fullmatch(str(brief_digest)) and sha256_file(brief_path) != brief_digest:
                    report.error("FILE_HASH", f"{location}.builder_brief.sha256", "does not match task bytes")
        instrumentation = _require_list(
            task, "common_instrumentation", report, location
        ) or []
        if not instrumentation:
            report.error(
                "TASK_INSTRUMENTATION",
                f"{location}.common_instrumentation",
                "must contain the frozen common builder instrumentation",
            )
        instrumentation_paths: set[str] = set()
        for instrumentation_index, instrumentation_record in enumerate(instrumentation):
            instrumentation_location = (
                f"{location}.common_instrumentation[{instrumentation_index}]"
            )
            if not isinstance(instrumentation_record, dict):
                report.error(
                    "TASK_INSTRUMENTATION",
                    instrumentation_location,
                    "must be an object",
                )
                continue
            path_value = instrumentation_record.get("path")
            instrumentation_path = _safe_member(
                project_root,
                path_value,
                report,
                f"{instrumentation_location}.path",
            )
            digest = instrumentation_record.get("sha256")
            _check_digest(digest, report, f"{instrumentation_location}.sha256")
            if isinstance(path_value, str):
                if path_value in instrumentation_paths:
                    report.error(
                        "TASK_INSTRUMENTATION",
                        f"{instrumentation_location}.path",
                        "duplicate instrumentation path",
                    )
                instrumentation_paths.add(path_value)
            if instrumentation_path is not None:
                if not instrumentation_path.is_file():
                    report.error(
                        "REQUIRED_FILE",
                        str(instrumentation_path),
                        "common instrumentation is missing",
                    )
                elif SHA256_RE.fullmatch(str(digest)) and sha256_file(instrumentation_path) != digest:
                    report.error(
                        "FILE_HASH",
                        f"{instrumentation_location}.sha256",
                        "does not match common instrumentation bytes",
                    )
        subject_prompt = _require_object(
            task, "subject_diagnosis_prompt", report, location
        )
        subject_prompt_path_value: str | None = None
        subject_prompt_digest: Any = None
        if subject_prompt is not None:
            subject_prompt_path_value = _require_string(
                subject_prompt,
                "path",
                report,
                f"{location}.subject_diagnosis_prompt",
            )
            subject_prompt_path = _safe_member(
                project_root,
                subject_prompt_path_value,
                report,
                f"{location}.subject_diagnosis_prompt.path",
            )
            subject_prompt_digest = subject_prompt.get("sha256")
            _check_digest(
                subject_prompt_digest,
                report,
                f"{location}.subject_diagnosis_prompt.sha256",
            )
            if subject_prompt_path is not None:
                if not subject_prompt_path.is_file():
                    report.error(
                        "REQUIRED_FILE",
                        str(subject_prompt_path),
                        "subject diagnosis prompt is missing",
                    )
                elif SHA256_RE.fullmatch(str(subject_prompt_digest)) and sha256_file(subject_prompt_path) != subject_prompt_digest:
                    report.error(
                        "FILE_HASH",
                        f"{location}.subject_diagnosis_prompt.sha256",
                        "does not match the frozen subject prompt bytes",
                    )
        evaluation = _require_object(task, "evaluation_protocol", report, location)
        if evaluation is not None:
            tree_digest = evaluation.get("tree_sha256")
            _check_digest(tree_digest, report, f"{location}.evaluation_protocol.tree_sha256")
            files = _require_list(evaluation, "files", report, f"{location}.evaluation_protocol") or []
            if not files:
                report.error(
                    "TASK_FILES",
                    f"{location}.evaluation_protocol.files",
                    "must contain the frozen evaluator protocol files",
                )
            file_paths: list[str] = []
            seen_file_paths: set[str] = set()
            for file_index, file_record in enumerate(files):
                file_location = f"{location}.evaluation_protocol.files[{file_index}]"
                if not isinstance(file_record, dict):
                    report.error("TASK_FILE", file_location, "must be an object")
                    continue
                file_path_value = file_record.get("path")
                file_path = _safe_member(project_root, file_path_value, report, f"{file_location}.path")
                file_digest = file_record.get("sha256")
                _check_digest(file_digest, report, f"{file_location}.sha256")
                if isinstance(file_path_value, str):
                    if file_path_value in seen_file_paths:
                        report.error(
                            "DUPLICATE_TASK_FILE",
                            f"{file_location}.path",
                            f"duplicate evaluator protocol path {file_path_value!r}",
                        )
                    else:
                        seen_file_paths.add(file_path_value)
                    file_paths.append(file_path_value)
                if file_path is not None:
                    if not file_path.is_file():
                        report.error("REQUIRED_FILE", str(file_path), "evaluation protocol file is missing")
                    elif SHA256_RE.fullmatch(str(file_digest)) and sha256_file(file_path) != file_digest:
                        report.error("FILE_HASH", f"{file_location}.sha256", "does not match evaluator bytes")
            if task_id and not {"TASK.md", "RATIONALE.md"}.issubset(
                {Path(value).name for value in file_paths}
            ):
                report.error(
                    "TASK_FILES",
                    f"{location}.evaluation_protocol.files",
                    "must include frozen TASK.md and RATIONALE.md evaluator files",
                )
            if subject_prompt_path_value is not None and not any(
                isinstance(file_record, dict)
                and file_record.get("path") == subject_prompt_path_value
                and file_record.get("sha256") == subject_prompt_digest
                for file_record in files
            ):
                report.error(
                    "TASK_SUBJECT_PROMPT",
                    f"{location}.evaluation_protocol.files",
                    "must include the exact frozen subject diagnosis prompt",
                )
            if file_paths:
                try:
                    actual_tree_digest, _ = hash_tree(project_root, file_paths)
                except (OSError, ValueError) as exc:
                    report.error("TASK_TREE", location, str(exc))
                else:
                    if SHA256_RE.fullmatch(str(tree_digest)) and actual_tree_digest != tree_digest:
                        report.error("TASK_TREE_HASH", f"{location}.evaluation_protocol.tree_sha256", "does not match evaluator file tree")
        if len(report.errors) == error_count:
            valid.append(task)
    report.facts["task_count"] = len(valid)
    return report, valid


def _validate_method_provenance_catalogs(
    project_root: Path,
    method_version_id: str | None,
    catalog_paths: dict[str, Path],
    report: Report,
    theory_versions: list[dict[str, Any]] | None = None,
    theory_schema_version: str | None = None,
    method_lineage: dict[str, Any] | None = None,
) -> None:
    report.facts["method_provenance_join_status"] = "invalid"
    strict_theory_roles = theory_schema_version == THEORY_INDEX_SCHEMA
    claims_doc = load_json(catalog_paths["claim_catalog"], report, "method claim catalog")
    sources_doc = load_json(catalog_paths["source_catalog"], report, "method source catalog")
    evidence_doc = load_json(catalog_paths["evidence_index"], report, "method evidence index")
    if claims_doc is None or sources_doc is None or evidence_doc is None:
        return

    catalog_specs = (
        (claims_doc, METHOD_CLAIMS_SCHEMA, {"schema_version", "method_version_id", "claims"}, "CLAIMS"),
        (sources_doc, METHOD_SOURCES_SCHEMA, {"schema_version", "method_version_id", "sources"}, "SOURCES"),
        (evidence_doc, METHOD_EVIDENCE_INDEX_SCHEMA, {"schema_version", "method_version_id", "bindings"}, "EVIDENCE_INDEX"),
    )
    for document, schema, fields, label in catalog_specs:
        if document.get("schema_version") != schema:
            report.error("METHOD_CATALOG_SCHEMA", label, f"expected {schema}")
        if set(document) != fields:
            report.error(
                "METHOD_CATALOG_FIELDS",
                label,
                f"must contain exactly {sorted(fields)}",
            )
        if document.get("method_version_id") != method_version_id:
            report.error(
                "METHOD_CATALOG_VERSION",
                f"{label}.method_version_id",
                "must match the cataloged method version",
            )

    claims = claims_doc.get("claims")
    if not isinstance(claims, list):
        report.error("METHOD_CLAIMS", "CLAIMS.claims", "must be an array")
        claims = []
    elif not claims:
        report.error("METHOD_CLAIMS_EMPTY", "CLAIMS.claims", "must be non-empty")
    claim_ids: set[str] = set()
    claims_by_id: dict[str, dict[str, Any]] = {}
    claim_fields = {"claim_id", "statement", "origin", "scope", "falsified_by"}
    for index, claim in enumerate(claims):
        location = f"CLAIMS.claims[{index}]"
        if not isinstance(claim, dict):
            report.error("METHOD_CLAIM", location, "must be an object")
            continue
        if set(claim) != claim_fields:
            report.error("METHOD_CLAIM_FIELDS", location, f"must contain exactly {sorted(claim_fields)}")
        claim_id = _require_string(claim, "claim_id", report, location)
        for key in ("statement", "origin", "scope", "falsified_by"):
            _require_string(claim, key, report, location)
        if strict_theory_roles:
            _check_enum(
                claim.get("origin"),
                {"method-decision", "theory-derived-method-decision"},
                report,
                f"{location}.origin",
            )
        if claim_id in claim_ids:
            report.error("DUPLICATE_METHOD_CLAIM", location, "duplicate claim_id")
        elif claim_id:
            claim_ids.add(claim_id)
            claims_by_id[claim_id] = claim

    sources = sources_doc.get("sources")
    if not isinstance(sources, list):
        report.error("METHOD_SOURCES", "SOURCES.sources", "must be an array")
        sources = []
    elif not sources:
        report.error("METHOD_SOURCES_EMPTY", "SOURCES.sources", "must be non-empty")
    source_ids: set[str] = set()
    sources_by_id: dict[str, dict[str, Any]] = {}
    source_kinds_by_id: dict[str, str | None] = {}
    source_fields = {
        "source_id",
        "kind",
        "artifact_id",
        "version_id",
        "repository_id",
        "commit",
        "path",
        "content_sha256",
    }
    for index, source in enumerate(sources):
        location = f"SOURCES.sources[{index}]"
        if not isinstance(source, dict):
            report.error("METHOD_SOURCE", location, "must be an object")
            continue
        if set(source) != source_fields:
            report.error("METHOD_SOURCE_FIELDS", location, f"must contain exactly {sorted(source_fields)}")
        source_id = _require_string(source, "source_id", report, location)
        for key in ("artifact_id", "version_id", "repository_id", "path"):
            _require_string(source, key, report, location)
        source_kind = _require_string(source, "kind", report, location)
        if strict_theory_roles:
            source_kind = _check_enum(
                source_kind,
                ALLOWED_METHOD_SOURCE_KINDS,
                report,
                f"{location}.kind",
            )
        commit = source.get("commit")
        if not isinstance(commit, str) or not GIT_SHA1_RE.fullmatch(commit):
            report.error("METHOD_SOURCE_COMMIT", f"{location}.commit", "must be a full lowercase Git commit")
        _check_digest(source.get("content_sha256"), report, f"{location}.content_sha256")
        _safe_member(project_root, source.get("path"), report, f"{location}.path")
        if source_id in source_ids:
            report.error("DUPLICATE_METHOD_SOURCE", location, "duplicate source_id")
        elif source_id:
            source_ids.add(source_id)
            sources_by_id[source_id] = source
            source_kinds_by_id[source_id] = source_kind

    primary_sources = [
        source
        for source_id, source in sources_by_id.items()
        if source_kinds_by_id.get(source_id) == "primary-theory"
    ]
    if strict_theory_roles and len(primary_sources) != 1:
        report.error(
            "METHOD_PRIMARY_THEORY_COUNT",
            "SOURCES.sources",
            "must contain exactly one primary-theory source",
        )
    primary_source = (
        primary_sources[0]
        if strict_theory_roles and len(primary_sources) == 1
        else None
    )
    theory_representation_kinds: dict[str, str] = {}
    if strict_theory_roles and theory_versions is not None:
        for source_id, source in sources_by_id.items():
            source_kind = source_kinds_by_id.get(source_id)
            if source_kind not in {"primary-theory", "drafting-provenance"}:
                continue
            matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for theory in theory_versions:
                if not isinstance(theory, dict):
                    continue
                theory_source = theory.get("source")
                representations = theory.get("representations")
                if not isinstance(theory_source, dict) or not isinstance(representations, list):
                    continue
                for representation in representations:
                    if not isinstance(representation, dict):
                        continue
                    if (
                        theory.get("artifact_id") == source.get("artifact_id")
                        and theory.get("version_id") == source.get("version_id")
                        and theory_source.get("repository_id") == source.get("repository_id")
                        and theory_source.get("commit") == source.get("commit")
                        and representation.get("path") == source.get("path")
                        and representation.get("sha256") == source.get("content_sha256")
                    ):
                        matches.append((theory, representation))
            if len(matches) != 1:
                report.error(
                    "METHOD_SOURCE_THEORY_REF",
                    f"SOURCES.{source_id}",
                    "must match exactly one cataloged theory artifact representation",
                )
            else:
                matched_role = matches[0][0].get("provenance_role")
                expected_role = {
                    "primary-theory": "published-primary",
                    "drafting-provenance": "consulted-drafting",
                }.get(source_kind)
                if matched_role != expected_role:
                    report.error(
                        "METHOD_SOURCE_THEORY_ROLE",
                        f"SOURCES.{source_id}",
                        f"{source_kind} must resolve to theory role {expected_role}",
                    )
                theory_representation_kinds[source_id] = str(
                    matches[0][1].get("kind")
                )

    if primary_source is not None and method_lineage is not None:
        lineage_mismatches = []
        expected_pairs = (
            ("version_id", "theory_version_id"),
            ("commit", "source_commit"),
            ("content_sha256", "content_sha256"),
        )
        for source_key, lineage_key in expected_pairs:
            if primary_source.get(source_key) != method_lineage.get(lineage_key):
                lineage_mismatches.append(f"{source_key}!={lineage_key}")
        primary_source_id = primary_source.get("source_id")
        representation_kind = theory_representation_kinds.get(str(primary_source_id))
        if (
            representation_kind is not None
            and representation_kind != method_lineage.get("representation")
        ):
            lineage_mismatches.append("representation")
        if lineage_mismatches:
            report.error(
                "METHOD_PRIMARY_THEORY_LINEAGE",
                "SOURCES.sources",
                "primary theory must equal derived_from; mismatches: "
                + ", ".join(lineage_mismatches),
            )

    bindings = evidence_doc.get("bindings")
    if not isinstance(bindings, list):
        report.error("METHOD_BINDINGS", "EVIDENCE_INDEX.bindings", "must be an array")
        bindings = []
    elif not bindings:
        report.error("METHOD_BINDINGS_EMPTY", "EVIDENCE_INDEX.bindings", "must be non-empty")
    bound_claims: set[str] = set()
    binding_fields = {"claim_id", "source_ids", "relationship"}
    for index, binding in enumerate(bindings):
        location = f"EVIDENCE_INDEX.bindings[{index}]"
        if not isinstance(binding, dict):
            report.error("METHOD_BINDING", location, "must be an object")
            continue
        if set(binding) != binding_fields:
            report.error("METHOD_BINDING_FIELDS", location, f"must contain exactly {sorted(binding_fields)}")
        claim_id = _require_string(binding, "claim_id", report, location)
        _require_string(binding, "relationship", report, location)
        refs = _require_string_list(binding, "source_ids", report, location)
        if not refs or len(refs) != len(set(refs)):
            report.error("METHOD_BINDING_SOURCES", f"{location}.source_ids", "must be a non-empty unique list")
        if claim_id not in claim_ids:
            report.error("METHOD_BINDING_CLAIM", f"{location}.claim_id", "must resolve exactly once")
        if claim_id in bound_claims:
            report.error("DUPLICATE_METHOD_BINDING", location, "claim_id is bound more than once")
        elif claim_id:
            bound_claims.add(claim_id)
        for source_id in refs:
            if source_id not in source_ids:
                report.error("METHOD_BINDING_SOURCE", f"{location}.source_ids", f"unresolved source_id {source_id}")
        claim = claims_by_id.get(str(claim_id))
        if (
            strict_theory_roles
            and claim is not None
            and claim.get("origin") == "theory-derived-method-decision"
            and primary_source is not None
            and primary_source.get("source_id") not in refs
        ):
            report.error(
                "METHOD_BINDING_PRIMARY_THEORY",
                f"{location}.source_ids",
                "theory-derived claims must bind the unique primary-theory source",
            )
    for claim_id in sorted(claim_ids - bound_claims):
        report.error("ORPHAN_METHOD_CLAIM", "EVIDENCE_INDEX.bindings", f"unbound claim_id {claim_id}")

    joins_valid = (
        not report.errors
        and bool(claim_ids)
        and bool(source_ids)
        and bool(bindings)
        and claim_ids == bound_claims
    )
    report.facts.update(
        {
            "method_claim_count": len(claim_ids),
            "method_source_count": len(source_ids),
            "method_binding_count": len(bound_claims),
            "method_primary_theory_source_id": (
                primary_source.get("source_id") if primary_source is not None else None
            ),
            "method_primary_theory_version_id": (
                primary_source.get("version_id") if primary_source is not None else None
            ),
            "method_drafting_provenance_count": sum(
                source_kind == "drafting-provenance"
                for source_kind in source_kinds_by_id.values()
            ),
            "method_provenance_join_status": "validated" if joins_valid else "invalid",
            "method_source_bytes_resolution_status": "not-resolved",
        }
    )


def validate_method_index(
    path: Path,
    theory_versions: list[dict[str, Any]] | None = None,
    theory_schema_version: str | None = None,
) -> tuple[Report, list[dict[str, Any]]]:
    """Validate the method-paper catalog without treating it as empirical evidence."""

    report = Report(subject=str(path.resolve()))
    document = load_json(path, report, "method index")
    if document is None:
        return report, []
    method_schema = document.get("schema_version")
    if not isinstance(method_schema, str) or method_schema not in (
        LEGACY_METHOD_INDEX_SCHEMA,
        METHOD_INDEX_SCHEMA,
    ):
        report.error(
            "SCHEMA_VERSION",
            str(path),
            f"expected {LEGACY_METHOD_INDEX_SCHEMA} or {METHOD_INDEX_SCHEMA}",
        )
    method_v2 = method_schema == METHOD_INDEX_SCHEMA
    if theory_versions is not None and (
        not isinstance(theory_schema_version, str)
        or (
            theory_schema_version != LEGACY_THEORY_INDEX_SCHEMA
            and theory_schema_version != THEORY_INDEX_SCHEMA
        )
    ):
        report.error(
            "METHOD_THEORY_SCHEMA_CONTEXT",
            str(path),
            "theory_versions require an explicit validated v1 or v2 schema context",
        )
        return report, []
    allowed_top = {"schema_version", "normative_source", "versions"}
    unknown_top = sorted(set(document) - allowed_top)
    if unknown_top:
        report.error(
            "METHOD_INDEX_FIELDS",
            path.name,
            f"unknown fields: {unknown_top}",
        )

    project_root = path.resolve().parents[1]
    normative_source = _require_string(
        document, "normative_source", report, path.name
    )
    versions = _require_list(document, "versions", report, path.name) or []
    if method_v2 and not versions:
        report.error(
            "METHOD_VERSION_COUNT",
            f"{path.name}.versions",
            "must contain at least one cataloged method version",
        )
    elif not method_v2 and len(versions) != 1:
        report.error(
            "METHOD_VERSION_COUNT",
            f"{path.name}.versions",
            "legacy v1 requires exactly one cataloged method version",
        )
    declared_study_versions = (
        [
            version
            for version in versions
            if isinstance(version, dict) and version.get("study_eligible") is True
        ]
        if method_v2
        else []
    )

    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, version in enumerate(versions):
        location = f"{path.name}.versions[{index}]"
        error_count = len(report.errors)
        if not isinstance(version, dict):
            report.error("METHOD_VERSION", location, "must be an object")
            continue
        legacy_allowed_version = {
            "version_id",
            "status",
            "builder_eligible",
            "source_commit",
            "path",
            "content_sha256",
            "scope_datum_path",
            "scope_datum_sha256",
            "derived_from",
            "claim_catalog",
            "source_catalog",
            "evidence_index",
        }
        allowed_version = legacy_allowed_version | (
            {"study_eligible", "adoption_eligible"} if method_v2 else set()
        )
        unknown = sorted(set(version) - allowed_version)
        if unknown:
            report.error("METHOD_VERSION_FIELDS", location, f"unknown fields: {unknown}")
        if "source_commit" not in version:
            report.error(
                "METHOD_VERSION_FIELDS",
                location,
                "must explicitly declare source_commit",
            )
        version_id = _require_string(version, "version_id", report, location)
        if version_id in seen:
            report.error("DUPLICATE_METHOD_VERSION", location, "duplicate version_id")
        elif version_id:
            seen.add(version_id)
        status = version.get("status")
        allowed_status = {"draft", "frozen"} if method_v2 else {"draft"}
        if not isinstance(status, str) or status not in allowed_status:
            report.error(
                "METHOD_STATUS",
                f"{location}.status",
                (
                    "must be draft or frozen"
                    if method_v2
                    else "legacy v1 method must remain draft"
                ),
            )
        builder_eligible = version.get("builder_eligible")
        eligibility_fields = [("builder_eligible", builder_eligible)]
        if method_v2:
            eligibility_fields[:0] = [
                ("study_eligible", version.get("study_eligible")),
                ("adoption_eligible", version.get("adoption_eligible")),
            ]
        for field_name, eligible in eligibility_fields:
            if not isinstance(eligible, bool):
                report.error(
                    "METHOD_ELIGIBILITY",
                    f"{location}.{field_name}",
                    "must be boolean",
                )
        if not method_v2 and builder_eligible is not False:
            report.error(
                "METHOD_BUILDER_ELIGIBILITY",
                f"{location}.builder_eligible",
                "legacy v1 checked-in method must remain builder-ineligible",
            )
        if method_v2 and (
            isinstance(version.get("adoption_eligible"), bool)
            and isinstance(builder_eligible, bool)
            and builder_eligible != version.get("adoption_eligible")
        ):
            report.error(
                "METHOD_ADOPTION_ALIAS",
                f"{location}.builder_eligible",
                "deprecated builder_eligible must equal adoption_eligible",
            )
        source_commit = version.get("source_commit")
        if method_v2:
            if not isinstance(source_commit, str) or not GIT_SHA1_RE.fullmatch(
                source_commit
            ):
                report.error(
                    "METHOD_SOURCE_COMMIT",
                    f"{location}.source_commit",
                    "v2 method versions must pin a full lowercase Git commit",
                )
        elif source_commit is not None:
            if not isinstance(source_commit, str) or not GIT_SHA1_RE.fullmatch(source_commit):
                report.error(
                    "METHOD_SOURCE_COMMIT",
                    f"{location}.source_commit",
                    "must be null or a full lowercase Git commit",
                )
        needs_frozen_pin = builder_eligible is True
        if method_v2:
            needs_frozen_pin = (
                version.get("study_eligible") is True
                or version.get("adoption_eligible") is True
            )
        if needs_frozen_pin and (status != "frozen" or source_commit is None):
            report.error(
                "METHOD_SOURCE_COMMIT",
                f"{location}.source_commit",
                "study- or adoption-eligible versions require frozen bytes at an exact source commit",
            )
        method_path_value = _require_string(version, "path", report, location)
        method_path = _safe_member(
            project_root, method_path_value, report, f"{location}.path"
        )
        method_digest = version.get("content_sha256")
        _check_digest(method_digest, report, f"{location}.content_sha256")
        if method_path is not None:
            if not method_path.is_file():
                report.error("METHOD_FILE", str(method_path), "method source is missing")
            elif (not method_v2 or source_commit is None) and (
                SHA256_RE.fullmatch(str(method_digest))
                and sha256_file(method_path) != method_digest
            ):
                report.error(
                    "METHOD_FILE_HASH",
                    f"{location}.content_sha256",
                    "does not match METHOD.md bytes",
                )
        resolved_commit: bytes | None = None
        if method_v2 and (
            isinstance(source_commit, str)
            and GIT_SHA1_RE.fullmatch(source_commit)
            and isinstance(method_path_value, str)
        ):
            resolved_commit = _read_git_object(
                project_root,
                ["rev-parse", "--verify", f"{source_commit}^{{commit}}"],
                report,
                f"{location}.source_commit",
            )
            if resolved_commit is not None and (
                resolved_commit.decode("ascii", errors="replace").strip()
                != source_commit
            ):
                report.error(
                    "METHOD_SOURCE_COMMIT",
                    f"{location}.source_commit",
                    "does not resolve to the declared commit object",
                )
            frozen_bytes = (
                _read_git_object(
                    project_root,
                    ["cat-file", "blob", f"{source_commit}:{method_path_value}"],
                    report,
                    f"{location}.source_commit",
                )
                if resolved_commit is not None
                else None
            )
            if frozen_bytes is not None and (
                "sha256:" + hashlib.sha256(frozen_bytes).hexdigest()
                != method_digest
            ):
                report.error(
                    "METHOD_SOURCE_HASH",
                    f"{location}.content_sha256",
                    "does not match method bytes at source_commit",
                )
        if method_path_value != normative_source:
            report.error(
                "METHOD_NORMATIVE_SOURCE",
                f"{location}.path",
                "must equal the sole normative_source",
            )

        scope_path_value = _require_string(
            version, "scope_datum_path", report, location
        )
        scope_path = _safe_member(
            project_root,
            scope_path_value,
            report,
            f"{location}.scope_datum_path",
        )
        scope_digest = version.get("scope_datum_sha256")
        _check_digest(scope_digest, report, f"{location}.scope_datum_sha256")
        if scope_path is not None:
            if not scope_path.is_file():
                report.error("METHOD_SCOPE_FILE", str(scope_path), "scope datum is missing")
            elif (not method_v2 or source_commit is None) and (
                SHA256_RE.fullmatch(str(scope_digest))
                and sha256_file(scope_path) != scope_digest
            ):
                report.error(
                    "METHOD_SCOPE_HASH",
                    f"{location}.scope_datum_sha256",
                    "does not match scope datum bytes",
                )
        if method_v2 and (
            resolved_commit is not None
            and isinstance(scope_path_value, str)
        ):
            frozen_scope_bytes = _read_git_object(
                project_root,
                ["cat-file", "blob", f"{source_commit}:{scope_path_value}"],
                report,
                f"{location}.source_commit",
            )
            if frozen_scope_bytes is not None and (
                "sha256:" + hashlib.sha256(frozen_scope_bytes).hexdigest()
                != scope_digest
            ):
                report.error(
                    "METHOD_SCOPE_SOURCE_HASH",
                    f"{location}.scope_datum_sha256",
                    "does not match scope datum bytes at source_commit",
                )

        catalog_paths: dict[str, Path] = {}
        for key in ("claim_catalog", "source_catalog", "evidence_index"):
            catalog_value = _require_string(version, key, report, location)
            catalog_path = _safe_member(
                project_root, catalog_value, report, f"{location}.{key}"
            )
            if catalog_path is not None:
                if not catalog_path.is_file():
                    report.error(
                        "METHOD_CATALOG_FILE",
                        str(catalog_path),
                        f"{key} is missing",
                    )
                else:
                    catalog_paths[key] = catalog_path

        lineage = _require_object(version, "derived_from", report, location)
        if lineage is not None:
            allowed_lineage = {
                "theory_version_id",
                "source_commit",
                "representation",
                "content_sha256",
            }
            unknown_lineage = sorted(set(lineage) - allowed_lineage)
            if unknown_lineage:
                report.error(
                    "METHOD_LINEAGE_FIELDS",
                    f"{location}.derived_from",
                    f"unknown fields: {unknown_lineage}",
                )
            for key in ("theory_version_id", "representation"):
                _require_string(lineage, key, report, f"{location}.derived_from")
            commit = _require_string(
                lineage, "source_commit", report, f"{location}.derived_from"
            )
            if isinstance(commit, str) and not GIT_SHA1_RE.fullmatch(commit):
                report.error(
                    "METHOD_LINEAGE_COMMIT",
                    f"{location}.derived_from.source_commit",
                    "must be a full lowercase Git commit",
                )
            _check_digest(
                lineage.get("content_sha256"),
                report,
                f"{location}.derived_from.content_sha256",
            )
            if theory_versions is not None:
                _validate_theory_reference(
                    {
                        "version_id": lineage.get("theory_version_id"),
                        "artifact_id": "charting-loop-theory",
                        "source_commit": lineage.get("source_commit"),
                        "representation": lineage.get("representation"),
                        "content_sha256": lineage.get("content_sha256"),
                    },
                    theory_versions,
                    report,
                    f"{location}.derived_from",
                )
        if (
            (not method_v2 or version.get("study_eligible") is True)
            and set(catalog_paths)
            == {"claim_catalog", "source_catalog", "evidence_index"}
        ):
            _validate_method_provenance_catalogs(
                project_root,
                version_id,
                catalog_paths,
                report,
                theory_versions=theory_versions,
                theory_schema_version=theory_schema_version,
                method_lineage=lineage,
            )
        if len(report.errors) == error_count:
            valid.append(version)

    if method_v2:
        valid_study_versions = [
            version for version in valid if version.get("study_eligible") is True
        ]
        if not declared_study_versions:
            report.error(
                "METHOD_STUDY_VERSION_COUNT",
                f"{path.name}.versions",
                "must contain at least one study-eligible method version",
            )
        elif len(valid_study_versions) != len(declared_study_versions):
            report.error(
                "METHOD_STUDY_VERSION_INVALID",
                f"{path.name}.versions",
                "every study-eligible method version must validate completely",
            )

    report.facts.update(
        {
            "schema_version": method_schema,
            "normative_source": normative_source,
            "version_count": len(valid),
            "builder_eligible_version_count": sum(
                version.get("builder_eligible") is True for version in valid
            ),
        }
    )
    if method_v2:
        report.facts.update(
            {
                "study_eligible_version_count": sum(
                    version.get("study_eligible") is True for version in valid
                ),
                "adoption_eligible_version_count": sum(
                    version.get("adoption_eligible") is True for version in valid
                ),
            }
        )
    if method_v2 and (
        not declared_study_versions
        or len(valid_study_versions) != len(declared_study_versions)
        or report.errors
    ):
        return report, []
    return report, valid


def _check_sequence(
    records: list[dict[str, Any]], report: Report, location: str, key: str = "seq"
) -> None:
    actual = [record.get(key) for record in records]
    expected = list(range(1, len(records) + 1))
    if any(not isinstance(value, int) or isinstance(value, bool) for value in actual):
        report.error(
            "SEQUENCE_TYPE", location, f"{key} values must be integers, not booleans"
        )
    elif actual != expected:
        report.error("SEQUENCE", location, f"{key} must be contiguous from 1; got {actual!r}")


def _check_timestamp_sequence(
    records: list[dict[str, Any]], report: Report, location: str
) -> None:
    previous: datetime | None = None
    for index, record in enumerate(records, start=1):
        raw = record.get("timestamp")
        try:
            current = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if previous is not None:
            try:
                out_of_order = current < previous
            except TypeError:
                out_of_order = False
            if out_of_order:
                report.error(
                    "TIMESTAMP_SEQUENCE",
                    f"{location}:{index}.timestamp",
                    "timestamps must be nondecreasing by sequence",
                )
        previous = current


def _check_unique_ids(
    records: list[dict[str, Any]], key: str, report: Report, location: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, start=1):
        value = record.get(key)
        record_location = f"{location}:{index}.{key}"
        if not isinstance(value, str) or not value:
            report.error("REQUIRED_ID", record_location, "must be a non-empty string")
            continue
        if value in result:
            report.error("DUPLICATE_ID", record_location, f"duplicate identifier {value!r}")
            continue
        result[value] = record
    return result


def _validate_trace_record(
    path: Path,
    *,
    expected_schema: str,
    corridor: dict[str, Any],
    report: Report,
    actor_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    record = load_json(path, report, "structured trace evidence")
    if record is None:
        return None
    if record.get("schema_version") != expected_schema:
        report.error("TRACE_SCHEMA", str(path), f"expected {expected_schema}")
    if record.get("corridor_id") != corridor.get("corridor_id"):
        report.error("TRACE_BINDING", str(path), "corridor_id does not match CORRIDOR.json")
    if record.get("revision_id") != corridor.get("revision_id"):
        report.error("TRACE_BINDING", str(path), "revision_id does not match CORRIDOR.json")
    if record.get("corridor_tree_sha256") != corridor.get("corridor_tree_sha256"):
        report.error("TRACE_BINDING", str(path), "corridor tree digest does not match CORRIDOR.json")
    evaluation_protocol = corridor.get("evaluation_protocol_ref")
    input_bundle = corridor.get("input_bundle")
    expected_task_id = (
        evaluation_protocol.get("task_id")
        if isinstance(evaluation_protocol, dict)
        else None
    )
    expected_input_digest = (
        input_bundle.get("manifest_sha256") if isinstance(input_bundle, dict) else None
    )
    for key, expected in (
        ("task_id", expected_task_id),
        ("input_bundle_sha256", expected_input_digest),
    ):
        if record.get(key) != expected:
            report.error(
                "TRACE_BINDING", f"{path}.{key}", "does not match CORRIDOR.json"
            )
    producer_actor_id = _require_string(
        record, "producer_actor_id", report, str(path)
    )
    if actor_map is not None and (
        producer_actor_id not in actor_map
        or actor_map[producer_actor_id].get("role") != "observer"
    ):
        report.error(
            "TRACE_PRODUCER",
            f"{path}.producer_actor_id",
            "must identify a declared observer, independent of the corridor builder",
        )
    _check_datetime(record.get("observed_at"), report, f"{path}.observed_at")
    observation = _require_string(record, "observation", report, str(path))
    observation_digest = record.get("observation_sha256")
    _check_digest(observation_digest, report, f"{path}.observation_sha256")
    if (
        isinstance(observation, str)
        and SHA256_RE.fullmatch(str(observation_digest))
        and sha256_text(observation) != observation_digest
    ):
        report.error(
            "TRACE_OBSERVATION_HASH",
            f"{path}.observation_sha256",
            "does not match observation text",
        )
    return record


def _validate_input_bundle(
    root: Path,
    corridor: dict[str, Any],
    report: Report,
    task_versions: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    binding = _require_object(corridor, "input_bundle", report, "CORRIDOR.json")
    if binding is None:
        return None
    manifest_value = binding.get("manifest_path")
    if manifest_value != CANONICAL_CORRIDOR_PATHS["input_manifest_path"]:
        report.error(
            "CANONICAL_PATH",
            "CORRIDOR.json.input_bundle.manifest_path",
            f"must equal {CANONICAL_CORRIDOR_PATHS['input_manifest_path']!r}",
        )
    manifest_path = _safe_member(
        root, manifest_value, report, "CORRIDOR.json.input_bundle.manifest_path"
    )
    manifest_digest = binding.get("manifest_sha256")
    _check_digest(
        manifest_digest, report, "CORRIDOR.json.input_bundle.manifest_sha256"
    )
    if manifest_path is None or not manifest_path.is_file():
        report.error(
            "REQUIRED_FILE",
            str(manifest_path or manifest_value),
            "input-bundle manifest is missing",
        )
        return None
    if (
        SHA256_RE.fullmatch(str(manifest_digest))
        and sha256_file(manifest_path) != manifest_digest
    ):
        report.error(
            "FILE_HASH",
            "CORRIDOR.json.input_bundle.manifest_sha256",
            "does not match input manifest",
        )
    manifest = load_json(manifest_path, report, "input-bundle manifest")
    if manifest is None:
        return None
    if manifest.get("schema_version") != INPUT_BUNDLE_SCHEMA:
        report.error("SCHEMA_VERSION", str(manifest_path), f"expected {INPUT_BUNDLE_SCHEMA}")
    _require_string(manifest, "bundle_id", report, "INPUTS.json")
    track = _require_string(manifest, "track", report, "INPUTS.json")
    if track not in ALLOWED_TRACKS:
        report.error("TRACK", "INPUTS.json.track", f"must be one of {sorted(ALLOWED_TRACKS)}")
    arm = _require_string(manifest, "knowledge_arm", report, "INPUTS.json")
    if arm not in ALLOWED_KNOWLEDGE_ARMS:
        report.error("KNOWLEDGE_ARM", "INPUTS.json.knowledge_arm", f"must be one of {sorted(ALLOWED_KNOWLEDGE_ARMS)}")
    entries = _require_list(manifest, "entries", report, "INPUTS.json") or []
    task_id = _require_string(manifest, "task_id", report, "INPUTS.json")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    input_classes: dict[str, str] = {}
    roles: list[str] = []
    entries_by_role: dict[str, list[dict[str, Any]]] = {
        role: [] for role in ALLOWED_INPUT_ROLES
    }
    for index, entry in enumerate(entries):
        location = f"INPUTS.json.entries[{index}]"
        if not isinstance(entry, dict):
            report.error("INPUT_ENTRY", location, "must be an object")
            continue
        input_id = _require_string(entry, "input_id", report, location)
        if input_id in seen_ids:
            report.error("DUPLICATE_ID", f"{location}.input_id", f"duplicate {input_id!r}")
        elif input_id:
            seen_ids.add(input_id)
        role = _require_string(entry, "role", report, location)
        if role not in ALLOWED_INPUT_ROLES:
            report.error("INPUT_ROLE", f"{location}.role", f"must be one of {sorted(ALLOWED_INPUT_ROLES)}")
        elif role:
            roles.append(role)
            entries_by_role[role].append(entry)
        path_value = entry.get("path")
        if isinstance(path_value, str):
            if path_value in seen_paths:
                report.error("DUPLICATE_PATH", f"{location}.path", f"duplicate {path_value!r}")
            else:
                seen_paths.add(path_value)
        input_class = entry.get("input_class")
        if not isinstance(input_class, str) or input_class not in {
            "common",
            "knowledge-treatment",
        }:
            report.error("INPUT_CLASS", f"{location}.input_class", "must be common or knowledge-treatment")
        elif isinstance(path_value, str):
            input_classes[path_value] = input_class
        if role in {"theory", "methodology", "generic-control", "other-framework"} and input_class != "knowledge-treatment":
            report.error("INPUT_CLASS", f"{location}.input_class", f"{role} must be a knowledge-treatment input")
        if role in {"builder-task", "instrumentation", "attachment"} and input_class != "common":
            report.error("INPUT_CLASS", f"{location}.input_class", f"{role} must be a common input")
        if track == "reference" and isinstance(path_value, str) and Path(path_value).name in {"TASK.md", "RATIONALE.md"}:
            report.error("EVALUATOR_LEAK", f"{location}.path", "evaluator-only file is forbidden in the reference builder bundle")
        if isinstance(path_value, str) and not (
            path_value == "AGENTS.md" or path_value.startswith("inputs/files/")
        ):
            report.error("BUILDER_VIEW_PATH", f"{location}.path", "builder inputs must live under inputs/files/ or be the root AGENTS.md")
        input_path = _safe_member(root, path_value, report, f"{location}.path")
        digest = entry.get("sha256")
        _check_digest(digest, report, f"{location}.sha256")
        if task_versions is not None:
            hidden_digests = {
                file_record.get("sha256")
                for task_record in task_versions
                if isinstance(task_record, dict)
                and isinstance(task_record.get("evaluation_protocol"), dict)
                for file_record in (
                    task_record["evaluation_protocol"].get("files", [])
                    if isinstance(
                        task_record["evaluation_protocol"].get("files", []), list
                    )
                    else []
                )
                if isinstance(file_record, dict)
                and isinstance(file_record.get("sha256"), str)
            }
            if isinstance(digest, str) and digest in hidden_digests:
                report.error("EVALUATOR_LEAK", f"{location}.sha256", "matches a cataloged evaluator-only file")
        if entry.get("visible_to_builder") is not True:
            report.error("INPUT_VISIBILITY", f"{location}.visible_to_builder", "input inventory contains only builder-visible files and must be true")
        if input_path is not None:
            if not input_path.is_file():
                report.error("REQUIRED_FILE", str(input_path), "declared builder input is missing")
            elif SHA256_RE.fullmatch(str(digest)) and sha256_file(input_path) != digest:
                report.error("FILE_HASH", f"{location}.sha256", "does not match builder input bytes")
    builder_view = _require_object(manifest, "builder_view", report, "INPUTS.json")
    if builder_view is not None:
        view_roots = _require_string_list(builder_view, "roots", report, "INPUTS.json.builder_view")
        if set(view_roots) != {"inputs/files", "AGENTS.md"} or len(view_roots) != 2:
            report.error("BUILDER_VIEW_ROOTS", "INPUTS.json.builder_view.roots", "must contain exactly inputs/files and AGENTS.md")
        safe_roots: list[str] = []
        for root_index, view_root in enumerate(view_roots):
            if _safe_member(root, view_root, report, f"INPUTS.json.builder_view.roots[{root_index}]") is not None:
                safe_roots.append(view_root)
        view_digest = builder_view.get("tree_sha256")
        _check_digest(view_digest, report, "INPUTS.json.builder_view.tree_sha256")
        if safe_roots:
            try:
                actual_view_digest, view_records = hash_tree(root, safe_roots)
            except (OSError, ValueError) as exc:
                report.error("BUILDER_VIEW", "INPUTS.json.builder_view", str(exc))
            else:
                actual_paths = {record["path"] for record in view_records}
                if actual_paths != seen_paths:
                    report.error("BUILDER_VIEW_INVENTORY", "INPUTS.json.entries", f"inventory paths {sorted(seen_paths)!r} do not equal builder-view files {sorted(actual_paths)!r}")
                if SHA256_RE.fullmatch(str(view_digest)) and actual_view_digest != view_digest:
                    report.error("BUILDER_VIEW_HASH", "INPUTS.json.builder_view.tree_sha256", "does not match the closed builder view")
                common_records = [record for record in view_records if input_classes.get(record["path"]) == "common"]
                treatment_records = [record for record in view_records if input_classes.get(record["path"]) == "knowledge-treatment"]
                common_digest = builder_view.get("common_inputs_sha256")
                treatment_digest = builder_view.get("treatment_inputs_sha256")
                _check_digest(common_digest, report, "INPUTS.json.builder_view.common_inputs_sha256")
                _check_digest(treatment_digest, report, "INPUTS.json.builder_view.treatment_inputs_sha256")
                if SHA256_RE.fullmatch(str(common_digest)) and digest_tree_records(common_records) != common_digest:
                    report.error("COMMON_INPUT_HASH", "INPUTS.json.builder_view.common_inputs_sha256", "does not match common builder inputs")
                if SHA256_RE.fullmatch(str(treatment_digest)) and digest_tree_records(treatment_records) != treatment_digest:
                    report.error("TREATMENT_INPUT_HASH", "INPUTS.json.builder_view.treatment_inputs_sha256", "does not match knowledge-treatment inputs")
                report.facts["common_inputs_sha256"] = common_digest
                report.facts["treatment_inputs_sha256"] = treatment_digest
    if roles.count("builder-task") != 1:
        report.error("BUILDER_TASK", "INPUTS.json.entries", "every bundle requires exactly one builder-task")
    if task_versions is not None:
        matches = [
            task
            for task in task_versions
            if isinstance(task, dict) and task.get("task_id") == task_id
        ]
        builder_entry = entries_by_role["builder-task"][0] if len(entries_by_role["builder-task"]) == 1 else {}
        if len(matches) != 1 or builder_entry.get("sha256") != matches[0].get("builder_brief", {}).get("sha256"):
            report.error("TASK_CATALOG_REF", "INPUTS.json", "task ID and builder-task digest must match the supplied task catalog")
        if len(matches) == 1:
            expected_instrumentation = sorted(
                record.get("sha256")
                for record in matches[0].get("common_instrumentation", [])
                if isinstance(record, dict) and isinstance(record.get("sha256"), str)
            )
            actual_instrumentation = sorted(
                record.get("sha256")
                for record in entries_by_role["instrumentation"]
                if isinstance(record.get("sha256"), str)
            )
            if actual_instrumentation != expected_instrumentation:
                report.error(
                    "TASK_INSTRUMENTATION_REF",
                    "INPUTS.json.entries",
                    "common instrumentation must exactly match the supplied task catalog",
                )
        if track == "reference" and entries_by_role["attachment"]:
            report.error(
                "REFERENCE_ATTACHMENT",
                "INPUTS.json.entries",
                "reference bundles forbid attachments; use a domain track for extra common inputs",
            )
    if arm == "methodology" and (
        roles.count("methodology") != 1
        or any(role in roles for role in ("theory", "other-framework"))
    ):
        report.error("KNOWLEDGE_ARM_INPUT", "INPUTS.json.entries", "methodology requires one methodology input and no theory/other-framework input")
    if arm == "theory-only" and (
        roles.count("theory") != 1
        or any(role in roles for role in ("methodology", "other-framework"))
    ):
        report.error("KNOWLEDGE_ARM_INPUT", "INPUTS.json.entries", "theory-only requires one theory input and no methodology/other-framework input")
    if arm == "control-none" and any(role in roles for role in ("theory", "methodology", "generic-control", "other-framework")):
        report.error("KNOWLEDGE_ARM_INPUT", "INPUTS.json.entries", "control-none may contain only the common task/instrumentation inputs")
    if arm == "control-other" and (
        roles.count("other-framework") != 1
        or any(role in roles for role in ("theory", "methodology"))
    ):
        report.error("KNOWLEDGE_ARM_INPUT", "INPUTS.json.entries", "control-other requires one other-framework and no theory/methodology input")
    if arm == "not-applicable" and any(
        role in roles
        for role in ("theory", "methodology", "generic-control", "other-framework")
    ):
        report.error("KNOWLEDGE_ARM_INPUT", "INPUTS.json.entries", "not-applicable may not contain a knowledge treatment")
    treatment_roles = sorted(
        entry.get("role")
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("input_class") == "knowledge-treatment"
        and isinstance(entry.get("role"), str)
    )
    expected_treatment_roles = {
        "methodology": ["methodology"],
        "theory-only": ["theory"],
        "control-none": [],
        "control-other": ["other-framework"],
        "not-applicable": [],
    }
    if arm in expected_treatment_roles and treatment_roles != expected_treatment_roles[arm]:
        report.error(
            "KNOWLEDGE_TREATMENT_MATRIX",
            "INPUTS.json.entries",
            f"knowledge-treatment roles must equal {expected_treatment_roles[arm]!r}",
        )
    theory_ref = corridor.get("theory_ref")
    if arm == "theory-only":
        theory_input = entries_by_role["theory"][0] if len(entries_by_role["theory"]) == 1 else {}
        if not isinstance(theory_ref, dict) or theory_input.get("sha256") != theory_ref.get("content_sha256"):
            report.error("KNOWLEDGE_REF_BINDING", "INPUTS.json.entries", "theory input digest must match CORRIDOR.json theory_ref")
    methodology_ref = corridor.get("methodology_ref")
    if arm == "methodology":
        methodology_input = entries_by_role["methodology"][0] if len(entries_by_role["methodology"]) == 1 else {}
        if not isinstance(methodology_ref, dict) or methodology_input.get("sha256") != methodology_ref.get("content_sha256"):
            report.error("KNOWLEDGE_REF_BINDING", "INPUTS.json.entries", "methodology input digest must match CORRIDOR.json methodology_ref")
    framework_ref = corridor.get("framework_ref")
    if arm == "control-other":
        framework_input = entries_by_role["other-framework"][0] if len(entries_by_role["other-framework"]) == 1 else {}
        if not isinstance(framework_ref, dict) or framework_input.get("sha256") != framework_ref.get("content_sha256"):
            report.error("KNOWLEDGE_REF_BINDING", "INPUTS.json.entries", "other-framework input digest must match CORRIDOR.json framework_ref")
    reference_matrix_ok = {
        "methodology": theory_ref is None
        and isinstance(methodology_ref, dict)
        and framework_ref is None,
        "theory-only": isinstance(theory_ref, dict)
        and methodology_ref is None
        and framework_ref is None,
        "control-none": theory_ref is None
        and methodology_ref is None
        and framework_ref is None,
        "control-other": theory_ref is None
        and methodology_ref is None
        and isinstance(framework_ref, dict),
        "not-applicable": theory_ref is None
        and methodology_ref is None
        and framework_ref is None,
    }
    if arm in reference_matrix_ok and not reference_matrix_ok[arm]:
        report.error(
            "KNOWLEDGE_REF_MATRIX",
            "CORRIDOR.json",
            "theory/methodology/framework treatment refs do not match INPUTS.json knowledge_arm",
        )
    report.facts.update(
        {
            "input_bundle_track": track,
            "knowledge_arm": arm,
            "builder_input_count": len(entries),
            "input_bundle_sha256": manifest_digest,
        }
    )
    return manifest


def _validate_authority(
    root: Path,
    corridor: dict[str, Any],
    authority_paths: dict[str, Path],
    report: Report,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    manifest_path = authority_paths["manifest"]
    manifest = load_json(manifest_path, report, "authority manifest")
    if manifest is None:
        return {}, {}
    if manifest.get("schema_version") != AUTHORITY_SCHEMA:
        report.error("SCHEMA_VERSION", str(manifest_path), f"expected {AUTHORITY_SCHEMA}")

    design = _require_object(manifest, "study_design", report, "AUTHORITY.json")
    if design is not None:
        if design.get("path") != CANONICAL_CORRIDOR_PATHS["authority_design_path"]:
            report.error("CANONICAL_PATH", "AUTHORITY.json.study_design.path", f"must equal {CANONICAL_CORRIDOR_PATHS['authority_design_path']!r}")
        design_path = _safe_member(root, design.get("path"), report, "AUTHORITY.json.study_design.path")
        design_digest = design.get("sha256")
        _check_digest(design_digest, report, "AUTHORITY.json.study_design.sha256")
        if design_path is not None:
            if not design_path.is_file():
                report.error("REQUIRED_FILE", str(design_path), "authority study design is missing")
            elif SHA256_RE.fullmatch(str(design_digest)) and sha256_file(design_path) != design_digest:
                report.error("FILE_HASH", "AUTHORITY.json.study_design.sha256", "does not match study design")
        report.facts["authority_design_sha256"] = design_digest

    corridor_authority = corridor.get("exogenous_authority", {})
    boundary_id = _require_string(
        manifest, "authority_boundary_id", report, "AUTHORITY.json"
    )
    if boundary_id != corridor_authority.get("authority_boundary_id"):
        report.error(
            "AUTHORITY_BOUNDARY",
            "AUTHORITY.json.authority_boundary_id",
            "does not match CORRIDOR.json",
        )

    condition = _require_object(manifest, "assigned_condition", report, "AUTHORITY.json")
    if condition is not None:
        mode = _require_string(condition, "mode", report, "AUTHORITY.json.assigned_condition")
        if mode not in ALLOWED_AUTHORITY_CONDITIONS:
            report.error(
                "AUTHORITY_CONDITION",
                "AUTHORITY.json.assigned_condition.mode",
                f"must be one of {sorted(ALLOWED_AUTHORITY_CONDITIONS)}",
            )
        if mode != corridor_authority.get("input_condition"):
            report.error(
                "AUTHORITY_CONDITION",
                "AUTHORITY.json.assigned_condition.mode",
                "does not match CORRIDOR.json",
            )
        protocol_path_value = condition.get("protocol_path")
        if protocol_path_value != CANONICAL_CORRIDOR_PATHS["condition_protocol_path"]:
            report.error(
                "CANONICAL_PATH",
                "AUTHORITY.json.assigned_condition.protocol_path",
                f"must equal {CANONICAL_CORRIDOR_PATHS['condition_protocol_path']!r}",
            )
        protocol_path = _safe_member(
            root,
            protocol_path_value,
            report,
            "AUTHORITY.json.assigned_condition.protocol_path",
        )
        protocol_digest = condition.get("protocol_sha256")
        _check_digest(
            protocol_digest, report, "AUTHORITY.json.assigned_condition.protocol_sha256"
        )
        if protocol_path is not None:
            if not protocol_path.is_file():
                report.error("REQUIRED_FILE", str(protocol_path), "condition protocol is missing")
            elif SHA256_RE.fullmatch(str(protocol_digest)) and sha256_file(protocol_path) != protocol_digest:
                report.error("FILE_HASH", "AUTHORITY.json.assigned_condition.protocol_sha256", "does not match protocol_path")
        _check_datetime(
            condition.get("frozen_at"),
            report,
            "AUTHORITY.json.assigned_condition.frozen_at",
        )
        report.facts["authority_condition"] = mode

    actors = _require_list(manifest, "actors", report, "AUTHORITY.json") or []
    actor_map: dict[str, dict[str, Any]] = {}
    for index, actor in enumerate(actors):
        location = f"AUTHORITY.json.actors[{index}]"
        if not isinstance(actor, dict):
            report.error("ACTOR_TYPE", location, "must be an object")
            continue
        actor_id = _require_string(actor, "actor_id", report, location)
        role = _require_string(actor, "role", report, location)
        actor_type = _require_string(actor, "actor_type", report, location)
        acts = _require_string_list(actor, "authorized_acts", report, location)
        scopes = _require_string_list(actor, "authority_scope", report, location)
        if actor_id:
            if actor_id in actor_map:
                report.error("DUPLICATE_ACTOR", location, f"duplicate actor {actor_id!r}")
            else:
                actor_map[actor_id] = actor
        if role not in {"exogenous-authority", "executor", "observer"}:
            report.error("ACTOR_ROLE", f"{location}.role", "unknown actor role")
        if actor_type not in {"human", "ai", "institution", "service", "other"}:
            report.error("ACTOR_TYPE", f"{location}.actor_type", "unknown actor type")
        unknown = set(acts) - ALLOWED_AUTHORITY_ACTS
        if unknown:
            report.error("AUTHORITY_ACT", f"{location}.authorized_acts", f"unknown acts {sorted(unknown)}")
        if role != "exogenous-authority" and acts:
            report.error(
                "AUTHORITY_ROLE",
                f"{location}.authorized_acts",
                "only exogenous-authority actors may receive authority acts",
            )
        if role == "exogenous-authority" and not scopes:
            report.error("AUTHORITY_SCOPE", f"{location}.authority_scope", "must not be empty")

    if not any(actor.get("role") == "exogenous-authority" for actor in actor_map.values()):
        report.error("AUTHORITY_MISSING", "AUTHORITY.json.actors", "no exogenous-authority actor")
    assignment_value = {
        "authority_boundary_id": manifest.get("authority_boundary_id"),
        "study_design": manifest.get("study_design"),
        "assigned_condition": manifest.get("assigned_condition"),
        "actors": manifest.get("actors"),
    }
    assignment_digest = sha256_json_value(assignment_value)
    declared_assignment_digest = corridor_authority.get("assignment_sha256")
    _check_digest(declared_assignment_digest, report, "CORRIDOR.json.exogenous_authority.assignment_sha256")
    if declared_assignment_digest != assignment_digest:
        report.error("AUTHORITY_ASSIGNMENT_HASH", "CORRIDOR.json.exogenous_authority.assignment_sha256", "does not match frozen boundary/condition/actor assignment")
    report.facts["authority_assignment_sha256"] = assignment_digest
    boundary_design_digest = authority_boundary_design_digest(manifest.get("actors"))
    declared_boundary_design_digest = corridor_authority.get(
        "boundary_design_sha256"
    )
    _check_digest(
        declared_boundary_design_digest,
        report,
        "CORRIDOR.json.exogenous_authority.boundary_design_sha256",
    )
    if declared_boundary_design_digest != boundary_design_digest:
        report.error(
            "AUTHORITY_BOUNDARY_HASH",
            "CORRIDOR.json.exogenous_authority.boundary_design_sha256",
            "does not match the canonical role/actor-type/acts/scope design",
        )
    report.facts["authority_boundary_design_sha256"] = boundary_design_digest
    builder_value = corridor.get("builder")
    builder_actor = (
        builder_value.get("actor_id") if isinstance(builder_value, dict) else None
    )
    if not isinstance(builder_actor, str) or builder_actor not in actor_map:
        report.error("BUILDER_ACTOR", "CORRIDOR.json.builder.actor_id", "actor is not declared")
    else:
        builder_record = actor_map[builder_actor]
        if builder_record.get("role") != "executor" or builder_record.get("actor_type") != "ai":
            report.error("BUILDER_ACTOR", "CORRIDOR.json.builder.actor_id", "corridor builder must be a declared AI executor")

    try:
        revision_frozen_at = datetime.fromisoformat(
            str(corridor.get("revision_frozen_at")).replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        revision_frozen_at = None

    capture = _require_object(manifest, "capture", report, "AUTHORITY.json")
    capture_completeness: str | None = None
    if capture is not None:
        capture_completeness = _check_enum(capture.get("completeness"), ALLOWED_CAPTURE_STATUS, report, "AUTHORITY.json.capture.completeness")
        report.facts["authority_capture"] = capture_completeness
        if capture_completeness != "complete":
            if not capture.get("gap_reason"):
                report.error(
                    "CAPTURE_GAP",
                    "AUTHORITY.json.capture.gap_reason",
                    "must explain a partial or unavailable capture",
                )
            report.warn(
                "AUTHORITY_INELIGIBLE",
                "AUTHORITY.json.capture.completeness",
                "run is not eligible for authority-effect comparison",
            )
        expected_interactions = corridor_authority.get("interaction_log_path")
        expected_events = corridor_authority.get("event_log_path")
        if capture.get("interaction_log") != expected_interactions:
            report.error("CAPTURE_PATH", "AUTHORITY.json.capture.interaction_log", "does not match CORRIDOR.json")
        if capture.get("authority_event_log") != expected_events:
            report.error("CAPTURE_PATH", "AUTHORITY.json.capture.authority_event_log", "does not match CORRIDOR.json")
        _check_datetime(
            capture.get("build_cutoff_at"),
            report,
            "AUTHORITY.json.capture.build_cutoff_at",
        )
        _check_datetime(
            capture.get("record_frozen_at"),
            report,
            "AUTHORITY.json.capture.record_frozen_at",
        )
        try:
            build_cutoff_at = datetime.fromisoformat(
                str(capture.get("build_cutoff_at")).replace("Z", "+00:00")
            )
            if revision_frozen_at is not None and build_cutoff_at != revision_frozen_at:
                report.error(
                    "AUTHORITY_BUILD_CUTOFF",
                    "AUTHORITY.json.capture.build_cutoff_at",
                    "must equal CORRIDOR.json revision_frozen_at",
                )
            record_frozen_at = datetime.fromisoformat(
                str(capture.get("record_frozen_at")).replace("Z", "+00:00")
            )
            report.facts["authority_record_frozen_at"] = capture.get(
                "record_frozen_at"
            )
            if record_frozen_at < build_cutoff_at:
                report.error(
                    "CAPTURE_BOUNDARY",
                    "AUTHORITY.json.capture.record_frozen_at",
                    "must not precede the declared build cutoff",
                )
        except (TypeError, ValueError):
            pass

    interactions = load_jsonl(authority_paths["interactions"], report, "interaction")
    _check_sequence(interactions, report, str(authority_paths["interactions"]))
    _check_timestamp_sequence(
        interactions, report, str(authority_paths["interactions"])
    )
    interaction_map = _check_unique_ids(
        interactions, "interaction_id", report, str(authority_paths["interactions"])
    )
    if capture_completeness == "complete":
        if not any(record.get("channel") == "user" for record in interactions):
            report.error("INTERACTION_BOUNDARY", str(authority_paths["interactions"]), "complete capture must contain at least one user message")
        if not any(record.get("channel") == "assistant" for record in interactions):
            report.error("INTERACTION_BOUNDARY", str(authority_paths["interactions"]), "complete capture must contain at least one assistant message")
    elif not interactions and capture is not None:
        if capture.get("first_interaction_id") is not None or capture.get("last_interaction_id") is not None:
            report.error(
                "CAPTURE_BOUNDARY",
                "AUTHORITY.json.capture",
                "empty partial/unavailable capture requires null first/last interaction IDs",
            )
    if capture is not None and interactions:
        if capture.get("first_interaction_id") != interactions[0].get("interaction_id"):
            report.error("CAPTURE_BOUNDARY", "AUTHORITY.json.capture.first_interaction_id", "does not match the first log record")
        if capture.get("last_interaction_id") != interactions[-1].get("interaction_id"):
            report.error("CAPTURE_BOUNDARY", "AUTHORITY.json.capture.last_interaction_id", "does not match the last log record")
        _check_datetime(capture.get("record_frozen_at"), report, "AUTHORITY.json.capture.record_frozen_at")
        try:
            frozen_at = datetime.fromisoformat(
                str(capture.get("record_frozen_at")).replace("Z", "+00:00")
            )
            last_message_at = datetime.fromisoformat(
                str(interactions[-1].get("timestamp")).replace("Z", "+00:00")
            )
            if frozen_at < last_message_at:
                report.error(
                    "CAPTURE_BOUNDARY",
                    "AUTHORITY.json.capture.record_frozen_at",
                    "must not precede the last interaction",
                )
        except (TypeError, ValueError):
            pass
    if condition is not None and interactions:
        try:
            condition_frozen_at = datetime.fromisoformat(
                str(condition.get("frozen_at")).replace("Z", "+00:00")
            )
            first_interaction_at = datetime.fromisoformat(
                str(interactions[0].get("timestamp")).replace("Z", "+00:00")
            )
            if condition_frozen_at > first_interaction_at:
                report.error(
                    "AUTHORITY_CONDITION_TIME",
                    "AUTHORITY.json.assigned_condition.frozen_at",
                    "must not follow the first interaction",
                )
        except (TypeError, ValueError):
            pass
    assistant_before_revision_freeze = False
    post_freeze_interaction_ids: set[str] = set()
    for index, interaction in enumerate(interactions, start=1):
        location = f"{authority_paths['interactions']}:{index}"
        actor_id = interaction.get("actor_id")
        interaction_actor = (
            actor_map.get(actor_id) if isinstance(actor_id, str) else None
        )
        if interaction_actor is None:
            report.error("INTERACTION_ACTOR", f"{location}.actor_id", "actor is not declared")
        channel = _check_enum(interaction.get("channel"), ALLOWED_CHANNELS, report, f"{location}.channel")
        if channel == "user" and (
            interaction_actor is None
            or interaction_actor.get("role") != "exogenous-authority"
        ):
            report.error(
                "INTERACTION_CHANNEL_ACTOR",
                location,
                "user-channel records must come from a declared exogenous-authority actor",
            )
        if channel == "assistant" and (
            actor_id != builder_actor
            or interaction_actor is None
            or interaction_actor.get("role") != "executor"
            or interaction_actor.get("actor_type") != "ai"
        ):
            report.error(
                "INTERACTION_CHANNEL_ACTOR",
                location,
                "assistant-channel records must come from the declared AI corridor builder",
            )
        _check_datetime(interaction.get("timestamp"), report, f"{location}.timestamp")
        if revision_frozen_at is not None:
            try:
                interaction_time = datetime.fromisoformat(
                    str(interaction.get("timestamp")).replace("Z", "+00:00")
                )
                if channel == "assistant" and interaction_time < revision_frozen_at:
                    assistant_before_revision_freeze = True
                if interaction_time >= revision_frozen_at and isinstance(
                    interaction.get("interaction_id"), str
                ):
                    post_freeze_interaction_ids.add(interaction["interaction_id"])
            except (TypeError, ValueError):
                pass
        digest = interaction.get("content_sha256")
        _check_digest(digest, report, f"{location}.content_sha256")
        redacted = interaction.get("redacted")
        if not isinstance(redacted, bool):
            report.error("REDACTION", f"{location}.redacted", "must be boolean")
        content = interaction.get("content")
        if redacted:
            if not interaction.get("redaction_reason"):
                report.error("REDACTION_REASON", location, "redacted content requires a reason")
            report.warn("REDACTED_INTERACTION", location, "content cannot be publicly re-hashed")
        elif not isinstance(content, str):
            report.error("INTERACTION_CONTENT", f"{location}.content", "must be a string")
        elif SHA256_RE.fullmatch(str(digest)) and sha256_text(content) != digest:
            report.error("CONTENT_HASH", f"{location}.content_sha256", "does not match content")

    if (
        capture_completeness == "complete"
        and revision_frozen_at is not None
        and not assistant_before_revision_freeze
    ):
        report.error(
            "AUTHORITY_BUILD_TIME",
            str(authority_paths["interactions"]),
            "complete build capture requires an AI builder response before revision_frozen_at",
        )

    events = load_jsonl(authority_paths["events"], report, "authority event")
    _check_sequence(events, report, str(authority_paths["events"]))
    _check_timestamp_sequence(events, report, str(authority_paths["events"]))
    event_map = _check_unique_ids(events, "event_id", report, str(authority_paths["events"]))
    observed_counts = {act: 0 for act in sorted(ALLOWED_AUTHORITY_ACTS)}
    redacted_authority_sources: set[str] = set()
    lifecycle_interaction_ids: set[str] = set()
    for index, event in enumerate(events, start=1):
        location = f"{authority_paths['events']}:{index}"
        actor_id = event.get("authority_actor_id")
        actor = actor_map.get(actor_id) if isinstance(actor_id, str) else None
        act = _check_enum(event.get("act"), ALLOWED_AUTHORITY_ACTS, report, f"{location}.act")
        if act is not None:
            observed_counts[act] += 1
        if actor is None:
            report.error("AUTHORITY_ACTOR", f"{location}.authority_actor_id", "actor is not declared")
        else:
            if actor.get("role") != "exogenous-authority":
                report.error("AUTHORITY_ROLE", location, "event actor is not exogenous authority")
            authorized_acts = actor.get("authorized_acts")
            if not isinstance(authorized_acts, list) or act not in authorized_acts:
                report.error("AUTHORITY_PERMISSION", location, f"actor is not authorized for {act!r}")
            authority_scope = actor.get("authority_scope")
            if not isinstance(authority_scope, list) or event.get(
                "target_kind"
            ) not in authority_scope:
                report.error("AUTHORITY_SCOPE", location, f"actor scope does not cover target kind {event.get('target_kind')!r}")
        if act == "ratify" and isinstance(actor_id, str) and actor_id == builder_actor:
            report.error("SELF_RATIFY", location, "the corridor builder may not ratify its own corridor")
        raw_references = event.get("interaction_ids")
        if not isinstance(raw_references, list) or not raw_references:
            report.error("AUTHORITY_SOURCE", f"{location}.interaction_ids", "must cite at least one interaction")
            references = []
        else:
            references = []
            for ref_index, reference in enumerate(raw_references):
                if not isinstance(reference, str) or not reference:
                    report.error("AUTHORITY_SOURCE", f"{location}.interaction_ids[{ref_index}]", "must be a non-empty string")
                else:
                    references.append(reference)
        if act in {"ratify", "repeal"}:
            lifecycle_interaction_ids.update(references)
        cited_own_message = False
        for reference in references:
            interaction = interaction_map.get(reference)
            if interaction is None:
                report.error("AUTHORITY_SOURCE", f"{location}.interaction_ids", f"unknown interaction {reference!r}")
            elif interaction.get("actor_id") == actor_id:
                cited_own_message = True
                if interaction.get("redacted") is True:
                    redacted_authority_sources.add(str(reference))
                    report.warn(
                        "REDACTED_AUTHORITY_SOURCE",
                        location,
                        f"authority source {reference!r} is not publicly re-hashable",
                    )
            if interaction is not None:
                try:
                    event_time = datetime.fromisoformat(
                        str(event.get("timestamp")).replace("Z", "+00:00")
                    )
                    interaction_time = datetime.fromisoformat(
                        str(interaction.get("timestamp")).replace("Z", "+00:00")
                    )
                    if event_time < interaction_time:
                        report.error(
                            "AUTHORITY_SOURCE_TIME",
                            location,
                            f"event precedes cited interaction {reference!r}",
                        )
                except (TypeError, ValueError):
                    pass
        if references and not cited_own_message:
            report.error("AUTHORITY_SOURCE", location, "must cite an interaction authored by the authority actor")
        if not isinstance(event.get("target_ref"), str) or not event.get("target_ref"):
            report.error("AUTHORITY_TARGET", f"{location}.target_ref", "must be a non-empty string")
        target_kind = _check_enum(event.get("target_kind"), ALLOWED_AUTHORITY_TARGETS, report, f"{location}.target_kind")
        _check_digest(event.get("target_sha256"), report, f"{location}.target_sha256")
        effect = _check_enum(event.get("effect"), ALLOWED_EFFECTS, report, f"{location}.effect")
        if act in AUTHORITY_ACT_MATRIX:
            allowed_effects, allowed_targets = AUTHORITY_ACT_MATRIX[act]
            if effect not in allowed_effects or target_kind not in allowed_targets:
                report.error(
                    "AUTHORITY_ACT_MATRIX",
                    location,
                    f"{act} requires effect in {sorted(allowed_effects)} and target_kind in {sorted(allowed_targets)}",
                )
        _check_datetime(event.get("timestamp"), report, f"{location}.timestamp")
        if revision_frozen_at is not None:
            try:
                event_time = datetime.fromisoformat(
                    str(event.get("timestamp")).replace("Z", "+00:00")
                )
                if act in {"provision", "reframe", "redirect", "delegate"} and event_time >= revision_frozen_at:
                    report.error(
                        "AUTHORITY_BUILD_TIME",
                        location,
                        f"build-time {act} event must precede revision_frozen_at",
                    )
                if (
                    act in {"ratify", "repeal"}
                    and target_kind == "corridor-revision"
                    and event_time <= revision_frozen_at
                ):
                    report.error(
                        "AUTHORITY_REVISION_TIME",
                        location,
                        f"{act} of a corridor revision must follow revision_frozen_at",
                    )
            except (TypeError, ValueError):
                pass
        if capture is not None:
            try:
                event_time = datetime.fromisoformat(
                    str(event.get("timestamp")).replace("Z", "+00:00")
                )
                frozen_at = datetime.fromisoformat(
                    str(capture.get("record_frozen_at")).replace("Z", "+00:00")
                )
                if event_time > frozen_at:
                    report.error("AUTHORITY_EVENT_BOUNDARY", location, "event occurs after authority record freeze")
            except (TypeError, ValueError):
                pass

    undeclared_post_freeze = post_freeze_interaction_ids - lifecycle_interaction_ids
    if undeclared_post_freeze:
        report.error(
            "AUTHORITY_POST_FREEZE_INTERACTION",
            str(authority_paths["interactions"]),
            "post-freeze interactions must be cited by ratify/repeal lifecycle events; "
            f"uncited IDs: {sorted(undeclared_post_freeze)!r}",
        )

    counts = manifest.get("record_counts")
    if isinstance(counts, dict):
        if counts.get("interactions") != len(interactions):
            report.error("RECORD_COUNT", "AUTHORITY.json.record_counts.interactions", "does not match log")
        if counts.get("authority_events") != len(events):
            report.error("RECORD_COUNT", "AUTHORITY.json.record_counts.authority_events", "does not match log")
    else:
        report.error("RECORD_COUNT", "AUTHORITY.json.record_counts", "must be an object")

    condition_mode = report.facts.get("authority_condition")
    provisions = [event for event in events if event.get("act") == "provision"]
    if capture_completeness == "complete" and len(provisions) != 1:
        report.error("FOUNDING_PROVISION", str(authority_paths["events"]), "complete capture requires exactly one founding provision event")
    if capture_completeness != "complete" and len(provisions) > 1:
        report.error("FOUNDING_PROVISION", str(authority_paths["events"]), "partial/unavailable capture may contain at most one founding provision event")
    if events and events[0].get("act") != "provision":
        report.error("FOUNDING_PROVISION", str(authority_paths["events"]), "the first authority event must be provision")
    if len(provisions) == 1:
        raw_input_binding = corridor.get("input_bundle")
        input_binding = (
            raw_input_binding if isinstance(raw_input_binding, dict) else {}
        )
        input_manifest_path = root / CANONICAL_CORRIDOR_PATHS["input_manifest_path"]
        input_manifest = load_json(input_manifest_path, report, "input-bundle manifest")
        provision = provisions[0]
        if (
            input_manifest is None
            or provision.get("effect") != "issued"
            or provision.get("target_kind") != "input-bundle"
            or provision.get("target_ref") != input_manifest.get("bundle_id")
            or provision.get("target_sha256") != input_binding.get("manifest_sha256")
        ):
            report.error("FOUNDING_PROVISION_BINDING", str(authority_paths["events"]), "founding provision must issue the exact input-bundle ID and manifest digest")
    if condition_mode == "bootstrap-only":
        if len(events) > 1:
            report.error(
                "AUTHORITY_CONDITION_VIOLATION",
                str(authority_paths["events"]),
                f"bootstrap-only run contains later events {[event.get('act') for event in events[1:]]!r}",
            )

    report.facts["observed_authority_acts"] = observed_counts
    report.facts["redacted_interactions"] = sum(
        interaction.get("redacted") is True for interaction in interactions
    )
    report.facts["redacted_authority_sources"] = len(redacted_authority_sources)
    return actor_map, event_map


def _validate_assessments(
    root: Path,
    path: Path,
    corridor: dict[str, Any],
    report: Report,
    theory_versions: list[dict[str, Any]] | None,
    task_versions: list[dict[str, Any]] | None,
    actor_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    records = load_jsonl(path, report, "diagnosis assessment")
    _check_sequence(records, report, str(path))
    record_map = _check_unique_ids(records, "assessment_id", report, str(path))
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    builder_value = corridor.get("builder")
    builder_actor = (
        builder_value.get("actor_id") if isinstance(builder_value, dict) else None
    )
    builder_model = (
        builder_value.get("model") if isinstance(builder_value, dict) else None
    )
    builder_runtime = (
        builder_value.get("runtime") if isinstance(builder_value, dict) else None
    )
    builder_web_access = (
        builder_value.get("web_access") if isinstance(builder_value, dict) else None
    )
    input_manifest = load_json(
        root / CANONICAL_CORRIDOR_PATHS["input_manifest_path"],
        report,
        "input-bundle manifest",
    )
    raw_knowledge_arm = input_manifest.get("knowledge_arm") if input_manifest else None
    knowledge_arm = raw_knowledge_arm if isinstance(raw_knowledge_arm, str) else None
    subject_theory_ref = corridor.get("theory_ref")
    analysis_theory_ref = corridor.get("analysis_theory_ref")
    expected_subject_theory_version = (
        subject_theory_ref.get("version_id")
        if isinstance(subject_theory_ref, dict)
        else None
    )
    expected_analysis_theory_version = (
        analysis_theory_ref.get("version_id")
        if isinstance(analysis_theory_ref, dict)
        else None
    )
    corridor_input_bundle = corridor.get("input_bundle")
    corridor_evaluation_protocol = corridor.get("evaluation_protocol_ref")
    expected_input_bundle_digest = (
        corridor_input_bundle.get("manifest_sha256")
        if isinstance(corridor_input_bundle, dict)
        else None
    )
    expected_task_id = (
        corridor_evaluation_protocol.get("task_id")
        if isinstance(corridor_evaluation_protocol, dict)
        else None
    )
    expected_evaluation_protocol_digest = (
        corridor_evaluation_protocol.get("tree_sha256")
        if isinstance(corridor_evaluation_protocol, dict)
        else None
    )
    expected_analysis_theory_digest = (
        analysis_theory_ref.get("content_sha256")
        if isinstance(analysis_theory_ref, dict)
        else None
    )
    expected_subject_prompt_digest = (
        corridor_evaluation_protocol.get("subject_diagnosis_prompt_sha256")
        if isinstance(corridor_evaluation_protocol, dict)
        else None
    )
    if task_versions is not None:
        matching_tasks = [
            task
            for task in task_versions
            if isinstance(task, dict) and task.get("task_id") == expected_task_id
        ]
        if len(matching_tasks) == 1 and isinstance(
            matching_tasks[0].get("subject_diagnosis_prompt"), dict
        ):
            cataloged_prompt_digest = matching_tasks[0][
                "subject_diagnosis_prompt"
            ].get("sha256")
            if expected_subject_prompt_digest != cataloged_prompt_digest:
                report.error(
                    "ASSESSMENT_PROMPT_BINDING",
                    "CORRIDOR.json.evaluation_protocol_ref.subject_diagnosis_prompt_sha256",
                    "must match the task catalog's frozen subject-diagnosis prompt",
                )
    known_theory_versions = {
        version.get("version_id") for version in (theory_versions or [])
    }
    scenario_trace_times: dict[str, datetime] = {}
    for index, record in enumerate(records, start=1):
        location = f"{path}:{index}"
        scenario_id = _check_enum(record.get("scenario_id"), set(SCENARIO_IDS), report, f"{location}.scenario_id")
        role = _check_enum(record.get("role"), ALLOWED_ASSESSMENT_ROLES, report, f"{location}.role")
        actor_id = _require_string(record, "actor_id", report, location)
        common_assessment_keys = {
            "seq",
            "assessment_id",
            "scenario_id",
            "role",
            "actor_id",
            "actor_type",
            "model",
            "blind_to_other_assessment",
            "timestamp",
            "verdict",
            "classification_status",
            "failure_factors",
            "theory_version_id",
            "rationale",
            "evidence_refs",
            "evidence_sha256",
            "task_id",
            "input_bundle_sha256",
        }
        role_specific_keys = {
            "subject-diagnosis": {
                "runtime",
                "web_access",
                "diagnosis_prompt_sha256",
            },
            "evaluator-assessment": {
                "evaluation_protocol_sha256",
                "analysis_theory_content_sha256",
            },
        }
        if role in role_specific_keys:
            expected_keys = common_assessment_keys | role_specific_keys[role]
            if set(record) != expected_keys:
                report.error(
                    "ASSESSMENT_KEYS",
                    location,
                    f"must contain exactly {sorted(expected_keys)}",
                )
        for key, expected in (
            ("task_id", expected_task_id),
            ("input_bundle_sha256", expected_input_bundle_digest),
        ):
            if record.get(key) != expected:
                report.error(
                    "ASSESSMENT_BINDING",
                    f"{location}.{key}",
                    "does not match the frozen corridor experiment envelope",
                )
        if role == "subject-diagnosis":
            for hidden_key in (
                "evaluation_protocol_sha256",
                "analysis_theory_content_sha256",
            ):
                if hidden_key in record:
                    report.error(
                        "ASSESSMENT_BLINDING",
                        f"{location}.{hidden_key}",
                        "subject diagnosis must not carry evaluator-only identities",
                    )
            if record.get("diagnosis_prompt_sha256") != expected_subject_prompt_digest:
                report.error(
                    "ASSESSMENT_PROMPT_BINDING",
                    f"{location}.diagnosis_prompt_sha256",
                    "must match the cataloged frozen subject-diagnosis prompt",
                )
        if role == "evaluator-assessment":
            for key, expected in (
                ("evaluation_protocol_sha256", expected_evaluation_protocol_digest),
                ("analysis_theory_content_sha256", expected_analysis_theory_digest),
            ):
                if record.get(key) != expected:
                    report.error(
                        "ASSESSMENT_BINDING",
                        f"{location}.{key}",
                        "does not match the frozen evaluator context",
                    )
        actor_type = _check_enum(record.get("actor_type"), {"ai", "human"}, report, f"{location}.actor_type")
        model = record.get("model")
        if actor_type == "ai" and (not isinstance(model, str) or not model):
            report.error("ASSESSOR_MODEL", f"{location}.model", "AI assessor requires an exact model identifier")
        if actor_type == "human" and model is not None:
            report.error("ASSESSOR_MODEL", f"{location}.model", "human assessor model must be null")
        if record.get("blind_to_other_assessment") is not True:
            report.error("ASSESSMENT_BLINDING", f"{location}.blind_to_other_assessment", "must be true")
        _check_datetime(record.get("timestamp"), report, f"{location}.timestamp")
        verdict = _check_enum(record.get("verdict"), ALLOWED_DIAGNOSIS_VERDICTS, report, f"{location}.verdict")
        classification = _check_enum(record.get("classification_status"), ALLOWED_CLASSIFICATION_STATUS, report, f"{location}.classification_status")
        factors = record.get("failure_factors")
        valid_factors: list[str] = []
        if not isinstance(factors, list):
            report.error("FAILURE_FACTORS", f"{location}.failure_factors", "must be an array")
        else:
            valid_factors = [factor for factor in factors if isinstance(factor, str)]
            if len(valid_factors) != len(factors) or set(valid_factors) - ALLOWED_FAILURE_FACTORS:
                report.error("FAILURE_FACTORS", f"{location}.failure_factors", f"must contain only {sorted(ALLOWED_FAILURE_FACTORS)}")
            if len(valid_factors) != len(set(valid_factors)):
                report.error("FAILURE_FACTORS", f"{location}.failure_factors", "must not contain duplicates")
        if verdict == "drift":
            if classification == "classified" and not valid_factors:
                report.error("FAILURE_FACTORS", location, "classified drift requires a P/D/E factor")
            if classification == "not-classifiable" and valid_factors:
                report.error("FAILURE_FACTORS", location, "not-classifiable drift must not claim P/D/E factors")
            if classification == "not-assessed":
                report.error("CLASSIFICATION_STATUS", location, "drift verdict must be classified or not-classifiable")
        elif verdict == "no-drift" and (classification != "not-assessed" or valid_factors):
            report.error("FAILURE_FACTORS", location, "no-drift must be not-assessed with no factors")
        elif verdict == "abstain" and (classification != "not-classifiable" or valid_factors):
            report.error("FAILURE_FACTORS", location, "abstain must be not-classifiable with no factors")
        _require_string(record, "rationale", report, location)
        evidence_refs = record.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            report.error("ASSESSMENT_EVIDENCE", f"{location}.evidence_refs", "must cite at least one evidence file")
        else:
            canonical_scenario_evidence = (
                f"trace/scenarios/{scenario_id}.json" if scenario_id else None
            )
            if evidence_refs != [canonical_scenario_evidence]:
                report.error(
                    "ASSESSMENT_EVIDENCE_BOUNDARY",
                    f"{location}.evidence_refs",
                    "must cite only this scenario's canonical pre-adjudication trace record",
                )
            for evidence_index, evidence_ref in enumerate(evidence_refs):
                if not isinstance(evidence_ref, str) or not evidence_ref.startswith(
                    "trace/"
                ):
                    report.error(
                        "ASSESSMENT_EVIDENCE_BOUNDARY",
                        f"{location}.evidence_refs[{evidence_index}]",
                        "assessment evidence must be a frozen trace/ artifact, not an evaluation output",
                    )
                evidence_path = _safe_member(root, evidence_ref, report, f"{location}.evidence_refs[{evidence_index}]")
                if evidence_path is not None and not evidence_path.is_file():
                    report.error("ASSESSMENT_EVIDENCE", str(evidence_path), "evidence file is missing")
            evidence_digest = record.get("evidence_sha256")
            _check_digest(evidence_digest, report, f"{location}.evidence_sha256")
            canonical_path = _safe_member(
                root,
                canonical_scenario_evidence,
                report,
                f"{location}.evidence_sha256",
            )
            if (
                canonical_path is not None
                and canonical_path.is_file()
                and SHA256_RE.fullmatch(str(evidence_digest))
                and sha256_file(canonical_path) != evidence_digest
            ):
                report.error(
                    "ASSESSMENT_EVIDENCE_HASH",
                    f"{location}.evidence_sha256",
                    "does not match the frozen pre-adjudication trace bytes",
                )
            if canonical_path is not None and canonical_path.is_file():
                trace_record = load_json(
                    canonical_path, report, "assessment trace evidence"
                )
                if trace_record is not None:
                    try:
                        observed_at = datetime.fromisoformat(
                            str(trace_record.get("observed_at")).replace("Z", "+00:00")
                        )
                        assessed_at = datetime.fromisoformat(
                            str(record.get("timestamp")).replace("Z", "+00:00")
                        )
                        if observed_at >= assessed_at:
                            report.error(
                                "ASSESSMENT_EVIDENCE_TIME",
                                location,
                                "trace observation must be frozen before the assessment",
                            )
                        if scenario_id is not None:
                            scenario_trace_times[scenario_id] = observed_at
                    except (TypeError, ValueError):
                        pass
        theory_version_id = record.get("theory_version_id")
        if theory_version_id is not None and (
            not isinstance(theory_version_id, str)
            or (theory_versions is not None and theory_version_id not in known_theory_versions)
        ):
            report.error("ASSESSMENT_THEORY", f"{location}.theory_version_id", "must be null or a cataloged theory version")
        if role == "subject-diagnosis" and actor_id != builder_actor:
            report.error("ASSESSMENT_ACTOR", f"{location}.actor_id", "subject diagnosis must come from the corridor builder")
        if role == "subject-diagnosis" and (
            actor_type != "ai" or model != builder_model
        ):
            report.error("ASSESSMENT_ACTOR", location, "subject diagnosis actor type/model must match the AI corridor builder")
        if role == "subject-diagnosis" and (
            record.get("runtime") != builder_runtime
            or record.get("web_access") != builder_web_access
        ):
            report.error(
                "ASSESSMENT_RUNTIME",
                location,
                "subject runtime and web_access must match the frozen corridor builder context",
            )
        if role == "evaluator-assessment" and actor_id == builder_actor:
            report.error("ASSESSMENT_ACTOR", f"{location}.actor_id", "evaluator must be independent of the builder")
        if role == "evaluator-assessment" and actor_type != "human":
            report.error(
                "ASSESSMENT_ACTOR",
                f"{location}.actor_type",
                "the v1 reference protocol requires an independent human evaluator",
            )
        if role == "evaluator-assessment":
            evaluator_actor = actor_map.get(actor_id) if isinstance(actor_id, str) else None
            if (
                evaluator_actor is None
                or evaluator_actor.get("role") != "observer"
                or evaluator_actor.get("actor_type") != "human"
            ):
                report.error(
                    "ASSESSMENT_ACTOR",
                    f"{location}.actor_id",
                    "evaluator must be a declared human observer in the frozen actor roster",
                )
        if role == "subject-diagnosis":
            if knowledge_arm == "theory-only" and theory_version_id != expected_subject_theory_version:
                report.error("ASSESSMENT_THEORY", f"{location}.theory_version_id", "must match the theory version associated with the assigned knowledge treatment")
            if knowledge_arm in {"methodology", "control-none", "control-other", "not-applicable"} and theory_version_id is not None:
                report.error("ASSESSMENT_THEORY", f"{location}.theory_version_id", "subject may not claim an unseen theory representation")
        if role == "evaluator-assessment" and theory_version_id != expected_analysis_theory_version:
            report.error("ASSESSMENT_THEORY", f"{location}.theory_version_id", "evaluator assessment must cite the corridor's cataloged analysis theory version")
        if scenario_id and role:
            key = (scenario_id, role)
            if key in pairs:
                report.error("DUPLICATE_ASSESSMENT", location, f"duplicate {key!r}")
            else:
                pairs[key] = record
    verdict_agreement = 0
    decisive_evaluator_count = 0
    decisive_agreement_count = 0
    factor_agreement = 0
    factor_comparable = 0
    complete_pairs = 0
    subject_records = [
        record
        for (scenario, role), record in pairs.items()
        if role == "subject-diagnosis"
    ]
    evaluator_records = [
        record
        for (scenario, role), record in pairs.items()
        if role == "evaluator-assessment"
    ]
    if subject_records:
        try:
            earliest_subject_time = min(
                datetime.fromisoformat(
                    str(record.get("timestamp")).replace("Z", "+00:00")
                )
                for record in subject_records
            )
            relevant_trace_times = [
                scenario_trace_times[record.get("scenario_id")]
                for record in subject_records
                if record.get("scenario_id") in scenario_trace_times
            ]
            if (
                len(relevant_trace_times) == len(subject_records)
                and max(relevant_trace_times) >= earliest_subject_time
            ):
                report.error(
                    "ASSESSMENT_TRACE_BARRIER",
                    str(path),
                    "all scenario traces must be frozen before any subject diagnosis",
                )
        except (TypeError, ValueError):
            pass
    if subject_records and evaluator_records:
        try:
            latest_subject_time = max(
                datetime.fromisoformat(
                    str(record.get("timestamp")).replace("Z", "+00:00")
                )
                for record in subject_records
            )
            earliest_evaluator_time = min(
                datetime.fromisoformat(
                    str(record.get("timestamp")).replace("Z", "+00:00")
                )
                for record in evaluator_records
            )
            subject_sequences = [record.get("seq") for record in subject_records]
            evaluator_sequences = [record.get("seq") for record in evaluator_records]
            if (
                latest_subject_time >= earliest_evaluator_time
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    for value in subject_sequences + evaluator_sequences
                )
                or max(subject_sequences) >= min(evaluator_sequences)
            ):
                report.error(
                    "ASSESSMENT_GLOBAL_ORDER",
                    str(path),
                    "all six subject diagnoses must be frozen before any evaluator assessment",
                )
        except (TypeError, ValueError):
            pass
    for scenario_id in SCENARIO_IDS:
        subject = pairs.get((scenario_id, "subject-diagnosis"))
        evaluator = pairs.get((scenario_id, "evaluator-assessment"))
        if subject and evaluator:
            complete_pairs += 1
            if subject.get("verdict") == evaluator.get("verdict"):
                verdict_agreement += 1
            if evaluator.get("verdict") in ("drift", "no-drift"):
                decisive_evaluator_count += 1
                if subject.get("verdict") == evaluator.get("verdict"):
                    decisive_agreement_count += 1
            subject_factors = subject.get("failure_factors")
            evaluator_factors = evaluator.get("failure_factors")
            clean_subject_factors = {value for value in subject_factors if isinstance(value, str)} if isinstance(subject_factors, list) else None
            clean_evaluator_factors = {value for value in evaluator_factors if isinstance(value, str)} if isinstance(evaluator_factors, list) else None
            factors_are_comparable = (
                evaluator.get("verdict") == "drift"
                and evaluator.get("classification_status") == "classified"
                and clean_evaluator_factors is not None
            )
            if factors_are_comparable:
                factor_comparable += 1
                if (
                    subject.get("verdict") == "drift"
                    and subject.get("classification_status") == "classified"
                    and clean_subject_factors is not None
                    and clean_subject_factors == clean_evaluator_factors
                ):
                    factor_agreement += 1
            try:
                subject_at = datetime.fromisoformat(str(subject.get("timestamp")).replace("Z", "+00:00"))
                evaluator_at = datetime.fromisoformat(str(evaluator.get("timestamp")).replace("Z", "+00:00"))
                subject_seq = subject.get("seq")
                evaluator_seq = evaluator.get("seq")
                if (
                    subject_at >= evaluator_at
                    or not isinstance(subject_seq, int)
                    or not isinstance(evaluator_seq, int)
                    or subject_seq >= evaluator_seq
                ):
                    report.error("ASSESSMENT_ORDER", scenario_id, "subject diagnosis must be frozen strictly before evaluator assessment in time and sequence")
            except (TypeError, ValueError):
                pass
    report.facts.update(
        {
            "diagnosis_pair_count": complete_pairs,
            "diagnosis_verdict_agreement_count": verdict_agreement,
            "diagnosis_evaluable_count": decisive_evaluator_count,
            "diagnosis_decisive_agreement_count": decisive_agreement_count,
            "diagnosis_factor_comparable_count": factor_comparable,
            "diagnosis_factor_exact_agreement_count": factor_agreement,
        }
    )
    return record_map


def _validate_registry_diagnosis(
    value: Any, report: Report, location: str
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        report.error("DIAGNOSIS_RECORD", location, "must be an object")
        return None
    _require_string(value, "actor_id", report, location)
    _check_enum(
        value.get("actor_type"),
        {"ai", "human"},
        report,
        f"{location}.actor_type",
    )
    verdict = _check_enum(
        value.get("verdict"), ALLOWED_DIAGNOSIS_VERDICTS, report, f"{location}.verdict"
    )
    classification = _check_enum(
        value.get("classification_status"),
        ALLOWED_CLASSIFICATION_STATUS,
        report,
        f"{location}.classification_status",
    )
    factors = value.get("failure_factors")
    clean_factors: list[str] = []
    if not isinstance(factors, list):
        report.error("FAILURE_FACTORS", f"{location}.failure_factors", "must be an array")
    else:
        clean_factors = [factor for factor in factors if isinstance(factor, str)]
        if (
            len(clean_factors) != len(factors)
            or set(clean_factors) - ALLOWED_FAILURE_FACTORS
            or len(clean_factors) != len(set(clean_factors))
        ):
            report.error(
                "FAILURE_FACTORS",
                f"{location}.failure_factors",
                f"must contain unique values from {sorted(ALLOWED_FAILURE_FACTORS)}",
            )
    theory_version_id = value.get("theory_version_id")
    if theory_version_id is not None and not isinstance(theory_version_id, str):
        report.error(
            "DIAGNOSIS_THEORY",
            f"{location}.theory_version_id",
            "must be a string or null",
        )
    if verdict == "drift" and (
        classification not in {"classified", "not-classifiable"}
        or (classification == "classified" and not clean_factors)
        or (classification == "not-classifiable" and clean_factors)
    ):
        report.error("DIAGNOSIS_SEMANTICS", location, "invalid classified drift record")
    if verdict == "no-drift" and (
        classification != "not-assessed" or clean_factors
    ):
        report.error("DIAGNOSIS_SEMANTICS", location, "no-drift may not claim factors")
    if verdict == "abstain" and (
        classification != "not-classifiable" or clean_factors
    ):
        report.error("DIAGNOSIS_SEMANTICS", location, "abstain may not claim factors")
    return value


def _valid_v2_repository_hostname(hostname: str) -> bool:
    if not hostname or hostname.endswith(".") or not hostname.isascii():
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if len(hostname) > 253:
        return False
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        is not None
        for label in hostname.split(".")
    )


def _validate_v2_world_ref(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, dict):
        report.error("REQUIRED_OBJECT", location, "must be an object")
        return
    expected_world = {
        "project_id",
        "run_id",
        "generation_id",
        "repository_url",
        "base_commit",
        "environment_sha256",
        "evidence_prefix",
        "derived_state_sha256",
    }
    if set(value) != expected_world:
        report.error(
            "WORLD_REF_FIELDS",
            location,
            f"must contain exactly {sorted(expected_world)}",
        )
    repository_url = value.get("repository_url")
    valid_repository_url = False
    if (
        isinstance(repository_url, str)
        and repository_url == repository_url.strip()
        and repository_url.startswith("https://")
        and "\\" not in repository_url
        and not any(
            character.isspace()
            or ord(character) < 32
            or ord(character) == 127
            for character in repository_url
        )
    ):
        try:
            parts = urlsplit(repository_url)
            port = parts.port
            hostname = parts.hostname
            valid_repository_url = (
                parts.scheme == "https"
                and bool(parts.netloc)
                and bool(hostname)
                and _valid_v2_repository_hostname(str(hostname))
                and parts.username is None
                and parts.password is None
                and not parts.query
                and not parts.fragment
                and not parts.netloc.endswith(":")
                and (port is None or 1 <= port <= 65535)
            )
        except ValueError:
            valid_repository_url = False
    if not valid_repository_url:
        report.error(
            "WORLD_REF_REPOSITORY",
            f"{location}.repository_url",
            "must be a non-empty HTTPS repository identity",
        )
    for key in ("project_id", "run_id", "generation_id"):
        _require_string(value, key, report, location)
    commit = value.get("base_commit")
    if not isinstance(commit, str) or not GIT_SHA1_RE.fullmatch(commit):
        report.error(
            "WORLD_REF_COMMIT",
            f"{location}.base_commit",
            "must be a full lowercase Git commit",
        )
    _check_digest(
        value.get("environment_sha256"), report, f"{location}.environment_sha256"
    )
    _check_digest(
        value.get("derived_state_sha256"),
        report,
        f"{location}.derived_state_sha256",
    )
    prefix = value.get("evidence_prefix")
    if not isinstance(prefix, dict):
        report.error("WORLD_REF_PREFIX", f"{location}.evidence_prefix", "must be an object")
        return
    expected_prefix = {
        "stream_id",
        "through_sequence",
        "prefix_sha256",
        "admission",
        "projector",
    }
    prefix_location = f"{location}.evidence_prefix"
    if set(prefix) != expected_prefix:
        report.error(
            "WORLD_REF_PREFIX_FIELDS",
            prefix_location,
            f"must contain exactly {sorted(expected_prefix)}",
        )
    _require_string(prefix, "stream_id", report, prefix_location)
    sequence = prefix.get("through_sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        report.error(
            "WORLD_REF_PREFIX_SEQUENCE",
            f"{prefix_location}.through_sequence",
            "must be a non-negative integer",
        )
    _check_digest(prefix.get("prefix_sha256"), report, f"{prefix_location}.prefix_sha256")
    admission = prefix.get("admission")
    admission_location = f"{prefix_location}.admission"
    if not isinstance(admission, dict):
        report.error("REQUIRED_OBJECT", admission_location, "must be an object")
    else:
        expected_admission = {
            "receipt_id",
            "admitted_root_sha256",
            "rule_revision",
            "rule_sha256",
        }
        if set(admission) != expected_admission:
            report.error(
                "WORLD_REF_ADMISSION_FIELDS",
                admission_location,
                f"must contain exactly {sorted(expected_admission)}",
            )
        for key in ("receipt_id", "rule_revision"):
            _require_string(admission, key, report, admission_location)
        for key in ("admitted_root_sha256", "rule_sha256"):
            _check_digest(admission.get(key), report, f"{admission_location}.{key}")

    projector = prefix.get("projector")
    projector_location = f"{prefix_location}.projector"
    if not isinstance(projector, dict):
        report.error("REQUIRED_OBJECT", projector_location, "must be an object")
        return
    expected_projector = {
        "schema_version",
        "algorithm_id",
        "algorithm_version",
        "algorithm_sha256",
    }
    if set(projector) != expected_projector:
        report.error(
            "WORLD_REF_PROJECTOR_FIELDS",
            projector_location,
            f"must contain exactly {sorted(expected_projector)}",
        )
    for key in ("schema_version", "algorithm_id", "algorithm_version"):
        _require_string(projector, key, report, projector_location)
    _check_digest(
        projector.get("algorithm_sha256"),
        report,
        f"{projector_location}.algorithm_sha256",
    )


def candidate_semantic_closure_sha256(candidate: dict[str, Any]) -> str:
    """Hash Candidate semantics while excluding later orthogonal evidence surfaces."""

    projection = {
        key: value
        for key, value in candidate.items()
        if key not in {"semantic_closure_sha256", "assurances", "authority_evidence"}
    }
    return sha256_json_value(projection)


def _validate_candidate_v2(
    root: Path,
    candidate: dict[str, Any],
    report: Report,
    *,
    allow_template: bool,
    method_versions: list[dict[str, Any]] | None,
) -> None:
    """Validate the deliberately narrow, non-indexable v2 Candidate template."""

    manifest_path = root / "CORRIDOR.json"
    allowed_top = {
        "schema_version",
        "template",
        "candidate_id",
        "revision_id",
        "status",
        "candidate_state",
        "semantic_closure_sha256",
        "method_ref",
        "input_planes",
        "guide",
        "position",
        "world_ref",
        "guide_result",
        "implementation",
        "authority_evidence",
        "assurances",
        "reentry",
        "builder_eligible",
        "known_limits",
    }
    unknown_top = sorted(set(candidate) - allowed_top)
    if unknown_top:
        report.error(
            "CANDIDATE_FIELDS",
            "CORRIDOR.json",
            f"unknown v2 fields: {unknown_top}",
        )

    is_template = candidate.get("template") is True
    report.facts.update(
        {
            "schema_version": CANDIDATE_SCHEMA,
            "template": is_template,
            "registry_eligible": False,
        }
    )
    if not is_template:
        report.error(
            "CANDIDATE_TEMPLATE_ONLY",
            str(manifest_path),
            "draft v2 validates only non-indexable templates",
        )
    elif not allow_template:
        report.error("TEMPLATE", str(manifest_path), "template artifacts cannot be indexed")

    candidate_id = _require_string(candidate, "candidate_id", report, "CORRIDOR.json")
    revision_id = _require_string(candidate, "revision_id", report, "CORRIDOR.json")
    if candidate.get("status") != "candidate":
        report.error(
            "CANDIDATE_STATUS",
            "CORRIDOR.json.status",
            "v2 template status must be candidate",
        )
    candidate_state = candidate.get("candidate_state")
    if not isinstance(candidate_state, str) or candidate_state not in {"open", "frozen"}:
        report.error(
            "CANDIDATE_STATE",
            "CORRIDOR.json.candidate_state",
            "must be open or frozen",
        )
    semantic_closure = candidate.get("semantic_closure_sha256")
    if candidate_state == "open" and semantic_closure is not None:
        report.error(
            "CANDIDATE_OPEN_CLOSURE",
            "CORRIDOR.json.semantic_closure_sha256",
            "open Candidate must not claim a semantic closure",
        )
    elif candidate_state == "frozen":
        _check_digest(
            semantic_closure,
            report,
            "CORRIDOR.json.semantic_closure_sha256",
        )
    if candidate.get("builder_eligible") is not False:
        report.error(
            "CANDIDATE_BUILDER_ELIGIBILITY",
            "CORRIDOR.json.builder_eligible",
            "draft v2 Candidate must be explicitly builder-ineligible",
        )
    report.facts.update(
        {
            "candidate_id": candidate_id,
            "revision_id": revision_id,
            "status": candidate.get("status"),
            "candidate_state": candidate_state,
            "builder_eligible": candidate.get("builder_eligible"),
        }
    )

    method_ref = _require_object(candidate, "method_ref", report, "CORRIDOR.json")
    if method_ref is not None:
        allowed_method = {
            "version_id",
            "source_commit",
            "path",
            "content_sha256",
            "builder_eligible",
        }
        unknown = sorted(set(method_ref) - allowed_method)
        if unknown:
            report.error(
                "METHOD_REF_FIELDS",
                "CORRIDOR.json.method_ref",
                f"unknown fields: {unknown}",
            )
        if "source_commit" not in method_ref:
            report.error(
                "METHOD_REF_FIELDS",
                "CORRIDOR.json.method_ref",
                "must explicitly declare the current method source_commit",
            )
        method_version_id = _require_string(
            method_ref, "version_id", report, "CORRIDOR.json.method_ref"
        )
        method_path = _require_string(
            method_ref, "path", report, "CORRIDOR.json.method_ref"
        )
        method_digest = method_ref.get("content_sha256")
        method_source_commit = method_ref.get("source_commit")
        if (
            not isinstance(method_source_commit, str)
            or not GIT_SHA1_RE.fullmatch(method_source_commit)
        ):
            report.error(
                "METHOD_REF_SOURCE_COMMIT",
                "CORRIDOR.json.method_ref.source_commit",
                "must be the full lowercase Git commit of the cataloged current method",
            )
        _check_digest(
            method_digest, report, "CORRIDOR.json.method_ref.content_sha256"
        )
        if method_ref.get("builder_eligible") is not False:
            report.error(
                "METHOD_REF_ELIGIBILITY",
                "CORRIDOR.json.method_ref.builder_eligible",
                "must preserve the cataloged draft ineligibility",
            )
        if method_versions is None:
            report.error(
                "METHOD_CATALOG_REQUIRED",
                "CORRIDOR.json.method_ref",
                "v2 Candidate validation requires the method catalog",
            )
        else:
            matches = [
                version
                for version in method_versions
                if version.get("version_id") == method_version_id
                and version.get("path") == method_path
                and version.get("content_sha256") == method_digest
                and version.get("builder_eligible") is False
                and version.get("study_eligible") is True
                and version.get("adoption_eligible") is False
                and version.get("source_commit") == method_source_commit
            ]
            if len(matches) != 1:
                report.error(
                    "METHOD_REF",
                    "CORRIDOR.json.method_ref",
                    "must match exactly one current, study-frozen, adoption-ineligible cataloged method version",
                )

    declared_rules: list[dict[str, Any]] = []
    declared_facts: list[dict[str, Any]] = []
    input_planes = _require_object(candidate, "input_planes", report, "CORRIDOR.json")
    if input_planes is not None:
        expected_input_planes = {"rules", "facts"}
        if set(input_planes) != expected_input_planes:
            report.error(
                "INPUT_PLANES",
                "CORRIDOR.json.input_planes",
                "must contain exactly the Rule and Fact input planes",
            )
        input_specs = {
            "rules": ({"rule_id", "version", "scope", "ref"},),
            "facts": ({"fact_id", "world_ref_ref", "ref"},),
        }
        seen_input_ids: set[str] = set()
        for kind, (allowed_fields,) in input_specs.items():
            records = _require_list(
                input_planes, kind, report, "CORRIDOR.json.input_planes"
            ) or []
            if not records:
                report.error(
                    "INPUT_PLANE_EMPTY",
                    f"CORRIDOR.json.input_planes.{kind}",
                    "must contain at least one declared input",
                )
            for index, record in enumerate(records):
                location = f"CORRIDOR.json.input_planes.{kind}[{index}]"
                if not isinstance(record, dict):
                    report.error("INPUT_RECORD", location, "must be an object")
                    continue
                record_fields = allowed_fields
                if kind == "rules" and "allowed_actions_sha256" in record:
                    record_fields = allowed_fields | {"allowed_actions_sha256"}
                if set(record) != record_fields:
                    report.error(
                        "INPUT_RECORD_FIELDS",
                        location,
                        f"must contain exactly {sorted(record_fields)}",
                    )
                id_key = next(key for key in record_fields if key.endswith("_id"))
                input_id = _require_string(record, id_key, report, location)
                if input_id in seen_input_ids:
                    report.error("DUPLICATE_INPUT", location, "input ids must be unique")
                elif input_id:
                    seen_input_ids.add(input_id)
                if kind == "rules":
                    declared_rules.append(record)
                else:
                    declared_facts.append(record)
                for key in sorted(record_fields - {id_key, "allowed_actions_sha256"}):
                    _require_string(record, key, report, location)
                if "allowed_actions_sha256" in record:
                    _check_digest(
                        record.get("allowed_actions_sha256"),
                        report,
                        f"{location}.allowed_actions_sha256",
                    )
                if (
                    kind == "facts"
                    and record.get("world_ref_ref") != "world_ref"
                ):
                    report.error(
                        "FACT_WORLD_REF",
                        f"{location}.world_ref_ref",
                        "must bind the exact Candidate WorldRef",
                    )

    guide = _require_object(candidate, "guide", report, "CORRIDOR.json")
    if guide is not None:
        expected_guide = {"contract_path", "evaluation", "input_refs", "result"}
        if set(guide) != expected_guide:
            report.error(
                "GUIDE_FIELDS",
                "CORRIDOR.json.guide",
                f"must contain exactly {sorted(expected_guide)}",
            )
        if guide.get("evaluation") != "deterministic":
            report.error(
                "GUIDE_DETERMINISM",
                "CORRIDOR.json.guide.evaluation",
                "Guide must declare deterministic evaluation",
            )
        contract_path = guide.get("contract_path")
        if contract_path != "implementation/GUIDE-CONTRACT.md":
            report.error(
                "GUIDE_CONTRACT_PATH",
                "CORRIDOR.json.guide.contract_path",
                "draft v2 fixes the Guide contract at implementation/GUIDE-CONTRACT.md",
            )
        guide_path = _safe_member(
            root,
            contract_path,
            report,
            "CORRIDOR.json.guide.contract_path",
        )
        if guide_path is not None and not guide_path.is_file():
            report.error(
                "GUIDE_CONTRACT_PATH",
                str(guide_path),
                "must be a regular file",
            )
        input_refs = _require_object(
            guide, "input_refs", report, "CORRIDOR.json.guide"
        )
        expected_input_refs = {
            "rules": "input_planes.rules",
            "admitted_facts": "input_planes.facts",
            "position": "position",
            "evidential_warranty": "assurances.evidential_warranty",
            "authority_warranty": "assurances.authority_warranty",
        }
        if input_refs is not None and input_refs != expected_input_refs:
            report.error(
                "GUIDE_INPUT_REFS",
                "CORRIDOR.json.guide.input_refs",
                "must bind Rules, admitted Facts, complete Position, and both warranty inputs",
            )
        result = _require_object(guide, "result", report, "CORRIDOR.json.guide")
        if result is not None:
            if set(result) != {"cardinality", "variants"}:
                report.error(
                    "GUIDE_RESULT_FIELDS",
                    "CORRIDOR.json.guide.result",
                    "must contain exactly cardinality and variants",
                )
            if result.get("cardinality") != "exactly-one":
                report.error(
                    "GUIDE_RESULT_CARDINALITY",
                    "CORRIDOR.json.guide.result.cardinality",
                    "must be exactly-one",
                )
            if result.get("variants") != ["entrance", "typed-refusal"]:
                report.error(
                    "GUIDE_RESULT_VARIANTS",
                    "CORRIDOR.json.guide.result.variants",
                    "must be the ordered entrance or typed-refusal union",
                )

    position = _require_object(candidate, "position", report, "CORRIDOR.json")
    if position is not None:
        expected_position = {
            "role_definition",
            "role_assignment",
            "object_ref",
            "world_ref_ref",
        }
        if set(position) != expected_position:
            report.error(
                "POSITION_FIELDS",
                "CORRIDOR.json.position",
                f"must contain exactly {sorted(expected_position)}",
            )
        for key in ("object_ref", "world_ref_ref"):
            _require_string(position, key, report, "CORRIDOR.json.position")
        role_definition = _require_object(
            position, "role_definition", report, "CORRIDOR.json.position"
        )
        expected_role_definition = {"role_id", "version", "scope", "ref"}
        if role_definition is not None:
            if set(role_definition) != expected_role_definition:
                report.error(
                    "ROLE_DEFINITION_FIELDS",
                    "CORRIDOR.json.position.role_definition",
                    f"must contain exactly {sorted(expected_role_definition)}",
                )
            for key in sorted(expected_role_definition):
                _require_string(
                    role_definition,
                    key,
                    report,
                    "CORRIDOR.json.position.role_definition",
                )
        role_assignment = _require_object(
            position, "role_assignment", report, "CORRIDOR.json.position"
        )
        expected_role_assignment = {
            "holder",
            "role_id",
            "scope",
            "assignment_fact_id",
            "assignment_ref",
            "required_warranty_kinds",
        }
        if role_assignment is not None:
            if set(role_assignment) != expected_role_assignment:
                report.error(
                    "ROLE_ASSIGNMENT_FIELDS",
                    "CORRIDOR.json.position.role_assignment",
                    f"must contain exactly {sorted(expected_role_assignment)}",
                )
            for key in sorted(expected_role_assignment - {"required_warranty_kinds"}):
                _require_string(
                    role_assignment,
                    key,
                    report,
                    "CORRIDOR.json.position.role_assignment",
                )
            if role_assignment.get("required_warranty_kinds") != [
                "EvidentialWarranty",
                "AuthorityWarranty",
            ]:
                report.error(
                    "ROLE_ASSIGNMENT_WARRANTIES",
                    "CORRIDOR.json.position.role_assignment.required_warranty_kinds",
                    "must require exactly EvidentialWarranty then AuthorityWarranty",
                )
        if (
            role_definition is not None
            and role_assignment is not None
            and (
                role_definition.get("role_id") != role_assignment.get("role_id")
                or role_definition.get("scope") != role_assignment.get("scope")
            )
        ):
            report.error(
                "ROLE_ASSIGNMENT_BINDING",
                "CORRIDOR.json.position.role_assignment",
                "must bind the declared role definition and scope",
            )
        if role_definition is not None:
            rule_matches = [
                rule
                for rule in declared_rules
                if rule.get("ref") == role_definition.get("ref")
                and rule.get("version") == role_definition.get("version")
                and rule.get("scope") == role_definition.get("scope")
            ]
            if len(rule_matches) != 1:
                report.error(
                    "ROLE_DEFINITION_RULE",
                    "CORRIDOR.json.position.role_definition",
                    "must resolve exactly once to a declared Rule ref, version, and scope",
                )
        if role_assignment is not None:
            assignment_matches = [
                fact
                for fact in declared_facts
                if fact.get("fact_id") == role_assignment.get("assignment_fact_id")
                and fact.get("ref") == role_assignment.get("assignment_ref")
            ]
            if len(assignment_matches) != 1:
                report.error(
                    "ROLE_ASSIGNMENT_FACT",
                    "CORRIDOR.json.position.role_assignment",
                    "must resolve exactly once to an admitted Fact id and ref",
                )
        expected_object_ref = (
            f"{candidate_id}@{revision_id}"
            if isinstance(candidate_id, str) and isinstance(revision_id, str)
            else None
        )
        if expected_object_ref is not None and position.get("object_ref") != expected_object_ref:
            report.error(
                "POSITION_OBJECT_REF",
                "CORRIDOR.json.position.object_ref",
                f"must equal {expected_object_ref}",
            )
        if position.get("world_ref_ref") != "world_ref":
            report.error(
                "POSITION_WORLD_REF",
                "CORRIDOR.json.position.world_ref_ref",
                "must bind the exact Candidate WorldRef",
            )

    _validate_v2_world_ref(candidate.get("world_ref"), report, "CORRIDOR.json.world_ref")

    guide_result = _require_object(candidate, "guide_result", report, "CORRIDOR.json")
    entrance: dict[str, Any] | None = None
    if guide_result is not None:
        kind = guide_result.get("kind")
        report.facts["guide_result_kind"] = kind
        if kind == "entrance":
            if set(guide_result) != {"kind", "entrance"}:
                report.error(
                    "GUIDE_RESULT_UNION",
                    "CORRIDOR.json.guide_result",
                    "entrance result must contain exactly kind and entrance",
                )
            entrance_value = guide_result.get("entrance")
            if not isinstance(entrance_value, dict):
                report.error(
                    "REQUIRED_OBJECT",
                    "CORRIDOR.json.guide_result.entrance",
                    "must be an object",
                )
            else:
                entrance = entrance_value
        elif kind == "typed-refusal":
            if set(guide_result) != {"kind", "refusal"}:
                report.error(
                    "GUIDE_RESULT_UNION",
                    "CORRIDOR.json.guide_result",
                    "typed-refusal result must contain exactly kind and refusal",
                )
            refusal = guide_result.get("refusal")
            if not isinstance(refusal, dict):
                report.error(
                    "REQUIRED_OBJECT",
                    "CORRIDOR.json.guide_result.refusal",
                    "must be an object",
                )
            else:
                if set(refusal) != {"code", "reason", "governing_rule"}:
                    report.error(
                        "GUIDE_REFUSAL_FIELDS",
                        "CORRIDOR.json.guide_result.refusal",
                        "must contain exactly code, reason, and governing_rule",
                    )
                for key in ("code", "reason"):
                    _require_string(
                        refusal,
                        key,
                        report,
                        "CORRIDOR.json.guide_result.refusal",
                    )
                if refusal.get("code") not in {
                    "stale",
                    "unauthorized",
                    "unknown",
                    "not_assessed",
                    "stale_world_ref",
                }:
                    report.error(
                        "GUIDE_REFUSAL_CODE",
                        "CORRIDOR.json.guide_result.refusal.code",
                        "must be a stable typed warranty/world refusal code",
                    )
                governing_rule = refusal.get("governing_rule")
                if not isinstance(governing_rule, dict):
                    report.error(
                        "GUIDE_REFUSAL_RULE",
                        "CORRIDOR.json.guide_result.refusal.governing_rule",
                        "must bind one declared Rule and evaluated input context",
                    )
                else:
                    expected_governing = {
                        "rule_id",
                        "rule_version",
                        "rule_ref",
                        "input_context_sha256",
                    }
                    if set(governing_rule) != expected_governing:
                        report.error(
                            "GUIDE_REFUSAL_RULE_FIELDS",
                            "CORRIDOR.json.guide_result.refusal.governing_rule",
                            f"must contain exactly {sorted(expected_governing)}",
                        )
                    _check_digest(
                        governing_rule.get("input_context_sha256"),
                        report,
                        "CORRIDOR.json.guide_result.refusal.governing_rule.input_context_sha256",
                    )
                    for key in ("rule_id", "rule_version", "rule_ref"):
                        _require_string(
                            governing_rule,
                            key,
                            report,
                            "CORRIDOR.json.guide_result.refusal.governing_rule",
                        )
                    rule_matches = [
                        rule
                        for rule in declared_rules
                        if rule.get("rule_id") == governing_rule.get("rule_id")
                        and rule.get("version") == governing_rule.get("rule_version")
                        and rule.get("ref") == governing_rule.get("rule_ref")
                    ]
                    if len(rule_matches) != 1:
                        report.error(
                            "GUIDE_REFUSAL_RULE",
                            "CORRIDOR.json.guide_result.refusal.governing_rule",
                            "must resolve exactly once to a declared Rule",
                        )
        else:
            report.error(
                "GUIDE_RESULT_KIND",
                "CORRIDOR.json.guide_result.kind",
                "must be entrance or typed-refusal",
            )
    if entrance is not None:
        expected_entrance = {
            "entrance_id",
            "task_ref",
            "direction",
            "consumable_instruction",
            "instruction_contract",
            "allowed_actions",
            "allowed_actions_sha256",
            "action_transition_rule",
        }
        if set(entrance) != expected_entrance:
            report.error(
                "ENTRANCE_FIELDS",
                "CORRIDOR.json.guide_result.entrance",
                f"must contain exactly {sorted(expected_entrance)}",
            )
        entrance_location = "CORRIDOR.json.guide_result.entrance"
        _require_string(entrance, "entrance_id", report, entrance_location)
        allowed_actions = _require_string_list(
            entrance, "allowed_actions", report, entrance_location
        )
        if not allowed_actions:
            report.error(
                "ENTRANCE_ACTIONS",
                f"{entrance_location}.allowed_actions",
                "must declare at least one legal action",
            )
        elif len(set(allowed_actions)) != len(allowed_actions):
            report.error(
                "ENTRANCE_ACTIONS",
                f"{entrance_location}.allowed_actions",
                "actions must be unique",
            )
        action_digest = entrance.get("allowed_actions_sha256")
        _check_digest(
            action_digest,
            report,
            f"{entrance_location}.allowed_actions_sha256",
        )
        if allowed_actions and action_digest != sha256_json_value(sorted(allowed_actions)):
            report.error(
                "ENTRANCE_ACTIONS_HASH",
                f"{entrance_location}.allowed_actions_sha256",
                "must match the canonical allowed-action set",
            )
        action_rule = _require_object(
            entrance,
            "action_transition_rule",
            report,
            entrance_location,
        )
        if action_rule is not None:
            expected_action_rule = {
                "rule_id",
                "rule_version",
                "rule_scope",
                "rule_ref",
            }
            if set(action_rule) != expected_action_rule:
                report.error(
                    "ENTRANCE_ACTION_RULE_FIELDS",
                    f"{entrance_location}.action_transition_rule",
                    f"must contain exactly {sorted(expected_action_rule)}",
                )
            for key in sorted(expected_action_rule):
                _require_string(
                    action_rule,
                    key,
                    report,
                    f"{entrance_location}.action_transition_rule",
                )
            action_rule_matches = [
                rule
                for rule in declared_rules
                if rule.get("rule_id") == action_rule.get("rule_id")
                and rule.get("version") == action_rule.get("rule_version")
                and rule.get("scope") == action_rule.get("rule_scope")
                and rule.get("ref") == action_rule.get("rule_ref")
                and rule.get("allowed_actions_sha256") == action_digest
            ]
            if len(action_rule_matches) != 1:
                report.error(
                    "ENTRANCE_ACTION_RULE",
                    f"{entrance_location}.action_transition_rule",
                    "must resolve exactly once to a declared action-transition Rule with the same action-set digest",
                )

        task_ref = _require_object(
            entrance, "task_ref", report, "CORRIDOR.json.entrance"
        )
        if task_ref is not None:
            expected_task = {"taskset_id", "task_id", "manifest_sha256"}
            if set(task_ref) != expected_task:
                report.error(
                    "TASK_REF_FIELDS",
                    "CORRIDOR.json.entrance.task_ref",
                    f"must contain exactly {sorted(expected_task)}",
                )
            for key in ("taskset_id", "task_id"):
                _require_string(
                    task_ref, key, report, "CORRIDOR.json.entrance.task_ref"
                )
            _check_digest(
                task_ref.get("manifest_sha256"),
                report,
                "CORRIDOR.json.entrance.task_ref.manifest_sha256",
            )

        direction = _require_object(
            entrance, "direction", report, "CORRIDOR.json.entrance"
        )
        if direction is not None:
            expected_direction = {
                "direction_id",
                "statement",
                "acceptance_sha256",
                "rule_id",
                "rule_version",
                "rule_ref",
            }
            if set(direction) != expected_direction:
                report.error(
                    "DIRECTION_FIELDS",
                    "CORRIDOR.json.entrance.direction",
                    f"must contain exactly {sorted(expected_direction)}",
                )
            for key in (
                "direction_id",
                "statement",
                "rule_id",
                "rule_version",
                "rule_ref",
            ):
                _require_string(
                    direction, key, report, "CORRIDOR.json.entrance.direction"
                )
            _check_digest(
                direction.get("acceptance_sha256"),
                report,
                "CORRIDOR.json.entrance.direction.acceptance_sha256",
            )
            direction_matches = [
                rule
                for rule in declared_rules
                if rule.get("rule_id") == direction.get("rule_id")
                and rule.get("version") == direction.get("rule_version")
                and rule.get("ref") == direction.get("rule_ref")
            ]
            if len(direction_matches) != 1:
                report.error(
                    "DIRECTION_RULE",
                    "CORRIDOR.json.entrance.direction",
                    "must resolve exactly once to a declared Rule",
                )

        instruction = _require_object(
            entrance, "consumable_instruction", report, "CORRIDOR.json.entrance"
        )
        if instruction is not None:
            expected_instruction = {
                "facade",
                "argument_mode",
                "opaque_key",
                "arguments_sha256",
                "lookup_scope_id",
                "lookup_scope_version",
                "lookup_scope_sha256",
                "max_matches",
            }
            if set(instruction) != expected_instruction:
                report.error(
                    "ENTRANCE_INSTRUCTION_FIELDS",
                    "CORRIDOR.json.entrance.consumable_instruction",
                    f"must contain exactly {sorted(expected_instruction)}",
                )
            instruction_location = "CORRIDOR.json.entrance.consumable_instruction"
            facade = _require_object(
                instruction,
                "facade",
                report,
                instruction_location,
            )
            if facade is not None:
                expected_facade = {
                    "facade_id",
                    "facade_version",
                    "facade_sha256",
                    "interface",
                }
                if set(facade) != expected_facade:
                    report.error(
                        "ENTRANCE_FACADE_FIELDS",
                        f"{instruction_location}.facade",
                        f"must contain exactly {sorted(expected_facade)}",
                    )
                for key in ("facade_id", "facade_version"):
                    _require_string(facade, key, report, f"{instruction_location}.facade")
                _check_digest(
                    facade.get("facade_sha256"),
                    report,
                    f"{instruction_location}.facade.facade_sha256",
                )
                interface = facade.get("interface")
                if not isinstance(interface, dict):
                    report.error(
                        "ENTRANCE_INTERFACE",
                        f"{instruction_location}.facade.interface",
                        "must be an exact pinned interface identity",
                    )
                else:
                    expected_interface = {
                        "interface_id",
                        "interface_version",
                        "interface_sha256",
                        "operation",
                    }
                    if set(interface) != expected_interface:
                        report.error(
                            "ENTRANCE_INTERFACE_FIELDS",
                            f"{instruction_location}.facade.interface",
                            f"must contain exactly {sorted(expected_interface)}",
                        )
                    for key in ("interface_id", "interface_version", "operation"):
                        _require_string(
                            interface,
                            key,
                            report,
                            f"{instruction_location}.facade.interface",
                        )
                    _check_digest(
                        interface.get("interface_sha256"),
                        report,
                        f"{instruction_location}.facade.interface.interface_sha256",
                    )
            if instruction.get("argument_mode") != "bounded-opaque-key":
                report.error(
                    "ENTRANCE_ARGUMENT_MODE",
                    "CORRIDOR.json.entrance.consumable_instruction.argument_mode",
                    "template must use bounded-opaque-key indirection",
                )
            _require_string(
                instruction,
                "opaque_key",
                report,
                "CORRIDOR.json.entrance.consumable_instruction",
            )
            for key in ("lookup_scope_id", "lookup_scope_version"):
                _require_string(
                    instruction,
                    key,
                    report,
                    instruction_location,
                )
            arguments_digest = instruction.get("arguments_sha256")
            _check_digest(
                arguments_digest,
                report,
                f"{instruction_location}.arguments_sha256",
            )
            expected_arguments_digest = sha256_json_value(
                {
                    "argument_mode": instruction.get("argument_mode"),
                    "opaque_key": instruction.get("opaque_key"),
                }
            )
            if arguments_digest != expected_arguments_digest:
                report.error(
                    "ENTRANCE_ARGUMENTS_HASH",
                    f"{instruction_location}.arguments_sha256",
                    "must bind the exact argument mode and opaque key",
                )
            _check_digest(
                instruction.get("lookup_scope_sha256"),
                report,
                "CORRIDOR.json.entrance.consumable_instruction.lookup_scope_sha256",
            )
            max_matches = instruction.get("max_matches")
            if (
                not isinstance(max_matches, int)
                or isinstance(max_matches, bool)
                or max_matches != 1
            ):
                report.error(
                    "ENTRANCE_LOOKUP_BOUND",
                    "CORRIDOR.json.entrance.consumable_instruction.max_matches",
                    "must be the deterministic bound 1",
                )
            forbidden_navigation = re.compile(
                r"(?i)(?:\bgrep\b|\bsearch\b|\brag\b|\bbrowse\b|\bnavigate\b|"
                r"\bscan\s+(?:the\s+)?repo(?:sitory)?\b|\bopen\s+(?:the\s+)?repo(?:sitory)?\b)"
            )
            instruction_surfaces = [
                instruction.get("opaque_key"),
                *allowed_actions,
            ]
            if isinstance(facade, dict):
                instruction_surfaces.extend(
                    value
                    for value in facade.values()
                    if isinstance(value, str)
                )
                interface = facade.get("interface")
                if isinstance(interface, dict):
                    instruction_surfaces.extend(
                        value
                        for value in interface.values()
                        if isinstance(value, str)
                    )
            if any(
                isinstance(value, str) and forbidden_navigation.search(value)
                for value in instruction_surfaces
            ):
                report.error(
                    "ENTRANCE_SEMANTIC_PULL",
                    f"{entrance_location}.consumable_instruction",
                    "agent-side grep/search/RAG or open-repository navigation is forbidden",
                )

        instruction_contract = _require_object(
            entrance, "instruction_contract", report, entrance_location
        )
        expected_contract = {
            "navigation_responsibility": "runtime",
            "lookup_scope": "closed",
            "selection_cardinality": 1,
            "agent_source_selection": False,
        }
        if instruction_contract is not None:
            exact_contract = bool(
                set(instruction_contract) == set(expected_contract)
                and instruction_contract.get("navigation_responsibility") == "runtime"
                and instruction_contract.get("lookup_scope") == "closed"
                and type(instruction_contract.get("selection_cardinality")) is int
                and instruction_contract.get("selection_cardinality") == 1
                and type(instruction_contract.get("agent_source_selection")) is bool
                and instruction_contract.get("agent_source_selection") is False
            )
            if not exact_contract:
                report.error(
                    "ENTRANCE_INSTRUCTION_CONTRACT",
                    f"{entrance_location}.instruction_contract",
                    "must assign closed, single-result source selection to the runtime with exact JSON types",
                )

    implementation = _require_object(
        candidate, "implementation", report, "CORRIDOR.json"
    )
    if implementation is not None:
        expected_implementation = {"path", "runner_owned_paths", "tree_sha256"}
        if set(implementation) != expected_implementation:
            report.error(
                "IMPLEMENTATION_FIELDS",
                "CORRIDOR.json.implementation",
                f"must contain exactly {sorted(expected_implementation)}",
            )
        implementation_path_value = implementation.get("path")
        if implementation_path_value != "implementation":
            report.error(
                "IMPLEMENTATION_PATH",
                "CORRIDOR.json.implementation.path",
                "draft v2 fixes the closed implementation tree at implementation",
            )
        runner_owned_paths = _require_string_list(
            implementation,
            "runner_owned_paths",
            report,
            "CORRIDOR.json.implementation",
        )
        if runner_owned_paths != ["implementation/GUIDE-CONTRACT.md"]:
            report.error(
                "IMPLEMENTATION_OWNERSHIP",
                "CORRIDOR.json.implementation.runner_owned_paths",
                "must identify only the runner-owned read-only Guide contract",
            )
        implementation_path = _safe_member(
            root,
            implementation_path_value,
            report,
            "CORRIDOR.json.implementation.path",
        )
        implementation_digest = implementation.get("tree_sha256")
        if candidate_state == "open" and implementation_digest is not None:
            report.error(
                "CANDIDATE_OPEN_TREE",
                "CORRIDOR.json.implementation.tree_sha256",
                "open Candidate must not claim a frozen implementation tree",
            )
        elif candidate_state == "frozen":
            _check_digest(
                implementation_digest,
                report,
                "CORRIDOR.json.implementation.tree_sha256",
            )
        if implementation_path is not None:
            if not implementation_path.is_dir():
                report.error(
                    "IMPLEMENTATION_PATH",
                    str(implementation_path),
                    "must be a directory",
                )
            elif isinstance(implementation_path_value, str):
                try:
                    actual_tree_digest, _ = hash_tree(root, (implementation_path_value,))
                except (OSError, ValueError) as exc:
                    report.error("IMPLEMENTATION_TREE", str(implementation_path), str(exc))
                else:
                    if (
                        candidate_state == "frozen"
                        and SHA256_RE.fullmatch(str(implementation_digest))
                        and implementation_digest != actual_tree_digest
                    ):
                        report.error(
                            "IMPLEMENTATION_TREE_HASH",
                            "CORRIDOR.json.implementation.tree_sha256",
                            "does not match the closed implementation tree",
                        )

    if (
        candidate_state == "frozen"
        and SHA256_RE.fullmatch(str(semantic_closure))
        and semantic_closure != candidate_semantic_closure_sha256(candidate)
    ):
        report.error(
            "CANDIDATE_SEMANTIC_CLOSURE",
            "CORRIDOR.json.semantic_closure_sha256",
            "does not match the frozen Candidate semantic projection",
        )

    authority_evidence = candidate.get("authority_evidence")
    if authority_evidence is not None:
        report.error(
            "AUTHORITY_EVIDENCE",
            "CORRIDOR.json.authority_evidence",
            "must remain null until a strict optional-evidence profile is implemented",
        )
    report.facts["authority_evidence_status"] = "not_assessed"

    assurances = _require_object(candidate, "assurances", report, "CORRIDOR.json")
    expected_assurances = {
        "traversal_receipt",
        "path_certificate",
        "evidential_warranty",
        "authority_warranty",
    }
    if assurances is not None:
        if set(assurances) != expected_assurances:
            report.error(
                "ASSURANCE_FIELDS",
                "CORRIDOR.json.assurances",
                f"must contain exactly {sorted(expected_assurances)}",
            )
        for key in sorted(expected_assurances):
            if assurances.get(key) is not None:
                report.error(
                    "ASSURANCE_TEMPLATE_CLAIM",
                    f"CORRIDOR.json.assurances.{key}",
                    "template must not claim a receipt, certificate, or assurance",
                )

    reentry = _require_object(candidate, "reentry", report, "CORRIDOR.json")
    expected_reentry = {"from_candidate_id", "reason"}
    if reentry is not None:
        if set(reentry) != expected_reentry:
            report.error(
                "REENTRY_FIELDS",
                "CORRIDOR.json.reentry",
                f"must contain exactly {sorted(expected_reentry)}",
            )
        if any(reentry.get(key) is not None for key in expected_reentry):
            report.error(
                "REENTRY_TEMPLATE",
                "CORRIDOR.json.reentry",
                "base template must not claim historical re-entry",
            )

    known_limits = _require_string_list(
        candidate, "known_limits", report, "CORRIDOR.json"
    )
    if not known_limits:
        report.error(
            "KNOWN_LIMITS",
            "CORRIDOR.json.known_limits",
            "must disclose at least one limit",
        )


def validate_corridor(
    root: Path,
    *,
    allow_template: bool = False,
    theory_versions: list[dict[str, Any]] | None = None,
    task_versions: list[dict[str, Any]] | None = None,
    method_versions: list[dict[str, Any]] | None = None,
) -> Report:
    root = root.resolve()
    report = Report(subject=str(root))
    manifest_path = root / "CORRIDOR.json"
    corridor = load_json(manifest_path, report, "corridor manifest")
    if corridor is None:
        return report
    if corridor.get("schema_version") == CANDIDATE_SCHEMA:
        _validate_candidate_v2(
            root,
            corridor,
            report,
            allow_template=allow_template,
            method_versions=method_versions,
        )
        return report
    if corridor.get("schema_version") != CORRIDOR_SCHEMA:
        report.error("SCHEMA_VERSION", str(manifest_path), f"expected {CORRIDOR_SCHEMA}")

    is_template = corridor.get("template") is True
    report.facts["template"] = is_template
    if is_template and not allow_template:
        report.error("TEMPLATE", str(manifest_path), "template artifacts cannot be indexed")

    corridor_id = _require_string(corridor, "corridor_id", report, "CORRIDOR.json")
    revision_id = _require_string(corridor, "revision_id", report, "CORRIDOR.json")
    _check_datetime(
        corridor.get("revision_frozen_at"),
        report,
        "CORRIDOR.json.revision_frozen_at",
    )
    status = _require_string(corridor, "status", report, "CORRIDOR.json")
    if status not in ALLOWED_CORRIDOR_STATUS:
        report.error("CORRIDOR_STATUS", "CORRIDOR.json.status", f"must be one of {sorted(ALLOWED_CORRIDOR_STATUS)}")
    report.facts.update({"corridor_id": corridor_id, "revision_id": revision_id, "status": status})

    evaluation_protocol_ref = _require_object(
        corridor, "evaluation_protocol_ref", report, "CORRIDOR.json"
    )
    if evaluation_protocol_ref is not None:
        evaluation_task_id = _require_string(
            evaluation_protocol_ref,
            "task_id",
            report,
            "CORRIDOR.json.evaluation_protocol_ref",
        )
        evaluation_protocol_digest = evaluation_protocol_ref.get("tree_sha256")
        _check_digest(
            evaluation_protocol_digest,
            report,
            "CORRIDOR.json.evaluation_protocol_ref.tree_sha256",
        )
        subject_prompt_digest = evaluation_protocol_ref.get(
            "subject_diagnosis_prompt_sha256"
        )
        _check_digest(
            subject_prompt_digest,
            report,
            "CORRIDOR.json.evaluation_protocol_ref.subject_diagnosis_prompt_sha256",
        )
        if task_versions is not None:
            matches = [
                task
                for task in task_versions
                if isinstance(task, dict)
                and task.get("task_id") == evaluation_task_id
                and isinstance(task.get("evaluation_protocol"), dict)
                and task["evaluation_protocol"].get("tree_sha256")
                == evaluation_protocol_digest
            ]
            if len(matches) != 1:
                report.error(
                    "EVALUATION_PROTOCOL_REF",
                    "CORRIDOR.json.evaluation_protocol_ref",
                    "must match exactly one cataloged task/evaluator tree",
                )
            elif (
                not isinstance(matches[0].get("subject_diagnosis_prompt"), dict)
                or matches[0]["subject_diagnosis_prompt"].get("sha256")
                != subject_prompt_digest
            ):
                report.error(
                    "EVALUATION_PROTOCOL_REF",
                    "CORRIDOR.json.evaluation_protocol_ref.subject_diagnosis_prompt_sha256",
                    "must match the cataloged task's frozen subject-diagnosis prompt",
                )

    analysis_theory = _require_object(
        corridor, "analysis_theory_ref", report, "CORRIDOR.json"
    )
    if analysis_theory is not None:
        _require_string(
            analysis_theory,
            "version_id",
            report,
            "CORRIDOR.json.analysis_theory_ref",
        )
        _require_string(
            analysis_theory,
            "artifact_id",
            report,
            "CORRIDOR.json.analysis_theory_ref",
        )
        commit = analysis_theory.get("source_commit")
        if not isinstance(commit, str) or not GIT_SHA1_RE.fullmatch(commit):
            report.error("GIT_COMMIT", "CORRIDOR.json.analysis_theory_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _require_string(
            analysis_theory,
            "representation",
            report,
            "CORRIDOR.json.analysis_theory_ref",
        )
        _check_digest(
            analysis_theory.get("content_sha256"),
            report,
            "CORRIDOR.json.analysis_theory_ref.content_sha256",
        )
        if theory_versions is not None:
            _validate_theory_reference(
                analysis_theory,
                theory_versions,
                report,
                "CORRIDOR.json.analysis_theory_ref",
            )

    theory = corridor.get("theory_ref")
    if theory is not None and not isinstance(theory, dict):
        report.error(
            "THEORY_REF", "CORRIDOR.json.theory_ref", "must be an object or null"
        )
    if isinstance(theory, dict):
        _require_string(theory, "version_id", report, "CORRIDOR.json.theory_ref")
        _require_string(theory, "artifact_id", report, "CORRIDOR.json.theory_ref")
        treatment_commit = theory.get("source_commit")
        if not isinstance(treatment_commit, str) or not GIT_SHA1_RE.fullmatch(
            treatment_commit
        ):
            report.error("GIT_COMMIT", "CORRIDOR.json.theory_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _require_string(theory, "representation", report, "CORRIDOR.json.theory_ref")
        _check_digest(theory.get("content_sha256"), report, "CORRIDOR.json.theory_ref.content_sha256")
        if theory_versions is not None:
            _validate_theory_reference(
                theory, theory_versions, report, "CORRIDOR.json.theory_ref"
            )

    methodology = corridor.get("methodology_ref")
    if methodology is not None and not isinstance(methodology, dict):
        report.error("METHODOLOGY_REF", "CORRIDOR.json.methodology_ref", "must be an object or null")
    if isinstance(methodology, dict):
        _require_string(methodology, "artifact_id", report, "CORRIDOR.json.methodology_ref")
        _require_string(methodology, "derived_from_theory_version_id", report, "CORRIDOR.json.methodology_ref")
        method_commit = methodology.get("source_commit")
        if not isinstance(method_commit, str) or not GIT_SHA1_RE.fullmatch(method_commit):
            report.error("GIT_COMMIT", "CORRIDOR.json.methodology_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _check_digest(methodology.get("content_sha256"), report, "CORRIDOR.json.methodology_ref.content_sha256")
        if (
            isinstance(analysis_theory, dict)
            and methodology.get("derived_from_theory_version_id")
            != analysis_theory.get("version_id")
        ):
            report.error(
                "METHODOLOGY_DERIVATION",
                "CORRIDOR.json.methodology_ref.derived_from_theory_version_id",
                "must match analysis_theory_ref.version_id",
            )

    framework = corridor.get("framework_ref")
    if framework is not None and not isinstance(framework, dict):
        report.error("FRAMEWORK_REF", "CORRIDOR.json.framework_ref", "must be an object or null")
    if isinstance(framework, dict):
        _require_string(framework, "artifact_id", report, "CORRIDOR.json.framework_ref")
        framework_commit = framework.get("source_commit")
        if not isinstance(framework_commit, str) or not GIT_SHA1_RE.fullmatch(framework_commit):
            report.error("GIT_COMMIT", "CORRIDOR.json.framework_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _check_digest(framework.get("content_sha256"), report, "CORRIDOR.json.framework_ref.content_sha256")

    builder = _require_object(corridor, "builder", report, "CORRIDOR.json")
    if builder is not None:
        _require_string(builder, "actor_id", report, "CORRIDOR.json.builder")
        _require_string(builder, "model", report, "CORRIDOR.json.builder")
        _require_string(builder, "runtime", report, "CORRIDOR.json.builder")
        _check_date(builder.get("run_date"), report, "CORRIDOR.json.builder.run_date")
        _check_enum(
            builder.get("web_access"),
            ALLOWED_WEB_ACCESS,
            report,
            "CORRIDOR.json.builder.web_access",
        )

    input_manifest = _validate_input_bundle(root, corridor, report, task_versions)
    if (
        input_manifest is not None
        and evaluation_protocol_ref is not None
        and input_manifest.get("task_id") != evaluation_protocol_ref.get("task_id")
    ):
        report.error(
            "TASK_BINDING",
            "CORRIDOR.json.evaluation_protocol_ref.task_id",
            "must match INPUTS.json.task_id",
        )

    authority = _require_object(corridor, "exogenous_authority", report, "CORRIDOR.json")
    authority_paths: dict[str, Path] = {}
    if authority is not None:
        _require_string(authority, "authority_boundary_id", report, "CORRIDOR.json.exogenous_authority")
        condition = _require_string(authority, "input_condition", report, "CORRIDOR.json.exogenous_authority")
        if condition not in ALLOWED_AUTHORITY_CONDITIONS:
            report.error("AUTHORITY_CONDITION", "CORRIDOR.json.exogenous_authority.input_condition", f"must be one of {sorted(ALLOWED_AUTHORITY_CONDITIONS)}")
        for key, path_key, digest_key in (
            ("manifest", "manifest_path", "manifest_sha256"),
            ("interactions", "interaction_log_path", "interaction_log_sha256"),
            ("events", "event_log_path", "event_log_sha256"),
        ):
            if authority.get(path_key) != CANONICAL_CORRIDOR_PATHS[path_key]:
                report.error(
                    "CANONICAL_PATH",
                    f"CORRIDOR.json.exogenous_authority.{path_key}",
                    f"must equal {CANONICAL_CORRIDOR_PATHS[path_key]!r}",
                )
            path = _safe_member(root, authority.get(path_key), report, f"CORRIDOR.json.exogenous_authority.{path_key}")
            _check_digest(authority.get(digest_key), report, f"CORRIDOR.json.exogenous_authority.{digest_key}")
            if path is not None:
                authority_paths[key] = path
                if not path.is_file():
                    report.error("REQUIRED_FILE", str(path), "file is missing")
                elif SHA256_RE.fullmatch(str(authority.get(digest_key))) and sha256_file(path) != authority.get(digest_key):
                    report.error("FILE_HASH", f"CORRIDOR.json.exogenous_authority.{digest_key}", f"does not match {path_key}")

    artifacts = _require_object(corridor, "artifacts", report, "CORRIDOR.json")
    artifact_paths: dict[str, Path] = {}
    if artifacts is not None:
        for key in ("corridor_path", "trace_path", "evaluation_path"):
            if artifacts.get(key) != CANONICAL_CORRIDOR_PATHS[key]:
                report.error(
                    "CANONICAL_PATH",
                    f"CORRIDOR.json.artifacts.{key}",
                    f"must equal {CANONICAL_CORRIDOR_PATHS[key]!r}",
                )
            path = _safe_member(root, artifacts.get(key), report, f"CORRIDOR.json.artifacts.{key}")
            if path is not None:
                artifact_paths[key] = path
                if not path.is_dir():
                    report.error("REQUIRED_DIRECTORY", str(path), "directory is missing")

    declared_payload_digest = corridor.get("payload_tree_sha256")
    _check_digest(
        declared_payload_digest, report, "CORRIDOR.json.payload_tree_sha256"
    )
    payload_members = ("inputs", "authority", "corridor", "trace", "evaluation")
    if all((root / member).is_dir() for member in payload_members):
        try:
            actual_payload_digest, payload_records = hash_tree(root, payload_members)
        except (OSError, ValueError) as exc:
            report.error("PAYLOAD_TREE", str(root), str(exc))
        else:
            if (
                SHA256_RE.fullmatch(str(declared_payload_digest))
                and actual_payload_digest != declared_payload_digest
            ):
                report.error(
                    "PAYLOAD_HASH",
                    "CORRIDOR.json.payload_tree_sha256",
                    "does not match canonical authority/corridor/trace/evaluation tree",
                )
            report.facts["payload_file_count"] = len(payload_records)

    declared_corridor_digest = corridor.get("corridor_tree_sha256")
    _check_digest(
        declared_corridor_digest, report, "CORRIDOR.json.corridor_tree_sha256"
    )
    if (root / "corridor").is_dir():
        try:
            actual_corridor_digest, corridor_records = hash_tree(root, ("corridor",))
        except (OSError, ValueError) as exc:
            report.error("CORRIDOR_TREE", str(root / "corridor"), str(exc))
        else:
            if (
                SHA256_RE.fullmatch(str(declared_corridor_digest))
                and actual_corridor_digest != declared_corridor_digest
            ):
                report.error(
                    "CORRIDOR_HASH",
                    "CORRIDOR.json.corridor_tree_sha256",
                    "does not match the canonical corridor implementation tree",
                )
            report.facts["corridor_file_count"] = len(corridor_records)

    actor_map: dict[str, dict[str, Any]] = {}
    event_map: dict[str, dict[str, Any]] = {}
    if set(authority_paths) == {"manifest", "interactions", "events"} and all(
        path.is_file() for path in authority_paths.values()
    ):
        actor_map, event_map = _validate_authority(
            root, corridor, authority_paths, report
        )

    result_path = artifact_paths.get("evaluation_path", root / "evaluation") / "RESULT.json"
    evaluation_result: dict[str, Any] | None = None
    first_trace_time: datetime | None = None
    execution_instance_ids: set[str] = set()
    evaluation_baseline_sha256: str | None = None
    if result_path.is_file():
        result = load_json(result_path, report, "evaluation result")
        if result is not None:
            evaluation_result = result
            if result.get("schema_version") != EVALUATION_SCHEMA:
                report.error("SCHEMA_VERSION", str(result_path), f"expected {EVALUATION_SCHEMA}")
            if result.get("corridor_id") != corridor_id or result.get("revision_id") != revision_id:
                report.error("EVALUATION_ID", str(result_path), "corridor/revision does not match manifest")
            evaluation_status = _check_enum(result.get("status"), ALLOWED_EVALUATION_STATUS, report, f"{result_path}.status")
            assessment_map: dict[str, dict[str, Any]] = {}
            assessment_log_value = result.get("assessment_log_path")
            if evaluation_status == "not-run":
                if assessment_log_value is not None or result.get("assessment_log_sha256") is not None:
                    report.error("ASSESSMENT_LOG", str(result_path), "assessment path and digest must be null when evaluation is not run")
                if (root / CANONICAL_CORRIDOR_PATHS["assessment_log_path"]).exists():
                    report.error(
                        "ASSESSMENT_LOG",
                        str(root / CANONICAL_CORRIDOR_PATHS["assessment_log_path"]),
                        "canonical assessment log must be absent when evaluation is not run",
                    )
            else:
                if assessment_log_value != CANONICAL_CORRIDOR_PATHS["assessment_log_path"]:
                    report.error("CANONICAL_PATH", f"{result_path}.assessment_log_path", f"must equal {CANONICAL_CORRIDOR_PATHS['assessment_log_path']!r}")
                assessment_digest = result.get("assessment_log_sha256")
                _check_digest(assessment_digest, report, f"{result_path}.assessment_log_sha256")
                assessment_path = _safe_member(root, assessment_log_value, report, f"{result_path}.assessment_log_path")
                if assessment_path is not None:
                    if not assessment_path.is_file():
                        report.error("ASSESSMENT_LOG", str(assessment_path), "assessment log is missing")
                    else:
                        if SHA256_RE.fullmatch(str(assessment_digest)) and sha256_file(assessment_path) != assessment_digest:
                            report.error("ASSESSMENT_LOG_HASH", f"{result_path}.assessment_log_sha256", "does not match assessment log bytes")
                        assessment_map = _validate_assessments(
                            root,
                            assessment_path,
                            corridor,
                            report,
                            theory_versions,
                            task_versions,
                            actor_map,
                        )
            first = _require_object(result, "first_traversal", report, str(result_path))
            if first is not None:
                _check_enum(first.get("status"), {"passed", "failed", "not-attempted"}, report, f"{result_path}.first_traversal.status")
                if first.get("frozen_revision") != revision_id:
                    report.error("FIRST_TRAVERSAL_REVISION", f"{result_path}.first_traversal.frozen_revision", "does not match revision_id")
                if first.get("frozen_corridor_sha256") != corridor.get("corridor_tree_sha256"):
                    report.error("FIRST_TRAVERSAL_REVISION", f"{result_path}.first_traversal.frozen_corridor_sha256", "does not match corridor_tree_sha256")
                if not isinstance(first.get("fresh"), bool):
                    report.error("FIRST_TRAVERSAL_FRESH", f"{result_path}.first_traversal.fresh", "must be boolean")
                if not isinstance(first.get("bypass_used"), bool):
                    report.error("FIRST_TRAVERSAL_BYPASS", f"{result_path}.first_traversal.bypass_used", "must be boolean")
                first_attempt_count = first.get("attempt_count")
                if not isinstance(first_attempt_count, int) or isinstance(first_attempt_count, bool) or first_attempt_count < 0:
                    report.error("FIRST_TRAVERSAL_COUNT", f"{result_path}.first_traversal.attempt_count", "must be a non-negative integer")
                trace_ref = first.get("trace_ref")
                if first.get("status") == "not-attempted":
                    if trace_ref is not None:
                        report.error("FIRST_TRAVERSAL_TRACE", f"{result_path}.first_traversal.trace_ref", "must be null when not attempted")
                    if first.get("fresh") is not False or first.get("bypass_used") is not False or first_attempt_count != 0:
                        report.error("FIRST_TRAVERSAL_STATE", f"{result_path}.first_traversal", "not-attempted requires fresh=false, bypass=false, attempt_count=0")
                    if (root / "trace" / "FIRST-TRAVERSAL.json").exists():
                        report.error(
                            "FIRST_TRAVERSAL_STATE",
                            str(root / "trace" / "FIRST-TRAVERSAL.json"),
                            "canonical traversal evidence must be absent when not attempted",
                        )
                else:
                    if trace_ref != "trace/FIRST-TRAVERSAL.json":
                        report.error(
                            "FIRST_TRAVERSAL_TRACE",
                            f"{result_path}.first_traversal.trace_ref",
                            "must equal trace/FIRST-TRAVERSAL.json",
                        )
                    if (
                        not isinstance(first_attempt_count, int)
                        or isinstance(first_attempt_count, bool)
                        or first_attempt_count < 1
                        or (first_attempt_count != 1 and evaluation_status != "invalid")
                    ):
                        report.error("FIRST_TRAVERSAL_COUNT", f"{result_path}.first_traversal.attempt_count", "a non-invalid attempted traversal requires exactly one attempt")
                    trace_path = _safe_member(root, trace_ref, report, f"{result_path}.first_traversal.trace_ref")
                    if trace_path is not None and not trace_path.is_file():
                        report.error("FIRST_TRAVERSAL_TRACE", str(trace_path), "trace file is missing")
                    elif trace_path is not None:
                        trace_record = _validate_trace_record(
                            trace_path,
                            expected_schema=FIRST_TRAVERSAL_EVIDENCE_SCHEMA,
                            corridor=corridor,
                            report=report,
                            actor_map=actor_map,
                        )
                        expected_first_trace_keys = {
                            "schema_version",
                            "corridor_id",
                            "revision_id",
                            "corridor_tree_sha256",
                            "task_id",
                            "input_bundle_sha256",
                            "status",
                            "fresh",
                            "bypass_used",
                            "attempt_count",
                            "producer_actor_id",
                            "execution_instance_id",
                            "baseline_state_sha256",
                            "clean_copy_attestation",
                            "observed_at",
                            "observation",
                            "observation_sha256",
                        }
                        if trace_record is not None and set(trace_record) != expected_first_trace_keys:
                            report.error(
                                "FIRST_TRAVERSAL_TRACE_KEYS",
                                str(trace_path),
                                f"must contain exactly {sorted(expected_first_trace_keys)}",
                            )
                        if trace_record is not None and (
                            trace_record.get("status") != first.get("status")
                            or trace_record.get("fresh") != first.get("fresh")
                            or trace_record.get("bypass_used")
                            != first.get("bypass_used")
                            or trace_record.get("attempt_count")
                            != first.get("attempt_count")
                        ):
                            report.error(
                                "FIRST_TRAVERSAL_TRACE_BINDING",
                                str(trace_path),
                                "status/fresh/bypass/attempt_count must match RESULT.json",
                            )
                        if trace_record is not None:
                            execution_instance_id = _require_string(
                                trace_record,
                                "execution_instance_id",
                                report,
                                str(trace_path),
                            )
                            if execution_instance_id is not None:
                                execution_instance_ids.add(execution_instance_id)
                            _check_digest(
                                trace_record.get("baseline_state_sha256"),
                                report,
                                f"{trace_path}.baseline_state_sha256",
                            )
                            if isinstance(trace_record.get("baseline_state_sha256"), str):
                                evaluation_baseline_sha256 = trace_record.get(
                                    "baseline_state_sha256"
                                )
                            if trace_record.get("clean_copy_attestation") is not True:
                                report.error(
                                    "FIRST_TRAVERSAL_CLEAN_COPY",
                                    str(trace_path),
                                    "runner must attest that the traversal used a fresh clean instance",
                                )
                            try:
                                first_trace_time = datetime.fromisoformat(
                                    str(trace_record.get("observed_at")).replace(
                                        "Z", "+00:00"
                                    )
                                )
                                revision_frozen_at = datetime.fromisoformat(
                                    str(corridor.get("revision_frozen_at")).replace(
                                        "Z", "+00:00"
                                    )
                                )
                                if first_trace_time <= revision_frozen_at:
                                    report.error(
                                        "FIRST_TRAVERSAL_TIME",
                                        str(trace_path),
                                        "first traversal must occur after revision_frozen_at",
                                    )
                            except (TypeError, ValueError):
                                pass
            scenarios = result.get("scenarios")
            if not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIO_IDS):
                report.error("SCENARIOS", f"{result_path}.scenarios", f"must contain exactly {list(SCENARIO_IDS)}")
            else:
                referenced_assessment_ids: set[str] = set()
                for scenario_id, scenario in scenarios.items():
                    scenario_location = f"{result_path}.scenarios.{scenario_id}"
                    if not isinstance(scenario, dict):
                        report.error("SCENARIO", scenario_location, "must be an object")
                        continue
                    scenario_status = _check_enum(scenario.get("status"), ALLOWED_SCENARIO_STATUS, report, f"{scenario_location}.status")
                    subject_diagnosis_id = scenario.get("subject_diagnosis_id")
                    evaluator_assessment_id = scenario.get("evaluator_assessment_id")
                    evidence_refs = scenario.get("evidence_refs")
                    if not isinstance(evidence_refs, list):
                        report.error("SCENARIO_EVIDENCE", f"{scenario_location}.evidence_refs", "must be an array")
                    elif scenario_status != "not-run" and not evidence_refs:
                        report.error("SCENARIO_EVIDENCE", f"{scenario_location}.evidence_refs", "attempted scenario requires evidence")
                    elif isinstance(evidence_refs, list):
                        canonical_scenario_evidence = (
                            f"trace/scenarios/{scenario_id}.json"
                        )
                        if (
                            scenario_status != "not-run"
                            and evidence_refs != [canonical_scenario_evidence]
                        ):
                            report.error(
                                "SCENARIO_EVIDENCE_BOUNDARY",
                                f"{scenario_location}.evidence_refs",
                                "must contain only this scenario's canonical structured trace record",
                            )
                        for evidence_index, evidence_ref in enumerate(evidence_refs):
                            evidence_location = f"{scenario_location}.evidence_refs[{evidence_index}]"
                            if not isinstance(
                                evidence_ref, str
                            ) or not evidence_ref.startswith("trace/"):
                                report.error(
                                    "SCENARIO_EVIDENCE_BOUNDARY",
                                    evidence_location,
                                    "scenario evidence must be a frozen trace/ artifact",
                                )
                            evidence_path = _safe_member(root, evidence_ref, report, evidence_location)
                            if evidence_path is not None and not evidence_path.is_file():
                                report.error("SCENARIO_EVIDENCE", str(evidence_path), "evidence file is missing")
                        if scenario_status != "not-run":
                            canonical_path = _safe_member(
                                root,
                                canonical_scenario_evidence,
                                report,
                                f"{scenario_location}.evidence_refs",
                            )
                            if canonical_path is not None and canonical_path.is_file():
                                scenario_trace = _validate_trace_record(
                                    canonical_path,
                                    expected_schema=SCENARIO_EVIDENCE_SCHEMA,
                                    corridor=corridor,
                                    report=report,
                                    actor_map=actor_map,
                                )
                                expected_scenario_trace_keys = {
                                    "schema_version",
                                    "corridor_id",
                                    "revision_id",
                                    "corridor_tree_sha256",
                                    "task_id",
                                    "input_bundle_sha256",
                                    "scenario_id",
                                    "producer_actor_id",
                                    "execution_instance_id",
                                    "baseline_state_sha256",
                                    "clean_copy_attestation",
                                    "observed_at",
                                    "observation",
                                    "observation_sha256",
                                    "label_free_attestation",
                                }
                                if scenario_trace is not None and set(scenario_trace) != expected_scenario_trace_keys:
                                    report.error(
                                        "SCENARIO_TRACE_KEYS",
                                        str(canonical_path),
                                        f"must contain exactly {sorted(expected_scenario_trace_keys)}",
                                    )
                                if scenario_trace is not None and scenario_trace.get(
                                    "scenario_id"
                                ) != scenario_id:
                                    report.error(
                                        "SCENARIO_TRACE_BINDING",
                                        str(canonical_path),
                                        "scenario_id must match RESULT.json; raw subject-visible evidence must not contain an adjudicated status",
                                    )
                                if scenario_trace is not None and "status" in scenario_trace:
                                    report.error(
                                        "SCENARIO_TRACE_LABEL_LEAK",
                                        str(canonical_path),
                                        "subject-visible scenario evidence must not contain an adjudicated status",
                                    )
                                if scenario_trace is not None and scenario_trace.get(
                                    "label_free_attestation"
                                ) is not True:
                                    report.error(
                                        "SCENARIO_TRACE_LABEL_ATTESTATION",
                                        str(canonical_path),
                                        "runner must attest that the subject-visible observation contains no adjudicated label or answer key",
                                    )
                                if scenario_trace is not None:
                                    execution_instance_id = _require_string(
                                        scenario_trace,
                                        "execution_instance_id",
                                        report,
                                        str(canonical_path),
                                    )
                                    if execution_instance_id in execution_instance_ids:
                                        report.error(
                                            "SCENARIO_EXECUTION_INSTANCE",
                                            str(canonical_path),
                                            "first traversal and every scenario require distinct clean execution instances",
                                        )
                                    elif execution_instance_id is not None:
                                        execution_instance_ids.add(execution_instance_id)
                                    baseline_state_sha256 = scenario_trace.get(
                                        "baseline_state_sha256"
                                    )
                                    _check_digest(
                                        baseline_state_sha256,
                                        report,
                                        f"{canonical_path}.baseline_state_sha256",
                                    )
                                    if (
                                        evaluation_baseline_sha256 is not None
                                        and baseline_state_sha256
                                        != evaluation_baseline_sha256
                                    ):
                                        report.error(
                                            "SCENARIO_BASELINE",
                                            str(canonical_path),
                                            "all clean instances must begin from the first traversal's frozen baseline digest",
                                        )
                                    if scenario_trace.get("clean_copy_attestation") is not True:
                                        report.error(
                                            "SCENARIO_CLEAN_COPY",
                                            str(canonical_path),
                                            "runner must attest that the scenario used an independent clean instance",
                                        )
                                if scenario_trace is not None and first_trace_time is not None:
                                    try:
                                        scenario_trace_time = datetime.fromisoformat(
                                            str(scenario_trace.get("observed_at")).replace(
                                                "Z", "+00:00"
                                            )
                                        )
                                        if scenario_trace_time <= first_trace_time:
                                            report.error(
                                                "SCENARIO_TRACE_TIME",
                                                str(canonical_path),
                                                "scenario evidence must be observed after the first traversal",
                                            )
                                    except (TypeError, ValueError):
                                        pass
                    factors = scenario.get("failure_factors")
                    classification_status = _check_enum(scenario.get("classification_status"), ALLOWED_CLASSIFICATION_STATUS, report, f"{scenario_location}.classification_status")
                    if not isinstance(factors, list):
                        report.error("FAILURE_FACTORS", f"{scenario_location}.failure_factors", "must be an array")
                    else:
                        valid_factors = [factor for factor in factors if isinstance(factor, str)]
                        if len(valid_factors) != len(factors):
                            report.error("FAILURE_FACTORS", f"{scenario_location}.failure_factors", "entries must be strings")
                        unknown_factors = set(valid_factors) - ALLOWED_FAILURE_FACTORS
                        if unknown_factors:
                            report.error("FAILURE_FACTORS", f"{scenario_location}.failure_factors", f"unknown factors {sorted(unknown_factors)}")
                        if len(valid_factors) != len(set(valid_factors)):
                            report.error("FAILURE_FACTORS", f"{scenario_location}.failure_factors", "must not contain duplicates")
                        if scenario_status in {"failed", "blocked"}:
                            if classification_status == "classified" and not valid_factors:
                                report.error("FAILURE_FACTORS", f"{scenario_location}.failure_factors", "classified failure requires at least one P/D/E factor")
                            if classification_status == "not-classifiable" and valid_factors:
                                report.error("FAILURE_FACTORS", f"{scenario_location}.failure_factors", "not-classifiable failure must not claim P/D/E factors")
                            if classification_status == "not-assessed":
                                report.error("CLASSIFICATION_STATUS", f"{scenario_location}.classification_status", "failed or blocked scenario must be classified or explicitly not-classifiable")
                        elif valid_factors or classification_status != "not-assessed":
                            report.error("FAILURE_FACTORS", scenario_location, "passed or unrun scenario must be not-assessed with no failure factors")
                    if scenario_status == "not-run":
                        if evidence_refs != []:
                            report.error(
                                "SCENARIO_EVIDENCE",
                                f"{scenario_location}.evidence_refs",
                                "not-run scenario evidence_refs must be empty",
                            )
                        if subject_diagnosis_id is not None or evaluator_assessment_id is not None:
                            report.error("ASSESSMENT_REF", scenario_location, "unrun scenario assessment references must be null")
                        canonical_unrun_path = root / "trace" / "scenarios" / f"{scenario_id}.json"
                        if canonical_unrun_path.exists():
                            report.error(
                                "SCENARIO_STATE",
                                str(canonical_unrun_path),
                                "canonical scenario evidence must be absent when status is not-run",
                            )
                    elif scenario_status in {"passed", "failed", "blocked"}:
                        if isinstance(subject_diagnosis_id, str):
                            referenced_assessment_ids.add(subject_diagnosis_id)
                        if isinstance(evaluator_assessment_id, str):
                            referenced_assessment_ids.add(evaluator_assessment_id)
                        subject = assessment_map.get(subject_diagnosis_id) if isinstance(subject_diagnosis_id, str) else None
                        evaluator = assessment_map.get(evaluator_assessment_id) if isinstance(evaluator_assessment_id, str) else None
                        if subject is None or subject.get("role") != "subject-diagnosis" or subject.get("scenario_id") != scenario_id:
                            report.error("ASSESSMENT_REF", f"{scenario_location}.subject_diagnosis_id", "must reference this scenario's subject diagnosis")
                        if evaluator is None or evaluator.get("role") != "evaluator-assessment" or evaluator.get("scenario_id") != scenario_id:
                            report.error("ASSESSMENT_REF", f"{scenario_location}.evaluator_assessment_id", "must reference this scenario's independent evaluator assessment")
                        elif scenario_status == "passed":
                            if evaluator.get("verdict") != "no-drift":
                                report.error("ASSESSMENT_RESULT", scenario_location, "passed scenario requires evaluator no-drift verdict")
                        elif scenario_status == "failed":
                            if evaluator.get("verdict") != "drift":
                                report.error("ASSESSMENT_RESULT", scenario_location, "failed scenario requires evaluator drift verdict")
                            evaluator_factors = evaluator.get("failure_factors")
                            if (
                                evaluator.get("classification_status")
                                != classification_status
                                or not isinstance(evaluator_factors, list)
                                or set(
                                    value
                                    for value in evaluator_factors
                                    if isinstance(value, str)
                                )
                                != set(
                                    value for value in factors if isinstance(value, str)
                                )
                            ):
                                report.error("ASSESSMENT_RESULT", scenario_location, "scenario classification must match evaluator assessment")
                        elif scenario_status == "blocked":
                            if (
                                evaluator.get("verdict") != "abstain"
                                or evaluator.get("classification_status")
                                != "not-classifiable"
                                or evaluator.get("failure_factors") != []
                            ):
                                report.error(
                                    "ASSESSMENT_RESULT",
                                    scenario_location,
                                    "blocked scenario requires evaluator abstain/not-classifiable with no P/D/E claim",
                                )
                            if classification_status != "not-classifiable" or factors != []:
                                report.error(
                                    "ASSESSMENT_RESULT",
                                    scenario_location,
                                    "blocked scenario must remain not-classifiable with no P/D/E claim",
                                )
                if set(assessment_map) != referenced_assessment_ids:
                    report.error(
                        "ASSESSMENT_COVERAGE",
                        str(result_path),
                        "assessment log records must equal exactly the subject/evaluator IDs referenced by attempted scenarios",
                    )
                scenario_statuses = [
                    scenarios[scenario_id].get("status")
                    for scenario_id in SCENARIO_IDS
                    if isinstance(scenarios.get(scenario_id), dict)
                ]
                first_status = first.get("status") if isinstance(first, dict) else None
                if evaluation_status == "not-run" and (
                    first_status != "not-attempted"
                    or any(value != "not-run" for value in scenario_statuses)
                ):
                    report.error(
                        "EVALUATION_STATE",
                        str(result_path),
                        "not-run requires an unattempted first traversal and six not-run scenarios",
                    )
                if evaluation_status == "passed" and (
                    first_status != "passed"
                    or any(value != "passed" for value in scenario_statuses)
                ):
                    report.error(
                        "EVALUATION_STATE",
                        str(result_path),
                        "passed requires a passed first traversal and six passed scenarios",
                    )
                if evaluation_status in {"passed", "failed", "blocked"} and (
                    not isinstance(first, dict)
                    or first.get("fresh") is not True
                    or first.get("bypass_used") is not False
                    or first.get("attempt_count") != 1
                ):
                    report.error(
                        "EVALUATION_STATE",
                        str(result_path),
                        "a conclusive evaluation requires one fresh, zero-bypass first traversal",
                    )
                if evaluation_status == "failed" and (
                    first_status not in ("passed", "failed")
                    or any(value == "not-run" for value in scenario_statuses)
                    or not (
                        first_status == "failed"
                        or any(value == "failed" for value in scenario_statuses)
                    )
                ):
                    report.error(
                        "EVALUATION_STATE",
                        str(result_path),
                        "failed requires all scenarios attempted and a failed first traversal or scenario",
                    )
                if evaluation_status == "blocked" and (
                    first_status != "passed"
                    or any(value == "not-run" for value in scenario_statuses)
                    or any(value == "failed" for value in scenario_statuses)
                    or not any(value == "blocked" for value in scenario_statuses)
                ):
                    report.error(
                        "EVALUATION_STATE",
                        str(result_path),
                        "blocked requires a passed first traversal, no failed scenario, and at least one blocked scenario",
                    )
                if status != "candidate" and any(
                    scenarios[scenario_id].get("status") == "not-run"
                    for scenario_id in SCENARIO_IDS
                    if isinstance(scenarios.get(scenario_id), dict)
                ):
                    report.error("SCENARIOS_INCOMPLETE", f"{result_path}.scenarios", "non-candidate corridor must attempt all six scenarios")
    elif status != "candidate":
        report.error("EVALUATION_MISSING", str(result_path), "non-candidate corridor requires RESULT.json")

    certificate = corridor.get("certificate")
    if status == "candidate" and certificate is not None:
        report.warn("CANDIDATE_CERTIFICATE", "CORRIDOR.json.certificate", "candidate status ignores certificate claims")
    if status in {"provisionally-charted", "currently-charted", "expired"}:
        if report.facts.get("authority_capture") != "complete":
            report.error(
                "CERTIFICATE_CAPTURE",
                "AUTHORITY.json.capture.completeness",
                "charted and expired states require a complete authority capture",
            )
        if not isinstance(certificate, dict):
            report.error("CERTIFICATE_MISSING", "CORRIDOR.json.certificate", "charted or expired status requires a certificate")
        else:
            if certificate.get("corridor_revision") != revision_id:
                report.error("CERTIFICATE_REVISION", "CORRIDOR.json.certificate.corridor_revision", "does not match revision_id")
            if certificate.get("corridor_tree_sha256") != corridor.get("corridor_tree_sha256"):
                report.error("CERTIFICATE_REVISION", "CORRIDOR.json.certificate.corridor_tree_sha256", "does not match corridor_tree_sha256")
            if certificate.get("fresh") is not True:
                report.error("CERTIFICATE_FRESH", "CORRIDOR.json.certificate.fresh", "must be true")
            if certificate.get("bypass_used") is not False:
                report.error("CERTIFICATE_BYPASS", "CORRIDOR.json.certificate.bypass_used", "must be false")
            warranty_event = certificate.get("authority_warranty_event_id")
            event = event_map.get(warranty_event) if isinstance(warranty_event, str) else None
            if (
                event is None
                or event.get("act") != "ratify"
                or event.get("effect") != "approved"
                or event.get("target_kind") != "corridor-revision"
                or event.get("target_ref") != f"{corridor_id}:{revision_id}"
                or event.get("target_sha256") != corridor.get("corridor_tree_sha256")
            ):
                report.error("CERTIFICATE_AUTHORITY", "CORRIDOR.json.certificate.authority_warranty_event_id", "must reference an approved external ratification of this exact corridor revision and implementation-tree digest")
            else:
                later_revocations = [
                    candidate
                    for candidate in event_map.values()
                    if candidate.get("act") == "repeal"
                    and candidate.get("effect") == "revoked"
                    and candidate.get("target_kind") == "corridor-revision"
                    and candidate.get("target_ref") == event.get("target_ref")
                    and candidate.get("target_sha256") == event.get("target_sha256")
                    and isinstance(candidate.get("seq"), int)
                    and isinstance(event.get("seq"), int)
                    and candidate.get("seq") > event.get("seq")
                ]
                if status in {"provisionally-charted", "currently-charted"} and later_revocations:
                    report.error("CERTIFICATE_REPEALED", "CORRIDOR.json.certificate.authority_warranty_event_id", "authority warranty was later repealed")
                if status == "expired" and not later_revocations:
                    report.error(
                        "CERTIFICATE_NOT_EXPIRED",
                        "CORRIDOR.json.certificate.authority_warranty_event_id",
                        "pilot v1 can derive expired only from a later matching repeal",
                    )
                try:
                    ratified_at = datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00"))
                    issued_at = datetime.fromisoformat(str(certificate.get("issued_at")).replace("Z", "+00:00"))
                    authority_record_frozen_at = datetime.fromisoformat(
                        str(report.facts.get("authority_record_frozen_at")).replace(
                            "Z", "+00:00"
                        )
                    )
                    if ratified_at > issued_at:
                        report.error("CERTIFICATE_AUTHORITY_TIME", "CORRIDOR.json.certificate.issued_at", "certificate predates its ratification")
                    if issued_at > authority_record_frozen_at:
                        report.error(
                            "CERTIFICATE_CAPTURE_TIME",
                            "CORRIDOR.json.certificate.issued_at",
                            "certificate issuance must fall within the frozen complete authority record",
                        )
                    if first_trace_time is not None and issued_at <= first_trace_time:
                        report.error(
                            "CERTIFICATE_TRAVERSAL_TIME",
                            "CORRIDOR.json.certificate.issued_at",
                            "certificate must be issued after its first-traversal evidence",
                        )
                    if status == "expired":
                        revocation_times: list[datetime] = []
                        for revocation in later_revocations:
                            try:
                                revocation_times.append(
                                    datetime.fromisoformat(
                                        str(revocation.get("timestamp")).replace(
                                            "Z", "+00:00"
                                        )
                                    )
                                )
                            except (TypeError, ValueError):
                                continue
                        if not any(
                            revocation_time > issued_at
                            for revocation_time in revocation_times
                        ):
                            report.error(
                                "CERTIFICATE_EXPIRY_TIME",
                                "CORRIDOR.json.certificate.authority_warranty_event_id",
                                "expired requires a matching repeal strictly after certificate issuance",
                            )
                except (TypeError, ValueError):
                    pass
            traversal_ref = certificate.get("traversal_ref")
            if traversal_ref != "trace/FIRST-TRAVERSAL.json":
                report.error(
                    "TRAVERSAL_BOUNDARY",
                    "CORRIDOR.json.certificate.traversal_ref",
                    "must equal trace/FIRST-TRAVERSAL.json",
                )
            traversal = _safe_member(root, traversal_ref, report, "CORRIDOR.json.certificate.traversal_ref")
            if traversal is not None and not traversal.is_file():
                report.error("TRAVERSAL_MISSING", str(traversal), "certificate traversal is missing")
            if evaluation_result is None:
                report.error("CERTIFICATE_EVALUATION", "CORRIDOR.json.certificate", "requires a valid RESULT.json")
            else:
                first = evaluation_result.get("first_traversal")
                if not isinstance(first, dict):
                    report.error("CERTIFICATE_EVALUATION", "CORRIDOR.json.certificate", "RESULT.json first_traversal is missing")
                elif (
                    first.get("status") != "passed"
                    or first.get("fresh") is not True
                    or first.get("bypass_used") is not False
                    or first.get("trace_ref") != certificate.get("traversal_ref")
                    or first.get("frozen_corridor_sha256") != certificate.get("corridor_tree_sha256")
                    or first.get("attempt_count") != 1
                ):
                    report.error("CERTIFICATE_EVALUATION", "CORRIDOR.json.certificate", "must match a passed, fresh, zero-bypass first traversal of the same corridor digest and trace")
            for key in ("datum_ref", "executor_profile", "environment_epoch", "witness_input_ref"):
                _require_string(certificate, key, report, "CORRIDOR.json.certificate")
            _check_datetime(certificate.get("issued_at"), report, "CORRIDOR.json.certificate.issued_at")

    return report


def validate_registry_entry(
    path: Path,
    theory_versions: list[dict[str, Any]] | None = None,
    task_versions: list[dict[str, Any]] | None = None,
) -> tuple[Report, dict[str, Any] | None]:
    report = Report(subject=str(path))
    entry = load_json(path, report, "registry entry")
    if entry is None:
        return report, None
    if entry.get("schema_version") != REGISTRY_SCHEMA:
        report.error("SCHEMA_VERSION", str(path), f"expected {REGISTRY_SCHEMA}")
    for key in ("entry_id", "run_id"):
        _require_string(entry, key, report, path.name)
    _check_enum(entry.get("status"), ALLOWED_REGISTRY_STATUS, report, f"{path.name}.status")

    experiment = _require_object(entry, "experiment", report, path.name)
    knowledge_arm: str | None = None
    system_condition: str | None = None
    comparison_intent: str | None = None
    if experiment is not None:
        track = _require_string(experiment, "track", report, f"{path.name}.experiment")
        if track not in ALLOWED_TRACKS:
            report.error(
                "TRACK",
                f"{path.name}.experiment.track",
                f"must be one of {sorted(ALLOWED_TRACKS)}",
            )
        knowledge_arm = _require_string(
            experiment, "knowledge_arm", report, f"{path.name}.experiment"
        )
        if knowledge_arm not in ALLOWED_KNOWLEDGE_ARMS:
            report.error(
                "KNOWLEDGE_ARM",
                f"{path.name}.experiment.knowledge_arm",
                f"must be one of {sorted(ALLOWED_KNOWLEDGE_ARMS)}",
            )
        system_condition = _require_string(
            experiment, "system_condition", report, f"{path.name}.experiment"
        )
        if system_condition not in ALLOWED_SYSTEM_CONDITIONS:
            report.error(
                "SYSTEM_CONDITION",
                f"{path.name}.experiment.system_condition",
                f"must be one of {sorted(ALLOWED_SYSTEM_CONDITIONS)}",
            )
        comparison_intent = _require_string(
            experiment, "comparison_intent", report, f"{path.name}.experiment"
        )
        if comparison_intent not in ALLOWED_COMPARISON_INTENTS:
            report.error(
                "COMPARISON_INTENT",
                f"{path.name}.experiment.comparison_intent",
                f"must be one of {sorted(ALLOWED_COMPARISON_INTENTS)}",
            )
        if comparison_intent == "knowledge-effect":
            if knowledge_arm == "not-applicable":
                report.error("COMPARISON_INTENT", f"{path.name}.experiment.knowledge_arm", "knowledge-effect requires an assigned knowledge arm")
            if system_condition != "corridor":
                report.error("COMPARISON_INTENT", f"{path.name}.experiment.system_condition", "knowledge-effect compares corridor-build inputs and requires corridor")
        if comparison_intent == "system-effect" and knowledge_arm != "not-applicable":
            report.error("COMPARISON_INTENT", f"{path.name}.experiment.knowledge_arm", "system-effect requires not-applicable; the evaluated subject is already frozen")
        _require_string(experiment, "task_id", report, f"{path.name}.experiment")
        for key in (
            "task_sha256",
            "evaluation_protocol_sha256",
            "input_bundle_sha256",
            "common_inputs_sha256",
            "treatment_inputs_sha256",
        ):
            _check_digest(experiment.get(key), report, f"{path.name}.experiment.{key}")
        if track == "reference" and task_versions is not None:
            matches = [task for task in task_versions if task.get("task_id") == experiment.get("task_id")]
            if len(matches) != 1:
                report.error("TASK_CATALOG_REF", f"{path.name}.experiment.task_id", "must match exactly one reference task")
            else:
                task_record = matches[0]
                if experiment.get("task_sha256") != task_record.get("builder_brief", {}).get("sha256"):
                    report.error("TASK_CATALOG_REF", f"{path.name}.experiment.task_sha256", "does not match cataloged builder brief")
                if experiment.get("evaluation_protocol_sha256") != task_record.get("evaluation_protocol", {}).get("tree_sha256"):
                    report.error("TASK_CATALOG_REF", f"{path.name}.experiment.evaluation_protocol_sha256", "does not match cataloged evaluator protocol")

    subject = _require_object(entry, "subject", report, path.name)
    if subject is not None:
        _require_string(subject, "artifact_id", report, f"{path.name}.subject")
        _require_string(subject, "revision_id", report, f"{path.name}.subject")
        corridor_id = subject.get("corridor_id")
        if system_condition == "corridor":
            if not isinstance(corridor_id, str) or not corridor_id:
                report.error(
                    "CORRIDOR_ID",
                    f"{path.name}.subject.corridor_id",
                    "is required for a corridor condition",
                )
        elif corridor_id is not None:
            report.error(
                "CORRIDOR_ID",
                f"{path.name}.subject.corridor_id",
                "must be null for a non-corridor condition",
            )

    source = _require_object(entry, "source", report, path.name)
    if source is not None:
        repository = _require_string(source, "repository_url", report, f"{path.name}.source")
        repository_segments = (
            repository.removeprefix("https://github.com/").split("/")
            if isinstance(repository, str)
            else []
        )
        if repository and (
            not GITHUB_REPOSITORY_RE.fullmatch(repository)
            or repository != repository.lower()
            or len(repository_segments) != 2
            or any(segment in {".", ".."} for segment in repository_segments)
            or repository_segments[-1].endswith(".git")
        ):
            report.error(
                "REPOSITORY_URL",
                f"{path.name}.source.repository_url",
                "must be a lowercase canonical https://github.com/owner/repository URL without .git or a trailing slash",
            )
        for key in ("base_commit", "artifact_commit"):
            value = source.get(key)
            if not isinstance(value, str) or not GIT_SHA1_RE.fullmatch(value):
                report.error("GIT_COMMIT", f"{path.name}.source.{key}", "must be a full lowercase SHA-1 commit")
        _check_registry_relative_path(
            source.get("artifact_root"),
            report,
            f"{path.name}.source.artifact_root",
        )
        if "branch_hint" in source and not isinstance(source["branch_hint"], str):
            report.error("BRANCH_HINT", f"{path.name}.source.branch_hint", "must be a string")

    _check_digest(entry.get("artifact_tree_sha256"), report, f"{path.name}.artifact_tree_sha256")
    verification = _require_object(entry, "artifact_verification", report, path.name)
    verification_status: str | None = None
    if verification is not None:
        verification_status = _check_enum(verification.get("status"), ALLOWED_ARTIFACT_VERIFICATION, report, f"{path.name}.artifact_verification.status")
        if verification_status == "unresolved":
            report.warn("UNVERIFIED_ARTIFACT", f"{path.name}.artifact_verification.status", "remote artifact bytes and authority logs were not independently resolved")
    builder = _require_object(entry, "builder", report, path.name)
    if builder is not None:
        _require_string(builder, "model", report, f"{path.name}.builder")
        _require_string(builder, "runtime", report, f"{path.name}.builder")
        _check_date(builder.get("run_date"), report, f"{path.name}.builder.run_date")
        _check_enum(builder.get("web_access"), ALLOWED_WEB_ACCESS, report, f"{path.name}.builder.web_access")

    analysis_theory = _require_object(
        entry, "analysis_theory_ref", report, path.name
    )
    if analysis_theory is not None:
        _require_string(
            analysis_theory,
            "version_id",
            report,
            f"{path.name}.analysis_theory_ref",
        )
        _require_string(
            analysis_theory,
            "artifact_id",
            report,
            f"{path.name}.analysis_theory_ref",
        )
        _require_string(
            analysis_theory,
            "representation",
            report,
            f"{path.name}.analysis_theory_ref",
        )
        analysis_commit = analysis_theory.get("source_commit")
        if not isinstance(analysis_commit, str) or not GIT_SHA1_RE.fullmatch(
            analysis_commit
        ):
            report.error(
                "GIT_COMMIT",
                f"{path.name}.analysis_theory_ref.source_commit",
                "must be a full lowercase SHA-1 commit",
            )
        _check_digest(
            analysis_theory.get("content_sha256"),
            report,
            f"{path.name}.analysis_theory_ref.content_sha256",
        )
        if theory_versions is not None:
            _validate_theory_reference(
                analysis_theory,
                theory_versions,
                report,
                f"{path.name}.analysis_theory_ref",
            )

    theory = entry.get("theory_ref")
    if knowledge_arm == "theory-only" and not isinstance(theory, dict):
        report.error(
            "THEORY_REF",
            f"{path.name}.theory_ref",
            "is required for the theory-only arm",
        )
    if theory is not None and not isinstance(theory, dict):
        report.error("THEORY_REF", f"{path.name}.theory_ref", "must be an object or null")
    if isinstance(theory, dict):
        _require_string(theory, "version_id", report, f"{path.name}.theory_ref")
        _require_string(theory, "artifact_id", report, f"{path.name}.theory_ref")
        _require_string(theory, "representation", report, f"{path.name}.theory_ref")
        commit = theory.get("source_commit")
        if not isinstance(commit, str) or not GIT_SHA1_RE.fullmatch(commit):
            report.error("GIT_COMMIT", f"{path.name}.theory_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _check_digest(theory.get("content_sha256"), report, f"{path.name}.theory_ref.content_sha256")
        if theory_versions is not None:
            _validate_theory_reference(
                theory,
                theory_versions,
                report,
                f"{path.name}.theory_ref",
            )

    methodology = entry.get("methodology_ref")
    if knowledge_arm == "methodology" and not isinstance(methodology, dict):
        report.error(
            "METHODOLOGY_REF",
            f"{path.name}.methodology_ref",
            "is required for the methodology arm",
        )
    if methodology is not None and not isinstance(methodology, dict):
        report.error("METHODOLOGY_REF", f"{path.name}.methodology_ref", "must be an object or null")
    if isinstance(methodology, dict):
        _require_string(methodology, "artifact_id", report, f"{path.name}.methodology_ref")
        _require_string(methodology, "derived_from_theory_version_id", report, f"{path.name}.methodology_ref")
        method_commit = methodology.get("source_commit")
        if not isinstance(method_commit, str) or not GIT_SHA1_RE.fullmatch(method_commit):
            report.error("GIT_COMMIT", f"{path.name}.methodology_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _check_digest(methodology.get("content_sha256"), report, f"{path.name}.methodology_ref.content_sha256")
        if (
            isinstance(analysis_theory, dict)
            and methodology.get("derived_from_theory_version_id")
            != analysis_theory.get("version_id")
        ):
            report.error(
                "METHODOLOGY_DERIVATION",
                f"{path.name}.methodology_ref.derived_from_theory_version_id",
                "must match analysis_theory_ref.version_id",
            )

    framework = entry.get("framework_ref")
    if framework is not None and not isinstance(framework, dict):
        report.error("FRAMEWORK_REF", f"{path.name}.framework_ref", "must be an object or null")
    if isinstance(framework, dict):
        _require_string(framework, "artifact_id", report, f"{path.name}.framework_ref")
        framework_commit = framework.get("source_commit")
        if not isinstance(framework_commit, str) or not GIT_SHA1_RE.fullmatch(framework_commit):
            report.error("GIT_COMMIT", f"{path.name}.framework_ref.source_commit", "must be a full lowercase SHA-1 commit")
        _check_digest(framework.get("content_sha256"), report, f"{path.name}.framework_ref.content_sha256")

    reference_matrix_ok = {
        "methodology": theory is None and isinstance(methodology, dict) and framework is None,
        "theory-only": isinstance(theory, dict) and methodology is None and framework is None,
        "control-none": theory is None and methodology is None and framework is None,
        "control-other": theory is None and methodology is None and isinstance(framework, dict),
        "not-applicable": theory is None and methodology is None and framework is None,
    }
    if knowledge_arm in reference_matrix_ok and not reference_matrix_ok[knowledge_arm]:
        report.error("KNOWLEDGE_REF_MATRIX", path.name, "theory/methodology/framework refs do not match the assigned knowledge arm")

    authority = _require_object(entry, "authority_evidence", report, path.name)
    if authority is not None:
        condition = _check_enum(authority.get("input_condition"), ALLOWED_AUTHORITY_CONDITIONS, report, f"{path.name}.authority_evidence.input_condition")
        for key in (
            "design_sha256",
            "boundary_design_sha256",
            "assignment_sha256",
            "condition_protocol_sha256",
            "manifest_sha256",
            "interaction_log_sha256",
            "event_log_sha256",
        ):
            _check_digest(authority.get(key), report, f"{path.name}.authority_evidence.{key}")
        capture_status = _check_enum(authority.get("capture_status"), ALLOWED_CAPTURE_STATUS, report, f"{path.name}.authority_evidence.capture_status")
        observed = authority.get("observed_act_counts")
        if not isinstance(observed, dict):
            report.error(
                "AUTHORITY_COUNTS",
                f"{path.name}.authority_evidence.observed_act_counts",
                "must be an object",
            )
        else:
            if set(observed) != ALLOWED_AUTHORITY_ACTS:
                report.error(
                    "AUTHORITY_COUNTS",
                    f"{path.name}.authority_evidence.observed_act_counts",
                    f"must contain exactly {sorted(ALLOWED_AUTHORITY_ACTS)}",
                )
            for act, count in observed.items():
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    report.error(
                        "AUTHORITY_COUNT",
                        f"{path.name}.authority_evidence.observed_act_counts.{act}",
                        "must be a non-negative integer",
                    )
            if capture_status == "complete" and observed.get("provision") != 1:
                report.error("FOUNDING_PROVISION", f"{path.name}.authority_evidence.observed_act_counts.provision", "complete capture requires exactly one provision")
            if capture_status != "complete" and observed.get("provision", 0) > 1:
                report.error("FOUNDING_PROVISION", f"{path.name}.authority_evidence.observed_act_counts.provision", "partial/unavailable capture may report at most one provision")
            if condition == "bootstrap-only" and any(
                observed.get(act, 0) != 0 for act in ALLOWED_AUTHORITY_ACTS - {"provision"}
            ):
                report.error("AUTHORITY_CONDITION_VIOLATION", f"{path.name}.authority_evidence.observed_act_counts", "bootstrap-only permits no post-provision authority acts")
        for key in ("redacted_interaction_count", "redacted_authority_source_count"):
            count = authority.get(key)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                report.error("AUTHORITY_REDACTION_COUNT", f"{path.name}.authority_evidence.{key}", "must be a non-negative integer")
        publication_status = _check_enum(
            authority.get("publication_status"),
            ALLOWED_PUBLICATION_STATUS,
            report,
            f"{path.name}.authority_evidence.publication_status",
        )
        if publication_status == "public-complete" and (
            authority.get("redacted_interaction_count") != 0
            or authority.get("redacted_authority_source_count") != 0
        ):
            report.error(
                "AUTHORITY_PUBLICATION_STATUS",
                f"{path.name}.authority_evidence.publication_status",
                "public-complete requires zero redacted interactions and zero redacted authority sources",
            )

    evaluation = _require_object(entry, "evaluation_summary", report, path.name)
    if evaluation is not None:
        _check_digest(
            evaluation.get("result_sha256"),
            report,
            f"{path.name}.evaluation_summary.result_sha256",
        )
        assessment_log_digest = evaluation.get("assessment_log_sha256")
        has_declared_assessments = any(
            isinstance(evaluation.get(key), int)
            and not isinstance(evaluation.get(key), bool)
            and evaluation.get(key) > 0
            for key in ("subject_diagnosis_count", "evaluator_assessment_count")
        )
        if (
            evaluation.get("first_traversal") == "not-attempted"
            and not has_declared_assessments
        ):
            if assessment_log_digest is not None:
                report.error(
                    "ASSESSMENT_LOG",
                    f"{path.name}.evaluation_summary.assessment_log_sha256",
                    "must be null when no traversal or scenario was attempted",
                )
        else:
            _check_digest(
                assessment_log_digest,
                report,
                f"{path.name}.evaluation_summary.assessment_log_sha256",
            )
        diagnoses_digest = evaluation.get("diagnoses_sha256")
        _check_digest(
            diagnoses_digest,
            report,
            f"{path.name}.evaluation_summary.diagnoses_sha256",
        )
        _check_enum(evaluation.get("first_traversal"), {"passed", "failed", "not-attempted"}, report, f"{path.name}.evaluation_summary.first_traversal")
        if not isinstance(evaluation.get("first_traversal_fresh"), bool):
            report.error("FIRST_TRAVERSAL_FRESH", f"{path.name}.evaluation_summary.first_traversal_fresh", "must be boolean")
        if not isinstance(evaluation.get("first_traversal_bypass_used"), bool):
            report.error("FIRST_TRAVERSAL_BYPASS", f"{path.name}.evaluation_summary.first_traversal_bypass_used", "must be boolean")
        attempt_count = evaluation.get("first_traversal_attempt_count")
        if not isinstance(attempt_count, int) or isinstance(attempt_count, bool) or attempt_count < 0:
            report.error("FIRST_TRAVERSAL_COUNT", f"{path.name}.evaluation_summary.first_traversal_attempt_count", "must be a non-negative integer")
        if entry.get("status") == "evaluated" and (
            evaluation.get("first_traversal") == "not-attempted"
            or evaluation.get("first_traversal_fresh") is not True
            or evaluation.get("first_traversal_bypass_used") is not False
            or attempt_count != 1
        ):
            report.error("FIRST_TRAVERSAL_INVALID", f"{path.name}.evaluation_summary", "an evaluated run requires exactly one fresh, attempted, zero-bypass first traversal")
        diagnosis_counts: dict[str, int] = {}
        for key in (
            "subject_diagnosis_count",
            "evaluator_assessment_count",
            "diagnosis_verdict_agreement_count",
            "diagnosis_evaluable_count",
            "diagnosis_decisive_agreement_count",
            "diagnosis_factor_comparable_count",
            "diagnosis_factor_exact_agreement_count",
        ):
            count = evaluation.get(key)
            if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 6:
                report.error("DIAGNOSIS_COUNT", f"{path.name}.evaluation_summary.{key}", "must be an integer from 0 through 6")
            else:
                diagnosis_counts[key] = count
        if entry.get("status") == "evaluated" and (
            diagnosis_counts.get("subject_diagnosis_count") != 6
            or diagnosis_counts.get("evaluator_assessment_count") != 6
        ):
            report.error("DIAGNOSIS_INCOMPLETE", f"{path.name}.evaluation_summary", "evaluated run requires subject and independent evaluator assessments for all six scenarios")
        if diagnosis_counts.get(
            "diagnosis_factor_exact_agreement_count", 0
        ) > diagnosis_counts.get("diagnosis_factor_comparable_count", 0):
            report.error(
                "DIAGNOSIS_COUNT",
                f"{path.name}.evaluation_summary",
                "exact P/D/E agreement cannot exceed the number of comparable classified-drift pairs",
            )
        scenarios = evaluation.get("scenarios")
        if not isinstance(scenarios, dict):
            report.error(
                "SCENARIOS",
                f"{path.name}.evaluation_summary.scenarios",
                "must be an object",
            )
        else:
            if set(scenarios) != set(SCENARIO_IDS):
                report.error(
                    "SCENARIOS",
                    f"{path.name}.evaluation_summary.scenarios",
                    f"must contain exactly {list(SCENARIO_IDS)}",
                )
            for scenario_id, result in scenarios.items():
                _check_enum(result, ALLOWED_SCENARIO_STATUS, report, f"{path.name}.evaluation_summary.scenarios.{scenario_id}")
            if entry.get("status") == "evaluated" and any(
                scenarios.get(scenario_id) == "not-run" for scenario_id in SCENARIO_IDS
            ):
                report.error(
                    "SCENARIOS_INCOMPLETE",
                    f"{path.name}.evaluation_summary.scenarios",
                    "an evaluated run must attempt all six scenarios",
                )
            attempted_count = sum(
                isinstance(scenarios.get(scenario_id), str)
                and scenarios.get(scenario_id) in ("passed", "failed", "blocked")
                for scenario_id in SCENARIO_IDS
            )
            failed_count = sum(
                scenarios.get(scenario_id) == "failed"
                for scenario_id in SCENARIO_IDS
            )
            if diagnosis_counts.get("subject_diagnosis_count", 0) > attempted_count or diagnosis_counts.get(
                "evaluator_assessment_count", 0
            ) > attempted_count:
                report.error(
                    "DIAGNOSIS_COUNT",
                    f"{path.name}.evaluation_summary",
                    "assessment counts cannot exceed attempted scenario count",
                )
            if diagnosis_counts.get(
                "diagnosis_verdict_agreement_count", 0
            ) > min(
                diagnosis_counts.get("subject_diagnosis_count", 0),
                diagnosis_counts.get("evaluator_assessment_count", 0),
            ):
                report.error(
                    "DIAGNOSIS_COUNT",
                    f"{path.name}.evaluation_summary.diagnosis_verdict_agreement_count",
                    "verdict agreement cannot exceed complete assessment pairs",
                )
            if diagnosis_counts.get(
                "diagnosis_factor_comparable_count", 0
            ) > failed_count:
                report.error(
                    "DIAGNOSIS_COUNT",
                    f"{path.name}.evaluation_summary.diagnosis_factor_comparable_count",
                    "comparable classified-drift pairs cannot exceed failed scenarios",
                )
            diagnoses = evaluation.get("diagnoses")
            if not isinstance(diagnoses, dict) or set(diagnoses) != set(SCENARIO_IDS):
                report.error(
                    "DIAGNOSES",
                    f"{path.name}.evaluation_summary.diagnoses",
                    f"must contain exactly {list(SCENARIO_IDS)}",
                )
            else:
                if (
                    SHA256_RE.fullmatch(str(diagnoses_digest))
                    and sha256_json_value(diagnoses) != diagnoses_digest
                ):
                    report.error(
                        "DIAGNOSES_HASH",
                        f"{path.name}.evaluation_summary.diagnoses_sha256",
                        "does not match the canonical per-scenario diagnosis summary",
                    )
                computed_subject = 0
                computed_evaluator = 0
                computed_verdict_agreement = 0
                computed_evaluable = 0
                computed_decisive_agreement = 0
                computed_factor_comparable = 0
                computed_factor_exact = 0
                expected_subject_theory = (
                    theory.get("version_id")
                    if isinstance(theory, dict)
                    and knowledge_arm == "theory-only"
                    else None
                )
                expected_evaluator_theory = (
                    analysis_theory.get("version_id")
                    if isinstance(analysis_theory, dict)
                    else None
                )
                registry_builder_model = (
                    builder.get("model") if isinstance(builder, dict) else None
                )
                seen_diagnosis_assessment_ids: set[str] = set()
                for scenario_id in SCENARIO_IDS:
                    pair = diagnoses.get(scenario_id)
                    raw_scenario_status = scenarios.get(scenario_id)
                    scenario_status = (
                        raw_scenario_status
                        if isinstance(raw_scenario_status, str)
                        else None
                    )
                    diagnosis_location = (
                        f"{path.name}.evaluation_summary.diagnoses.{scenario_id}"
                    )
                    if scenario_status == "not-run":
                        if pair is not None:
                            report.error(
                                "DIAGNOSES",
                                diagnosis_location,
                                "must be null for an unattempted scenario",
                            )
                        continue
                    if not isinstance(pair, dict):
                        report.error(
                            "DIAGNOSES",
                            diagnosis_location,
                            "attempted scenario requires subject and evaluator summaries",
                        )
                        continue
                    subject_diagnosis = _validate_registry_diagnosis(
                        pair.get("subject"),
                        report,
                        f"{diagnosis_location}.subject",
                    )
                    evaluator_diagnosis = _validate_registry_diagnosis(
                        pair.get("evaluator"),
                        report,
                        f"{diagnosis_location}.evaluator",
                    )
                    if subject_diagnosis is None or evaluator_diagnosis is None:
                        continue
                    computed_subject += 1
                    computed_evaluator += 1
                    subject_assessment_id = _require_string(
                        subject_diagnosis,
                        "assessment_id",
                        report,
                        f"{diagnosis_location}.subject",
                    )
                    evaluator_assessment_id = _require_string(
                        evaluator_diagnosis,
                        "assessment_id",
                        report,
                        f"{diagnosis_location}.evaluator",
                    )
                    for assessment_id, assessment_location in (
                        (subject_assessment_id, f"{diagnosis_location}.subject.assessment_id"),
                        (evaluator_assessment_id, f"{diagnosis_location}.evaluator.assessment_id"),
                    ):
                        if assessment_id is None:
                            continue
                        if assessment_id in seen_diagnosis_assessment_ids:
                            report.error(
                                "DUPLICATE_ASSESSMENT",
                                assessment_location,
                                f"assessment ID {assessment_id!r} is reused",
                            )
                        else:
                            seen_diagnosis_assessment_ids.add(assessment_id)
                    if subject_diagnosis.get("model") != registry_builder_model:
                        report.error(
                            "DIAGNOSIS_MODEL",
                            f"{diagnosis_location}.subject.model",
                            "must match builder.model",
                        )
                    if subject_diagnosis.get("actor_type") != "ai":
                        report.error(
                            "DIAGNOSIS_ACTOR",
                            f"{diagnosis_location}.subject.actor_type",
                            "subject diagnosis must identify an AI actor",
                        )
                    if evaluator_diagnosis.get("actor_type") != "human":
                        report.error(
                            "DIAGNOSIS_ACTOR",
                            f"{diagnosis_location}.evaluator.actor_type",
                            "evaluator assessment must identify a human actor",
                        )
                    if subject_diagnosis.get("theory_version_id") != expected_subject_theory:
                        report.error(
                            "DIAGNOSIS_THEORY",
                            f"{diagnosis_location}.subject.theory_version_id",
                            "must match the builder-visible knowledge treatment",
                        )
                    if evaluator_diagnosis.get("theory_version_id") != expected_evaluator_theory:
                        report.error(
                            "DIAGNOSIS_THEORY",
                            f"{diagnosis_location}.evaluator.theory_version_id",
                            "must match analysis_theory_ref",
                        )
                    if subject_diagnosis.get("actor_id") == evaluator_diagnosis.get("actor_id"):
                        report.error(
                            "DIAGNOSIS_INDEPENDENCE",
                            diagnosis_location,
                            "subject and evaluator actor IDs must differ",
                        )
                    evaluator_verdict = evaluator_diagnosis.get("verdict")
                    expected_verdict = {
                        "passed": "no-drift",
                        "failed": "drift",
                        "blocked": "abstain",
                    }.get(scenario_status)
                    if evaluator_verdict != expected_verdict:
                        report.error(
                            "DIAGNOSIS_RESULT",
                            f"{diagnosis_location}.evaluator.verdict",
                            "does not match the registered scenario outcome",
                        )
                    if subject_diagnosis.get("verdict") == evaluator_verdict:
                        computed_verdict_agreement += 1
                    if evaluator_verdict in ("drift", "no-drift"):
                        computed_evaluable += 1
                        if subject_diagnosis.get("verdict") == evaluator_verdict:
                            computed_decisive_agreement += 1
                    comparable = (
                        evaluator_verdict == "drift"
                        and evaluator_diagnosis.get("classification_status")
                        == "classified"
                    )
                    if comparable:
                        computed_factor_comparable += 1
                        subject_factor_values = subject_diagnosis.get("failure_factors")
                        evaluator_factor_values = evaluator_diagnosis.get("failure_factors")
                        subject_factor_set = {
                            value
                            for value in subject_factor_values
                            if isinstance(value, str)
                        } if isinstance(subject_factor_values, list) else set()
                        evaluator_factor_set = {
                            value
                            for value in evaluator_factor_values
                            if isinstance(value, str)
                        } if isinstance(evaluator_factor_values, list) else set()
                        if (
                            subject_diagnosis.get("verdict") == "drift"
                            and subject_diagnosis.get("classification_status")
                            == "classified"
                            and subject_factor_set == evaluator_factor_set
                        ):
                            computed_factor_exact += 1
                computed_counts = {
                    "subject_diagnosis_count": computed_subject,
                    "evaluator_assessment_count": computed_evaluator,
                    "diagnosis_verdict_agreement_count": computed_verdict_agreement,
                    "diagnosis_evaluable_count": computed_evaluable,
                    "diagnosis_decisive_agreement_count": computed_decisive_agreement,
                    "diagnosis_factor_comparable_count": computed_factor_comparable,
                    "diagnosis_factor_exact_agreement_count": computed_factor_exact,
                }
                for key, computed in computed_counts.items():
                    if diagnosis_counts.get(key) != computed:
                        report.error(
                            "DIAGNOSIS_COUNT_BINDING",
                            f"{path.name}.evaluation_summary.{key}",
                            f"must equal {computed} as derived from per-scenario diagnoses",
                        )
    return report, entry


def collect_registry(
    registry_root: Path,
    theory_versions: list[dict[str, Any]] | None = None,
    task_versions: list[dict[str, Any]] | None = None,
) -> tuple[Report, list[dict[str, Any]]]:
    report = Report(subject=str(registry_root.resolve()))
    run_dir = registry_root / "runs"
    if run_dir.is_symlink() or not run_dir.is_dir():
        report.error(
            "REGISTRY_RUNS_DIRECTORY",
            str(run_dir),
            "registry/runs must exist and be a directory",
        )
        return report, []
    entries: list[dict[str, Any]] = []
    seen_entry_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    seen_artifacts: dict[tuple[str, str, str], str] = {}
    for path in sorted(run_dir.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            report.error(
                "REGISTRY_RUN_FILE",
                str(path),
                "registry records must be regular non-symlink JSON files",
            )
            continue
        entry_report, entry = validate_registry_entry(path, theory_versions, task_versions)
        report.errors.extend(entry_report.errors)
        report.warnings.extend(entry_report.warnings)
        if entry is None or entry_report.errors:
            continue
        entry_id = entry.get("entry_id")
        run_id = entry.get("run_id")
        if isinstance(entry_id, str) and entry_id in seen_entry_ids:
            report.error("DUPLICATE_ENTRY", str(path), f"duplicate entry_id {entry_id!r}")
        if isinstance(run_id, str) and run_id in seen_run_ids:
            report.error("DUPLICATE_RUN", str(path), f"duplicate run_id {run_id!r}")
        source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
        provenance = (
            source.get("repository_url"),
            source.get("artifact_commit"),
            source.get("artifact_root"),
        )
        artifact_digest = entry.get("artifact_tree_sha256")
        if all(isinstance(value, str) for value in provenance) and isinstance(
            artifact_digest, str
        ):
            typed_provenance = tuple(provenance)
            previous_digest = seen_artifacts.get(typed_provenance)
            if previous_digest == artifact_digest:
                report.error(
                    "DUPLICATE_ARTIFACT",
                    str(path),
                    "same pinned artifact provenance is already registered",
                )
            elif previous_digest is not None:
                report.error(
                    "CONFLICTING_ARTIFACT",
                    str(path),
                    "same repository/commit/root claims a different artifact tree digest",
                )
            else:
                seen_artifacts[typed_provenance] = artifact_digest
        if isinstance(entry_id, str):
            seen_entry_ids.add(entry_id)
        if isinstance(run_id, str):
            seen_run_ids.add(run_id)
        entries.append(entry)
    report.facts["entry_count"] = len(entries)
    report.facts["comparison_group_count"] = len(
        {_comparison_key(entry) for entry in entries}
    )
    return report, entries


def build_index_documents(entries: Iterable[dict[str, Any]]) -> tuple[str, str]:
    ordered = sorted(entries, key=lambda item: str(item.get("entry_id", "")))
    summaries = []
    for entry in ordered:
        experiment = entry.get("experiment", {})
        subject = entry.get("subject", {})
        builder = entry.get("builder", {})
        analysis_theory = entry.get("analysis_theory_ref") or {}
        theory = entry.get("theory_ref") or {}
        methodology = entry.get("methodology_ref") or {}
        framework = entry.get("framework_ref") or {}
        verification = entry.get("artifact_verification", {})
        source = entry.get("source", {})
        authority = entry.get("authority_evidence", {})
        evaluation = entry.get("evaluation_summary", {})
        scenarios = evaluation.get("scenarios", {})
        summaries.append(
            {
                "entry_id": entry.get("entry_id"),
                "run_id": entry.get("run_id"),
                "status": entry.get("status"),
                "comparison_key": _comparison_key(entry),
                "comparison_intent": experiment.get("comparison_intent"),
                "track": experiment.get("track"),
                "knowledge_arm": experiment.get("knowledge_arm"),
                "system_condition": experiment.get("system_condition"),
                "task_id": experiment.get("task_id"),
                "task_sha256": experiment.get("task_sha256"),
                "evaluation_protocol_sha256": experiment.get("evaluation_protocol_sha256"),
                "artifact_id": subject.get("artifact_id"),
                "artifact_tree_sha256": entry.get("artifact_tree_sha256"),
                "revision_id": subject.get("revision_id"),
                "corridor_id": subject.get("corridor_id"),
                "model": builder.get("model"),
                "runtime": builder.get("runtime"),
                "run_date": builder.get("run_date"),
                "web_access": builder.get("web_access"),
                "input_bundle_sha256": experiment.get("input_bundle_sha256"),
                "common_inputs_sha256": experiment.get("common_inputs_sha256"),
                "treatment_inputs_sha256": experiment.get("treatment_inputs_sha256"),
                "analysis_theory_version_id": analysis_theory.get("version_id"),
                "analysis_theory_source_commit": analysis_theory.get("source_commit"),
                "analysis_theory_representation": analysis_theory.get("representation"),
                "analysis_theory_content_sha256": analysis_theory.get("content_sha256"),
                "theory_version_id": theory.get("version_id"),
                "theory_source_commit": theory.get("source_commit"),
                "theory_representation": theory.get("representation"),
                "theory_content_sha256": theory.get("content_sha256"),
                "methodology_source_commit": methodology.get("source_commit"),
                "methodology_content_sha256": methodology.get("content_sha256"),
                "framework_source_commit": framework.get("source_commit"),
                "framework_content_sha256": framework.get("content_sha256"),
                "authority_input_condition": authority.get("input_condition"),
                "authority_design_sha256": authority.get("design_sha256"),
                "authority_boundary_design_sha256": authority.get("boundary_design_sha256"),
                "authority_assignment_sha256": authority.get("assignment_sha256"),
                "authority_condition_protocol_sha256": authority.get("condition_protocol_sha256"),
                "authority_manifest_sha256": authority.get("manifest_sha256"),
                "authority_interaction_log_sha256": authority.get("interaction_log_sha256"),
                "authority_event_log_sha256": authority.get("event_log_sha256"),
                "authority_capture_status": authority.get("capture_status"),
                "authority_publication_status": authority.get("publication_status"),
                "redacted_interaction_count": authority.get("redacted_interaction_count"),
                "redacted_authority_source_count": authority.get("redacted_authority_source_count"),
                "observed_authority_acts": authority.get("observed_act_counts"),
                "first_traversal": evaluation.get("first_traversal"),
                "result_sha256": evaluation.get("result_sha256"),
                "assessment_log_sha256": evaluation.get("assessment_log_sha256"),
                "diagnoses_sha256": evaluation.get("diagnoses_sha256"),
                "first_traversal_fresh": evaluation.get("first_traversal_fresh"),
                "first_traversal_bypass_used": evaluation.get("first_traversal_bypass_used"),
                "first_traversal_attempt_count": evaluation.get("first_traversal_attempt_count"),
                "subject_diagnosis_count": evaluation.get("subject_diagnosis_count"),
                "evaluator_assessment_count": evaluation.get("evaluator_assessment_count"),
                "diagnosis_verdict_agreement_count": evaluation.get("diagnosis_verdict_agreement_count"),
                "diagnosis_evaluable_count": evaluation.get("diagnosis_evaluable_count"),
                "diagnosis_decisive_agreement_count": evaluation.get("diagnosis_decisive_agreement_count"),
                "diagnosis_factor_comparable_count": evaluation.get("diagnosis_factor_comparable_count"),
                "diagnosis_factor_exact_agreement_count": evaluation.get("diagnosis_factor_exact_agreement_count"),
                "diagnoses": evaluation.get("diagnoses"),
                "artifact_verification_status": verification.get("status"),
                "diagnosis_verification_status": verification.get("status"),
                "scenario_results": scenarios,
                "scenario_pass_count": sum(
                    result == "passed" for result in scenarios.values()
                ),
                "comparison_conditions_complete": (
                    entry.get("status") == "evaluated"
                    and verification.get("status") != "unresolved"
                    and experiment.get("comparison_intent") != "observational"
                    and authority.get("capture_status") == "complete"
                    and authority.get("input_condition") != "observational"
                    and authority.get("publication_status") == "public-complete"
                    and authority.get("redacted_interaction_count") == 0
                    and authority.get("redacted_authority_source_count") == 0
                    and evaluation.get("first_traversal") in {"passed", "failed"}
                    and evaluation.get("first_traversal_fresh") is True
                    and evaluation.get("first_traversal_bypass_used") is False
                    and evaluation.get("first_traversal_attempt_count") == 1
                    and evaluation.get("subject_diagnosis_count") == 6
                    and evaluation.get("evaluator_assessment_count") == 6
                    and set(scenarios) == set(SCENARIO_IDS)
                    and all(scenarios.get(key) != "not-run" for key in SCENARIO_IDS)
                ),
                "direct_comparison_eligible": False,
                "repository_url": source.get("repository_url"),
                "artifact_commit": source.get("artifact_commit"),
                "artifact_root": source.get("artifact_root"),
                "branch_hint": source.get("branch_hint"),
            }
        )
    json_text = json.dumps(
        {"schema_version": INDEX_SCHEMA, "entries": summaries},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"

    lines = [
        "# Experiment registry",
        "",
        "Generated by `tools/corridor_registry.py build-index`. Do not edit by hand.",
        "",
        "Reported matching groups share a `comparison` key. Remote artifacts are unresolved,",
        "so direct-comparison eligibility remains false; model/runtime/date still require stratification.",
        "",
        "| run | status | intent | comparison | track | knowledge | system | task | analysis theory | treatment theory | model | authority | first | S1–S6 | reported AI vs evaluator | reported P/D/E exact | verified | artifact |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in summaries:
        commit = str(item.get("artifact_commit") or "")
        repository = str(item.get("repository_url") or "").removesuffix(".git")
        root = str(item.get("artifact_root") or ".").strip("/")
        if repository and commit:
            target = f"{repository}/tree/{commit}"
            if root and root != ".":
                target += f"/{root}"
            artifact_cell = f"[{commit[:12]}]({target})"
        else:
            artifact_cell = ""
        values = [
            item.get("run_id"),
            item.get("status"),
            item.get("comparison_intent"),
            str(item.get("comparison_key") or "").removeprefix("sha256:")[:12],
            item.get("track"),
            item.get("knowledge_arm"),
            item.get("system_condition"),
            item.get("task_id"),
            item.get("analysis_theory_version_id") or "none",
            item.get("theory_version_id") or "none",
            f"{item.get('model') or ''} / {item.get('runtime') or ''}",
            f"{item.get('authority_input_condition') or ''} / {item.get('authority_capture_status') or ''}",
            item.get("first_traversal"),
            f"{item.get('scenario_pass_count', 0)}/6",
            (
                f"{item.get('diagnosis_decisive_agreement_count', 0)}/{item.get('diagnosis_evaluable_count', 0)}"
                if item.get("diagnosis_evaluable_count")
                else "N/A"
            ),
            (
                f"{item.get('diagnosis_factor_exact_agreement_count', 0)}/{item.get('diagnosis_factor_comparable_count', 0)}"
                if item.get("diagnosis_factor_comparable_count")
                else "N/A"
            ),
            item.get("artifact_verification_status"),
        ]
        safe = [_escape_markdown_cell(value) for value in values]
        lines.append("| " + " | ".join(safe + [artifact_cell]) + " |")
    if not summaries:
        lines.append("| _(none yet)_ | | | | | | | | | | | | | | | | | |")
    return json_text, "\n".join(lines) + "\n"


def _emit_report(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    status = "VALID" if report.ok else "INVALID"
    print(f"{status}: {report.subject}")
    for warning in report.warnings:
        print(f"WARNING {warning}")
    for error in report.errors:
        print(f"ERROR {error}")
    if report.facts:
        print("FACTS " + json.dumps(report.facts, ensure_ascii=False, sort_keys=True))


def command_validate_corridor(args: argparse.Namespace) -> int:
    theory_report, versions = validate_theory_index(Path(args.theory_index))
    task_report, tasks = validate_task_index(Path(args.task_index))
    method_report, methods = validate_method_index(
        Path(args.method_index),
        theory_versions=versions,
        theory_schema_version=theory_report.facts.get("schema_version"),
    )
    report = validate_corridor(
        Path(args.path),
        allow_template=args.allow_template,
        theory_versions=versions,
        task_versions=tasks,
        method_versions=methods,
    )
    report.errors[:0] = (
        theory_report.errors + task_report.errors + method_report.errors
    )
    report.warnings[:0] = (
        theory_report.warnings + task_report.warnings + method_report.warnings
    )
    _emit_report(report, args.json)
    return 0 if report.ok else 1


def command_validate_registry(args: argparse.Namespace) -> int:
    theory_report, versions = validate_theory_index(Path(args.theory_index))
    task_report, tasks = validate_task_index(Path(args.task_index))
    report, _ = collect_registry(Path(args.registry), versions, tasks)
    report.errors[:0] = theory_report.errors + task_report.errors
    report.warnings[:0] = theory_report.warnings + task_report.warnings
    _emit_report(report, args.json)
    return 0 if report.ok else 1


def command_validate_theory(args: argparse.Namespace) -> int:
    report, versions = validate_theory_index(Path(args.theory_index))
    if args.source_root is not None and report.ok:
        validate_theory_source_checkout(Path(args.source_root), versions, report)
    _emit_report(report, args.json)
    return 0 if report.ok else 1


def command_validate_task(args: argparse.Namespace) -> int:
    report, _ = validate_task_index(Path(args.task_index))
    _emit_report(report, args.json)
    return 0 if report.ok else 1


def command_validate_method(args: argparse.Namespace) -> int:
    theory_report, versions = validate_theory_index(Path(args.theory_index))
    report, _ = validate_method_index(
        Path(args.method_index),
        theory_versions=versions,
        theory_schema_version=theory_report.facts.get("schema_version"),
    )
    report.errors[:0] = theory_report.errors
    report.warnings[:0] = theory_report.warnings
    _emit_report(report, args.json)
    return 0 if report.ok else 1


def command_hash_tree(args: argparse.Namespace) -> int:
    if args.payload:
        members = ("inputs", "authority", "corridor", "trace", "evaluation")
    elif args.corridor:
        members = ("corridor",)
    else:
        members = None
    try:
        digest, records = hash_tree(Path(args.path), members)
    except (OSError, ValueError) as exc:
        print(f"INVALID: {args.path}\nERROR TREE_HASH {exc}")
        return 1
    if args.json:
        print(
            json.dumps(
                {"sha256": digest, "file_count": len(records), "files": records},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(digest)
    return 0


def prepare_builder_workspace(
    source_root: Path,
    destination: Path,
    *,
    theory_versions: list[dict[str, Any]] | None = None,
    task_versions: list[dict[str, Any]] | None = None,
) -> Report:
    source_root = source_root.resolve()
    destination = destination.resolve()
    report = Report(subject=str(destination))
    corridor = load_json(source_root / "CORRIDOR.json", report, "corridor manifest")
    if corridor is None:
        return report
    if corridor.get("schema_version") != CORRIDOR_SCHEMA:
        report.error(
            "SCHEMA_VERSION",
            str(source_root / "CORRIDOR.json"),
            f"expected {CORRIDOR_SCHEMA}",
        )
    _validate_input_bundle(source_root, corridor, report, task_versions)
    theory_ref = corridor.get("theory_ref")
    if isinstance(theory_ref, dict) and theory_versions is not None:
        _validate_theory_reference(
            theory_ref,
            theory_versions,
            report,
            "CORRIDOR.json.theory_ref",
        )
    if not report.ok:
        return report
    if destination.exists():
        report.error(
            "BUILDER_WORKSPACE_EXISTS",
            str(destination),
            "destination must not already exist; prepare-builder never overwrites",
        )
        return report
    try:
        destination.relative_to(source_root)
    except ValueError:
        pass
    else:
        report.error(
            "BUILDER_WORKSPACE_BOUNDARY",
            str(destination),
            "destination must be outside the runner-owned experiment envelope",
        )
        return report

    manifest = load_json(
        source_root / CANONICAL_CORRIDOR_PATHS["input_manifest_path"],
        report,
        "input-bundle manifest",
    )
    builder_view = manifest.get("builder_view") if isinstance(manifest, dict) else None
    roots = builder_view.get("roots") if isinstance(builder_view, dict) else None
    if not isinstance(roots, list) or not roots:
        report.error("BUILDER_VIEW", "INPUTS.json.builder_view.roots", "must be a non-empty array")
        return report
    safe_roots: list[str] = []
    for index, root_value in enumerate(roots):
        source_member = _safe_member(
            source_root,
            root_value,
            report,
            f"INPUTS.json.builder_view.roots[{index}]",
        )
        if source_member is not None and source_member.exists() and isinstance(root_value, str):
            safe_roots.append(root_value)
    if not report.ok:
        return report

    try:
        destination.mkdir(parents=True, exist_ok=False)
        for root_value in safe_roots:
            source_member = source_root / root_value
            destination_member = destination / root_value
            if source_member.is_dir():
                shutil.copytree(source_member, destination_member)
            else:
                destination_member.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_member, destination_member)
        (destination / "corridor").mkdir()
        copied_digest, copied_records = hash_tree(destination, safe_roots)
    except (OSError, ValueError) as exc:
        report.error("BUILDER_WORKSPACE", str(destination), str(exc))
        return report
    declared_digest = builder_view.get("tree_sha256")
    if copied_digest != declared_digest:
        report.error(
            "BUILDER_WORKSPACE_HASH",
            str(destination),
            "materialized builder view does not match INPUTS.json.builder_view.tree_sha256",
        )
    report.facts["builder_workspace"] = str(destination)
    report.facts["materialized_input_count"] = len(copied_records)
    report.facts["materialized_builder_view_sha256"] = copied_digest
    return report


def command_prepare_builder(args: argparse.Namespace) -> int:
    theory_report, versions = validate_theory_index(Path(args.theory_index))
    task_report, tasks = validate_task_index(Path(args.task_index))
    report = prepare_builder_workspace(
        Path(args.source),
        Path(args.destination),
        theory_versions=versions,
        task_versions=tasks,
    )
    report.errors[:0] = theory_report.errors + task_report.errors
    report.warnings[:0] = theory_report.warnings + task_report.warnings
    _emit_report(report, args.json)
    return 0 if report.ok else 1


def command_build_index(args: argparse.Namespace) -> int:
    registry_root = Path(args.registry)
    theory_report, versions = validate_theory_index(Path(args.theory_index))
    task_report, tasks = validate_task_index(Path(args.task_index))
    report, entries = collect_registry(registry_root, versions, tasks)
    report.errors[:0] = theory_report.errors + task_report.errors
    report.warnings[:0] = theory_report.warnings + task_report.warnings
    if not report.ok:
        _emit_report(report, args.json)
        return 1
    json_text, markdown_text = build_index_documents(entries)
    json_path = registry_root / "INDEX.json"
    markdown_path = registry_root / "EXPERIMENTS.md"
    if args.check:
        stale = []
        for path, expected in ((json_path, json_text), (markdown_path, markdown_text)):
            try:
                actual = path.read_text(encoding="utf-8")
            except OSError:
                stale.append(str(path))
                continue
            if actual != expected:
                stale.append(str(path))
        if stale:
            for path in stale:
                report.error("INDEX_STALE", path, "generated index is missing or stale")
            _emit_report(report, args.json)
            return 1
    else:
        json_path.write_text(json_text, encoding="utf-8")
        markdown_path.write_text(markdown_text, encoding="utf-8")
    _emit_report(report, args.json)
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_corridor_parser = subparsers.add_parser(
        "validate-corridor", help="validate one frozen corridor artifact"
    )
    validate_corridor_parser.add_argument("path")
    validate_corridor_parser.add_argument("--allow-template", action="store_true")
    validate_corridor_parser.add_argument("--theory-index", default="theory/VERSIONS.json")
    validate_corridor_parser.add_argument("--task-index", default="reference-task/VERSIONS.json")
    validate_corridor_parser.add_argument(
        "--method-index", default="method-paper/VERSIONS.json"
    )
    validate_corridor_parser.add_argument("--json", action="store_true")
    validate_corridor_parser.set_defaults(func=command_validate_corridor)

    validate_registry_parser = subparsers.add_parser(
        "validate-registry", help="validate all immutable registry records"
    )
    validate_registry_parser.add_argument("--registry", default="registry")
    validate_registry_parser.add_argument("--theory-index", default="theory/VERSIONS.json")
    validate_registry_parser.add_argument("--task-index", default="reference-task/VERSIONS.json")
    validate_registry_parser.add_argument("--json", action="store_true")
    validate_registry_parser.set_defaults(func=command_validate_registry)

    validate_theory_parser = subparsers.add_parser(
        "validate-theory", help="validate the catalog of pinned theory representations"
    )
    validate_theory_parser.add_argument("--theory-index", default="theory/VERSIONS.json")
    validate_theory_parser.add_argument(
        "--source-root",
        help="resolve every cataloged representation against an exact local Git checkout",
    )
    validate_theory_parser.add_argument("--json", action="store_true")
    validate_theory_parser.set_defaults(func=command_validate_theory)

    validate_task_parser = subparsers.add_parser(
        "validate-task", help="validate the cataloged reference task and evaluator bytes"
    )
    validate_task_parser.add_argument("--task-index", default="reference-task/VERSIONS.json")
    validate_task_parser.add_argument("--json", action="store_true")
    validate_task_parser.set_defaults(func=command_validate_task)

    validate_method_parser = subparsers.add_parser(
        "validate-method", help="validate the sole normative method-paper catalog"
    )
    validate_method_parser.add_argument(
        "--method-index", default="method-paper/VERSIONS.json"
    )
    validate_method_parser.add_argument(
        "--theory-index", default="theory/VERSIONS.json"
    )
    validate_method_parser.add_argument("--json", action="store_true")
    validate_method_parser.set_defaults(func=command_validate_method)

    hash_tree_parser = subparsers.add_parser(
        "hash-tree", help="hash an exact artifact tree using the canonical manifest algorithm"
    )
    hash_tree_parser.add_argument("path")
    hash_tree_mode = hash_tree_parser.add_mutually_exclusive_group()
    hash_tree_mode.add_argument(
        "--payload",
        action="store_true",
        help="hash only inputs/authority/corridor/trace/evaluation subtrees",
    )
    hash_tree_mode.add_argument(
        "--corridor",
        action="store_true",
        help="hash only the corridor implementation subtree",
    )
    hash_tree_parser.add_argument("--json", action="store_true")
    hash_tree_parser.set_defaults(func=command_hash_tree)

    prepare_builder_parser = subparsers.add_parser(
        "prepare-builder",
        help="materialize only the closed builder view into a new no-.git workspace",
    )
    prepare_builder_parser.add_argument("source", help="runner-owned corridor envelope")
    prepare_builder_parser.add_argument("destination", help="new builder workspace path")
    prepare_builder_parser.add_argument("--theory-index", default="theory/VERSIONS.json")
    prepare_builder_parser.add_argument("--task-index", default="reference-task/VERSIONS.json")
    prepare_builder_parser.add_argument("--json", action="store_true")
    prepare_builder_parser.set_defaults(func=command_prepare_builder)

    build_parser = subparsers.add_parser(
        "build-index", help="generate registry/INDEX.json and registry/EXPERIMENTS.md"
    )
    build_parser.add_argument("--registry", default="registry")
    build_parser.add_argument("--theory-index", default="theory/VERSIONS.json")
    build_parser.add_argument("--task-index", default="reference-task/VERSIONS.json")
    build_parser.add_argument("--check", action="store_true")
    build_parser.add_argument("--json", action="store_true")
    build_parser.set_defaults(func=command_build_index)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # defensive boundary for untrusted PR artifacts
        print(f"INVALID: validator internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
