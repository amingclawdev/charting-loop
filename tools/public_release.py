#!/usr/bin/env python3
"""Validate public-release custody records and scan an exact Git release surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


REGISTRY_SCHEMA = "charting-loop/public-release-registry/v1"
PUBLIC_RESULT_SCHEMA = "charting-loop/public-result-summary/v1"
PUBLIC_RESULT_EVIDENCE_SCHEMA = "charting-loop/public-result-evidence/v2"
CAUSAL_EVIDENCE_SCHEMA = "charting-loop/public-causal-evidence-matrix/v1"
OBSERVABLE_LINEAGE_SCHEMA = "charting-loop/observable-lineage-receipt/v1"
EXECUTION_AMENDMENT_SCHEMA = "charting-loop/public-execution-amendment/v1"
ATTEMPT_DISPOSITION_SCHEMA = "charting-loop/public-attempt-disposition-ledger/v1"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{2,127}$")
SAFE_REF_RE = re.compile(r"^(?:HEAD|[0-9a-f]{40}|refs/heads/[A-Za-z0-9._/-]+)$")
BRANCH_REF_RE = re.compile(
    r"^refs/heads/(?:(?:main)|(?:corridor/[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/"
    r"[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/"
    r"[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*)|"
    r"(?:results/[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/"
    r"[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/"
    r"[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*/[a-z0-9][a-z0-9.-]*))$"
)
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DEFAULT_MAX_BLOB_BYTES = 1024 * 1024

EXPECTED_NAMESPACES = [
    {
        "artifact_kind": "custody",
        "default_visibility": "public-summary",
        "template": "main",
    },
    {
        "artifact_kind": "corridor",
        "default_visibility": "embargoed-solution-bearing",
        "template": "corridor/{dataset}/{release}/{taskset}/{task}/{construction}/{build}/{candidate}/{revision}",
    },
    {
        "artifact_kind": "results",
        "default_visibility": "public-summary",
        "template": "results/{dataset}/{release}/{taskset}/{task}/{study}/{run}/{arm}/{result-release}",
    },
]
EXPECTED_PUBLIC_CLASSES = [
    "citation",
    "digest",
    "index",
    "license",
    "method",
    "protocol",
    "summary",
    "validation-tool",
]
EXPECTED_RESTRICTED_CLASSES = [
    "database",
    "detailed-agent-log",
    "hidden-evaluator",
    "internal-git-history",
    "raw-session",
    "solution-code",
    "trajectory",
    "writeback-sql",
]
REGISTRY_KEYS = {
    "branch_namespaces",
    "public_artifact_classes",
    "release_policy",
    "releases",
    "restricted_artifact_classes",
    "schema_version",
}
POLICY_KEYS = {
    "append_only",
    "claim_default",
    "default_visibility",
    "exact_service_replay",
    "method_transfer_replication",
    "publication_gate",
}
RELEASE_KEYS = {
    "artifact_manifest_sha256",
    "artifact_manifest_path",
    "branch_kind",
    "branch_ref",
    "claims",
    "commit_sha",
    "contamination_facts",
    "contamination_status",
    "identity",
    "outcomes",
    "publication_evidence",
    "released_at",
    "release_id",
    "sealed_artifacts",
    "sequence",
    "supersedes_release_id",
    "tree_sha",
    "visibility",
}
IDENTITY_KEYS = {
    "arm",
    "attempt_id",
    "benchmark_dataset",
    "benchmark_release",
    "build_id",
    "candidate_id",
    "candidate_revision",
    "construction_id",
    "launch_id",
    "method_version_id",
    "protocol_id",
    "result_release",
    "run_id",
    "study_id",
    "task_id",
    "taskset_id",
}
CONTAMINATION_KEYS = {
    "counting_disposition",
    "evaluated_model",
    "local_artifact_published_at",
    "local_artifact_visibility",
    "method_attribution",
    "model_knowledge_cutoff",
    "network_policy",
    "runtime_identity",
    "training_ingestion",
    "upstream_oracle_published_at",
    "upstream_oracle_visibility",
}
OUTCOME_KEYS = {"blocked", "fail", "invalid", "pass", "timeout", "total", "unscored"}
SEALED_ARTIFACT_KEYS = {
    "artifact_id",
    "custody",
    "license_status",
    "media_type",
    "provenance",
    "release_trigger",
    "sha256",
    "size_bytes",
    "source_ref",
}
PUBLICATION_EVIDENCE_KEYS = {"maintainer_clearance_ref", "retirement_evidence_ref"}
ALLOWED_VISIBILITY = {
    "public-summary",
    "embargoed-solution-bearing",
    "restricted-on-request",
    "public-after-retirement-or-maintainer-clearance",
}
ALLOWED_BRANCH_KIND = {"custody", "corridor", "results"}
ALLOWED_CONTAMINATION = {
    "active-task-embargoed",
    "not-assessed",
    "retired-task",
    "maintainer-approved",
}
ALLOWED_CLAIMS = {"descriptive", "engineering", "method-transfer", "no-effect-claim"}
ALLOWED_ORACLE_VISIBILITY = {"not-public", "public-after-run", "public-before-run", "unknown"}
ALLOWED_LOCAL_VISIBILITY = {"controlled", "private", "public"}
ALLOWED_NETWORK_POLICY = {"allowlisted", "none", "open", "unknown"}
ALLOWED_COUNTING = {"counted", "excluded-prospectively", "incomplete", "invalid-infrastructure", "unscored"}
ALLOWED_METHOD_ATTRIBUTION = {
    "no-method",
    "other-declared-method",
    "paper2-current-v2",
    "charting-loop-method-v4",
    "charting-loop-method-v5",
}
ALLOWED_LICENSE_STATUS = {"cleared", "not-assessed", "restricted", "upstream-reference-only"}

PUBLIC_RESULT_V1_KEYS = {
    "condition",
    "identity",
    "interpretation",
    "official_evaluation",
    "process",
    "public_summary",
    "release_id",
    "schema_version",
    "sealed_artifacts",
    "source_custody",
}
PUBLIC_RESULT_V2_KEYS = PUBLIC_RESULT_V1_KEYS | {
    "attempt_disposition",
    "causal_evidence",
    "execution_amendment",
    "observable_lineage",
}
PUBLIC_RESULT_CONDITION_KEYS = {
    "corridor_access",
    "corridor_observably_used",
    "label",
    "plain_language",
}
PUBLIC_RESULT_INTERPRETATION_KEYS = {
    "causal_claim",
    "distinct_benchmark_tasks",
    "evidence_class",
    "leaderboard_claim",
    "mechanism_summary",
    "multi_task_evidence",
}
PUBLIC_RESULT_OFFICIAL_KEYS = {"checks_passed", "checks_total", "outcome", "reward"}
PUBLIC_RESULT_PROCESS_KEYS = {
    "database_changed_after_qa",
    "evaluation_mode",
    "post_repair_qa_performed",
    "qa_outcome",
    "repair_attempts_executed",
    "repair_launch_attempted",
    "repair_status",
}
PUBLIC_RESULT_SUMMARY_KEYS = {"path", "sha256", "size_bytes"}
PUBLIC_RESULT_SOURCE_CUSTODY_KEYS = {
    "builder_service_commit",
    "builder_service_tree",
    "controlled_result_commit",
    "controlled_result_path",
    "controlled_result_tree",
    "method_source_commit",
    "official_task_committed_at",
    "official_task_source_commit",
    "official_task_url",
}
CAUSAL_EVIDENCE_KEYS = {"arm", "attempt_id", "entries", "schema_version"}
CAUSAL_EVIDENCE_ENTRY_KEYS = {
    "claim",
    "controlled_source_refs",
    "evidence_id",
    "public_refs",
    "reason",
    "status",
}
CAUSAL_EVIDENCE_IDS = [f"E{index}" for index in range(1, 8)]
CAUSAL_EVIDENCE_STATUSES = {
    "declared-only",
    "digest-only-commitment",
    "independently-verifiable",
    "public-event-receipt",
    "unavailable",
    "unsupported-inference",
}
OBSERVABLE_LINEAGE_KEYS = {
    "arm",
    "attempt_id",
    "events",
    "official_evaluator",
    "prescore_world",
    "redaction",
    "schema_version",
    "service_revision",
    "worker_log",
    "writebacks",
}
LINEAGE_SERVICE_KEYS = {"commit", "status", "tree"}
LINEAGE_WORKER_LOG_KEYS = {
    "agent_message_count",
    "command_count",
    "hidden_reasoning_event_count",
    "reasoning_effort",
    "sha256",
    "size_bytes",
    "source_ref",
}
LINEAGE_EVENT_KEYS = {
    "event_id",
    "exit_code",
    "kind",
    "output_sha256",
    "public_summary",
    "source_ref",
    "status",
}
LINEAGE_WRITEBACK_KEYS = {"sha256", "size_bytes", "source_ref", "system"}
LINEAGE_PRESCORE_KEYS = {"capture_sha256", "image_sha256", "source_ref"}
LINEAGE_EVALUATOR_KEYS = {"checks_passed", "checks_total", "receipt_sha256", "source_ref"}
LINEAGE_REDACTION_KEYS = {"excluded", "full_log_public", "policy"}
EXECUTION_AMENDMENT_KEYS = {
    "amendment_reason",
    "arm",
    "attempt_id",
    "frozen_study_overwritten",
    "qa_repair_order",
    "schema_version",
    "seed_retry",
    "service_revision",
    "source_refs",
    "timing",
    "tools_runtime",
    "usage",
    "prescore_world",
}
EXECUTION_TOOLS_RUNTIME_KEYS = {
    "agent_message_count",
    "codex_version",
    "command_count",
    "model",
    "network_policy",
    "reasoning_effort",
    "runtime_identity",
}
EXECUTION_TIMING_KEYS = {"finished_at", "reason", "started_at", "status"}
EXECUTION_USAGE_KEYS = {
    "cached_input_tokens",
    "input_tokens",
    "output_tokens",
    "reason",
    "status",
}
EXECUTION_SEED_RETRY_KEYS = {
    "reason",
    "repair_attempts_executed",
    "retry_count",
    "retry_status",
    "seed",
    "seed_status",
}
EXECUTION_QA_REPAIR_KEYS = {
    "post_repair_qa_performed",
    "qa_outcome",
    "repair_attempts_executed",
    "repair_launch_attempted",
    "repair_status",
}
ATTEMPT_DISPOSITION_KEYS = {
    "current_attempt",
    "invalid_predecessors",
    "schema_version",
}
ATTEMPT_CURRENT_KEYS = {"attempt_id", "counted", "reason", "run_id", "status"}
ATTEMPT_INVALID_KEYS = {
    "attempt_label",
    "counted",
    "public_record_status",
    "reason",
    "source_ref",
    "status",
    "waiver_reason",
}

ALLOWED_TEXT_SUFFIXES = {
    ".bib",
    ".cff",
    ".css",
    ".csv",
    ".gitignore",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
ALLOWED_EXTENSIONLESS = {".gitignore", "LICENSE", "NOTICE"}
ARCHIVE_SUFFIXES = {
    ".7z",
    ".bz2",
    ".gz",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
}
RESTRICTED_SUFFIXES = {
    ".bundle",
    ".db",
    ".har",
    ".idx",
    ".log",
    ".pack",
    ".rev",
    ".sql",
    ".sqlite",
    ".sqlite3",
}
LOCAL_PATH_PATTERNS = (
    re.compile(rb"/Users/[A-Za-z0-9._-]+/"),
    re.compile(rb"/home/[A-Za-z0-9._-]+/"),
    re.compile(rb"/var/folders/[A-Za-z0-9._-]+/"),
    re.compile(rb"[A-Za-z]:\\\\Users\\\\[A-Za-z0-9._-]+\\\\"),
)
TOKEN_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9])"),
    re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"),
    re.compile(rb"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"),
    re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
)
SECRET_ASSIGNMENT_RE = re.compile(
    rb'"(?:access_token|api_key|password|refresh_token|secret_key|session_token)"\s*:\s*"([^"\r\n]+)"',
    re.IGNORECASE,
)
HIDDEN_REASONING_RE = re.compile(
    rb'(?:"(?:chain_of_thought|reasoning_content|hidden_reasoning)"\s*:|'
    + b"<"
    + b"analysis>"
    + b")",
    re.IGNORECASE,
)


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
        value = f"{code} {location}: {message}"
        if value not in self.errors:
            self.errors.append(value)

    def warn(self, code: str, location: str, message: str) -> None:
        value = f"{code} {location}: {message}"
        if value not in self.warnings:
            self.warnings.append(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": self.errors,
            "facts": self.facts,
            "ok": self.ok,
            "subject": self.subject,
            "warnings": self.warnings,
        }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, report: Report) -> dict[str, Any] | None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        report.error("REGISTRY_JSON", str(path), f"cannot load strict JSON ({type(exc).__name__})")
        return None
    return _load_json_bytes(raw, report, str(path))


def _load_json_bytes(raw: bytes, report: Report, location: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        report.error("REGISTRY_JSON", location, f"cannot load strict JSON ({type(exc).__name__})")
        return None
    if not isinstance(value, dict):
        report.error("REGISTRY_JSON", location, "top level must be an object")
        return None
    return value


def _closed_keys(value: Any, expected: set[str], report: Report, location: str) -> bool:
    if not isinstance(value, dict):
        report.error("REGISTRY_SHAPE", location, "must be an object")
        return False
    actual = set(value)
    if actual != expected:
        report.error(
            "REGISTRY_FIELDS",
            location,
            f"expected {sorted(expected)}, got {sorted(actual)}",
        )
        return False
    return True


def _valid_slug(value: Any) -> bool:
    return isinstance(value, str) and RELEASE_ID_RE.fullmatch(value) is not None


def _validate_identity(
    value: Any,
    *,
    branch_kind: Any,
    branch_ref: Any,
    location: str,
    report: Report,
) -> str | None:
    if branch_kind == "custody":
        if value is not None:
            report.error("RELEASE_IDENTITY", location, "custody identity must be null")
        return None
    if not _closed_keys(value, IDENTITY_KEYS, report, location):
        return None
    for key, item in value.items():
        if item is not None and not _valid_slug(item):
            report.error("RELEASE_IDENTITY", f"{location}.{key}", "must be null or a stable lowercase slug")
    common = {
        "benchmark_dataset",
        "benchmark_release",
        "method_version_id",
        "protocol_id",
        "task_id",
        "taskset_id",
    }
    corridor = {"build_id", "candidate_id", "candidate_revision", "construction_id"}
    results = {"arm", "attempt_id", "launch_id", "result_release", "run_id", "study_id"}
    required = common | (corridor if branch_kind == "corridor" else results)
    for key in sorted(required):
        if not _valid_slug(value.get(key)):
            report.error("RELEASE_IDENTITY", f"{location}.{key}", "is required for this branch kind")
    if isinstance(branch_ref, str) and all(_valid_slug(value.get(key)) for key in required):
        if branch_kind == "corridor":
            expected = (
                "refs/heads/corridor/{benchmark_dataset}/{benchmark_release}/{taskset_id}/"
                "{task_id}/{construction_id}/{build_id}/{candidate_id}/{candidate_revision}"
            ).format(**value)
        else:
            expected = (
                "refs/heads/results/{benchmark_dataset}/{benchmark_release}/{taskset_id}/"
                "{task_id}/{study_id}/{run_id}/{arm}/{result_release}"
            ).format(**value)
        if branch_ref != expected:
            report.error("RELEASE_IDENTITY_REF", location, "branch_ref does not project the identity locator")
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _validate_contamination(value: Any, *, location: str, report: Report) -> None:
    if not _closed_keys(value, CONTAMINATION_KEYS, report, location):
        return
    if value.get("upstream_oracle_visibility") not in ALLOWED_ORACLE_VISIBILITY:
        report.error("RELEASE_CONTAMINATION", location, "invalid upstream_oracle_visibility")
    if value.get("local_artifact_visibility") not in ALLOWED_LOCAL_VISIBILITY:
        report.error("RELEASE_CONTAMINATION", location, "invalid local_artifact_visibility")
    if value.get("network_policy") not in ALLOWED_NETWORK_POLICY:
        report.error("RELEASE_CONTAMINATION", location, "invalid network_policy")
    if value.get("counting_disposition") not in ALLOWED_COUNTING:
        report.error("RELEASE_CONTAMINATION", location, "invalid counting_disposition")
    if value.get("method_attribution") not in ALLOWED_METHOD_ATTRIBUTION:
        report.error("RELEASE_CONTAMINATION", location, "invalid method_attribution")
    if value.get("training_ingestion") != "not-inferred":
        report.error("RELEASE_CONTAMINATION", location, "training_ingestion must remain not-inferred")
    for key in ("evaluated_model", "model_knowledge_cutoff", "runtime_identity"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            report.error("RELEASE_CONTAMINATION", f"{location}.{key}", "must be a non-empty declared value")
    for key in ("upstream_oracle_published_at", "local_artifact_published_at"):
        timestamp = value.get(key)
        if timestamp is not None and (not isinstance(timestamp, str) or not UTC_RE.fullmatch(timestamp)):
            report.error("RELEASE_CONTAMINATION", f"{location}.{key}", "must be null or second-precision UTC")
    if value.get("upstream_oracle_visibility") in {"public-before-run", "public-after-run"} and value.get(
        "upstream_oracle_published_at"
    ) is None:
        report.error("RELEASE_CONTAMINATION", location, "public upstream oracle requires publication time")
    if value.get("local_artifact_visibility") == "public" and value.get(
        "local_artifact_published_at"
    ) is None:
        report.error("RELEASE_CONTAMINATION", location, "public local artifact requires publication time")


def _validate_outcomes(value: Any, *, required: bool, location: str, report: Report) -> None:
    if not required and value is None:
        return
    if not _closed_keys(value, OUTCOME_KEYS, report, location):
        return
    for key in OUTCOME_KEYS:
        if not isinstance(value.get(key), int) or isinstance(value.get(key), bool) or value[key] < 0:
            report.error("RELEASE_OUTCOMES", f"{location}.{key}", "must be a non-negative integer")
    if all(isinstance(value.get(key), int) and not isinstance(value.get(key), bool) for key in OUTCOME_KEYS):
        subtotal = sum(value[key] for key in OUTCOME_KEYS if key != "total")
        if value["total"] != subtotal or (required and value["total"] == 0):
            report.error("RELEASE_OUTCOMES", location, "total must equal all six explicit outcome counts and be nonzero")


def _validate_sealed_artifacts(value: Any, *, location: str, report: Report) -> None:
    if not isinstance(value, list):
        report.error("RELEASE_SEALED", location, "must be an array")
        return
    known: set[str] = set()
    for index, artifact in enumerate(value):
        item_location = f"{location}[{index}]"
        if not _closed_keys(artifact, SEALED_ARTIFACT_KEYS, report, item_location):
            continue
        artifact_id = artifact.get("artifact_id")
        if not _valid_slug(artifact_id) or artifact_id in known:
            report.error("RELEASE_SEALED", item_location, "artifact_id must be a unique stable slug")
        else:
            known.add(artifact_id)
        if not isinstance(artifact.get("sha256"), str) or not SHA256_RE.fullmatch(artifact["sha256"]):
            report.error("RELEASE_SEALED", item_location, "sha256 must be sha256:<64 hex>")
        if not isinstance(artifact.get("size_bytes"), int) or isinstance(artifact.get("size_bytes"), bool) or artifact[
            "size_bytes"
        ] < 0:
            report.error("RELEASE_SEALED", item_location, "size_bytes must be a non-negative integer")
        if artifact.get("license_status") not in ALLOWED_LICENSE_STATUS:
            report.error("RELEASE_SEALED", item_location, "invalid license_status")
        for key in ("custody", "media_type", "provenance", "release_trigger", "source_ref"):
            if not isinstance(artifact.get(key), str) or not artifact[key].strip():
                report.error("RELEASE_SEALED", f"{item_location}.{key}", "must be non-empty")


def _validate_publication_evidence(value: Any, *, location: str, report: Report) -> bool:
    if not _closed_keys(value, PUBLICATION_EVIDENCE_KEYS, report, location):
        return False
    valid = True
    for key in PUBLICATION_EVIDENCE_KEYS:
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or not item.strip()):
            report.error("RELEASE_PUBLICATION_EVIDENCE", f"{location}.{key}", "must be null or non-empty")
            valid = False
    return valid


def _git(repo: Path, args: list[str], *, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _validate_release_entry(
    entry: Any,
    index: int,
    known_ids: set[str],
    known_refs: set[str],
    known_identities: set[str],
    report: Report,
) -> None:
    location = f"releases[{index}]"
    if not _closed_keys(entry, RELEASE_KEYS, report, location):
        return
    if entry.get("sequence") != index + 1:
        report.error("RELEASE_SEQUENCE", location, "sequence must be contiguous and one-based")
    release_id = entry.get("release_id")
    if not isinstance(release_id, str) or not RELEASE_ID_RE.fullmatch(release_id):
        report.error("RELEASE_ID", location, "release_id must be a stable lowercase slug")
    elif release_id in known_ids:
        report.error("RELEASE_ID", location, "release_id must be unique")
    else:
        known_ids.add(release_id)
    branch_kind = entry.get("branch_kind")
    if branch_kind not in ALLOWED_BRANCH_KIND:
        report.error("RELEASE_BRANCH_KIND", location, "invalid branch_kind")
    branch_ref = entry.get("branch_ref")
    if not isinstance(branch_ref, str) or not BRANCH_REF_RE.fullmatch(branch_ref):
        report.error("RELEASE_BRANCH_REF", location, "branch_ref is outside the deterministic namespaces")
    elif subprocess.run(
        ["git", "check-ref-format", branch_ref],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        report.error("RELEASE_BRANCH_REF", location, "branch_ref is not a valid Git ref")
    elif branch_kind == "custody" and branch_ref != "refs/heads/main":
        report.error("RELEASE_BRANCH_REF", location, "custody releases must use refs/heads/main")
    elif branch_kind in {"corridor", "results"} and not branch_ref.startswith(
        f"refs/heads/{branch_kind}/"
    ):
        report.error("RELEASE_BRANCH_REF", location, "branch_ref does not match branch_kind")
    if isinstance(branch_ref, str):
        if branch_ref in known_refs:
            report.error("RELEASE_NAMESPACE_COLLISION", location, "branch_ref must be unique")
        else:
            known_refs.add(branch_ref)
    identity_key = _validate_identity(
        entry.get("identity"),
        branch_kind=branch_kind,
        branch_ref=branch_ref,
        location=f"{location}.identity",
        report=report,
    )
    if identity_key is not None:
        collision_key = f"{branch_kind}:{identity_key}"
        if collision_key in known_identities:
            report.error("RELEASE_NAMESPACE_COLLISION", location, "full experiment identity must be unique")
        else:
            known_identities.add(collision_key)
    for key in ("commit_sha", "tree_sha"):
        if not isinstance(entry.get(key), str) or not COMMIT_RE.fullmatch(entry[key]):
            report.error("RELEASE_GIT_ID", f"{location}.{key}", "must be a full lowercase Git object id")
    if not isinstance(entry.get("artifact_manifest_sha256"), str) or not SHA256_RE.fullmatch(
        entry["artifact_manifest_sha256"]
    ):
        report.error("RELEASE_DIGEST", location, "artifact_manifest_sha256 must be sha256:<64 hex>")
    manifest_path = entry.get("artifact_manifest_path")
    if (
        not isinstance(manifest_path, str)
        or not manifest_path
        or PurePosixPath(manifest_path).is_absolute()
        or ".." in PurePosixPath(manifest_path).parts
        or "\\" in manifest_path
    ):
        report.error("RELEASE_MANIFEST", location, "artifact_manifest_path must be normalized repository-relative POSIX")
    visibility = entry.get("visibility")
    if visibility not in ALLOWED_VISIBILITY:
        report.error("RELEASE_VISIBILITY", location, "invalid visibility")
    if entry.get("contamination_status") not in ALLOWED_CONTAMINATION:
        report.error("RELEASE_CONTAMINATION", location, "invalid contamination_status")
    contamination = entry.get("contamination_facts")
    if branch_kind == "custody":
        if contamination is not None:
            report.error("RELEASE_CONTAMINATION", location, "custody contamination_facts must be null")
    else:
        _validate_contamination(contamination, location=f"{location}.contamination_facts", report=report)
    _validate_outcomes(
        entry.get("outcomes"),
        required=branch_kind == "results",
        location=f"{location}.outcomes",
        report=report,
    )
    _validate_sealed_artifacts(entry.get("sealed_artifacts"), location=f"{location}.sealed_artifacts", report=report)
    publication_evidence = entry.get("publication_evidence")
    publication_evidence_valid = _validate_publication_evidence(
        publication_evidence,
        location=f"{location}.publication_evidence",
        report=report,
    )
    claims = entry.get("claims")
    if (
        not isinstance(claims, list)
        or not claims
        or any(not isinstance(item, str) for item in claims)
        or len(set(claims)) != len(claims)
        or any(item not in ALLOWED_CLAIMS for item in claims)
    ):
        report.error("RELEASE_CLAIMS", location, "claims must be a non-empty closed claim list")
    if not isinstance(entry.get("released_at"), str) or not UTC_RE.fullmatch(entry["released_at"]):
        report.error("RELEASE_TIME", location, "released_at must be second-precision UTC")
    supersedes = entry.get("supersedes_release_id")
    if supersedes is not None and (not isinstance(supersedes, str) or supersedes not in known_ids):
        report.error("RELEASE_SUPERSEDES", location, "supersedes_release_id must name an earlier row")
    if entry.get("visibility") == "public-after-retirement-or-maintainer-clearance" and entry.get(
        "contamination_status"
    ) not in {"maintainer-approved", "retired-task"}:
        report.error("RELEASE_VISIBILITY", location, "public-after visibility requires retirement or maintainer clearance")
    if entry.get("visibility") == "public-after-retirement-or-maintainer-clearance" and publication_evidence_valid:
        expected_key = (
            "maintainer_clearance_ref"
            if entry.get("contamination_status") == "maintainer-approved"
            else "retirement_evidence_ref"
        )
        if not publication_evidence.get(expected_key):
            report.error("RELEASE_PUBLICATION_EVIDENCE", location, f"public-after visibility requires {expected_key}")


def _validate_release_authority(
    entry: dict[str, Any],
    index: int,
    *,
    repo: Path,
    base_commit: str | None,
    report: Report,
) -> None:
    location = f"releases[{index}]"
    commit = entry.get("commit_sha")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        return
    resolved = _git(repo, ["rev-parse", "--verify", f"{commit}^{{commit}}"])
    if resolved.returncode != 0 or resolved.stdout.decode().strip() != commit:
        report.error("RELEASE_AUTHORITY_COMMIT", location, "commit_sha is not an exact repository commit")
        return
    tree = _git(repo, ["rev-parse", f"{commit}^{{tree}}"])
    expected_tree = tree.stdout.decode().strip() if tree.returncode == 0 else ""
    if entry.get("tree_sha") != expected_tree:
        report.error("RELEASE_AUTHORITY_TREE", location, "tree_sha does not equal commit^{tree}")
    branch_ref = entry.get("branch_ref")
    if isinstance(branch_ref, str):
        candidate_refs = [branch_ref]
        if branch_ref.startswith("refs/heads/"):
            candidate_refs.append(
                "refs/remotes/origin/" + branch_ref.removeprefix("refs/heads/")
            )
        resolved_refs: dict[str, str] = {}
        for candidate_ref in candidate_refs:
            ref = _git(
                repo,
                ["rev-parse", "--verify", f"{candidate_ref}^{{commit}}"],
            )
            if ref.returncode == 0:
                resolved_refs[candidate_ref] = ref.stdout.decode().strip()
        if len(set(resolved_refs.values())) > 1:
            report.error(
                "RELEASE_AUTHORITY_REF_DIVERGED",
                location,
                "local and origin-tracking branch locators resolve to different commits",
            )
        elif commit not in resolved_refs.values():
            report.error(
                "RELEASE_AUTHORITY_REF",
                location,
                "neither the local nor origin-tracking branch locator resolves to commit_sha",
            )
    manifest_path = entry.get("artifact_manifest_path")
    if isinstance(manifest_path, str) and manifest_path:
        manifest = _git(repo, ["show", f"{commit}:{manifest_path}"])
        if manifest.returncode != 0:
            report.error("RELEASE_AUTHORITY_MANIFEST", location, "manifest is absent from the recorded commit")
        else:
            actual_digest = "sha256:" + hashlib.sha256(manifest.stdout).hexdigest()
            if entry.get("artifact_manifest_sha256") != actual_digest:
                report.error("RELEASE_AUTHORITY_MANIFEST", location, "manifest digest does not match committed bytes")
            if manifest_path.startswith("public/results/"):
                _validate_public_result_manifest(
                    entry,
                    manifest.stdout,
                    manifest_path=manifest_path,
                    commit=commit,
                    repo=repo,
                    location=location,
                    report=report,
                )
    if base_commit is not None:
        ancestry = _git(repo, ["merge-base", "--is-ancestor", base_commit, commit])
        if ancestry.returncode != 0:
            report.error("RELEASE_AUTHORITY_ANCESTRY", location, "release commit is not descended from base_ref")


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_negative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_causal_evidence(
    value: Any,
    *,
    identity: Any,
    location: str,
    report: Report,
) -> None:
    if not _closed_keys(value, CAUSAL_EVIDENCE_KEYS, report, location):
        return
    if value.get("schema_version") != CAUSAL_EVIDENCE_SCHEMA:
        report.error("PUBLIC_CAUSAL_EVIDENCE", location, "invalid causal-evidence schema")
    expected_attempt = identity.get("attempt_id") if isinstance(identity, dict) else None
    expected_arm = identity.get("arm") if isinstance(identity, dict) else None
    if value.get("attempt_id") != expected_attempt or value.get("arm") != expected_arm:
        report.error("PUBLIC_CAUSAL_EVIDENCE", location, "attempt_id and arm must join the manifest identity")
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) != len(CAUSAL_EVIDENCE_IDS):
        report.error("PUBLIC_CAUSAL_EVIDENCE", f"{location}.entries", "must contain exactly E1 through E7")
        return
    observed_ids: list[Any] = []
    for index, item in enumerate(entries):
        item_location = f"{location}.entries[{index}]"
        if not _closed_keys(item, CAUSAL_EVIDENCE_ENTRY_KEYS, report, item_location):
            continue
        observed_ids.append(item.get("evidence_id"))
        if item.get("status") not in CAUSAL_EVIDENCE_STATUSES:
            report.error("PUBLIC_CAUSAL_EVIDENCE", f"{item_location}.status", "invalid evidence status")
        for key in ("claim", "reason"):
            if not _non_empty_string(item.get(key)):
                report.error("PUBLIC_CAUSAL_EVIDENCE", f"{item_location}.{key}", "must be non-empty")
        for key in ("public_refs", "controlled_source_refs"):
            refs = item.get(key)
            if not isinstance(refs, list) or any(not _non_empty_string(ref) for ref in refs):
                report.error("PUBLIC_CAUSAL_EVIDENCE", f"{item_location}.{key}", "must be an array of refs")
        if item.get("status") in {"unavailable", "unsupported-inference"} and item.get("public_refs"):
            report.error(
                "PUBLIC_CAUSAL_EVIDENCE",
                item_location,
                "unavailable or unsupported evidence must not carry a PASS-shaped public ref",
            )
    if observed_ids != CAUSAL_EVIDENCE_IDS:
        report.error("PUBLIC_CAUSAL_EVIDENCE", f"{location}.entries", "evidence ids must be ordered E1 through E7")


def _validate_observable_lineage(
    value: Any,
    *,
    identity: Any,
    source_custody: Any,
    official: Any,
    location: str,
    report: Report,
) -> None:
    if not _closed_keys(value, OBSERVABLE_LINEAGE_KEYS, report, location):
        return
    if value.get("schema_version") != OBSERVABLE_LINEAGE_SCHEMA:
        report.error("PUBLIC_OBSERVABLE_LINEAGE", location, "invalid observable-lineage schema")
    expected_attempt = identity.get("attempt_id") if isinstance(identity, dict) else None
    expected_arm = identity.get("arm") if isinstance(identity, dict) else None
    if value.get("attempt_id") != expected_attempt or value.get("arm") != expected_arm:
        report.error("PUBLIC_OBSERVABLE_LINEAGE", location, "attempt_id and arm must join the manifest identity")

    service = value.get("service_revision")
    if _closed_keys(service, LINEAGE_SERVICE_KEYS, report, f"{location}.service_revision"):
        if expected_arm == "treatment":
            if service.get("status") != "frozen-and-consumed":
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.service_revision.status", "invalid Treatment status")
            if not isinstance(source_custody, dict) or (
                service.get("commit") != source_custody.get("builder_service_commit")
                or service.get("tree") != source_custody.get("builder_service_tree")
            ):
                report.error("PUBLIC_OBSERVABLE_LINEAGE_JOIN", f"{location}.service_revision", "service identity is not joined to source custody")
        elif service != {"commit": None, "status": "not-available-to-control", "tree": None}:
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.service_revision", "Control must record no service access")

    worker_log = value.get("worker_log")
    if _closed_keys(worker_log, LINEAGE_WORKER_LOG_KEYS, report, f"{location}.worker_log"):
        if not isinstance(worker_log.get("sha256"), str) or not SHA256_RE.fullmatch(worker_log["sha256"]):
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.worker_log.sha256", "invalid digest")
        for key in ("size_bytes", "command_count", "agent_message_count", "hidden_reasoning_event_count"):
            if not _non_negative_integer(worker_log.get(key)):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.worker_log.{key}", "must be non-negative integer")
        if worker_log.get("reasoning_effort") not in {"low", "medium", "high", "xhigh"}:
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.worker_log.reasoning_effort", "must be a declared runtime effort")
        if worker_log.get("hidden_reasoning_event_count") != 0:
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.worker_log", "public source must report zero hidden-reasoning events")
        if not _non_empty_string(worker_log.get("source_ref")):
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.worker_log.source_ref", "must be non-empty")

    events = value.get("events")
    known_event_ids: set[str] = set()
    if not isinstance(events, list) or not events:
        report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.events", "must contain observable event receipts")
    else:
        for index, event in enumerate(events):
            event_location = f"{location}.events[{index}]"
            if not _closed_keys(event, LINEAGE_EVENT_KEYS, report, event_location):
                continue
            event_id = event.get("event_id")
            if not _non_empty_string(event_id) or event_id in known_event_ids:
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{event_location}.event_id", "must be a unique event id")
            else:
                known_event_ids.add(event_id)
            if event.get("status") not in {"failed", "observed", "succeeded"}:
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{event_location}.status", "invalid event status")
            if not isinstance(event.get("exit_code"), int) or isinstance(event.get("exit_code"), bool):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{event_location}.exit_code", "must be an integer")
            if not isinstance(event.get("output_sha256"), str) or not SHA256_RE.fullmatch(event["output_sha256"]):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{event_location}.output_sha256", "invalid digest")
            for key in ("kind", "public_summary", "source_ref"):
                if not _non_empty_string(event.get(key)):
                    report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{event_location}.{key}", "must be non-empty")

    writebacks = value.get("writebacks")
    systems: list[Any] = []
    if not isinstance(writebacks, list) or len(writebacks) != 3:
        report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.writebacks", "must bind ERP, MES, and WMS")
    else:
        for index, receipt in enumerate(writebacks):
            receipt_location = f"{location}.writebacks[{index}]"
            if not _closed_keys(receipt, LINEAGE_WRITEBACK_KEYS, report, receipt_location):
                continue
            systems.append(receipt.get("system"))
            if not isinstance(receipt.get("sha256"), str) or not SHA256_RE.fullmatch(receipt["sha256"]):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{receipt_location}.sha256", "invalid digest")
            if not _non_negative_integer(receipt.get("size_bytes")):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{receipt_location}.size_bytes", "must be non-negative integer")
            if not _non_empty_string(receipt.get("source_ref")):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{receipt_location}.source_ref", "must be non-empty")
        if systems != ["erp", "mes", "wms"]:
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.writebacks", "systems must be ordered ERP, MES, WMS")

    prescore = value.get("prescore_world")
    if _closed_keys(prescore, LINEAGE_PRESCORE_KEYS, report, f"{location}.prescore_world"):
        for key in ("capture_sha256", "image_sha256"):
            if not isinstance(prescore.get(key), str) or not SHA256_RE.fullmatch(prescore[key]):
                report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.prescore_world.{key}", "invalid digest")
        if not _non_empty_string(prescore.get("source_ref")):
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.prescore_world.source_ref", "must be non-empty")

    evaluator = value.get("official_evaluator")
    if _closed_keys(evaluator, LINEAGE_EVALUATOR_KEYS, report, f"{location}.official_evaluator"):
        if not isinstance(evaluator.get("receipt_sha256"), str) or not SHA256_RE.fullmatch(evaluator["receipt_sha256"]):
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.official_evaluator.receipt_sha256", "invalid digest")
        if not _non_empty_string(evaluator.get("source_ref")):
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.official_evaluator.source_ref", "must be non-empty")
        if not isinstance(official, dict) or evaluator.get("checks_passed") != official.get("checks_passed") or evaluator.get(
            "checks_total"
        ) != official.get("checks_total"):
            report.error("PUBLIC_OBSERVABLE_LINEAGE_JOIN", f"{location}.official_evaluator", "evaluator counts do not join official_evaluation")

    redaction = value.get("redaction")
    if _closed_keys(redaction, LINEAGE_REDACTION_KEYS, report, f"{location}.redaction"):
        expected_exclusions = [
            "subscription-authentication",
            "credential-values",
            "host-private-paths",
            "hidden-reasoning",
            "hidden-tests",
        ]
        if redaction.get("excluded") != expected_exclusions or redaction.get("full_log_public") is not False:
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.redaction", "must preserve the closed safe-public exclusion policy")
        if not _non_empty_string(redaction.get("policy")):
            report.error("PUBLIC_OBSERVABLE_LINEAGE", f"{location}.redaction.policy", "must be non-empty")


def _validate_execution_amendment(
    value: Any,
    *,
    identity: Any,
    process: Any,
    lineage: Any,
    registry_entry: Any,
    location: str,
    report: Report,
) -> None:
    if not _closed_keys(value, EXECUTION_AMENDMENT_KEYS, report, location):
        return
    if value.get("schema_version") != EXECUTION_AMENDMENT_SCHEMA:
        report.error("PUBLIC_EXECUTION_AMENDMENT", location, "invalid execution-amendment schema")
    if not isinstance(identity, dict) or value.get("attempt_id") != identity.get(
        "attempt_id"
    ) or value.get("arm") != identity.get("arm"):
        report.error("PUBLIC_EXECUTION_AMENDMENT_JOIN", location, "attempt and arm must join identity")
    if value.get("frozen_study_overwritten") is not False:
        report.error("PUBLIC_EXECUTION_AMENDMENT", location, "must not rewrite the frozen study")
    if not _non_empty_string(value.get("amendment_reason")):
        report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.amendment_reason", "must be non-empty")
    source_refs = value.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs or any(
        not _non_empty_string(item) for item in source_refs
    ):
        report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.source_refs", "must be non-empty refs")

    worker_log = lineage.get("worker_log") if isinstance(lineage, dict) else None
    contamination = (
        registry_entry.get("contamination_facts")
        if isinstance(registry_entry, dict)
        else None
    )
    tools_runtime = value.get("tools_runtime")
    if _closed_keys(
        tools_runtime,
        EXECUTION_TOOLS_RUNTIME_KEYS,
        report,
        f"{location}.tools_runtime",
    ):
        expected = {
            "model": contamination.get("evaluated_model") if isinstance(contamination, dict) else None,
            "network_policy": contamination.get("network_policy") if isinstance(contamination, dict) else None,
            "reasoning_effort": worker_log.get("reasoning_effort") if isinstance(worker_log, dict) else None,
            "runtime_identity": contamination.get("runtime_identity") if isinstance(contamination, dict) else None,
            "command_count": worker_log.get("command_count") if isinstance(worker_log, dict) else None,
            "agent_message_count": worker_log.get("agent_message_count") if isinstance(worker_log, dict) else None,
        }
        if any(tools_runtime.get(key) != expected_value for key, expected_value in expected.items()):
            report.error("PUBLIC_EXECUTION_AMENDMENT_JOIN", f"{location}.tools_runtime", "runtime facts do not join registry and lineage")
        if not _non_empty_string(tools_runtime.get("codex_version")):
            report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.tools_runtime.codex_version", "must be non-empty")

    timing = value.get("timing")
    if _closed_keys(timing, EXECUTION_TIMING_KEYS, report, f"{location}.timing"):
        timing_status = timing.get("status")
        if timing_status == "observed":
            if not _non_empty_string(timing.get("started_at")) or not _non_empty_string(timing.get("finished_at")) or timing.get("reason") is not None:
                report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.timing", "observed timing requires start/finish and null reason")
        elif timing_status == "unavailable":
            if timing.get("started_at") is not None or timing.get("finished_at") is not None or not _non_empty_string(timing.get("reason")):
                report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.timing", "unavailable timing requires null values and a reason")
        else:
            report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.timing.status", "invalid timing status")

    usage = value.get("usage")
    if _closed_keys(usage, EXECUTION_USAGE_KEYS, report, f"{location}.usage"):
        usage_status = usage.get("status")
        metrics = ("input_tokens", "cached_input_tokens", "output_tokens")
        if usage_status == "observed":
            if any(not _non_negative_integer(usage.get(key)) for key in metrics) or usage.get("reason") is not None:
                report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.usage", "observed usage requires integer metrics and null reason")
            elif usage["cached_input_tokens"] > usage["input_tokens"]:
                report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.usage", "cached input must not exceed input tokens")
        elif usage_status == "unavailable":
            if any(usage.get(key) is not None for key in metrics) or not _non_empty_string(usage.get("reason")):
                report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.usage", "unavailable usage requires null metrics and a reason")
        else:
            report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.usage.status", "invalid usage status")

    seed_retry = value.get("seed_retry")
    if _closed_keys(
        seed_retry,
        EXECUTION_SEED_RETRY_KEYS,
        report,
        f"{location}.seed_retry",
    ):
        if (
            seed_retry.get("seed_status") != "unavailable"
            or seed_retry.get("seed") is not None
            or seed_retry.get("retry_status") != "unavailable"
            or seed_retry.get("retry_count") is not None
            or not _non_empty_string(seed_retry.get("reason"))
        ):
            report.error("PUBLIC_EXECUTION_AMENDMENT", f"{location}.seed_retry", "missing seed/retry must remain explicitly unavailable")
        expected_repairs = process.get("repair_attempts_executed") if isinstance(process, dict) else None
        if seed_retry.get("repair_attempts_executed") != expected_repairs:
            report.error("PUBLIC_EXECUTION_AMENDMENT_JOIN", f"{location}.seed_retry", "repair count does not join process")

    qa_repair = value.get("qa_repair_order")
    if _closed_keys(
        qa_repair,
        EXECUTION_QA_REPAIR_KEYS,
        report,
        f"{location}.qa_repair_order",
    ):
        if not isinstance(process, dict) or any(
            qa_repair.get(key) != process.get(key) for key in EXECUTION_QA_REPAIR_KEYS
        ):
            report.error("PUBLIC_EXECUTION_AMENDMENT_JOIN", f"{location}.qa_repair_order", "QA/repair order does not join process")

    if not isinstance(lineage, dict) or value.get("service_revision") != lineage.get(
        "service_revision"
    ) or value.get("prescore_world") != lineage.get("prescore_world"):
        report.error("PUBLIC_EXECUTION_AMENDMENT_JOIN", location, "service and pre-score identities do not join observable lineage")


def _validate_attempt_disposition(
    value: Any,
    *,
    identity: Any,
    location: str,
    report: Report,
) -> None:
    if not _closed_keys(value, ATTEMPT_DISPOSITION_KEYS, report, location):
        return
    if value.get("schema_version") != ATTEMPT_DISPOSITION_SCHEMA:
        report.error("PUBLIC_ATTEMPT_DISPOSITION", location, "invalid attempt-disposition schema")
    current = value.get("current_attempt")
    if _closed_keys(current, ATTEMPT_CURRENT_KEYS, report, f"{location}.current_attempt"):
        if (
            not isinstance(identity, dict)
            or current.get("attempt_id") != identity.get("attempt_id")
            or current.get("run_id") != identity.get("run_id")
            or current.get("counted") is not True
            or current.get("status") != "counted-completed"
            or not _non_empty_string(current.get("reason"))
        ):
            report.error("PUBLIC_ATTEMPT_DISPOSITION_JOIN", f"{location}.current_attempt", "current attempt does not join the counted identity")
    invalid = value.get("invalid_predecessors")
    if not isinstance(invalid, list):
        report.error("PUBLIC_ATTEMPT_DISPOSITION", f"{location}.invalid_predecessors", "must be an array")
        return
    labels: set[str] = set()
    for index, item in enumerate(invalid):
        item_location = f"{location}.invalid_predecessors[{index}]"
        if not _closed_keys(item, ATTEMPT_INVALID_KEYS, report, item_location):
            continue
        label = item.get("attempt_label")
        if not _non_empty_string(label) or label in labels:
            report.error("PUBLIC_ATTEMPT_DISPOSITION", f"{item_location}.attempt_label", "must be a unique non-empty label")
        else:
            labels.add(label)
        if item.get("counted") is not False or item.get("status") != "invalid-not-a-study-result" or item.get("public_record_status") != "waived-no-posthoc-backfill":
            report.error("PUBLIC_ATTEMPT_DISPOSITION", item_location, "invalid predecessor must remain noncounting and waived without backfill")
        for key in ("reason", "source_ref", "waiver_reason"):
            if not _non_empty_string(item.get(key)):
                report.error("PUBLIC_ATTEMPT_DISPOSITION", f"{item_location}.{key}", "must be non-empty")


def _validate_public_result_manifest(
    entry: dict[str, Any],
    manifest_bytes: bytes,
    *,
    manifest_path: str,
    commit: str,
    repo: Path,
    location: str,
    report: Report,
) -> None:
    manifest_location = f"{location}.artifact_manifest"
    try:
        manifest = json.loads(
            manifest_bytes,
            object_pairs_hook=_strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        report.error(
            "PUBLIC_RESULT_MANIFEST",
            manifest_location,
            "manifest must be strict JSON",
        )
        return
    if not isinstance(manifest, dict):
        report.error(
            "PUBLIC_RESULT_MANIFEST",
            manifest_location,
            "manifest top level must be an object",
        )
        return
    schema_version = manifest.get("schema_version")
    manifest_keys = {
        PUBLIC_RESULT_SCHEMA: PUBLIC_RESULT_V1_KEYS,
        PUBLIC_RESULT_EVIDENCE_SCHEMA: PUBLIC_RESULT_V2_KEYS,
    }.get(schema_version)
    if manifest_keys is None:
        report.error(
            "PUBLIC_RESULT_MANIFEST",
            manifest_location,
            "schema_version must name a supported public-result schema",
        )
        return
    if not _closed_keys(manifest, manifest_keys, report, manifest_location):
        return
    canonical = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if manifest_bytes != canonical:
        report.error(
            "PUBLIC_RESULT_MANIFEST",
            manifest_location,
            "manifest must use canonical sorted, indented JSON",
        )
    for key in ("release_id", "identity", "sealed_artifacts"):
        if manifest.get(key) != entry.get(key):
            report.error(
                "PUBLIC_RESULT_MANIFEST_BINDING",
                manifest_location,
                f"{key} does not match the registry row",
            )

    identity = manifest.get("identity")
    arm = identity.get("arm") if isinstance(identity, dict) else None
    condition = manifest.get("condition")
    expected_condition = {
        "control": ("Control", False),
        "treatment": ("Treatment", True),
    }.get(arm)
    if not _closed_keys(
        condition,
        PUBLIC_RESULT_CONDITION_KEYS,
        report,
        f"{manifest_location}.condition",
    ) or expected_condition is None:
        report.error(
            "PUBLIC_RESULT_CONDITION",
            manifest_location,
            "condition and typed arm must describe treatment or control",
        )
    else:
        expected_label, expected_access = expected_condition
        if (
            condition.get("label") != expected_label
            or condition.get("corridor_access") is not expected_access
        ):
            report.error(
                "PUBLIC_RESULT_CONDITION",
                manifest_location,
                "condition label and Corridor access do not match the typed arm",
            )
        observed = condition.get("corridor_observably_used")
        if schema_version == PUBLIC_RESULT_EVIDENCE_SCHEMA and observed is not expected_access:
            report.error(
                "PUBLIC_RESULT_CONDITION",
                manifest_location,
                "v2 must record contemporaneously evidenced Corridor use for Treatment and false for Control",
            )

    interpretation = manifest.get("interpretation")
    interpretation_closed = _closed_keys(
        interpretation,
        PUBLIC_RESULT_INTERPRETATION_KEYS,
        report,
        f"{manifest_location}.interpretation",
    )
    if not interpretation_closed or any(
        interpretation.get(key) is not False
        for key in ("causal_claim", "leaderboard_claim", "multi_task_evidence")
    ) or interpretation.get("distinct_benchmark_tasks") != 1:
        report.error(
            "PUBLIC_RESULT_CLAIM_BOUNDARY",
            manifest_location,
            "manifest must preserve the one-task descriptive claim boundary",
        )

    official = manifest.get("official_evaluation")
    outcomes = entry.get("outcomes")
    official_closed = _closed_keys(
        official,
        PUBLIC_RESULT_OFFICIAL_KEYS,
        report,
        f"{manifest_location}.official_evaluation",
    )
    if not official_closed or not isinstance(outcomes, dict):
        report.error(
            "PUBLIC_RESULT_OUTCOME",
            manifest_location,
            "official evaluation and registry outcomes must be objects",
        )
    else:
        outcome = official.get("outcome")
        counted = {
            key: outcomes.get(key)
            for key in OUTCOME_KEYS
            if key != "total"
        }
        if (
            outcome not in counted
            or outcomes.get("total") != 1
            or counted.get(outcome) != 1
            or sum(value for value in counted.values() if isinstance(value, int)) != 1
        ):
            report.error(
                "PUBLIC_RESULT_OUTCOME",
                manifest_location,
                "official outcome does not match the single-arm registry count",
            )

    process = manifest.get("process")
    _closed_keys(
        process,
        PUBLIC_RESULT_PROCESS_KEYS,
        report,
        f"{manifest_location}.process",
    )
    source_custody = manifest.get("source_custody")
    source_closed = _closed_keys(
        source_custody,
        PUBLIC_RESULT_SOURCE_CUSTODY_KEYS,
        report,
        f"{manifest_location}.source_custody",
    )
    if schema_version == PUBLIC_RESULT_EVIDENCE_SCHEMA and source_closed:
        for key in (
            "controlled_result_commit",
            "controlled_result_tree",
            "method_source_commit",
            "official_task_source_commit",
        ):
            if not isinstance(source_custody.get(key), str) or not COMMIT_RE.fullmatch(source_custody[key]):
                report.error(
                    "PUBLIC_RESULT_SOURCE_CUSTODY",
                    f"{manifest_location}.source_custody.{key}",
                    "must be a full lowercase 40-hex Git object id",
                )
        for key in ("builder_service_commit", "builder_service_tree"):
            item = source_custody.get(key)
            if arm == "treatment":
                if not isinstance(item, str) or not COMMIT_RE.fullmatch(item):
                    report.error(
                        "PUBLIC_RESULT_SOURCE_CUSTODY",
                        f"{manifest_location}.source_custody.{key}",
                        "Treatment must bind a full lowercase 40-hex Git object id",
                    )
            elif item is not None:
                report.error(
                    "PUBLIC_RESULT_SOURCE_CUSTODY",
                    f"{manifest_location}.source_custody.{key}",
                    "Control must not claim a builder service identity",
                )
        if not isinstance(source_custody.get("controlled_result_path"), str) or not source_custody[
            "controlled_result_path"
        ].startswith("exogenous/results/"):
            report.error(
                "PUBLIC_RESULT_SOURCE_CUSTODY",
                f"{manifest_location}.source_custody.controlled_result_path",
                "must name normalized controlled result custody",
            )

    if schema_version == PUBLIC_RESULT_EVIDENCE_SCHEMA:
        _validate_causal_evidence(
            manifest.get("causal_evidence"),
            identity=identity,
            location=f"{manifest_location}.causal_evidence",
            report=report,
        )
        _validate_observable_lineage(
            manifest.get("observable_lineage"),
            identity=identity,
            source_custody=source_custody,
            official=official,
            location=f"{manifest_location}.observable_lineage",
            report=report,
        )
        _validate_execution_amendment(
            manifest.get("execution_amendment"),
            identity=identity,
            process=process,
            lineage=manifest.get("observable_lineage"),
            registry_entry=entry,
            location=f"{manifest_location}.execution_amendment",
            report=report,
        )
        _validate_attempt_disposition(
            manifest.get("attempt_disposition"),
            identity=identity,
            location=f"{manifest_location}.attempt_disposition",
            report=report,
        )

    public_summary = manifest.get("public_summary")
    expected_summary_path = str(PurePosixPath(manifest_path).with_name("SUMMARY.md"))
    summary_closed = _closed_keys(
        public_summary,
        PUBLIC_RESULT_SUMMARY_KEYS,
        report,
        f"{manifest_location}.public_summary",
    )
    if not summary_closed or public_summary.get("path") != expected_summary_path:
        report.error(
            "PUBLIC_RESULT_SUMMARY",
            manifest_location,
            "public_summary.path must name the sibling SUMMARY.md",
        )
        return
    summary = _git(repo, ["show", f"{commit}:{expected_summary_path}"])
    if summary.returncode != 0:
        report.error(
            "PUBLIC_RESULT_SUMMARY",
            manifest_location,
            "public summary is absent from the recorded commit",
        )
        return
    actual_summary_digest = "sha256:" + hashlib.sha256(summary.stdout).hexdigest()
    if (
        public_summary.get("sha256") != actual_summary_digest
        or public_summary.get("size_bytes") != len(summary.stdout)
    ):
        report.error(
            "PUBLIC_RESULT_SUMMARY",
            manifest_location,
            "public summary digest or byte size does not match committed bytes",
        )


def validate_registry(
    path: Path,
    *,
    repo: Path | None = None,
    base_ref: str | None = None,
    history_base_ref: str | None = None,
    genesis: bool = False,
    source_bytes: bytes | None = None,
    source_label: str | None = None,
) -> Report:
    path = path.resolve()
    report = Report(subject=source_label or str(path))
    value = (
        _load_json(path, report)
        if source_bytes is None
        else _load_json_bytes(source_bytes, report, source_label or str(path))
    )
    if value is None:
        return report
    if not _closed_keys(value, REGISTRY_KEYS, report, "PUBLIC-RELEASES.json"):
        return report
    if value.get("schema_version") != REGISTRY_SCHEMA:
        report.error("REGISTRY_SCHEMA", "schema_version", f"must equal {REGISTRY_SCHEMA}")
    if value.get("branch_namespaces") != EXPECTED_NAMESPACES:
        report.error("REGISTRY_NAMESPACES", "branch_namespaces", "must equal the deterministic namespace catalog")
    if value.get("public_artifact_classes") != EXPECTED_PUBLIC_CLASSES:
        report.error("REGISTRY_CLASSES", "public_artifact_classes", "must equal the closed public class list")
    if value.get("restricted_artifact_classes") != EXPECTED_RESTRICTED_CLASSES:
        report.error("REGISTRY_CLASSES", "restricted_artifact_classes", "must equal the closed restricted class list")
    policy = value.get("release_policy")
    if _closed_keys(policy, POLICY_KEYS, report, "release_policy"):
        expected = {
            "append_only": True,
            "claim_default": "descriptive-only",
            "default_visibility": "restricted-on-request",
            "exact_service_replay": "embargoed-solution-bearing",
            "method_transfer_replication": "public-default",
            "publication_gate": "human-authorization-after-machine-check",
        }
        if policy != expected:
            report.error("REGISTRY_POLICY", "release_policy", "must equal the frozen v1 public-release policy")
    releases = value.get("releases")
    if not isinstance(releases, list):
        report.error("REGISTRY_RELEASES", "releases", "must be an array")
        releases = []
    known_ids: set[str] = set()
    known_refs: set[str] = set()
    known_identities: set[str] = set()
    for index, entry in enumerate(releases):
        _validate_release_entry(entry, index, known_ids, known_refs, known_identities, report)
    canonical = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if source_bytes is None:
        try:
            actual = path.read_text(encoding="utf-8")
        except OSError:
            actual = ""
    else:
        try:
            actual = source_bytes.decode("utf-8")
        except UnicodeDecodeError:
            actual = ""
    if actual != canonical:
        report.error("REGISTRY_CANONICAL", str(path), "must use canonical sorted, indented JSON with one final newline")
    resolved_base_commit: str | None = None
    if genesis and not base_ref:
        report.error("REGISTRY_GENESIS", "genesis", "--genesis requires --base-ref naming the candidate public root")
    if genesis and history_base_ref:
        report.error("REGISTRY_GENESIS", "history_base_ref", "genesis cannot use a separate history base")
    if base_ref:
        if repo is None:
            report.error("REGISTRY_BASE", "base_ref", "repo is required with base_ref")
        else:
            resolved_base = _git(repo.resolve(), ["rev-parse", "--verify", f"{base_ref}^{{commit}}"])
            if resolved_base.returncode != 0:
                report.error("REGISTRY_BASE", base_ref, "cannot resolve base ref")
            else:
                resolved_base_commit = resolved_base.stdout.decode().strip()
    history_ref = history_base_ref or base_ref
    if history_ref:
        if repo is None:
            report.error("REGISTRY_BASE", "history_base_ref", "repo is required with a history base")
        else:
            try:
                relative = path.relative_to(repo.resolve()).as_posix()
            except ValueError:
                report.error("REGISTRY_BASE", str(path), "registry must be inside repo")
            else:
                resolved_history = _git(repo.resolve(), ["rev-parse", "--verify", f"{history_ref}^{{commit}}"])
                if resolved_history.returncode != 0:
                    report.error("REGISTRY_BASE", history_ref, "cannot resolve history base ref")
                    base = None
                else:
                    resolved_history_commit = resolved_history.stdout.decode().strip()
                    shown = _git(repo.resolve(), ["show", f"{history_ref}:{relative}"])
                    if shown.returncode != 0:
                        report.error("REGISTRY_BASE", history_ref, "history base ref does not contain the registry")
                        base = None
                    else:
                        try:
                            parsed_base = json.loads(
                                shown.stdout, object_pairs_hook=_strict_object
                            )
                        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                            report.error(
                                "REGISTRY_BASE",
                                history_ref,
                                "base registry is not valid strict JSON",
                            )
                            base = None
                        else:
                            if not isinstance(parsed_base, dict):
                                report.error(
                                    "REGISTRY_BASE",
                                    history_ref,
                                    "base registry top level must be an object",
                                )
                                base = None
                            else:
                                base = parsed_base
                if base is not None:
                    if genesis:
                        parents = _git(repo.resolve(), ["rev-list", "--parents", "-n", "1", resolved_history_commit])
                        parent_fields = parents.stdout.decode().strip().split() if parents.returncode == 0 else []
                        if len(parent_fields) != 1 or releases:
                            report.error("REGISTRY_GENESIS", history_ref, "genesis must be an empty registry in a no-parent public root")
                    base_releases = base.get("releases")
                    if not isinstance(base_releases, list):
                        report.error("REGISTRY_APPEND_ONLY", "base_ref", "base registry is malformed")
                    elif releases[: len(base_releases)] != base_releases:
                        report.error(
                            "REGISTRY_APPEND_ONLY",
                            "releases",
                            "existing release rows may not be deleted, edited, or reordered",
                        )
                    for key in REGISTRY_KEYS - {"releases"}:
                        if base.get(key) != value.get(key):
                            report.error(
                                "REGISTRY_APPEND_ONLY",
                                key,
                                "v1 registry policy is immutable; introduce a new schema instead",
                            )
    if releases and not base_ref:
        report.error("REGISTRY_BASE_REQUIRED", "releases", "non-empty registry validation requires --base-ref")
    if releases and repo is None:
        report.error("RELEASE_AUTHORITY", "releases", "non-empty registry validation requires --repo")
    elif repo is not None:
        authority_repo = repo.resolve()
        for index, entry in enumerate(releases):
            if isinstance(entry, dict):
                _validate_release_authority(
                    entry,
                    index,
                    repo=authority_repo,
                    base_commit=resolved_base_commit if not genesis else None,
                    report=report,
                )
    report.facts.update({"release_count": len(releases), "schema_version": value.get("schema_version")})
    return report


def render_registry_summary(value: dict[str, Any]) -> str:
    """Render the append-only release registry without changing the run index."""
    lines = [
        "# Public releases",
        "",
        "Generated by `tools/public_release.py summarize-registry`. Do not edit by hand.",
        "",
        "| sequence | release | kind | visibility | task | run | outcomes | commit |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    releases = value.get("releases") if isinstance(value, dict) else None
    if not isinstance(releases, list) or not releases:
        lines.append("| | _(none published)_ | | | | | | |")
    else:
        for row in releases:
            identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
            outcomes = row.get("outcomes") if isinstance(row.get("outcomes"), dict) else None
            outcome_text = ""
            if outcomes is not None:
                outcome_text = ", ".join(
                    f"{key}={outcomes[key]}"
                    for key in ("pass", "fail", "blocked", "invalid", "timeout", "unscored")
                )
            lines.append(
                "| {sequence} | `{release}` | {kind} | `{visibility}` | `{task}` | `{run}` | {outcomes} | `{commit}` |".format(
                    sequence=row.get("sequence", ""),
                    release=row.get("release_id", ""),
                    kind=row.get("branch_kind", ""),
                    visibility=row.get("visibility", ""),
                    task=identity.get("task_id") or "",
                    run=identity.get("run_id") or "",
                    outcomes=outcome_text,
                    commit=row.get("commit_sha", ""),
                )
            )
    return "\n".join(lines) + "\n"


def _safe_ref(ref: str) -> bool:
    return bool(SAFE_REF_RE.fullmatch(ref)) and ".." not in ref and "//" not in ref


def _path_policy(path: str, report: Report, location: str) -> str | None:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or not path or "\\" in path:
        report.error("RELEASE_PATH", location, "path must be normalized repository-relative POSIX")
        return None
    lower = path.lower()
    parts = {part.lower() for part in pure.parts}
    name = pure.name.lower()
    suffix = pure.suffix.lower()
    if {".git", ".codex", ".aming-claw"} & parts or name == ".gitmodules":
        report.error("NESTED_GIT", location, "nested Git metadata, submodules, and runtime metadata are forbidden")
        return None
    if lower == "exogenous/local" or lower.startswith("exogenous/local/"):
        report.error("LOCAL_EVIDENCE", location, "exogenous/local is never public")
        return None
    if suffix in ARCHIVE_SUFFIXES:
        report.error("ARCHIVE", location, "archives are not accepted on the public release surface")
        return None
    if suffix in RESTRICTED_SUFFIXES:
        report.error("RESTRICTED_ARTIFACT", location, f"{suffix} artifacts are embargoed or restricted")
        return None
    if suffix == ".jsonl" and not lower.startswith("templates/legacy-corridor-v1/authority/"):
        report.error("RAW_LOG", location, "JSONL is allowed only for the public legacy authority fixture")
        return None
    if re.search(r"(?:^|[-_.])(trajectory|transcript|session)(?:[-_.]|$)", name):
        report.error("RAW_SESSION", location, "raw session, transcript, and trajectory files are restricted")
        return None
    if re.search(r"(?:^|[-_.])hidden[-_.]?(?:test|tests|evaluator|verifier)(?:[-_.]|$)", name):
        report.error("HIDDEN_EVALUATOR", location, "hidden evaluator material is restricted")
        return None
    if re.search(r"(?:^|[-_.])(solution|solver|solve|planner_service|writeback)(?:[-_.]|$)", name):
        report.error("SOLUTION_ARTIFACT", location, "solution-bearing artifacts are embargoed")
        return None
    if pure.name in ALLOWED_EXTENSIONLESS:
        return "text"
    if suffix not in ALLOWED_TEXT_SUFFIXES and suffix != ".jsonl":
        report.error("UNCLASSIFIED_BLOB", location, "blob type is not on the public text allowlist")
        return None
    return "text"


def _validate_method_provenance(
    repo: Path,
    *,
    resolved_commit: str,
    report: Report,
) -> None:
    """Require cataloged method bytes to live in the selected public history."""
    catalog_path = "method-paper/VERSIONS.json"
    shown = _git(repo, ["show", f"{resolved_commit}:{catalog_path}"])
    if shown.returncode != 0:
        report.facts["method_provenance_version_count"] = 0
        report.facts["method_provenance_commits"] = []
        return
    try:
        catalog = json.loads(shown.stdout, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        report.error(
            "METHOD_PROVENANCE_CATALOG",
            catalog_path,
            f"cannot load strict JSON ({type(exc).__name__})",
        )
        return
    if not isinstance(catalog, dict) or catalog.get("schema_version") != "charting-loop/method-index/v2":
        report.error(
            "METHOD_PROVENANCE_CATALOG",
            catalog_path,
            "must be a charting-loop/method-index/v2 object",
        )
        return
    versions = catalog.get("versions")
    if not isinstance(versions, list):
        report.error("METHOD_PROVENANCE_CATALOG", f"{catalog_path}.versions", "must be an array")
        return

    source_commits: set[str] = set()
    for index, version in enumerate(versions):
        location = f"{catalog_path}.versions[{index}]"
        if not isinstance(version, dict):
            report.error("METHOD_PROVENANCE_CATALOG", location, "must be an object")
            continue
        version_id = version.get("version_id")
        source_commit = version.get("source_commit")
        if not isinstance(source_commit, str) or COMMIT_RE.fullmatch(source_commit) is None:
            report.error(
                "METHOD_PROVENANCE_COMMIT",
                f"{location}.source_commit",
                f"{version_id or 'unnamed version'} must name a full lowercase commit id",
            )
            continue
        resolved_source = _git(repo, ["rev-parse", "--verify", f"{source_commit}^{{commit}}"])
        if resolved_source.returncode != 0 or resolved_source.stdout.decode().strip() != source_commit:
            report.error(
                "METHOD_PROVENANCE_REACHABILITY",
                f"{location}.source_commit",
                f"{source_commit} is not an available commit",
            )
            continue
        ancestor = _git(repo, ["merge-base", "--is-ancestor", source_commit, resolved_commit])
        if ancestor.returncode != 0:
            report.error(
                "METHOD_PROVENANCE_REACHABILITY",
                f"{location}.source_commit",
                f"{source_commit} is not an ancestor of selected ref {resolved_commit}",
            )
            continue
        source_commits.add(source_commit)
        for path_key, digest_key in (
            ("path", "content_sha256"),
            ("scope_datum_path", "scope_datum_sha256"),
        ):
            source_path = version.get(path_key)
            expected_digest = version.get(digest_key)
            pure = PurePosixPath(source_path) if isinstance(source_path, str) else None
            if (
                pure is None
                or not source_path
                or pure.is_absolute()
                or ".." in pure.parts
                or "\\" in source_path
            ):
                report.error(
                    "METHOD_PROVENANCE_PATH",
                    f"{location}.{path_key}",
                    "must be a normalized repository-relative POSIX path",
                )
                continue
            if not isinstance(expected_digest, str) or SHA256_RE.fullmatch(expected_digest) is None:
                report.error(
                    "METHOD_PROVENANCE_DIGEST",
                    f"{location}.{digest_key}",
                    "must be a sha256-prefixed lowercase digest",
                )
                continue
            source_blob = _git(repo, ["show", f"{source_commit}:{source_path}"])
            if source_blob.returncode != 0:
                report.error(
                    "METHOD_PROVENANCE_BLOB",
                    f"{location}.{path_key}",
                    f"cannot read {source_path} from {source_commit}",
                )
                continue
            actual_digest = "sha256:" + hashlib.sha256(source_blob.stdout).hexdigest()
            if actual_digest != expected_digest:
                report.error(
                    "METHOD_PROVENANCE_DIGEST",
                    f"{location}.{digest_key}",
                    f"declared {expected_digest}, source bytes hash to {actual_digest}",
                )
    report.facts["method_provenance_version_count"] = len(versions)
    report.facts["method_provenance_commits"] = sorted(source_commits)


def _placeholder_secret(value: bytes) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized in {b"redacted", b"example", b"placeholder", b"none", b"null"}
        or normalized.startswith((b"<", b"${", b"sha256:"))
    )


def _scan_blob(path: str, data: bytes, size: int, max_bytes: int, report: Report, location: str) -> None:
    classification = _path_policy(path, report, location)
    if classification is None:
        return
    if size > max_bytes:
        report.error("OVERSIZE_BLOB", location, f"{size} bytes exceeds limit {max_bytes}")
        return
    if b"\x00" in data:
        report.error("UNCLASSIFIED_BLOB", location, "binary blob is not allowed")
        return
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        report.error("UNCLASSIFIED_BLOB", location, "public text blobs must be UTF-8")
        return
    if any(pattern.search(data) for pattern in LOCAL_PATH_PATTERNS):
        report.error("LOCAL_PATH", location, "host-local absolute path detected")
    if any(pattern.search(data) for pattern in TOKEN_PATTERNS):
        report.error("CREDENTIAL", location, "credential-shaped material detected")
    for match in SECRET_ASSIGNMENT_RE.finditer(data):
        if not _placeholder_secret(match.group(1)):
            report.error("CREDENTIAL", location, "non-placeholder secret assignment detected")
            break
    if HIDDEN_REASONING_RE.search(data):
        report.error("HIDDEN_REASONING", location, "hidden reasoning or chain-of-thought shaped content detected")


def _batch_object_metadata(repo: Path, object_ids: Iterable[str]) -> dict[str, tuple[str, int]]:
    unique = sorted(set(object_ids))
    if not unique:
        return {}
    payload = ("\n".join(unique) + "\n").encode()
    result = _git(repo, ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"], input_bytes=payload)
    if result.returncode != 0:
        return {}
    metadata: dict[str, tuple[str, int]] = {}
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2].isdigit():
            metadata[fields[0]] = (fields[1], int(fields[2]))
    return metadata


def _read_blob(repo: Path, object_id: str) -> bytes | None:
    result = _git(repo, ["cat-file", "blob", object_id])
    return result.stdout if result.returncode == 0 else None


def _index_entries(repo: Path, report: Report) -> list[tuple[str, str, str]]:
    result = _git(repo, ["ls-files", "--stage", "-z"])
    if result.returncode != 0:
        report.error("GIT_INDEX", "staged", "cannot read Git index")
        return []
    entries: list[tuple[str, str, str]] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            header, encoded_path = raw.split(b"\t", 1)
            mode, object_id, stage = header.decode().split()
            path = encoded_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            report.error("GIT_INDEX", "staged", "malformed index entry")
            continue
        if stage != "0":
            report.error("GIT_INDEX", path, "unmerged index entries are forbidden")
            continue
        if mode == "160000":
            report.error("NESTED_GIT", f"staged:{path}", "gitlinks/submodules are forbidden")
            continue
        if mode == "120000":
            report.error("SYMLINK", f"staged:{path}", "symlinks are forbidden on the public release surface")
            continue
        entries.append((object_id, path, mode))
    return entries


def _ref_tree_entries(repo: Path, ref: str, report: Report) -> list[tuple[str, str, str]]:
    result = _git(repo, ["ls-tree", "-r", "-z", "--full-tree", ref])
    if result.returncode != 0:
        report.error("GIT_REF", ref, "cannot read exact ref tree")
        return []
    entries: list[tuple[str, str, str]] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            header, encoded_path = raw.split(b"\t", 1)
            mode, object_type, object_id = header.decode().split()
            path = encoded_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            report.error("GIT_REF", ref, "malformed tree entry")
            continue
        if mode == "160000" or object_type == "commit":
            report.error("NESTED_GIT", f"ref:{path}", "gitlinks/submodules are forbidden")
            continue
        if mode == "120000":
            report.error("SYMLINK", f"ref:{path}", "symlinks are forbidden on the public release surface")
            continue
        if object_type == "blob":
            entries.append((object_id, path, mode))
    return entries


def _reachable_named_objects(repo: Path, ref: str, report: Report) -> list[tuple[str, str]]:
    result = _git(repo, ["rev-list", "--objects", "-z", ref])
    if result.returncode != 0:
        report.error("GIT_REF", ref, "cannot enumerate reachable objects")
        return []
    objects: list[tuple[str, str]] = []
    tokens = [raw for raw in result.stdout.split(b"\0") if raw]
    index = 0
    while index < len(tokens):
        raw = tokens[index]
        try:
            object_id = raw.decode("ascii")
        except UnicodeDecodeError:
            report.error("GIT_OBJECT_ID", ref, "reachable object id must be ASCII")
            index += 1
            continue
        index += 1
        if not COMMIT_RE.fullmatch(object_id):
            report.error("GIT_OBJECT_ID", ref, "reachable object id must be full lowercase hex")
            continue
        if index >= len(tokens) or not tokens[index].startswith(b"path="):
            continue
        try:
            path = tokens[index][5:].decode("utf-8")
        except UnicodeDecodeError:
            report.error("GIT_OBJECT_PATH", ref, "reachable object path must be UTF-8")
            index += 1
            continue
        index += 1
        if path:
            objects.append((object_id, path))
    return objects


def scan_release(
    repo: Path,
    *,
    ref: str,
    allowed_refs: list[str],
    max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES,
    require_clean: bool = True,
) -> Report:
    repo = repo.resolve()
    report = Report(subject=f"{repo}@{ref}")
    if not allowed_refs:
        report.error("REF_ALLOWLIST", ref, "at least one explicit --allow-ref is required")
        return report
    if any(not _safe_ref(item) for item in allowed_refs):
        report.error("REF_ALLOWLIST", ref, "allowlist contains an unsafe or ambiguous ref")
        return report
    if ref not in set(allowed_refs):
        report.error("REF_ALLOWLIST", ref, "requested ref is not in the explicit allowlist")
        return report
    if not _safe_ref(ref):
        report.error("GIT_REF", ref, "unsafe or ambiguous ref")
        return report
    if not isinstance(max_blob_bytes, int) or max_blob_bytes < 1024:
        report.error("BLOB_LIMIT", str(max_blob_bytes), "limit must be at least 1024 bytes")
        return report
    top = _git(repo, ["rev-parse", "--show-toplevel"])
    if top.returncode != 0 or Path(top.stdout.decode().strip()).resolve() != repo:
        report.error("GIT_REPOSITORY", str(repo), "must be the exact Git worktree root")
        return report
    resolved = _git(repo, ["rev-parse", "--verify", f"{ref}^{{commit}}"])
    if resolved.returncode != 0:
        report.error("GIT_REF", ref, "cannot resolve ref to a commit")
        return report
    resolved_commit = resolved.stdout.decode().strip()
    _validate_method_provenance(repo, resolved_commit=resolved_commit, report=report)
    ref_tree_result = _git(repo, ["rev-parse", f"{resolved_commit}^{{tree}}"])
    ref_tree_id = ref_tree_result.stdout.decode().strip() if ref_tree_result.returncode == 0 else ""
    status = _git(repo, ["status", "--porcelain=v1", "--untracked-files=all"])
    dirty_lines = status.stdout.decode("utf-8", "replace").splitlines()
    if require_clean and dirty_lines:
        report.error("WORKTREE_DIRTY", "staged", "release self-check requires a clean worktree")
    if require_clean:
        head_tree = _git(repo, ["rev-parse", "HEAD^{tree}"])
        index_tree = _git(repo, ["write-tree"])
        if head_tree.returncode != 0 or head_tree.stdout.decode().strip() != ref_tree_id:
            report.error("REF_TREE_MISMATCH", ref, "clean HEAD tree must equal the selected ref tree")
        if index_tree.returncode != 0 or index_tree.stdout.decode().strip() != ref_tree_id:
            report.error("REF_TREE_MISMATCH", ref, "clean index tree must equal the selected ref tree")
    staged = _index_entries(repo, report)
    ref_tree = _ref_tree_entries(repo, ref, report)
    reachable = _reachable_named_objects(repo, ref, report)
    all_ids = [item[0] for item in staged] + [item[0] for item in ref_tree] + [item[0] for item in reachable]
    metadata = _batch_object_metadata(repo, all_ids)
    missing_metadata = sorted(set(all_ids) - set(metadata))
    if missing_metadata:
        report.error(
            "GIT_OBJECT_METADATA",
            ref,
            f"cannot classify {len(missing_metadata)} referenced Git object(s)",
        )
    blob_cache: dict[str, bytes | None] = {}

    def scan_entries(entries: Iterable[tuple[str, str]], origin: str) -> int:
        count = 0
        seen: set[tuple[str, str]] = set()
        for object_id, path in entries:
            if (object_id, path) in seen:
                continue
            seen.add((object_id, path))
            object_type, size = metadata.get(object_id, ("", -1))
            if object_type != "blob":
                continue
            count += 1
            location = f"{origin}:{path}@{object_id}"
            if size > max_blob_bytes:
                _path_policy(path, report, location)
                report.error("OVERSIZE_BLOB", location, f"{size} bytes exceeds limit {max_blob_bytes}")
                continue
            if object_id not in blob_cache:
                blob_cache[object_id] = _read_blob(repo, object_id)
            data = blob_cache[object_id]
            if data is None:
                report.error("GIT_BLOB", location, "cannot read blob")
                continue
            _scan_blob(path, data, size, max_blob_bytes, report, location)
        return count

    staged_count = scan_entries(((oid, path) for oid, path, _mode in staged), "staged")
    ref_count = scan_entries(((oid, path) for oid, path, _mode in ref_tree), "ref")
    reachable_count = scan_entries(reachable, "reachable")
    report.facts.update(
        {
            "allowed_refs": sorted(set(allowed_refs)),
            "max_blob_bytes": max_blob_bytes,
            "reachable_blob_count": reachable_count,
            "ref": ref,
            "ref_blob_count": ref_count,
            "resolved_commit": resolved_commit,
            "resolved_tree": ref_tree_id,
            "staged_blob_count": staged_count,
            "worktree_clean": not dirty_lines,
        }
    )
    return report


def _merge(target: Report, source: Report) -> None:
    target.errors.extend(item for item in source.errors if item not in target.errors)
    target.warnings.extend(item for item in source.warnings if item not in target.warnings)
    target.facts.update(source.facts)


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


def command_validate_registry(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    registry_argument = Path(args.registry)
    registry_path = registry_argument if registry_argument.is_absolute() else repo / registry_argument
    report = validate_registry(
        registry_path,
        repo=repo,
        base_ref=args.base_ref,
        history_base_ref=args.history_base_ref,
        genesis=args.genesis,
    )
    _emit(report, args.json)
    return 0 if report.ok else 1


def command_check(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    report = Report(subject=f"public-release:{repo}@{args.ref}")
    registry_argument = Path(args.registry)
    registry_path = (
        registry_argument.resolve()
        if registry_argument.is_absolute()
        else (repo / registry_argument).resolve()
    )
    try:
        registry_relative = registry_path.relative_to(repo).as_posix()
    except ValueError:
        report.error("REGISTRY_PATH", str(registry_path), "registry must be inside repo")
        registry_bytes = b""
        registry_source = "invalid-registry-path"
    else:
        selected = _git(
            repo,
            ["show", f":{registry_relative}"] if args.allow_dirty else ["show", f"{args.ref}:{registry_relative}"],
        )
        registry_source = ("index:" if args.allow_dirty else f"{args.ref}:") + registry_relative
        if selected.returncode != 0:
            report.error("REGISTRY_SELECTED", registry_source, "selected tree does not contain the registry")
            registry_bytes = b""
        else:
            registry_bytes = selected.stdout
    registry = validate_registry(
        registry_path,
        repo=repo,
        base_ref=args.base_ref,
        history_base_ref=args.history_base_ref,
        genesis=args.genesis,
        source_bytes=registry_bytes,
        source_label=registry_source,
    )
    if args.genesis and args.base_ref:
        selected_ref = _git(repo, ["rev-parse", "--verify", f"{args.ref}^{{commit}}"])
        selected_base = _git(repo, ["rev-parse", "--verify", f"{args.base_ref}^{{commit}}"])
        if (
            selected_ref.returncode != 0
            or selected_base.returncode != 0
            or selected_ref.stdout != selected_base.stdout
        ):
            report.error("REGISTRY_GENESIS", args.ref, "genesis base_ref must resolve to the selected ref")
    scan = scan_release(
        repo,
        ref=args.ref,
        allowed_refs=args.allow_ref,
        max_blob_bytes=args.max_blob_bytes,
        require_clean=not args.allow_dirty,
    )
    _merge(report, registry)
    _merge(report, scan)
    _emit(report, args.json)
    return 0 if report.ok else 1


def command_summarize_registry(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    registry_argument = Path(args.registry)
    path = (registry_argument if registry_argument.is_absolute() else repo / registry_argument).resolve()
    report = Report(subject=str(path))
    value = _load_json(path, report)
    if value is None:
        _emit(report, False)
        return 1
    validation = validate_registry(path, repo=repo, base_ref=args.base_ref)
    if not validation.ok:
        _emit(validation, False)
        return 1
    sys.stdout.write(render_registry_summary(value))
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    registry = subparsers.add_parser("validate-registry")
    registry.add_argument("--repo", default=".")
    registry.add_argument("--registry", default="exogenous/registry/PUBLIC-RELEASES.json")
    registry.add_argument("--base-ref")
    registry.add_argument("--history-base-ref")
    registry.add_argument("--genesis", action="store_true")
    registry.add_argument("--json", action="store_true")
    registry.set_defaults(func=command_validate_registry)
    check = subparsers.add_parser("check")
    check.add_argument("--repo", default=".")
    check.add_argument("--registry", default="exogenous/registry/PUBLIC-RELEASES.json")
    check.add_argument("--ref", required=True)
    check.add_argument("--allow-ref", action="append", required=True)
    check.add_argument("--base-ref")
    check.add_argument("--history-base-ref")
    check.add_argument("--genesis", action="store_true")
    check.add_argument("--max-blob-bytes", type=int, default=DEFAULT_MAX_BLOB_BYTES)
    check.add_argument("--allow-dirty", action="store_true")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=command_check)
    summary = subparsers.add_parser("summarize-registry")
    summary.add_argument("--repo", default=".")
    summary.add_argument("--registry", default="exogenous/registry/PUBLIC-RELEASES.json")
    summary.add_argument("--base-ref")
    summary.set_defaults(func=command_summarize_registry)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"INVALID: public-release checker internal error: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
