#!/usr/bin/env python3
"""Assemble one manual, evidence-bound CL-014 acceptance record.

This runner never starts an agent, contacts a network service, or invents a session.  It
only consumes files produced by operator-supplied fresh sessions, validates the complete
exogenous registry and method catalog, hashes the raw evidence bytes, and delegates the
final decision to :mod:`corridor_runtime` with an out-of-band trusted context.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import corridor_runtime as runtime  # noqa: E402
import exogenous_registry  # noqa: E402


INPUT_SCHEMA = "charting-loop/acceptance-input/v1"
REPLAY_RECEIPT_SCHEMA = "charting-loop/acceptance-replay-receipt/v1"
INPUT_KEYS = {
    "schema_version",
    "acceptance_id",
    "runner_id",
    "runner_session_id",
    "runner_invocation_id",
    "manual_confirmation",
    "measurement_plan_path",
    "attempts",
    "pairs",
    "replay_receipt_path",
}
ATTEMPT_KEYS = {
    "attempt_id",
    "arm",
    "session_id",
    "invocation_id",
    "session_receipt_path",
    "agent_kind",
    "scripted",
    "run_path",
    "candidate_sha256",
    "common_condition_sha256",
    "outcome",
    "supersedes_attempt_id",
    "repair_reason",
    "usage_receipt_path",
    "evidence",
}
EVIDENCE_KEYS = {"artifact_id", "kind", "path"}
PAIR_KEYS = {
    "pair_id",
    "builder_attempt_id",
    "treatment_attempt_id",
    "control_attempt_id",
    "candidate_sha256",
    "common_condition_sha256",
}
SESSION_RECEIPT_KEYS = {
    "schema_version",
    "receipt_id",
    "issuer_id",
    "issuer_session_id",
    "issuer_invocation_id",
    "attempt_id",
    "session_id",
    "invocation_id",
    "agent_kind",
    "scripted",
}
REPLAY_KEYS = {
    "schema_version",
    "replay_id",
    "verifier_id",
    "verifier_session_id",
    "verifier_invocation_id",
    "runner_id",
    "runner_session_id",
    "runner_invocation_id",
    "payload_sha256",
    "outcome_sha256",
    "verified",
}
ALLOWED_ARMS = {"builder", "treatment", "control"}


class AcceptanceInputError(ValueError):
    """A stable fail-closed input error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise AcceptanceInputError(code, message)


def _closed(value: Any, keys: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        _fail("input_fields", f"{location} must contain exactly {sorted(keys)}; got {actual}")
    return value


def _text(value: Any, location: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(char) < 32 or char == "\x7f" for char in value)
    ):
        _fail("input_string", f"{location} must be a non-empty string")
    return value


def _digest(value: Any, location: str) -> str:
    text = _text(value, location)
    if not runtime.SHA256_RE.fullmatch(text):
        _fail("input_digest", f"{location} must be a lowercase sha256 digest")
    return text


def load_closed_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = runtime.load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _fail("input_json", f"cannot load {label}: {type(exc).__name__}: {exc}")
    if not isinstance(value, dict):
        _fail("input_object", f"{label} must be a JSON object")
    return value


def safe_file(root: Path, relative: Any, *, label: str) -> tuple[str, Path]:
    """Resolve a regular file below *root* without following any symlink component."""

    text = _text(relative, label)
    pure = PurePosixPath(text)
    if pure.is_absolute() or text != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("unsafe_path", f"{label} must be a normalized safe-relative POSIX path")
    if root.is_symlink():
        _fail("unsafe_root", f"root for {label} must not be a symlink")
    root = root.resolve(strict=True)
    if not root.is_dir():
        _fail("unsafe_root", f"root for {label} must be a regular directory")
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _fail("unsafe_path", f"{label} traverses a symlink")
    try:
        resolved = cursor.resolve(strict=True)
    except OSError as exc:
        _fail("missing_file", f"{label} is unavailable: {type(exc).__name__}")
    if root not in resolved.parents or not resolved.is_file():
        _fail("unsafe_path", f"{label} must resolve to a regular file below its root")
    return pure.as_posix(), resolved


def safe_directory(root: Path, relative: Any, *, label: str) -> tuple[str, Path]:
    text = _text(relative, label)
    pure = PurePosixPath(text)
    if pure.is_absolute() or text != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("unsafe_path", f"{label} must be a normalized safe-relative POSIX path")
    if root.is_symlink():
        _fail("unsafe_root", f"root for {label} must not be a symlink")
    root = root.resolve(strict=True)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _fail("unsafe_path", f"{label} traverses a symlink")
    try:
        resolved = cursor.resolve(strict=True)
    except OSError as exc:
        _fail("missing_directory", f"{label} is unavailable: {type(exc).__name__}")
    if root not in resolved.parents or not resolved.is_dir():
        _fail("unsafe_path", f"{label} must resolve to a directory below its root")
    return pure.as_posix(), resolved


