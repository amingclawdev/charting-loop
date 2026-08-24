"""Pure prompt and evidence contracts for the full-method benchmark agent.

Nothing in this module imports Harbor.  The split is intentional: public tests can
verify the scientific contract without installing or authenticating a benchmark
runtime, while ``harbor_agent.py`` remains a thin orchestration adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import textwrap
from pathlib import Path
from typing import Any

from corridor_kit.acceptance import (
    MAX_QA_JSON_BYTES,
    QA_ASSESSMENT_SCHEMA,
    load_qa_json_text,
    validate_qa_assessment as validate_corridor_qa_assessment,
)
from corridor_kit.scaffold import method_capsule
from corridor_kit.core import regular_tree_digest, regular_tree_manifest


RUNTIME_ROOT = "/tmp/charting-loop"
SDK_ROOT = "/opt/charting-loop-sdk"
SDK_PACKAGE_PATH = f"{SDK_ROOT}/corridor_kit"
POSITION_ROOT = "/tmp/charting-loop-position"
POSITION_PATH = f"{POSITION_ROOT}/POSITION.jsonl"
METHOD_PATH = f"{RUNTIME_ROOT}/method/METHOD.md"
CORRIDOR_PATH = f"{RUNTIME_ROOT}/corridor"
GRAPH_PATH = f"{CORRIDOR_PATH}/GRAPH.jsonl"
STUDY_PROFILE_PATH = f"{CORRIDOR_PATH}/STUDY.json"
TYPED_RULE_IR_PATH = f"{CORRIDOR_PATH}/TYPED-RULE-IR-FIRST.json"
TYPED_RULE_REPORT_PATH = f"{CORRIDOR_PATH}/TYPED-RULE-COMPILE-FIRST.json"
EXECUTION_TEST_ROOT = f"{RUNTIME_ROOT}/execution-tests"
EXECUTION_TEST_QA_PATH = f"{RUNTIME_ROOT}/qa/execution-test-audit.json"
ACCEPTANCE_PATH = f"{CORRIDOR_PATH}/ACCEPTANCE.json"
WORK_PATH = f"{CORRIDOR_PATH}/WORK_ITEMS.json"
CAPABILITIES_PATH = f"{CORRIDOR_PATH}/CAPABILITIES.json"
FREEZE_PATH = f"{RUNTIME_ROOT}/FREEZE.json"
QA_PATH = f"{RUNTIME_ROOT}/qa/assessment.json"
CLOSURE_PATH = f"{RUNTIME_ROOT}/qa/closure.json"
WORKER_FACTS_PATH = "/tmp/charting-loop-worker-fact-candidates.json"
SUBMISSION_ROOT = "/logs/agent/submissions"

FREEZE_SCHEMA = "charting-loop/frozen-task-corridor/v2"
ACCEPTANCE_SCHEMA = "charting-loop/task-acceptance-ledger/v2"
ASSESSMENT_SCHEMA = QA_ASSESSMENT_SCHEMA
QA_OUTCOMES = frozenset({"pass", "fail", "blocked", "not_assessed"})
ACCEPTANCE_APPLICABILITY = frozenset(
    {"applicable", "not_applicable", "unknown"}
)
ACCEPTANCE_STATES = frozenset({"pass", "fail", "unknown", "not_reached"})
CONSTRUCTION_READINESS_STATES = frozenset({"ready", "unresolved"})
ASSESSMENT_CLOSURE_STATES = frozenset({"complete", "incomplete"})
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
METHOD_VERSION_ID = "charting-loop-method-v8"
METHOD_CONTENT_SHA256 = (
    "sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446"
)
METHOD_SCOPE_SHA256 = (
    "sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af"
)
GRAPH_STUDY_SCHEMA = "charting-loop/method-guided-graph-study/v2"
GRAPH_AUDIT_SCHEMA = "charting-loop/graph-path-audit/v2"
RULE_COMPILE_AUDIT_SCHEMA = "charting-loop/rule-compile-audit/v1"
RULE_COMPILE_FAILURE_AUDIT_SCHEMA = "charting-loop/rule-compile-failure-audit/v1"
EXECUTION_TEST_AUDIT_SCHEMA = "charting-loop/execution-test-audit/v1"
VERIFIER_ALIGNMENT_SCHEMA = "charting-loop/verifier-alignment/v1"
PRE_VERIFIER_ROOT_SCHEMA = "charting-loop/pre-verifier-root/v1"
VERIFIER_ORDER_RECEIPT_SCHEMA = "charting-loop/verifier-order-receipt/v1"
VERIFIER_ALIGNMENT_CLASSIFICATIONS = frozenset(
    {
        "aligned",
        "compile_gap",
        "execution_gap",
        "verifier_undercoverage",
        "evaluator_mismatch",
        "unresolved",
    }
)
NEUTRAL_GRAPH_INSTRUCTION = (
    "Use the supplied task-neutral graph utilities as optional note-taking tools. "
    "The official task remains the only task authority. Inspect live state, choose "
    "your own plan, verify changes, preserve a usable result before the deadline, "
    "and do not treat graph structure as correctness or completion evidence."
)
NEUTRAL_GRAPH_INSTRUCTION_SHA256 = "sha256:" + hashlib.sha256(
    NEUTRAL_GRAPH_INSTRUCTION.encode("utf-8")
).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON value for stable content-addressing."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def pre_verifier_root_manifest(
    *, frozen_artifacts: dict[str, str], runner_ref: str
) -> dict[str, Any]:
    """Freeze the runner-owned, pre-verifier analysis boundary."""

    if not isinstance(frozen_artifacts, dict) or "submission" not in frozen_artifacts:
        raise ValueError("pre-verifier root requires a submission artifact")
    if any(
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(digest, str)
        or SHA256_RE.fullmatch(digest) is None
        for name, digest in frozen_artifacts.items()
    ):
        raise ValueError("pre-verifier artifacts must map names to sha256 digests")
    if not isinstance(runner_ref, str) or not runner_ref.strip():
        raise ValueError("runner_ref must be non-empty text")
    manifest = {
        "schema_version": PRE_VERIFIER_ROOT_SCHEMA,
        "actor_role": "runner",
        "runner_ref": runner_ref,
        "frozen_artifacts": dict(sorted(frozen_artifacts.items())),
    }
    manifest["root_digest"] = sha256_bytes(canonical_json_bytes(manifest))
    return manifest


def verifier_order_receipt(
    *,
    pre_verifier_root_digest: str,
    verifier_input_digest: str,
    verifier_output_digest: str,
    runner_ref: str,
) -> dict[str, Any]:
    """Bind the one legal runner order without making it a runtime Gate."""

    for name, value in (
        ("pre_verifier_root_digest", pre_verifier_root_digest),
        ("verifier_input_digest", verifier_input_digest),
        ("verifier_output_digest", verifier_output_digest),
    ):
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            raise ValueError(f"{name} must be a sha256 digest")
    if not isinstance(runner_ref, str) or not runner_ref.strip():
        raise ValueError("runner_ref must be non-empty text")
    receipt = {
        "schema_version": VERIFIER_ORDER_RECEIPT_SCHEMA,
        "actor_role": "runner",
        "runner_ref": runner_ref,
        "event_order": [
            "pre_verifier_root_frozen",
            "agent_returned",
            "official_verifier_started",
            "official_verifier_finished",
            "posthoc_alignment_started",
        ],
        "pre_verifier_root_digest": pre_verifier_root_digest,
        "verifier_input_digest": verifier_input_digest,
        "verifier_output_digest": verifier_output_digest,
    }
    receipt["receipt_digest"] = sha256_bytes(canonical_json_bytes(receipt))
    return receipt


def verifier_alignment_record(
    *,
    pre_verifier_manifest: dict[str, Any],
    verifier_identity: str,
    verifier_version: str,
    verifier_input_digest: str,
    verifier_output_digest: str,
    order_receipt: dict[str, Any],
    classification: str,
    observations: list[str],
) -> dict[str, Any]:
    """Record post-hoc verifier comparison without feeding it into Rule authority."""

    if classification not in VERIFIER_ALIGNMENT_CLASSIFICATIONS:
        raise ValueError("unknown verifier-alignment classification")
    for name, value in (
        ("verifier_input_digest", verifier_input_digest),
        ("verifier_output_digest", verifier_output_digest),
    ):
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            raise ValueError(f"{name} must be a sha256 digest")
    for name, value in (
        ("verifier_identity", verifier_identity),
        ("verifier_version", verifier_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty text")
    if not isinstance(observations, list) or any(
        not isinstance(item, str) or not item.strip() for item in observations
    ):
        raise ValueError("verifier-alignment observations must be a text list")
    expected_manifest = pre_verifier_root_manifest(
        frozen_artifacts=pre_verifier_manifest.get("frozen_artifacts", {}),
        runner_ref=pre_verifier_manifest.get("runner_ref", ""),
    )
    if pre_verifier_manifest != expected_manifest:
        raise ValueError("pre_verifier_manifest is not a canonical runner root")
    if expected_manifest["frozen_artifacts"]["submission"] != verifier_input_digest:
        raise ValueError("verifier input differs from the frozen submission")
    expected_receipt = verifier_order_receipt(
        pre_verifier_root_digest=expected_manifest["root_digest"],
        verifier_input_digest=verifier_input_digest,
        verifier_output_digest=verifier_output_digest,
        runner_ref=order_receipt.get("runner_ref", ""),
    )
    if order_receipt != expected_receipt:
        raise ValueError("order_receipt does not prove the post-hoc runner order")
    record = {
        "schema_version": VERIFIER_ALIGNMENT_SCHEMA,
        "pre_verifier_manifest": pre_verifier_manifest,
        "verifier_identity": verifier_identity,
        "verifier_version": verifier_version,
        "verifier_input_digest": verifier_input_digest,
        "verifier_output_digest": verifier_output_digest,
        "order_receipt": order_receipt,
        "classification": classification,
        "observations": observations,
        "read_only": True,
        "rule_source": False,
        "authorizes_rule_mutation": False,
        "authorizes_task_mutation": False,
        "blocking_gate": False,
        "analysis_isolation": {
            "namespace": "posthoc_verifier_alignment",
            "importable_into_rule_graph": False,
            "available_to_fresh_task_context": False,
        },
    }
    record["record_digest"] = sha256_bytes(canonical_json_bytes(record))
    return record


def custody_provenance(source_kind: str, *, direct_byte_match: bool) -> dict[str, Any]:
    """Classify custody honestly; reconstruction is never called a download."""

    direct = source_kind == "direct_runtime_capture"
    recovered = source_kind == "recovered_from_builder_events"
    return {
        "source_kind": source_kind,
        "custody_status": (
            "direct"
            if direct and direct_byte_match
            else "digest_mismatch"
            if direct
            else "recovered"
            if recovered
            else "capture_failed"
        ),
        "direct_byte_match": direct and direct_byte_match,
        "recovered": recovered,
        "direct_download": direct and direct_byte_match,
    }


def private_custody_program(
    *,
    agent_dir: str,
    expected_corridor_digest: str,
    runtime_root: str = RUNTIME_ROOT,
    position_path: str = POSITION_PATH,
    submission_root: str = SUBMISSION_ROOT,
) -> str:
    """Return a teardown-safe private capture program for benchmark evidence."""

    return textwrap.dedent(
        f"""
        import hashlib
        import json
        import os
        import shutil
        import stat
        import tempfile
        from datetime import datetime, timezone
        from pathlib import Path
        from corridor_kit.core import regular_tree_manifest

        agent_dir = Path({agent_dir!r})
        runtime_root = Path({runtime_root!r})
        position_path = Path({position_path!r})
        submission_root = Path({submission_root!r})
        expected_digest = {expected_corridor_digest!r}
        target = agent_dir / "corridor-custody"

        def digest(data):
            return "sha256:" + hashlib.sha256(data).hexdigest()

        def canonical(value):
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")

        def corridor_identity(root):
            tree = regular_tree_manifest(root)
            if not tree["files"]:
                raise ValueError("archived Corridor is empty")
            return tree["files"], tree["tree_digest"]

        def file_manifest(root):
            if root.is_symlink() or not root.is_dir():
                raise ValueError("custody target must be a real directory")
            records = []
            for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
                if path.is_symlink():
                    raise ValueError(f"custody symlink is forbidden: {{path}}")
                if path.is_dir() or path == root / "custody-manifest.json":
                    continue
                if not path.is_file():
                    raise ValueError(f"custody special file is forbidden: {{path}}")
                data = path.read_bytes()
                records.append({{
                    "path": path.relative_to(root).as_posix(),
                    "bytes": len(data),
                    "sha256": digest(data),
                }})
            return records

        if target.exists() or target.is_symlink():
            try:
                if target.is_symlink() or not target.is_dir():
                    raise ValueError("existing private custody target is unsafe")
                manifest_path = target / "custody-manifest.json"
                manifest_bytes = manifest_path.read_bytes()

                def reject_duplicates(pairs):
                    value = {{}}
                    for key, item in pairs:
                        if key in value:
                            raise ValueError(f"duplicate manifest key: {{key}}")
                        value[key] = item
                    return value

                existing = json.loads(
                    manifest_bytes.decode("utf-8"),
                    object_pairs_hook=reject_duplicates,
                    parse_constant=lambda item: (_ for _ in ()).throw(
                        ValueError(f"non-finite manifest value: {{item}}")
                    ),
                )
                if not isinstance(existing, dict):
                    raise ValueError("existing private custody manifest is invalid")
                corridor_files, copied_digest = corridor_identity(
                    target / "frozen-corridor"
                )
                records = file_manifest(target)
                expected_fields = {{
                    "schema_version": "charting-loop/benchmark-private-custody/v1",
                    "private": True,
                    "public_release_allowed": False,
                    "source_kind": "direct_runtime_capture",
                    "custody_status": "direct",
                    "direct_byte_match": True,
                    "direct_download": True,
                    "recovered": False,
                    "expected_corridor_digest": expected_digest,
                    "copied_corridor_digest": copied_digest,
                    "corridor_files": corridor_files,
                    "files": records,
                    "tree_digest": digest(canonical(records)),
                    "builder_recovery_evidence": "roles/builder",
                }}
                if set(existing) != set(expected_fields) | {{"captured_at"}}:
                    raise ValueError("existing custody manifest fields mismatch")
                captured_at = existing.get("captured_at")
                if (
                    not isinstance(captured_at, str)
                    or not captured_at.endswith("Z")
                ):
                    raise ValueError("existing custody captured_at is invalid")
                datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                if manifest_bytes != canonical(existing) + b"\\n":
                    raise ValueError("existing custody manifest is not canonical")
                for key, value in expected_fields.items():
                    if existing.get(key) != value:
                        raise ValueError(f"existing custody mismatch: {{key}}")
                if copied_digest != expected_digest:
                    raise ValueError("existing custody Corridor digest mismatch")
                for required_path in (
                    target / "FREEZE.json",
                    target / "POSITION.jsonl",
                    target / "roles" / "builder",
                    target / "submission-manifests",
                ):
                    if required_path.is_symlink() or not required_path.exists():
                        raise ValueError(
                            f"existing custody surface missing: {{required_path.name}}"
                        )
                print(json.dumps({{
                    "ok": True,
                    **existing,
                    "already_captured": True,
                    "preserved_existing": True,
                    "existing_bytes_revalidated": True,
                }}, sort_keys=True))
            except Exception as exc:
                print(json.dumps({{
                    "ok": False,
                    "schema_version": "charting-loop/benchmark-private-custody/v1",
                    "private": True,
                    "public_release_allowed": False,
                    "source_kind": "direct_runtime_capture_failed",
                    "custody_status": "capture_failed",
                    "direct_byte_match": False,
                    "direct_download": False,
                    "recovered": False,
                    "expected_corridor_digest": expected_digest,
                    "error_type": type(exc).__name__,
                    "existing_bytes_revalidated": False,
                    "preserved_existing": True,
                    "builder_recovery_evidence": "../phases/builder",
                }}, sort_keys=True))
            raise SystemExit(0)

        staging = Path(tempfile.mkdtemp(prefix=".corridor-custody-", dir=agent_dir))

        def copy_regular_tree(source, destination, predicate=lambda path: True):
            if source.is_symlink() or not source.is_dir():
                raise ValueError(f"custody source must be a real directory: {{source}}")
            destination.mkdir(parents=True, exist_ok=True)
            for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
                if path.is_symlink():
                    raise ValueError(f"custody symlink is forbidden: {{path}}")
                relative = path.relative_to(source)
                if path.is_dir():
                    continue
                if not path.is_file():
                    raise ValueError(f"custody special file is forbidden: {{path}}")
                if not predicate(path):
                    continue
                output = destination / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, output)
                os.chmod(output, stat.S_IMODE(path.stat().st_mode) & 0o777)

        try:
            copy_regular_tree(runtime_root / "corridor", staging / "frozen-corridor")
            shutil.copyfile(runtime_root / "FREEZE.json", staging / "FREEZE.json")
            shutil.copyfile(position_path, staging / "POSITION.jsonl")
            copy_regular_tree(agent_dir / "phases", staging / "roles")
            copy_regular_tree(
                submission_root,
                staging / "submission-manifests",
                lambda path: path.name == "manifest.json"
                or (path.parent.name == "latest" and path.suffix == ".json"),
            )
            corridor_files, copied_digest = corridor_identity(staging / "frozen-corridor")
            direct_match = copied_digest == expected_digest
            records = file_manifest(staging)
            manifest = {{
                "schema_version": "charting-loop/benchmark-private-custody/v1",
                "private": True,
                "public_release_allowed": False,
                "source_kind": "direct_runtime_capture",
                "custody_status": "direct" if direct_match else "digest_mismatch",
                "direct_byte_match": direct_match,
                "direct_download": direct_match,
                "recovered": False,
                "expected_corridor_digest": expected_digest,
                "copied_corridor_digest": copied_digest,
                "corridor_files": corridor_files,
                "files": records,
                "tree_digest": digest(canonical(records)),
                "builder_recovery_evidence": "roles/builder",
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }}
            (staging / "custody-manifest.json").write_bytes(canonical(manifest) + b"\\n")
            if target.exists() or target.is_symlink():
                raise ValueError("private custody target appeared during capture")
            os.replace(staging, target)
            print(json.dumps({{"ok": direct_match, **manifest}}, sort_keys=True))
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            failure = {{
                "schema_version": "charting-loop/benchmark-private-custody/v1",
                "private": True,
                "public_release_allowed": False,
                "source_kind": "direct_runtime_capture_failed",
                "custody_status": "capture_failed",
                "direct_byte_match": False,
                "direct_download": False,
                "recovered": False,
                "expected_corridor_digest": expected_digest,
                "error_type": type(exc).__name__,
                "builder_recovery_evidence": "../phases/builder",
            }}
            if not target.exists() and not target.is_symlink():
                target.mkdir(parents=True)
                (target / "custody-manifest.json").write_bytes(
                    canonical(failure) + b"\\n"
                )
            else:
                failure["preserved_existing"] = True
            print(json.dumps({{"ok": False, **failure}}, sort_keys=True))
        """
    )


def corridor_manifest(corridor: Path) -> list[dict[str, Any]]:
    """Return the deterministic regular-file manifest used by the freezer.

    Symlinks and special files are rejected because a frozen Corridor must be a
    closed byte set.  Directories are structural and are not separately hashed.
    """

    try:
        files = regular_tree_manifest(corridor)["files"]
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    if not files:
        raise ValueError("corridor contains no regular files")
    return files


def corridor_digest(files: list[dict[str, Any]]) -> str:
    """Digest a manifest, including relative paths, sizes, and file hashes."""

    return regular_tree_digest(files)


def freeze_program(runtime_root: str = RUNTIME_ROOT) -> str:
    """Return the root-run program that closes and freezes the Builder output.

    A missing or unsafe Builder output is replaced by an explicit fallback record.
    This keeps the benchmark trial progressing without pretending construction
    succeeded.  The fallback is visible to both downstream roles and in FREEZE.json.
    """

    expected_capsule = method_capsule(
        method_version=METHOD_VERSION_ID,
        method_digest=METHOD_CONTENT_SHA256,
        method_scope_digest=METHOD_SCOPE_SHA256,
    )
    expected_capsule_digest = sha256_bytes(canonical_json_bytes(expected_capsule))

    return textwrap.dedent(
        f"""
        import hashlib
        import json
        import os
        import shutil
        import stat
        from pathlib import Path
        from corridor_kit.core import purge_python_caches, regular_tree_manifest

        root = Path({runtime_root!r})
        corridor = root / "corridor"
        method = root / "method" / "METHOD.md"
        freeze = root / "FREEZE.json"
        schema = {FREEZE_SCHEMA!r}
        expected_capsule = {expected_capsule!r}
        expected_capsule_digest = {expected_capsule_digest!r}

        def digest(data):
            return "sha256:" + hashlib.sha256(data).hexdigest()

        def canonical(value):
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")

        def scan():
            purge_python_caches(corridor)
            tree = regular_tree_manifest(corridor)
            if not tree["files"]:
                raise ValueError("corridor contains no regular files")
            return tree

        def strict_json(path):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"regular JSON file required: {{path.name}}")

            def reject_duplicates(pairs):
                value = {{}}
                for key, item in pairs:
                    if key in value:
                        raise ValueError(f"duplicate key: {{key}}")
                    value[key] = item
                return value

            return json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=reject_duplicates,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ValueError(f"non-finite value: {{item}}")
                ),
            )

        def summarize_method_capsule():
            summary = {{
                "status": "missing",
                "expected_digest": expected_capsule_digest,
                "actual_digest": None,
                "stored_digest": None,
                "stored_digest_matches_actual": False,
                "errors": [],
            }}
            try:
                capsule = strict_json(corridor / "METHOD-CAPSULE.json")
            except Exception as exc:
                summary["errors"].append(
                    f"METHOD_CAPSULE_JSON:{{type(exc).__name__}}"
                )
                return summary
            if not isinstance(capsule, dict):
                summary["status"] = "invalid"
                summary["errors"].append("METHOD_CAPSULE_OBJECT_REQUIRED")
                return summary
            try:
                summary["actual_digest"] = digest(canonical(capsule))
            except Exception as exc:
                summary["status"] = "invalid"
                summary["errors"].append(
                    f"METHOD_CAPSULE_CANONICAL:{{type(exc).__name__}}"
                )
                return summary
            if capsule != expected_capsule:
                summary["errors"].append("METHOD_CAPSULE_CONTENT_MISMATCH")
            if summary["actual_digest"] != expected_capsule_digest:
                summary["errors"].append("METHOD_CAPSULE_DIGEST_MISMATCH")
            try:
                kit = strict_json(corridor / "KIT.json")
            except Exception as exc:
                summary["errors"].append(f"KIT_JSON:{{type(exc).__name__}}")
                kit = None
            if not isinstance(kit, dict):
                summary["errors"].append("KIT_OBJECT_REQUIRED")
            else:
                summary["stored_digest"] = kit.get("method_capsule_digest")
                summary["stored_digest_matches_actual"] = (
                    summary["stored_digest"] == summary["actual_digest"]
                )
                if not summary["stored_digest_matches_actual"]:
                    summary["errors"].append(
                        "METHOD_CAPSULE_STORED_DIGEST_MISMATCH"
                    )
            summary["status"] = "complete" if not summary["errors"] else "invalid"
            return summary

        def summarize_acceptance():
            path = corridor / "ACCEPTANCE.json"
            summary = {{
                "status": "missing",
                "schema_version": None,
                "acceptance_ids": [],
                "required_acceptance_ids": [],
                "unmapped_count": 0,
                "ambiguous_count": 0,
                "ambiguous_acceptance_ids": [],
                "source_mapping_status": "unknown",
                "definition_closure_status": "unknown",
                "construction_readiness_status": "unknown",
                "coupled_acceptance_ids": [],
                "unresolved_constraints": [],
                "errors": [],
            }}
            if path.is_symlink() or not path.is_file():
                summary["errors"].append("ACCEPTANCE_LEDGER_MISSING")
                return summary

            def reject_duplicates(pairs):
                value = {{}}
                for key, item in pairs:
                    if key in value:
                        raise ValueError(f"duplicate key: {{key}}")
                    value[key] = item
                return value

            try:
                ledger = json.loads(
                    path.read_text(encoding="utf-8"),
                    object_pairs_hook=reject_duplicates,
                    parse_constant=lambda item: (_ for _ in ()).throw(
                        ValueError(f"non-finite value: {{item}}")
                    ),
                )
            except Exception as exc:
                summary["status"] = "invalid"
                summary["errors"].append(
                    f"ACCEPTANCE_LEDGER_JSON:{{type(exc).__name__}}"
                )
                return summary

            if not isinstance(ledger, dict):
                summary["status"] = "invalid"
                summary["errors"].append("ACCEPTANCE_LEDGER_OBJECT_REQUIRED")
                return summary
            summary["schema_version"] = ledger.get("schema_version")
            if ledger.get("schema_version") != {ACCEPTANCE_SCHEMA!r}:
                summary["errors"].append("ACCEPTANCE_LEDGER_SCHEMA")

            coverage = ledger.get("coverage")
            if not isinstance(coverage, dict):
                summary["errors"].append("ACCEPTANCE_COVERAGE_OBJECT_REQUIRED")
                coverage = {{}}
            coverage_status = coverage.get("status")
            if coverage_status not in ("complete", "incomplete"):
                summary["errors"].append("ACCEPTANCE_COVERAGE_STATUS")
            for field in ("unmapped_clauses", "ambiguous_clauses"):
                values = coverage.get(field)
                if not isinstance(values, list):
                    summary["errors"].append(
                        "ACCEPTANCE_" + field.upper() + "_LIST_REQUIRED"
                    )
                    values = []
                summary[
                    "unmapped_count"
                    if field == "unmapped_clauses"
                    else "ambiguous_count"
                ] = len(values)
                for index, value in enumerate(values):
                    if not isinstance(value, dict):
                        summary["errors"].append(
                            f"ACCEPTANCE_{{field.upper()}}_{{index}}"
                        )
                        continue
                    for required_field in ("source_ref", "statement", "reason"):
                        item = value.get(required_field)
                        if not isinstance(item, str) or not item.strip():
                            summary["errors"].append(
                                f"ACCEPTANCE_{{field.upper()}}_"
                                f"{{required_field.upper()}}_{{index}}"
                            )

            items = ledger.get("items")
            if not isinstance(items, list) or not items:
                summary["errors"].append("ACCEPTANCE_ITEMS_NONEMPTY_LIST_REQUIRED")
                items = []
            seen = set()
            relation_targets = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    summary["errors"].append(f"ACCEPTANCE_ITEM_{{index}}")
                    continue
                acceptance_id = item.get("acceptance_id")
                if not isinstance(acceptance_id, str) or not acceptance_id.strip():
                    summary["errors"].append(f"ACCEPTANCE_ID_{{index}}")
                    continue
                if acceptance_id in seen:
                    summary["errors"].append(
                        f"ACCEPTANCE_ID_DUPLICATE:{{acceptance_id}}"
                    )
                    continue
                seen.add(acceptance_id)
                summary["acceptance_ids"].append(acceptance_id)
                if item.get("required") is True:
                    summary["required_acceptance_ids"].append(acceptance_id)
                elif item.get("required") is not False:
                    summary["errors"].append(
                        f"ACCEPTANCE_REQUIRED_BOOLEAN:{{acceptance_id}}"
                    )
                for field in ("source_ref", "statement"):
                    value = item.get(field)
                    if not isinstance(value, str) or not value.strip():
                        summary["errors"].append(
                            f"ACCEPTANCE_{{field.upper()}}:{{acceptance_id}}"
                        )
                if item.get("definition_state") not in (
                    "defined",
                    "ambiguous",
                ):
                    summary["errors"].append(
                        f"ACCEPTANCE_DEFINITION_STATE:{{acceptance_id}}"
                    )
                elif item.get("definition_state") == "ambiguous":
                    summary["ambiguous_acceptance_ids"].append(acceptance_id)
                for field in ("scope", "rule"):
                    value = item.get(field)
                    if not isinstance(value, dict) or not value:
                        summary["errors"].append(
                            f"ACCEPTANCE_{{field.upper()}}:{{acceptance_id}}"
                        )
                obligations = item.get("verification_obligations")
                obligation_kinds = (
                    "positive",
                    "negative",
                    "boundary",
                    "state",
                    "temporal",
                    "coupled",
                )
                if not isinstance(obligations, dict) or set(obligations) != set(obligation_kinds):
                    summary["errors"].append(
                        f"ACCEPTANCE_VERIFICATION_OBLIGATIONS:{{acceptance_id}}"
                    )
                    obligations = {{}}
                for obligation_kind in obligation_kinds:
                    values = obligations.get(obligation_kind)
                    if not isinstance(values, list) or not values or any(
                        not isinstance(value, str) or not value.strip()
                        for value in values
                    ):
                        summary["errors"].append(
                            f"ACCEPTANCE_VERIFICATION_{{obligation_kind.upper()}}:{{acceptance_id}}"
                        )
                relations = item.get("relations")
                if not isinstance(relations, list):
                    summary["errors"].append(
                        f"ACCEPTANCE_RELATIONS:{{acceptance_id}}"
                    )
                    continue
                for relation_index, relation in enumerate(relations):
                    if not isinstance(relation, dict):
                        summary["errors"].append(
                            f"ACCEPTANCE_RELATION_{{acceptance_id}}_"
                            f"{{relation_index}}"
                        )
                        continue
                    if relation.get("type") not in (
                        "requires",
                        "subsumes",
                        "overlaps",
                        "conflicts",
                        "derived_from",
                    ):
                        summary["errors"].append(
                            f"ACCEPTANCE_RELATION_TYPE:{{acceptance_id}}"
                        )
                    target = relation.get("target_id")
                    if not isinstance(target, str) or not target.strip():
                        summary["errors"].append(
                            f"ACCEPTANCE_RELATION_TARGET:{{acceptance_id}}"
                        )
                    else:
                        relation_targets.append((acceptance_id, target))
            for source, target in relation_targets:
                if target not in seen:
                    summary["errors"].append(
                        f"ACCEPTANCE_RELATION_UNKNOWN:{{source}}:{{target}}"
                    )

            if coverage_status == "complete" and summary["unmapped_count"]:
                summary["errors"].append(
                    "ACCEPTANCE_COMPLETE_MAPPING_HAS_UNMAPPED_CLAUSES"
                )
            if coverage_status == "incomplete" and not summary["unmapped_count"]:
                summary["errors"].append(
                    "ACCEPTANCE_INCOMPLETE_MAPPING_NEEDS_UNMAPPED_CLAUSE"
                )
            summary["source_mapping_status"] = (
                "complete"
                if coverage_status == "complete" and not summary["unmapped_count"]
                else "incomplete"
            )
            summary["definition_closure_status"] = (
                "complete"
                if not summary["ambiguous_count"]
                and not summary["ambiguous_acceptance_ids"]
                else "incomplete"
            )

            readiness = ledger.get("construction_readiness")
            if not isinstance(readiness, dict):
                summary["errors"].append(
                    "ACCEPTANCE_CONSTRUCTION_READINESS_OBJECT_REQUIRED"
                )
                readiness = {{}}
            readiness_status = readiness.get("status")
            summary["construction_readiness_status"] = (
                readiness_status if isinstance(readiness_status, str) else "unknown"
            )
            if readiness_status not in ("ready", "unresolved"):
                summary["errors"].append(
                    "ACCEPTANCE_CONSTRUCTION_READINESS_STATUS"
                )
            coupled_ids = readiness.get("coupled_acceptance_ids")
            if not isinstance(coupled_ids, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in coupled_ids
            ):
                summary["errors"].append(
                    "ACCEPTANCE_COUPLED_IDS_LIST_REQUIRED"
                )
                coupled_ids = []
            elif len(set(coupled_ids)) != len(coupled_ids):
                summary["errors"].append("ACCEPTANCE_COUPLED_IDS_DUPLICATE")
            summary["coupled_acceptance_ids"] = coupled_ids
            for acceptance_id in coupled_ids:
                if acceptance_id not in seen:
                    summary["errors"].append(
                        f"ACCEPTANCE_COUPLED_ID_UNKNOWN:{{acceptance_id}}"
                    )
            unresolved = readiness.get("unresolved_constraints")
            if not isinstance(unresolved, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in unresolved
            ):
                summary["errors"].append(
                    "ACCEPTANCE_UNRESOLVED_CONSTRAINTS_LIST_REQUIRED"
                )
                unresolved = []
            summary["unresolved_constraints"] = unresolved
            replay_entrypoint = readiness.get("replay_entrypoint")
            if readiness_status == "ready":
                if unresolved:
                    summary["errors"].append(
                        "ACCEPTANCE_READY_WITH_UNRESOLVED_CONSTRAINTS"
                    )
                if coupled_ids and (
                    not isinstance(replay_entrypoint, str)
                    or not replay_entrypoint.strip()
                ):
                    summary["errors"].append(
                        "ACCEPTANCE_COUPLED_REPLAY_ENTRYPOINT_REQUIRED"
                    )
                if summary["source_mapping_status"] != "complete":
                    summary["errors"].append(
                        "ACCEPTANCE_READY_REQUIRES_SOURCE_MAPPING"
                    )
                if summary["definition_closure_status"] != "complete":
                    summary["errors"].append(
                        "ACCEPTANCE_READY_REQUIRES_DEFINITION_CLOSURE"
                    )
            elif readiness_status == "unresolved" and not unresolved:
                summary["errors"].append(
                    "ACCEPTANCE_UNRESOLVED_REASON_REQUIRED"
                )

            if summary["errors"]:
                summary["status"] = "invalid"
            elif (
                summary["source_mapping_status"] == "complete"
                and summary["definition_closure_status"] == "complete"
            ):
                summary["status"] = "complete"
            else:
                summary["status"] = "incomplete"
            return summary

        root.mkdir(parents=True, exist_ok=True)
        status = "frozen"
        failure = None
        try:
            tree = scan()
        except Exception as exc:
            status = "fallback"
            failure = f"{{type(exc).__name__}}: {{exc}}"[:1000]
            if corridor.is_symlink():
                corridor.unlink()
            elif corridor.exists():
                shutil.rmtree(corridor)
            corridor.mkdir(parents=True, exist_ok=True)
            (corridor / "CORRIDOR.md").write_text(
                "# Corridor construction unavailable\\n\\n"
                "The Builder did not leave a safe, non-empty Corridor. "
                "Worker and QA receive this same frozen failure record.\\n",
                encoding="utf-8",
            )
            tree = scan()

        files = tree["files"]

        acceptance = summarize_acceptance()
        capsule = summarize_method_capsule()
        manifest = {{
            "schema_version": schema,
            "builder_corridor_status": status,
            "builder_failure": failure,
            "method_sha256": digest(method.read_bytes()) if method.is_file() else None,
            "corridor_tree_sha256": tree["tree_digest"],
            "corridor_exclusion_policy": tree["exclusion_policy"],
            "method_capsule": capsule,
            "acceptance_ledger": acceptance,
            "files": files,
        }}
        freeze.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\\n",
            encoding="utf-8",
        )

        # Root ownership plus world-readable closed modes lets downstream roles use
        # the same files even when Harbor runs them as a non-root user. Executable
        # Builder tools remain executable; ordinary files never gain that bit.
        for path in [corridor, *sorted(corridor.rglob("*")), freeze, method]:
            if not path.exists() or path.is_symlink():
                continue
            current = stat.S_IMODE(path.stat().st_mode)
            if path.is_dir():
                mode = 0o555
            elif path in (freeze, method):
                mode = 0o444
            else:
                mode = 0o555 if current & 0o111 else 0o444
            os.chmod(path, mode)
            try:
                os.chown(path, 0, 0)
            except PermissionError:
                pass

        print(json.dumps({{
            "ok": True,
            "corridor_digest": manifest["corridor_tree_sha256"],
            "builder_corridor_status": status,
            "method_capsule_status": capsule["status"],
            "method_capsule_errors": capsule["errors"],
            "method_capsule_digest": capsule["actual_digest"],
            "method_capsule_expected_digest": capsule["expected_digest"],
            "method_capsule_stored_digest": capsule["stored_digest"],
            "method_capsule_digest_matches_stored": capsule[
                "stored_digest_matches_actual"
            ],
            "acceptance_ledger_status": acceptance["status"],
            "acceptance_ids": acceptance["acceptance_ids"],
            "required_acceptance_ids": acceptance["required_acceptance_ids"],
            "acceptance_ledger_errors": acceptance["errors"],
            "source_mapping_status": acceptance["source_mapping_status"],
            "definition_closure_status": acceptance[
                "definition_closure_status"
            ],
            "unmapped_count": acceptance["unmapped_count"],
            "ambiguous_count": acceptance["ambiguous_count"],
            "ambiguous_acceptance_ids": acceptance[
                "ambiguous_acceptance_ids"
            ],
            "construction_readiness_status": acceptance[
                "construction_readiness_status"
            ],
            "coupled_acceptance_ids": acceptance["coupled_acceptance_ids"],
            "unresolved_constraints": acceptance["unresolved_constraints"],
            "file_count": len(files),
        }}, sort_keys=True))
        """
    ).strip()


def verify_freeze_program(runtime_root: str = RUNTIME_ROOT) -> str:
    """Return a read-only probe that recomputes the frozen Corridor digest."""

    return textwrap.dedent(
        f"""
        import hashlib
        import json
        import stat
        from pathlib import Path
        from corridor_kit.core import TREE_EXCLUSION_POLICY, regular_tree_manifest

        root = Path({runtime_root!r})
        corridor = root / "corridor"
        freeze = root / "FREEZE.json"

        def digest(data):
            return "sha256:" + hashlib.sha256(data).hexdigest()

        def canonical(value):
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")

        manifest = json.loads(freeze.read_text(encoding="utf-8"))
        violations = []
        if corridor.is_symlink() or not corridor.is_dir():
            violations.append("corridor_not_real_directory")
        else:
            for path in sorted(corridor.rglob("*"), key=lambda p: p.as_posix()):
                if path.is_symlink():
                    violations.append("symlink:" + path.as_posix())
                    continue
                if path.is_dir():
                    if stat.S_IMODE(path.stat().st_mode) & 0o222:
                        violations.append("writable:" + path.as_posix())
                    if stat.S_IMODE(path.stat().st_mode) & 0o055 != 0o055:
                        violations.append("not_traversable:" + path.as_posix())
                    continue
                if not path.is_file():
                    violations.append("special:" + path.as_posix())
                    continue
                if stat.S_IMODE(path.stat().st_mode) & 0o222:
                    violations.append("writable:" + path.as_posix())
                if stat.S_IMODE(path.stat().st_mode) & 0o044 != 0o044:
                    violations.append("not_readable:" + path.as_posix())
                relative = path.relative_to(corridor)
                if "__pycache__" in relative.parts or relative.suffix in (".pyc", ".pyo"):
                    violations.append("excluded_cache_present:" + relative.as_posix())

        try:
            tree = regular_tree_manifest(corridor)
            files = tree["files"]
            actual = tree["tree_digest"]
        except Exception as exc:
            files = []
            actual = None
            violations.append("manifest_error:" + type(exc).__name__)
        expected = manifest.get("corridor_tree_sha256")
        if files != manifest.get("files"):
            violations.append("manifest_file_mismatch")
        if actual != expected:
            violations.append("corridor_digest_mismatch")
        if manifest.get("corridor_exclusion_policy") != list(TREE_EXCLUSION_POLICY):
            violations.append("corridor_exclusion_policy_mismatch")
        if stat.S_IMODE(freeze.stat().st_mode) & 0o222:
            violations.append("freeze_manifest_writable")
        print(json.dumps({{
            "ok": not violations,
            "corridor_digest": actual,
            "expected_digest": expected,
            "violations": violations,
        }}, sort_keys=True))
        raise SystemExit(0 if not violations else 2)
        """
    ).strip()


def remote_json_read_program(path: str) -> str:
    """Return a bounded JSON-file reader for an in-trial evidence artifact."""

    return textwrap.dedent(
        f"""
        from pathlib import Path
        path = Path({path!r})
        if path.is_symlink() or not path.is_file():
            raise SystemExit(2)
        if path.stat().st_size > {MAX_QA_JSON_BYTES}:
            raise SystemExit(3)
        print(path.read_text(encoding="utf-8"))
        """
    ).strip()


def _task_block(task_instruction: str) -> str:
    task = task_instruction.strip()
    return f"<official_task>\n{task}\n</official_task>"


def _frozen_method_block(method_text: str) -> str:
    """Embed the exact frozen Method bytes, rejecting summaries or revisions."""

    if not isinstance(method_text, str):
        raise ValueError("method_text must be the exact frozen Method text")
    if sha256_bytes(method_text.encode("utf-8")) != METHOD_CONTENT_SHA256:
        raise ValueError("method_text does not match the frozen Method digest")
    return (
        f'<frozen_method version="{METHOD_VERSION_ID}" sha256="{METHOD_CONTENT_SHA256}">\n'
        + method_text
        + "</frozen_method>"
    )


def graph_study_profile(
    *,
    arm: str,
    task_instruction: str,
    model_name: str,
    task_timeout_seconds: int,
    agent_version: str,
    kit_version: str,
    kit_tree_digest: str,
) -> dict[str, Any]:
    """Freeze the matched study identity; only the condition block varies by arm."""

    if arm not in {"method", "neutral"}:
        raise ValueError("graph study arm must be method or neutral")
    condition = (
        {
            "kind": "frozen_method",
            "version": METHOD_VERSION_ID,
            "digest": METHOD_CONTENT_SHA256,
            "scope_digest": METHOD_SCOPE_SHA256,
        }
        if arm == "method"
        else {
            "kind": "frozen_neutral_instruction",
            "version": "graph-neutral-v1",
            "digest": NEUTRAL_GRAPH_INSTRUCTION_SHA256,
            "scope_digest": None,
        }
    )
    profile = {
        "schema_version": GRAPH_STUDY_SCHEMA,
        "study_profile": "integrated_executor_authoring",
        "task_identity": sha256_bytes(task_instruction.strip().encode("utf-8")),
        "model_name": model_name,
        "task_timeout_seconds": task_timeout_seconds,
        "agent_version": agent_version,
        "kit_version": kit_version,
        "kit_tree_digest": kit_tree_digest,
        "roles": ["worker", "qa"],
        "task_clock_roles": ["worker", "qa"],
        "builder_present": False,
        "qa_schedule": "compile_candidate_then_each_worker_freeze",
        "qa_budget_is_separate": False,
        "qa_can_recommend_repair": True,
        "qa_can_repair": False,
        "repair_actor": "same_worker_session",
        "phase_time_allocations": None,
        "submission_rule": "latest_valid_worker_freeze_before_official_verifier",
        "official_verifier_schedule": "after_agent_return",
        "graph_is_advisory": True,
        "graph_authorizes_mutation": False,
        "condition": condition,
    }
    profile["profile_digest"] = sha256_bytes(canonical_json_bytes(profile))
    return profile


def _graph_condition_block(arm: str, method_text: str | None) -> str:
    if arm == "method":
        if method_text is None:
            raise ValueError("method arm requires exact Method text")
        return (
            "The following frozen Method is procedural guidance for diagnosing your "
            "own drift. It is not task authority, a stored answer, or a Gate.\n\n"
            + _frozen_method_block(method_text)
        )
    if arm == "neutral":
        if method_text is not None:
            raise ValueError("neutral arm must not receive Method text")
        return (
            '<frozen_neutral_instruction version="graph-neutral-v1" '
            f'sha256="{NEUTRAL_GRAPH_INSTRUCTION_SHA256}">\n'
            f"{NEUTRAL_GRAPH_INSTRUCTION}\n</frozen_neutral_instruction>"
        )
    raise ValueError("graph study arm must be method or neutral")


def graph_compile_probe_prompt(
    task_instruction: str,
    *,
    method_text: str,
    compiler_config_digest: str,
) -> str:
    """Return the isolated, non-scoring pre-experiment Rule compile probe."""

    return f"""You are an independent task-requirement compiler, not the task Worker.

