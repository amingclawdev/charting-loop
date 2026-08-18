from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import exogenous_registry as registry
from tools import public_release


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DIGESTS = ["sha256:" + (character * 64) for character in "123456789abcdef"]
COMMITS = [character * 40 for character in "1234"]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def make_fixture(root: Path, *, run_id: str = "run-001", scored: bool = False) -> None:
    taskset_dir = root / "benchmarks" / "bench" / "v1"
    input_path = taskset_dir / "tasks" / "task.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text('{"task":"frozen"}\n', encoding="utf-8")
    task_digest = registry.file_sha256(input_path)
    tasks = [
        {
            "task_id": "task-001",
            "input": {
                "kind": "vendored",
                "locator": "tasks/task.json",
                "sha256": task_digest,
            },
        }
    ]
    evaluator = {
        "scorer_id": "scorer",
        "scorer_revision": "v1",
        "scorer_sha256": DIGESTS[0],
        "verifier_id": "verifier",
        "verifier_revision": "v1",
        "verifier_sha256": DIGESTS[1],
    }
    taskset = {
        "schema_version": registry.TASKSET_SCHEMA,
        "taskset_id": "bench-v1",
        "benchmark": {
            "dataset_id": "bench",
            "release": "v1",
            "repository_url": "https://example.invalid/benchmark",
            "source_commit": COMMITS[0],
        },
        "tasks": tasks,
        "task_list_sha256": registry.canonical_sha256(
            [{"task_id": "task-001", "input_sha256": task_digest}]
        ),
        "environment": {
            "environment_id": "env-v1",
            "image_sha256": DIGESTS[2],
            "data_sha256": DIGESTS[3],
        },
        "evaluator": evaluator,
        "license": {"identifier": "test-only", "redistribution": "vendored"},
    }
    taskset_path = taskset_dir / "TASKSET.json"
    write_json(taskset_path, taskset)

    study = {
        "schema_version": registry.STUDY_SCHEMA,
        "study_id": "study-001",
        "title": "Frozen task-only study",
        "taskset_ref": {
            "taskset_id": "bench-v1",
            "path": "benchmarks/bench/v1/TASKSET.json",
            "sha256": registry.file_sha256(taskset_path),
        },
        "protocol_sha256": DIGESTS[4],
        "comparison_intent": "observational",
        "conditions": [
            {
                "condition_id": "task-only",
                "system_condition": "task-only",
                "knowledge_condition": "task-only",
                "common_inputs_sha256": DIGESTS[5],
                "treatment_inputs_sha256": DIGESTS[6],
                "method_paper_ref": None,
            }
        ],
        "assignment": {
            "mode": "fixed",
            "unit": "run",
            "assignment_sha256": DIGESTS[7],
        },
    }
    study_path = root / "studies" / "study-001" / "STUDY.json"
    write_json(study_path, study)

    run = {
        "schema_version": registry.RUN_SCHEMA,
        "template": False,
        "run_id": run_id,
        "runner_id": "runner-001",
        "study_ref": {
            "study_id": "study-001",
            "path": "studies/study-001/STUDY.json",
            "sha256": registry.file_sha256(study_path),
        },
        "task_ref": {
            "taskset_id": "bench-v1",
            "taskset_sha256": registry.file_sha256(taskset_path),
            "task_id": "task-001",
            "task_sha256": task_digest,
        },
        "condition_id": "task-only",
        "status": "completed",
        "trial": 0,
        "seed": "seed-001",
        "runtime": {
            "executor_type": "ai-agent",
            "provider": "test-provider",
            "model": "test-model",
            "runtime": "test-runtime",
            "profile_sha256": DIGESTS[8],
            "tools_sha256": DIGESTS[9],
            "network_access": "disabled",
            "budget_sha256": DIGESTS[10],
            "stopping_rule_sha256": DIGESTS[11],
        },
        "measurement_plan": {
            "schema_version": registry.MEASUREMENT_PLAN_SCHEMA,
            "usage_receipt_schema": registry.USAGE_RECEIPT_SCHEMA,
            "package_cost_schema": registry.PACKAGE_COST_SCHEMA,
            "required_usage_stages": list(registry.REQUIRED_USAGE_STAGES),
            "raw_evidence_profile": "complete-digest-bound",
            "independent_replay_required": True,
        },
        "world_ref": {
            "project_id": "charting-loop",
            "run_id": run_id,
            "generation_id": "generation-001",
            "repository_url": "https://example.invalid/participant",
            "base_commit": COMMITS[1],
            "environment_sha256": registry.canonical_sha256(taskset["environment"]),
            "evidence_prefix": {
                "stream_id": "test-raw-ledger",
                "through_sequence": 0,
                "prefix_sha256": DIGESTS[13],
                "admission": {
                    "receipt_id": "admission-receipt-001",
                    "admitted_root_sha256": DIGESTS[14],
                    "rule_revision": "admission-rule-v1",
                    "rule_sha256": DIGESTS[0],
                },
                "projector": {
                    "schema_version": "charting-loop/world-projector/v1",
                    "algorithm_id": "test-world-projector",
                    "algorithm_version": "1",
                    "algorithm_sha256": DIGESTS[1],
                },
            },
            "derived_state_sha256": DIGESTS[12],
        },
        "subject": {
            "system_condition": "task-only",
            "repository_url": "https://example.invalid/participant",
            "base_commit": COMMITS[1],
            "artifact_commit": COMMITS[2],
            "artifact_root": f"runs/{run_id}/output",
            "artifact_tree_sha256": DIGESTS[12],
            "branch_hint": "exp/test",
        },
        "supersedes_run_id": None,
    }
    run_path = root / "runs" / run_id / "RUN.json"
    write_json(run_path, run)
    if scored:
        score = {
            "schema_version": registry.SCORE_SCHEMA,
            "score_id": f"score-{run_id}",
            "evaluator_id": "evaluator-001",
            "run_ref": {
                "run_id": run_id,
                "sha256": registry.file_sha256(run_path),
            },
            "task_ref": run["task_ref"],
            "evaluator": evaluator,
            "environment_sha256": run["world_ref"]["environment_sha256"],
            "world_ref_sha256": registry.canonical_sha256(run["world_ref"]),
            "subject_ref": {
                "artifact_commit": run["subject"]["artifact_commit"],
                "artifact_tree_sha256": run["subject"]["artifact_tree_sha256"],
            },
            "trial": run["trial"],
            "seed": run["seed"],
            "outcome_status": "passed",
            "raw_outcome": {"score": 1},
            "infrastructure_status": "ok",
            "evaluated_at": "2026-08-12T00:00:00Z",
        }
        write_json(run_path.parent / "SCORE.json", score)
    (root / "registry").mkdir(parents=True)


def copy_method_project(root: Path) -> None:
    for directory in ("method-paper", "catalog", "theory"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "catalog" / "v4").mkdir()
    (root / "catalog" / "v5").mkdir()
    (root / "catalog" / "v6").mkdir()
    (root / "catalog" / "v7").mkdir()
    for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
        shutil.copy2(
            REPOSITORY_ROOT / "method-paper" / name,
            root / "method-paper" / name,
        )
    for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
        shutil.copy2(
            REPOSITORY_ROOT / "catalog" / name,
            root / "catalog" / name,
        )
        shutil.copy2(
            REPOSITORY_ROOT / "catalog" / "v4" / name,
            root / "catalog" / "v4" / name,
        )
        shutil.copy2(
            REPOSITORY_ROOT / "catalog" / "v5" / name,
            root / "catalog" / "v5" / name,
        )
        shutil.copy2(
            REPOSITORY_ROOT / "catalog" / "v6" / name,
            root / "catalog" / "v6" / name,
        )
        shutil.copy2(
            REPOSITORY_ROOT / "catalog" / "v7" / name,
            root / "catalog" / "v7" / name,
        )
    shutil.copy2(
        REPOSITORY_ROOT / "theory" / "VERSIONS.json",
        root / "theory" / "VERSIONS.json",
    )


def downgrade_fixture_to_v1(root: Path, *, run_id: str = "run-001") -> None:
    study_path = root / "studies" / "study-001" / "STUDY.json"
    study = json.loads(study_path.read_text(encoding="utf-8"))
    study["schema_version"] = registry.LEGACY_STUDY_SCHEMA
    write_json(study_path, study)

    run_path = root / "runs" / run_id / "RUN.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["schema_version"] = registry.LEGACY_RUN_SCHEMA
    run.pop("measurement_plan")
    run["study_ref"]["sha256"] = registry.file_sha256(study_path)
    run["world_ref"] = {
        "base_commit": run["world_ref"]["base_commit"],
        "environment_sha256": run["world_ref"]["environment_sha256"],
        "evidence_prefix": None,
    }
    write_json(run_path, run)

    score_path = run_path.parent / "SCORE.json"
    if score_path.exists():
        score = json.loads(score_path.read_text(encoding="utf-8"))
        score["run_ref"]["sha256"] = registry.file_sha256(run_path)
        score["world_ref_sha256"] = registry.canonical_sha256(run["world_ref"])
        write_json(score_path, score)