def validate_acceptance_input(value: Any, *, manual: bool) -> dict[str, Any]:
    root = _closed(value, INPUT_KEYS, "input")
    if root.get("schema_version") != INPUT_SCHEMA:
        _fail("input_schema", f"input.schema_version must be {INPUT_SCHEMA}")
    for key in (
        "acceptance_id",
        "runner_id",
        "runner_session_id",
        "runner_invocation_id",
        "measurement_plan_path",
        "replay_receipt_path",
    ):
        _text(root.get(key), f"input.{key}")
    if manual is not True or root.get("manual_confirmation") is not True:
        _fail(
            "manual_confirmation_required",
            "both --manual and input.manual_confirmation=true are required; this runner never creates sessions",
        )

    attempts = root.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        _fail("attempts_required", "input.attempts must be a non-empty array")
    attempt_ids: set[str] = set()
    session_ids: set[str] = set()
    invocation_ids: set[str] = set()
    artifact_ids: set[str] = set()
    for index, raw_attempt in enumerate(attempts):
        location = f"input.attempts[{index}]"
        attempt = _closed(raw_attempt, ATTEMPT_KEYS, location)
        attempt_id = _text(attempt.get("attempt_id"), f"{location}.attempt_id")
        session_id = _text(attempt.get("session_id"), f"{location}.session_id")
        invocation_id = _text(attempt.get("invocation_id"), f"{location}.invocation_id")
        if attempt_id in attempt_ids:
            _fail("duplicate_attempt", f"duplicate attempt_id: {attempt_id}")
        if session_id in session_ids:
            _fail("session_reuse", f"session_id must be fresh and unique: {session_id}")
        if invocation_id in invocation_ids:
            _fail("invocation_reuse", f"invocation_id must be unique: {invocation_id}")
        attempt_ids.add(attempt_id)
        session_ids.add(session_id)
        invocation_ids.add(invocation_id)
        arm = attempt.get("arm")
        if not isinstance(arm, str) or arm not in ALLOWED_ARMS:
            _fail("attempt_arm", f"{location}.arm must be one of {sorted(ALLOWED_ARMS)}")
        if attempt.get("agent_kind") != "ai-agent" or attempt.get("scripted") is not False:
            _fail("real_ai_required", f"{location} must describe a non-scripted ai-agent session")
        for key in ("run_path", "outcome", "usage_receipt_path", "session_receipt_path"):
            _text(attempt.get(key), f"{location}.{key}")
        if arm == "control":
            if attempt.get("candidate_sha256") is not None:
                _fail("control_candidate", f"{location}.candidate_sha256 must be null")
        else:
            _digest(attempt.get("candidate_sha256"), f"{location}.candidate_sha256")
        _digest(attempt.get("common_condition_sha256"), f"{location}.common_condition_sha256")
        parent = attempt.get("supersedes_attempt_id")
        reason = attempt.get("repair_reason")
        if parent is None:
            if reason is not None:
                _fail("repair_ancestry", f"{location}.repair_reason must be null without a parent")
        else:
            _text(parent, f"{location}.supersedes_attempt_id")
            _text(reason, f"{location}.repair_reason")
        evidence = attempt.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            _fail("evidence_required", f"{location}.evidence must be a non-empty array")
        for evidence_index, raw_artifact in enumerate(evidence):
            artifact_location = f"{location}.evidence[{evidence_index}]"
            artifact = _closed(raw_artifact, EVIDENCE_KEYS, artifact_location)
            artifact_id = _text(artifact.get("artifact_id"), f"{artifact_location}.artifact_id")
            _text(artifact.get("kind"), f"{artifact_location}.kind")
            _text(artifact.get("path"), f"{artifact_location}.path")
            if artifact_id in artifact_ids:
                _fail("duplicate_artifact", f"duplicate artifact_id: {artifact_id}")
            artifact_ids.add(artifact_id)

    by_attempt = {item["attempt_id"]: item for item in attempts}
    attempt_order = {item["attempt_id"]: index for index, item in enumerate(attempts)}
    for index, attempt in enumerate(attempts):
        parent = attempt.get("supersedes_attempt_id")
        if parent is None:
            continue
        previous = by_attempt.get(parent)
        if (
            previous is None
            or previous.get("arm") != attempt.get("arm")
            or attempt_order.get(parent, index) >= index
        ):
            _fail(
                "repair_ancestry",
                f"input.attempts[{index}].supersedes_attempt_id must resolve an earlier same-arm attempt",
            )

    pairs = root.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        _fail("pairs_required", "input.pairs must be a non-empty array")
    pair_ids: set[str] = set()
    for index, raw_pair in enumerate(pairs):
        location = f"input.pairs[{index}]"
        pair = _closed(raw_pair, PAIR_KEYS, location)
        pair_id = _text(pair.get("pair_id"), f"{location}.pair_id")
        if pair_id in pair_ids:
            _fail("duplicate_pair", f"duplicate pair_id: {pair_id}")
        pair_ids.add(pair_id)
        for key in ("builder_attempt_id", "treatment_attempt_id", "control_attempt_id"):
            ref = _text(pair.get(key), f"{location}.{key}")
            if ref not in attempt_ids:
                _fail("pair_attempt_join", f"{location}.{key} does not resolve: {ref}")
        for key in ("candidate_sha256", "common_condition_sha256"):
            _digest(pair.get(key), f"{location}.{key}")
    return root


def measurement_plan() -> dict[str, Any]:
    return {
        "schema_version": runtime.MEASUREMENT_PLAN_SCHEMA,
        "usage_receipt_schema": runtime.USAGE_RECEIPT_SCHEMA,
        "package_cost_schema": runtime.PACKAGE_COST_SCHEMA,
        "required_usage_stages": list(runtime.USAGE_STAGES),
        "raw_evidence_profile": "complete-digest-bound",
        "independent_replay_required": True,
    }