{_task_block(task_instruction)}

Read only the public task above, every public authoritative source that it names, the
frozen Method below, and the documented `charting-loop/typed-rule-ir/v4` compiler
interface. Do not read any historical task
Graph, verifier output, prior result, or prior task transcript. Do not solve or mutate
the task and do not choose a Direction.

{_frozen_method_block(method_text)}

Emit exactly one first-attempt Typed Rule IR JSON object. Before authoring any Rule,
prepare the plane-typed AuthoritySnapshot for the runner to validate and freeze:
enumerate the normative Rule
plane, public task-world Fact material, and supporting inputs. Bind byte status, media
type, size and digest separately from semantic-extraction status, extractor identity,
and extraction-artifact digest. Readable bytes are not proof of successful extraction.
Declare source closure `complete` only when every normative source is byte-bound and
semantically extracted. Bind the exact source manifest and runner freeze receipt.
Independently enumerate every normative source clause in `source_clause_inventory`,
including nested, trailing, exception, and optional clauses. Give every clause a
unique stable `clause_order_key`; array position is display-only and never authority.
Reconstruct each clause from stable ordered half-open UTF-8 byte slices. Each slice
explicitly names either original source bytes or the digest-bound UTF-8 extraction
artifact; disjoint and cross-source slices are allowed. Mark each clause
`required` or `optional`; bind mapped clauses to exact Rule IDs, and retain every
unmapped, ambiguous, or unsupported clause as an explicit issue. Set `revision_kind`
to `first_attempt`, with no parent and no QA witness.