class ExogenousRegistryTests(unittest.TestCase):
    def test_append_only_waiver_is_exact_base_path_and_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Waiver Test"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "waiver@example.invalid"],
                cwd=root,
                check=True,
            )
            method_digest = DIGESTS[0]
            scope_digest = DIGESTS[1]
            method_catalog = {
                "versions": [
                    {
                        "study_eligible": True,
                        "content_sha256": method_digest,
                        "scope_datum_sha256": scope_digest,
                    }
                ]
            }
            write_json(root / "method-paper" / "VERSIONS.json", method_catalog)
            exogenous = root / "exogenous"
            core_path = exogenous / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            core_path.parent.mkdir(parents=True)
            core_path.write_text('{"version":1}\n', encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "public base"], cwd=root, check=True)
            base_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            before_digest = "sha256:" + hashlib.sha256(core_path.read_bytes()).hexdigest()
            core_path.write_text('{"version":2}\n', encoding="utf-8")
            after_digest = "sha256:" + hashlib.sha256(core_path.read_bytes()).hexdigest()
            write_json(
                exogenous / "APPEND-ONLY-WAIVERS.json",
                {
                    "schema_version": registry.APPEND_ONLY_WAIVER_SCHEMA,
                    "waivers": [
                        {
                            "affected_files": [
                                {
                                    "after_sha256": after_digest,
                                    "before_sha256": before_digest,
                                    "path": "exogenous/benchmarks/bench/v1/TASKSET.json",
                                }
                            ],
                            "base_commit": base_commit,
                            "change_class": "public-provenance-repin-only",
                            "invariants": {
                                "method_content_sha256": method_digest,
                                "outcome_data_changed": False,
                                "scope_datum_sha256": scope_digest,
                                "solution_bearing_content_added": False,
                            },
                            "reason": "The private provenance commit cannot be published; repin identical bytes.",
                            "status": "waived",
                            "waiver_id": "test-public-provenance-repin",
                        }
                    ],
                },
            )

            report = registry.Report(subject="waived")
            registry.check_append_only(exogenous, base_commit, report)
            self.assertTrue(report.ok, report.errors)
            self.assertTrue(any("APPEND_ONLY_WAIVED" in warning for warning in report.warnings))

            core_path.write_text('{"version":3}\n', encoding="utf-8")
            tampered = registry.Report(subject="tampered")
            registry.check_append_only(exogenous, base_commit, tampered)
            self.assertFalse(tampered.ok)
            self.assertTrue(any("APPEND_ONLY_WAIVER_DIGEST" in error for error in tampered.errors))
            self.assertTrue(any("APPEND_ONLY" in error for error in tampered.errors))

    def test_replication_docs_separate_human_and_operator_context(self) -> None:
        invitation = (REPOSITORY_ROOT / "docs" / "REPLICATION-INVITATION.md").read_text(
            encoding="utf-8"
        )
        runbook = (REPOSITORY_ROOT / "docs" / "AI-REPLICATION-RUNBOOK.md").read_text(
            encoding="utf-8"
        )

        invitation_sections = [
            "## Two evidence dimensions worth testing",
            "## The Method, in brief",
            "## The Theory, in brief",
            "## Hypothesis",
            "## The simple matched design",
            "## What an independent report should answer",
            "## Running or publishing a study",
            "## Why this experiment exists",
        ]
        positions = [invitation.index(section) for section in invitation_sections]
        self.assertEqual(positions, sorted(positions))
        invitation_words = " ".join(invitation.split())
        for source_marker in (
            "[normative Method v8 source](../method-paper/METHOD.md)",
            "[published Theory v1 original](https://doi.org/10.5281/zenodo.21844624)",
            "[version and byte-identity catalog](../theory/README.md)",
        ):
            self.assertIn(source_marker, invitation)
        for origin_marker in (
            "The idea began in Aming Claw",
            "an agent could use the theory as a diagnostic method",
            "combine the theory with lessons from Aming Claw into a reusable methodology",
            "a fresh builder agent receives the frozen methodology and the task requirements",
            "one arm works with Corridor access and the other works without Corridor access",
        ):
            self.assertIn(origin_marker, invitation_words)
        self.assertNotIn("After Paper 2, an independent AI review", invitation_words)
        self.assertIn("fresh Worker and a separate fresh QA", invitation)
        self.assertNotIn("## Preferred independent replication", invitation)
        self.assertNotIn("## Minimum report", invitation)

        self.assertIn("# AI/operator replication runbook", runbook)
        self.assertIn(
            "MUST NOT\n> be exposed to experimental builder, Worker, or QA sessions",
            runbook,
        )
        self.assertIn(
            "protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md", runbook
        )
        self.assertIn("It does not add method rules", runbook)
        for section in (
            "## 1. Freeze before dispatch",
            "## 2. Construct and freeze the treatment",
            "## 3. Prepare the matched Docker pair",
            "## 4. Run Worker, QA, and bounded rework",
            "## 5. Score and classify every attempt",
            "## 6. Preserve evidence without changing visibility",
        ):
            self.assertIn(section, runbook)

    def test_checked_in_task_constraint_datum_is_closed_and_bound(self) -> None:
        exogenous_root = REPOSITORY_ROOT / "exogenous"
        taskset_path = (
            exogenous_root
            / "benchmarks"
            / "terminal-bench"
            / "3.0"
            / "TASKSET.json"
        )
        report, taskset = registry.validate_taskset(taskset_path, exogenous_root)
        self.assertTrue(report.ok, report.errors)
        self.assertIsNotNone(taskset)
        self.assertEqual(report.facts["schema_version"], registry.TASKSET_V2_SCHEMA)
        self.assertTrue(report.facts["task_constraint_required"])

        constraint_path = taskset_path.parent / taskset["tasks"][0]["constraint_datum"]["path"]
        constraint_report, constraint = registry.validate_task_constraint(
            constraint_path,
            expected_task_id="production-planning",
            expected_instruction_sha256=taskset["tasks"][0]["input"]["sha256"],
        )
        self.assertTrue(constraint_report.ok, constraint_report.errors)
        self.assertEqual(constraint["audit"]["starts_after"], "official-score")
        self.assertEqual(constraint["egress"]["task_public_internet"], "disabled")
        self.assertEqual(
            constraint["pair"]["treatment_only"],
            ["frozen-builder-branch-service", "minimal-consume-instruction"],
        )
        self.assertEqual(constraint["pair"]["control_only"], [])

    def test_taskset_v3_allows_an_immutable_release_variant(self) -> None:
        source_release = (
            REPOSITORY_ROOT
            / "exogenous"
            / "benchmarks"
            / "terminal-bench"
            / "3.0"
        )
        with tempfile.TemporaryDirectory() as temporary:
            exogenous_root = Path(temporary)
            variant = (
                exogenous_root
                / "benchmarks"
                / "terminal-bench"
                / "3.0"
                / "tasksets"
                / "tb30-cl029-worker-qa"
            )
            shutil.copytree(source_release, variant)
            taskset_path = variant / "TASKSET.json"
            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
            taskset["schema_version"] = registry.TASKSET_V3_SCHEMA
            taskset["taskset_id"] = "tb30-cl029-worker-qa"
            write_json(taskset_path, taskset)

            report, validated = registry.validate_taskset(taskset_path, exogenous_root)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(validated["schema_version"], registry.TASKSET_V3_SCHEMA)
            self.assertTrue(report.facts["task_constraint_required"])

            (exogenous_root / "runs").mkdir()
            collect_report, summaries = registry.collect_registry(exogenous_root)
            self.assertTrue(collect_report.ok, collect_report.errors)
            self.assertEqual(summaries, [])
            self.assertEqual(collect_report.facts["taskset_count"], 1)

            legacy_location = (
                exogenous_root / "benchmarks" / "terminal-bench" / "3.0" / "TASKSET.json"
            )
            shutil.copy2(taskset_path, legacy_location)
            report, _ = registry.validate_taskset(legacy_location, exogenous_root)
            self.assertFalse(report.ok)
            self.assertTrue(any("TASKSET_PATH" in error for error in report.errors))

    def test_task_constraint_v2_freezes_matched_qa_and_position_ledger(self) -> None:
        source_release = (
            REPOSITORY_ROOT
            / "exogenous"
            / "benchmarks"
            / "terminal-bench"
            / "3.0"
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "benchmarks" / "terminal-bench" / "3.0"
            shutil.copytree(source_release, release)
            taskset_path = release / "TASKSET.json"
            constraint_path = (
                release / "tasks" / "production-planning" / "TASK-CONSTRAINTS.json"
            )
            qa_instruction_path = constraint_path.parent / "QA-INSTRUCTION.md"
            qa_instruction_path.write_text(
                "Review the public task and exact Worker result. Report findings; do not edit.\n",
                encoding="utf-8",
            )

            constraint = json.loads(constraint_path.read_text(encoding="utf-8"))
            constraint["schema_version"] = registry.TASK_CONSTRAINT_V2_SCHEMA
            constraint["pair"].update(
                {
                    "comparison_unit": "matched-independent-worker-qa-task-sessions",
                    "shared": [
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
                    ],
                    "score_order": "official-evaluator-after-matched-qa-repair-before-experiment-audit",
                    "repair_policy": "matched-one-qa-repair-before-official-score",
                }
            )
            constraint["qa"] = {
                "construction": {
                    "role": "fresh-independent-construction-qa",
                    "timing": "after-builder-before-service-freeze",
                    "permission": "read-only-assessment-no-edit",
                    "feedback_visibility": "visible-to-builder-only",
                    "repair_rounds": 1,
                    "failure_policy": "preserve-freeze-and-run-not-gating",
                },
                "matched_pair": {
                    "worker_session_policy": "fresh-distinct-per-arm",
                    "qa_session_policy": "fresh-distinct-from-workers-and-other-qa",
                    "qa_instruction": {
                        "path": "QA-INSTRUCTION.md",
                        "sha256": registry.file_sha256(qa_instruction_path),
                    },
                    "timing": "after-worker-before-official-evaluator",
                    "permission": "read-only-assessment-no-edit",
                    "feedback_visibility": "visible-to-own-worker-only",
                    "budget_sha256": DIGESTS[0],
                    "repair_rounds": 1,
                    "outcomes": ["pass", "fail", "blocked", "not_assessed"],
                    "failure_policy": "preserve-repair-once-and-score-all-outcomes",
                },
            }
            constraint["position_ledger"] = {
                "schema_version": "charting-loop/position-ledger-entry/v1",
                "capture_policy": "runner-held-identical-both-arms",
                "worker_builder_visibility": "hidden",
                "qa_visibility": "reviewed-prefix-readable",
                "hash_chain": "sha256-previous-entry",
                "starts_at": "worker-dispatch",
                "ends_at": "official-score-recorded",
                "failure_policy": "preserve-and-score",
                "retention": "result-branch-content-addressed",
            }
            write_json(constraint_path, constraint)

            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
            constraint_sha = registry.file_sha256(constraint_path)
            taskset["tasks"][0]["constraint_datum"]["sha256"] = constraint_sha
            taskset["task_list_sha256"] = registry.canonical_sha256(
                [
                    {
                        "task_id": taskset["tasks"][0]["task_id"],
                        "input_sha256": taskset["tasks"][0]["input"]["sha256"],
                        "constraint_sha256": constraint_sha,
                    }
                ]
            )
            write_json(taskset_path, taskset)

            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertTrue(report.ok, report.errors)

            for qa_scope in ("construction", "matched_pair"):
                constraint["qa"][qa_scope]["repair_rounds"] = True
                write_json(constraint_path, constraint)
                report, _ = registry.validate_task_constraint(
                    constraint_path,
                    expected_task_id="production-planning",
                    expected_instruction_sha256=taskset["tasks"][0]["input"]["sha256"],
                )
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("QA" in error for error in report.errors),
                    report.errors,
                )
                constraint["qa"][qa_scope]["repair_rounds"] = 1

            constraint["qa"]["matched_pair"]["repair_rounds"] = 2
            write_json(constraint_path, constraint)
            report, _ = registry.validate_task_constraint(
                constraint_path,
                expected_task_id="production-planning",
                expected_instruction_sha256=taskset["tasks"][0]["input"]["sha256"],
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any("TASK_CONSTRAINT_MATCHED_QA" in error for error in report.errors),
                report.errors,
            )

            constraint["qa"]["matched_pair"]["repair_rounds"] = 1
            constraint["position_ledger"]["worker_builder_visibility"] = "visible"
            write_json(constraint_path, constraint)
            report, _ = registry.validate_task_constraint(
                constraint_path,
                expected_task_id="production-planning",
                expected_instruction_sha256=taskset["tasks"][0]["input"]["sha256"],
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any("TASK_CONSTRAINT_POSITION_LEDGER" in error for error in report.errors),
                report.errors,
            )

    def test_v2_task_constraint_missing_tampered_or_symlinked_fails_closed(self) -> None:
        source_release = (
            REPOSITORY_ROOT
            / "exogenous"
            / "benchmarks"
            / "terminal-bench"
            / "3.0"
        )

        def fixture(root: Path) -> tuple[Path, Path]:
            release = root / "benchmarks" / "terminal-bench" / "3.0"
            shutil.copytree(source_release, release)
            taskset_path = release / "TASKSET.json"
            constraint_path = release / "tasks" / "production-planning" / "TASK-CONSTRAINTS.json"
            return taskset_path, constraint_path

        def rebind(taskset_path: Path, constraint_path: Path) -> None:
            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
            constraint_sha = registry.file_sha256(constraint_path)
            taskset["tasks"][0]["constraint_datum"]["sha256"] = constraint_sha
            taskset["task_list_sha256"] = registry.canonical_sha256(
                [
                    {
                        "task_id": taskset["tasks"][0]["task_id"],
                        "input_sha256": taskset["tasks"][0]["input"]["sha256"],
                        "constraint_sha256": constraint_sha,
                    }
                ]
            )
            write_json(taskset_path, taskset)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taskset_path, constraint_path = fixture(root)
            constraint_path.unlink()
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(any("TASK_CONSTRAINT_FILE" in error for error in report.errors))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taskset_path, _ = fixture(root)
            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
            taskset["tasks"][0]["constraint_datum"]["sha256"] = DIGESTS[0]
            write_json(taskset_path, taskset)
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(any("TASK_CONSTRAINT_HASH" in error for error in report.errors))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taskset_path, constraint_path = fixture(root)
            constraint = json.loads(constraint_path.read_text(encoding="utf-8"))
            constraint["unexpected"] = True
            write_json(constraint_path, constraint)
            rebind(taskset_path, constraint_path)
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(any("FIELDS_UNKNOWN" in error for error in report.errors))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taskset_path, constraint_path = fixture(root)
            outside = root / "outside.json"
            shutil.copy2(constraint_path, outside)
            constraint_path.unlink()
            os.symlink(outside, constraint_path)
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(any("PATH_SYMLINK" in error for error in report.errors))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taskset_path, constraint_path = fixture(root)
            constraint = json.loads(constraint_path.read_text(encoding="utf-8"))
            constraint["source"]["instruction_sha256"] = DIGESTS[0]
            write_json(constraint_path, constraint)
            rebind(taskset_path, constraint_path)
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("TASK_CONSTRAINT_INPUT_HASH" in error for error in report.errors)
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taskset_path, constraint_path = fixture(root)
            constraint = json.loads(constraint_path.read_text(encoding="utf-8"))
            constraint["source"]["public_environment_tree_git_sha1"] = COMMITS[0]
            write_json(constraint_path, constraint)
            rebind(taskset_path, constraint_path)
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("TASK_CONSTRAINT_ENVIRONMENT_JOIN" in error for error in report.errors)
            )

    def test_v2_study_common_inputs_bind_task_and_constraint_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "benchmarks" / "terminal-bench" / "3.0"
            shutil.copytree(
                REPOSITORY_ROOT
                / "exogenous"
                / "benchmarks"
                / "terminal-bench"
                / "3.0",
                release,
            )
            study_path = root / "studies" / "cl027-tb3-production-planning" / "STUDY.json"
            study_path.parent.mkdir(parents=True)
            study = json.loads(
                (
                    REPOSITORY_ROOT
                    / "exogenous"
                    / "studies"
                    / "cl027-tb3-production-planning"
                    / "STUDY.json"
                ).read_text(encoding="utf-8")
            )
            study["conditions"][0]["common_inputs_sha256"] = DIGESTS[0]
            write_json(study_path, study)
            taskset_path = release / "TASKSET.json"
            taskset_report, taskset = registry.validate_taskset(taskset_path, root)
            self.assertTrue(taskset_report.ok, taskset_report.errors)
            method_report, methods = registry.load_method_catalog(
                REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"
            )
            self.assertTrue(method_report.ok, method_report.errors)
            report, _ = registry.validate_study(
                study_path,
                root,
                {taskset["taskset_id"]: (taskset_path, taskset)},
                method_versions=methods,
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("STUDY_COMMON_INPUTS" in error for error in report.errors))

            study["conditions"][0]["common_inputs_sha256"] = taskset["task_list_sha256"]
            constraint_path = (
                release / "tasks" / "production-planning" / "TASK-CONSTRAINTS.json"
            )
            original_constraint_bytes = constraint_path.read_bytes()
            constraint_path.write_bytes(original_constraint_bytes + b"\n")
            write_json(study_path, study)
            report, _ = registry.validate_study(
                study_path,
                root,
                {taskset["taskset_id"]: (taskset_path, taskset)},
                method_versions=methods,
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any("STUDY_TASK_CONSTRAINT_HASH" in error for error in report.errors)
            )
            constraint_path.write_bytes(original_constraint_bytes)

            study["conditions"][0]["method_paper_ref"]["content_sha256"] = DIGESTS[0]
            write_json(study_path, study)
            report, _ = registry.validate_study(
                study_path,
                root,
                {taskset["taskset_id"]: (taskset_path, taskset)},
                method_versions=methods,
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any("STUDY_TASK_CONSTRAINT_METHOD_JOIN" in error for error in report.errors)
            )

    def test_manifest_projects_current_validator_and_method_contract(self) -> None:
        manifest = (
            REPOSITORY_ROOT / "protocol" / "MANIFEST-SCHEMA.md"
        ).read_text(encoding="utf-8")

        for schema in (
            registry.LEGACY_RUN_SCHEMA,
            registry.RUN_SCHEMA,
            registry.LEGACY_STUDY_SCHEMA,
            registry.STUDY_SCHEMA,
            registry.STUDY_V3_SCHEMA,
            registry.TASKSET_V3_SCHEMA,
            registry.TASK_CONSTRAINT_SCHEMA,
            registry.TASK_CONSTRAINT_V2_SCHEMA,
            registry.LEGACY_METHOD_INDEX_SCHEMA,
            registry.METHOD_INDEX_SCHEMA,
        ):
            with self.subTest(schema=schema):
                self.assertIn(f"`{schema}`", manifest)

        def projected_keys(name: str) -> set[str]:
            prefix = f"- `{name}`: "
            declarations = [
                line for line in manifest.splitlines() if line.startswith(prefix)
            ]
            self.assertEqual(len(declarations), 1, name)
            tokens = declarations[0][len(prefix) :].split(", ")
            self.assertTrue(
                all(token.startswith("`") and token.endswith("`") for token in tokens),
                declarations[0],
            )
            return {token[1:-1] for token in tokens}

        for name, expected in (
            ("WORLD_REF_KEYS", registry.WORLD_REF_KEYS),
            ("PREFIX_KEYS", registry.PREFIX_KEYS),
            ("ADMISSION_KEYS", registry.ADMISSION_KEYS),
            ("PROJECTOR_KEYS", registry.PROJECTOR_KEYS),
        ):
            with self.subTest(field_set=name):
                self.assertEqual(projected_keys(name), expected)

        method_index = json.loads(
            (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(method_index["normative_source"], "method-paper/METHOD.md")
        current = method_index["versions"][0]
        for projection in (
            current["version_id"],
            current["source_commit"],
            current["content_sha256"],
            current["scope_datum_sha256"],
            f"status={current['status']}",
            f"study_eligible={str(current['study_eligible']).lower()}",
            f"adoption_eligible={str(current['adoption_eligible']).lower()}",
            f"builder_eligible={str(current['builder_eligible']).lower()}",
        ):
            with self.subTest(method_projection=projection):
                self.assertIn(f"`{projection}`", manifest)

    def test_checked_in_template_and_empty_indexes(self) -> None:
        report, _ = registry.validate_run(
            REPOSITORY_ROOT / "templates" / "run", allow_template=True
        )
        self.assertTrue(report.ok, report.errors)
        method_report, methods = registry.load_method_catalog(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"
        )
        self.assertTrue(method_report.ok, method_report.errors)
        collect_report, summaries = registry.collect_registry(
            REPOSITORY_ROOT / "exogenous", method_versions=methods
        )
        self.assertTrue(collect_report.ok, collect_report.errors)
        execution_amendments = registry.collect_public_execution_amendments(
            REPOSITORY_ROOT
        )
        self.assertEqual(len(execution_amendments), 6)
        json_text, markdown_text = registry.build_index_documents(
            summaries,
            public_execution_amendments=execution_amendments,
        )
        self.assertEqual(
            json_text,
            (REPOSITORY_ROOT / "exogenous" / "registry" / "INDEX.json").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            markdown_text,
            (
                REPOSITORY_ROOT / "exogenous" / "registry" / "EXPERIMENTS.md"
            ).read_text(encoding="utf-8"),
        )
        release_report = public_release.validate_registry(
            REPOSITORY_ROOT
            / "exogenous"
            / "registry"
            / "PUBLIC-RELEASES.json",
            repo=REPOSITORY_ROOT,
            base_ref="4e97d0ae66dc7cf7211eb57c4d7badebb13ce095",
            history_base_ref="0029d1f2412ee41c040b9a2364c2e78e69c0e81d",
        )
        self.assertTrue(release_report.ok, release_report.errors)
        self.assertEqual(release_report.facts["release_count"], 14)
        for marker in (
            "## Public executed-topology amendments",
            "they do not rewrite the frozen STUDY or RUN registry",
            "cl030-treatment-public-v2",
            "openai/gpt-5.6-sol / low",
            "cl031-treatment-public-v2",
            "openai/gpt-5.6-sol / high",
            "### Invalid predecessor disposition",
            "attempt-001",
            "launcher_repair_was_not_conditioned_on_qa_fail",
            "attempt-003",
            "control_independent_qa_timeout_before_matched_pipeline_completion",
            "waived-no-posthoc-backfill",
        ):
            self.assertIn(marker, markdown_text)
        release_protocol = (
            REPOSITORY_ROOT / "protocol" / "PUBLIC-RELEASE-BRANCHES.md"
        ).read_text(encoding="utf-8")
        invitation = (
            REPOSITORY_ROOT / "docs" / "REPLICATION-INVITATION.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Method-transfer replication", release_protocol)
        invitation_words = " ".join(invitation.split())
        self.assertIn("authorized public release is live", invitation_words)
        self.assertIn("six sanitized arm summaries", invitation_words)
        method_report, versions = registry.load_method_catalog(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"
        )
        self.assertTrue(method_report.ok, method_report.errors)
        self.assertEqual(
            [version["version_id"] for version in versions],
            [
                "paper2-current-v2",
                "draft-v2",
                "charting-loop-method-v4",
                "charting-loop-method-v5",
                "charting-loop-method-v6",
                "charting-loop-method-v7",
                "charting-loop-method-v8",
            ],
        )
        current = next(
            version for version in versions if version["version_id"] == "paper2-current-v2"
        )
        v4 = next(
            version for version in versions if version["version_id"] == "charting-loop-method-v4"
        )
        v5 = next(
            version for version in versions if version["version_id"] == "charting-loop-method-v5"
        )
        v6 = next(
            version for version in versions if version["version_id"] == "charting-loop-method-v6"
        )
        v7 = next(
            version for version in versions if version["version_id"] == "charting-loop-method-v7"
        )
        v8 = next(
            version for version in versions if version["version_id"] == "charting-loop-method-v8"
        )
        historical = next(
            version for version in versions if version["version_id"] == "draft-v2"
        )
        self.assertEqual(
            current["source_commit"],
            "f58e065ad5d035b55fc8668b094e42327382345a",
        )
        self.assertEqual(
            current["content_sha256"],
            "sha256:ce9c94c12660c57a8dc34c98afd46c644b07214a2f9e7a9a494078fbe7be0905",
        )
        self.assertEqual(
            current["scope_datum_sha256"],
            "sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307",
        )
        self.assertFalse(historical["study_eligible"])
        self.assertEqual(
            historical["scope_datum_sha256"],
            "sha256:973d0993193ec2598cacfeb3e708161f8fddade02448ea1ad5bc105a293cf91c",
        )
        self.assertEqual(
            method_report.facts["schema_version"], registry.METHOD_INDEX_SCHEMA
        )
        self.assertEqual(
            v4["source_commit"],
            "0d3ed5c357c906edcc697a83b3ce681c68cd353a",
        )
        self.assertEqual(
            v4["content_sha256"],
            "sha256:d3a9da497c31f3bde46a31f37990236af51b9f677ae807d023582b27254c4ab0",
        )
        self.assertEqual(
            v4["scope_datum_sha256"],
            "sha256:65c6a91120c15bec30278288a26ecc98bdf96cfb07fd490dc915408a78844327",
        )
        self.assertTrue(v4["study_eligible"])
        self.assertFalse(v4["adoption_eligible"])
        self.assertTrue(v5["study_eligible"])
        self.assertFalse(v5["adoption_eligible"])
        self.assertEqual(
            v5["source_commit"],
            "8b0fd5e1c6102c6b4c44cf03612b93c450ddb6fd",
        )
        self.assertTrue(v6["study_eligible"])
        self.assertFalse(v6["adoption_eligible"])
        self.assertEqual(
            v6["source_commit"],
            "3bf463f013e68f157028f85e0e80c7608091a851",
        )
        self.assertTrue(v7["study_eligible"])
        self.assertFalse(v7["adoption_eligible"])
        self.assertEqual(
            v7["source_commit"],
            "c68813cea1aa1d1eeaafde69a3f35f71ffab6d0d",
        )
        self.assertTrue(v8["study_eligible"])
        self.assertFalse(v8["adoption_eligible"])
        self.assertEqual(
            v8["source_commit"],
            "3c3813444a7d43d0a56837e9cb960be86ce26d06",
        )
        self.assertEqual(method_report.facts["study_eligible_method_version_count"], 6)
        self.assertEqual(method_report.facts["adoption_eligible_method_version_count"], 0)
        self.assertEqual(method_report.facts["eligible_method_version_count"], 0)

    def test_method_loader_rejects_historical_ambient_scope_digest(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            root = Path(temporary)
            copy_method_project(root)
            index_path = root / "method-paper" / "VERSIONS.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            historical = next(
                version
                for version in index["versions"]
                if version["version_id"] == "draft-v2"
            )
            historical["scope_datum_sha256"] = (
                "sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307"
            )
            write_json(index_path, index)

            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_SCOPE_SOURCE_HASH" in error for error in report.errors),
                report.errors,
            )

    def test_method_loader_rejects_unpinned_v2_history_with_ambient_digests(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            root = Path(temporary)
            copy_method_project(root)
            index_path = root / "method-paper" / "VERSIONS.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            historical = next(
                version
                for version in index["versions"]
                if version["version_id"] == "draft-v2"
            )
            historical["source_commit"] = None
            historical["content_sha256"] = (
                "sha256:ce9c94c12660c57a8dc34c98afd46c644b07214a2f9e7a9a494078fbe7be0905"
            )
            historical["scope_datum_sha256"] = (
                "sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307"
            )
            write_json(index_path, index)

            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_SOURCE_COMMIT" in error for error in report.errors),
                report.errors,
            )

    def test_method_loader_supports_multiple_study_versions_but_requires_one(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            root = Path(temporary)
            copy_method_project(root)
            index_path = root / "method-paper" / "VERSIONS.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for version in index["versions"]:
                version["study_eligible"] = False
            write_json(index_path, index)

            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_STUDY_VERSION_COUNT" in error for error in report.errors),
                report.errors,
            )

        report, versions = registry.load_method_catalog(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json"
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(
            [
                version["version_id"]
                for version in versions
                if version["study_eligible"] is True
            ],
            [
                "paper2-current-v2",
                "charting-loop-method-v4",
                "charting-loop-method-v5",
                "charting-loop-method-v6",
                "charting-loop-method-v7",
                "charting-loop-method-v8",
            ],
        )

    def test_method_loader_rejects_any_invalid_study_eligible_version(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            root = Path(temporary)
            copy_method_project(root)
            index_path = root / "method-paper" / "VERSIONS.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            draft = next(
                version
                for version in index["versions"]
                if version["version_id"] == "draft-v2"
            )
            draft["study_eligible"] = True
            write_json(index_path, index)

            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_STUDY_VERSION_INVALID" in error for error in report.errors),
                report.errors,
            )

    def test_valid_unscored_run_remains_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            report, summaries = registry.collect_registry(root)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0]["score_status"], "unscored")
            self.assertEqual(summaries[0]["outcome_status"], "not-assessed")
            self.assertEqual(
                set(summaries[0]),
                {
                    "study_id",
                    "run_id",
                    "run_status",
                    "condition_id",
                    "trial",
                    "seed",
                    "system_condition",
                    "model",
                    "runtime",
                    "subject_identity_sha256",
                    "world_ref_sha256",
                    "score_status",
                    "outcome_status",
                    "infrastructure_status",
                    "raw_outcome_sha256",
                    "optional_evidence_status",
                    "provenance_status",
                    "direct_comparison_eligible",
                },
            )
            index_json, _ = registry.build_index_documents(summaries)
            self.assertEqual(
                json.loads(index_json)["schema_version"], registry.INDEX_SCHEMA
            )
            run_path = root / "runs" / "run-001" / "RUN.json"
            run_report, _ = registry.validate_run(run_path.parent)
            self.assertTrue(run_report.ok, run_report.errors)
            self.assertTrue(run_report.facts["measurement_plan_complete"])
            self.assertEqual(
                run_report.facts["run_sha256"], registry.file_sha256(run_path)
            )
            self.assertEqual(
                run_report.facts["measurement_plan_sha256"],
                registry.canonical_sha256(
                    json.loads(
                        run_path.read_text(encoding="utf-8")
                    )["measurement_plan"]
                ),
            )
            self.assertFalse(summaries[0]["direct_comparison_eligible"])

    def test_legacy_v1_study_and_run_remain_readable_but_not_formal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root, scored=True)
            downgrade_fixture_to_v1(root)

            report, summaries = registry.collect_registry(root)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(summaries), 1)
            summary = summaries[0]
            run_path = root / "runs" / "run-001" / "RUN.json"
            run_report, _ = registry.validate_run(run_path.parent)
            self.assertTrue(run_report.ok, run_report.errors)
            self.assertEqual(
                run_report.facts["schema_version"], registry.LEGACY_RUN_SCHEMA
            )
            self.assertFalse(run_report.facts["measurement_plan_complete"])
            self.assertIsNone(run_report.facts["measurement_plan_sha256"])
            self.assertEqual(
                run_report.facts["run_sha256"], registry.file_sha256(run_path)
            )
            taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            taskset_report, taskset = registry.validate_taskset(taskset_path, root)
            self.assertTrue(taskset_report.ok, taskset_report.errors)
            study_report, _ = registry.validate_study(
                root / "studies" / "study-001" / "STUDY.json",
                root,
                {"bench-v1": (taskset_path, taskset)},
            )
            self.assertTrue(study_report.ok, study_report.errors)
            self.assertEqual(
                study_report.facts["schema_version"], registry.LEGACY_STUDY_SCHEMA
            )
            self.assertEqual(study_report.facts["study_eligible_method_refs"], [])
            self.assertFalse(study_report.facts["formal_method_study_eligible"])
            self.assertFalse(summary["direct_comparison_eligible"])

    def test_v2_measurement_plan_is_exact_and_fail_closed(self) -> None:
        mutations = {
            "null": lambda run: run.__setitem__("measurement_plan", None),
            "missing": lambda run: run["measurement_plan"].pop(
                "package_cost_schema"
            ),
            "extra": lambda run: run["measurement_plan"].__setitem__(
                "extra", True
            ),
            "usage-schema": lambda run: run["measurement_plan"].__setitem__(
                "usage_receipt_schema", "charting-loop/usage-receipt/v0"
            ),
            "package-schema": lambda run: run["measurement_plan"].__setitem__(
                "package_cost_schema", "charting-loop/package-cost/v0"
            ),
            "stage-order": lambda run: run["measurement_plan"].__setitem__(
                "required_usage_stages",
                list(reversed(registry.REQUIRED_USAGE_STAGES)),
            ),
            "profile": lambda run: run["measurement_plan"].__setitem__(
                "raw_evidence_profile", "partial"
            ),
            "replay-bool-int": lambda run: run["measurement_plan"].__setitem__(
                "independent_replay_required", 1
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                make_fixture(root)
                run_path = root / "runs" / "run-001" / "RUN.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                mutate(run)
                write_json(run_path, run)
                report, _ = registry.validate_run(run_path.parent)
                self.assertFalse(report.ok, report.errors)
                self.assertFalse(report.facts["measurement_plan_complete"])

    def test_non_string_schema_versions_fail_closed(self) -> None:
        for bad_schema in ([], {}):
            with self.subTest(kind="run", value=bad_schema), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                make_fixture(root)
                run_path = root / "runs" / "run-001" / "RUN.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                run["schema_version"] = bad_schema
                write_json(run_path, run)
                report, _ = registry.validate_run(run_path.parent)
                self.assertFalse(report.ok)
                self.assertTrue(any("SCHEMA " in error for error in report.errors))

            with self.subTest(kind="study", value=bad_schema), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                make_fixture(root)
                taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
                _, taskset = registry.validate_taskset(taskset_path, root)
                study_path = root / "studies" / "study-001" / "STUDY.json"
                study = json.loads(study_path.read_text(encoding="utf-8"))
                study["schema_version"] = bad_schema
                write_json(study_path, study)
                report, _ = registry.validate_study(
                    study_path,
                    root,
                    {"bench-v1": (taskset_path, taskset)},
                )
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("STUDY_SCHEMA" in error for error in report.errors)
                )

            with self.subTest(kind="method", value=bad_schema), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_method_project(root)
                method_path = root / "method-paper" / "VERSIONS.json"
                method = json.loads(method_path.read_text(encoding="utf-8"))
                method["schema_version"] = bad_schema
                write_json(method_path, method)
                report, _ = registry.load_method_catalog(method_path)
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("METHOD_SCHEMA" in error for error in report.errors)
                )

    def test_valid_score_binds_exact_run_task_world_and_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root, scored=True)
            report, summaries = registry.collect_registry(root)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(summaries[0]["outcome_status"], "passed")
            self.assertEqual(summaries[0]["infrastructure_status"], "ok")
            self.assertTrue(summaries[0]["raw_outcome_sha256"].startswith("sha256:"))

    def test_score_binding_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root, scored=True)
            score_path = root / "runs" / "run-001" / "SCORE.json"
            score = json.loads(score_path.read_text(encoding="utf-8"))
            score["seed"] = "different"
            write_json(score_path, score)
            report, _ = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertTrue(any("SCORE_SEED" in error for error in report.errors))

    def test_optional_attachments_and_local_files_are_never_read_or_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            secret = "private-marker-do-not-index"
            attachment = root / "runs" / "run-001" / "attachments" / "raw.bin"
            attachment.parent.mkdir()
            attachment.write_bytes(b"\xff\x00" + secret.encode())
            local = root / "local" / "invalid.json"
            local.parent.mkdir()
            local.write_text("{not-json " + secret, encoding="utf-8")
            report, summaries = registry.collect_registry(root)
            self.assertTrue(report.ok, report.errors)
            json_text, markdown_text = registry.build_index_documents(summaries)
            self.assertNotIn(secret, json_text + markdown_text)
            self.assertNotIn("raw.bin", json_text + markdown_text)

    def test_branch_hint_does_not_change_subject_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_root = root / "runs" / "run-001"
            first, _ = registry.validate_run(run_root)
            run_path = run_root / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["subject"]["branch_hint"] = "renamed/location"
            write_json(run_path, run)
            second, _ = registry.validate_run(run_root)
            self.assertTrue(first.ok and second.ok)
            self.assertEqual(
                first.facts["subject_identity_sha256"],
                second.facts["subject_identity_sha256"],
            )

    def test_bool_trial_and_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["trial"] = True
            write_json(run_path, run)
            report, _ = registry.validate_run(run_path.parent)
            self.assertFalse(report.ok)
            self.assertTrue(any("TRIAL" in error for error in report.errors))
            run_path.write_text('{"schema_version":"x","schema_version":"y"}\n')
            report, _ = registry.validate_run(run_path.parent)
            self.assertFalse(report.ok)
            self.assertTrue(any("JSON_PARSE" in error for error in report.errors))

    def test_deep_json_and_surrogate_never_escape_as_internal_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            nested = "[" * (registry.MAX_JSON_DEPTH + 2) + '"\\ud800"' + "]" * (
                registry.MAX_JSON_DEPTH + 2
            )
            (run_root / "RUN.json").write_text(
                '{"value":' + nested + "}\n",
                encoding="utf-8",
            )
            report, _ = registry.validate_run(run_root)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    code in error
                    for code in ("JSON_DEPTH", "JSON_PARSE", "JSON_SURROGATE")
                    for error in report.errors
                ),
                report.errors,
            )
            completed = subprocess.run(
                [
                    "python3",
                    str(REPOSITORY_ROOT / "tools" / "exogenous_registry.py"),
                    "validate-run",
                    str(run_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertNotIn("internal error", completed.stderr)

    def test_urls_fail_closed_without_parser_exceptions(self) -> None:
        invalid_urls = (
            "https://[",
            "https://:443/x",
            "https://example.invalid:bad/x",
            "https://example.invalid:0/x",
            "https://example.invalid:99999/x",
            " https://example.invalid/x",
            "https://exa mple.invalid/x",
            "https://-bad.example/x",
            "https://example.invalid./x",
            "https://user@example.invalid/x",
            "https://example.invalid/x?query=1",
        )
        for value in invalid_urls:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    make_fixture(root)
                    run_path = root / "runs" / "run-001" / "RUN.json"
                    run = json.loads(run_path.read_text(encoding="utf-8"))
                    run["subject"]["repository_url"] = value
                    write_json(run_path, run)
                    report, _ = registry.validate_run(run_path.parent)
                    self.assertFalse(report.ok)
                    self.assertTrue(any("URL" in error for error in report.errors))

    def test_vendored_input_rejects_ancestor_symlink_and_oversize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
            outside = root / "outside"
            outside.mkdir()
            outside_file = outside / "task.json"
            outside_file.write_text('{"task":"outside"}\n', encoding="utf-8")
            link = taskset_path.parent / "tasks" / "link"
            os.symlink(outside, link)
            taskset["tasks"][0]["input"] = {
                "kind": "vendored",
                "locator": "tasks/link/task.json",
                "sha256": registry.file_sha256(outside_file),
            }
            taskset["task_list_sha256"] = registry.canonical_sha256(
                [
                    {
                        "task_id": "task-001",
                        "input_sha256": taskset["tasks"][0]["input"]["sha256"],
                    }
                ]
            )
            write_json(taskset_path, taskset)
            report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(any("PATH_SYMLINK" in error for error in report.errors))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            with mock.patch.object(registry, "MAX_HASH_BYTES", 8):
                report, _ = registry.validate_taskset(taskset_path, root)
            self.assertFalse(report.ok)
            self.assertTrue(any("FILE_HASH_READ" in error for error in report.errors))

    def test_sparse_file_exceeding_hash_limit_is_rejected_without_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sparse.bin"
            with path.open("wb") as handle:
                handle.seek(registry.MAX_HASH_BYTES)
                handle.write(b"x")
            report = registry.Report(subject=str(path))
            self.assertIsNone(registry.file_sha256(path, report, "sparse.bin"))
            self.assertTrue(any("FILE_HASH_READ" in error for error in report.errors))

    def test_knowledge_condition_is_a_closed_enum(self) -> None:
        for invalid in ("ambient-corpus", [], {}):
            with self.subTest(invalid=invalid):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    make_fixture(root)
                    taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
                    taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
                    study_path = root / "studies" / "study-001" / "STUDY.json"
                    study = json.loads(study_path.read_text(encoding="utf-8"))
                    study["conditions"][0]["knowledge_condition"] = invalid
                    write_json(study_path, study)
                    report, _ = registry.validate_study(
                        study_path,
                        root,
                        {"bench-v1": (taskset_path, taskset)},
                    )
                    self.assertFalse(report.ok)
                    self.assertTrue(
                        any("KNOWLEDGE_CONDITION" in error for error in report.errors)
                    )

    def test_enum_containers_are_structurally_invalid_not_internal_errors(self) -> None:
        mutations = (
            ("task-kind", ("benchmarks", "bench", "v1", "TASKSET.json"), ("tasks", 0, "input", "kind"), "TASK_INPUT_KIND"),
            ("redistribution", ("benchmarks", "bench", "v1", "TASKSET.json"), ("license", "redistribution"), "REDISTRIBUTION"),
            ("study-system", ("studies", "study-001", "STUDY.json"), ("conditions", 0, "system_condition"), "CONDITION_SYSTEM"),
            ("run-template", ("runs", "run-001", "RUN.json"), ("template",), "TEMPLATE_TYPE"),
            ("run-status", ("runs", "run-001", "RUN.json"), ("status",), "RUN_STATUS"),
            ("network", ("runs", "run-001", "RUN.json"), ("runtime", "network_access"), "NETWORK_ACCESS"),
            ("run-system", ("runs", "run-001", "RUN.json"), ("subject", "system_condition"), "SYSTEM_CONDITION"),
            ("score-outcome", ("runs", "run-001", "SCORE.json"), ("outcome_status",), "SCORE_OUTCOME"),
            ("score-infrastructure", ("runs", "run-001", "SCORE.json"), ("infrastructure_status",), "SCORE_INFRASTRUCTURE"),
        )
        for name, path_parts, key_path, code in mutations:
            for invalid in ([], {}):
                with self.subTest(name=name, invalid=invalid):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        make_fixture(
                            root,
                            scored=name.startswith("score-"),
                        )
                        path = root.joinpath(*path_parts)
                        document = json.loads(path.read_text(encoding="utf-8"))
                        target = document
                        for key in key_path[:-1]:
                            target = target[key]
                        target[key_path[-1]] = invalid
                        write_json(path, document)
                        if name.startswith("task-") or name == "redistribution":
                            report, _ = registry.validate_taskset(path, root)
                        elif name.startswith("study-"):
                            taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
                            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
                            report, _ = registry.validate_study(
                                path,
                                root,
                                {"bench-v1": (taskset_path, taskset)},
                            )
                        elif name.startswith("score-"):
                            report, _ = registry.collect_registry(root)
                        else:
                            report, _ = registry.validate_run(path.parent)
                        self.assertFalse(report.ok)
                        self.assertTrue(
                            any(code in error for error in report.errors),
                            report.errors,
                        )

    def test_unhashable_run_id_is_structurally_invalid(self) -> None:
        for invalid in ([], {}):
            with self.subTest(invalid=invalid):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    make_fixture(root)
                    run_path = root / "runs" / "run-001" / "RUN.json"
                    run = json.loads(run_path.read_text(encoding="utf-8"))
                    run["run_id"] = invalid
                    write_json(run_path, run)
                    report, _ = registry.collect_registry(root)
                    self.assertFalse(report.ok)
                    self.assertTrue(any("STRING" in error for error in report.errors))

    def test_task_list_digest_and_generated_order_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root, run_id="run-b")
            source = root / "runs" / "run-b" / "RUN.json"
            second = json.loads(source.read_text(encoding="utf-8"))
            second["run_id"] = "run-a"
            second["world_ref"]["run_id"] = "run-a"
            second["subject"]["artifact_root"] = "runs/run-a/output"
            write_json(root / "runs" / "run-a" / "RUN.json", second)
            report, summaries = registry.collect_registry(root)
            self.assertTrue(report.ok, report.errors)
            first_json, first_markdown = registry.build_index_documents(summaries)
            second_json, second_markdown = registry.build_index_documents(
                list(reversed(summaries))
            )
            self.assertEqual(first_json, second_json)
            self.assertEqual(first_markdown, second_markdown)
            taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            taskset = json.loads(taskset_path.read_text(encoding="utf-8"))
            taskset["task_list_sha256"] = DIGESTS[13]
            write_json(taskset_path, taskset)
            report, _ = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertTrue(any("TASK_LIST_HASH" in error for error in report.errors))

    def test_run_rejects_condition_executor_and_world_base_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["runtime"]["executor_type"] = "human"
            run["subject"]["system_condition"] = "external-system"
            run["subject"]["base_commit"] = COMMITS[3]
            write_json(run_path, run)
            report, summaries = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertEqual(summaries, [])
            self.assertTrue(any("EXECUTOR_TYPE" in error for error in report.errors))
            self.assertTrue(any("RUN_WORLD_BASE" in error for error in report.errors))

    def test_invalid_nested_run_records_never_reach_projection(self) -> None:
        for field in ("runtime", "study_ref", "subject", "world_ref"):
            for invalid in ([], {}):
                with self.subTest(field=field, invalid=invalid):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        make_fixture(root)
                        run_path = root / "runs" / "run-001" / "RUN.json"
                        run = json.loads(run_path.read_text(encoding="utf-8"))
                        run[field] = invalid
                        write_json(run_path, run)
                        report, summaries = registry.collect_registry(root)
                        self.assertFalse(report.ok)
                        self.assertEqual(summaries, [])

    def test_declared_invalid_status_is_data_and_remains_projectable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = "invalid"
            write_json(run_path, run)
            report, summaries = registry.collect_registry(root)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual([item["run_status"] for item in summaries], ["invalid"])

    def test_structurally_valid_run_condition_mismatch_is_not_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["subject"]["system_condition"] = "external-system"
            write_json(run_path, run)
            report, summaries = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertEqual(summaries, [])
            self.assertTrue(
                any("RUN_CONDITION_SYSTEM" in error for error in report.errors)
            )

    def test_run_environment_must_equal_the_taskset_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["world_ref"]["environment_sha256"] = DIGESTS[2]
            write_json(run_path, run)
            report, summaries = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertEqual(summaries, [])
            self.assertTrue(any("RUN_ENVIRONMENT" in error for error in report.errors))

    def test_broken_score_symlink_is_invalid_not_unscored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            score_path = root / "runs" / "run-001" / "SCORE.json"
            os.symlink(root / "missing-score.json", score_path)
            report, summaries = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertEqual(summaries, [])
            self.assertTrue(any("JSON_FILE" in error for error in report.errors))

    def test_study_ancestor_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            study_directory = root / "studies" / "study-001"
            outside = root / "outside-study"
            shutil.move(study_directory, outside)
            os.symlink(outside, study_directory)
            report, summaries = registry.collect_registry(root)
            self.assertFalse(report.ok)
            self.assertEqual(summaries, [])
            self.assertTrue(any("PATH_SYMLINK" in error for error in report.errors))

    def test_world_prefix_requires_digest_and_projector_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["world_ref"]["evidence_prefix"] = {
                "stream_id": "timeline",
                "through_sequence": 1,
                "prefix_sha256": DIGESTS[0],
            }
            write_json(run_path, run)
            report, _ = registry.validate_run(run_path.parent)
            self.assertFalse(report.ok)
            self.assertTrue(any("FIELDS_MISSING" in error for error in report.errors))

    def test_method_condition_requires_exact_eligible_local_catalog_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_fixture(root)
            study_path = root / "studies" / "study-001" / "STUDY.json"
            study = json.loads(study_path.read_text(encoding="utf-8"))
            condition = study["conditions"][0]
            condition["knowledge_condition"] = "method-paper"
            condition["method_paper_ref"] = {
                "version_id": "paper2-current-v2",
                "source_commit": COMMITS[0],
                "representation_path": "method-paper/METHOD.md",
                "content_sha256": DIGESTS[0],
                "study_eligible": True,
                "adoption_eligible": False,
                "builder_eligible": False,
            }
            write_json(study_path, study)
            run_path = root / "runs" / "run-001" / "RUN.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["study_ref"]["sha256"] = registry.file_sha256(study_path)
            write_json(run_path, run)

            report, _ = registry.collect_registry(
                root,
                method_versions=[
                    {
                        "version_id": "paper2-current-v2",
                        "source_commit": COMMITS[0],
                        "path": "method-paper/METHOD.md",
                        "content_sha256": DIGESTS[0],
                        "study_eligible": False,
                        "adoption_eligible": False,
                        "builder_eligible": False,
                    }
                ],
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("METHOD_CATALOG_REF" in error for error in report.errors))

            report, _ = registry.collect_registry(
                root,
                method_versions=[
                    {
                        "version_id": "paper2-current-v2",
                        "source_commit": COMMITS[1],
                        "path": "method-paper/METHOD.md",
                        "content_sha256": DIGESTS[0],
                        "study_eligible": True,
                        "adoption_eligible": False,
                        "builder_eligible": False,
                    }
                ],
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("METHOD_CATALOG_REF" in error for error in report.errors))

            valid_method = {
                "version_id": "paper2-current-v2",
                "source_commit": COMMITS[0],
                "path": "method-paper/METHOD.md",
                "content_sha256": DIGESTS[0],
                "study_eligible": True,
                "adoption_eligible": False,
                "builder_eligible": False,
            }
            historical_method = {
                "version_id": "draft-v2",
                "source_commit": COMMITS[1],
                "path": "method-paper/METHOD.md",
                "content_sha256": DIGESTS[1],
                "study_eligible": False,
                "adoption_eligible": False,
                "builder_eligible": False,
            }
            report, summaries = registry.collect_registry(
                root, method_versions=[valid_method, historical_method]
            )
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(summaries), 1)
            taskset_path = root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            taskset_report, taskset = registry.validate_taskset(taskset_path, root)
            self.assertTrue(taskset_report.ok, taskset_report.errors)
            study_report, _ = registry.validate_study(
                study_path,
                root,
                {"bench-v1": (taskset_path, taskset)},
                method_versions=[valid_method, historical_method],
            )
            self.assertTrue(study_report.ok, study_report.errors)
            self.assertTrue(study_report.facts["formal_method_study_eligible"])
            method_fact = study_report.facts["study_eligible_method_refs"][0]
            self.assertTrue(method_fact["study_eligible"])
            self.assertFalse(method_fact["adoption_eligible"])
            self.assertFalse(method_fact["builder_eligible"])
            self.assertEqual(method_fact["version_id"], "paper2-current-v2")
            self.assertEqual(method_fact["source_commit"], COMMITS[0])
            self.assertEqual(
                method_fact["representation_path"], "method-paper/METHOD.md"
            )
            self.assertEqual(method_fact["content_sha256"], DIGESTS[0])
            self.assertFalse(summaries[0]["direct_comparison_eligible"])

    def test_score_never_changes_pinned_method_eligibility(self) -> None:
        projected: list[tuple[bool, bool, bool]] = []
        for scored in (False, True):
            with self.subTest(scored=scored), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                make_fixture(root, scored=scored)
                study_path = root / "studies" / "study-001" / "STUDY.json"
                study = json.loads(study_path.read_text(encoding="utf-8"))
                condition = study["conditions"][0]
                condition["knowledge_condition"] = "method-paper"
                condition["method_paper_ref"] = {
                    "version_id": "draft-v2",
                    "source_commit": COMMITS[0],
                    "representation_path": "method-paper/METHOD.md",
                    "content_sha256": DIGESTS[0],
                    "study_eligible": True,
                    "adoption_eligible": False,
                    "builder_eligible": False,
                }
                write_json(study_path, study)
                run_path = root / "runs" / "run-001" / "RUN.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                run["study_ref"]["sha256"] = registry.file_sha256(study_path)
                write_json(run_path, run)
                score_path = run_path.parent / "SCORE.json"
                if score_path.exists():
                    score = json.loads(score_path.read_text(encoding="utf-8"))
                    score["run_ref"]["sha256"] = registry.file_sha256(run_path)
                    write_json(score_path, score)
                method = {
                    "version_id": "draft-v2",
                    "source_commit": COMMITS[0],
                    "path": "method-paper/METHOD.md",
                    "content_sha256": DIGESTS[0],
                    "study_eligible": True,
                    "adoption_eligible": False,
                    "builder_eligible": False,
                }
                report, summaries = registry.collect_registry(
                    root, method_versions=[method]
                )
                self.assertTrue(report.ok, report.errors)
                taskset_path = (
                    root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
                )
                taskset_report, taskset = registry.validate_taskset(taskset_path, root)
                self.assertTrue(taskset_report.ok, taskset_report.errors)
                study_report, _ = registry.validate_study(
                    study_path,
                    root,
                    {"bench-v1": (taskset_path, taskset)},
                    method_versions=[method],
                )
                self.assertTrue(study_report.ok, study_report.errors)
                method_fact = study_report.facts["study_eligible_method_refs"][0]
                projected.append(
                    (
                        method_fact["study_eligible"],
                        method_fact["adoption_eligible"],
                        method_fact["builder_eligible"],
                    )
                )
        self.assertEqual(projected, [(True, False, False), (True, False, False)])

    def test_eligible_method_catalog_requires_a_frozen_source_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            method_root = root / "method-paper"
            method_root.mkdir()
            method_path = method_root / "METHOD.md"
            method_path.write_text("frozen method\n", encoding="utf-8")
            catalog = json.loads(
                (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                    encoding="utf-8"
                )
            )
            version = catalog["versions"][0]
            version["adoption_eligible"] = True
            version["builder_eligible"] = True
            version["path"] = "method-paper/METHOD.md"
            version["content_sha256"] = registry.file_sha256(method_path)
            version["source_commit"] = None
            write_json(method_root / "VERSIONS.json", catalog)
            report, _ = registry.load_method_catalog(method_root / "VERSIONS.json")
            self.assertFalse(report.ok)
            self.assertTrue(
                any("METHOD_SOURCE_COMMIT" in error for error in report.errors)
            )

    def test_method_catalog_and_declared_members_reject_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_method_project(root)
            linked_index = root / "method-paper" / "LINKED-VERSIONS.json"
            os.symlink("VERSIONS.json", linked_index)
            report, versions = registry.load_method_catalog(linked_index)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(any("JSON_FILE" in error for error in report.errors))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_method_project(root)
            outside = root / "outside-scope"
            outside.mkdir()
            shutil.copy2(root / "method-paper" / "SCOPE-DATUM.md", outside / "SCOPE-DATUM.md")
            os.symlink(outside, root / "scope-link")
            index_path = root / "method-paper" / "VERSIONS.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["versions"][0]["scope_datum_path"] = "scope-link/SCOPE-DATUM.md"
            write_json(index_path, index)
            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(any("PATH_SYMLINK" in error for error in report.errors))

    def test_method_provenance_catalogs_are_nonempty_and_fully_joined(self) -> None:
        mutations = (
            ("catalog/CLAIMS.json", "claims", []),
            ("catalog/SOURCES.json", "sources", []),
            ("catalog/EVIDENCE-INDEX.json", "bindings", []),
        )
        for relative, field, invalid in mutations:
            with self.subTest(relative=relative, field=field):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    copy_method_project(root)
                    path = root / relative
                    document = json.loads(path.read_text(encoding="utf-8"))
                    document[field] = invalid
                    write_json(path, document)
                    report, versions = registry.load_method_catalog(
                        root / "method-paper" / "VERSIONS.json"
                    )
                    self.assertFalse(report.ok)
                    self.assertEqual(versions, [])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_method_project(root)
            path = root / "catalog" / "EVIDENCE-INDEX.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["bindings"][0]["source_ids"] = ["missing-source"]
            write_json(path, document)
            report, versions = registry.load_method_catalog(
                root / "method-paper" / "VERSIONS.json"
            )
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(any("METHOD_BINDING_SOURCE" in error for error in report.errors))

    def test_method_loader_enforces_public_primary_theory_boundary(self) -> None:
        cases = ("missing-primary", "drafting-only-binding")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                copy_method_project(root)
                if case == "missing-primary":
                    path = root / "catalog" / "SOURCES.json"
                    document = json.loads(path.read_text(encoding="utf-8"))
                    document["sources"][0]["kind"] = "drafting-provenance"
                    write_json(path, document)
                    expected_code = "METHOD_PRIMARY_THEORY_COUNT"
                else:
                    path = root / "catalog" / "EVIDENCE-INDEX.json"
                    document = json.loads(path.read_text(encoding="utf-8"))
                    binding = next(
                        item
                        for item in document["bindings"]
                        if item["claim_id"] == "claim-one-entrance"
                    )
                    binding["source_ids"] = [
                        "charting-loop-theory-internal-v5"
                    ]
                    write_json(path, document)
                    expected_code = "METHOD_BINDING_PRIMARY_THEORY"
                report, versions = registry.load_method_catalog(
                    root / "method-paper" / "VERSIONS.json"
                )
                self.assertFalse(report.ok)
                self.assertEqual(versions, [])
                self.assertTrue(
                    any(expected_code in error for error in report.errors),
                    report.errors,
                )

    def test_method_loader_preserves_legacy_v1_theory_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_method_project(root)
            theory_path = root / "theory" / "VERSIONS.json"
            theory_doc = json.loads(theory_path.read_text(encoding="utf-8"))
            legacy_theory = theory_doc["artifacts"][1]
            legacy_theory["provenance_role"] = "published-primary"
            legacy_theory["publication"] = {
                "record_doi": "10.5281/zenodo.99999999"
            }
            theory_doc = {
                "schema_version": "charting-loop/theory-index/v1",
                "artifacts": [legacy_theory],
            }
            write_json(theory_path, theory_doc)

            versions_path = root / "method-paper" / "VERSIONS.json"
            versions_doc = json.loads(versions_path.read_text(encoding="utf-8"))
            versions_doc["schema_version"] = registry.LEGACY_METHOD_INDEX_SCHEMA
            versions_doc["versions"] = [versions_doc["versions"][0]]
            versions_doc["versions"][0]["status"] = "draft"
            versions_doc["versions"][0]["source_commit"] = None
            versions_doc["versions"][0].pop("study_eligible")
            versions_doc["versions"][0].pop("adoption_eligible")
            versions_doc["versions"][0]["content_sha256"] = registry.file_sha256(
                root / "method-paper" / "METHOD.md"
            )
            versions_doc["versions"][0]["scope_datum_sha256"] = registry.file_sha256(
                root / "method-paper" / "SCOPE-DATUM.md"
            )
            versions_doc["versions"][0]["derived_from"] = {
                "theory_version_id": "internal-v5-arxiv-initial",
                "source_commit": "e0dd3a466654011ecf0cb6d8f32e9cbbc4c3cc99",
                "representation": "markdown",
                "content_sha256": "sha256:7c7a1522d3d6abd7fb3568046816e8f2708a979cbce0f3c2e041d24f4f8135ea",
            }
            write_json(versions_path, versions_doc)

            sources_path = root / "catalog" / "SOURCES.json"
            sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
            sources_doc["sources"] = [
                source
                for source in sources_doc["sources"]
                if source["source_id"] != "charting-loop-theory-zenodo-v1"
            ]
            sources_doc["sources"][0]["kind"] = "primary-theory"
            write_json(sources_path, sources_doc)

            evidence_path = root / "catalog" / "EVIDENCE-INDEX.json"
            evidence_doc = json.loads(evidence_path.read_text(encoding="utf-8"))
            for binding in evidence_doc["bindings"]:
                binding["source_ids"] = list(
                    dict.fromkeys(
                        "charting-loop-theory-internal-v5"
                        if source_id == "charting-loop-theory-zenodo-v1"
                        else source_id
                        for source_id in binding["source_ids"]
                    )
                )
            write_json(evidence_path, evidence_doc)

            report, versions = registry.load_method_catalog(versions_path)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(versions), 1)
            self.assertIsNone(report.facts["method_primary_theory_source_id"])

    def test_rejected_theory_catalog_path_is_invalid_not_an_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_method_project(root)
            external_theory = root / "external-theory"
            (root / "theory").rename(external_theory)
            (root / "theory").symlink_to(external_theory, target_is_directory=True)

            report, versions = registry.load_method_catalog(
                root / "method-paper" / "VERSIONS.json"
            )
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("PATH_SYMLINK" in error for error in report.errors),
                report.errors,
            )

    def test_eligible_method_uses_exact_bytes_from_a_real_source_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_method_project(root)
            index_path = root / "method-paper" / "VERSIONS.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["versions"] = [index["versions"][0]]
            write_json(index_path, index)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Registry Test"], cwd=root, check=True
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "freeze method"], cwd=root, check=True)
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            method_path = root / "method-paper" / "METHOD.md"
            frozen_digest = registry.file_sha256(method_path)
            method_path.write_text(method_path.read_text(encoding="utf-8") + "\nworktree drift\n", encoding="utf-8")
            worktree_digest = registry.file_sha256(method_path)
            scope_path = root / "method-paper" / "SCOPE-DATUM.md"
            frozen_scope_digest = registry.file_sha256(scope_path)
            scope_path.write_text(
                scope_path.read_text(encoding="utf-8") + "\nworktree drift\n",
                encoding="utf-8",
            )
            worktree_scope_digest = registry.file_sha256(scope_path)
            index = json.loads(index_path.read_text(encoding="utf-8"))
            version = index["versions"][0]
            version["status"] = "frozen"
            version["study_eligible"] = True
            version["adoption_eligible"] = True
            version["builder_eligible"] = True
            version["source_commit"] = commit
            version["content_sha256"] = frozen_digest
            version["scope_datum_sha256"] = frozen_scope_digest
            write_json(index_path, index)

            report, versions = registry.load_method_catalog(index_path)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(versions), 1)

            version["content_sha256"] = worktree_digest
            write_json(index_path, index)
            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(any("METHOD_SOURCE_HASH" in error for error in report.errors))

            version["content_sha256"] = frozen_digest
            version["scope_datum_sha256"] = worktree_scope_digest
            write_json(index_path, index)
            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_SCOPE_SOURCE_HASH" in error for error in report.errors),
                report.errors,
            )

            version["source_commit"] = "f" * 40
            version["content_sha256"] = frozen_digest
            version["scope_datum_sha256"] = frozen_scope_digest
            write_json(index_path, index)
            report, versions = registry.load_method_catalog(index_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(any("METHOD_SOURCE_GIT" in error for error in report.errors))

    def test_study_v3_binds_a_versioned_protocol_without_rewriting_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary) / "project"
            exogenous_root = project_root / "exogenous"
            make_fixture(exogenous_root)
            protocol_path = project_root / "protocol" / "EXPERIMENT-V2.md"
            protocol_path.parent.mkdir(parents=True)
            protocol_path.write_text("# Frozen experiment protocol v2\n", encoding="utf-8")

            taskset_path = (
                exogenous_root / "benchmarks" / "bench" / "v1" / "TASKSET.json"
            )
            taskset_report, taskset = registry.validate_taskset(
                taskset_path, exogenous_root
            )
            self.assertTrue(taskset_report.ok, taskset_report.errors)
            study_path = exogenous_root / "studies" / "study-001" / "STUDY.json"
            study = json.loads(study_path.read_text(encoding="utf-8"))
            study["schema_version"] = registry.STUDY_V3_SCHEMA
            study.pop("protocol_sha256")
            study["protocol_ref"] = {
                "path": "protocol/EXPERIMENT-V2.md",
                "sha256": registry.file_sha256(protocol_path),
            }
            write_json(study_path, study)

            report, validated = registry.validate_study(
                study_path,
                exogenous_root,
                {"bench-v1": (taskset_path, taskset)},
            )
            self.assertTrue(report.ok, report.errors)
            self.assertIsNotNone(validated)
            self.assertEqual(report.facts["protocol_ref"], study["protocol_ref"])

            study["protocol_ref"]["sha256"] = DIGESTS[0]
            write_json(study_path, study)
            report, _ = registry.validate_study(
                study_path,
                exogenous_root,
                {"bench-v1": (taskset_path, taskset)},
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("STUDY_PROTOCOL_HASH" in error for error in report.errors))

            study["protocol_ref"] = {
                "path": "outside-protocol.md",
                "sha256": registry.file_sha256(protocol_path),
            }
            write_json(study_path, study)
            report, _ = registry.validate_study(
                study_path,
                exogenous_root,
                {"bench-v1": (taskset_path, taskset)},
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("STUDY_PROTOCOL_PATH" in error for error in report.errors))

            protocol_link = project_root / "protocol" / "LINK.md"
            os.symlink(protocol_path, protocol_link)
            study["protocol_ref"] = {
                "path": "protocol/LINK.md",
                "sha256": registry.file_sha256(protocol_path),
            }
            write_json(study_path, study)
            report, _ = registry.validate_study(
                study_path,
                exogenous_root,
                {"bench-v1": (taskset_path, taskset)},
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("PATH_SYMLINK" in error for error in report.errors))

    def test_prospective_v8_method_does_not_rewrite_frozen_v2(self) -> None:
        paths = [
            REPOSITORY_ROOT / "method-paper" / "METHOD.md",
            REPOSITORY_ROOT / "method-paper" / "SCOPE-DATUM.md",
            REPOSITORY_ROOT / "protocol" / "CANDIDATE-CERTIFICATE.md",
            REPOSITORY_ROOT / "protocol" / "RUNTIME-EVIDENCE-SCHEMA.md",
            REPOSITORY_ROOT
            / "protocol"
            / "TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md",
            REPOSITORY_ROOT / "protocol" / "RUNNING-AN-EXPERIMENT.md",
            REPOSITORY_ROOT / "protocol" / "TASK-CONSTRAINT-DATUM.md",
        ]
        documents = {path.name: path.read_text(encoding="utf-8") for path in paths}
        method = documents["METHOD.md"]
        protocol_v2 = documents["TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md"]
        running = documents["RUNNING-AN-EXPERIMENT.md"]

        self.assertIn("Charting Loop corridor method — v8", method)
        self.assertIn("Status: **normative source**", method)
        self.assertIn("Architecture and projection boundary", method)
        self.assertIn("none is a reference\narchitecture", method)
        self.assertIn("construction-experiment profile", method)
        self.assertIn("long-lived governed-system profile", method)
        self.assertIn("append-only **Position ledger**", method)
        self.assertIn("IndependentQAAssessment", method)
        self.assertIn("task acceptance ledger", method)
        self.assertIn("Work backlog and reusable capability modules", method)
        self.assertIn("current row", method)
        self.assertIn("reminder", method)
        self.assertIn("Closing a reported witness is not task closure", method)
        self.assertIn("linear unlock", method)
        self.assertIn("Rule is the normative authority layer", method)
        self.assertIn("Rule consistency", method)
        self.assertIn("Rule-transition coherence", method)
        self.assertIn("Gate conformance", method)
        self.assertIn("Gate-chain coherence", method)
        self.assertIn("typed `projection_mismatch`", method)
        self.assertIn("cooperative-agent experiment profile", method)
        self.assertIn("not a credential, account", method)
        self.assertIn("per-file atomic", method)
        self.assertIn("timeline presence alone never admits a Fact", method)
        self.assertIn("two navigation variables", method)
        self.assertIn("PositionRef", method)
        self.assertIn("DirectionDigest", method)
        self.assertIn("CounterfactualTransition", method)
        self.assertIn("hypothetical=true", method)
        self.assertIn("Behavioral acceptance closure", method)
        self.assertIn("does not silently revise the published theory", method)
        self.assertIn("fresh Worker and a separate fresh Independent", protocol_v2)
        self.assertIn("exactly one bounded Worker repair opportunity", protocol_v2)
        self.assertIn("Agent-visible QA is a matched common intervention", protocol_v2)
        self.assertIn("append-only Position ledger invisibly and identically", running)
        self.assertIn("official evaluator", running)

        historical_protocol = (
            REPOSITORY_ROOT
            / "protocol"
            / "TASK-CONDITIONED-CORRIDOR-EXPERIMENT.md"
        )
        historical_study = json.loads(
            (
                REPOSITORY_ROOT
                / "exogenous"
                / "studies"
                / "cl027-tb3-production-planning"
                / "STUDY.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            registry.file_sha256(historical_protocol),
            historical_study["protocol_sha256"],
        )

        versions = json.loads(
            (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )["versions"]
        frozen = next(
            version for version in versions if version["version_id"] == "paper2-current-v2"
        )
        self.assertEqual(
            frozen["source_commit"],
            "f58e065ad5d035b55fc8668b094e42327382345a",
        )
        self.assertEqual(
            frozen["content_sha256"],
            "sha256:ce9c94c12660c57a8dc34c98afd46c644b07214a2f9e7a9a494078fbe7be0905",
        )
        self.assertTrue(frozen["study_eligible"])
        self.assertFalse(frozen["adoption_eligible"])
        self.assertFalse(frozen["builder_eligible"])

        non_primed = "\n".join(documents.values())
        for forbidden in (
            "CL-028",
            "c3a7c4714",
            "2025-06-17",
            "test_outputs.py",
            "qty_mismatch",
            "UTC-Z",
            "missing Z",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, non_primed)


if __name__ == "__main__":
    unittest.main()