def _common_conditions(run: dict[str, Any], *, evaluator_sha256: str) -> dict[str, Any]:
    """Project closed nuisance variables only after evaluator identity is resolved."""

    runtime_record = run["runtime"]
    # A complete WorldRef includes run_id, so distinct experimental RUN records
    # cannot truthfully share one.  The paired-condition projection removes only
    # that per-run identity; it is not represented as a WorldRef or WorldSpan.
    world_comparison = dict(run["world_ref"])
    world_comparison.pop("run_id", None)
    return {
        "task_sha256": run["task_ref"]["task_sha256"],
        "world_comparison_sha256": exogenous_registry.canonical_sha256(
            world_comparison
        ),
        "provider": runtime_record["provider"],
        "model": runtime_record["model"],
        "runtime": runtime_record["runtime"],
        "profile_sha256": runtime_record["profile_sha256"],
        "tools_sha256": runtime_record["tools_sha256"],
        "network_access": runtime_record["network_access"],
        "budget_sha256": runtime_record["budget_sha256"],
        "stopping_rule_sha256": runtime_record["stopping_rule_sha256"],
        "evaluator_sha256": evaluator_sha256,
        "trial": run["trial"],
        "seed": run["seed"],
    }


def _validate_exogenous_sources(
    value: dict[str, Any], *, exogenous_root: Path, method_index: Path,
    plan: dict[str, Any], plan_sha256: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Derive record inputs only from full catalog, STUDY, and RUN validation."""

    exogenous_root = exogenous_root.resolve(strict=True)
    method_index = method_index.resolve(strict=True)
    method_report, method_versions = exogenous_registry.load_method_catalog(method_index)
    registry_report, summaries = exogenous_registry.collect_registry(
        exogenous_root, method_versions=method_versions
    )
    errors = list(method_report.errors) + list(registry_report.errors)
    if errors:
        _fail("exogenous_validation_failed", "; ".join(errors[:8]))
    valid_run_ids = {item.get("run_id") for item in summaries}
    run_records: dict[str, dict[str, Any]] = {}
    run_paths: dict[str, Path] = {}
    run_reports: dict[str, Any] = {}
    run_by_attempt: dict[str, str] = {}
    study_objects: dict[str, tuple[Path, dict[str, Any]]] = {}

    for index, attempt in enumerate(value["attempts"]):
        relative, run_root = safe_directory(
            exogenous_root, attempt["run_path"],
            label=f"input.attempts[{index}].run_path",
        )
        if PurePosixPath(relative).parts[:1] != ("runs",):
            _fail("run_path", "run paths must be below exogenous/runs")
        run_path = run_root / "RUN.json"
        if run_path.is_symlink() or not run_path.is_file():
            _fail("run_path", f"{relative}/RUN.json must be a regular file")
        direct_report, run = exogenous_registry.validate_run(run_root)
        if run is None or not direct_report.ok:
            _fail("run_validation_failed", "; ".join(direct_report.errors[:8]))
        run_id = str(run.get("run_id"))
        if run_id not in valid_run_ids:
            _fail("run_not_registry_validated", f"RUN {run_id!r} failed full registry validation")
        if relative != f"runs/{run_id}":
            _fail(
                "run_path",
                f"attempt RUN path must be the exact registry member runs/{run_id}",
            )
        if run.get("schema_version") != exogenous_registry.RUN_SCHEMA:
            _fail("run_schema", "acceptance requires exogenous RUN v2")
        if run.get("status") != "completed":
            _fail("run_status", f"RUN {run_id!r} must be completed")
        if run.get("measurement_plan") != plan or direct_report.facts.get("measurement_plan_sha256") != plan_sha256:
            _fail("run_plan_join", f"RUN {run_id!r} must contain the exact acceptance plan")
        if run.get("runtime", {}).get("executor_type") != "ai-agent":
            _fail("real_ai_required", f"RUN {run_id!r} is not an ai-agent RUN")
        expected_system = {"builder": "corridor", "treatment": "corridor", "control": "task-only"}[attempt["arm"]]
        if run.get("subject", {}).get("system_condition") != expected_system:
            _fail("run_arm_join", f"{attempt['arm']} must bind a {expected_system} RUN")
        if run_id in run_records and runtime.file_sha256(run_paths[run_id]) != runtime.file_sha256(run_path):
            _fail("run_id_collision", f"RUN id {run_id!r} resolves different bytes")
        run_records[run_id] = run
        run_paths[run_id] = run_path
        run_reports[run_id] = direct_report
        run_by_attempt[attempt["attempt_id"]] = run_id
        study_ref = run["study_ref"]
        _study_relative, study_path = safe_file(
            exogenous_root, study_ref["path"], label=f"RUN {run_id} study_ref.path"
        )
        if runtime.file_sha256(study_path) != study_ref["sha256"]:
            _fail("study_digest_join", f"RUN {run_id} does not bind actual STUDY bytes")
        study = load_closed_json(study_path, label=f"STUDY for {run_id}")
        study_objects[str(study["study_id"])] = (study_path, study)

    if len(study_objects) != 1:
        _fail("study_join", "all acceptance attempts must bind one validated STUDY")
    _study_id, (study_path, study) = next(iter(study_objects.items()))
    _taskset_relative, taskset_path = safe_file(
        exogenous_root, study["taskset_ref"]["path"], label="STUDY.taskset_ref.path"
    )
    taskset_report, taskset = exogenous_registry.validate_taskset(taskset_path, exogenous_root)
    if taskset is None or not taskset_report.ok:
        _fail("taskset_validation_failed", "; ".join(taskset_report.errors[:8]))
    study_report, validated_study = exogenous_registry.validate_study(
        study_path,
        exogenous_root,
        {str(taskset["taskset_id"]): (taskset_path, taskset)},
        method_versions=method_versions,
    )
    if validated_study is None or not study_report.ok:
        _fail("study_validation_failed", "; ".join(study_report.errors[:8]))
    if study_report.facts.get("formal_method_study_eligible") is not True:
        _fail("study_ineligible", "full STUDY validator did not establish study eligibility")

    evaluator_sha = exogenous_registry.canonical_sha256(taskset["evaluator"])
    common_by_run = {
        run_id: _common_conditions(run, evaluator_sha256=evaluator_sha)
        for run_id, run in run_records.items()
    }
    for attempt in value["attempts"]:
        run_id = run_by_attempt[attempt["attempt_id"]]
        if attempt["common_condition_sha256"] != runtime.sha256_json(common_by_run[run_id]):
            _fail("common_condition_join", f"attempt {attempt['attempt_id']} does not bind its RUN")

    conditions = {
        item["condition_id"]: item for item in study["conditions"] if isinstance(item, dict)
    }
    builder_runs = {
        run_by_attempt[item["attempt_id"]] for item in value["attempts"] if item["arm"] == "builder"
    }
    treatment_runs = {
        run_by_attempt[item["attempt_id"]] for item in value["attempts"] if item["arm"] == "treatment"
    }
    if not builder_runs <= treatment_runs:
        _fail("builder_run_join", "every builder must bind a treatment RUN")
    for pair in value["pairs"]:
        builder_run = run_by_attempt[pair["builder_attempt_id"]]
        treatment_run = run_by_attempt[pair["treatment_attempt_id"]]
        control_run = run_by_attempt[pair["control_attempt_id"]]
        if builder_run != treatment_run:
            _fail("builder_run_join", f"pair {pair['pair_id']} builder must bind treatment RUN")
        treatment = run_records[treatment_run]
        control = run_records[control_run]
        same_task = (
            treatment["task_ref"]["taskset_id"] == control["task_ref"]["taskset_id"]
            and treatment["task_ref"]["task_id"] == control["task_ref"]["task_id"]
        )
        same_study_inputs = (
            conditions[treatment["condition_id"]]["common_inputs_sha256"]
            == conditions[control["condition_id"]]["common_inputs_sha256"]
        )
        if (
            treatment_run == control_run
            or common_by_run[treatment_run] != common_by_run[control_run]
            or not same_task
            or not same_study_inputs
        ):
            _fail("pair_run_join", f"pair {pair['pair_id']} RUNs are not matched and distinct")

    treatment_condition_ids = {run_records[run_id]["condition_id"] for run_id in treatment_runs}
    method_refs = {
        runtime.sha256_json(conditions[condition_id]["method_paper_ref"]): conditions[condition_id]["method_paper_ref"]
        for condition_id in treatment_condition_ids
        if conditions.get(condition_id, {}).get("method_paper_ref") is not None
    }
    if len(method_refs) != 1:
        _fail("method_study_join", "treatment RUNs must bind one exact MethodRef")
    method_ref = next(iter(method_refs.values()))
    eligible_refs = study_report.facts.get("study_eligible_method_refs")
    matches = [item for item in eligible_refs if isinstance(item, dict) and all(
        item.get(key) == value for key, value in {
            "version_id": method_ref.get("version_id"),
            "source_commit": method_ref.get("source_commit"),
            "representation_path": method_ref.get("representation_path"),
            "content_sha256": method_ref.get("content_sha256"),
            "study_eligible": method_ref.get("study_eligible"),
            "adoption_eligible": method_ref.get("adoption_eligible"),
            "builder_eligible": method_ref.get("builder_eligible"),
        }.items()
    )] if isinstance(eligible_refs, list) else []
    if len(matches) != 1:
        _fail("method_eligibility_join", "MethodRef did not resolve one study-eligible validator fact")
    method_condition_id = matches[0]["condition_id"]
    catalog_matches = [item for item in method_versions if all(
        item.get(key) == value for key, value in {
            "version_id": method_ref.get("version_id"),
            "source_commit": method_ref.get("source_commit"),
            "path": method_ref.get("representation_path"),
            "content_sha256": method_ref.get("content_sha256"),
            "study_eligible": method_ref.get("study_eligible"),
            "adoption_eligible": method_ref.get("adoption_eligible"),
            "builder_eligible": method_ref.get("builder_eligible"),
        }.items()
    )]
    if len(catalog_matches) != 1:
        _fail("method_catalog_join", "MethodRef did not resolve one validated catalog entry")
    version = catalog_matches[0]
    method_binding = {
        "condition_id": method_condition_id,
        "study_id": study["study_id"],
        "study_schema_version": study["schema_version"],
        "study_sha256": runtime.file_sha256(study_path),
        "catalog_sha256": runtime.file_sha256(method_index),
        "version_id": version["version_id"],
        "status": version["status"],
        "source_commit": version["source_commit"],
        "representation_path": version["path"],
        "content_sha256": version["content_sha256"],
        "study_eligible": version["study_eligible"],
        "adoption_eligible": version["adoption_eligible"],
        "builder_eligible": version["builder_eligible"],
    }
    run_bindings = []
    for run_id in sorted(run_records):
        run = run_records[run_id]
        condition = conditions[run["condition_id"]]
        common = common_by_run[run_id]
        run_bindings.append(
            {
                "schema_version": run["schema_version"],
                "run_id": run_id,
                "run_sha256": runtime.file_sha256(run_paths[run_id]),
                "study_id": run["study_ref"]["study_id"],
                "study_sha256": run["study_ref"]["sha256"],
                "condition_id": run["condition_id"],
                "taskset_id": run["task_ref"]["taskset_id"],
                "task_id": run["task_ref"]["task_id"],
                "trial": run["trial"],
                "seed": run["seed"],
                "status": run["status"],
                "system_condition": condition["system_condition"],
                "knowledge_condition": condition["knowledge_condition"],
                "runner_id": run["runner_id"],
                "measurement_plan_sha256": plan_sha256,
                "common_conditions": common,
                "common_condition_sha256": runtime.sha256_json(common),
            }
        )
    source_validation = {
        "schema_version": runtime.SOURCE_VALIDATION_SCHEMA,
        "catalog_schema_version": method_report.facts["schema_version"],
        "catalog_sha256": runtime.file_sha256(method_index),
        "catalog_selected_version": {
            key: version[key]
            for key in (
                "version_id", "status", "source_commit", "path", "content_sha256",
                "study_eligible", "adoption_eligible", "builder_eligible",
            )
        },
        "study_schema_version": study_report.facts["schema_version"],
        "study_id": study_report.facts["study_id"],
        "study_sha256": runtime.file_sha256(study_path),
        "formal_method_study_eligible": study_report.facts["formal_method_study_eligible"],
        "study_eligible_condition_ids": study_report.facts["study_eligible_condition_ids"],
        "study_eligible_method_refs": study_report.facts["study_eligible_method_refs"],
        "run_facts": [
            {
                "run_id": binding["run_id"],
                "schema_version": report.facts["schema_version"],
                "status": report.facts["status"],
                "run_sha256": report.facts["run_sha256"],
                "study_id": run_records[binding["run_id"]]["study_ref"]["study_id"],
                "study_sha256": run_records[binding["run_id"]]["study_ref"]["sha256"],
                "condition_id": run_records[binding["run_id"]]["condition_id"],
                "measurement_plan_sha256": report.facts["measurement_plan_sha256"],
                "measurement_plan_complete": report.facts["measurement_plan_complete"],
                "common_condition_sha256": binding["common_condition_sha256"],
                "run_binding_sha256": runtime.sha256_json(binding),
            }
            for binding in run_bindings
            for report in (run_reports[binding["run_id"]],)
        ],
    }
    return (
        {
            "run_bindings": run_bindings,
            "method_binding": method_binding,
            "source_validation": source_validation,
        },
        {
            attempt_id: {
                **run_records[run_id],
                "__run_sha256": runtime.file_sha256(run_paths[run_id]),
            }
            for attempt_id, run_id in run_by_attempt.items()
        },
    )


def validate_exogenous_sources(
    value: dict[str, Any], *, exogenous_root: Path, method_index: Path,
    plan: dict[str, Any], plan_sha256: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate and project exogenous inputs without leaking canonical failures."""

    try:
        return _validate_exogenous_sources(
            value,
            exogenous_root=exogenous_root,
            method_index=method_index,
            plan=plan,
            plan_sha256=plan_sha256,
        )
    except AcceptanceInputError:
        raise
    except (OverflowError, RecursionError, TypeError, UnicodeError, ValueError) as exc:
        _fail(
            "canonical_json",
            f"exogenous evidence cannot be canonically hashed: {type(exc).__name__}",
        )


def load_session_receipt(
    source: dict[str, Any], *, evidence_root: Path, assembler: dict[str, str],
    forbidden_issuer_values: set[str],
) -> tuple[str, str, Path]:
    relative, path = safe_file(
        evidence_root,
        source["session_receipt_path"],
        label=f"session receipt for {source['attempt_id']}",
    )
    receipt = _closed(
        load_closed_json(path, label=f"session receipt for {source['attempt_id']}"),
        SESSION_RECEIPT_KEYS,
        "session receipt",
    )
    if receipt.get("schema_version") != runtime.SESSION_RECEIPT_SCHEMA:
        _fail("session_receipt_schema", "session receipt schema is not supported")
    for key in (
        "receipt_id", "issuer_id", "issuer_session_id", "issuer_invocation_id",
        "attempt_id", "session_id", "invocation_id", "agent_kind",
    ):
        _text(receipt.get(key), f"session receipt.{key}")
    if (
        receipt["attempt_id"] != source["attempt_id"]
        or receipt["session_id"] != source["session_id"]
        or receipt["invocation_id"] != source["invocation_id"]
        or receipt["agent_kind"] != source["agent_kind"]
        or receipt["scripted"] is not source["scripted"]
    ):
        _fail("session_receipt_join", "session receipt does not bind the exact attempt")
    forbidden = forbidden_issuer_values | {
        assembler["runner_id"], assembler["session_id"], assembler["invocation_id"],
        source["session_id"], source["invocation_id"],
    }
    if any(
        receipt[key] in forbidden
        for key in ("issuer_id", "issuer_session_id", "issuer_invocation_id")
    ):
        _fail(
            "session_receipt_independence",
            "session receipt issuer must differ from assembler and bound agent session",
        )
    return relative, runtime.file_sha256(path), path


def collect_evidence(
    value: dict[str, Any], *, evidence_root: Path,
    run_by_attempt: dict[str, dict[str, Any]], assembler: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Path]]:
    artifacts: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    session_receipt_paths: set[Path] = set()
    session_receipt_digests: set[str] = set()
    forbidden_issuer_values = {
        assembler["runner_id"], assembler["session_id"], assembler["invocation_id"],
        *[item["session_id"] for item in value["attempts"]],
        *[item["invocation_id"] for item in value["attempts"]],
        *[item["runner_id"] for item in run_by_attempt.values()],
    }
    for attempt_index, source in enumerate(value["attempts"]):
        artifact_ids: list[str] = []
        for artifact_index, spec in enumerate(source["evidence"]):
            label = f"input.attempts[{attempt_index}].evidence[{artifact_index}].path"
            relative, path = safe_file(evidence_root, spec["path"], label=label)
            artifact_id = spec["artifact_id"]
            artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "kind": spec["kind"],
                    "path": relative,
                    "content_sha256": runtime.file_sha256(path),
                    "attempt_id": source["attempt_id"],
                }
            )
            paths[artifact_id] = path
            artifact_ids.append(artifact_id)
        session_receipt_relative, session_receipt_sha256, session_receipt_path = load_session_receipt(
            source,
            evidence_root=evidence_root,
            assembler=assembler,
            forbidden_issuer_values=forbidden_issuer_values,
        )
        if (
            session_receipt_path in session_receipt_paths
            or session_receipt_sha256 in session_receipt_digests
        ):
            _fail("session_receipt_reuse", "each attempt requires a distinct session receipt")
        session_receipt_paths.add(session_receipt_path)
        session_receipt_digests.add(session_receipt_sha256)
        run = run_by_attempt[source["attempt_id"]]
        attempts.append(
            {
                "attempt_id": source["attempt_id"],
                "arm": source["arm"],
                "run_id": run["run_id"],
                "session_id": source["session_id"],
                "invocation_id": source["invocation_id"],
                "session_receipt_path": session_receipt_relative,
                "session_receipt_sha256": session_receipt_sha256,
                "agent_kind": source["agent_kind"],
                "scripted": source["scripted"],
                "candidate_sha256": source["candidate_sha256"],
                "common_condition_sha256": source["common_condition_sha256"],
                "artifact_ids": artifact_ids,
                "outcome": source["outcome"],
                "supersedes_attempt_id": source["supersedes_attempt_id"],
                "repair_reason": source["repair_reason"],
            }
        )
    return artifacts, attempts, paths