Every immutable RuleCandidate must retain its source-clause and slice bindings, labeling each slice's
semantic role. Its source-provenance digest must resolve through the clause identity,
order key, exact source digest, byte bounds, and slice digest. Every dependency must
declare either direct relationship slices or a
declared derivation over both current endpoint Rule provenance digests. Every
relationship must also declare endpoint semantics and an explicit alignment mode:
composable keyed joins, aggregate-to-member mapping, exact pairs, or source-backed
all-to-all. Include scope and per-endpoint cardinality; missing alignment emits no
v4 checklist edge. Bounds and
digests establish source identity, not semantic correctness. Every Rule must retain
its Rule kind, applicability predicate,
quantifier, and source-defined subject domain. Treat an open domain introduced by
words such as "including" as open; do not close a universal domain by enumerating only
the output you plan to produce. A collective ordering requirement such as "X first"
is not automatically a separate per-subject first requirement. Represent each true
conditional branch and expected outcome separately. Use `per_subject` projection only
when the source requires each subject independently. Temporal, transition, or coupled
Rules must type each condition as static, temporal, or state-transition; temporal
conditions retain their causal/ordering predicate and require an operator such as
`ordered_before`, `ordered_after`, `duration`, or `state_transition`; a timeless
set/union witness is not equivalent. Declare Rule dependencies with their semantic
relationship instead of relying on list order. Preserve ambiguity as an explicit
compile failure rather than weakening a Rule. Compare the compiler's reverse semantic
projection with the source slices. If SemanticDelta is non-empty, write a new immutable
`semantic_repair` revision and repeat; otherwise preserve an honest incomplete terminal
state. Typed Guidance is advisory and never becomes Rule authority.

