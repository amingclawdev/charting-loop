#!/usr/bin/env python3
"""Validate neutral exogenous run records and build deterministic indexes."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

try:
    from tools import corridor_registry as corridor_method_registry
except ModuleNotFoundError:  # Direct execution from tools/.
    import corridor_registry as corridor_method_registry


LEGACY_RUN_SCHEMA = "charting-loop/exogenous-run/v1"
RUN_SCHEMA = "charting-loop/exogenous-run/v2"
SCORE_SCHEMA = "charting-loop/exogenous-score/v1"
TASKSET_SCHEMA = "charting-loop/exogenous-taskset/v1"
TASKSET_V2_SCHEMA = "charting-loop/exogenous-taskset/v2"
TASKSET_V3_SCHEMA = "charting-loop/exogenous-taskset/v3"
TASK_CONSTRAINT_SCHEMA = "charting-loop/task-constraint-datum/v1"
TASK_CONSTRAINT_V2_SCHEMA = "charting-loop/task-constraint-datum/v2"
LEGACY_STUDY_SCHEMA = "charting-loop/exogenous-study/v1"
STUDY_SCHEMA = "charting-loop/exogenous-study/v2"
STUDY_V3_SCHEMA = "charting-loop/exogenous-study/v3"
INDEX_SCHEMA = "charting-loop/exogenous-index/v1"
LEGACY_METHOD_INDEX_SCHEMA = "charting-loop/method-index/v1"
METHOD_INDEX_SCHEMA = "charting-loop/method-index/v2"
METHOD_CLAIMS_SCHEMA = "charting-loop/method-claims/v1"
METHOD_SOURCES_SCHEMA = "charting-loop/method-sources/v1"
METHOD_EVIDENCE_INDEX_SCHEMA = "charting-loop/method-evidence-index/v1"
MEASUREMENT_PLAN_SCHEMA = "charting-loop/measurement-plan/v1"
USAGE_RECEIPT_SCHEMA = "charting-loop/usage-receipt/v1"
PACKAGE_COST_SCHEMA = "charting-loop/package-cost/v1"
REQUIRED_USAGE_STAGES = (
    "construction",
    "guided_execution",
    "reentry_revalidation",
    "retry",
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_JSON_DEPTH = 100
MAX_HASH_BYTES = 50 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
LEGACY_RUN_KEYS = {
    "schema_version",
    "template",
    "run_id",
    "runner_id",
    "study_ref",
    "task_ref",
    "condition_id",
    "status",
    "trial",
    "seed",
    "runtime",
    "world_ref",
    "subject",
    "supersedes_run_id",
}
RUN_KEYS = LEGACY_RUN_KEYS | {"measurement_plan"}
STUDY_REF_KEYS = {"study_id", "path", "sha256"}
TASK_REF_KEYS = {"taskset_id", "taskset_sha256", "task_id", "task_sha256"}
RUNTIME_KEYS = {
    "executor_type",
    "provider",
    "model",
    "runtime",
    "profile_sha256",
    "tools_sha256",
    "network_access",
    "budget_sha256",
    "stopping_rule_sha256",
}
MEASUREMENT_PLAN_KEYS = {
    "schema_version",
    "usage_receipt_schema",
    "package_cost_schema",
    "required_usage_stages",
    "raw_evidence_profile",
    "independent_replay_required",
}
LEGACY_WORLD_REF_KEYS = {"base_commit", "environment_sha256", "evidence_prefix"}
WORLD_REF_KEYS = {
    "project_id",
    "run_id",
    "generation_id",
    "repository_url",
    "base_commit",
    "environment_sha256",
    "evidence_prefix",
    "derived_state_sha256",
}
LEGACY_PREFIX_KEYS = {"stream_id", "through_sequence", "prefix_sha256", "projector"}
PREFIX_KEYS = {"stream_id", "through_sequence", "prefix_sha256", "admission", "projector"}
LEGACY_PROJECTOR_KEYS = {"id", "version", "sha256"}
PROJECTOR_KEYS = {"schema_version", "algorithm_id", "algorithm_version", "algorithm_sha256"}
ADMISSION_KEYS = {"receipt_id", "admitted_root_sha256", "rule_revision", "rule_sha256"}
SUBJECT_KEYS = {
    "system_condition",
    "repository_url",
    "base_commit",
    "artifact_commit",
    "artifact_root",
    "artifact_tree_sha256",
    "branch_hint",
}
SCORE_KEYS = {
    "schema_version",
    "score_id",
    "evaluator_id",
    "run_ref",
    "task_ref",
    "evaluator",
    "environment_sha256",
    "world_ref_sha256",
    "subject_ref",
    "trial",
    "seed",
    "outcome_status",
    "raw_outcome",
    "infrastructure_status",
    "evaluated_at",
}
ALLOWED_RUN_STATUS = {"registered", "completed", "failed", "blocked", "invalid"}
ALLOWED_NETWORK = {"disabled", "enabled", "unknown"}
ALLOWED_SYSTEM = {"corridor", "task-only", "external-system"}
ALLOWED_OUTCOME = {"passed", "failed", "blocked", "invalid", "not-assessed"}
ALLOWED_INFRA = {"ok", "degraded", "error"}
ALLOWED_KNOWLEDGE = {"task-only", "method-paper"}
TASKSET_KEYS = {
    "schema_version",
    "taskset_id",
    "benchmark",
    "tasks",
    "task_list_sha256",
    "environment",
    "evaluator",
    "license",
}
BENCHMARK_KEYS = {"dataset_id", "release", "repository_url", "source_commit"}
LEGACY_TASK_KEYS = {"task_id", "input"}
TASK_KEYS = LEGACY_TASK_KEYS | {"constraint_datum"}
TASK_INPUT_KEYS = {"kind", "locator", "sha256"}
TASK_CONSTRAINT_REF_KEYS = {"path", "sha256"}
TASK_CONSTRAINT_KEYS = {
    "schema_version",
    "datum_id",
    "task_id",
    "source",
    "builder",
    "pair",
    "runtime",
    "egress",
    "audit",
    "excluded_inputs",
}
TASK_CONSTRAINT_V2_KEYS = TASK_CONSTRAINT_KEYS | {"qa", "position_ledger"}
TASK_CONSTRAINT_SOURCE_KEYS = {
    "repository_url",
    "release",
    "tag",
    "source_commit",
    "task_path",
    "instruction_path",
    "instruction_sha256",
    "task_metadata_path",
    "task_metadata_sha256",
    "public_environment_path",
    "public_environment_tree_git_sha1",
    "public_environment_manifest_sha256",
    "evaluator_path",
    "evaluator_tree_git_sha1",
    "evaluator_manifest_sha256",
    "license",
}
TASK_CONSTRAINT_BUILDER_KEYS = {
    "study_mode",
    "method_ref",
    "visible_inputs",
    "neutral_objective",
}
TASK_CONSTRAINT_PAIR_KEYS = {
    "comparison_unit",
    "shared",
    "treatment_only",
    "control_only",
    "treatment_consume_instruction",
    "service_attempt_policy",
    "score_order",
    "repair_policy",
}
TASK_CONSTRAINT_RUNTIME_KEYS = {
    "builder_timeout_seconds",
    "task_timeout_seconds",
    "verifier_timeout_seconds",
    "environment_build_timeout_seconds",
    "cpus",
    "memory_mb",
    "storage_mb",
    "retry_policy",
    "seed_policy",
}
TASK_CONSTRAINT_EGRESS_KEYS = {
    "task_public_internet",
    "shared_internal",
    "treatment_only_internal",
    "control_plane",
    "dependency_policy",
    "logging",
}
TASK_CONSTRAINT_AUDIT_KEYS = {
    "starts_after",
    "preserve",
    "scored_tree_policy",
    "evidence_branch_policy",
    "failed_run_policy",
    "publish_hidden_reasoning",
}
TASK_CONSTRAINT_QA_KEYS = {"construction", "matched_pair"}
TASK_CONSTRAINT_CONSTRUCTION_QA_KEYS = {
    "role",
    "timing",
    "permission",
    "feedback_visibility",
    "repair_rounds",
    "failure_policy",
}
TASK_CONSTRAINT_MATCHED_QA_KEYS = {
    "worker_session_policy",
    "qa_session_policy",
    "qa_instruction",
    "timing",
    "permission",
    "feedback_visibility",
    "budget_sha256",
    "repair_rounds",
    "outcomes",
    "failure_policy",
}
TASK_CONSTRAINT_QA_INSTRUCTION_KEYS = {"path", "sha256"}
TASK_CONSTRAINT_POSITION_LEDGER_KEYS = {
    "schema_version",
    "capture_policy",
    "worker_builder_visibility",
    "qa_visibility",
    "hash_chain",
    "starts_at",
    "ends_at",
    "failure_policy",
    "retention",
}
ENVIRONMENT_KEYS = {"environment_id", "image_sha256", "data_sha256"}
ENVIRONMENT_V2_KEYS = {
    "environment_id",
    "source_path",
    "source_tree_git_sha1",
    "source_manifest_sha256",
    "runtime_image_policy",
}
EVALUATOR_KEYS = {
    "scorer_id",
    "scorer_revision",
    "scorer_sha256",
    "verifier_id",
    "verifier_revision",
    "verifier_sha256",
}
LICENSE_KEYS = {"identifier", "redistribution"}
STUDY_KEYS = {
    "schema_version",
    "study_id",
    "title",
    "taskset_ref",
    "protocol_sha256",
    "comparison_intent",
    "conditions",
    "assignment",
}
STUDY_V3_KEYS = (STUDY_KEYS - {"protocol_sha256"}) | {"protocol_ref"}
STUDY_TASKSET_REF_KEYS = {"taskset_id", "path", "sha256"}
STUDY_PROTOCOL_REF_KEYS = {"path", "sha256"}
CONDITION_KEYS = {
    "condition_id",
    "system_condition",
    "knowledge_condition",
    "common_inputs_sha256",
    "treatment_inputs_sha256",
    "method_paper_ref",
}
LEGACY_METHOD_REF_KEYS = {
    "version_id",
    "source_commit",
    "representation_path",
    "content_sha256",
    "builder_eligible",
}
METHOD_REF_KEYS = LEGACY_METHOD_REF_KEYS | {"study_eligible", "adoption_eligible"}
ASSIGNMENT_KEYS = {"mode", "unit", "assignment_sha256"}
METHOD_INDEX_KEYS = {"schema_version", "normative_source", "versions"}
LEGACY_METHOD_VERSION_KEYS = {
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
METHOD_VERSION_KEYS = LEGACY_METHOD_VERSION_KEYS | {
    "study_eligible",
    "adoption_eligible",
}


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
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _inspect_json_tree(value: Any) -> str | None:
    """Iteratively reject excessive depth and unpaired surrogates."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            return "depth"
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                return "surrogate"
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            for key, item in current.items():
                stack.append((key, depth + 1))
                stack.append((item, depth + 1))
    return None


def load_json(path: Path, report: Report, label: str) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file():
            report.error("JSON_FILE", label, "must be a regular non-symlink file")
            return None
        if path.stat().st_size > MAX_JSON_BYTES:
            report.error("JSON_SIZE", label, "file exceeds the size limit")
            return None
        raw = path.read_bytes()
    except OSError as exc:
        report.error("JSON_READ", label, type(exc).__name__)
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        report.error("JSON_BOM", label, "UTF-8 BOM is forbidden")
        return None
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
        report.error("JSON_PARSE", label, type(exc).__name__)
        return None
    if not isinstance(value, dict):
        report.error("JSON_OBJECT", label, "root must be an object")
        return None
    tree_issue = _inspect_json_tree(value)
    if tree_issue == "depth":
        report.error("JSON_DEPTH", label, f"nesting exceeds {MAX_JSON_DEPTH}")
        return None
    if tree_issue == "surrogate":
        report.error("JSON_SURROGATE", label, "Unicode surrogate is forbidden")
        return None
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_sha256(
    path: Path,
    report: Report | None = None,
    location: str | None = None,
) -> str | None:
    """Hash a stable regular file through a bounded streaming read."""

    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise ValueError("must be a regular non-symlink file")
        if before.st_size > MAX_HASH_BYTES:
            raise ValueError(f"file exceeds {MAX_HASH_BYTES} byte hash limit")
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_HASH_BYTES:
                    raise ValueError(f"file exceeds {MAX_HASH_BYTES} byte hash limit")
                digest.update(chunk)
        after = path.lstat()
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_before != identity_after:
            raise ValueError("file changed while hashing")
        return "sha256:" + digest.hexdigest()
    except (OSError, ValueError) as exc:
        if report is None:
            raise
        report.error(
            "FILE_HASH_READ",
            location or str(path),
            str(exc),
        )
        return None