def load_replay_receipt(
    value: dict[str, Any], *, evidence_root: Path, record: dict[str, Any],
    clean_pair_ids: list[str],
) -> dict[str, Any]:
    _relative, path = safe_file(
        evidence_root, value["replay_receipt_path"], label="input.replay_receipt_path"
    )
    receipt = _closed(load_closed_json(path, label="replay receipt"), REPLAY_KEYS, "replay receipt")
    if receipt.get("schema_version") != REPLAY_RECEIPT_SCHEMA:
        _fail("replay_schema", f"replay receipt schema must be {REPLAY_RECEIPT_SCHEMA}")
    for key in (
        "replay_id", "verifier_id", "verifier_session_id", "verifier_invocation_id",
        "runner_id", "runner_session_id", "runner_invocation_id",
    ):
        _text(receipt.get(key), f"replay receipt.{key}")
    if (
        receipt["runner_id"] != value["runner_id"]
        or receipt["runner_session_id"] != value["runner_session_id"]
        or receipt["runner_invocation_id"] != value["runner_invocation_id"]
    ):
        _fail("replay_runner_join", "replay receipt must bind this runner invocation")
    if (
        receipt["verifier_id"] == receipt["runner_id"]
        or receipt["verifier_session_id"] == receipt["runner_session_id"]
        or receipt["verifier_invocation_id"] == receipt["runner_invocation_id"]
    ):
        _fail(
            "replay_independence",
            "replay verifier identity, session, and invocation must differ from the runner",
        )
    if receipt.get("verified") is not True:
        _fail("replay_not_verified", "replay receipt must carry a positive independent verdict")
    forbidden = {
        value["runner_id"], value["runner_session_id"], value["runner_invocation_id"],
        *[item["session_id"] for item in record["attempts"]],
        *[item["invocation_id"] for item in record["attempts"]],
        *[item["runner_id"] for item in record["run_bindings"]],
    }
    if any(
        receipt[key] in forbidden
        for key in ("verifier_id", "verifier_session_id", "verifier_invocation_id")
    ):
        _fail("replay_independence", "replay verifier must be independent of every session")
    expected_payload = runtime.sha256_json(runtime._replay_payload(record))
    expected_outcome = runtime.sha256_json(
        {
            "attempt_outcomes": [
                {"attempt_id": item["attempt_id"], "outcome": item["outcome"]}
                for item in sorted(record["attempts"], key=lambda item: item["attempt_id"])
            ],
            "clean_pair_ids": clean_pair_ids,
        }
    )
    if receipt.get("payload_sha256") != expected_payload:
        _fail("replay_payload_join", "replay receipt does not bind the complete canonical payload")
    if receipt.get("outcome_sha256") != expected_outcome:
        _fail("replay_outcome_join", "replay receipt does not bind outcomes and clean pairs")
    return {
        **receipt,
        "receipt_path": value["replay_receipt_path"],
        "receipt_sha256": runtime.file_sha256(path),
    }