Bind `method_digest` to `{METHOD_CONTENT_SHA256}` and `compiler_config_digest` to
`{compiler_config_digest}`. The caller will run:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit rules compile <ir.json>`

This is a diagnostic before the formal experiment. Preserve this immutable first
attempt separately from the independent source audit and any later semantic-repair IR.
Its IR is reviewed for compilation quality but is not injected into the later Worker.
If task-source interpretation or compiler bytes change after same-task verifier
feedback, classify the later run as `same_task_regression`, not fresh efficacy or
transfer evidence.
"""


def graph_worker_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    remaining_seconds: int,
    method_text: str | None,
) -> str:
    """Prompt stage one: the Worker compiles public authority, but does not implement."""

    condition = _graph_condition_block(arm, method_text)
    return f"""You are the Worker responsible for compiling the official task authority.

{_task_block(task_instruction)}

{condition}

There is no Builder phase and no precomputed task-specific Corridor. A byte-identical,
task-neutral Graph Kernel is available at `{SDK_PACKAGE_PATH}` in both study arms.
The frozen Study profile is `{STUDY_PROFILE_PATH}` with digest
`{study_profile_digest}`. The append-only execution graph is `{GRAPH_PATH}`.

This is stage 1 of one in-clock lifecycle. Do not implement, patch, or submit the
official task in this turn. The runner will construct and seal the candidate graph;
do not append runner- or QA-owned records yourself. First
compile the complete public task authority into `charting-loop/typed-rule-ir/v4`.
Write the immutable first attempt to `{TYPED_RULE_IR_PATH}` and run
`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit rules compile {TYPED_RULE_IR_PATH} > {TYPED_RULE_REPORT_PATH}`.
In the AuthoritySnapshot, enumerate the normative Rule plane, public task-world Fact
material, and supporting inputs. Propose byte status, media type, size and digest
separately from semantic-extraction status and extractor/artifact identity; an
unavailable source remains explicit and cannot carry invented bytes. The runner must
validate and append the complete snapshot as `authority_snapshot` before its exact
`task_source_artifact` records. A complete extraction artifact freezes its derived
UTF-8 bytes, digest, size, extractor, and source-byte digest; a source slice names
`source_bytes` or `extraction_artifact`. Independently
write `source_clause_inventory` with every normative clause—including trailing,
nested, exception, and optional clauses—before mapping clauses to Rules. Give every
clause a unique stable `clause_order_key`; array position is display-only and never
authority. Every clause uses stable, ordered, half-open UTF-8 byte slices; every Rule binds one or more of
those slices to explicit semantic roles (obligation, applicability, domain, condition,
outcome, quantifier, prohibition, witness/evidence requirement, or relationship). Multiple
disjoint and cross-source slices are allowed. A Rule provenance digest resolves these
bindings through the clause/order identity and exact source bytes. Do not report closed source coverage
while a named source is unavailable, malformed, or not digest-bound.

For each semantic Rule dependency, declare either direct provenance from relationship
slices or derived provenance from the exact current endpoint Rule provenance digests.
Also declare endpoint semantics, scope, cardinality and an explicit keyed,
aggregate-to-members, exact-pairs, or source-backed all-to-all alignment. Never infer
an edge from list order or an implicit Cartesian product. The runner will project the
returned `authority_snapshot_template`, `source_artifact_templates`,
`source_clause_templates`, and `rule_bodies` into a sealed candidate graph for QA.
Treat them as immutable RuleCandidates, not authority. Read the compiler's
reverse semantic projection and SemanticDelta back against exact source slices; if the
delta is non-empty, append a separate semantic-repair candidate revision and recompile.
The runner replays the IR and freezes the complete compiler output plus current Rule
record IDs as `rule_candidate_report`. QA returns a digest-bound
`rule_qa_assessment` against that existing report. Only a later authorized
runner/operator `rule_ratification` receipt may establish RuleClosure, and only when
the referenced report reproduces exactly, compilation is complete, all
SemanticDelta/coverage/alignment sets are empty, and that exact QA assessment passes.
Materialize every returned checklist
template with that current `source_rule_record_id`; do not merge subject/condition
coverage cells. Add `rule_dependency` edges using the returned semantic relationship,
edge provenance, and endpoint provenance digests. Then materialize every returned
`typed_dependency_template` with both current endpoint Rule record IDs so dependency
order is executable rather than implicit. A Rule revision makes ratification and dependent projections
stale until they are recomputed; changed source bytes require a new source identity.
Propose evidence as `fact_proposal`; for a typed checklist bind
`witness_bindings` to its checklist ID, Rule-semantics digest, and exact operators.
Admit evidence only through a current ratified admission Rule and an explicit
`fact_admission` receipt.

Keep universal domains source-defined: "including" is not a closed enumeration, and
the output you happen to produce cannot define the domain that the Rule is supposed
to check. Distinguish collective ordering from per-subject ordering, preserve temporal
and coupled predicates, and classify each clause and Rule as required or optional.
For a conditional optional checklist cell that truly does not apply, record
`applicability_status: not_applicable`, `status: unknown`, and an admitted Fact receipt
that proves the applicability predicate is false. Never treat omission as N/A.

Compile each current Rule into source-bound `acceptance_checklist_item` records.
Preserve its exact obligation, scope and quantifier, required behavioral partitions,
evidence requirement, and pass/fail/unknown decision rule; mark an incomplete or
ambiguous compilation honestly. Add `typed_dependency` records for normative,
work-row, and evidence dependencies. Only `requires`, `produces_fact_for`, and
`precondition_for` impose order; a conflict remains blocked until a current ratified
Rule authorizes a `dependency_resolution`. `requires` points from dependant to
prerequisite; `produces_fact_for` and `precondition_for` point from prerequisite to
dependant.

After RuleClosure exists, freeze the Direction datum, then append a whole-state
`position_checkpoint` that binds the current Rule records and RuleClosure digests,
admitted Fact receipts, task/world identity, scope, role
assignments, and known artifact revisions. Then write one or more
`direction_proposal` records against that exact Position and the same RuleClosure. You choose Direction; the
Kernel only checks identity and reference closure. A later QA reviews the path but
does not authoritatively choose Direction for you.

Before proposing Direction, query the one-shot bounded `active-context` pack. For
each relevant declared semantic edge, query `edge-source-trace` and compare its
declared relationship, endpoint Rule/checklist identities, source bindings or
derivation inputs, condition kinds, and witness obligations with the current
Position. Do not infer an expected relationship from Rule or condition kind: an
`unresolved` expectation remains unresolved. Direction carries no concrete action.
Each `semantic_bindings` entry uses exactly `position_ref`, `rule_id`,
`rule_record_id`, `semantic_edge_ids`, `checklist_item_id`, and
`witness_obligation_ids`. Select the later task action only after freezing this
Position-bound projection.

For new checkpoints, bind `checkpoint_kind` (`row_progress` or
`acceptance_assessment`), the whole current checklist, pass/fail/unknown assessments
and Fact-receipt witnesses, plus the recomputed ready, blocked, and unresolved
frontier. Bind those same checklist/frontier identities into every Direction. If an
upstream assessment changes, re-project downstream assessment and Direction instead
of carrying a stale completion claim forward.

Use:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph append {GRAPH_PATH} --type <record-type> --actor worker --body-file <json-file>`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph replay {GRAPH_PATH}`

Do not repeatedly rescan the JSONL chain to answer graph questions. Use the immutable,
digest-bound advisory index, for example:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph query {GRAPH_PATH} --kind topology`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph query {GRAPH_PATH} --kind prerequisites --ref <checklist-or-rule-id>`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph query {GRAPH_PATH} --kind explain-blocked --ref <checklist-id>`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph query {GRAPH_PATH} --kind active-context`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph query {GRAPH_PATH} --kind edge-source-trace --ref <semantic-edge-id>`

The query result is guidance only. It reports its logical graph digest, exact byte
digest, and head record ID; it cannot establish RuleClosure, choose Direction,
authorize mutation, or create a Gate.