def _require_fields(
    value: Any,
    expected: set[str],
    report: Report,
    location: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        report.error("OBJECT", location, "must be an object")
        return None
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        report.error("FIELDS_MISSING", location, f"missing fields: {missing}")
    if unknown:
        report.error("FIELDS_UNKNOWN", location, f"unknown fields: {unknown}")
    return value


def _string(value: Any, report: Report, location: str) -> str | None:
    if not isinstance(value, str) or not value:
        report.error("STRING", location, "must be a non-empty string")
        return None
    return value


def _digest(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        report.error("SHA256", location, "must be a lowercase sha256 digest")
    elif value == "sha256:" + ("0" * 64):
        report.error("SHA256_SENTINEL", location, "all-zero digest is forbidden")


def _commit(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        report.error("COMMIT", location, "must be a full lowercase Git commit")


def _relative_path(value: Any, report: Report, location: str) -> str | None:
    text = _string(value, report, location)
    if text is None:
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text or not path.parts:
        report.error("PATH", location, "must be a safe relative POSIX path")
        return None
    return text


def _safe_member(
    root: Path,
    value: Any,
    report: Report,
    location: str,
) -> Path | None:
    text = _relative_path(value, report, location)
    if text is None:
        return None
    lexical_root = root.absolute()
    try:
        if lexical_root.is_symlink():
            report.error("PATH_SYMLINK", location, "root must not be a symlink")
            return None
        cursor = lexical_root
        for part in PurePosixPath(text).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                report.error(
                    "PATH_SYMLINK",
                    location,
                    f"symbolic-link path component is forbidden: {cursor}",
                )
                return None
        resolved_root = lexical_root.resolve()
        candidate = (lexical_root / text).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        report.error("PATH_ESCAPE", location, f"cannot resolve beneath root: {exc}")
        return None
    return candidate


def _https_url(value: Any, report: Report, location: str) -> None:
    text = _string(value, report, location)
    if text is None:
        return
    if (
        text != text.strip()
        or not text.startswith("https://")
        or "\\" in text
        or any(
            character.isspace()
            or ord(character) < 32
            or ord(character) == 127
            for character in text
        )
    ):
        report.error(
            "URL",
            location,
            "URL whitespace, controls, and backslashes are forbidden",
        )
        return
    try:
        parts = urlsplit(text)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        report.error("URL", location, "must be a valid HTTPS URL")
        return
    if (
        parts.scheme != "https"
        or not parts.netloc
        or not hostname
        or not _valid_url_hostname(hostname)
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        report.error(
            "URL",
            location,
            "must be HTTPS without credentials, query, or fragment",
        )


def _valid_url_hostname(hostname: str) -> bool:
    """Accept canonical ASCII DNS names or literal IP addresses only."""

    if not hostname or hostname.endswith(".") or not hostname.isascii():
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if len(hostname) > 253:
        return False
    labels = hostname.split(".")
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        is not None
        for label in labels
    )


def _git_object(value: Any, report: Report, location: str) -> None:
    if not isinstance(value, str) or not GIT_OBJECT_RE.fullmatch(value):
        report.error("GIT_OBJECT", location, "must be a full lowercase Git object id")


def _positive_integer(value: Any, report: Report, location: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        report.error("POSITIVE_INTEGER", location, "must be a positive integer")


def _exact_string_list(
    value: Any,
    expected: tuple[str, ...],
    report: Report,
    location: str,
) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        report.error("STRING_LIST", location, "must be an array of strings")
        return
    if value != list(expected):
        report.error("STRING_LIST_VALUE", location, f"must equal {list(expected)}")


def validate_task_constraint(
    path: Path,
    *,
    expected_task_id: str | None,
    expected_instruction_sha256: Any,
    expected_benchmark: dict[str, Any] | None = None,
    expected_environment: dict[str, Any] | None = None,
    expected_evaluator: dict[str, Any] | None = None,
) -> tuple[Report, dict[str, Any] | None]:
    """Validate the closed runner-facing study boundary for one task."""

    report = Report(subject=str(path.resolve()))
    datum = load_json(path, report, "TASK-CONSTRAINTS.json")
    if datum is None:
        return report, None
    constraint_schema = datum.get("schema_version")
    constraint_v2 = constraint_schema == TASK_CONSTRAINT_V2_SCHEMA
    _require_fields(
        datum,
        TASK_CONSTRAINT_V2_KEYS if constraint_v2 else TASK_CONSTRAINT_KEYS,
        report,
        "TASK-CONSTRAINTS.json",
    )
    if constraint_schema not in (TASK_CONSTRAINT_SCHEMA, TASK_CONSTRAINT_V2_SCHEMA):
        report.error(
            "TASK_CONSTRAINT_SCHEMA",
            "TASK-CONSTRAINTS.json.schema_version",
            f"expected {TASK_CONSTRAINT_SCHEMA} or {TASK_CONSTRAINT_V2_SCHEMA}",
        )
    _string(datum.get("datum_id"), report, "TASK-CONSTRAINTS.json.datum_id")
    task_id = _string(datum.get("task_id"), report, "TASK-CONSTRAINTS.json.task_id")
    if expected_task_id is not None and task_id != expected_task_id:
        report.error(
            "TASK_CONSTRAINT_TASK",
            "TASK-CONSTRAINTS.json.task_id",
            "must equal the containing TASKSET task_id",
        )

    source = _require_fields(
        datum.get("source"),
        TASK_CONSTRAINT_SOURCE_KEYS,
        report,
        "TASK-CONSTRAINTS.json.source",
    )
    if source is not None:
        _https_url(source.get("repository_url"), report, "TASK-CONSTRAINTS.json.source.repository_url")
        for key in ("release", "tag", "license"):
            _string(source.get(key), report, f"TASK-CONSTRAINTS.json.source.{key}")
        _commit(source.get("source_commit"), report, "TASK-CONSTRAINTS.json.source.source_commit")
        for key in (
            "task_path",
            "instruction_path",
            "task_metadata_path",
            "public_environment_path",
            "evaluator_path",
        ):
            _relative_path(source.get(key), report, f"TASK-CONSTRAINTS.json.source.{key}")
        for key in (
            "instruction_sha256",
            "task_metadata_sha256",
            "public_environment_manifest_sha256",
            "evaluator_manifest_sha256",
        ):
            _digest(source.get(key), report, f"TASK-CONSTRAINTS.json.source.{key}")
        for key in ("public_environment_tree_git_sha1", "evaluator_tree_git_sha1"):
            _git_object(source.get(key), report, f"TASK-CONSTRAINTS.json.source.{key}")
        if source.get("instruction_sha256") != expected_instruction_sha256:
            report.error(
                "TASK_CONSTRAINT_INPUT_HASH",
                "TASK-CONSTRAINTS.json.source.instruction_sha256",
                "must equal the TASKSET vendored input digest",
            )
        if expected_benchmark is not None:
            for source_key, benchmark_key in (
                ("repository_url", "repository_url"),
                ("release", "release"),
                ("source_commit", "source_commit"),
            ):
                if source.get(source_key) != expected_benchmark.get(benchmark_key):
                    report.error(
                        "TASK_CONSTRAINT_BENCHMARK_JOIN",
                        f"TASK-CONSTRAINTS.json.source.{source_key}",
                        f"must equal TASKSET benchmark.{benchmark_key}",
                    )
        if expected_environment is not None and (
            source.get("public_environment_path")
            != expected_environment.get("source_path")
            or source.get("public_environment_tree_git_sha1")
            != expected_environment.get("source_tree_git_sha1")
            or source.get("public_environment_manifest_sha256")
            != expected_environment.get("source_manifest_sha256")
        ):
            report.error(
                "TASK_CONSTRAINT_ENVIRONMENT_JOIN",
                "TASK-CONSTRAINTS.json.source.public_environment_path",
                "must equal the TASKSET frozen environment source identity",
            )
        if expected_evaluator is not None and (
            source.get("evaluator_manifest_sha256")
            != expected_evaluator.get("verifier_sha256")
            or source.get("source_commit")
            != expected_evaluator.get("verifier_revision")
        ):
            report.error(
                "TASK_CONSTRAINT_EVALUATOR_JOIN",
                "TASK-CONSTRAINTS.json.source.evaluator_manifest_sha256",
                "must equal the TASKSET evaluator source identity",
            )

    builder = _require_fields(
        datum.get("builder"),
        TASK_CONSTRAINT_BUILDER_KEYS,
        report,
        "TASK-CONSTRAINTS.json.builder",
    )
    if builder is not None:
        if builder.get("study_mode") != "task-conditioned-corridor":
            report.error(
                "TASK_CONSTRAINT_BUILDER_MODE",
                "TASK-CONSTRAINTS.json.builder.study_mode",
                "must be task-conditioned-corridor",
            )
        _string(builder.get("neutral_objective"), report, "TASK-CONSTRAINTS.json.builder.neutral_objective")
        _exact_string_list(
            builder.get("visible_inputs"),
            ("frozen-paper2", "official-task-instruction", "official-public-environment"),
            report,
            "TASK-CONSTRAINTS.json.builder.visible_inputs",
        )
        method_ref = _require_fields(
            builder.get("method_ref"), METHOD_REF_KEYS, report, "TASK-CONSTRAINTS.json.builder.method_ref"
        )
        if method_ref is not None:
            _string(method_ref.get("version_id"), report, "TASK-CONSTRAINTS.json.builder.method_ref.version_id")
            _commit(method_ref.get("source_commit"), report, "TASK-CONSTRAINTS.json.builder.method_ref.source_commit")
            _relative_path(
                method_ref.get("representation_path"),
                report,
                "TASK-CONSTRAINTS.json.builder.method_ref.representation_path",
            )
            _digest(method_ref.get("content_sha256"), report, "TASK-CONSTRAINTS.json.builder.method_ref.content_sha256")
            if (
                method_ref.get("study_eligible") is not True
                or method_ref.get("adoption_eligible") is not False
                or method_ref.get("builder_eligible") is not False
            ):
                report.error(
                    "TASK_CONSTRAINT_METHOD_STATUS",
                    "TASK-CONSTRAINTS.json.builder.method_ref",
                    "requires study_eligible=true and adoption/builder eligibility=false",
                )

    pair = _require_fields(
        datum.get("pair"), TASK_CONSTRAINT_PAIR_KEYS, report, "TASK-CONSTRAINTS.json.pair"
    )
    if pair is not None:
        pair_policy = (
            {
                "comparison_unit": "matched-independent-worker-qa-task-sessions",
                "service_attempt_policy": "required-attempt-observed-not-gating",
                "score_order": "official-evaluator-after-matched-qa-repair-before-experiment-audit",
                "repair_policy": "matched-one-qa-repair-before-official-score",
            }
            if constraint_v2
            else {
                "comparison_unit": "matched-independent-task-sessions",
                "service_attempt_policy": "required-attempt-observed-not-gating",
                "score_order": "official-evaluator-before-experiment-audit",
                "repair_policy": "no-repair-after-pair-freeze",
            }
        )
        for key, expected in pair_policy.items():
            if pair.get(key) != expected:
                report.error("TASK_CONSTRAINT_PAIR", f"TASK-CONSTRAINTS.json.pair.{key}", f"must be {expected}")
        _exact_string_list(
            pair.get("shared"),
            (
                (
                    "official-task-bytes",
                    "public-environment",
                    "model",
                    "tools",
                    "runtime-limits",
                    "retry-policy",
                    "evaluator",
                    "seed-assignment",
                    "worker-qa-topology",
                    "qa-instruction-bytes",
                    "qa-budget",
                    "repair-budget",
                    "position-ledger-capture",
                )
                if constraint_v2
                else (
                    "official-task-bytes",
                    "public-environment",
                    "model",
                    "tools",
                    "runtime-limits",
                    "retry-policy",
                    "evaluator",
                    "seed-assignment",
                )
            ),
            report,
            "TASK-CONSTRAINTS.json.pair.shared",
        )
        _exact_string_list(
            pair.get("treatment_only"),
            ("frozen-builder-branch-service", "minimal-consume-instruction"),
            report,
            "TASK-CONSTRAINTS.json.pair.treatment_only",
        )
        _exact_string_list(pair.get("control_only"), (), report, "TASK-CONSTRAINTS.json.pair.control_only")
        _string(
            pair.get("treatment_consume_instruction"),
            report,
            "TASK-CONSTRAINTS.json.pair.treatment_consume_instruction",
        )

    if constraint_v2:
        qa = _require_fields(
            datum.get("qa"),
            TASK_CONSTRAINT_QA_KEYS,
            report,
            "TASK-CONSTRAINTS.json.qa",
        )
        if qa is not None:
            construction = _require_fields(
                qa.get("construction"),
                TASK_CONSTRAINT_CONSTRUCTION_QA_KEYS,
                report,
                "TASK-CONSTRAINTS.json.qa.construction",
            )
            if construction is not None:
                for key, expected in {
                    "role": "fresh-independent-construction-qa",
                    "timing": "after-builder-before-service-freeze",
                    "permission": "read-only-assessment-no-edit",
                    "feedback_visibility": "visible-to-builder-only",
                    "failure_policy": "preserve-freeze-and-run-not-gating",
                }.items():
                    if construction.get(key) != expected:
                        report.error(
                            "TASK_CONSTRAINT_CONSTRUCTION_QA",
                            f"TASK-CONSTRAINTS.json.qa.construction.{key}",
                            f"must be {expected}",
                        )
                if (
                    type(construction.get("repair_rounds")) is not int
                    or construction.get("repair_rounds") != 1
                ):
                    report.error(
                        "TASK_CONSTRAINT_CONSTRUCTION_QA",
                        "TASK-CONSTRAINTS.json.qa.construction.repair_rounds",
                        "must be exactly 1",
                    )

            matched = _require_fields(
                qa.get("matched_pair"),
                TASK_CONSTRAINT_MATCHED_QA_KEYS,
                report,
                "TASK-CONSTRAINTS.json.qa.matched_pair",
            )
            if matched is not None:
                for key, expected in {
                    "worker_session_policy": "fresh-distinct-per-arm",
                    "qa_session_policy": "fresh-distinct-from-workers-and-other-qa",
                    "timing": "after-worker-before-official-evaluator",
                    "permission": "read-only-assessment-no-edit",
                    "feedback_visibility": "visible-to-own-worker-only",
                    "failure_policy": "preserve-repair-once-and-score-all-outcomes",
                }.items():
                    if matched.get(key) != expected:
                        report.error(
                            "TASK_CONSTRAINT_MATCHED_QA",
                            f"TASK-CONSTRAINTS.json.qa.matched_pair.{key}",
                            f"must be {expected}",
                        )
                _digest(
                    matched.get("budget_sha256"),
                    report,
                    "TASK-CONSTRAINTS.json.qa.matched_pair.budget_sha256",
                )
                if (
                    type(matched.get("repair_rounds")) is not int
                    or matched.get("repair_rounds") != 1
                ):
                    report.error(
                        "TASK_CONSTRAINT_MATCHED_QA",
                        "TASK-CONSTRAINTS.json.qa.matched_pair.repair_rounds",
                        "must be exactly 1",
                    )
                _exact_string_list(
                    matched.get("outcomes"),
                    ("pass", "fail", "blocked", "not_assessed"),
                    report,
                    "TASK-CONSTRAINTS.json.qa.matched_pair.outcomes",
                )
                qa_instruction = _require_fields(
                    matched.get("qa_instruction"),
                    TASK_CONSTRAINT_QA_INSTRUCTION_KEYS,
                    report,
                    "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction",
                )
                if qa_instruction is not None:
                    qa_instruction_path = _relative_path(
                        qa_instruction.get("path"),
                        report,
                        "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction.path",
                    )
                    _digest(
                        qa_instruction.get("sha256"),
                        report,
                        "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction.sha256",
                    )
                    resolved_qa_instruction = (
                        _safe_member(
                            path.parent,
                            qa_instruction_path,
                            report,
                            "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction.path",
                        )
                        if isinstance(qa_instruction_path, str)
                        else None
                    )
                    if resolved_qa_instruction is not None:
                        if not resolved_qa_instruction.is_file():
                            report.error(
                                "TASK_CONSTRAINT_QA_INSTRUCTION_FILE",
                                "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction.path",
                                "must resolve to a regular file",
                            )
                        elif file_sha256(
                            resolved_qa_instruction,
                            report,
                            "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction.path",
                        ) != qa_instruction.get("sha256"):
                            report.error(
                                "TASK_CONSTRAINT_QA_INSTRUCTION_HASH",
                                "TASK-CONSTRAINTS.json.qa.matched_pair.qa_instruction.sha256",
                                "does not match QA instruction bytes",
                            )

        position_ledger = _require_fields(
            datum.get("position_ledger"),
            TASK_CONSTRAINT_POSITION_LEDGER_KEYS,
            report,
            "TASK-CONSTRAINTS.json.position_ledger",
        )
        if position_ledger is not None:
            for key, expected in {
                "schema_version": "charting-loop/position-ledger-entry/v1",
                "capture_policy": "runner-held-identical-both-arms",
                "worker_builder_visibility": "hidden",
                "qa_visibility": "reviewed-prefix-readable",
                "hash_chain": "sha256-previous-entry",
                "starts_at": "worker-dispatch",
                "ends_at": "official-score-recorded",
                "failure_policy": "preserve-and-score",
                "retention": "result-branch-content-addressed",
            }.items():
                if position_ledger.get(key) != expected:
                    report.error(
                        "TASK_CONSTRAINT_POSITION_LEDGER",
                        f"TASK-CONSTRAINTS.json.position_ledger.{key}",
                        f"must be {expected}",
                    )

    runtime = _require_fields(
        datum.get("runtime"), TASK_CONSTRAINT_RUNTIME_KEYS, report, "TASK-CONSTRAINTS.json.runtime"
    )
    if runtime is not None:
        for key in (
            "builder_timeout_seconds",
            "task_timeout_seconds",
            "verifier_timeout_seconds",
            "environment_build_timeout_seconds",
            "cpus",
            "memory_mb",
            "storage_mb",
        ):
            _positive_integer(runtime.get(key), report, f"TASK-CONSTRAINTS.json.runtime.{key}")
        for key in ("retry_policy", "seed_policy"):
            if runtime.get(key) != "matched-frozen-in-run":
                report.error(
                    "TASK_CONSTRAINT_RUNTIME_POLICY",
                    f"TASK-CONSTRAINTS.json.runtime.{key}",
                    "must be matched-frozen-in-run",
                )

    egress = _require_fields(
        datum.get("egress"), TASK_CONSTRAINT_EGRESS_KEYS, report, "TASK-CONSTRAINTS.json.egress"
    )
    if egress is not None:
        for key, expected in {
            "task_public_internet": "disabled",
            "control_plane": "runner-proxy-exact-allowlist-frozen-in-run",
            "dependency_policy": "pre-fetched-only",
            "logging": "metadata-only-no-auth-or-payload",
        }.items():
            if egress.get(key) != expected:
                report.error("TASK_CONSTRAINT_EGRESS", f"TASK-CONSTRAINTS.json.egress.{key}", f"must be {expected}")
        _exact_string_list(
            egress.get("shared_internal"),
            ("benchmark-declared-services",),
            report,
            "TASK-CONSTRAINTS.json.egress.shared_internal",
        )
        _exact_string_list(
            egress.get("treatment_only_internal"),
            ("frozen-corridor-service",),
            report,
            "TASK-CONSTRAINTS.json.egress.treatment_only_internal",
        )

    audit = _require_fields(
        datum.get("audit"), TASK_CONSTRAINT_AUDIT_KEYS, report, "TASK-CONSTRAINTS.json.audit"
    )
    if audit is not None:
        for key, expected in {
            "starts_after": "official-score",
            "scored_tree_policy": "immutable",
            "evidence_branch_policy": "descendant-or-separate-result-branch",
            "failed_run_policy": "preserve",
            "publish_hidden_reasoning": False,
        }.items():
            if audit.get(key) != expected:
                report.error("TASK_CONSTRAINT_AUDIT", f"TASK-CONSTRAINTS.json.audit.{key}", f"must be {expected!r}")
        _exact_string_list(
            audit.get("preserve"),
            (
                "official-score",
                "observable-agent-runner-tool-service-logs",
                "exact-commits-and-trees",
                "pre-score-container-rootfs",
                "persistent-file-manifest",
                "database-files-dumps-transaction-logs-and-volume-identities",
            ),
            report,
            "TASK-CONSTRAINTS.json.audit.preserve",
        )

    _exact_string_list(
        datum.get("excluded_inputs"),
        (
            "solutions",
            "hidden-tests",
            "verifier-bodies",
            "prior-results",
            "governance-and-qualification-instructions",
            "task-specific-hints",
            "private-data",
        ),
        report,
        "TASK-CONSTRAINTS.json.excluded_inputs",
    )
    report.facts.update(
        {
            "schema_version": constraint_schema,
            "datum_id": datum.get("datum_id"),
            "task_id": task_id,
            "constraint_sha256": file_sha256(path, report, "TASK-CONSTRAINTS.json"),
        }
    )
    return report, datum


def validate_taskset(
    path: Path,
    exogenous_root: Path,
) -> tuple[Report, dict[str, Any] | None]:
    report = Report(subject=str(path.resolve()))
    taskset = load_json(path, report, "TASKSET.json")
    if taskset is None:
        return report, None
    _require_fields(taskset, TASKSET_KEYS, report, "TASKSET.json")
    taskset_schema = taskset.get("schema_version")
    if taskset_schema not in (TASKSET_SCHEMA, TASKSET_V2_SCHEMA, TASKSET_V3_SCHEMA):
        report.error(
            "TASKSET_SCHEMA",
            "TASKSET.json.schema_version",
            f"expected {TASKSET_SCHEMA}, {TASKSET_V2_SCHEMA}, or {TASKSET_V3_SCHEMA}",
        )
    taskset_with_constraints = taskset_schema in (
        TASKSET_V2_SCHEMA,
        TASKSET_V3_SCHEMA,
    )
    taskset_id = _string(
        taskset.get("taskset_id"), report, "TASKSET.json.taskset_id"
    )
    benchmark = _require_fields(
        taskset.get("benchmark"), BENCHMARK_KEYS, report, "TASKSET.json.benchmark"
    )
    if benchmark is not None:
        for key in ("dataset_id", "release"):
            _string(benchmark.get(key), report, f"TASKSET.json.benchmark.{key}")
        _https_url(
            benchmark.get("repository_url"),
            report,
            "TASKSET.json.benchmark.repository_url",
        )
        _commit(
            benchmark.get("source_commit"),
            report,
            "TASKSET.json.benchmark.source_commit",
        )
        expected_parts = (
            (
                "benchmarks",
                str(benchmark.get("dataset_id")),
                str(benchmark.get("release")),
                "tasksets",
                str(taskset_id),
                "TASKSET.json",
            )
            if taskset_schema == TASKSET_V3_SCHEMA
            else (
                "benchmarks",
                str(benchmark.get("dataset_id")),
                str(benchmark.get("release")),
                "TASKSET.json",
            )
        )
        try:
            actual_parts = path.resolve().relative_to(exogenous_root.resolve()).parts
        except ValueError:
            actual_parts = ()
        if actual_parts != expected_parts:
            report.error(
                "TASKSET_PATH",
                "TASKSET.json",
                "path must be benchmarks/<dataset_id>/<release>/TASKSET.json",
            )

    tasks = taskset.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        report.error("TASKS", "TASKSET.json.tasks", "must be a non-empty array")
        tasks = []
    seen: set[str] = set()
    digest_projection: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        location = f"TASKSET.json.tasks[{index}]"
        task_obj = _require_fields(
            task,
            TASK_KEYS if taskset_with_constraints else LEGACY_TASK_KEYS,
            report,
            location,
        )
        if task_obj is None:
            continue
        task_id = _string(task_obj.get("task_id"), report, f"{location}.task_id")
        if task_id in seen:
            report.error("DUPLICATE_TASK", location, "duplicate task_id")
        elif task_id:
            seen.add(task_id)
        input_obj = _require_fields(
            task_obj.get("input"), TASK_INPUT_KEYS, report, f"{location}.input"
        )
        if input_obj is None:
            continue
        kind = input_obj.get("kind")
        if not isinstance(kind, str) or kind not in {"vendored", "immutable-ref"}:
            report.error(
                "TASK_INPUT_KIND",
                f"{location}.input.kind",
                "must be vendored or immutable-ref",
            )
        locator = _string(
            input_obj.get("locator"), report, f"{location}.input.locator"
        )
        _digest(input_obj.get("sha256"), report, f"{location}.input.sha256")
        if kind == "vendored" and isinstance(locator, str):
            safe = _relative_path(locator, report, f"{location}.input.locator")
            if safe is not None:
                input_path = _safe_member(
                    path.parent,
                    safe,
                    report,
                    f"{location}.input.locator",
                )
                if input_path is None:
                    pass
                elif not input_path.is_file():
                    report.error(
                        "TASK_INPUT_FILE",
                        f"{location}.input.locator",
                        "vendored input must be a regular file",
                    )
                elif file_sha256(
                    input_path,
                    report,
                    f"{location}.input.locator",
                ) != input_obj.get("sha256"):
                    report.error(
                        "TASK_INPUT_HASH",
                        f"{location}.input.sha256",
                        "does not match vendored bytes",
                    )
        elif kind == "immutable-ref" and isinstance(locator, str):
            _https_url(locator, report, f"{location}.input.locator")
        digest_record = {
            "task_id": task_id,
            "input_sha256": input_obj.get("sha256"),
        }
        if taskset_with_constraints:
            constraint_ref = _require_fields(
                task_obj.get("constraint_datum"),
                TASK_CONSTRAINT_REF_KEYS,
                report,
                f"{location}.constraint_datum",
            )
            if constraint_ref is not None:
                constraint_path_value = _relative_path(
                    constraint_ref.get("path"),
                    report,
                    f"{location}.constraint_datum.path",
                )
                _digest(
                    constraint_ref.get("sha256"),
                    report,
                    f"{location}.constraint_datum.sha256",
                )
                expected_constraint_path = (
                    f"tasks/{task_id}/TASK-CONSTRAINTS.json" if task_id else None
                )
                if constraint_path_value != expected_constraint_path:
                    report.error(
                        "TASK_CONSTRAINT_PATH",
                        f"{location}.constraint_datum.path",
                        "must be tasks/<task_id>/TASK-CONSTRAINTS.json",
                    )
                constraint_path = (
                    _safe_member(
                        path.parent,
                        constraint_path_value,
                        report,
                        f"{location}.constraint_datum.path",
                    )
                    if isinstance(constraint_path_value, str)
                    else None
                )
                if constraint_path is not None:
                    if not constraint_path.is_file():
                        report.error(
                            "TASK_CONSTRAINT_FILE",
                            f"{location}.constraint_datum.path",
                            "must resolve to a regular file",
                        )
                    else:
                        actual_constraint_sha = file_sha256(
                            constraint_path,
                            report,
                            f"{location}.constraint_datum.path",
                        )
                        if actual_constraint_sha != constraint_ref.get("sha256"):
                            report.error(
                                "TASK_CONSTRAINT_HASH",
                                f"{location}.constraint_datum.sha256",
                                "does not match constraint datum bytes",
                            )
                        constraint_report, _ = validate_task_constraint(
                            constraint_path,
                            expected_task_id=task_id,
                            expected_instruction_sha256=input_obj.get("sha256"),
                            expected_benchmark=benchmark,
                            expected_environment=taskset.get("environment"),
                            expected_evaluator=taskset.get("evaluator"),
                        )
                        report.errors.extend(constraint_report.errors)
                        report.warnings.extend(constraint_report.warnings)
                digest_record["constraint_sha256"] = constraint_ref.get("sha256")
        digest_projection.append(digest_record)
    declared_task_list_digest = taskset.get("task_list_sha256")
    _digest(
        declared_task_list_digest, report, "TASKSET.json.task_list_sha256"
    )
    if declared_task_list_digest != canonical_sha256(digest_projection):
        report.error(
            "TASK_LIST_HASH",
            "TASKSET.json.task_list_sha256",
            "does not match ordered task ids and input digests",
        )

    environment = _require_fields(
        taskset.get("environment"),
        ENVIRONMENT_V2_KEYS if taskset_with_constraints else ENVIRONMENT_KEYS,
        report,
        "TASKSET.json.environment",
    )
    if environment is not None:
        _string(
            environment.get("environment_id"),
            report,
            "TASKSET.json.environment.environment_id",
        )
        if taskset_with_constraints:
            _relative_path(
                environment.get("source_path"),
                report,
                "TASKSET.json.environment.source_path",
            )
            _git_object(
                environment.get("source_tree_git_sha1"),
                report,
                "TASKSET.json.environment.source_tree_git_sha1",
            )
            _digest(
                environment.get("source_manifest_sha256"),
                report,
                "TASKSET.json.environment.source_manifest_sha256",
            )
            if environment.get("runtime_image_policy") != "build-from-frozen-source-and-pin-in-run":
                report.error(
                    "ENVIRONMENT_IMAGE_POLICY",
                    "TASKSET.json.environment.runtime_image_policy",
                    "must be build-from-frozen-source-and-pin-in-run",
                )
        else:
            for key in ("image_sha256", "data_sha256"):
                _digest(
                    environment.get(key), report, f"TASKSET.json.environment.{key}"
                )
    evaluator = _require_fields(
        taskset.get("evaluator"),
        EVALUATOR_KEYS,
        report,
        "TASKSET.json.evaluator",
    )
    if evaluator is not None:
        for key in (
            "scorer_id",
            "scorer_revision",
            "verifier_id",
            "verifier_revision",
        ):
            _string(evaluator.get(key), report, f"TASKSET.json.evaluator.{key}")
        for key in ("scorer_sha256", "verifier_sha256"):
            _digest(evaluator.get(key), report, f"TASKSET.json.evaluator.{key}")
    license_record = _require_fields(
        taskset.get("license"), LICENSE_KEYS, report, "TASKSET.json.license"
    )
    if license_record is not None:
        _string(
            license_record.get("identifier"),
            report,
            "TASKSET.json.license.identifier",
        )
        redistribution = license_record.get("redistribution")
        if (
            not isinstance(redistribution, str)
            or redistribution not in {"vendored", "reference-only"}
        ):
            report.error(
                "REDISTRIBUTION",
                "TASKSET.json.license.redistribution",
                "must be vendored or reference-only",
            )
    report.facts["taskset_id"] = taskset_id
    report.facts["schema_version"] = taskset_schema
    report.facts["task_constraint_required"] = taskset_with_constraints
    return report, taskset


def _merge_corridor_report(
    target: Report,
    source: corridor_method_registry.Report,
) -> None:
    target.errors.extend(source.errors)
    target.warnings.extend(source.warnings)
    target.facts.update(source.facts)


def _git_blob_at_commit(
    project_root: Path,
    commit: str,
    relative_path: str,
    report: Report,
    location: str,
) -> bytes | None:
    if ":" in relative_path or any(ord(character) < 32 for character in relative_path):
        report.error("METHOD_SOURCE_PATH", location, "Git blob path is not canonical")
        return None

    def run(arguments: list[str]) -> subprocess.CompletedProcess[bytes] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(project_root), *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            report.error("METHOD_SOURCE_GIT", location, type(exc).__name__)
            return None

    verified = run(["rev-parse", "--verify", f"{commit}^{{commit}}"])
    if (
        verified is None
        or verified.returncode != 0
        or verified.stdout.decode("ascii", errors="replace").strip() != commit
    ):
        report.error("METHOD_SOURCE_GIT", location, "source commit is not resolvable")
        return None
    object_spec = f"{commit}:{relative_path}"
    size_result = run(["cat-file", "-s", object_spec])
    if size_result is None or size_result.returncode != 0:
        report.error("METHOD_SOURCE_GIT", location, "method blob is not resolvable")
        return None
    try:
        size = int(size_result.stdout.strip())
    except ValueError:
        report.error("METHOD_SOURCE_GIT", location, "method blob size is invalid")
        return None
    if size > MAX_HASH_BYTES:
        report.error(
            "METHOD_SOURCE_SIZE",
            location,
            f"method blob exceeds {MAX_HASH_BYTES} bytes",
        )
        return None
    blob_result = run(["cat-file", "blob", object_spec])
    if blob_result is None or blob_result.returncode != 0:
        report.error("METHOD_SOURCE_GIT", location, "method blob cannot be read")
        return None
    if len(blob_result.stdout) != size or len(blob_result.stdout) > MAX_HASH_BYTES:
        report.error("METHOD_SOURCE_SIZE", location, "method blob size changed")
        return None
    return blob_result.stdout


def load_method_catalog(path: Path) -> tuple[Report, list[dict[str, Any]]]:
    """Validate method treatment authority, including provenance and frozen bytes."""

    path = path.absolute()
    report = Report(subject=str(path))
    document = load_json(path, report, "method catalog")
    if document is None:
        return report, []
    _require_fields(document, METHOD_INDEX_KEYS, report, "method catalog")
    method_schema = document.get("schema_version")
    if not isinstance(method_schema, str) or method_schema not in (
        LEGACY_METHOD_INDEX_SCHEMA,
        METHOD_INDEX_SCHEMA,
    ):
        report.error(
            "METHOD_SCHEMA",
            "method catalog.schema_version",
            f"expected {LEGACY_METHOD_INDEX_SCHEMA} or {METHOD_INDEX_SCHEMA}",
        )
    method_v2 = method_schema == METHOD_INDEX_SCHEMA
    project_root = path.parent.parent.absolute()
    normative_source = _relative_path(
        document.get("normative_source"),
        report,
        "method catalog.normative_source",
    )
    versions = document.get("versions")
    if not isinstance(versions, list) or not versions:
        report.error(
            "METHOD_VERSIONS",
            "method catalog.versions",
            "must be a non-empty array",
        )
        return report, []
    declared_study_versions = (
        [
            version
            for version in versions
            if isinstance(version, dict) and version.get("study_eligible") is True
        ]
        if method_v2
        else []
    )

    theory_index = _safe_member(
        project_root,
        "theory/VERSIONS.json",
        report,
        "theory catalog",
    )
    theory_versions: list[dict[str, Any]] = []
    theory_schema_version: str | None = None
    if theory_index is not None:
        theory_report, theory_versions = corridor_method_registry.validate_theory_index(
            theory_index
        )
        theory_schema_version = theory_report.facts.get("schema_version")
        _merge_corridor_report(report, theory_report)

    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    for index, version in enumerate(versions):
        location = f"method catalog.versions[{index}]"
        error_count = len(report.errors)
        version_obj = _require_fields(
            version,
            METHOD_VERSION_KEYS if method_v2 else LEGACY_METHOD_VERSION_KEYS,
            report,
            location,
        )
        if version_obj is None:
            continue
        version_id = _string(
            version_obj.get("version_id"),
            report,
            f"{location}.version_id",
        )
        if version_id in seen:
            report.error("DUPLICATE_METHOD", location, "duplicate version_id")
        elif version_id:
            seen.add(version_id)

        status = version_obj.get("status")
        if not isinstance(status, str) or status not in {"draft", "frozen"}:
            report.error(
                "METHOD_STATUS",
                f"{location}.status",
                "must be draft or frozen",
            )
        builder_eligible = version_obj.get("builder_eligible")
        eligibility_fields = [("builder_eligible", builder_eligible)]
        if method_v2:
            eligibility_fields[:0] = [
                ("study_eligible", version_obj.get("study_eligible")),
                ("adoption_eligible", version_obj.get("adoption_eligible")),
            ]
        for field_name, eligible in eligibility_fields:
            if isinstance(eligible, bool):
                continue
            report.error(
                "METHOD_ELIGIBILITY",
                f"{location}.{field_name}",
                "must be boolean",
            )
        if method_v2 and (
            isinstance(version_obj.get("adoption_eligible"), bool)
            and isinstance(builder_eligible, bool)
            and builder_eligible != version_obj.get("adoption_eligible")
        ):
            report.error(
                "METHOD_ADOPTION_ALIAS",
                f"{location}.builder_eligible",
                "deprecated builder_eligible must equal adoption_eligible",
            )
        source_commit = version_obj.get("source_commit")
        if method_v2:
            if not isinstance(source_commit, str) or not COMMIT_RE.fullmatch(
                source_commit
            ):
                report.error(
                    "METHOD_SOURCE_COMMIT",
                    f"{location}.source_commit",
                    "v2 method versions must pin a full lowercase commit",
                )
        elif source_commit is not None and (
            not isinstance(source_commit, str)
            or not COMMIT_RE.fullmatch(source_commit)
        ):
            report.error(
                "METHOD_SOURCE_COMMIT",
                f"{location}.source_commit",
                "must be null or a full lowercase commit",
            )
        needs_frozen_pin = builder_eligible is True
        if method_v2:
            needs_frozen_pin = (
                version_obj.get("study_eligible") is True
                or version_obj.get("adoption_eligible") is True
            )
        if needs_frozen_pin and (status != "frozen" or source_commit is None):
            report.error(
                "METHOD_SOURCE_COMMIT",
                f"{location}.source_commit",
                "study- or adoption-eligible method versions must be frozen at an exact commit",
            )
        method_path_value = _relative_path(
            version_obj.get("path"),
            report,
            f"{location}.path",
        )
        method_member = _safe_member(
            project_root,
            version_obj.get("path"),
            report,
            f"{location}.path",
        )
        method_digest = version_obj.get("content_sha256")
        _digest(method_digest, report, f"{location}.content_sha256")
        if method_path_value != normative_source:
            report.error(
                "METHOD_NORMATIVE_SOURCE",
                f"{location}.path",
                "must equal normative_source",
            )
        if method_member is not None and not method_member.is_file():
            report.error("METHOD_FILE", f"{location}.path", "method file is missing")
        if (
            method_member is not None
            and method_member.is_file()
            and source_commit is None
            and file_sha256(method_member, report, f"{location}.path") != method_digest
        ):
            report.error(
                "METHOD_FILE_HASH",
                f"{location}.content_sha256",
                "does not match current method bytes",
            )
        frozen_method_bytes: bytes | None = None
        if (
            isinstance(source_commit, str)
            and COMMIT_RE.fullmatch(source_commit)
            and isinstance(method_path_value, str)
        ):
            frozen_method_bytes = _git_blob_at_commit(
                project_root,
                source_commit,
                method_path_value,
                report,
                f"{location}.source_commit",
            )
            if (
                frozen_method_bytes is not None
                and "sha256:" + hashlib.sha256(frozen_method_bytes).hexdigest()
                != method_digest
            ):
                report.error(
                    "METHOD_SOURCE_HASH",
                    f"{location}.content_sha256",
                    "does not match method bytes at source_commit",
                )

        scope_path = _safe_member(
            project_root,
            version_obj.get("scope_datum_path"),
            report,
            f"{location}.scope_datum_path",
        )
        scope_digest = version_obj.get("scope_datum_sha256")
        _digest(scope_digest, report, f"{location}.scope_datum_sha256")
        if scope_path is None or not scope_path.is_file():
            report.error(
                "METHOD_SCOPE_FILE",
                f"{location}.scope_datum_path",
                "scope datum must be a regular non-symlink file",
            )
        elif (not method_v2 or source_commit is None) and file_sha256(
            scope_path, report, f"{location}.scope_datum_path"
        ) != scope_digest:
            report.error(
                "METHOD_SCOPE_HASH",
                f"{location}.scope_datum_sha256",
                "does not match scope datum bytes",
            )
        if (
            method_v2
            and isinstance(source_commit, str)
            and COMMIT_RE.fullmatch(source_commit)
            and isinstance(version_obj.get("scope_datum_path"), str)
        ):
            frozen_scope_bytes = _git_blob_at_commit(
                project_root,
                source_commit,
                version_obj["scope_datum_path"],
                report,
                f"{location}.source_commit",
            )
            if (
                frozen_scope_bytes is not None
                and "sha256:" + hashlib.sha256(frozen_scope_bytes).hexdigest()
                != scope_digest
            ):
                report.error(
                    "METHOD_SCOPE_SOURCE_HASH",
                    f"{location}.scope_datum_sha256",
                    "does not match scope datum bytes at source_commit",
                )

        lineage = _require_fields(
            version_obj.get("derived_from"),
            {
                "theory_version_id",
                "source_commit",
                "representation",
                "content_sha256",
            },
            report,
            f"{location}.derived_from",
        )
        if lineage is not None:
            theory_version_id = _string(
                lineage.get("theory_version_id"),
                report,
                f"{location}.derived_from.theory_version_id",
            )
            lineage_commit = lineage.get("source_commit")
            _commit(
                lineage_commit,
                report,
                f"{location}.derived_from.source_commit",
            )
            representation = _string(
                lineage.get("representation"),
                report,
                f"{location}.derived_from.representation",
            )
            lineage_digest = lineage.get("content_sha256")
            _digest(
                lineage_digest,
                report,
                f"{location}.derived_from.content_sha256",
            )
            lineage_matches = [
                theory
                for theory in theory_versions
                if theory.get("version_id") == theory_version_id
                and isinstance(theory.get("source"), dict)
                and theory["source"].get("commit") == lineage_commit
                and any(
                    isinstance(item, dict)
                    and item.get("kind") == representation
                    and item.get("sha256") == lineage_digest
                    for item in theory.get("representations", [])
                )
            ]
            if len(lineage_matches) != 1:
                report.error(
                    "METHOD_LINEAGE",
                    f"{location}.derived_from",
                    "must resolve exactly once to the local theory catalog",
                )

        catalog_paths: dict[str, Path] = {}
        for key in ("claim_catalog", "source_catalog", "evidence_index"):
            member = _safe_member(
                project_root,
                version_obj.get(key),
                report,
                f"{location}.{key}",
            )
            if member is None or not member.is_file():
                report.error(
                    "METHOD_CATALOG_FILE",
                    f"{location}.{key}",
                    "must be a regular non-symlink file",
                )
            else:
                catalog_paths[key] = member
        if (
            version_id is not None
            and (
                not method_v2
                or (
                    len(declared_study_versions) == 1
                    and version_obj is declared_study_versions[0]
                )
            )
            and set(catalog_paths)
            == {"claim_catalog", "source_catalog", "evidence_index"}
        ):
            provenance_report = corridor_method_registry.Report(
                subject=str(project_root)
            )
            corridor_method_registry._validate_method_provenance_catalogs(
                project_root,
                version_id,
                catalog_paths,
                provenance_report,
                theory_versions=theory_versions,
                theory_schema_version=theory_schema_version,
                method_lineage=lineage,
            )
            _merge_corridor_report(report, provenance_report)

        if len(report.errors) == error_count:
            valid.append(version_obj)

    if method_v2:
        valid_study_versions = [
            version for version in valid if version.get("study_eligible") is True
        ]
        if len(declared_study_versions) != 1:
            report.error(
                "METHOD_STUDY_VERSION_COUNT",
                "method catalog.versions",
                "must contain exactly one study-eligible method version",
            )
        elif len(valid_study_versions) != 1:
            report.error(
                "METHOD_STUDY_VERSION_INVALID",
                "method catalog.versions",
                "the unique study-eligible method version must validate completely",
            )

    report.facts["method_version_count"] = len(valid)
    report.facts["schema_version"] = method_schema
    if method_v2:
        report.facts["study_eligible_method_version_count"] = sum(
            version.get("study_eligible") is True for version in valid
        )
        report.facts["adoption_eligible_method_version_count"] = sum(
            version.get("adoption_eligible") is True for version in valid
        )
    report.facts["eligible_method_version_count"] = sum(
        version.get("builder_eligible") is True for version in valid
    )
    if method_v2 and (
        len(declared_study_versions) != 1
        or len(valid_study_versions) != 1
        or report.errors
    ):
        return report, []
    return report, valid


def validate_study(
    path: Path,
    exogenous_root: Path,
    tasksets_by_id: dict[str, tuple[Path, dict[str, Any]]],
    method_versions: list[dict[str, Any]] | None = None,
) -> tuple[Report, dict[str, Any] | None]:
    report = Report(subject=str(path.resolve()))
    study = load_json(path, report, "STUDY.json")
    if study is None:
        return report, None
    study_schema = study.get("schema_version")
    if not isinstance(study_schema, str) or study_schema not in (
        LEGACY_STUDY_SCHEMA,
        STUDY_SCHEMA,
        STUDY_V3_SCHEMA,
    ):
        report.error(
            "STUDY_SCHEMA",
            "STUDY.json.schema_version",
            f"expected {LEGACY_STUDY_SCHEMA}, {STUDY_SCHEMA}, or {STUDY_V3_SCHEMA}",
        )
    _require_fields(
        study,
        STUDY_V3_KEYS if study_schema == STUDY_V3_SCHEMA else STUDY_KEYS,
        report,
        "STUDY.json",
    )
    study_v2 = study_schema in (STUDY_SCHEMA, STUDY_V3_SCHEMA)
    study_v3 = study_schema == STUDY_V3_SCHEMA
    study_id = _string(study.get("study_id"), report, "STUDY.json.study_id")
    resolved_taskset: dict[str, Any] | None = None
    resolved_constraint_method_refs: list[dict[str, Any]] = []
    _string(study.get("title"), report, "STUDY.json.title")
    if path.parent.name != study_id or path.name != "STUDY.json":
        report.error(
            "STUDY_PATH",
            "STUDY.json",
            "path must be studies/<study_id>/STUDY.json",
        )
    taskset_ref = _require_fields(
        study.get("taskset_ref"),
        STUDY_TASKSET_REF_KEYS,
        report,
        "STUDY.json.taskset_ref",
    )
    if taskset_ref is not None:
        taskset_id = _string(
            taskset_ref.get("taskset_id"),
            report,
            "STUDY.json.taskset_ref.taskset_id",
        )
        taskset_path_value = _relative_path(
            taskset_ref.get("path"), report, "STUDY.json.taskset_ref.path"
        )
        _digest(
            taskset_ref.get("sha256"),
            report,
            "STUDY.json.taskset_ref.sha256",
        )
        found = tasksets_by_id.get(str(taskset_id))
        if found is None:
            report.error(
                "STUDY_TASKSET",
                "STUDY.json.taskset_ref",
                "taskset_id is not cataloged",
            )
        else:
            found_path, resolved_taskset = found
            expected_relative = found_path.relative_to(exogenous_root).as_posix()
            if taskset_path_value != expected_relative:
                report.error(
                    "STUDY_TASKSET_PATH",
                    "STUDY.json.taskset_ref.path",
                    "does not match cataloged TASKSET path",
                )
            if taskset_ref.get("sha256") != file_sha256(
                found_path,
                report,
                "STUDY.json.taskset_ref.path",
            ):
                report.error(
                    "STUDY_TASKSET_HASH",
                    "STUDY.json.taskset_ref.sha256",
                    "does not match TASKSET bytes",
                )
            if resolved_taskset.get("schema_version") in (
                TASKSET_V2_SCHEMA,
                TASKSET_V3_SCHEMA,
            ):
                for task_index, task in enumerate(resolved_taskset.get("tasks", [])):
                    constraint_ref = task.get("constraint_datum") if isinstance(task, dict) else None
                    constraint_path = (
                        _safe_member(
                            found_path.parent,
                            constraint_ref.get("path"),
                            report,
                            f"STUDY.json.taskset_ref.constraints[{task_index}]",
                        )
                        if isinstance(constraint_ref, dict)
                        else None
                    )
                    if constraint_path is not None and isinstance(constraint_ref, dict):
                        constraint_sha256 = file_sha256(
                            constraint_path,
                            report,
                            f"STUDY.json.taskset_ref.constraints[{task_index}]",
                        )
                        if constraint_ref.get("sha256") != constraint_sha256:
                            report.error(
                                "STUDY_TASK_CONSTRAINT_HASH",
                                f"STUDY.json.taskset_ref.constraints[{task_index}]",
                                "does not match the constraint datum bytes consumed by the study",
                            )
                    constraint = (
                        load_json(
                            constraint_path,
                            report,
                            f"STUDY.json.taskset_ref.constraints[{task_index}]",
                        )
                        if constraint_path is not None
                        else None
                    )
                    builder = constraint.get("builder") if isinstance(constraint, dict) else None
                    method_ref = builder.get("method_ref") if isinstance(builder, dict) else None
                    if isinstance(method_ref, dict):
                        resolved_constraint_method_refs.append(method_ref)
    resolved_protocol_path: Path | None = None
    if study_v3:
        protocol_ref = _require_fields(
            study.get("protocol_ref"),
            STUDY_PROTOCOL_REF_KEYS,
            report,
            "STUDY.json.protocol_ref",
        )
        if protocol_ref is not None:
            protocol_path_value = _relative_path(
                protocol_ref.get("path"),
                report,
                "STUDY.json.protocol_ref.path",
            )
            _digest(
                protocol_ref.get("sha256"),
                report,
                "STUDY.json.protocol_ref.sha256",
            )
            if protocol_path_value is not None:
                protocol_parts = PurePosixPath(protocol_path_value).parts
                if not protocol_parts or protocol_parts[0] != "protocol":
                    report.error(
                        "STUDY_PROTOCOL_PATH",
                        "STUDY.json.protocol_ref.path",
                        "must name a repository-relative file beneath protocol/",
                    )
                else:
                    resolved_protocol_path = _safe_member(
                        exogenous_root.parent,
                        protocol_path_value,
                        report,
                        "STUDY.json.protocol_ref.path",
                    )
                    if resolved_protocol_path is not None:
                        actual_protocol_sha256 = file_sha256(
                            resolved_protocol_path,
                            report,
                            "STUDY.json.protocol_ref.path",
                        )
                        if protocol_ref.get("sha256") != actual_protocol_sha256:
                            report.error(
                                "STUDY_PROTOCOL_HASH",
                                "STUDY.json.protocol_ref.sha256",
                                "does not match the declared protocol bytes",
                            )
        report.facts["protocol_ref"] = (
            {
                "path": study.get("protocol_ref", {}).get("path"),
                "sha256": study.get("protocol_ref", {}).get("sha256"),
            }
            if isinstance(study.get("protocol_ref"), dict)
            else None
        )
    else:
        _digest(study.get("protocol_sha256"), report, "STUDY.json.protocol_sha256")
    _string(
        study.get("comparison_intent"),
        report,
        "STUDY.json.comparison_intent",
    )
    conditions = study.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        report.error(
            "STUDY_CONDITIONS",
            "STUDY.json.conditions",
            "must be a non-empty array",
        )
        conditions = []
    condition_ids: set[str] = set()
    study_eligible_condition_ids: set[str] = set()
    study_eligible_method_refs: list[dict[str, Any]] = []
    for index, condition in enumerate(conditions):
        location = f"STUDY.json.conditions[{index}]"
        condition_obj = _require_fields(condition, CONDITION_KEYS, report, location)
        if condition_obj is None:
            continue
        condition_id = _string(
            condition_obj.get("condition_id"), report, f"{location}.condition_id"
        )
        if condition_id in condition_ids:
            report.error("DUPLICATE_CONDITION", location, "duplicate condition_id")
        elif condition_id:
            condition_ids.add(condition_id)
        system_condition = condition_obj.get("system_condition")
        if (
            not isinstance(system_condition, str)
            or system_condition not in ALLOWED_SYSTEM
        ):
            report.error(
                "CONDITION_SYSTEM",
                f"{location}.system_condition",
                "invalid system condition",
            )
        knowledge = _string(
            condition_obj.get("knowledge_condition"),
            report,
            f"{location}.knowledge_condition",
        )
        if knowledge not in ALLOWED_KNOWLEDGE:
            report.error(
                "KNOWLEDGE_CONDITION",
                f"{location}.knowledge_condition",
                f"must be one of {sorted(ALLOWED_KNOWLEDGE)}",
            )
        for key in ("common_inputs_sha256", "treatment_inputs_sha256"):
            _digest(condition_obj.get(key), report, f"{location}.{key}")
        if (
            resolved_taskset is not None
            and resolved_taskset.get("schema_version")
            in (TASKSET_V2_SCHEMA, TASKSET_V3_SCHEMA)
            and condition_obj.get("common_inputs_sha256")
            != resolved_taskset.get("task_list_sha256")
        ):
            report.error(
                "STUDY_COMMON_INPUTS",
                f"{location}.common_inputs_sha256",
                "constraint-bearing TaskSet studies must bind the ordered task and constraint datum digest",
            )
        method_ref = condition_obj.get("method_paper_ref")
        if knowledge == "method-paper":
            method_obj = _require_fields(
                method_ref,
                METHOD_REF_KEYS if study_v2 else LEGACY_METHOD_REF_KEYS,
                report,
                f"{location}.method_paper_ref",
            )
            if method_obj is not None:
                if resolved_constraint_method_refs and any(
                    constraint_method_ref != method_obj
                    for constraint_method_ref in resolved_constraint_method_refs
                ):
                    report.error(
                        "STUDY_TASK_CONSTRAINT_METHOD_JOIN",
                        f"{location}.method_paper_ref",
                        "must equal every v2 task constraint MethodRef",
                    )
                method_version_id = _string(
                    method_obj.get("version_id"),
                    report,
                    f"{location}.method_paper_ref.version_id",
                )
                _commit(
                    method_obj.get("source_commit"),
                    report,
                    f"{location}.method_paper_ref.source_commit",
                )
                representation_path = _relative_path(
                    method_obj.get("representation_path"),
                    report,
                    f"{location}.method_paper_ref.representation_path",
                )
                _digest(
                    method_obj.get("content_sha256"),
                    report,
                    f"{location}.method_paper_ref.content_sha256",
                )
                builder_eligible = method_obj.get("builder_eligible")
                if not isinstance(builder_eligible, bool):
                    report.error(
                        "METHOD_ELIGIBILITY",
                        f"{location}.method_paper_ref.builder_eligible",
                        "must be boolean",
                    )
                if study_v2:
                    study_eligible = method_obj.get("study_eligible")
                    adoption_eligible = method_obj.get("adoption_eligible")
                    for field_name, eligible in (
                        ("study_eligible", study_eligible),
                        ("adoption_eligible", adoption_eligible),
                    ):
                        if not isinstance(eligible, bool):
                            report.error(
                                "METHOD_ELIGIBILITY",
                                f"{location}.method_paper_ref.{field_name}",
                                "must be boolean",
                            )
                if study_v2 and method_obj.get("study_eligible") is not True:
                    report.error(
                        "METHOD_INELIGIBLE",
                        f"{location}.method_paper_ref.study_eligible",
                        "method treatment requires an explicitly study-eligible frozen version",
                    )
                if study_v2 and (
                    isinstance(method_obj.get("adoption_eligible"), bool)
                    and isinstance(builder_eligible, bool)
                    and builder_eligible != method_obj.get("adoption_eligible")
                ):
                    report.error(
                        "METHOD_ADOPTION_ALIAS",
                        f"{location}.method_paper_ref.builder_eligible",
                        "deprecated builder_eligible must equal adoption_eligible",
                    )
                if method_versions is None:
                    report.error(
                        "METHOD_CATALOG_REQUIRED",
                        f"{location}.method_paper_ref",
                        "method-paper conditions require the local method catalog",
                    )
                else:
                    matches = []
                    for version in method_versions:
                        exact_pin = (
                            version.get("version_id") == method_version_id
                            and version.get("source_commit")
                            == method_obj.get("source_commit")
                            and version.get("path") == representation_path
                            and version.get("content_sha256")
                            == method_obj.get("content_sha256")
                            and version.get("builder_eligible")
                            == method_obj.get("builder_eligible")
                        )
                        if not exact_pin:
                            continue
                        if study_v2:
                            exact_pin = (
                                version.get("study_eligible")
                                == method_obj.get("study_eligible")
                                and version.get("adoption_eligible")
                                == method_obj.get("adoption_eligible")
                                and version.get("study_eligible") is True
                            )
                        else:
                            exact_pin = version.get("builder_eligible") is True
                        if exact_pin:
                            matches.append(version)
                    if len(matches) != 1:
                        report.error(
                            "METHOD_CATALOG_REF",
                            f"{location}.method_paper_ref",
                            "must match exactly one locally cataloged study-eligible method version and frozen eligibility snapshot",
                        )
                    elif study_v2 and isinstance(condition_id, str):
                        study_eligible_condition_ids.add(condition_id)
                        study_eligible_method_refs.append(
                            {
                                "condition_id": condition_id,
                                "version_id": method_obj.get("version_id"),
                                "source_commit": method_obj.get("source_commit"),
                                "representation_path": method_obj.get(
                                    "representation_path"
                                ),
                                "content_sha256": method_obj.get("content_sha256"),
                                "study_eligible": method_obj.get("study_eligible"),
                                "adoption_eligible": method_obj.get(
                                    "adoption_eligible"
                                ),
                                "builder_eligible": method_obj.get(
                                    "builder_eligible"
                                ),
                            }
                        )
        elif method_ref is not None:
            report.error(
                "METHOD_REF_UNEXPECTED",
                f"{location}.method_paper_ref",
                "must be null outside method-paper condition",
            )
    if (
        resolved_taskset is not None
        and resolved_taskset.get("schema_version")
        in (TASKSET_V2_SCHEMA, TASKSET_V3_SCHEMA)
        and any(
            isinstance(condition, dict)
            and condition.get("system_condition") == "corridor"
            for condition in conditions
        )
    ):
        if study_v3:
            if resolved_protocol_path is None:
                report.error(
                    "STUDY_PROTOCOL_REF",
                    "STUDY.json.protocol_ref",
                    "must resolve to exact protocol bytes for a Corridor condition",
                )
        else:
            protocol_path = (
                exogenous_root.parent
                / "protocol"
                / "TASK-CONDITIONED-CORRIDOR-EXPERIMENT.md"
            )
            protocol_sha256 = file_sha256(
                protocol_path,
                report,
                "STUDY.json.protocol_sha256",
            )
            if study.get("protocol_sha256") != protocol_sha256:
                report.error(
                    "STUDY_PROTOCOL_HASH",
                    "STUDY.json.protocol_sha256",
                    "must equal the historical task-conditioned Corridor protocol bytes",
                )
    assignment = _require_fields(
        study.get("assignment"),
        ASSIGNMENT_KEYS,
        report,
        "STUDY.json.assignment",
    )
    if assignment is not None:
        for key in ("mode", "unit"):
            _string(assignment.get(key), report, f"STUDY.json.assignment.{key}")
        _digest(
            assignment.get("assignment_sha256"),
            report,
            "STUDY.json.assignment.assignment_sha256",
        )
    report.facts["study_id"] = study_id
    report.facts["schema_version"] = study_schema
    report.facts["study_eligible_condition_ids"] = sorted(
        study_eligible_condition_ids
    )
    report.facts["study_eligible_method_refs"] = sorted(
        study_eligible_method_refs, key=lambda item: str(item["condition_id"])
    )
    report.facts["formal_method_study_eligible"] = (
        study_v2 and report.ok and bool(study_eligible_condition_ids)
    )
    report.facts["condition_ids"] = sorted(condition_ids)
    return report, study


def validate_run(
    run_root: Path,
    *,
    allow_template: bool = False,
) -> tuple[Report, dict[str, Any] | None]:
    run_root = run_root.resolve()
    report = Report(subject=str(run_root))
    run = load_json(run_root / "RUN.json", report, "RUN.json")
    if run is None:
        return report, None
    run_schema = run.get("schema_version")
    run_v2 = run_schema == RUN_SCHEMA
    _require_fields(
        run,
        RUN_KEYS if run_v2 else LEGACY_RUN_KEYS,
        report,
        "RUN.json",
    )
    if not isinstance(run_schema, str) or run_schema not in (
        LEGACY_RUN_SCHEMA,
        RUN_SCHEMA,
    ):
        report.error(
            "SCHEMA",
            "RUN.json.schema_version",
            f"expected {LEGACY_RUN_SCHEMA} or {RUN_SCHEMA}",
        )
    is_template = run.get("template") is True
    if not isinstance(run.get("template"), bool):
        report.error("TEMPLATE_TYPE", "RUN.json.template", "must be boolean")
    if is_template and not allow_template:
        report.error("TEMPLATE", "RUN.json", "template cannot be registered")

    run_id = _string(run.get("run_id"), report, "RUN.json.run_id")
    _string(run.get("runner_id"), report, "RUN.json.runner_id")
    status = run.get("status")
    if not isinstance(status, str) or status not in ALLOWED_RUN_STATUS:
        report.error("RUN_STATUS", "RUN.json.status", "invalid run status")
    _string(run.get("condition_id"), report, "RUN.json.condition_id")
    trial = run.get("trial")
    if not isinstance(trial, int) or isinstance(trial, bool) or trial < 0:
        report.error("TRIAL", "RUN.json.trial", "must be a non-negative integer")
    _string(run.get("seed"), report, "RUN.json.seed")

    study = _require_fields(
        run.get("study_ref"), STUDY_REF_KEYS, report, "RUN.json.study_ref"
    )
    if study is not None:
        _string(study.get("study_id"), report, "RUN.json.study_ref.study_id")
        _relative_path(study.get("path"), report, "RUN.json.study_ref.path")
        _digest(study.get("sha256"), report, "RUN.json.study_ref.sha256")

    task = _require_fields(
        run.get("task_ref"), TASK_REF_KEYS, report, "RUN.json.task_ref"
    )
    if task is not None:
        for key in ("taskset_id", "task_id"):
            _string(task.get(key), report, f"RUN.json.task_ref.{key}")
        for key in ("taskset_sha256", "task_sha256"):
            _digest(task.get(key), report, f"RUN.json.task_ref.{key}")

    runtime = _require_fields(
        run.get("runtime"), RUNTIME_KEYS, report, "RUN.json.runtime"
    )
    if runtime is not None:
        if runtime.get("executor_type") != "ai-agent":
            report.error(
                "EXECUTOR_TYPE",
                "RUN.json.runtime.executor_type",
                "v1 supports exactly ai-agent",
            )
        for key in ("executor_type", "provider", "model", "runtime"):
            _string(runtime.get(key), report, f"RUN.json.runtime.{key}")
        for key in (
            "profile_sha256",
            "tools_sha256",
            "budget_sha256",
            "stopping_rule_sha256",
        ):
            _digest(runtime.get(key), report, f"RUN.json.runtime.{key}")
        network_access = runtime.get("network_access")
        if (
            not isinstance(network_access, str)
            or network_access not in ALLOWED_NETWORK
        ):
            report.error(
                "NETWORK_ACCESS",
                "RUN.json.runtime.network_access",
                "invalid network access state",
            )

    measurement_plan_complete = False
    if run_v2:
        measurement_plan = _require_fields(
            run.get("measurement_plan"),
            MEASUREMENT_PLAN_KEYS,
            report,
            "RUN.json.measurement_plan",
        )
    else:
        measurement_plan = None
    if run_v2 and measurement_plan is not None:
        if measurement_plan.get("schema_version") != MEASUREMENT_PLAN_SCHEMA:
            report.error(
                "MEASUREMENT_PLAN_SCHEMA",
                "RUN.json.measurement_plan.schema_version",
                f"expected {MEASUREMENT_PLAN_SCHEMA}",
            )
        if measurement_plan.get("usage_receipt_schema") != USAGE_RECEIPT_SCHEMA:
            report.error(
                "USAGE_RECEIPT_SCHEMA",
                "RUN.json.measurement_plan.usage_receipt_schema",
                f"expected {USAGE_RECEIPT_SCHEMA}",
            )
        if measurement_plan.get("package_cost_schema") != PACKAGE_COST_SCHEMA:
            report.error(
                "PACKAGE_COST_SCHEMA",
                "RUN.json.measurement_plan.package_cost_schema",
                f"expected {PACKAGE_COST_SCHEMA}",
            )
        if measurement_plan.get("required_usage_stages") != list(
            REQUIRED_USAGE_STAGES
        ):
            report.error(
                "REQUIRED_USAGE_STAGES",
                "RUN.json.measurement_plan.required_usage_stages",
                f"must equal the ordered stages {list(REQUIRED_USAGE_STAGES)}",
            )
        if measurement_plan.get("raw_evidence_profile") != "complete-digest-bound":
            report.error(
                "RAW_EVIDENCE_PROFILE",
                "RUN.json.measurement_plan.raw_evidence_profile",
                "must be complete-digest-bound",
            )
        if measurement_plan.get("independent_replay_required") is not True:
            report.error(
                "INDEPENDENT_REPLAY_REQUIRED",
                "RUN.json.measurement_plan.independent_replay_required",
                "must be boolean true",
            )
        measurement_plan_complete = (
            set(measurement_plan) == MEASUREMENT_PLAN_KEYS
            and measurement_plan.get("schema_version") == MEASUREMENT_PLAN_SCHEMA
            and measurement_plan.get("usage_receipt_schema")
            == USAGE_RECEIPT_SCHEMA
            and measurement_plan.get("package_cost_schema") == PACKAGE_COST_SCHEMA
            and measurement_plan.get("required_usage_stages")
            == list(REQUIRED_USAGE_STAGES)
            and measurement_plan.get("raw_evidence_profile")
            == "complete-digest-bound"
            and measurement_plan.get("independent_replay_required") is True
        )

    world = _require_fields(
        run.get("world_ref"),
        WORLD_REF_KEYS if run_v2 else LEGACY_WORLD_REF_KEYS,
        report,
        "RUN.json.world_ref",
    )
    if world is not None:
        if run_v2:
            for key in ("project_id", "run_id", "generation_id"):
                _string(world.get(key), report, f"RUN.json.world_ref.{key}")
            _https_url(
                world.get("repository_url"),
                report,
                "RUN.json.world_ref.repository_url",
            )
            if world.get("run_id") != run_id:
                report.error(
                    "RUN_WORLD_RUN",
                    "RUN.json.world_ref.run_id",
                    "must equal RUN.json.run_id",
                )
            _digest(
                world.get("derived_state_sha256"),
                report,
                "RUN.json.world_ref.derived_state_sha256",
            )
        _commit(world.get("base_commit"), report, "RUN.json.world_ref.base_commit")
        _digest(
            world.get("environment_sha256"),
            report,
            "RUN.json.world_ref.environment_sha256",
        )
        prefix = world.get("evidence_prefix")
        if run_v2 and prefix is None:
            report.error(
                "RUN_WORLD_PREFIX",
                "RUN.json.world_ref.evidence_prefix",
                "v2 WorldRef requires a complete raw-ledger prefix",
            )
        if prefix is not None:
            prefix_obj = _require_fields(
                prefix,
                PREFIX_KEYS if run_v2 else LEGACY_PREFIX_KEYS,
                report,
                "RUN.json.world_ref.evidence_prefix",
            )
            if prefix_obj is not None:
                _string(
                    prefix_obj.get("stream_id"),
                    report,
                    "RUN.json.world_ref.evidence_prefix.stream_id",
                )
                sequence = prefix_obj.get("through_sequence")
                if (
                    not isinstance(sequence, int)
                    or isinstance(sequence, bool)
                    or sequence < 0
                ):
                    report.error(
                        "PREFIX_SEQUENCE",
                        "RUN.json.world_ref.evidence_prefix.through_sequence",
                        "must be a non-negative integer",
                    )
                _digest(
                    prefix_obj.get("prefix_sha256"),
                    report,
                    "RUN.json.world_ref.evidence_prefix.prefix_sha256",
                )
                projector = _require_fields(
                    prefix_obj.get("projector"),
                    PROJECTOR_KEYS if run_v2 else LEGACY_PROJECTOR_KEYS,
                    report,
                    "RUN.json.world_ref.evidence_prefix.projector",
                )
                if projector is not None:
                    for key in (
                        ("schema_version", "algorithm_id", "algorithm_version")
                        if run_v2
                        else ("id", "version")
                    ):
                        _string(
                            projector.get(key),
                            report,
                            f"RUN.json.world_ref.evidence_prefix.projector.{key}",
                        )
                    digest_key = "algorithm_sha256" if run_v2 else "sha256"
                    _digest(
                        projector.get(digest_key),
                        report,
                        f"RUN.json.world_ref.evidence_prefix.projector.{digest_key}",
                    )
                if run_v2:
                    admission = _require_fields(
                        prefix_obj.get("admission"),
                        ADMISSION_KEYS,
                        report,
                        "RUN.json.world_ref.evidence_prefix.admission",
                    )
                    if admission is not None:
                        for key in ("receipt_id", "rule_revision"):
                            _string(admission.get(key), report, f"RUN.json.world_ref.evidence_prefix.admission.{key}")
                        for key in ("admitted_root_sha256", "rule_sha256"):
                            _digest(admission.get(key), report, f"RUN.json.world_ref.evidence_prefix.admission.{key}")

    subject = _require_fields(
        run.get("subject"), SUBJECT_KEYS, report, "RUN.json.subject"
    )
    if subject is not None:
        system_condition = subject.get("system_condition")
        if (
            not isinstance(system_condition, str)
            or system_condition not in ALLOWED_SYSTEM
        ):
            report.error(
                "SYSTEM_CONDITION",
                "RUN.json.subject.system_condition",
                "invalid system condition",
            )
        _https_url(
            subject.get("repository_url"), report, "RUN.json.subject.repository_url"
        )
        for key in ("base_commit", "artifact_commit"):
            _commit(subject.get(key), report, f"RUN.json.subject.{key}")
        if world is not None and subject.get("base_commit") != world.get("base_commit"):
            report.error(
                "RUN_WORLD_BASE",
                "RUN.json.subject.base_commit",
                "must equal RUN WorldRef base_commit",
            )
        if run_v2 and world is not None and subject.get("repository_url") != world.get("repository_url"):
            report.error(
                "RUN_WORLD_REPOSITORY",
                "RUN.json.subject.repository_url",
                "must equal RUN WorldRef repository_url",
            )
        _relative_path(
            subject.get("artifact_root"), report, "RUN.json.subject.artifact_root"
        )
        _digest(
            subject.get("artifact_tree_sha256"),
            report,
            "RUN.json.subject.artifact_tree_sha256",
        )
        if subject.get("branch_hint") is not None:
            _string(
                subject.get("branch_hint"), report, "RUN.json.subject.branch_hint"
            )

    supersedes = run.get("supersedes_run_id")
    if supersedes is not None:
        _string(supersedes, report, "RUN.json.supersedes_run_id")
        if supersedes == run_id:
            report.error(
                "SUPERSEDES_SELF",
                "RUN.json.supersedes_run_id",
                "run cannot supersede itself",
            )

    report.facts.update(
        {
            "run_id": run_id,
            "schema_version": run_schema,
            "template": is_template,
            "status": status,
            "measurement_plan_complete": measurement_plan_complete,
            "measurement_plan_sha256": (
                canonical_sha256(measurement_plan)
                if measurement_plan_complete
                else None
            ),
            "run_sha256": file_sha256(
                run_root / "RUN.json", report, "RUN.json"
            ),
            "world_ref_sha256": canonical_sha256(run.get("world_ref")),
            "subject_identity_sha256": canonical_sha256(
                {
                    key: subject.get(key)
                    for key in (
                        "system_condition",
                        "repository_url",
                        "base_commit",
                        "artifact_commit",
                        "artifact_root",
                        "artifact_tree_sha256",
                    )
                }
            )
            if subject is not None
            else "",
        }
    )
    return report, run


def _validate_score(
    path: Path,
    run: dict[str, Any],
    report: Report,
    taskset: dict[str, Any] | None,
) -> dict[str, Any] | None:
    score = load_json(path, report, "SCORE.json")
    if score is None:
        return None
    _require_fields(score, SCORE_KEYS, report, "SCORE.json")
    if score.get("schema_version") != SCORE_SCHEMA:
        report.error("SCORE_SCHEMA", "SCORE.json.schema_version", "invalid score schema")
    for key in ("score_id", "evaluator_id", "seed", "evaluated_at"):
        _string(score.get(key), report, f"SCORE.json.{key}")
    run_ref = _require_fields(
        score.get("run_ref"), {"run_id", "sha256"}, report, "SCORE.json.run_ref"
    )
    if run_ref is not None:
        if run_ref.get("run_id") != run.get("run_id"):
            report.error("SCORE_RUN_REF", "SCORE.json.run_ref.run_id", "run id mismatch")
        if run_ref.get("sha256") != file_sha256(
            path.parent / "RUN.json",
            report,
            "SCORE.json.run_ref.sha256",
        ):
            report.error("SCORE_RUN_REF", "SCORE.json.run_ref.sha256", "run digest mismatch")
    if score.get("task_ref") != run.get("task_ref"):
        report.error("SCORE_TASK_REF", "SCORE.json.task_ref", "must equal RUN task_ref")
    evaluator = _require_fields(
        score.get("evaluator"),
        EVALUATOR_KEYS,
        report,
        "SCORE.json.evaluator",
    )
    if (
        evaluator is not None
        and taskset is not None
        and evaluator != taskset.get("evaluator")
    ):
        report.error(
            "SCORE_EVALUATOR",
            "SCORE.json.evaluator",
            "must equal TASKSET evaluator identity",
        )
    if score.get("environment_sha256") != run.get("world_ref", {}).get(
        "environment_sha256"
    ):
        report.error(
            "SCORE_ENVIRONMENT",
            "SCORE.json.environment_sha256",
            "must equal RUN environment",
        )
    if score.get("world_ref_sha256") != canonical_sha256(run.get("world_ref")):
        report.error(
            "SCORE_WORLD_REF",
            "SCORE.json.world_ref_sha256",
            "must bind exact RUN WorldRef",
        )
    expected_subject = {
        "artifact_commit": run.get("subject", {}).get("artifact_commit"),
        "artifact_tree_sha256": run.get("subject", {}).get("artifact_tree_sha256"),
    }
    if score.get("subject_ref") != expected_subject:
        report.error(
            "SCORE_SUBJECT_REF",
            "SCORE.json.subject_ref",
            "must bind exact RUN subject",
        )
    if score.get("trial") != run.get("trial") or isinstance(score.get("trial"), bool):
        report.error("SCORE_TRIAL", "SCORE.json.trial", "must equal RUN trial")
    if score.get("seed") != run.get("seed"):
        report.error("SCORE_SEED", "SCORE.json.seed", "must equal RUN seed")
    outcome_status = score.get("outcome_status")
    if (
        not isinstance(outcome_status, str)
        or outcome_status not in ALLOWED_OUTCOME
    ):
        report.error("SCORE_OUTCOME", "SCORE.json.outcome_status", "invalid outcome")
    infrastructure_status = score.get("infrastructure_status")
    if (
        not isinstance(infrastructure_status, str)
        or infrastructure_status not in ALLOWED_INFRA
    ):
        report.error(
            "SCORE_INFRASTRUCTURE",
            "SCORE.json.infrastructure_status",
            "invalid infrastructure status",
        )
    return score


def collect_registry(
    root: Path,
    method_versions: list[dict[str, Any]] | None = None,
) -> tuple[Report, list[dict[str, Any]]]:
    root = root.resolve()
    report = Report(subject=str(root))
    run_dir = root / "runs"
    if run_dir.is_symlink() or not run_dir.is_dir():
        report.error("RUN_DIRECTORY", "runs", "must be a directory")
        return report, []
    tasksets_by_id: dict[str, tuple[Path, dict[str, Any]]] = {}
    taskset_paths = set(root.glob("benchmarks/*/*/TASKSET.json"))
    taskset_paths.update(root.glob("benchmarks/*/*/tasksets/*/TASKSET.json"))
    for path in sorted(taskset_paths):
        safe_path = _safe_member(
            root,
            path.relative_to(root).as_posix(),
            report,
            "benchmarks TASKSET.json",
        )
        if safe_path is None:
            continue
        taskset_report, taskset = validate_taskset(safe_path, root)
        report.errors.extend(taskset_report.errors)
        report.warnings.extend(taskset_report.warnings)
        if taskset is None or not taskset_report.ok:
            continue
        taskset_id = taskset.get("taskset_id")
        if taskset_id in tasksets_by_id:
            report.error("DUPLICATE_TASKSET", "benchmarks", "duplicate taskset_id")
        elif isinstance(taskset_id, str):
            tasksets_by_id[taskset_id] = (safe_path, taskset)

    studies_by_id: dict[
        str, tuple[Path, dict[str, Any], dict[str, dict[str, Any]]]
    ] = {}
    for path in sorted(root.glob("studies/*/STUDY.json")):
        safe_path = _safe_member(
            root,
            path.relative_to(root).as_posix(),
            report,
            "studies STUDY.json",
        )
        if safe_path is None:
            continue
        study_report, study = validate_study(
            safe_path,
            root,
            tasksets_by_id,
            method_versions=method_versions,
        )
        report.errors.extend(study_report.errors)
        report.warnings.extend(study_report.warnings)
        if study is None or not study_report.ok:
            continue
        study_id = study.get("study_id")
        if study_id in studies_by_id:
            report.error("DUPLICATE_STUDY", "studies", "duplicate study_id")
        elif isinstance(study_id, str):
            studies_by_id[study_id] = (
                safe_path,
                study,
                {
                    condition.get("condition_id"): condition
                    for condition in study.get("conditions", [])
                    if isinstance(condition, dict)
                    and isinstance(condition.get("condition_id"), str)
                },
            )
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    successors: dict[str, str] = {}
    for child in sorted(run_dir.iterdir(), key=lambda path: path.name):
        if child.name == "README.md":
            continue
        if child.is_symlink() or not child.is_dir():
            report.error("RUN_PATH", "runs", "run entries must be directories")
            continue
        run_report, run = validate_run(child)
        report.errors.extend(run_report.errors)
        report.warnings.extend(run_report.warnings)
        if run is None or not run_report.ok:
            continue
        run_error_count = len(report.errors)
        run_id = run.get("run_id")
        if child.name != run_id:
            report.error("RUN_DIRECTORY_ID", "runs", "directory must equal run_id")
        if isinstance(run_id, str):
            if run_id in seen:
                report.error("DUPLICATE_RUN", "runs", "duplicate run_id")
            else:
                seen.add(run_id)
        supersedes = run.get("supersedes_run_id")
        if isinstance(supersedes, str):
            if supersedes in successors:
                report.error(
                    "SUPERSESSION_FANOUT",
                    "runs",
                    "one run cannot have multiple direct successors",
                )
            successors[supersedes] = str(run_id)
        study_ref = run.get("study_ref", {})
        study_record = studies_by_id.get(str(study_ref.get("study_id")))
        taskset_record: dict[str, Any] | None = None
        if study_record is None:
            report.error(
                "RUN_STUDY_REF",
                "RUN.json.study_ref",
                "study_id is not cataloged",
            )
        else:
            study_path, study, conditions_by_id = study_record
            expected_path = study_path.relative_to(root).as_posix()
            if study_ref.get("path") != expected_path:
                report.error(
                    "RUN_STUDY_PATH",
                    "RUN.json.study_ref.path",
                    "does not match cataloged STUDY path",
                )
            if study_ref.get("sha256") != file_sha256(
                study_path,
                report,
                "RUN.json.study_ref.path",
            ):
                report.error(
                    "RUN_STUDY_HASH",
                    "RUN.json.study_ref.sha256",
                    "does not match STUDY bytes",
                )
            selected_condition = conditions_by_id.get(str(run.get("condition_id")))
            if selected_condition is None:
                report.error(
                    "RUN_CONDITION",
                    "RUN.json.condition_id",
                    "is not declared by the study",
                )
            elif run.get("subject", {}).get("system_condition") != selected_condition.get(
                "system_condition"
            ):
                report.error(
                    "RUN_CONDITION_SYSTEM",
                    "RUN.json.subject.system_condition",
                    "must equal the selected STUDY condition system_condition",
                )
            taskset_id = study.get("taskset_ref", {}).get("taskset_id")
            found_taskset = tasksets_by_id.get(str(taskset_id))
            if found_taskset is not None:
                taskset_path, taskset_record = found_taskset
                task_ref = run.get("task_ref", {})
                if task_ref.get("taskset_id") != taskset_id:
                    report.error(
                        "RUN_TASKSET_ID",
                        "RUN.json.task_ref.taskset_id",
                        "must equal STUDY taskset",
                    )
                if task_ref.get("taskset_sha256") != file_sha256(
                    taskset_path,
                    report,
                    "RUN.json.task_ref.taskset_sha256",
                ):
                    report.error(
                        "RUN_TASKSET_HASH",
                        "RUN.json.task_ref.taskset_sha256",
                        "must equal TASKSET bytes",
                    )
                task_matches = [
                    task
                    for task in taskset_record.get("tasks", [])
                    if task.get("task_id") == task_ref.get("task_id")
                ]
                if len(task_matches) != 1:
                    report.error(
                        "RUN_TASK_ID",
                        "RUN.json.task_ref.task_id",
                        "must match one TASKSET task",
                    )
                elif (
                    task_ref.get("task_sha256")
                    != task_matches[0].get("input", {}).get("sha256")
                ):
                    report.error(
                        "RUN_TASK_HASH",
                        "RUN.json.task_ref.task_sha256",
                        "must equal TASKSET task input digest",
                    )
                expected_environment = canonical_sha256(
                    taskset_record.get("environment")
                )
                if (
                    run.get("world_ref", {}).get("environment_sha256")
                    != expected_environment
                ):
                    report.error(
                        "RUN_ENVIRONMENT",
                        "RUN.json.world_ref.environment_sha256",
                        "must equal the canonical TASKSET environment digest",
                    )
        score_path = child / "SCORE.json"
        score = (
            _validate_score(score_path, run, report, taskset_record)
            if score_path.is_symlink() or score_path.exists()
            else None
        )
        if len(report.errors) != run_error_count:
            continue
        study = run.get("study_ref", {})
        subject = run.get("subject", {})
        runtime = run.get("runtime", {})
        summaries.append(
            {
                "study_id": study.get("study_id"),
                "run_id": run_id,
                "run_status": run.get("status"),
                "condition_id": run.get("condition_id"),
                "trial": run.get("trial"),
                "seed": run.get("seed"),
                "system_condition": subject.get("system_condition"),
                "model": runtime.get("model"),
                "runtime": runtime.get("runtime"),
                "subject_identity_sha256": run_report.facts.get(
                    "subject_identity_sha256"
                ),
                "world_ref_sha256": run_report.facts.get("world_ref_sha256"),
                "score_status": "scored" if score is not None else "unscored",
                "outcome_status": score.get("outcome_status") if score else "not-assessed",
                "infrastructure_status": (
                    score.get("infrastructure_status") if score else "not-assessed"
                ),
                "raw_outcome_sha256": (
                    canonical_sha256(score.get("raw_outcome")) if score else None
                ),
                "optional_evidence_status": "not-assessed",
                "provenance_status": "unresolved",
                "direct_comparison_eligible": False,
            }
        )
    for source, target in successors.items():
        if source not in seen:
            report.error("SUPERSESSION_MISSING", "runs", "superseded run is missing")
        cursor = target
        visited = {source}
        while cursor in successors:
            if cursor in visited:
                report.error("SUPERSESSION_CYCLE", "runs", "supersession cycle")
                break
            visited.add(cursor)
            cursor = successors[cursor]
    report.facts["run_count"] = len(summaries)
    report.facts["taskset_count"] = len(tasksets_by_id)
    report.facts["study_count"] = len(studies_by_id)
    return report, summaries


def build_index_documents(summaries: list[dict[str, Any]]) -> tuple[str, str]:
    ordered = sorted(summaries, key=lambda item: (str(item["study_id"]), str(item["run_id"])))
    json_text = json.dumps(
        {"schema_version": INDEX_SCHEMA, "runs": ordered},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    lines = [
        "# Exogenous experiments",
        "",
        "Generated by `tools/exogenous_registry.py build-index`. Do not edit by hand.",
        "",
        "| study | run | status | condition | trial | seed | model | outcome | infrastructure | optional evidence | provenance |",
        "|---|---|---|---|---:|---|---|---|---|---|---|",
    ]
    if not ordered:
        lines.append("| _(none yet)_ | | | | | | | | | | |")
    else:
        for item in ordered:
            cells = [
                item["study_id"],
                item["run_id"],
                item["run_status"],
                item["condition_id"],
                item["trial"],
                item["seed"],
                item["model"],
                item["outcome_status"],
                item["infrastructure_status"],
                item["optional_evidence_status"],
                item["provenance_status"],
            ]
            escaped = [
                str(value).replace("|", "\\|").replace("\n", " ") for value in cells
            ]
            lines.append("| " + " | ".join(escaped) + " |")
    return json_text, "\n".join(lines) + "\n"


def check_append_only(root: Path, base_ref: str, report: Report) -> None:
    paths = subprocess.run(
        ["git", "diff", "--name-status", "--find-renames", base_ref, "--", "exogenous"],
        cwd=root.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    if paths.returncode != 0:
        report.error("BASE_REF", "exogenous", "cannot resolve base ref")
        return
    core = re.compile(
        r"^exogenous/(?:benchmarks/.+/TASKSET\.json|studies/.+/STUDY\.json|runs/.+/(?:RUN|SCORE)\.json)$"
    )
    for line in paths.stdout.splitlines():
        fields = line.split("\t")
        status = fields[0]
        affected = fields[1:]
        if status.startswith(("M", "D", "R")) and any(core.fullmatch(path) for path in affected):
            report.error(
                "APPEND_ONLY",
                "exogenous",
                "published core records may only be added",
            )


def _emit(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(("VALID" if report.ok else "INVALID") + f": {report.subject}")
    for warning in report.warnings:
        print("WARNING " + warning)
    for error in report.errors:
        print("ERROR " + error)
    if report.facts:
        print("FACTS " + json.dumps(report.facts, sort_keys=True))


def command_validate_run(args: argparse.Namespace) -> int:
    report, _ = validate_run(Path(args.path), allow_template=args.allow_template)
    _emit(report, args.json)
    return 0 if report.ok else 1


def command_validate_registry(args: argparse.Namespace) -> int:
    root = Path(args.root)
    method_report, methods = load_method_catalog(Path(args.method_index))
    report, _ = collect_registry(root, method_versions=methods)
    report.errors[:0] = method_report.errors
    report.warnings[:0] = method_report.warnings
    if args.base_ref:
        check_append_only(root, args.base_ref, report)
    else:
        report.warn(
            "APPEND_ONLY_UNCHECKED",
            "exogenous",
            "history immutability was not checked; pass --base-ref",
        )
    _emit(report, args.json)
    return 0 if report.ok else 1


def command_build_index(args: argparse.Namespace) -> int:
    root = Path(args.root)
    method_report, methods = load_method_catalog(Path(args.method_index))
    report, summaries = collect_registry(root, method_versions=methods)
    report.errors[:0] = method_report.errors
    report.warnings[:0] = method_report.warnings
    if args.base_ref:
        check_append_only(root, args.base_ref, report)
    if not report.ok:
        _emit(report, args.json)
        return 1
    json_text, markdown_text = build_index_documents(summaries)
    targets = (
        (root / "registry" / "INDEX.json", json_text),
        (root / "registry" / "EXPERIMENTS.md", markdown_text),
    )
    if args.check:
        for path, expected in targets:
            try:
                actual = path.read_text(encoding="utf-8")
            except OSError:
                actual = ""
            if actual != expected:
                report.error("INDEX_STALE", path.name, "generated index is stale")
    else:
        for path, expected in targets:
            path.write_text(expected, encoding="utf-8")
    _emit(report, args.json)
    return 0 if report.ok else 1


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_run_parser = subparsers.add_parser("validate-run")
    validate_run_parser.add_argument("path")
    validate_run_parser.add_argument("--allow-template", action="store_true")
    validate_run_parser.add_argument("--json", action="store_true")
    validate_run_parser.set_defaults(func=command_validate_run)
    for name, function in (
        ("validate-registry", command_validate_registry),
        ("build-index", command_build_index),
    ):
        child = subparsers.add_parser(name)
        child.add_argument("--root", default="exogenous")
        child.add_argument("--method-index", default="method-paper/VERSIONS.json")
        child.add_argument("--base-ref")
        child.add_argument("--json", action="store_true")
        if name == "build-index":
            child.add_argument("--check", action="store_true")
        child.set_defaults(func=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"INVALID: validator internal error: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
