from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPOSITORY_ROOT / "demos" / "service-plan-corridor-e2e" / "run_acceptance_pair.py"
SPEC = importlib.util.spec_from_file_location("service_plan_acceptance_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

DIGEST = "sha256:" + "1" * 64
COMMITS = [character * 40 for character in "1234"]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def attempt(identity: str, arm: str, session: str, *, outcome: str = "passed") -> dict:
    suffix = identity.rsplit("-", 1)[-1]
    run_arm = "treatment" if arm == "builder" else arm
    return {
        "attempt_id": identity,
        "arm": arm,
        "session_id": session,
        "invocation_id": f"invocation-{identity}",
        "session_receipt_path": f"session/{identity}.json",
        "agent_kind": "ai-agent",
        "scripted": False,
        "run_path": f"runs/{run_arm}-run-{suffix}",
        "candidate_sha256": None if arm == "control" else DIGEST,
        "common_condition_sha256": DIGEST,
        "outcome": outcome,
        "supersedes_attempt_id": None,
        "repair_reason": None,
        "usage_receipt_path": f"usage/{identity}.json",
        "evidence": [
            {
                "artifact_id": f"artifact-{identity}",
                "kind": "transcript" if arm == "control" else "candidate-artifact",
                "path": f"raw/{identity}.txt",
            }
        ],
    }


def pair(identity: str, suffix: str) -> dict:
    return {
        "pair_id": identity,
        "builder_attempt_id": f"builder-{suffix}",
        "treatment_attempt_id": f"treatment-{suffix}",
        "control_attempt_id": f"control-{suffix}",
        "candidate_sha256": DIGEST,
        "common_condition_sha256": DIGEST,
    }


def input_document(*, two_pairs: bool = False) -> dict:
    attempts = [
        attempt("builder-1", "builder", "session-builder-1"),
        attempt("treatment-1", "treatment", "session-treatment-1"),
        attempt("control-1", "control", "session-control-1"),
    ]
    pairs = [pair("pair-1", "1")]
    if two_pairs:
        attempts += [
            attempt("builder-2", "builder", "session-builder-2"),
            attempt("treatment-2", "treatment", "session-treatment-2"),
            attempt("control-2", "control", "session-control-2"),
        ]
        pairs.append(pair("pair-2", "2"))
    return {
        "schema_version": runner.INPUT_SCHEMA,
        "acceptance_id": "acceptance-test",
        "runner_id": "manual-runner",
        "runner_session_id": "manual-runner-session",
        "runner_invocation_id": "manual-runner-invocation",
        "manual_confirmation": True,
        "measurement_plan_path": "measurement-plan.json",
        "attempts": attempts,
        "pairs": pairs,
        "replay_receipt_path": "replay.json",
    }


def session_receipt(item: dict) -> dict:
    return {
        "schema_version": runner.runtime.SESSION_RECEIPT_SCHEMA,
        "receipt_id": f"receipt-{item['attempt_id']}",
        "issuer_id": f"issuer-{item['attempt_id']}",
        "issuer_session_id": f"issuer-session-{item['attempt_id']}",
        "issuer_invocation_id": f"issuer-invocation-{item['attempt_id']}",
        "attempt_id": item["attempt_id"],
        "session_id": item["session_id"],
        "invocation_id": item["invocation_id"],
        "agent_kind": item["agent_kind"],
        "scripted": item["scripted"],
    }


def usage_receipt(item: dict, run: dict, run_sha: str, plan_sha: str) -> dict:
    stages = []
    for index, stage in enumerate(runner.runtime.CORE_USAGE_STAGES):
        stages.append(
            {
                "stage": stage,
                "stage_receipt_id": f"stage-{item['attempt_id']}-{stage}",
                "attempt_id": f"stage-attempt-{item['attempt_id']}-{stage}",
                "retry_of_attempt_id": None,
                "retry_of_stage": None,
                "assessment_status": "measured",
                "input_tokens": index + 1,
                "cached_input_tokens": 0,
                "output_tokens": index + 1,
                "reasoning_output_tokens": 0,
                "wall_time_ms": index + 1,
                "tool_calls": 0,
            }
        )
    stages.append(
        {
            "stage": "retry",
            "stage_receipt_id": f"stage-{item['attempt_id']}-retry",
            "attempt_id": f"stage-attempt-{item['attempt_id']}-retry",
            "retry_of_attempt_id": stages[1]["attempt_id"],
            "retry_of_stage": "guided_execution",
            "assessment_status": "not_applicable",
            **{metric: None for metric in runner.runtime.USAGE_METRICS},
        }
    )
    return {
        "schema_version": runner.runtime.USAGE_RECEIPT_SCHEMA,
        "receipt_id": f"usage-{item['attempt_id']}",
        "run_id": run["run_id"],
        "run_sha256": run_sha,
        "session_id": item["session_id"],
        "attempt_id": item["attempt_id"],
        "measurement_plan_sha256": plan_sha,
        "stages": stages,
    }


def make_exogenous_fixture(exogenous: Path, evidence: Path, value: dict) -> None:
    method_index = json.loads((REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text())
    version = method_index["versions"][0]
    task_dir = exogenous / "benchmarks" / "service-plan" / "v1"
    task_path = task_dir / "tasks" / "task.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text('{"task":"compile a service plan"}\n', encoding="utf-8")
    task_sha = runner.exogenous_registry.file_sha256(task_path)
    evaluator = {
        "scorer_id": "scorer",
        "scorer_revision": "v1",
        "scorer_sha256": "sha256:" + "2" * 64,
        "verifier_id": "verifier",
        "verifier_revision": "v1",
        "verifier_sha256": "sha256:" + "3" * 64,
    }
    taskset = {
        "schema_version": runner.exogenous_registry.TASKSET_SCHEMA,
        "taskset_id": "service-plan-v1",
        "benchmark": {
            "dataset_id": "service-plan",
            "release": "v1",
            "repository_url": "https://example.invalid/benchmark",
            "source_commit": COMMITS[0],
        },
        "tasks": [{"task_id": "task-001", "input": {"kind": "vendored", "locator": "tasks/task.json", "sha256": task_sha}}],
        "task_list_sha256": runner.exogenous_registry.canonical_sha256(
            [{"task_id": "task-001", "input_sha256": task_sha}]
        ),
        "environment": {"environment_id": "env-v1", "image_sha256": "sha256:" + "4" * 64, "data_sha256": "sha256:" + "5" * 64},
        "evaluator": evaluator,
        "license": {"identifier": "test-only", "redistribution": "vendored"},
    }
    taskset_path = task_dir / "TASKSET.json"
    write_json(taskset_path, taskset)
    method_ref = {
        "version_id": version["version_id"],
        "source_commit": version["source_commit"],
        "representation_path": version["path"],
        "content_sha256": version["content_sha256"],
        "study_eligible": version["study_eligible"],
        "adoption_eligible": version["adoption_eligible"],
        "builder_eligible": version["builder_eligible"],
    }
    study = {
        "schema_version": runner.exogenous_registry.STUDY_SCHEMA,
        "study_id": "acceptance-study",
        "title": "Two-pair acceptance study",
        "taskset_ref": {"taskset_id": taskset["taskset_id"], "path": "benchmarks/service-plan/v1/TASKSET.json", "sha256": runner.exogenous_registry.file_sha256(taskset_path)},
        "protocol_sha256": "sha256:" + "6" * 64,
        "comparison_intent": "observational",
        "conditions": [
            {"condition_id": "corridor-method", "system_condition": "corridor", "knowledge_condition": "method-paper", "common_inputs_sha256": "sha256:" + "7" * 64, "treatment_inputs_sha256": "sha256:" + "8" * 64, "method_paper_ref": method_ref},
            {"condition_id": "task-only", "system_condition": "task-only", "knowledge_condition": "task-only", "common_inputs_sha256": "sha256:" + "7" * 64, "treatment_inputs_sha256": "sha256:" + "9" * 64, "method_paper_ref": None},
        ],
        "assignment": {"mode": "fixed", "unit": "run", "assignment_sha256": "sha256:" + "a" * 64},
    }
    study_path = exogenous / "studies" / "acceptance-study" / "STUDY.json"
    write_json(study_path, study)
    plan = runner.measurement_plan()
    write_json(evidence / value["measurement_plan_path"], plan)
    plan_sha = runner.runtime.sha256_json(plan)
    run_map = {}
    for pair_index in (1, 2):
        for arm in ("treatment", "control"):
            run_id = f"{arm}-run-{pair_index}"
            condition_id = "corridor-method" if arm == "treatment" else "task-only"
            system = "corridor" if arm == "treatment" else "task-only"
            run = {
                "schema_version": runner.exogenous_registry.RUN_SCHEMA,
                "template": False,
                "run_id": run_id,
                "runner_id": f"run-operator-{run_id}",
                "study_ref": {"study_id": study["study_id"], "path": "studies/acceptance-study/STUDY.json", "sha256": runner.exogenous_registry.file_sha256(study_path)},
                "task_ref": {"taskset_id": taskset["taskset_id"], "taskset_sha256": runner.exogenous_registry.file_sha256(taskset_path), "task_id": "task-001", "task_sha256": task_sha},
                "condition_id": condition_id,
                "status": "completed",
                "trial": pair_index,
                "seed": f"seed-{pair_index}",
                "runtime": {"executor_type": "ai-agent", "provider": "test-provider", "model": "test-model", "runtime": "test-runtime", "profile_sha256": "sha256:" + "b" * 64, "tools_sha256": "sha256:" + "c" * 64, "network_access": "disabled", "budget_sha256": "sha256:" + "d" * 64, "stopping_rule_sha256": "sha256:" + "e" * 64},
                "measurement_plan": plan,
                "world_ref": {
                    "project_id": "charting-loop",
                    "run_id": run_id,
                    "generation_id": "acceptance-generation-1",
                    "repository_url": "https://example.invalid/participant",
                    "base_commit": COMMITS[1],
                    "environment_sha256": runner.exogenous_registry.canonical_sha256(taskset["environment"]),
                    "evidence_prefix": {
                        "stream_id": "acceptance-raw-ledger",
                        "through_sequence": 0,
                        "prefix_sha256": "sha256:" + "1" * 64,
                        "admission": {
                            "receipt_id": "acceptance-admission-receipt",
                            "admitted_root_sha256": "sha256:" + "2" * 64,
                            "rule_revision": "acceptance-rule-v1",
                            "rule_sha256": "sha256:" + "3" * 64,
                        },
                        "projector": {
                            "schema_version": "charting-loop/world-projector/v1",
                            "algorithm_id": "acceptance-projector",
                            "algorithm_version": "1",
                            "algorithm_sha256": "sha256:" + "4" * 64,
                        },
                    },
                    "derived_state_sha256": "sha256:" + "f" * 64,
                },
                "subject": {"system_condition": system, "repository_url": "https://example.invalid/participant", "base_commit": COMMITS[1], "artifact_commit": COMMITS[2], "artifact_root": f"runs/{run_id}/output", "artifact_tree_sha256": "sha256:" + "f" * 64, "branch_hint": f"exp/{run_id}"},
                "supersedes_run_id": None,
            }
            path = exogenous / "runs" / run_id / "RUN.json"
            write_json(path, run)
            run_map[run_id] = (run, runner.runtime.file_sha256(path))
    (exogenous / "registry").mkdir(parents=True)
    for item in value["attempts"]:
        run_id = item["run_path"].split("/", 1)[1]
        run, run_sha = run_map[run_id]
        common = runner._common_conditions(
            run, evaluator_sha256=runner.exogenous_registry.canonical_sha256(evaluator)
        )
        item["common_condition_sha256"] = runner.runtime.sha256_json(common)
        raw_path = evidence / item["evidence"][0]["path"]
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(f"evidence for {item['attempt_id']}\n", encoding="utf-8")
        if item["arm"] != "control":
            item["candidate_sha256"] = runner.runtime.file_sha256(raw_path)
        write_json(evidence / item["session_receipt_path"], session_receipt(item))
        write_json(
            evidence / item["usage_receipt_path"],
            usage_receipt(item, run, run_sha, plan_sha),
        )
    for selected in value["pairs"]:
        builder = next(item for item in value["attempts"] if item["attempt_id"] == selected["builder_attempt_id"])
        treatment = next(item for item in value["attempts"] if item["attempt_id"] == selected["treatment_attempt_id"])
        treatment_path = evidence / treatment["evidence"][0]["path"]
        treatment_path.write_bytes((evidence / builder["evidence"][0]["path"]).read_bytes())
        treatment["candidate_sha256"] = builder["candidate_sha256"]
        selected["candidate_sha256"] = builder["candidate_sha256"]
        selected["common_condition_sha256"] = builder["common_condition_sha256"]


class ServicePlanAcceptanceRunnerTests(unittest.TestCase):
    def test_manual_flag_and_manifest_confirmation_are_both_required(self) -> None:
        value = input_document()
        with self.assertRaises(runner.AcceptanceInputError) as caught:
            runner.validate_acceptance_input(value, manual=False)
        self.assertEqual(caught.exception.code, "manual_confirmation_required")
        value["manual_confirmation"] = False
        with self.assertRaises(runner.AcceptanceInputError) as caught:
            runner.validate_acceptance_input(value, manual=True)
        self.assertEqual(caught.exception.code, "manual_confirmation_required")

    def test_cli_fails_closed_without_manual_and_writes_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            write_json(input_path, input_document())
            output = root / "acceptance.json"
            completed = subprocess.run(
                [sys.executable, str(RUNNER_PATH), "--input", str(input_path), "--evidence-root", str(root), "--exogenous-root", str(root), "--method-index", str(root / "missing.json"), "--output", str(output)],
                cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(json.loads(completed.stderr)["code"], "manual_confirmation_required")
            self.assertFalse(output.exists())

    def test_exact_schema_and_agent_requirements_fail_closed(self) -> None:
        value = input_document()
        value["validation_ok"] = True
        with self.assertRaises(runner.AcceptanceInputError) as caught:
            runner.validate_acceptance_input(value, manual=True)
        self.assertEqual(caught.exception.code, "input_fields")
        value = input_document()
        value["attempts"][0]["scripted"] = True
        with self.assertRaises(runner.AcceptanceInputError) as caught:
            runner.validate_acceptance_input(value, manual=True)
        self.assertEqual(caught.exception.code, "real_ai_required")

    def test_safe_file_rejects_parent_escape_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real.txt").write_text("bytes")
            (root / "link.txt").symlink_to(root / "real.txt")
            for relative in ("../real.txt", "link.txt"):
                with self.assertRaises(runner.AcceptanceInputError) as caught:
                    runner.safe_file(root, relative, label="test")
                self.assertEqual(caught.exception.code, "unsafe_path")

    def test_failed_and_repaired_attempts_are_retained_with_ancestry(self) -> None:
        value = input_document(two_pairs=True)
        failed = attempt("treatment-0", "treatment", "session-treatment-0", outcome="failed")
        value["attempts"].insert(0, failed)
        value["attempts"][2]["supersedes_attempt_id"] = failed["attempt_id"]
        value["attempts"][2]["repair_reason"] = "fresh retry after failure"
        validated = runner.validate_acceptance_input(value, manual=True)
        self.assertEqual(validated["attempts"][0]["outcome"], "failed")
        self.assertEqual(validated["attempts"][2]["supersedes_attempt_id"], "treatment-0")

    def test_session_receipt_binds_actual_bytes_and_independent_issuer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            item = input_document()["attempts"][0]
            write_json(root / item["session_receipt_path"], session_receipt(item))
            relative, digest, _ = runner.load_session_receipt(
                item,
                evidence_root=root,
                assembler={"runner_id": "manual-runner", "session_id": "runner-session", "invocation_id": "runner-invocation"},
                forbidden_issuer_values=set(),
            )
            self.assertEqual(relative, item["session_receipt_path"])
            self.assertEqual(digest, runner.runtime.file_sha256(root / relative))
            receipt = session_receipt(item)
            receipt["issuer_session_id"] = item["session_id"]
            write_json(root / item["session_receipt_path"], receipt)
            with self.assertRaises(runner.AcceptanceInputError) as caught:
                runner.load_session_receipt(item, evidence_root=root, assembler={"runner_id": "manual-runner", "session_id": "runner-session", "invocation_id": "runner-invocation"}, forbidden_issuer_values=set())
            self.assertEqual(caught.exception.code, "session_receipt_independence")

    def test_output_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            path.write_text("existing")
            with self.assertRaises(runner.AcceptanceInputError) as caught:
                runner.write_new_atomic(path, {"new": True})
            self.assertEqual(caught.exception.code, "output_exists")
            self.assertEqual(path.read_text(), "existing")

    def test_usage_incomplete_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            item = input_document()["attempts"][0]
            run = {"run_id": "treatment-run-1", "__run_sha256": DIGEST}
            receipt = usage_receipt(item, run, DIGEST, DIGEST)
            receipt["stages"][0]["assessment_status"] = "not_assessed"
            for metric in runner.runtime.USAGE_METRICS:
                receipt["stages"][0][metric] = None
            write_json(root / item["usage_receipt_path"], receipt)
            with self.assertRaises(runner.AcceptanceInputError) as caught:
                runner.load_usage_receipts(
                    {"attempts": [item]},
                    evidence_root=root,
                    plan_sha256=DIGEST,
                    run_by_attempt={item["attempt_id"]: run},
                )
            self.assertEqual(caught.exception.code, "usage_incomplete")

    def test_replay_must_bind_complete_payload_and_independent_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = input_document()
            attempts = [
                {
                    "attempt_id": item["attempt_id"],
                    "session_id": item["session_id"],
                    "invocation_id": item["invocation_id"],
                    "outcome": item["outcome"],
                }
                for item in value["attempts"]
            ]
            record = {
                "schema_version": runner.runtime.ACCEPTANCE_RECORD_SCHEMA,
                "acceptance_id": value["acceptance_id"],
                "assembler": {"runner_id": value["runner_id"], "session_id": value["runner_session_id"], "invocation_id": value["runner_invocation_id"]},
                "source_validation_sha256": DIGEST,
                "run_bindings": [],
                "method_binding": {},
                "measurement_plan": runner.measurement_plan(),
                "usage_receipts": [],
                "package_costs": [],
                "raw_evidence": [],
                "attempts": attempts,
                "pairs": [],
                "independent_replay": {},
                "gate": {},
            }
            outcome_sha = runner.runtime.sha256_json(
                {"attempt_outcomes": [{"attempt_id": item["attempt_id"], "outcome": item["outcome"]} for item in sorted(attempts, key=lambda item: item["attempt_id"])], "clean_pair_ids": []}
            )
            receipt = {
                "schema_version": runner.REPLAY_RECEIPT_SCHEMA,
                "replay_id": "replay",
                "verifier_id": "verifier",
                "verifier_session_id": "verifier-session",
                "verifier_invocation_id": "verifier-invocation",
                "runner_id": value["runner_id"],
                "runner_session_id": value["runner_session_id"],
                "runner_invocation_id": value["runner_invocation_id"],
                "payload_sha256": runner.runtime.sha256_json(runner.runtime._replay_payload(record)),
                "outcome_sha256": outcome_sha,
                "verified": True,
            }
            write_json(root / value["replay_receipt_path"], receipt)
            loaded = runner.load_replay_receipt(value, evidence_root=root, record=record, clean_pair_ids=[])
            self.assertEqual(loaded["receipt_path"], value["replay_receipt_path"])
            receipt["verifier_session_id"] = value["runner_session_id"]
            write_json(root / value["replay_receipt_path"], receipt)
            with self.assertRaises(runner.AcceptanceInputError) as caught:
                runner.load_replay_receipt(value, evidence_root=root, record=record, clean_pair_ids=[])
            self.assertEqual(caught.exception.code, "replay_independence")

    def test_real_two_pair_build_validate_and_cli_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, exogenous = root / "evidence", root / "exogenous"
            evidence.mkdir()
            exogenous.mkdir()
            value = input_document(two_pairs=True)
            make_exogenous_fixture(exogenous, evidence, value)
            method_index = REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"

            payload, source_validation = runner.assemble_record_payload(
                value, evidence_root=evidence, exogenous_root=exogenous, method_index=method_index
            )
            clean_ids = runner.derive_clean_pair_ids(
                payload["pairs"], payload["attempts"], payload["run_bindings"], payload["method_binding"]
            )
            replay = {
                "schema_version": runner.REPLAY_RECEIPT_SCHEMA,
                "replay_id": "replay-1",
                "verifier_id": "independent-verifier",
                "verifier_session_id": "independent-verifier-session",
                "verifier_invocation_id": "independent-verifier-invocation",
                "runner_id": value["runner_id"],
                "runner_session_id": value["runner_session_id"],
                "runner_invocation_id": value["runner_invocation_id"],
                "payload_sha256": runner.runtime.sha256_json(runner.runtime._replay_payload(payload)),
                "outcome_sha256": runner.runtime.sha256_json(
                    {"attempt_outcomes": [{"attempt_id": item["attempt_id"], "outcome": item["outcome"]} for item in sorted(payload["attempts"], key=lambda item: item["attempt_id"])], "clean_pair_ids": clean_ids}
                ),
                "verified": True,
            }
            write_json(evidence / value["replay_receipt_path"], replay)
            record, trusted = runner.build_record(
                value, evidence_root=evidence, exogenous_root=exogenous, method_index=method_index
            )
            self.assertEqual(trusted["source_validation"], source_validation)
            report = runner.validate_record(record, trusted_context=trusted, evidence_root=evidence)
            self.assertTrue(report.ok, report.errors)
            self.assertTrue(record["gate"]["instrumented_acceptance_pilot_ready"])
            self.assertFalse(record["gate"]["formal_comparison_ready"])
            self.assertFalse(record["gate"]["benchmark_result"])
            self.assertFalse(record["gate"]["causal_claim_allowed"])
            self.assertFalse(record["gate"]["adoption_claim_allowed"])
            self.assertEqual(record["gate"]["authority_warranty_state"], "not_assessed")

            input_path, output_path = root / "input.json", root / "acceptance.json"
            write_json(input_path, value)
            completed = subprocess.run(
                [sys.executable, str(RUNNER_PATH), "--manual", "--input", str(input_path), "--evidence-root", str(evidence), "--exogenous-root", str(exogenous), "--method-index", str(method_index), "--output", str(output_path)],
                cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["instrumented_acceptance_pilot_ready"])
            self.assertEqual(json.loads(output_path.read_text()), record)

    def test_oversized_run_integer_is_a_stable_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, exogenous = root / "evidence", root / "exogenous"
            evidence.mkdir()
            exogenous.mkdir()
            value = input_document(two_pairs=True)
            make_exogenous_fixture(exogenous, evidence, value)
            run_path = exogenous / "runs" / "treatment-run-1" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["trial"] = 1 << runner.runtime.MAX_JSON_INTEGER_BITS
            write_json(run_path, run)

            with self.assertRaises(runner.AcceptanceInputError) as caught:
                runner.assemble_record_payload(
                    value,
                    evidence_root=evidence,
                    exogenous_root=exogenous,
                    method_index=REPOSITORY_ROOT / "method-paper" / "VERSIONS.json",
                )
            self.assertEqual(caught.exception.code, "canonical_json")

    def test_sealed_two_pair_record_rejects_join_and_evidence_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, exogenous = root / "evidence", root / "exogenous"
            evidence.mkdir()
            exogenous.mkdir()
            value = input_document(two_pairs=True)
            make_exogenous_fixture(exogenous, evidence, value)
            method_index = REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"
            payload, _source = runner.assemble_record_payload(
                value,
                evidence_root=evidence,
                exogenous_root=exogenous,
                method_index=method_index,
            )
            clean_ids = runner.derive_clean_pair_ids(
                payload["pairs"],
                payload["attempts"],
                payload["run_bindings"],
                payload["method_binding"],
            )
            replay = {
                "schema_version": runner.REPLAY_RECEIPT_SCHEMA,
                "replay_id": "replay-mutation-base",
                "verifier_id": "independent-verifier",
                "verifier_session_id": "independent-verifier-session",
                "verifier_invocation_id": "independent-verifier-invocation",
                "runner_id": value["runner_id"],
                "runner_session_id": value["runner_session_id"],
                "runner_invocation_id": value["runner_invocation_id"],
                "payload_sha256": runner.runtime.sha256_json(
                    runner.runtime._replay_payload(payload)
                ),
                "outcome_sha256": runner.runtime.sha256_json(
                    {
                        "attempt_outcomes": [
                            {
                                "attempt_id": item["attempt_id"],
                                "outcome": item["outcome"],
                            }
                            for item in sorted(
                                payload["attempts"],
                                key=lambda item: item["attempt_id"],
                            )
                        ],
                        "clean_pair_ids": clean_ids,
                    }
                ),
                "verified": True,
            }
            write_json(evidence / value["replay_receipt_path"], replay)
            record, trusted = runner.build_record(
                value,
                evidence_root=evidence,
                exogenous_root=exogenous,
                method_index=method_index,
            )
            baseline = runner.validate_record(
                record, trusted_context=trusted, evidence_root=evidence
            )
            self.assertTrue(baseline.ok, baseline.errors)
            self.assertEqual(
                [item["corridor_e2e"]["total"]["input_tokens"] for item in baseline.facts["pair_cost_accounting"]],
                [12, 12],
            )
            self.assertEqual(
                [item["control_task"]["total"]["input_tokens"] for item in baseline.facts["pair_cost_accounting"]],
                [6, 6],
            )

            def rejected(mutant: object, context: object = trusted) -> set[str]:
                report = runner.runtime.validate_acceptance_record(
                    mutant,
                    trusted_context=context,  # type: ignore[arg-type]
                    evidence_root=evidence,
                )
                self.assertFalse(report.ok)
                self.assertFalse(report.facts["instrumented_acceptance_pilot_ready"])
                return {error["code"] for error in report.errors}

            mutant = copy.deepcopy(record)
            mutant["usage_receipts"][0]["stages"][0]["assessment_status"] = "not_assessed"
            for metric in runner.runtime.USAGE_METRICS:
                mutant["usage_receipts"][0]["stages"][0][metric] = None
            mutant["package_costs"][0] = runner.runtime.package_cost_from_usage(
                mutant["usage_receipts"][0]
            )
            self.assertIn("USAGE_INCOMPLETE", rejected(mutant))
            accounting = next(
                item
                for item in runner.runtime.validate_acceptance_record(
                    mutant,
                    trusted_context=trusted,
                    evidence_root=evidence,
                ).facts["pair_cost_accounting"]
                if item["pair_id"] == "pair-1"
            )
            self.assertFalse(accounting["corridor_e2e"]["complete"])
            self.assertIsNone(accounting["corridor_e2e"]["total"]["input_tokens"])
            self.assertIn(
                "builder-1:usage-incomplete",
                accounting["corridor_e2e"]["missing_stages"],
            )

            mutant = copy.deepcopy(record)
            mutant["method_binding"]["study_id"] = "other-study"
            self.assertTrue(
                {"PAIR_NOT_CLEAN", "SOURCE_STUDY_JOIN"} & rejected(mutant)
            )

            context = copy.deepcopy(trusted)
            context["source_validation"]["formal_method_study_eligible"] = False
            self.assertIn("SOURCE_VALIDATION_DIGEST", rejected(record, context))

            mutant = copy.deepcopy(record)
            mutant["run_bindings"][0]["runner_id"] = "forged-runner-id"
            self.assertIn("SOURCE_RUN_JOIN", rejected(mutant))

            mutant = copy.deepcopy(record)
            mutant["package_costs"].append(copy.deepcopy(mutant["package_costs"][0]))
            self.assertIn("DUPLICATE_PACKAGE_COST", rejected(mutant))

            mutant = copy.deepcopy(record)
            mutant["pairs"][1]["pair_id"] = mutant["pairs"][0]["pair_id"]
            self.assertIn("DUPLICATE_PAIR", rejected(mutant))

            mutant = copy.deepcopy(record)
            mutant["pairs"][0]["builder_attempt_id"] = "missing-attempt"
            self.assertIn("PAIR_NOT_CLEAN", rejected(mutant))

            mutant = copy.deepcopy(record)
            mutant["attempts"][0]["supersedes_attempt_id"] = mutant["attempts"][1]["attempt_id"]
            mutant["attempts"][0]["repair_reason"] = "invalid forward reference"
            self.assertIn("REPAIR_ANCESTRY", rejected(mutant))

            for key, malformed in (
                ("attempts", 0),
                ("independent_replay", []),
            ):
                with self.subTest(malformed=key):
                    mutant = copy.deepcopy(record)
                    mutant[key] = malformed
                    self.assertTrue(rejected(mutant))
            mutant = copy.deepcopy(record)
            mutant["attempts"][0]["artifact_ids"] = 0
            self.assertTrue(rejected(mutant))
            mutant = copy.deepcopy(record)
            mutant["independent_replay"]["verifier_id"] = []
            self.assertTrue(rejected(mutant))
            mutant = copy.deepcopy(record)
            mutant["raw_evidence"][0]["path"] = "bad\x00path"
            self.assertTrue(rejected(mutant))

            mutant = copy.deepcopy(record)
            mutant["gate"] = {}
            self.assertIn("GATE_DERIVATION", rejected(mutant))

            for key, replacement in (
                ("instrumented_acceptance_pilot_ready", 1),
                ("formal_comparison_ready", 0),
                ("required_clean_pair_count", 2.0),
            ):
                with self.subTest(gate_type=key):
                    mutant = copy.deepcopy(record)
                    mutant["gate"][key] = replacement
                    self.assertIn("GATE_DERIVATION", rejected(mutant))

            mutant = copy.deepcopy(record)
            mutant["package_costs"][0]["secondary"]["non_additive"] = 1
            self.assertIn("PACKAGE_COST_DERIVATION", rejected(mutant))

            raw_path = evidence / record["raw_evidence"][0]["path"]
            raw_original = raw_path.read_bytes()
            raw_path.write_bytes(raw_original + b"tampered")
            try:
                self.assertIn("EVIDENCE_DIGEST", rejected(record))
            finally:
                raw_path.write_bytes(raw_original)

            session_path = evidence / record["attempts"][0]["session_receipt_path"]
            session_original = session_path.read_bytes()
            session_path.write_bytes(session_original + b" ")
            try:
                self.assertIn("SESSION_RECEIPT_DIGEST", rejected(record))
            finally:
                session_path.write_bytes(session_original)

            replay_path = evidence / record["independent_replay"]["receipt_path"]
            replay_original = replay_path.read_bytes()
            replay_path.write_bytes(replay_original + b" ")
            try:
                self.assertIn("REPLAY_RECEIPT_DIGEST", rejected(record))
            finally:
                replay_path.write_bytes(replay_original)

    def test_repaired_lineage_is_counted_and_cannot_reuse_a_run_across_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, exogenous = root / "evidence", root / "exogenous"
            evidence.mkdir()
            exogenous.mkdir()
            value = input_document(two_pairs=True)
            old = attempt(
                "treatment-old",
                "treatment",
                "session-treatment-old",
                outcome="failed",
            )
            old["run_path"] = "runs/treatment-run-2"
            value["attempts"].insert(3, old)
            selected = next(
                item for item in value["attempts"] if item["attempt_id"] == "treatment-2"
            )
            selected["supersedes_attempt_id"] = old["attempt_id"]
            selected["repair_reason"] = "fresh retry after retained failure"
            make_exogenous_fixture(exogenous, evidence, value)
            method_index = REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"
            payload, _source = runner.assemble_record_payload(
                value,
                evidence_root=evidence,
                exogenous_root=exogenous,
                method_index=method_index,
            )
            clean_ids = runner.derive_clean_pair_ids(
                payload["pairs"],
                payload["attempts"],
                payload["run_bindings"],
                payload["method_binding"],
            )
            self.assertEqual(clean_ids, ["pair-1", "pair-2"])
            replay = {
                "schema_version": runner.REPLAY_RECEIPT_SCHEMA,
                "replay_id": "replay-repaired-lineage",
                "verifier_id": "independent-verifier",
                "verifier_session_id": "independent-verifier-session",
                "verifier_invocation_id": "independent-verifier-invocation",
                "runner_id": value["runner_id"],
                "runner_session_id": value["runner_session_id"],
                "runner_invocation_id": value["runner_invocation_id"],
                "payload_sha256": runner.runtime.sha256_json(
                    runner.runtime._replay_payload(payload)
                ),
                "outcome_sha256": runner.runtime.sha256_json(
                    {
                        "attempt_outcomes": [
                            {
                                "attempt_id": item["attempt_id"],
                                "outcome": item["outcome"],
                            }
                            for item in sorted(
                                payload["attempts"],
                                key=lambda item: item["attempt_id"],
                            )
                        ],
                        "clean_pair_ids": clean_ids,
                    }
                ),
                "verified": True,
            }
            write_json(evidence / value["replay_receipt_path"], replay)
            record, trusted = runner.build_record(
                value,
                evidence_root=evidence,
                exogenous_root=exogenous,
                method_index=method_index,
            )
            report = runner.validate_record(
                record,
                trusted_context=trusted,
                evidence_root=evidence,
            )
            self.assertTrue(report.ok, report.errors)
            pair_two = next(
                item
                for item in report.facts["pair_cost_accounting"]
                if item["pair_id"] == "pair-2"
            )
            self.assertEqual(
                pair_two["corridor_e2e"]["attempt_ids"],
                ["builder-2", "treatment-old", "treatment-2"],
            )
            self.assertEqual(
                pair_two["corridor_e2e"]["total"]["input_tokens"],
                18,
            )

            # Moving the retained ancestor onto pair 1's selected RUN makes the
            # pair lineages overlap even though every attempt/session is distinct.
            old_attempt = next(
                item for item in payload["attempts"] if item["attempt_id"] == "treatment-old"
            )
            old_attempt["run_id"] = "treatment-run-1"
            old_attempt["common_condition_sha256"] = next(
                run["common_condition_sha256"]
                for run in payload["run_bindings"]
                if run["run_id"] == "treatment-run-1"
            )
            self.assertEqual(
                runner.derive_clean_pair_ids(
                    payload["pairs"],
                    payload["attempts"],
                    payload["run_bindings"],
                    payload["method_binding"],
                ),
                ["pair-1"],
            )

    def test_nested_unregistered_run_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, exogenous = root / "evidence", root / "exogenous"
            evidence.mkdir()
            exogenous.mkdir()
            value = input_document(two_pairs=True)
            make_exogenous_fixture(exogenous, evidence, value)
            source = exogenous / "runs" / "treatment-run-1" / "RUN.json"
            nested = exogenous / "runs" / "treatment-run-1" / "unregistered"
            nested.mkdir()
            nested.joinpath("RUN.json").write_bytes(source.read_bytes())
            value["attempts"][0]["run_path"] = (
                "runs/treatment-run-1/unregistered"
            )
            with self.assertRaises(runner.AcceptanceInputError) as caught:
                runner.assemble_record_payload(
                    value,
                    evidence_root=evidence,
                    exogenous_root=exogenous,
                    method_index=REPOSITORY_ROOT / "method-paper" / "VERSIONS.json",
                )
            self.assertEqual(caught.exception.code, "run_path")


if __name__ == "__main__":
    unittest.main()