Immediately before each submission freeze, run the deterministic read-only check:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph doctor {GRAPH_PATH}`

Its only classifications are `structurally_invalid`,
`structurally_valid_but_incomplete`, and `acceptance_assessed_complete`. The report
does not choose Direction or establish task truth, delivery authority, or PASS.

An invalid graph mutation fails closed and leaves graph bytes unchanged, but it is
advisory: correct the record or continue the official task. Never wait for graph
completeness, create a Gate, or infer truth/PASS from a structurally valid graph.
Do not build a task-specific harness unless the official task itself requires one.

About {remaining_seconds} seconds remain on the same total task clock. Finish
the complete IR and deterministic compile report early, then return immediately for
independent compilation QA. If QA rejects this exact candidate, the harness resumes
this same Worker session with the evidence and a new immutable output path. Only a
passing compilation advances to implementation.
"""


def graph_compile_qa_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    candidate_report_record_id: str,
    candidate_report_digest: str,
    remaining_seconds: int,
    method_text: str | None,
    graph_path: str,
    typed_rule_ir_path: str,
    typed_rule_ir_digest: str,
    typed_rule_ir_size: int,
    typed_rule_report_path: str,
    typed_rule_report_digest: str,
    typed_rule_report_size: int,
    qa_output_path: str,
    audit_iteration: int,
) -> str:
    """Prompt stage two: independent QA audits one sealed compilation candidate."""

    condition = _graph_condition_block(arm, method_text)
    return f"""You are the independent compilation QA reviewer.

{_task_block(task_instruction)}

{condition}

This is stage 2 of one in-clock lifecycle. The Worker has not implemented the task.
Audit the sealed candidate graph `{graph_path}` with graph digest `{graph_digest}`.
The candidate-root read-only typed Rule IR is `{typed_rule_ir_path}`
({typed_rule_ir_digest}, {typed_rule_ir_size} bytes). The candidate-root read-only
compiler report is `{typed_rule_report_path}` ({typed_rule_report_digest},
{typed_rule_report_size} bytes). Hash both files before reading them and reject any
identity mismatch. These canonical views are decoded from this exact frozen candidate;
do not read or trust mutable Worker output paths.
Replay it and run the read-only Doctor. Independently re-read every public authority
source. Do not trust the Worker's inventory, semantic roles, dependency edges,
quantifiers, applicability predicates, or checklist projections merely because the
compiler accepted their shape.

The exact candidate report is `{candidate_report_record_id}` with digest
`{candidate_report_digest}`. Verify complete clause coverage, ordered byte slices,
source-to-role semantics, reverse projection, zero SemanticDelta, explicit dependency
alignment, temporal and conditional relations, required/optional classification,
deterministic checklist coverage, semantic-edge templates, and witness-obligation
templates. Check that a relationship is called `source_bound` only when explicit
relationship slices support it; derived or absent relationship meaning remains
`unresolved`. Bounds and digests establish identity, not meaning. QA must not mutate
the task, graph, IR, or candidate and must not ratify
Rules. A `pass` means this exact candidate can become RuleClosure; otherwise return
`fail` or `not_assessed` with one or more concise replayable findings that cite the
source clause/range and the mismatched Rule or edge.

This is compilation audit iteration {audit_iteration}. About {remaining_seconds}
seconds remain on the same total task clock; there is no QA-owned phase budget.
Write exactly one JSON object to `{qa_output_path}` with schema
`{RULE_COMPILE_AUDIT_SCHEMA}` and exactly these fields: `schema_version`,
`study_profile_digest`, `graph_digest`, `candidate_report_record_id`,
`candidate_report_digest`, `outcome` (`pass|fail|not_assessed`), `findings` (strings),
and `scope_limitations` (strings). A passing outcome has no findings; every
non-passing outcome has at least one finding. Return promptly.
"""


def graph_compile_failure_qa_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    failed_candidate_id: str,
    remaining_seconds: int,
    method_text: str | None,
    typed_rule_ir_path: str,
    typed_rule_ir_digest: str,
    typed_rule_ir_size: int,
    failure_descriptor_path: str,
    failure_descriptor_digest: str,
    failure_descriptor_size: int,
    qa_output_path: str,
    audit_iteration: int,
) -> str:
    """Prompt stage two to audit one sealed compiler-rejected IR."""

    condition = _graph_condition_block(arm, method_text)
    return f"""You are the independent compilation QA reviewer.

{_task_block(task_instruction)}

{condition}

This is stage 2 of one in-clock lifecycle. The Worker has not implemented the task.
The task-neutral compiler rejected exact sealed candidate `{failed_candidate_id}`.
Its read-only IR is `{typed_rule_ir_path}` ({typed_rule_ir_digest},
{typed_rule_ir_size} bytes). Its bounded read-only failure descriptor is
`{failure_descriptor_path}` ({failure_descriptor_digest},
{failure_descriptor_size} bytes). Hash both files before reading them and reject any
identity mismatch. Do not read or trust mutable Worker output paths.

Re-run exactly:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit rules compile {typed_rule_ir_path}`

Independently re-read the public authority and determine whether the compiler
rejection identifies a source-grounded semantic defect that the same Worker can
repair. The descriptor contains bounded identity and classification only; reproduce
the rejection rather than asking for raw runner stderr. Do not mutate the task, IR,
descriptor, or any graph. A compiler-rejected candidate can never PASS, establish
RuleClosure, or authorize implementation. Use `fail` with concise replayable
source/rule/edge findings when the rejection reproduces. Use `not_assessed` when the
identity, evidence, reproduction, or remaining time is insufficient.

This is compilation audit iteration {audit_iteration}. About {remaining_seconds}
seconds remain on the same total task clock; there is no QA-owned phase budget.
Write exactly one JSON object to `{qa_output_path}` with schema
`{RULE_COMPILE_FAILURE_AUDIT_SCHEMA}` and exactly these fields: `schema_version`,
`study_profile_digest`, `failed_candidate_id`, `typed_rule_ir_digest`,
`failure_descriptor_digest`, `outcome` (`fail|not_assessed`), `findings`, and
`scope_limitations`. Every outcome has at least one finding. Return promptly.
"""


def graph_compile_repair_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    prior_graph_digest: str,
    prior_candidate_report_record_id: str,
    qa_path: str,
    output_ir_path: str,
    output_report_path: str,
    remaining_seconds: int,
    method_text: str | None,
) -> str:
    """Resume the same Worker to produce a new immutable compilation candidate."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME compilation Worker.

{_task_block(task_instruction)}

{condition}

Stage-2 QA rejected or could not assess candidate
`{prior_candidate_report_record_id}` in graph `{prior_graph_digest}`. Read the sealed
QA report `{qa_path}`. Reproduce every finding against public authority before
changing semantics. Do not overwrite the prior IR, report, or graph. Write a complete
new `charting-loop/typed-rule-ir/v4` candidate to `{output_ir_path}` and its compiler
report to `{output_report_path}` using
`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit rules compile {output_ir_path} > {output_report_path}`.
Create parent directories as needed. Bind the revision to the prior candidate and QA
evidence using the IR's semantic-repair lineage fields. Do not implement, patch, or
submit the official task in this turn. About {remaining_seconds} seconds remain on
the same total clock. Return immediately after the new compile report is complete.
"""


def graph_compile_failure_repair_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    failed_candidate_id: str,
    prior_typed_rule_ir_digest: str,
    qa_path: str,
    output_ir_path: str,
    output_report_path: str,
    remaining_seconds: int,
    method_text: str | None,
) -> str:
    """Resume the same Worker after QA audits a sealed compiler rejection."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME compilation Worker.

{_task_block(task_instruction)}

{condition}

Stage-2 QA audited compiler-rejected candidate `{failed_candidate_id}`, whose sealed
IR digest is `{prior_typed_rule_ir_digest}`. Read the sealed QA report `{qa_path}`.
Reproduce every finding against public authority before changing semantics. Do not
overwrite the prior IR, failure descriptor, QA report, or any graph. Write a complete
new `charting-loop/typed-rule-ir/v4` candidate to `{output_ir_path}` and its compiler
report to `{output_report_path}` using
`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit rules compile {output_ir_path} > {output_report_path}`.
Create parent directories as needed. Bind the revision to the prior sealed IR digest
and QA evidence using the IR's semantic-repair lineage fields. Do not implement,
patch, or submit the official task in this turn. About {remaining_seconds} seconds
remain on the same total clock. Return immediately after the new compile report is
complete.
"""


def graph_execution_test_plan_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    qa_assessment_ref: str,
    remaining_seconds: int,
    method_text: str | None,
) -> str:
    """Project Direction and freeze tests/probes without implementing the task."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME Worker and prepare the next execution choice.

{_task_block(task_instruction)}

{condition}

Compilation QA `{qa_assessment_ref}` passed and RuleClosure exists in `{GRAPH_PATH}`
at graph digest `{graph_digest}`. This is a pre-action stage: do not yet mutate,
patch, or submit the official task. Replay the graph, query bounded `active-context`,
and reverse-trace relevant semantic edges. Append an initial whole-state
`position_checkpoint`, then a `direction_proposal` that remains a projection of all
applicable current Rules at that exact Position. Direction does not choose an action
or checklist subset. Append a `direction_snapshot` that selects that exact proposal;
the later execution contract cannot bind an unselected alternative.

After Direction, choose one bounded next execution step and append exactly one
non-authoritative `execution_test_contract`. Store its executable fixtures under
`{EXECUTION_TEST_ROOT}` before appending the record. The contract binds the exact
Position and Direction record, selected ready checklist rows and their current Rule,
semantic-edge and witness identities, plus one or more code tests, DB replays, CLI
probes, or interaction probes. Every selected checklist row needs a source-bound
positive case and a negative or boundary case. Each case names exact source slice
IDs, semantic dependency refs, predecessor probe IDs, operator, fixture path/digest,
command and oracle. `predecessor_probe_ids` is the explicit acyclic execution order;
use an empty list where the probe has no predecessor. Before action,
`pre_action_status: not_run_yet` is expected. If a fixture cannot be built, use
`unsupported` with a reason; do not invent evidence. `not_applicable` is legal only
with `applicability_predicate` exactly equal to the conditional Rule predicate and a
current admitted Fact receipt proving it. Other statuses use null for that field.

Compute `contract_digest` over every contract field except that digest. The Kernel
checks identity, source bindings, target readiness, operators, partition presence and
fixture identities; it does not judge semantic adequacy. Run the read-only Doctor,
which may honestly report missing receipts before action. Return immediately after
the graph and fixture bytes are complete so the runner can freeze the exact candidate
for independent QA. About {remaining_seconds} seconds remain on the one total task
clock; there is no stage-owned budget.
"""


def graph_execution_test_qa_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    contract_record_id: str,
    contract_digest: str,
    fixture_manifest_path: str,
    graph_path: str,
    qa_output_path: str,
    remaining_seconds: int,
    method_text: str | None,
    audit_iteration: int,
) -> str:
    """Review one frozen execution test/probe contract before implementation."""

    condition = _graph_condition_block(arm, method_text)
    return f"""You are the independent pre-action test/probe QA reviewer.

{_task_block(task_instruction)}

{condition}

The Worker has not implemented the selected action. Audit frozen graph `{graph_path}`
with digest `{graph_digest}` and exact `execution_test_contract`
`{contract_record_id}` / `{contract_digest}`. The runner's frozen fixture manifest is
`{fixture_manifest_path}`. Replay the graph, run Doctor, verify every frozen fixture
digest, and independently re-read the public Rule source slices.

Judge whether the positive and negative/boundary cases, operator, fixture, command and
oracle actually distinguish the required behavior. In particular, a temporal Rule
must include before/after boundary worlds; a timeless union or aggregate surrogate is
not equivalent. Structural validity and hashes establish identity, not semantics.
Do not edit the graph, fixtures or task, choose an action, authorize mutation, or
predict official PASS. A `fail` requires a concise source-grounded replayable finding.
Use `not_assessed` when evidence or time is insufficient. This review cannot prevent
implementation, complete snapshot custody, fallback, or official scoring.

This is execution-test audit iteration {audit_iteration}; about {remaining_seconds}
seconds remain on the single task clock. Write exactly one JSON object to
`{qa_output_path}` with schema `{EXECUTION_TEST_AUDIT_SCHEMA}` and exactly these
fields: `schema_version`, `study_profile_digest`, `graph_digest`,
`contract_record_id`, `contract_digest`, `outcome` (`pass|fail|not_assessed`),
`findings`, and `scope_limitations`. PASS has no findings; non-PASS has at least one.
Return promptly.
"""


def graph_execution_test_repair_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    prior_contract_record_id: str,
    prior_contract_digest: str,
    qa_path: str,
    remaining_seconds: int,
    method_text: str | None,
) -> str:
    """Resume the same Worker for one bounded pre-action contract revision."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME Worker before implementation.

{_task_block(task_instruction)}

{condition}

Independent QA reviewed execution test/probe contract
`{prior_contract_record_id}` / `{prior_contract_digest}`. Read `{qa_path}` and
reproduce each source-grounded finding. Do not overwrite prior graph records or
fixtures and do not mutate the official task. If a finding is valid, write separately
named fixture bytes and append one new complete `execution_test_contract` against the
same current Position/Direction. If it is unsupported, preserve that limitation
honestly. Return after one bounded revision. About {remaining_seconds} seconds remain
on the same total clock; there is no revision budget.
"""


def graph_implementation_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    qa_assessment_ref: str,
    remaining_seconds: int,
    method_text: str | None,
    execution_test_contract_record_id: str | None = None,
    execution_test_contract_digest: str | None = None,
    execution_test_qa_outcome: str = "not_assessed",
    execution_test_qa_assessment_record_id: str | None = None,
) -> str:
    """Prompt stage three: resume the same Worker after RuleClosure exists."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME Worker and now implement the official task.

{_task_block(task_instruction)}

{condition}