def load_usage_receipts(
    value: dict[str, Any], *, evidence_root: Path, plan_sha256: str,
    run_by_attempt: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    receipts: list[dict[str, Any]] = []
    costs: list[dict[str, Any]] = []
    for index, attempt in enumerate(value["attempts"]):
        _relative, path = safe_file(
            evidence_root,
            attempt["usage_receipt_path"],
            label=f"input.attempts[{index}].usage_receipt_path",
        )
        receipt = load_closed_json(path, label=f"usage receipt for {attempt['attempt_id']}")
        run = run_by_attempt[attempt["attempt_id"]]
        if (
            receipt.get("attempt_id") != attempt["attempt_id"]
            or receipt.get("session_id") != attempt["session_id"]
            or receipt.get("run_id") != run["run_id"]
            or receipt.get("run_sha256") != run["__run_sha256"]
        ):
            _fail("usage_attempt_join", f"usage receipt does not bind attempt {attempt['attempt_id']}")
        if receipt.get("measurement_plan_sha256") != plan_sha256:
            _fail("usage_plan_join", f"usage receipt does not bind the actual measurement plan")
        report = runtime.validate_usage_receipt(receipt)
        if not report.ok:
            _fail("usage_validation_failed", json.dumps(report.errors, sort_keys=True))
        if report.facts.get("usage_status") != "measured":
            _fail("usage_incomplete", f"usage receipt is incomplete for {attempt['attempt_id']}")
        receipts.append(receipt)
        costs.append(runtime.package_cost_from_usage(receipt))
    return receipts, costs


def derive_clean_pair_ids(
    pairs: list[dict[str, Any]], attempts: list[dict[str, Any]],
    run_bindings: list[dict[str, Any]], method_binding: dict[str, Any],
) -> list[str]:
    by_id = {item["attempt_id"]: item for item in attempts}
    runs = {item["run_id"]: item for item in run_bindings}
    used_sessions: set[str] = set()
    used_runs: set[str] = set()
    used_attempts: set[str] = set()
    used_assignments: set[tuple[str, str, int, str]] = set()
    clean_pair_ids: list[str] = []

    def lineage(attempt_id: str) -> list[str]:
        result: list[str] = []
        current: str | None = attempt_id
        seen: set[str] = set()
        while current is not None and current in by_id and current not in seen:
            seen.add(current)
            result.append(current)
            parent = by_id[current].get("supersedes_attempt_id")
            current = parent if isinstance(parent, str) else None
        result.reverse()
        return result

    for source in pairs:
        refs = [source["builder_attempt_id"], source["treatment_attempt_id"], source["control_attempt_id"]]
        selected = [by_id[ref] for ref in refs]
        lineages = [lineage(ref) for ref in refs]
        lineage_ids = [attempt_id for branch in lineages for attempt_id in branch]
        lineage_attempts = [by_id[attempt_id] for attempt_id in lineage_ids]
        sessions = [item["session_id"] for item in lineage_attempts]
        lineage_runs = {item["run_id"] for item in lineage_attempts}
        lineage_assignments = {
            (
                runs[run_id]["taskset_id"],
                runs[run_id]["task_id"],
                runs[run_id]["trial"],
                runs[run_id]["seed"],
            )
            for run_id in lineage_runs
            if run_id in runs
        }
        builder, treatment, control = selected
        treatment_run = treatment["run_id"]
        control_run = control["run_id"]
        clean = len(lineage_ids) == len(set(lineage_ids))
        clean = clean and len(set(sessions)) == len(lineage_ids)
        clean = clean and not any(item in used_sessions for item in sessions)
        clean = clean and not (set(lineage_ids) & used_attempts)
        clean = clean and [item["arm"] for item in selected] == ["builder", "treatment", "control"]
        clean = clean and builder["run_id"] == treatment_run
        clean = clean and treatment_run != control_run and not (lineage_runs & used_runs)
        clean = clean and not (lineage_assignments & used_assignments)
        clean = clean and builder["candidate_sha256"] == treatment["candidate_sha256"] == source["candidate_sha256"]
        clean = clean and all(item["common_condition_sha256"] == source["common_condition_sha256"] for item in selected)
        clean = clean and all(item["outcome"] == "passed" for item in selected)
        treatment_binding = runs.get(treatment_run)
        control_binding = runs.get(control_run)
        clean = clean and treatment_binding is not None and control_binding is not None
        if treatment_binding is not None and control_binding is not None:
            clean = clean and treatment_binding["system_condition"] == "corridor"
            clean = clean and treatment_binding["knowledge_condition"] == "method-paper"
            clean = clean and control_binding["system_condition"] == "task-only"
            clean = clean and control_binding["knowledge_condition"] == "task-only"
            clean = clean and treatment_binding["common_conditions"] == control_binding["common_conditions"]
            clean = clean and treatment_binding["taskset_id"] == control_binding["taskset_id"]
            clean = clean and treatment_binding["task_id"] == control_binding["task_id"]
            clean = clean and treatment_binding["condition_id"] == method_binding["condition_id"]
            clean = clean and treatment_binding["study_id"] == method_binding["study_id"]
            clean = clean and treatment_binding["study_sha256"] == method_binding["study_sha256"]
            clean = clean and control_binding["study_id"] == method_binding["study_id"]
            clean = clean and control_binding["study_sha256"] == method_binding["study_sha256"]
        if clean:
            clean_pair_ids.append(source["pair_id"])
            used_sessions.update(sessions)
            used_runs.update(lineage_runs)
            used_attempts.update(lineage_ids)
            used_assignments.update(lineage_assignments)
    return sorted(clean_pair_ids)


def assemble_record_payload(
    value: dict[str, Any], *, evidence_root: Path, exogenous_root: Path, method_index: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the replay-covered payload without inventing a verifier receipt.

    A separate verifier invocation can use this deterministic projection to compute
    ``_replay_payload`` and its outcome digest, issue the receipt file, and only then
    invoke :func:`build_record` for the trusted final validation.
    """

    plan_relative, plan_path = safe_file(
        evidence_root, value["measurement_plan_path"], label="input.measurement_plan_path"
    )
    del plan_relative
    plan = load_closed_json(plan_path, label="measurement plan")
    if plan != measurement_plan():
        _fail("measurement_plan", "measurement plan must equal the CL-014 fixed plan")
    plan_sha = runtime.sha256_json(plan)
    bindings, run_by_attempt = validate_exogenous_sources(
        value,
        exogenous_root=exogenous_root,
        method_index=method_index,
        plan=plan,
        plan_sha256=plan_sha,
    )
    assembler = {
        "runner_id": value["runner_id"],
        "session_id": value["runner_session_id"],
        "invocation_id": value["runner_invocation_id"],
    }
    artifacts, attempts, _paths = collect_evidence(
        value,
        evidence_root=evidence_root,
        run_by_attempt=run_by_attempt,
        assembler=assembler,
    )
    receipts, costs = load_usage_receipts(
        value,
        evidence_root=evidence_root,
        plan_sha256=plan_sha,
        run_by_attempt=run_by_attempt,
    )
    record: dict[str, Any] = {
        "schema_version": runtime.ACCEPTANCE_RECORD_SCHEMA,
        "acceptance_id": value["acceptance_id"],
        "assembler": assembler,
        "source_validation_sha256": runtime.sha256_json(bindings["source_validation"]),
        "run_bindings": bindings["run_bindings"],
        "method_binding": bindings["method_binding"],
        "measurement_plan": plan,
        "usage_receipts": receipts,
        "package_costs": costs,
        "raw_evidence": artifacts,
        "independent_replay": {},
        "attempts": attempts,
        "pairs": [dict(item) for item in value["pairs"]],
        "gate": {},
    }
    return record, bindings["source_validation"]


def build_record(
    value: dict[str, Any], *, evidence_root: Path, exogenous_root: Path, method_index: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    record, source_validation = assemble_record_payload(
        value,
        evidence_root=evidence_root,
        exogenous_root=exogenous_root,
        method_index=method_index,
    )
    clean_pair_ids = derive_clean_pair_ids(
        record["pairs"], record["attempts"], record["run_bindings"], record["method_binding"]
    )
    record["independent_replay"] = load_replay_receipt(
        value,
        evidence_root=evidence_root,
        record=record,
        clean_pair_ids=clean_pair_ids,
    )
    trusted_context = runtime.trusted_context_from_verified_sources(record, source_validation)
    return record, trusted_context


def validate_record(
    record: dict[str, Any], *, trusted_context: dict[str, Any], evidence_root: Path
) -> runtime.ValidationReport:
    clean_pair_ids = derive_clean_pair_ids(
        record["pairs"], record["attempts"], record["run_bindings"], record["method_binding"]
    )
    record["gate"] = runtime.acceptance_gate_for_verified_inputs(
        clean_pair_ids=clean_pair_ids,
        replay_verified=True,
        trusted_inputs_verified=True,
    )
    try:
        return runtime.validate_acceptance_record(
            record, trusted_context=trusted_context, evidence_root=evidence_root
        )
    except TypeError as exc:
        _fail("runtime_api_unavailable", f"acceptance validator lacks trusted-context API: {exc}")


def write_new_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail("output_exists", "refusing to replace an acceptance record; choose a new output path")
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        _fail("output_parent", "output parent must be an existing regular directory")
    data = runtime.canonical_json_bytes(value) + b"\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError:
        _fail("output_exists", "refusing to replace an acceptance record; choose a new output path")
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def run(args: argparse.Namespace) -> dict[str, Any]:
    value = validate_acceptance_input(
        load_closed_json(Path(args.input), label="acceptance input"), manual=args.manual
    )
    record, trusted_context = build_record(
        value,
        evidence_root=Path(args.evidence_root),
        exogenous_root=Path(args.exogenous_root),
        method_index=Path(args.method_index),
    )
    report = validate_record(
        record, trusted_context=trusted_context, evidence_root=Path(args.evidence_root)
    )
    if not report.ok:
        _fail("acceptance_validation_failed", json.dumps(report.errors, sort_keys=True))
    if record.get("gate", {}).get("formal_comparison_ready") is not False:
        _fail("claim_boundary", "formal_comparison_ready must remain false")
    if record.get("gate", {}).get("benchmark_result") is not False:
        _fail("claim_boundary", "benchmark_result must remain false")
    if record.get("gate", {}).get("causal_claim_allowed") is not False:
        _fail("claim_boundary", "causal_claim_allowed must remain false")
    if record.get("gate", {}).get("adoption_claim_allowed") is not False:
        _fail("claim_boundary", "adoption_claim_allowed must remain false")
    if record.get("gate", {}).get("authority_warranty_state") != "not_assessed":
        _fail("claim_boundary", "authority_warranty_state must remain not_assessed")
    write_new_atomic(Path(args.output), record)
    return {
        "ok": True,
        "output": str(Path(args.output)),
        "acceptance_sha256": runtime.sha256_json(record),
        "instrumented_acceptance_pilot_ready": record["gate"].get(
            "instrumented_acceptance_pilot_ready", False
        ),
        "formal_comparison_ready": False,
        "benchmark_result": False,
        "causal_claim_allowed": False,
        "adoption_claim_allowed": False,
        "authority_warranty_state": "not_assessed",
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually assemble a no-model/no-network CL-014 acceptance record."
    )
    parser.add_argument("--manual", action="store_true", help="confirm sessions already exist")
    parser.add_argument("--input", required=True, help="charting-loop/acceptance-input/v1 JSON")
    parser.add_argument("--evidence-root", required=True, help="root for safe-relative evidence paths")
    parser.add_argument("--exogenous-root", required=True, help="full exogenous registry root")
    parser.add_argument("--method-index", required=True, help="validated method VERSIONS.json")
    parser.add_argument("--output", required=True, help="new acceptance record path")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(make_parser().parse_args(argv))
    except AcceptanceInputError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as exc:  # fail closed without a traceback or output
        print(
            json.dumps(
                {"ok": False, "code": "runner_internal_error", "message": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