Compilation QA `{qa_assessment_ref}` passed and the runner materialized RuleClosure
in `{GRAPH_PATH}` at graph digest `{graph_digest}`. The pre-action stage already
froze the exact Position, Direction and non-authoritative execution choice. Replay
the graph before changing the task.

The selected execution test/probe contract is
`{execution_test_contract_record_id}` with digest
`{execution_test_contract_digest}`. Its independent pre-action QA outcome is
`{execution_test_qa_outcome}` and its graph assessment record is
`{execution_test_qa_assessment_record_id}`. Re-read its exact source, Position, Direction,
checklist, edge, witness, fixture and oracle bindings. A passing review is guidance,
not mutation authority. A fail/not_assessed/missing review keeps the execution claim
unresolved but never blocks implementation, custody, fallback, or official scoring.

Before each selected mutating action, preserve the contract's positive and
negative/boundary fixtures. After acting, run every supported test/probe command and
append one digest-bound `execution_test_receipt` per probe in predecessor order. Each
receipt must copy `pre_action_qa_status` and bind
`pre_action_qa_assessment_record_id`; when the review was unavailable, record status
`missing` and null assessment ID so Doctor reports unresolved without blocking. Use failures as evidence
for a new Position/Direction/contract revision. `not_applicable` requires its admitted
applicability Fact; `unsupported` remains visibly unresolved. Do not weaken a
temporal or conditional Rule into a timeless aggregate merely because that surrogate
passes a broad happy-path probe.

During implementation, append a new Position for meaningful state changes and a new
Position-bound Direction before the next move. Respect hard dependency order and
recompute downstream checklist/frontier state when upstream evidence changes. Run the
read-only graph Doctor before each submission freeze; it is diagnostic and never task
truth or PASS. Invalid graph writes leave bytes unchanged and do not authorize task
mutation.

Create a complete scorable result early and freeze each verified improvement with:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit submission freeze --root {SUBMISSION_ROOT} --role worker --path <absolute-output-path> [--path <absolute-output-path> ...]`

About {remaining_seconds} seconds remain on the same total task clock. Return after
the first complete locally verified scorable freeze so independent result QA can
audit it. A witnessed defect may resume this same Worker for repair.
"""


def graph_qa_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    latest_worker_snapshot_ref: str | None,
    remaining_seconds: int,
    method_text: str | None,
    study_profile_path: str = STUDY_PROFILE_PATH,
    graph_path: str = GRAPH_PATH,
    qa_output_path: str | None = QA_PATH,
    audit_iteration: int = 1,
) -> str:
    """Prompt in-clock QA over one immutable Worker/graph revision."""

    condition = _graph_condition_block(arm, method_text)
    output_instruction = (
        f"Write exactly one JSON object to `{qa_output_path}`"
        if qa_output_path is not None
        else "Return exactly one JSON object as your final response"
    )
    return f"""You are the independent advisory QA reviewer.

{_task_block(task_instruction)}

{condition}

There was no Builder. Read the byte-identical Graph Kernel, frozen Study profile
`{study_profile_path}` (`{study_profile_digest}`), and sealed Worker graph
`{graph_path}` (`{graph_digest}`). Replay it with:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph replay {graph_path}`

Re-run the same read-only Doctor over those exact frozen bytes:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph doctor {graph_path}`

Use `graph query` on the same frozen path for topology, prerequisite/dependant
closure, source trace, blocked explanations, and RuleClosure digest checks. Confirm
that every query reports the sealed graph digest and head record ID. These query
surfaces are advisory and do not replace your independent review or runner-owned
ratification.

Also run one `active-context` query and independently reverse-trace every semantic
edge referenced by the selected Direction. Verify each Direction semantic binding
against its exact Position, current Rule record, checklist row, source-bound or
honestly unresolved relationship status, and witness obligation. Aggregate identity
lists alone are not closure evidence. Direction must not contain the concrete action;
the later execution transition is reviewed separately.

Audit the entire path: runner-owned AuthoritySnapshot manifest/receipt equality,
source versus extraction-representation bytes,
official-source Rule coverage and dependencies, immutable candidate lineage, reverse
semantic projection and SemanticDelta, frozen `rule_candidate_report`, the matching
`rule_qa_assessment`, authorized RuleClosure receipts, evidence-bound
Facts, whole-state Position checkpoints, whether each
Direction is projected from its claimed Position, and whether the latest official
outputs agree with the evidence. Inspect the exact frozen Worker snapshot identified
below and the frozen graph copy. Verify the Worker snapshot before inspecting its
manifest and immutable blobs:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit submission verify --root {SUBMISSION_ROOT} --role worker --snapshot-id {latest_worker_snapshot_ref}`

Its manifest and blobs are under
`{SUBMISSION_ROOT}/snapshots/worker/{latest_worker_snapshot_ref}/`; use the manifest's
destination mapping to interpret each blob. The official verifier has not run yet. Graph validity
is not task truth or PASS. You may identify a better Direction, but you must not
mutate the task, graph, Worker snapshot, or official outputs. Only a concrete
replayable witness may recommend that the harness resume the same Worker for repair;
QA itself never repairs or blocks final submission.
Missing or incompatible witnesses keep the affected checklist and verified claim
open, but never block custody of the latest complete scorable freeze or external
grading.
Independently re-read the public instruction and every named public authoritative
source declared in `{TYPED_RULE_IR_PATH}`. Verify their retrieval statuses and digests,
then enumerate their normative clauses without trusting the Worker's Rule list.
Compare that independent inventory to `source_clause_inventory` and
`{TYPED_RULE_REPORT_PATH}`: check omissions, trailing qualifications, required versus
optional classification, clause-to-Rule bindings, applicability predicates, open
versus closed quantifier domains, collective versus per-subject ordering, and temporal
or coupled witness semantics. For successor IR, also verify each stable clause-order
key independently of array position, reconstruct each clause from its ordered frozen
byte slices, check slice-to-semantic-role coverage and resolved Rule provenance, and verify that
every dependency is directly source-backed or derived from the current endpoint Rule
provenance identities. Verify that relationship alignment names endpoint semantics,
scope and cardinality and uses keyed joins, aggregate membership, exact pairs, or an
explicit source-backed all-to-all rationale; reject implicit Cartesian projection.
Bounds and digests prove source identity, not semantic
correctness; independently judge whether each selected slice and role actually
expresses the claimed Rule or relationship. Audit the immutable first-attempt revision as written;
do not overwrite it. If compilation drift is concrete, emit a replayable source-clause
witness in the result audit. Compilation QA and runner ratification have already
established RuleClosure; result QA must not append a second Rule assessment, revise
Rule authority, or reinterpret the sealed compile candidate.
Treat the Doctor as deterministic audit material: inspect checklist partition
coverage, typed Rule coverage cells, witness-operator/semantics alignment, dependency
order, ready/blocked frontier, invalidation closure, and exact Position-bound
Direction freshness. Its classification is not a QA verdict, Gate, or substitute for
inspecting the official output.
The latest verified Worker snapshot ref is {json.dumps(latest_worker_snapshot_ref)}.
This is audit iteration {audit_iteration}. About {remaining_seconds} seconds remain
on the same total task clock; there is no QA-owned time slice. Write a complete
assessment early and return promptly.

{output_instruction} with schema `{GRAPH_AUDIT_SCHEMA}` and
fields: `schema_version`, `study_profile_digest`, `graph_digest`, `snapshot_ref`,
`path_assessment` (`coherent|drifted|incomplete|not_assessed`),
`repair_recommended` (boolean), `witnesses`, and `scope_limitations`. Each witness is
an exact object with non-empty `witness_id`, `category`
(`rule|fact|position|direction|output`), `observation`, `expected`, `evidence_ref`,
`replay`, `position_ref`, and `candidate_ref`. `candidate_ref` must equal the audited
Worker snapshot ref. A repair recommendation is valid only for `drifted` or
`incomplete` with at least one such witness. This report is concise audit evidence,
not hidden reasoning, and grants no task authority, mutation authority,
deliverability, correctness, Gate decision, or PASS.
"""


def graph_result_repair_test_plan_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    audited_snapshot_ref: str,
    qa_path: str,
    remaining_seconds: int,
    method_text: str | None,
) -> str:
    """Plan and freeze a witnessed result repair before mutating the task."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME Worker for a pre-repair execution choice only.

{_task_block(task_instruction)}

{condition}

QA audited Worker snapshot `{audited_snapshot_ref}` against graph digest
`{graph_digest}` under frozen Study `{study_profile_digest}`. Read `{qa_path}` and
reproduce every source-grounded witness, but do not yet mutate, patch, or submit the
official task. Reject unsupported QA advice.

For a reproduced defect, append a new whole-state Position that records the affected
checklist state, then project all applicable current Rules into a new Direction and
select that exact Direction snapshot. Append one new bounded
`execution_test_contract` for the proposed repair action. Bind exact Rule, source,
edge, witness and dependency identities; include source-grounded positive plus
negative/boundary probes, explicit acyclic predecessor probe IDs, exact fixture
digests, commands and oracles. Store fixtures under `{EXECUTION_TEST_ROOT}`. Do not
reuse the prior Direction's contract and do not append execution receipts yet.

Return immediately after those graph and fixture bytes are complete so the runner
can freeze them for distinct pre-action QA. About {remaining_seconds} seconds remain
on the same total clock; there is no repair-owned budget.
"""


def graph_repair_prompt(
    task_instruction: str,
    *,
    arm: str,
    study_profile_digest: str,
    graph_digest: str,
    audited_snapshot_ref: str,
    qa_path: str,
    remaining_seconds: int,
    method_text: str | None,
    execution_test_contract_record_id: str | None = None,
    execution_test_contract_digest: str | None = None,
    execution_test_qa_outcome: str = "not_assessed",
    execution_test_qa_assessment_record_id: str | None = None,
) -> str:
    """Resume the same Worker against one identity-bound advisory QA finding."""

    condition = _graph_condition_block(arm, method_text)
    return f"""Resume as the SAME Worker for an evidence-bound repair pass.

{_task_block(task_instruction)}

{condition}

QA audited Worker snapshot `{audited_snapshot_ref}` against graph digest
`{graph_digest}` under frozen Study `{study_profile_digest}`. Read its advisory
assessment at `{qa_path}`. Reproduce every witness before changing anything. QA is
not authority: reject a suggested repair if replay or the current ratified Rules and
admitted Facts do not support it.

The runner separately froze the proposed repair's pre-action contract
`{execution_test_contract_record_id}` / `{execution_test_contract_digest}` and its
independent QA outcome `{execution_test_qa_outcome}` at assessment record
`{execution_test_qa_assessment_record_id}`. Replay those exact records before acting.
Missing/not_assessed QA remains unresolved but does not block the repair, snapshot
custody, fallback, or official scoring.

If a repair is justified, update the official task under that already-frozen
Position/Direction/contract, append new evidence and a post-action Position/Direction,
and run the contract probes in predecessor order. Append digest-bound
`execution_test_receipt` records that copy the exact pre-action QA status and
assessment record ID (`missing` plus null when no assessment exists). Do not create a
contract and mutate in the same turn. Then
run `PYTHONPATH={SDK_ROOT} python3 -m corridor_kit graph doctor {GRAPH_PATH}`, verify the complete task, and freeze a new
complete scorable Worker revision. Never overwrite or invalidate the prior freeze.
For a semantic compilation repair, never overwrite `{TYPED_RULE_IR_PATH}` or
`{TYPED_RULE_REPORT_PATH}`. Write a separately named repair IR/report, set
`revision_kind` to `semantic_repair`, bind `parent_ir_digest` to the exact first or
current parent IR, and name each reproduced QA witness in `qa_witness_refs`; then
append source-bound Rule revisions and their newly projected checklist cells.
If no witness reproduces or the repair remains incomplete, preserve the prior freeze
and return without advancing it.

About {remaining_seconds} seconds remain on the same total task clock. There is no
repair-owned time slice. Return promptly after either freezing a newer valid revision
or determining that the prior freeze should remain current.
"""


def validate_graph_compile_audit(
    value: Any,
    *,
    study_profile_digest: str,
    graph_digest: str,
    candidate_report_record_id: str,
    candidate_report_digest: str,
) -> list[str]:
    """Validate the identity and outcome of one sealed compilation audit."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return ["RULE_COMPILE_AUDIT_OBJECT_REQUIRED"]
    expected_keys = {
        "schema_version",
        "study_profile_digest",
        "graph_digest",
        "candidate_report_record_id",
        "candidate_report_digest",
        "outcome",
        "findings",
        "scope_limitations",
    }
    if set(value) != expected_keys:
        errors.append("RULE_COMPILE_AUDIT_FIELDS")
    if value.get("schema_version") != RULE_COMPILE_AUDIT_SCHEMA:
        errors.append("RULE_COMPILE_AUDIT_SCHEMA")
    for field, expected in (
        ("study_profile_digest", study_profile_digest),
        ("graph_digest", graph_digest),
        ("candidate_report_record_id", candidate_report_record_id),
        ("candidate_report_digest", candidate_report_digest),
    ):
        if value.get(field) != expected:
            errors.append(f"RULE_COMPILE_AUDIT_{field.upper()}_IDENTITY")
    outcome = value.get("outcome")
    if outcome not in {"pass", "fail", "not_assessed"}:
        errors.append("RULE_COMPILE_AUDIT_OUTCOME")
    findings = value.get("findings")
    if not isinstance(findings, list) or any(
        not isinstance(item, str) or not item.strip() for item in findings
    ):
        errors.append("RULE_COMPILE_AUDIT_FINDINGS")
        findings = []
    limitations = value.get("scope_limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        errors.append("RULE_COMPILE_AUDIT_SCOPE_LIMITATIONS")
    if outcome == "pass" and findings:
        errors.append("RULE_COMPILE_AUDIT_PASS_WITH_FINDINGS")
    if outcome in {"fail", "not_assessed"} and not findings:
        errors.append("RULE_COMPILE_AUDIT_NONPASS_REQUIRES_FINDING")
    return errors


def validate_graph_compile_failure_audit(
    value: Any,
    *,
    study_profile_digest: str,
    failed_candidate_id: str,
    typed_rule_ir_digest: str,
    failure_descriptor_digest: str,
) -> list[str]:
    """Validate a non-PASS audit of one sealed compiler-rejected IR."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return ["RULE_COMPILE_FAILURE_AUDIT_OBJECT_REQUIRED"]
    expected_keys = {
        "schema_version",
        "study_profile_digest",
        "failed_candidate_id",
        "typed_rule_ir_digest",
        "failure_descriptor_digest",
        "outcome",
        "findings",
        "scope_limitations",
    }
    if set(value) != expected_keys:
        errors.append("RULE_COMPILE_FAILURE_AUDIT_FIELDS")
    if value.get("schema_version") != RULE_COMPILE_FAILURE_AUDIT_SCHEMA:
        errors.append("RULE_COMPILE_FAILURE_AUDIT_SCHEMA")
    for field, expected in (
        ("study_profile_digest", study_profile_digest),
        ("failed_candidate_id", failed_candidate_id),
        ("typed_rule_ir_digest", typed_rule_ir_digest),
        ("failure_descriptor_digest", failure_descriptor_digest),
    ):
        if value.get(field) != expected:
            errors.append(
                f"RULE_COMPILE_FAILURE_AUDIT_{field.upper()}_IDENTITY"
            )
    if value.get("outcome") not in {"fail", "not_assessed"}:
        errors.append("RULE_COMPILE_FAILURE_AUDIT_OUTCOME")
    findings = value.get("findings")
    if not isinstance(findings, list) or not findings or any(
        not isinstance(item, str) or not item.strip() for item in findings
    ):
        errors.append("RULE_COMPILE_FAILURE_AUDIT_FINDINGS")
    limitations = value.get("scope_limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        errors.append("RULE_COMPILE_FAILURE_AUDIT_SCOPE_LIMITATIONS")
    return errors


def validate_execution_test_audit(
    value: Any,
    *,
    study_profile_digest: str,
    graph_digest: str,
    contract_record_id: str,
    contract_digest: str,
) -> list[str]:
    """Validate one identity-bound pre-action test/probe QA result."""

    errors: list[str] = []
    if not isinstance(value, dict):
        return ["EXECUTION_TEST_AUDIT_OBJECT_REQUIRED"]
    expected_keys = {
        "schema_version",
        "study_profile_digest",
        "graph_digest",
        "contract_record_id",
        "contract_digest",
        "outcome",
        "findings",
        "scope_limitations",
    }
    if set(value) != expected_keys:
        errors.append("EXECUTION_TEST_AUDIT_FIELDS")
    if value.get("schema_version") != EXECUTION_TEST_AUDIT_SCHEMA:
        errors.append("EXECUTION_TEST_AUDIT_SCHEMA")
    for field, expected in (
        ("study_profile_digest", study_profile_digest),
        ("graph_digest", graph_digest),
        ("contract_record_id", contract_record_id),
        ("contract_digest", contract_digest),
    ):
        if value.get(field) != expected:
            errors.append(f"EXECUTION_TEST_AUDIT_{field.upper()}_IDENTITY")
    outcome = value.get("outcome")
    if outcome not in {"pass", "fail", "not_assessed"}:
        errors.append("EXECUTION_TEST_AUDIT_OUTCOME")
    findings = value.get("findings")
    if not isinstance(findings, list) or any(
        not isinstance(item, str) or not item.strip() for item in findings
    ):
        errors.append("EXECUTION_TEST_AUDIT_FINDINGS")
        findings = []
    limitations = value.get("scope_limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        errors.append("EXECUTION_TEST_AUDIT_SCOPE_LIMITATIONS")
    if outcome == "pass" and findings:
        errors.append("EXECUTION_TEST_AUDIT_PASS_WITH_FINDINGS")
    if outcome in {"fail", "not_assessed"} and not findings:
        errors.append("EXECUTION_TEST_AUDIT_NONPASS_REQUIRES_FINDING")
    return errors


def validate_graph_audit(
    value: Any,
    *,
    study_profile_digest: str,
    graph_digest: str,
    snapshot_ref: str | None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["GRAPH_AUDIT_OBJECT_REQUIRED"]
    expected_keys = {
        "schema_version",
        "study_profile_digest",
        "graph_digest",
        "snapshot_ref",
        "path_assessment",
        "repair_recommended",
        "witnesses",
        "scope_limitations",
    }
    if set(value) != expected_keys:
        errors.append("GRAPH_AUDIT_FIELDS")
    if value.get("schema_version") != GRAPH_AUDIT_SCHEMA:
        errors.append("GRAPH_AUDIT_SCHEMA")
    if value.get("study_profile_digest") != study_profile_digest:
        errors.append("GRAPH_AUDIT_STUDY_IDENTITY")
    if value.get("graph_digest") != graph_digest:
        errors.append("GRAPH_AUDIT_GRAPH_IDENTITY")
    if value.get("snapshot_ref") != snapshot_ref:
        errors.append("GRAPH_AUDIT_SNAPSHOT_IDENTITY")
    if value.get("path_assessment") not in {
        "coherent",
        "drifted",
        "incomplete",
        "not_assessed",
    }:
        errors.append("GRAPH_AUDIT_PATH_ASSESSMENT")
    if not isinstance(value.get("repair_recommended"), bool):
        errors.append("GRAPH_AUDIT_REPAIR_RECOMMENDED_BOOL")
    limitations = value.get("scope_limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in limitations
    ):
        errors.append("GRAPH_AUDIT_SCOPE_LIMITATIONS_LIST")
    witnesses = value.get("witnesses")
    witness_keys = {
        "witness_id",
        "category",
        "observation",
        "expected",
        "evidence_ref",
        "replay",
        "position_ref",
        "candidate_ref",
    }
    if not isinstance(witnesses, list):
        errors.append("GRAPH_AUDIT_WITNESSES_LIST")
        witnesses = []
    seen_witness_ids: set[str] = set()
    for witness in witnesses:
        if not isinstance(witness, dict) or set(witness) != witness_keys:
            errors.append("GRAPH_AUDIT_WITNESS_FIELDS")
            continue
        if any(
            not isinstance(witness.get(field), str) or not witness[field].strip()
            for field in witness_keys
        ):
            errors.append("GRAPH_AUDIT_WITNESS_TEXT")
            continue
        if witness["category"] not in {"rule", "fact", "position", "direction", "output"}:
            errors.append("GRAPH_AUDIT_WITNESS_CATEGORY")
        if witness["candidate_ref"] != snapshot_ref:
            errors.append("GRAPH_AUDIT_WITNESS_SNAPSHOT_IDENTITY")
        if witness["witness_id"] in seen_witness_ids:
            errors.append("GRAPH_AUDIT_WITNESS_DUPLICATE_ID")
        seen_witness_ids.add(witness["witness_id"])
    repair_recommended = value.get("repair_recommended") is True
    if repair_recommended and value.get("path_assessment") not in {"drifted", "incomplete"}:
        errors.append("GRAPH_AUDIT_REPAIR_OUTCOME_CONTRADICTION")
    if repair_recommended and not witnesses:
        errors.append("GRAPH_AUDIT_REPAIR_WITNESS_REQUIRED")
    return errors


def builder_prompt(task_instruction: str) -> str:
    """Prompt the construction role with the method and official task goal."""


    return f"""You are the Builder for one fresh Terminal-Bench trial.

Start with the runner-generated compact Method capsule at
{CORRIDOR_PATH}/METHOD-CAPSULE.json. It is bound to Method digest
{METHOD_CONTENT_SHA256} and scope digest {METHOD_SCOPE_SHA256}. Use its Builder
invariants and generated schemas first; consult the full frozen Method at
{METHOD_PATH} only when the capsule or public task leaves a genuine ambiguity. The
official task is included below because the Builder must compile task-specific Rules,
not reuse a stored answer.

The runner uploaded a frozen task-neutral Corridor SDK read-only at
{SDK_PACKAGE_PATH} and initialized the honest starter directly under
{CORRIDOR_PATH}. Extend those files in place. Inspect
`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit capabilities builtins`; do not rebuild
generic hashing, acceptance obligations, evidence records, source maps, unprivileged
replay, work-row, timeline, ELF inventory, binary-diff, or snapshot plumbing when the
SDK already provides it.

{_task_block(task_instruction)}

Construct a reusable task-specific Corridor under {CORRIDOR_PATH}. It may contain
documentation, diagnostic commands, validators, planners, or a service. Inspect the
public task environment as needed, but do not carry out the official task or mutate
its target state. Do not read verifier/oracle material that the official task does
not expose to ordinary agents.

Compile the generated {ACCEPTANCE_PATH}, {WORK_PATH}, {CAPABILITIES_PATH},
{CORRIDOR_PATH}/SOURCE-MAP.json, {CORRIDOR_PATH}/EVIDENCE.json, and
{CORRIDOR_PATH}/REPLAY.json in place. Compile `{CORRIDOR_PATH}/WITNESSES.json` only
from task-derived replay evidence; every witness must explicitly name the acceptance
IDs and one or more of the same six `obligation_partitions`. Preserve schema field names. Bind every
acceptance ID to work and replay evidence, and include only capabilities selected by
a row. Reusable mechanics may never contain a task answer, fixed task offset, hidden
verifier Fact, or outcome-derived repair.

The generated acceptance schema is `{ACCEPTANCE_SCHEMA}` and its six obligation keys
are exactly "positive", "negative", "boundary", "state", "temporal", and "coupled".

The top-level field is exactly `schema_version`, never `schema`. Every relation
target field is exactly `target_id`, never `target_acceptance_id` or another alias.
Decompose every normative
clause in the public task instruction and public task specification into an atomic
item with a stable `acceptance_id`, exact `source_ref`, normalized `statement`,
`required` boolean, `definition_state` (`defined|ambiguous`), non-empty task
`scope`, non-empty decision `rule`, and typed `relations` (`requires`,
`subsumes`, `overlaps`, `conflicts`, or `derived_from`). Every item must
also declare non-empty `verification_obligations` for `positive`, `negative`,
`boundary`, `state`, `temporal`, and `coupled`. If a partition truly does not apply,
write an explicit reason; never omit it or leave it empty. The top-level
`coverage` object must declare `status` and list all `unmapped_clauses` and
`ambiguous_clauses`, each with source_ref, statement, and reason. Mark coverage
complete only after re-reading the original public sources and mapping every
normative clause. Do not invent precedence for overlap or conflict.

`coverage.status` reports source-clause mapping only; it does not claim that a
candidate solution is feasible or optimal. A mapped clause may remain explicitly
ambiguous: keep it in `ambiguous_clauses`, mark its item `definition_state` as
`ambiguous`, and still report source mapping complete when nothing is unmapped.
Definition closure remains incomplete until those ambiguities are resolved. Use the separate
`construction_readiness` object for that. If hard requirements interact (for
example capacity, scheduling, inventory, identity, and priority/objective rules),
list their IDs in `coupled_acceptance_ids`. Mark construction `ready` only when the
Corridor has one replayable executable entrypoint that evaluates the coupled hard
constraints and objective together. Otherwise mark it `unresolved` and name every
missing proof in `unresolved_constraints`. Never recommend a candidate or claim
whole-task readiness while a required coupled constraint or objective is unknown.

Compile the acceptance graph into bounded work rows. Dependencies must be acyclic;
every acceptance and capability ID must resolve; and each row needs explicit task
scope and replayable done-when conditions. Reminders are advisory and must never
become approval, pre-mutation, or workflow Gates. Before finishing, run:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit validate {ACCEPTANCE_PATH}`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit validate-capabilities {CAPABILITIES_PATH}`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit validate-work {WORK_PATH} --acceptance {ACCEPTANCE_PATH} --capabilities {CAPABILITIES_PATH}`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit authoring validate {CORRIDOR_PATH} --expected-method-version {METHOD_VERSION_ID} --expected-method-digest {METHOD_CONTENT_SHA256} --expected-method-scope-digest {METHOD_SCOPE_SHA256}`

Build in bounded milestones: first write the exact acceptance ledger and a minimal
README, then make the global replay check executable, then deepen diagnostics only
if time remains. A partial but honest `unresolved` Corridor is preferable to an
invalid ledger or an unproved readiness claim.

Builder, Worker, QA, repair, and closure share the official task's single total
clock. There is no Builder-owned time slice to exhaust. Finish and hand off as soon
as a useful, valid Corridor is frozen-ready so that later roles retain time.

Experimental constraint: do not install a mandatory workflow gate, approval gate,
or pre-mutation gate that can block the later Worker from continuing. A Corridor may
diagnose, plan, validate, warn, or refuse an explicitly requested unsafe operation;
it must remain an aid the Worker chooses to call, not a new governance dependency.

Write only the Corridor and Builder scratch data under {RUNTIME_ROOT}. Leave a clear
README or entrypoint. Do not put a final task answer or precomputed writeback in the
Corridor. When finished, report what you built; the harness will freeze the bytes.
"""


def worker_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    construction_readiness_status: str = "unknown",
    work_backlog_status: str = "unknown",
    current_row_id: str | None = None,
    position_ref: str | None = None,
    direction_digest: str | None = None,
    remaining_seconds: int | None = None,
    method_text: str,
    fact_candidate_ref: str,
) -> str:
    """Prompt the execution role with the exact frozen Corridor identity."""

    return f"""You are the Worker responsible for completing the official task.

{_task_block(task_instruction)}

The official task above is the Rule authority. The following exact frozen Method is
procedural guidance, not task authority, a stored answer, or a Gate. Use it to
diagnose your own drift and keep Position, Direction, evidence, and action coherent.

{_frozen_method_block(method_text)}

The Builder's frozen task-conditioned Corridor is available read-only at
{CORRIDOR_PATH}. Its freeze manifest is {FREEZE_PATH}, and the harness-verified
Corridor digest is {corridor_digest_value}. Read the Corridor before acting and use
its diagnostics/planner/validator when relevant. The Corridor is an aid, not hidden
authority or a stored answer: inspect the live task state, obey the official task,
and independently verify every mutation.

Read the frozen task acceptance ledger at {ACCEPTANCE_PATH}. Use its stable
acceptance IDs to plan and verify the whole task, not only the first reproduced
failure. Re-check public source requirements when the ledger is ambiguous or
incomplete. The freeze manifest reports construction readiness
`{construction_readiness_status}`. Source coverage is not solution qualification:
when readiness is not `ready`, or any required coupled feasibility/objective check
returns unknown, do not trust a recommended candidate as globally valid. Complete
the missing live reasoning yourself and require replayable evidence before mutation.

The frozen work-backlog status is `{work_backlog_status}` and the runner's initial
current-row projection is {json.dumps(current_row_id)}. Its PositionRef is
{json.dumps(position_ref)} and its Direction digest is
{json.dumps(direction_digest)}. These identities can change after new observations;
when the work and capability files validate, re-query the same runner-owned Position
timeline and advisory Guide with:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit runtime guide --work {WORK_PATH} --acceptance {ACCEPTANCE_PATH} --capabilities {CAPABILITIES_PATH} --timeline {POSITION_PATH}`

Use the returned `position_ref`, `direction.direction_digest`, Rule closure, row
acceptance bindings, dependencies, done-when conditions, bounded capabilities, and
reminders to avoid losing place. Direction is a projection at that Position, not a
stored answer. Re-check live state: row events and reminders are RAW observations,
not authority or proof of completion.

Record concise evidence candidates, not chain-of-thought, at
{WORKER_FACTS_PATH}. The optional file must contain one JSON object with schema
`charting-loop/fact-candidates/v1` and a `candidates` list. Each candidate has
exactly these string fields: `candidate_id`, `role` (`worker`), `corridor_digest`
(`{corridor_digest_value}`), `position_ref` ({json.dumps(position_ref)}), `row_id`,
`acceptance_id`, `obligation_partition` (positive|negative|boundary|state|temporal|coupled),
`observation`, `source_ref`, `witness_ref`, `replay_ref`, and `candidate_ref`
(`{fact_candidate_ref}`). These are observations only. The runner alone may admit a
well-bound candidate as a Fact and then reproject Position and Direction.

All roles share one task-level deadline. At this handoff the runner reports about
{json.dumps(remaining_seconds)} seconds remaining; this is a progress signal, not a
separate Worker budget. Establish a complete, scorable version early. As soon as
every official output path for one internally consistent version exists, freeze it
with the task-neutral SDK, listing every required output path explicitly:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit submission freeze --root {SUBMISSION_ROOT} --role worker --path <absolute-output-path> [--path <absolute-output-path> ...]`

Run that command again after every verified improvement. A snapshot is immutable;
the newest complete snapshot becomes the monotonic fallback. Include only official
deliverables or task-state files needed for grading, never credentials, logs, or
unrelated host files. Freezing is custody, not acceptance and not a Gate: continue
working after a snapshot when time remains.

Execute the task now. Do not wait for QA and do not create a gate around your work.
The harness will invoke an independent QA role afterward.
"""


def qa_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    source_mapping_status: str = "unknown",
    definition_closure_status: str = "unknown",
    construction_readiness_status: str = "unknown",
    work_backlog_status: str = "unknown",
    current_row_id: str | None = None,
    position_ref: str | None = None,
    direction_digest: str | None = None,
    remaining_seconds: int | None = None,
    method_text: str,
    fact_candidate_ref: str | None,
) -> str:
    """Prompt an independent QA session that can use the same frozen Corridor."""

    return f"""You are the independent QA reviewer. Audit the Worker's current result.

{_task_block(task_instruction)}

The official task above is the Rule authority. The following exact frozen Method is
procedural guidance, not task authority, a stored answer, or a Gate. Use it to
diagnose your own drift and keep Position, Direction, evidence, and action coherent.

{_frozen_method_block(method_text)}

You MUST read and may execute the same frozen, read-only Corridor at {CORRIDOR_PATH}.
The freeze manifest is {FREEZE_PATH}; the expected digest is
{corridor_digest_value}. Use the Corridor for global constraint checks and
counterfactual validation, not merely as prose context.

The frozen work-backlog status is `{work_backlog_status}` and the runner's current-row
projection before QA is {json.dumps(current_row_id)}. Its PositionRef is
{json.dumps(position_ref)} and its Direction digest is
{json.dumps(direction_digest)}. Query the same read-only rows, capabilities, Position
timeline, Guide, and reminders used by Worker with:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit runtime guide --work {WORK_PATH} --acceptance {ACCEPTANCE_PATH} --capabilities {CAPABILITIES_PATH} --timeline {POSITION_PATH}`

Confirm the PositionRef and Direction digest you audited, inspect all six verification
partitions, audit row done-when evidence, and replay applicable capabilities. The SDK's
`runtime counterfactual` command may test an explicitly substituted Position or
acceptance Rule set, but its output is hypothetical and read-only. Never treat a row
state, Direction, counterfactual, or reminder as sufficient acceptance evidence.

The latest verified Worker snapshot reference is {json.dumps(fact_candidate_ref)}.
If it is null, you may still report an assessment, but no QA witness can be admitted
as a Fact and no repair is available; leave `witnesses` empty.

All roles share one task-level deadline. At this handoff the runner reports about
{json.dumps(remaining_seconds)} seconds remaining; this is not a QA-owned time
slice. Preserve a valid assessment early and deepen it only while time remains. The
runner will freeze each completed QA assessment as audit evidence. Worker and QA are
cooperative protocol roles, not security principals: the `qa` role is a provenance
namespace, not an authorization credential or Gate. Follow the protocol boundary
yourself. Do not delete, replace, or block the newest complete Worker snapshot, and
write only the assessment path named below.

Do not mutate the official task state, repair the result, or alter the Corridor.
Diagnostic reads are allowed. Your only write is {QA_PATH}. Write one JSON object:

{{
  "schema_version": "{ASSESSMENT_SCHEMA}",
  "outcome": "pass|fail|blocked|not_assessed",
  "summary": "concise human-readable conclusion",
  "corridor_digest": "{corridor_digest_value}",
  "source_mapping_complete": true,
  "definition_closure_complete": true,
  "assessment_closure": "complete|incomplete",
  "assessed_scope": "complete|partial",
  "scope_limitations": [],
  "acceptance_results": [{{
    "acceptance_id": "...",
    "applicability": "applicable|not_applicable|unknown",
    "status": "pass|fail|unknown|not_reached",
    "evidence": "...",
    "replay": "..."
  }}],
  "unmapped_requirements": [],
  "unresolved_relations": [],
  "checks": [{{"name": "...", "status": "pass|fail|unknown", "evidence": "..."}}],
  "witnesses": [{{
    "acceptance_id": "...",
    "constraint": "...",
    "evidence": "...",
    "replay": "...",
    "row_id": "...",
    "obligation_partition": "positive|negative|boundary|state|temporal|coupled",
    "position_ref": {json.dumps(position_ref)},
    "candidate_ref": {json.dumps(fact_candidate_ref)},
    "source_ref": "stable public or live-state source reference",
    "witness_ref": "stable witness reference"
  }}]
}}

The freeze manifest reports acceptance-ledger status
`{acceptance_ledger_status}` and the expected acceptance IDs are
{json.dumps(expected_acceptance_ids, ensure_ascii=False)}. Its source-mapping status
is `{source_mapping_status}`, definition-closure status is
`{definition_closure_status}`, and separate construction-readiness status is
`{construction_readiness_status}`. `source_mapping_complete` means every public
normative clause has a ledger location; it does not mean every mapped clause is
unambiguous. `definition_closure_complete` means no required definition or relation
remains ambiguous. `assessment_closure` means QA has reached a supported
applicability and status for every expected item. Do not collapse these three
claims. Source mapping is not proof of joint feasibility or objective optimality.
`assessment_closure=complete` with `definition_closure_complete=false` is a
contradiction unless `assessed_scope=partial` names non-empty
`scope_limitations`; a partial assessment can never pass the whole task.
If definition closure or readiness is unresolved, or a required coupled check
remains unknown, you may not pass the task. Emit exactly one result
for every expected ID. Independently re-read the original public task sources to
look for omissions; the Corridor is a frozen map, not authority that its own map is
complete. A pass is permitted only when the frozen ledger is complete, the expected
ID set is exact, every applicable item passes, every inapplicable item is justified,
and no requirement or relation remains unmapped, unresolved, unknown, or not
reached. Witness closure is not task closure.

A partial or uncompiled Corridor is advisory evidence about construction, not a
business inability to execute the official task. Incompleteness alone must be
reported as `not_assessed`, not `blocked`. A fail verdict is valid only with at least one concrete witness tied to an
acceptance ID whose constraint, observed evidence, and safe replay procedure are all
non-empty. If complete task closure cannot be established, use blocked or
not_assessed.

Keep the assessment concise and structured, not chain-of-thought. QA
witnesses are Fact candidates only. The runner validates every binding. The runner
alone may admit them before repair or Direction reprojection.

Persist evidence witness-first. As soon as you establish an invalid acceptance
ledger, an unresolved required coupled check, or one concrete failure witness, write
a schema-valid provisional assessment covering every expected ID. Write it to a
temporary file in the QA directory and atomically rename it to {QA_PATH}; continue
deepening the audit only after that durable checkpoint, and atomically replace it
with richer evidence. Before finishing, run the same advisory semantic check used
by harness intake:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit qa validate --path {QA_PATH} --freeze {FREEZE_PATH}`

If it reports invalid, correct the report when evidence permits; otherwise preserve
the raw report and accept `not_assessed`. QA is advisory: validator failure must
never prevent the official verifier from running or trigger repair.
"""


def repair_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    remaining_seconds: int | None = None,
) -> str:
    """Resume the same Worker once when QA supplies a valid failure witness."""

    return f"""Resume as the SAME Worker for one bounded repair pass.

{_task_block(task_instruction)}

Read the independent QA assessment at {QA_PATH}. Re-read the same frozen Corridor
at {CORRIDOR_PATH}; its expected digest remains {corridor_digest_value}. Reproduce
each QA witness before changing anything. QA suggestions are not authority: reject
a locally plausible repair when the Corridor's complete constraints show it would
make the global result worse or infeasible.

Apply only repairs justified by reproduced witnesses, then verify the complete task
again against every stable acceptance ID in {ACCEPTANCE_PATH}; closing the reported
witness alone is insufficient. This is the single permitted repair pass. Do not
create a new gate.

The shared task clock has about {json.dumps(remaining_seconds)} seconds remaining;
there is no repair-owned time slice. The prior Worker snapshot remains protected.
Only after the repaired result is again complete and scorable, freeze a newer
Worker version with the same `corridor_kit submission freeze` command and the full
set of official output paths. If the repair stays incomplete, do not advance the
snapshot: the runner will restore the last complete Worker version.

Re-query the shared advisory runtime Guide at {POSITION_PATH}; row state helps recover
Position but does not authorize repair.
"""


def closure_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    source_mapping_status: str = "unknown",
    definition_closure_status: str = "unknown",
    construction_readiness_status: str = "unknown",
    remaining_seconds: int | None = None,
) -> str:
    """Resume the same QA session to assess the one repair pass."""

    return f"""Resume as the SAME independent QA reviewer for closure verification.

{_task_block(task_instruction)}

The Worker has completed the single bounded repair pass. Re-read {QA_PATH}, inspect
the current task state, and use the same frozen Corridor at {CORRIDOR_PATH}. The
expected digest is still {corridor_digest_value}. Do not mutate task state or the
Corridor. Re-evaluate every expected acceptance ID
{json.dumps(expected_acceptance_ids, ensure_ascii=False)} and independently re-check
the public source for omissions; closing the prior witness does not close the task.
The frozen ledger status is `{acceptance_ledger_status}`. Write the same JSON
schema to {CLOSURE_PATH}. Its frozen source-mapping, definition-closure, and
construction-readiness statuses remain `{source_mapping_status}`,
`{definition_closure_status}`, and `{construction_readiness_status}` respectively;
report those dimensions separately from assessment closure. A fail still requires a concrete
acceptance-ID/constraint/evidence/replay witness. This closure is advisory and must
not gate the official verifier.

The shared task clock has about {json.dumps(remaining_seconds)} seconds remaining;
there is no closure-owned time slice. Write a complete atomic closure assessment
early. The runner freezes it as audit evidence and then restores/promotes the newest
complete Worker submission for official grading regardless of the QA verdict.

Before finishing, run `PYTHONPATH={SDK_ROOT} python3 -m corridor_kit qa validate
--path {CLOSURE_PATH} --freeze {FREEZE_PATH}`. Invalid closure semantics normalize
to `not_assessed`, remain raw audit evidence, and never trigger another repair.

Re-query the same runtime Guide and Position timeline at {POSITION_PATH}; row progress
and reminders remain RAW, advisory evidence rather than acceptance authority.
"""


def validate_qa_assessment(
    value: Any,
    *,
    expected_corridor_digest: str,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    required_acceptance_ids: list[str],
    source_mapping_status: str = "complete",
    definition_closure_status: str = "complete",
    construction_readiness_status: str = "ready",
) -> list[str]:
    """Use the SDK validator shared by QA pre-submit and harness intake."""

    return validate_corridor_qa_assessment(
        value,
        expected_corridor_digest=expected_corridor_digest,
        acceptance_ledger_status=acceptance_ledger_status,
        expected_acceptance_ids=expected_acceptance_ids,
        required_acceptance_ids=required_acceptance_ids,
        source_mapping_status=source_mapping_status,
        definition_closure_status=definition_closure_status,
        construction_readiness_status=construction_readiness_status,
    )
