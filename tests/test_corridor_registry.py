from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import corridor_registry as registry


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_TEMPLATE_ROOT = REPOSITORY_ROOT / "templates" / "corridor"
LEGACY_TEMPLATE_ROOT = REPOSITORY_ROOT / "templates" / "legacy-corridor-v1"
TEST_DIGEST = "sha256:" + ("a" * 64)
COMMIT = "1" * 40


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rehash_authority(corridor_root: Path) -> None:
    manifest_path = corridor_root / "authority" / "AUTHORITY.json"
    interactions_path = corridor_root / "authority" / "interactions.jsonl"
    events_path = corridor_root / "authority" / "events.jsonl"
    manifest = json.loads((corridor_root / "CORRIDOR.json").read_text(encoding="utf-8"))
    authority = manifest["exogenous_authority"]
    authority_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    authority["assignment_sha256"] = registry.sha256_json_value(
        {
            "authority_boundary_id": authority_manifest.get("authority_boundary_id"),
            "study_design": authority_manifest.get("study_design"),
            "assigned_condition": authority_manifest.get("assigned_condition"),
            "actors": authority_manifest.get("actors"),
        }
    )
    authority["boundary_design_sha256"] = (
        registry.authority_boundary_design_digest(authority_manifest.get("actors"))
    )
    authority["manifest_sha256"] = registry.sha256_file(manifest_path)
    authority["interaction_log_sha256"] = registry.sha256_file(interactions_path)
    authority["event_log_sha256"] = registry.sha256_file(events_path)
    manifest["payload_tree_sha256"], _ = registry.hash_tree(
        corridor_root, ("inputs", "authority", "corridor", "trace", "evaluation")
    )
    write_json(corridor_root / "CORRIDOR.json", manifest)


def valid_registry_entry(run_id: str = "run-001") -> dict:
    entry = {
        "schema_version": registry.REGISTRY_SCHEMA,
        "entry_id": f"entry-{run_id}",
        "run_id": run_id,
        "status": "evaluated",
        "experiment": {
            "track": "reference",
            "knowledge_arm": "control-none",
            "system_condition": "no-corridor",
            "task_id": "reference-v1",
            "comparison_intent": "observational",
            "task_sha256": TEST_DIGEST,
            "evaluation_protocol_sha256": TEST_DIGEST,
            "input_bundle_sha256": TEST_DIGEST,
            "common_inputs_sha256": TEST_DIGEST,
            "treatment_inputs_sha256": TEST_DIGEST,
        },
        "subject": {
            "artifact_id": "direct-executor-control",
            "revision_id": "revision-001",
            "corridor_id": None,
        },
        "builder": {
            "model": "test-model",
            "runtime": "test-runtime",
            "run_date": "2026-08-11",
            "web_access": "disabled",
        },
        "source": {
            "repository_url": "https://github.com/example/repository",
            "base_commit": COMMIT,
            "artifact_commit": COMMIT,
            "artifact_root": "runs/run-001",
            "branch_hint": "exp/reference/control-none/run-001",
        },
        "artifact_tree_sha256": TEST_DIGEST,
        "artifact_verification": {"status": "unresolved"},
        "analysis_theory_ref": {
            "version_id": "analysis-v1",
            "artifact_id": "analysis-theory",
            "source_commit": COMMIT,
            "representation": "markdown",
            "content_sha256": TEST_DIGEST,
        },
        "theory_ref": None,
        "authority_evidence": {
            "input_condition": "bootstrap-only",
            "design_sha256": TEST_DIGEST,
            "boundary_design_sha256": TEST_DIGEST,
            "assignment_sha256": TEST_DIGEST,
            "condition_protocol_sha256": TEST_DIGEST,
            "manifest_sha256": TEST_DIGEST,
            "interaction_log_sha256": TEST_DIGEST,
            "event_log_sha256": TEST_DIGEST,
            "capture_status": "complete",
            "publication_status": "public-complete",
            "redacted_interaction_count": 0,
            "redacted_authority_source_count": 0,
            "observed_act_counts": {
                act: 0 for act in sorted(registry.ALLOWED_AUTHORITY_ACTS)
            },
        },
        "evaluation_summary": {
            "result_sha256": TEST_DIGEST,
            "assessment_log_sha256": TEST_DIGEST,
            "first_traversal": "passed",
            "first_traversal_fresh": True,
            "first_traversal_bypass_used": False,
            "first_traversal_attempt_count": 1,
            "subject_diagnosis_count": 6,
            "evaluator_assessment_count": 6,
            "diagnosis_verdict_agreement_count": 6,
            "diagnosis_evaluable_count": 6,
            "diagnosis_decisive_agreement_count": 6,
            "diagnosis_factor_comparable_count": 0,
            "diagnosis_factor_exact_agreement_count": 0,
            "scenarios": {scenario: "passed" for scenario in registry.SCENARIO_IDS},
            "diagnoses": {
                scenario: {
                    "subject": {
                        "assessment_id": f"{scenario}-subject",
                        "actor_id": "test-builder",
                        "actor_type": "ai",
                        "model": "test-model",
                        "theory_version_id": None,
                        "verdict": "no-drift",
                        "classification_status": "not-assessed",
                        "failure_factors": [],
                    },
                    "evaluator": {
                        "assessment_id": f"{scenario}-evaluator",
                        "actor_id": "test-evaluator",
                        "actor_type": "human",
                        "theory_version_id": "analysis-v1",
                        "verdict": "no-drift",
                        "classification_status": "not-assessed",
                        "failure_factors": [],
                    },
                }
                for scenario in registry.SCENARIO_IDS
            },
        },
    }
    entry["authority_evidence"]["observed_act_counts"]["provision"] = 1
    entry["evaluation_summary"]["diagnoses_sha256"] = registry.sha256_json_value(
        entry["evaluation_summary"]["diagnoses"]
    )
    return entry


class LegacyCorridorValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "corridor"
        shutil.copytree(LEGACY_TEMPLATE_ROOT, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_checked_in_template_is_structurally_valid(self) -> None:
        theory_report, versions = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.assertTrue(theory_report.ok, theory_report.errors)
        report = registry.validate_corridor(
            self.root, allow_template=True, theory_versions=versions
        )
        self.assertTrue(report.ok, report.errors)
        self.assertFalse(report.as_dict()["indexable"])
        self.assertEqual(report.facts["authority_capture"], "complete")

    def test_prepare_builder_materializes_only_the_closed_view(self) -> None:
        theory_report, versions = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        task_report, tasks = registry.validate_task_index(
            REPOSITORY_ROOT / "reference-task" / "VERSIONS.json"
        )
        self.assertTrue(theory_report.ok, theory_report.errors)
        self.assertTrue(task_report.ok, task_report.errors)
        destination = self.root.parent / "builder-workspace"
        report = registry.prepare_builder_workspace(
            self.root,
            destination,
            theory_versions=versions,
            task_versions=tasks,
        )
        self.assertTrue(report.ok, report.errors)
        files = sorted(
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, ["AGENTS.md", "inputs/files/BUILDER-BRIEF.md"])
        self.assertTrue((destination / "corridor").is_dir())
        self.assertEqual(list((destination / "corridor").iterdir()), [])
        self.assertFalse((destination / ".git").exists())
        self.assertFalse((destination / "authority").exists())

        second = registry.prepare_builder_workspace(
            self.root,
            destination,
            theory_versions=versions,
            task_versions=tasks,
        )
        self.assertFalse(second.ok)
        self.assertTrue(
            any("BUILDER_WORKSPACE_EXISTS" in error for error in second.errors)
        )

    def test_boolean_sequence_number_is_rejected(self) -> None:
        report = registry.Report(subject="sequence")
        registry._check_sequence([{"seq": True}], report, "records")
        self.assertFalse(report.ok)
        self.assertTrue(any("SEQUENCE_TYPE" in error for error in report.errors))

    def test_changed_interaction_bytes_break_frozen_hash(self) -> None:
        path = self.root / "authority" / "interactions.jsonl"
        path.write_bytes(path.read_bytes().replace(b"Construct", b"Reconstruct", 1))
        report = registry.validate_corridor(self.root, allow_template=True)
        self.assertFalse(report.ok)
        self.assertTrue(any("FILE_HASH" in error for error in report.errors))

    def test_subject_prompt_is_bound_to_the_task_catalog(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evaluation_protocol_ref"][
            "subject_diagnosis_prompt_sha256"
        ] = TEST_DIGEST
        write_json(manifest_path, manifest)
        task_report, tasks = registry.validate_task_index(
            REPOSITORY_ROOT / "reference-task" / "VERSIONS.json"
        )
        self.assertTrue(task_report.ok, task_report.errors)
        report = registry.validate_corridor(
            self.root, allow_template=True, task_versions=tasks
        )
        self.assertFalse(report.ok)
        self.assertTrue(
            any("EVALUATION_PROTOCOL_REF" in error for error in report.errors)
        )

    def test_malformed_knowledge_arm_is_reported_not_raised_during_assessment(self) -> None:
        input_path = self.root / "inputs" / "INPUTS.json"
        input_manifest = json.loads(input_path.read_text(encoding="utf-8"))
        input_manifest["knowledge_arm"] = []
        write_json(input_path, input_manifest)
        corridor = json.loads(
            (self.root / "CORRIDOR.json").read_text(encoding="utf-8")
        )
        assessment_path = self.root / "evaluation" / "ASSESSMENTS.jsonl"
        assessment = {
            "seq": 1,
            "assessment_id": "malformed-arm-subject",
            "scenario_id": "S1",
            "role": "subject-diagnosis",
            "actor_id": "template-ai",
            "actor_type": "ai",
            "model": "template-model",
            "runtime": "template-runtime",
            "web_access": "disabled",
            "diagnosis_prompt_sha256": corridor["evaluation_protocol_ref"][
                "subject_diagnosis_prompt_sha256"
            ],
            "blind_to_other_assessment": True,
            "timestamp": "2026-08-11T12:01:01-04:00",
            "verdict": "no-drift",
            "classification_status": "not-assessed",
            "failure_factors": [],
            "theory_version_id": None,
            "rationale": "Malformed input should be reported, not raised.",
            "evidence_refs": ["trace/scenarios/S1.json"],
            "evidence_sha256": TEST_DIGEST,
            "task_id": corridor["evaluation_protocol_ref"]["task_id"],
            "input_bundle_sha256": corridor["input_bundle"]["manifest_sha256"],
        }
        assessment_path.write_text(
            json.dumps(assessment, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        authority = json.loads(
            (self.root / "authority" / "AUTHORITY.json").read_text(encoding="utf-8")
        )
        actor_map = {actor["actor_id"]: actor for actor in authority["actors"]}
        report = registry.Report(subject=str(self.root))
        registry._validate_assessments(
            self.root,
            assessment_path,
            corridor,
            report,
            theory_versions=None,
            task_versions=None,
            actor_map=actor_map,
        )
        self.assertFalse(report.ok)

    def test_build_authority_must_precede_revision_freeze(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["revision_frozen_at"] = "2026-08-11T11:59:30-04:00"
        write_json(manifest_path, manifest)
        report = registry.validate_corridor(self.root, allow_template=True)
        self.assertFalse(report.ok)
        self.assertTrue(any("AUTHORITY_BUILD_TIME" in error for error in report.errors))

    def test_missing_interaction_log_is_rejected(self) -> None:
        (self.root / "authority" / "interactions.jsonl").unlink()
        report = registry.validate_corridor(self.root, allow_template=True)
        self.assertFalse(report.ok)
        self.assertTrue(any("REQUIRED_FILE" in error for error in report.errors))

    def test_unavailable_capture_is_preserved_without_reconstruction(self) -> None:
        (self.root / "authority" / "interactions.jsonl").write_text("", encoding="utf-8")
        (self.root / "authority" / "events.jsonl").write_text("", encoding="utf-8")
        authority_path = self.root / "authority" / "AUTHORITY.json"
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        authority["capture"].update(
            {
                "completeness": "unavailable",
                "first_interaction_id": None,
                "last_interaction_id": None,
                "gap_reason": "Platform capture was unavailable.",
            }
        )
        authority["record_counts"] = {"interactions": 0, "authority_events": 0}
        write_json(authority_path, authority)
        rehash_authority(self.root)

        report = registry.validate_corridor(self.root, allow_template=True)
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(any("AUTHORITY_INELIGIBLE" in warning for warning in report.warnings))

    def test_evaluated_candidate_assessment_happy_path(self) -> None:
        corridor = json.loads((self.root / "CORRIDOR.json").read_text(encoding="utf-8"))
        trace_binding = {
            "task_id": corridor["evaluation_protocol_ref"]["task_id"],
            "input_bundle_sha256": corridor["input_bundle"]["manifest_sha256"],
        }
        evaluator_binding = {
            "evaluation_protocol_sha256": corridor["evaluation_protocol_ref"][
                "tree_sha256"
            ],
            "analysis_theory_content_sha256": corridor["analysis_theory_ref"][
                "content_sha256"
            ],
        }
        subject_prompt_digest = registry.sha256_file(
            REPOSITORY_ROOT / "reference-task" / "SUBJECT-DIAGNOSIS-PROMPT.md"
        )
        first_observation = "Fresh first traversal completed without a bypass."
        write_json(
            self.root / "trace" / "FIRST-TRAVERSAL.json",
            {
                "schema_version": registry.FIRST_TRAVERSAL_EVIDENCE_SCHEMA,
                "corridor_id": corridor["corridor_id"],
                "revision_id": corridor["revision_id"],
                "corridor_tree_sha256": corridor["corridor_tree_sha256"],
                "status": "passed",
                "fresh": True,
                "bypass_used": False,
                "attempt_count": 1,
                "producer_actor_id": "independent-runner",
                "execution_instance_id": "instance-first-traversal",
                "baseline_state_sha256": TEST_DIGEST,
                "clean_copy_attestation": True,
                "observed_at": "2026-08-11T12:00:59-04:00",
                "observation": first_observation,
                "observation_sha256": registry.sha256_text(first_observation),
                **trace_binding,
            },
        )
        scenario_root = self.root / "trace" / "scenarios"
        scenario_root.mkdir()
        for scenario_id in registry.SCENARIO_IDS:
            observation = (
                f"{scenario_id} produced the recorded event sequence for later blind assessment."
            )
            write_json(
                scenario_root / f"{scenario_id}.json",
                {
                    "schema_version": registry.SCENARIO_EVIDENCE_SCHEMA,
                    "corridor_id": corridor["corridor_id"],
                    "revision_id": corridor["revision_id"],
                    "corridor_tree_sha256": corridor["corridor_tree_sha256"],
                    "scenario_id": scenario_id,
                    "producer_actor_id": "independent-runner",
                    "execution_instance_id": f"instance-{scenario_id}",
                    "baseline_state_sha256": TEST_DIGEST,
                    "clean_copy_attestation": True,
                    "observed_at": "2026-08-11T12:01:00-04:00",
                    "observation": observation,
                    "observation_sha256": registry.sha256_text(observation),
                    "label_free_attestation": True,
                    **trace_binding,
                },
            )
        assessment_path = self.root / "evaluation" / "ASSESSMENTS.jsonl"
        records = []
        for scenario_number, scenario_id in enumerate(registry.SCENARIO_IDS, start=1):
            records.extend(
                [
                    {
                        "seq": scenario_number * 2 - 1,
                        "assessment_id": f"assessment-{scenario_id}-subject",
                        "scenario_id": scenario_id,
                        "role": "subject-diagnosis",
                        "actor_id": "template-ai",
                        "actor_type": "ai",
                        "model": "template-model",
                        "runtime": "template-runtime",
                        "web_access": "disabled",
                        "diagnosis_prompt_sha256": subject_prompt_digest,
                        "blind_to_other_assessment": True,
                        "timestamp": f"2026-08-11T12:01:{scenario_number * 2 - 1:02d}-04:00",
                        "verdict": "no-drift",
                        "classification_status": "not-assessed",
                        "failure_factors": [],
                        "theory_version_id": None,
                        "rationale": "No drift detected in the frozen trace.",
                        "evidence_refs": [f"trace/scenarios/{scenario_id}.json"],
                        "evidence_sha256": registry.sha256_file(
                            scenario_root / f"{scenario_id}.json"
                        ),
                        **trace_binding,
                    },
                    {
                        "seq": scenario_number * 2,
                        "assessment_id": f"assessment-{scenario_id}-evaluator",
                        "scenario_id": scenario_id,
                        "role": "evaluator-assessment",
                        "actor_id": "independent-human-evaluator",
                        "actor_type": "human",
                        "model": None,
                        "blind_to_other_assessment": True,
                        "timestamp": f"2026-08-11T12:01:{scenario_number * 2:02d}-04:00",
                        "verdict": "no-drift",
                        "classification_status": "not-assessed",
                        "failure_factors": [],
                        "theory_version_id": "internal-v5-arxiv-initial",
                        "rationale": "The frozen evidence supports a pass.",
                        "evidence_refs": [f"trace/scenarios/{scenario_id}.json"],
                        "evidence_sha256": registry.sha256_file(
                            scenario_root / f"{scenario_id}.json"
                        ),
                        **trace_binding,
                        **evaluator_binding,
                    },
                ]
            )
        records.sort(key=lambda record: record["role"] != "subject-diagnosis")
        for sequence, record in enumerate(records, start=1):
            record["seq"] = sequence
            record["timestamp"] = f"2026-08-11T12:01:{sequence:02d}-04:00"
        assessment_path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )

        result_path = self.root / "evaluation" / "RESULT.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["status"] = "passed"
        result["assessment_log_path"] = "evaluation/ASSESSMENTS.jsonl"
        result["assessment_log_sha256"] = registry.sha256_file(assessment_path)
        result["first_traversal"].update(
            {
                "status": "passed",
                "fresh": True,
                "bypass_used": False,
                "attempt_count": 1,
                "trace_ref": "trace/FIRST-TRAVERSAL.json",
            }
        )
        for scenario_id in registry.SCENARIO_IDS:
            result["scenarios"][scenario_id] = {
                "status": "passed",
                "classification_status": "not-assessed",
                "failure_factors": [],
                "subject_diagnosis_id": f"assessment-{scenario_id}-subject",
                "evaluator_assessment_id": f"assessment-{scenario_id}-evaluator",
                "evidence_refs": [f"trace/scenarios/{scenario_id}.json"],
            }
        write_json(result_path, result)
        rehash_authority(self.root)

        theory_report, versions = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.assertTrue(theory_report.ok, theory_report.errors)
        report = registry.validate_corridor(
            self.root, allow_template=True, theory_versions=versions
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["diagnosis_pair_count"], 6)
        self.assertEqual(report.facts["diagnosis_verdict_agreement_count"], 6)
        self.assertEqual(report.facts["diagnosis_factor_comparable_count"], 0)

        late_trace_path = scenario_root / "S6.json"
        late_trace = json.loads(late_trace_path.read_text(encoding="utf-8"))
        late_trace["observed_at"] = "2026-08-11T12:01:05-04:00"
        write_json(late_trace_path, late_trace)
        late_trace_digest = registry.sha256_file(late_trace_path)
        for record in records:
            if record["scenario_id"] == "S6":
                record["evidence_sha256"] = late_trace_digest
        assessment_path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        result["assessment_log_sha256"] = registry.sha256_file(assessment_path)
        write_json(result_path, result)
        rehash_authority(self.root)
        report = registry.validate_corridor(
            self.root, allow_template=True, theory_versions=versions
        )
        self.assertFalse(report.ok)
        self.assertTrue(
            any("ASSESSMENT_TRACE_BARRIER" in error for error in report.errors)
        )

    def test_builder_cannot_issue_its_own_ratification(self) -> None:
        events_path = self.root / "authority" / "events.jsonl"
        event = {
            "seq": 2,
            "event_id": "authority-event-002",
            "timestamp": "2026-08-11T12:00:02-04:00",
            "authority_actor_id": "template-ai",
            "act": "ratify",
            "interaction_ids": ["interaction-002"],
            "target_kind": "corridor-revision",
            "target_ref": "corridor:template-corridor:candidate-001",
            "target_sha256": TEST_DIGEST,
            "effect": "approved",
        }
        with events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        authority_path = self.root / "authority" / "AUTHORITY.json"
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        authority["record_counts"]["authority_events"] = 2
        write_json(authority_path, authority)
        rehash_authority(self.root)

        report = registry.validate_corridor(self.root, allow_template=True)
        self.assertFalse(report.ok)
        self.assertTrue(any("SELF_RATIFY" in error for error in report.errors))
        self.assertTrue(any("AUTHORITY_PERMISSION" in error for error in report.errors))

    def test_bootstrap_only_rejects_later_authority_acts(self) -> None:
        corridor_path = self.root / "CORRIDOR.json"
        corridor = json.loads(corridor_path.read_text(encoding="utf-8"))
        corridor["exogenous_authority"]["input_condition"] = "bootstrap-only"
        write_json(corridor_path, corridor)

        authority_path = self.root / "authority" / "AUTHORITY.json"
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        authority["assigned_condition"]["mode"] = "bootstrap-only"
        authority["record_counts"]["authority_events"] = 2
        write_json(authority_path, authority)

        events_path = self.root / "authority" / "events.jsonl"
        event = {
            "seq": 2,
            "event_id": "authority-event-002",
            "timestamp": "2026-08-11T12:00:02-04:00",
            "authority_actor_id": "template-user",
            "act": "redirect",
            "interaction_ids": ["interaction-001"],
            "target_kind": "direction",
            "target_ref": "reference-task:v2",
            "target_sha256": TEST_DIGEST,
            "effect": "issued",
        }
        with events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        rehash_authority(self.root)

        report = registry.validate_corridor(self.root, allow_template=True)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("AUTHORITY_CONDITION_VIOLATION" in error for error in report.errors)
        )


class CandidateV2ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "corridor"
        shutil.copytree(CANDIDATE_TEMPLATE_ROOT, self.root)
        self.theory_report, self.theories = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.method_report, self.methods = registry.validate_method_index(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json",
            theory_versions=self.theories,
            theory_schema_version=self.theory_report.facts["schema_version"],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self, *, allow_template: bool = True) -> registry.Report:
        return registry.validate_corridor(
            self.root,
            allow_template=allow_template,
            theory_versions=self.theories,
            method_versions=self.methods,
        )

    def test_checked_in_candidate_template_is_valid_and_not_indexable(self) -> None:
        self.assertTrue(self.theory_report.ok, self.theory_report.errors)
        self.assertTrue(self.method_report.ok, self.method_report.errors)
        report = self.validate()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["schema_version"], registry.CANDIDATE_SCHEMA)
        self.assertFalse(report.facts["builder_eligible"])
        self.assertEqual(report.facts["candidate_state"], "open")
        self.assertEqual(report.facts["guide_result_kind"], "entrance")
        self.assertEqual(report.facts["authority_evidence_status"], "not_assessed")
        self.assertFalse(report.as_dict()["indexable"])

    def test_candidate_template_requires_allow_template(self) -> None:
        report = self.validate(allow_template=False)
        self.assertFalse(report.ok)
        self.assertTrue(any("TEMPLATE" in error for error in report.errors))

    def test_candidate_cannot_self_claim_assurance(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["assurances"]["path_certificate"] = {"status": "passed"}
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("ASSURANCE_TEMPLATE_CLAIM" in error for error in report.errors)
        )

    def test_candidate_draft_cannot_be_builder_eligible(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["builder_eligible"] = True
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("CANDIDATE_BUILDER_ELIGIBILITY" in error for error in report.errors)
        )

    def test_candidate_rejects_unsafe_implementation_path(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["implementation"]["path"] = "../escape"
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("PATH_ESCAPE" in error for error in report.errors))

    def test_candidate_rejects_symlink_anywhere_in_implementation_tree(self) -> None:
        os.symlink("/etc/passwd", self.root / "implementation" / "escape")
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("IMPLEMENTATION_TREE" in error for error in report.errors))

    def test_guide_must_be_deterministic_and_return_one_result(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["guide"]["evaluation"] = "ranked-search"
        manifest["guide"]["result"]["cardinality"] = "many"
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("GUIDE_DETERMINISM" in error for error in report.errors))
        self.assertTrue(
            any("GUIDE_RESULT_CARDINALITY" in error for error in report.errors)
        )

    def test_role_assignment_must_bind_definition_and_scope(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["position"]["role_assignment"]["role_id"] = "evaluator"
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("ROLE_ASSIGNMENT_BINDING" in error for error in report.errors)
        )

    def test_role_assignment_must_resolve_to_an_admitted_fact(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["position"]["role_assignment"]["assignment_fact_id"] = (
            "undeclared-assignment-fact"
        )
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("ROLE_ASSIGNMENT_FACT" in error for error in report.errors))

    def test_opaque_entrance_lookup_is_bounded_to_one(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["guide_result"]["entrance"]["consumable_instruction"][
            "max_matches"
        ] = 2
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("ENTRANCE_LOOKUP_BOUND" in error for error in report.errors))

    def test_allowed_actions_remain_bound_to_the_declared_rule_digest(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entrance = manifest["guide_result"]["entrance"]
        entrance["allowed_actions"].append("delete candidate history")
        entrance["allowed_actions_sha256"] = registry.sha256_json_value(
            sorted(entrance["allowed_actions"])
        )
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("ENTRANCE_ACTION_RULE" in error for error in report.errors))

    def test_typed_refusal_is_a_valid_exclusive_guide_result(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["guide_result"] = {
            "kind": "typed-refusal",
            "refusal": {
                "code": "not_assessed",
                "reason": "input unavailable",
                "governing_rule": {
                    "rule_id": "direction-compilation-rule",
                    "rule_version": "draft",
                    "rule_ref": "runner-supplied immutable direction-compilation rule",
                    "input_context_sha256": TEST_DIGEST,
                },
            },
        }
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["guide_result_kind"], "typed-refusal")

        manifest["guide_result"]["refusal"]["governing_rule"]["rule_id"] = "undeclared"
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("GUIDE_REFUSAL_RULE" in error for error in report.errors))

    def test_candidate_state_container_is_structurally_invalid_not_an_exception(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        for invalid in ([], {}):
            with self.subTest(invalid=invalid):
                manifest = dict(original)
                manifest["candidate_state"] = invalid
                write_json(manifest_path, manifest)
                report = self.validate()
                self.assertFalse(report.ok)
                self.assertTrue(any("CANDIDATE_STATE" in error for error in report.errors))

    def test_open_and_frozen_candidate_digest_invariants(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["implementation"]["tree_sha256"] = TEST_DIGEST
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("CANDIDATE_OPEN_TREE" in error for error in report.errors))

        tree_digest, _ = registry.hash_tree(self.root, ("implementation",))
        manifest["candidate_state"] = "frozen"
        manifest["implementation"]["tree_sha256"] = tree_digest
        manifest["semantic_closure_sha256"] = registry.candidate_semantic_closure_sha256(
            manifest
        )
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertTrue(report.ok, report.errors)

    def test_guide_contract_and_instruction_selection_fail_closed(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["guide"]["contract_path"] = "CORRIDOR.json"
        entrance = manifest["guide_result"]["entrance"]
        entrance["consumable_instruction"]["facade"] = "grep"
        entrance["allowed_actions"].append("search the open repository with RAG")
        entrance["instruction_contract"]["agent_source_selection"] = True
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("GUIDE_CONTRACT_PATH" in error for error in report.errors))
        self.assertTrue(any("ENTRANCE_SEMANTIC_PULL" in error for error in report.errors))
        self.assertTrue(
            any("ENTRANCE_INSTRUCTION_CONTRACT" in error for error in report.errors)
        )

    def test_guide_contract_is_explicitly_runner_owned_read_only(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["implementation"]["runner_owned_paths"] = []
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("IMPLEMENTATION_OWNERSHIP" in error for error in report.errors))

    def test_instruction_contract_rejects_bool_int_type_confusion(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutations = (
            ("selection_cardinality", True),
            ("agent_source_selection", 0),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                manifest = json.loads(json.dumps(original))
                manifest["guide_result"]["entrance"]["instruction_contract"][key] = value
                write_json(manifest_path, manifest)
                report = self.validate()
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("ENTRANCE_INSTRUCTION_CONTRACT" in error for error in report.errors),
                    report.errors,
                )

    def test_implementation_path_cannot_exclude_the_guide_contract(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["candidate_state"] = "frozen"
        manifest["implementation"]["path"] = "receipts"
        tree_digest, _ = registry.hash_tree(self.root, ("receipts",))
        manifest["implementation"]["tree_sha256"] = tree_digest
        manifest["semantic_closure_sha256"] = registry.candidate_semantic_closure_sha256(
            manifest
        )
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("IMPLEMENTATION_PATH" in error for error in report.errors))

    def test_direction_must_resolve_to_a_declared_rule(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["guide_result"]["entrance"]["direction"]["rule_id"] = "undeclared"
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("DIRECTION_RULE" in error for error in report.errors))

    def test_method_ref_requires_explicit_cataloged_source_commit(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["method_ref"]["source_commit"]
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("METHOD_REF_FIELDS" in error for error in report.errors))

        manifest["method_ref"]["source_commit"] = COMMIT
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("METHOD_REF" in error for error in report.errors))

    def test_method_ref_requires_explicit_adoption_eligibility(self) -> None:
        current = next(
            version for version in self.methods if version["study_eligible"] is True
        )
        current.pop("adoption_eligible")

        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("METHOD_REF" in error for error in report.errors))

    def test_position_and_role_definition_must_resolve_exactly(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["position"]["object_ref"] = "different@revision"
        manifest["position"]["role_definition"]["ref"] = "undeclared-rule"
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("POSITION_OBJECT_REF" in error for error in report.errors))
        self.assertTrue(any("ROLE_DEFINITION_RULE" in error for error in report.errors))

    def test_authority_evidence_requires_a_future_strict_profile(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["authority_evidence"] = {}
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(any("AUTHORITY_EVIDENCE" in error for error in report.errors))

    def test_world_prefix_requires_digest_and_projector_identity(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["world_ref"]["evidence_prefix"] = {
            "stream_id": "timeline",
            "through_sequence": 1,
            "prefix_sha256": TEST_DIGEST,
        }
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("WORLD_REF_PREFIX_FIELDS" in error for error in report.errors)
        )

    def test_worldref_requires_complete_identity_and_digests(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in (
            "project_id",
            "run_id",
            "generation_id",
            "repository_url",
            "base_commit",
            "environment_sha256",
            "evidence_prefix",
            "derived_state_sha256",
        ):
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(original))
                del manifest["world_ref"][field]
                write_json(manifest_path, manifest)
                report = self.validate()
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("WORLD_REF_FIELDS" in error for error in report.errors),
                    report.errors,
                )

    def test_assignment_declares_exact_two_warranty_kinds(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["position"]["role_assignment"]["required_warranty_kinds"] = [
            "EvidentialWarranty"
        ]
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("ROLE_ASSIGNMENT_WARRANTIES" in error for error in report.errors)
        )

    def test_candidate_cannot_self_claim_authority_warranty(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["assurances"]["authority_warranty"] = {
            "state": "live"
        }
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        self.assertTrue(
            any("ASSURANCE_TEMPLATE_CLAIM" in error for error in report.errors)
        )

    def test_candidate_world_repository_requires_strict_https_identity(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        invalid_urls = (
            "https://",
            "https:///repo",
            "https://user@example.invalid/repo",
            "https://example.invalid/repo?branch=main",
            "https://example.invalid/repo#tip",
            "https://example.invalid:99999/repo",
            " https://example.invalid/repo",
            "https://exa mple.invalid/repo",
            "https://-bad.example/repo",
            "https://example.invalid./repo",
            "https://[",
        )
        for value in invalid_urls:
            with self.subTest(value=value):
                manifest = json.loads(json.dumps(original))
                manifest["world_ref"]["repository_url"] = value
                write_json(manifest_path, manifest)
                report = self.validate()
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("WORLD_REF_REPOSITORY" in error for error in report.errors),
                    report.errors,
                )

    def test_instruction_closure_uses_pinned_identity_and_digests(self) -> None:
        manifest_path = self.root / "CORRIDOR.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entrance = manifest["guide_result"]["entrance"]
        instruction = entrance["consumable_instruction"]
        instruction["opaque_key"] = "benign-different-key"
        del instruction["lookup_scope_id"]
        instruction["facade"]["interface"]["extra"] = "benign"
        entrance["instruction_contract"]["selection_cardinality"] = 2
        write_json(manifest_path, manifest)
        report = self.validate()
        self.assertFalse(report.ok)
        for code in (
            "ENTRANCE_ARGUMENTS_HASH",
            "ENTRANCE_INSTRUCTION_FIELDS",
            "ENTRANCE_INTERFACE_FIELDS",
            "ENTRANCE_INSTRUCTION_CONTRACT",
        ):
            self.assertTrue(any(code in error for error in report.errors), report.errors)


class MethodIndexValidationTests(unittest.TestCase):
    def test_non_string_method_schema_and_status_fail_closed(self) -> None:
        for field, bad_value in (("schema_version", []), ("status", [])):
            with self.subTest(field=field), tempfile.TemporaryDirectory(
                dir=REPOSITORY_ROOT
            ) as temporary:
                temporary_root = Path(temporary)
                method_root = temporary_root / "method-paper"
                catalog_root = temporary_root / "catalog"
                method_root.mkdir()
                catalog_root.mkdir()
                for name in ("METHOD.md", "SCOPE-DATUM.md"):
                    shutil.copy2(
                        REPOSITORY_ROOT / "method-paper" / name,
                        method_root / name,
                    )
                for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                    shutil.copy2(
                        REPOSITORY_ROOT / "catalog" / name,
                        catalog_root / name,
                    )
                document = json.loads(
                    (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                        encoding="utf-8"
                    )
                )
                if field == "schema_version":
                    document[field] = bad_value
                else:
                    document["versions"][0][field] = bad_value
                write_json(method_root / "VERSIONS.json", document)
                report, versions = registry.validate_method_index(
                    method_root / "VERSIONS.json"
                )
                self.assertFalse(report.ok)
                self.assertEqual(versions, [])

    def test_checked_in_method_is_frozen_for_study_not_adoption(self) -> None:
        theory_report, theories = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.assertTrue(theory_report.ok, theory_report.errors)
        report, versions = registry.validate_method_index(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json",
            theory_versions=theories,
            theory_schema_version=theory_report.facts["schema_version"],
        )
        self.assertTrue(report.ok, report.errors)
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
        self.assertEqual(
            report.facts["schema_version"], registry.METHOD_INDEX_SCHEMA
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
        self.assertEqual(current["status"], "frozen")
        self.assertFalse(current["adoption_eligible"])
        self.assertFalse(current["builder_eligible"])
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
        self.assertFalse(historical["adoption_eligible"])
        self.assertFalse(historical["builder_eligible"])
        self.assertEqual(
            historical["source_commit"],
            "8b36a35b368c787d07bd3d1b81ee6aae46a21e5c",
        )
        self.assertEqual(
            historical["content_sha256"],
            "sha256:bc73c87a348eff6eeec9444e85e71a706c808827a6c11c9f810fd919be630fc7",
        )
        self.assertEqual(
            historical["scope_datum_sha256"],
            "sha256:973d0993193ec2598cacfeb3e708161f8fddade02448ea1ad5bc105a293cf91c",
        )
        self.assertEqual(v4["status"], "frozen")
        self.assertTrue(v4["study_eligible"])
        self.assertFalse(v4["adoption_eligible"])
        self.assertFalse(v4["builder_eligible"])
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
        self.assertEqual(v5["status"], "frozen")
        self.assertTrue(v5["study_eligible"])
        self.assertFalse(v5["adoption_eligible"])
        self.assertFalse(v5["builder_eligible"])
        self.assertEqual(
            v5["source_commit"],
            "8b0fd5e1c6102c6b4c44cf03612b93c450ddb6fd",
        )
        self.assertEqual(v6["status"], "frozen")
        self.assertTrue(v6["study_eligible"])
        self.assertFalse(v6["adoption_eligible"])
        self.assertFalse(v6["builder_eligible"])
        self.assertEqual(
            v6["source_commit"],
            "3bf463f013e68f157028f85e0e80c7608091a851",
        )
        self.assertEqual(v7["status"], "frozen")
        self.assertTrue(v7["study_eligible"])
        self.assertFalse(v7["adoption_eligible"])
        self.assertFalse(v7["builder_eligible"])
        self.assertEqual(
            v7["source_commit"],
            "c68813cea1aa1d1eeaafde69a3f35f71ffab6d0d",
        )
        self.assertEqual(v8["status"], "frozen")
        self.assertTrue(v8["study_eligible"])
        self.assertFalse(v8["adoption_eligible"])
        self.assertFalse(v8["builder_eligible"])
        self.assertEqual(
            v8["source_commit"],
            "3c3813444a7d43d0a56837e9cb960be86ce26d06",
        )
        self.assertEqual(
            v8["content_sha256"],
            "sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446",
        )
        self.assertEqual(
            v8["scope_datum_sha256"],
            "sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af",
        )
        self.assertEqual(report.facts["study_eligible_version_count"], 6)
        self.assertEqual(report.facts["adoption_eligible_version_count"], 0)
        self.assertEqual(report.facts["builder_eligible_version_count"], 0)
        self.assertEqual(
            current["derived_from"],
            {
                "theory_version_id": "zenodo-v1",
                "source_commit": "cf5ac479e208a2401b9358527d58df48e22c0670",
                "representation": "pdf",
                "content_sha256": "sha256:f557af476441e814e4d86041969c18fde2299a6a47d28658bdeb8cec2d7296c1",
            },
        )
        self.assertEqual(report.facts["method_provenance_join_status"], "validated")
        self.assertEqual(
            report.facts["method_primary_theory_source_id"],
            "charting-loop-theory-zenodo-v1",
        )
        self.assertEqual(report.facts["method_primary_theory_version_id"], "zenodo-v1")
        self.assertEqual(report.facts["method_drafting_provenance_count"], 1)
        self.assertEqual(report.facts["method_claim_count"], 20)
        self.assertEqual(report.facts["method_binding_count"], 20)
        self.assertEqual(report.facts["method_source_count"], 4)
        self.assertEqual(
            report.facts["method_source_bytes_resolution_status"], "not-resolved"
        )
        method_text = (REPOSITORY_ROOT / "method-paper" / "METHOD.md").read_text(
            encoding="utf-8"
        )
        references_text = (
            REPOSITORY_ROOT / "method-paper" / "references.bib"
        ).read_text(encoding="utf-8")
        scope_text = (
            REPOSITORY_ROOT / "method-paper" / "SCOPE-DATUM.md"
        ).read_text(encoding="utf-8")
        for text in (method_text, references_text, scope_text):
            self.assertIn("10.5281/zenodo.21844624", text)
        self.assertIn("version      = {v1}", references_text)
        self.assertIn("future Theory v2", method_text)
        self.assertIn("estimator definitions", scope_text)
        self.assertIn("results belong to Paper 3", scope_text)
        evidence = json.loads(
            (REPOSITORY_ROOT / "catalog" / "EVIDENCE-INDEX.json").read_text(
                encoding="utf-8"
            )
        )
        drafting_bindings = [
            binding["claim_id"]
            for binding in evidence["bindings"]
            if "charting-loop-theory-internal-v5" in binding["source_ids"]
        ]
        self.assertEqual(
            drafting_bindings,
            ["claim-failure-diagnostic-rubric"],
        )
        diagnostic_binding = next(
            binding
            for binding in evidence["bindings"]
            if binding["claim_id"] == "claim-failure-diagnostic-rubric"
        )
        self.assertIn("non-primary", diagnostic_binding["relationship"])

    def test_method_scope_digest_is_resolved_at_each_declared_commit(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                shutil.copy2(
                    REPOSITORY_ROOT / "method-paper" / name,
                    method_root / name,
                )
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / name,
                    catalog_root / name,
                )

            versions_path = method_root / "VERSIONS.json"
            document = json.loads(versions_path.read_text(encoding="utf-8"))
            historical = next(
                version
                for version in document["versions"]
                if version["version_id"] == "draft-v2"
            )
            historical["scope_datum_sha256"] = (
                "sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307"
            )
            write_json(versions_path, document)

            report, versions = registry.validate_method_index(versions_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_SCOPE_SOURCE_HASH" in error for error in report.errors),
                report.errors,
            )

    def test_v2_historical_method_cannot_fall_back_to_ambient_bytes(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                shutil.copy2(
                    REPOSITORY_ROOT / "method-paper" / name,
                    method_root / name,
                )
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / name,
                    catalog_root / name,
                )

            versions_path = method_root / "VERSIONS.json"
            document = json.loads(versions_path.read_text(encoding="utf-8"))
            historical = next(
                version
                for version in document["versions"]
                if version["version_id"] == "draft-v2"
            )
            historical["source_commit"] = None
            historical["content_sha256"] = (
                "sha256:ce9c94c12660c57a8dc34c98afd46c644b07214a2f9e7a9a494078fbe7be0905"
            )
            historical["scope_datum_sha256"] = (
                "sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307"
            )
            write_json(versions_path, document)

            report, versions = registry.validate_method_index(versions_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_SOURCE_COMMIT" in error for error in report.errors),
                report.errors,
            )

    def test_v2_method_catalog_supports_multiple_study_versions_but_requires_one(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            (catalog_root / "v4").mkdir()
            (catalog_root / "v5").mkdir()
            (catalog_root / "v6").mkdir()
            (catalog_root / "v7").mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                shutil.copy2(REPOSITORY_ROOT / "method-paper" / name, method_root / name)
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(REPOSITORY_ROOT / "catalog" / name, catalog_root / name)
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / "v4" / name,
                    catalog_root / "v4" / name,
                )
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / "v5" / name,
                    catalog_root / "v5" / name,
                )
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / "v6" / name,
                    catalog_root / "v6" / name,
                )
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / "v7" / name,
                    catalog_root / "v7" / name,
                )
            versions_path = method_root / "VERSIONS.json"
            document = json.loads(versions_path.read_text(encoding="utf-8"))
            for version in document["versions"]:
                version["study_eligible"] = False
            write_json(versions_path, document)

            report, versions = registry.validate_method_index(versions_path)
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_STUDY_VERSION_COUNT" in error for error in report.errors),
                report.errors,
            )

        report, versions = registry.validate_method_index(
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

    def test_primary_theory_and_theory_derived_bindings_are_enforced(self) -> None:
        theory_report, theories = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.assertTrue(theory_report.ok, theory_report.errors)
        cases = (
            "duplicate-primary",
            "missing-primary",
            "lineage-mismatch",
            "drafting-only-binding",
            "role-swap",
            "container-kind",
        )
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
                    temporary_root = Path(temporary)
                    method_root = temporary_root / "method-paper"
                    catalog_root = temporary_root / "catalog"
                    method_root.mkdir()
                    catalog_root.mkdir()
                    for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                        shutil.copy2(
                            REPOSITORY_ROOT / "method-paper" / name,
                            method_root / name,
                        )
                    for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                        shutil.copy2(
                            REPOSITORY_ROOT / "catalog" / name,
                            catalog_root / name,
                        )

                    sources_path = catalog_root / "SOURCES.json"
                    sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
                    if case == "duplicate-primary":
                        sources_doc["sources"][1]["kind"] = "primary-theory"
                        write_json(sources_path, sources_doc)
                    elif case == "missing-primary":
                        sources_doc["sources"][0]["kind"] = "drafting-provenance"
                        write_json(sources_path, sources_doc)
                    elif case == "lineage-mismatch":
                        versions_path = method_root / "VERSIONS.json"
                        versions_doc = json.loads(
                            versions_path.read_text(encoding="utf-8")
                        )
                        versions_doc["versions"][0]["derived_from"]["source_commit"] = (
                            "f" * 40
                        )
                        write_json(versions_path, versions_doc)
                    elif case == "drafting-only-binding":
                        evidence_path = catalog_root / "EVIDENCE-INDEX.json"
                        evidence_doc = json.loads(
                            evidence_path.read_text(encoding="utf-8")
                        )
                        binding = next(
                            item
                            for item in evidence_doc["bindings"]
                            if item["claim_id"] == "claim-one-entrance"
                        )
                        binding["source_ids"] = [
                            "charting-loop-theory-internal-v5"
                        ]
                        write_json(evidence_path, evidence_doc)
                    elif case == "role-swap":
                        sources_doc["sources"][0]["kind"] = "drafting-provenance"
                        sources_doc["sources"][1]["kind"] = "primary-theory"
                        write_json(sources_path, sources_doc)
                        versions_path = method_root / "VERSIONS.json"
                        versions_doc = json.loads(
                            versions_path.read_text(encoding="utf-8")
                        )
                        versions_doc["versions"][0]["derived_from"] = {
                            "theory_version_id": "internal-v5-arxiv-initial",
                            "source_commit": "e0dd3a466654011ecf0cb6d8f32e9cbbc4c3cc99",
                            "representation": "markdown",
                            "content_sha256": "sha256:7c7a1522d3d6abd7fb3568046816e8f2708a979cbce0f3c2e041d24f4f8135ea",
                        }
                        write_json(versions_path, versions_doc)
                        evidence_path = catalog_root / "EVIDENCE-INDEX.json"
                        evidence_doc = json.loads(
                            evidence_path.read_text(encoding="utf-8")
                        )
                        for binding in evidence_doc["bindings"]:
                            binding["source_ids"] = [
                                "charting-loop-theory-internal-v5"
                                if source_id == "charting-loop-theory-zenodo-v1"
                                else source_id
                                for source_id in binding["source_ids"]
                            ]
                        write_json(evidence_path, evidence_doc)
                    else:
                        sources_doc["sources"][0]["kind"] = []
                        write_json(sources_path, sources_doc)

                    report, _ = registry.validate_method_index(
                        method_root / "VERSIONS.json",
                        theory_versions=theories,
                        theory_schema_version=theory_report.facts["schema_version"],
                    )
                    self.assertFalse(report.ok)
                    expected_code = {
                        "duplicate-primary": "METHOD_PRIMARY_THEORY_COUNT",
                        "missing-primary": "METHOD_PRIMARY_THEORY_COUNT",
                        "lineage-mismatch": "METHOD_PRIMARY_THEORY_LINEAGE",
                        "drafting-only-binding": "METHOD_BINDING_PRIMARY_THEORY",
                        "role-swap": "METHOD_SOURCE_THEORY_ROLE",
                        "container-kind": "ENUM",
                    }[case]
                    self.assertTrue(
                        any(expected_code in error for error in report.errors),
                        report.errors,
                    )

    def test_legacy_v1_theory_remains_consumable_by_legacy_method_catalogs(self) -> None:
        current_theory = json.loads(
            (REPOSITORY_ROOT / "theory" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        legacy_theory = json.loads(json.dumps(current_theory["artifacts"][1]))
        legacy_theory["provenance_role"] = "published-primary"
        legacy_theory["publication"] = {
            "record_doi": "10.5281/zenodo.99999999"
        }
        theory_versions = [legacy_theory]
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                shutil.copy2(
                    REPOSITORY_ROOT / "method-paper" / name,
                    method_root / name,
                )
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(
                    REPOSITORY_ROOT / "catalog" / name,
                    catalog_root / name,
                )

            versions_path = method_root / "VERSIONS.json"
            versions_doc = json.loads(versions_path.read_text(encoding="utf-8"))
            versions_doc["versions"] = [versions_doc["versions"][0]]
            versions_doc["versions"][0]["derived_from"] = {
                "theory_version_id": "internal-v5-arxiv-initial",
                "source_commit": "e0dd3a466654011ecf0cb6d8f32e9cbbc4c3cc99",
                "representation": "markdown",
                "content_sha256": "sha256:7c7a1522d3d6abd7fb3568046816e8f2708a979cbce0f3c2e041d24f4f8135ea",
            }
            write_json(versions_path, versions_doc)

            sources_path = catalog_root / "SOURCES.json"
            sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
            sources_doc["sources"] = [
                source
                for source in sources_doc["sources"]
                if source["source_id"] != "charting-loop-theory-zenodo-v1"
            ]
            sources_doc["sources"][0]["kind"] = "primary-theory"
            write_json(sources_path, sources_doc)

            evidence_path = catalog_root / "EVIDENCE-INDEX.json"
            evidence_doc = json.loads(evidence_path.read_text(encoding="utf-8"))
            for binding in evidence_doc["bindings"]:
                binding["source_ids"] = [
                    "charting-loop-theory-internal-v5"
                    if source_id == "charting-loop-theory-zenodo-v1"
                    else source_id
                    for source_id in binding["source_ids"]
                ]
                binding["source_ids"] = list(dict.fromkeys(binding["source_ids"]))
            write_json(evidence_path, evidence_doc)

            report, versions = registry.validate_method_index(
                versions_path,
                theory_versions=theory_versions,
                theory_schema_version=registry.LEGACY_THEORY_INDEX_SCHEMA,
            )
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(versions), 1)
            self.assertIsNone(report.facts["method_primary_theory_source_id"])

    def test_v2_role_policy_cannot_be_downgraded_by_deleting_all_roles(self) -> None:
        theory_report, theories = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.assertTrue(theory_report.ok, theory_report.errors)
        roleless = json.loads(json.dumps(theories))
        for theory in roleless:
            theory.pop("provenance_role")

        report, versions = registry.validate_method_index(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json",
            theory_versions=roleless,
            theory_schema_version=registry.THEORY_INDEX_SCHEMA,
        )
        self.assertFalse(report.ok)
        self.assertEqual(versions, [])
        self.assertTrue(
            any("METHOD_SOURCE_THEORY_ROLE" in error for error in report.errors),
            report.errors,
        )

        contextless_report, contextless_versions = registry.validate_method_index(
            REPOSITORY_ROOT / "method-paper" / "VERSIONS.json",
            theory_versions=roleless,
        )
        self.assertFalse(contextless_report.ok)
        self.assertEqual(contextless_versions, [])
        self.assertTrue(
            any(
                "METHOD_THEORY_SCHEMA_CONTEXT" in error
                for error in contextless_report.errors
            ),
            contextless_report.errors,
        )

    def test_method_catalog_rejects_adoption_alias_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md"):
                shutil.copy2(REPOSITORY_ROOT / "method-paper" / name, method_root / name)
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(REPOSITORY_ROOT / "catalog" / name, catalog_root / name)
            document = json.loads(
                (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                    encoding="utf-8"
                )
            )
            document["versions"][0]["builder_eligible"] = True
            write_json(method_root / "VERSIONS.json", document)
            report, _ = registry.validate_method_index(method_root / "VERSIONS.json")
            self.assertFalse(report.ok)
            self.assertTrue(
                any("METHOD_ADOPTION_ALIAS" in error for error in report.errors)
            )

    def test_legacy_v1_nonnull_commit_cannot_bypass_method_byte_check(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md"):
                shutil.copy2(REPOSITORY_ROOT / "method-paper" / name, method_root / name)
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(REPOSITORY_ROOT / "catalog" / name, catalog_root / name)
            document = json.loads(
                (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                    encoding="utf-8"
                )
            )
            document["schema_version"] = registry.LEGACY_METHOD_INDEX_SCHEMA
            document["versions"] = [document["versions"][0]]
            version = document["versions"][0]
            version["status"] = "draft"
            version.pop("study_eligible")
            version.pop("adoption_eligible")
            version["source_commit"] = "1" * 40
            version["content_sha256"] = "sha256:" + ("f" * 64)
            write_json(method_root / "VERSIONS.json", document)

            report, versions = registry.validate_method_index(
                method_root / "VERSIONS.json"
            )
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("METHOD_FILE_HASH" in error for error in report.errors),
                report.errors,
            )

    def test_v2_method_source_commit_rejects_tree_object_id(self) -> None:
        document = json.loads(
            (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        tree_oid = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md"):
                shutil.copy2(REPOSITORY_ROOT / "method-paper" / name, method_root / name)
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(REPOSITORY_ROOT / "catalog" / name, catalog_root / name)
            document["versions"][0]["source_commit"] = tree_oid
            write_json(method_root / "VERSIONS.json", document)

            report, versions = registry.validate_method_index(
                method_root / "VERSIONS.json"
            )
            self.assertFalse(report.ok)
            self.assertEqual(versions, [])
            self.assertTrue(
                any("THEORY_SOURCE_GIT" in error for error in report.errors),
                report.errors,
            )

    def test_method_provenance_catalog_requires_exact_resolved_joins(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
            temporary_root = Path(temporary)
            method_root = temporary_root / "method-paper"
            catalog_root = temporary_root / "catalog"
            method_root.mkdir()
            catalog_root.mkdir()
            for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                shutil.copy2(REPOSITORY_ROOT / "method-paper" / name, method_root / name)
            for name in ("CLAIMS.json", "SOURCES.json", "EVIDENCE-INDEX.json"):
                shutil.copy2(REPOSITORY_ROOT / "catalog" / name, catalog_root / name)

            claims_path = catalog_root / "CLAIMS.json"
            claims = json.loads(claims_path.read_text(encoding="utf-8"))
            claims["claims"].append(dict(claims["claims"][0]))
            write_json(claims_path, claims)
            evidence_path = catalog_root / "EVIDENCE-INDEX.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["bindings"].pop()
            evidence["bindings"][0]["source_ids"] = ["missing-source"]
            write_json(evidence_path, evidence)

            report, _ = registry.validate_method_index(method_root / "VERSIONS.json")
            self.assertFalse(report.ok)
            self.assertTrue(
                any("DUPLICATE_METHOD_CLAIM" in error for error in report.errors)
            )
            self.assertTrue(
                any("METHOD_BINDING_SOURCE" in error for error in report.errors)
            )
            self.assertTrue(any("ORPHAN_METHOD_CLAIM" in error for error in report.errors))
            self.assertEqual(
                report.facts["method_provenance_join_status"], "invalid"
            )

    def test_method_provenance_catalogs_must_each_be_non_empty(self) -> None:
        catalog_map = {
            "CLAIMS.json": "claims",
            "SOURCES.json": "sources",
            "EVIDENCE-INDEX.json": "bindings",
        }
        for filename, collection in catalog_map.items():
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as temporary:
                    temporary_root = Path(temporary)
                    method_root = temporary_root / "method-paper"
                    catalog_root = temporary_root / "catalog"
                    method_root.mkdir()
                    catalog_root.mkdir()
                    for name in ("METHOD.md", "SCOPE-DATUM.md", "VERSIONS.json"):
                        shutil.copy2(
                            REPOSITORY_ROOT / "method-paper" / name,
                            method_root / name,
                        )
                    for name in catalog_map:
                        shutil.copy2(
                            REPOSITORY_ROOT / "catalog" / name,
                            catalog_root / name,
                        )
                    target = catalog_root / filename
                    document = json.loads(target.read_text(encoding="utf-8"))
                    document[collection] = []
                    write_json(target, document)
                    report, _ = registry.validate_method_index(
                        method_root / "VERSIONS.json"
                    )
                    self.assertFalse(report.ok)
                    self.assertEqual(
                        report.facts["method_provenance_join_status"], "invalid"
                    )

    def test_pinned_v1_repository_source_uses_path_at_that_commit(self) -> None:
        sources = json.loads(
            (REPOSITORY_ROOT / "catalog" / "SOURCES.json").read_text(encoding="utf-8")
        )["sources"]
        source = next(
            item for item in sources if item["source_id"] == "charting-loop-repository-v1"
        )
        self.assertEqual(source["commit"], "177ab03baa8d03ce77bbc0bd823fe4198e0ec076")
        self.assertEqual(source["path"], "templates/corridor/CORRIDOR.json")


class TheoryValidationTests(unittest.TestCase):
    def test_legacy_v1_catalog_remains_readable_without_v2_publication_fields(self) -> None:
        current = json.loads(
            (REPOSITORY_ROOT / "theory" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        drafting = json.loads(json.dumps(current["artifacts"][1]))
        drafting.pop("provenance_role")
        drafting.pop("publication")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "VERSIONS.json"
            write_json(
                path,
                {
                    "schema_version": registry.LEGACY_THEORY_INDEX_SCHEMA,
                    "artifacts": [drafting],
                },
            )
            report, versions = registry.validate_theory_index(path)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(len(versions), 1)
            self.assertEqual(
                report.facts["schema_version"],
                registry.LEGACY_THEORY_INDEX_SCHEMA,
            )
            self.assertEqual(report.facts["published_primary_count"], 0)

    def test_checked_in_public_v1_and_drafting_roles_are_exact(self) -> None:
        report, versions = registry.validate_theory_index(
            REPOSITORY_ROOT / "theory" / "VERSIONS.json"
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["schema_version"], registry.THEORY_INDEX_SCHEMA)
        self.assertEqual(report.facts["published_primary_count"], 1)
        self.assertEqual(
            report.facts["published_theory_record_doi"],
            "10.5281/zenodo.21844624",
        )
        published = next(
            item for item in versions if item["version_id"] == "zenodo-v1"
        )
        self.assertEqual(published["provenance_role"], "published-primary")
        self.assertEqual(
            published["source"]["commit"],
            "cf5ac479e208a2401b9358527d58df48e22c0670",
        )
        drafting = next(
            item
            for item in versions
            if item["version_id"] == "internal-v5-arxiv-initial"
        )
        self.assertEqual(drafting["provenance_role"], "consulted-drafting")
        self.assertIsNone(drafting["publication"])

    def test_public_v1_identity_and_bytes_drift_are_rejected(self) -> None:
        original = json.loads(
            (REPOSITORY_ROOT / "theory" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        cases = ("doi", "version", "digest")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                document = json.loads(json.dumps(original))
                published = document["artifacts"][0]
                if case == "doi":
                    published["publication"]["record_doi"] = (
                        "10.5281/zenodo.99999999"
                    )
                elif case == "version":
                    published["publication"]["version"] = "v2"
                else:
                    published["representations"][0]["sha256"] = TEST_DIGEST
                path = Path(directory) / "VERSIONS.json"
                write_json(path, document)
                report, _ = registry.validate_theory_index(path)
                self.assertFalse(report.ok)
                expected_code = (
                    "THEORY_PUBLICATION_IDENTITY"
                    if case in {"doi", "version"}
                    else "THEORY_PUBLICATION_BYTES"
                )
                self.assertTrue(
                    any(expected_code in error for error in report.errors),
                    report.errors,
                )

    def test_malformed_v2_identity_fields_are_invalid_not_exceptions(self) -> None:
        original = json.loads(
            (REPOSITORY_ROOT / "theory" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        mutations: list[tuple[str, object]] = [
            ("schema_version", []),
            ("schema_version", {}),
        ]
        for field in ("kind", "path", "git_blob_sha1", "sha256"):
            mutations.extend(((field, []), (field, {})))

        for field, value in mutations:
            with self.subTest(field=field, value_type=type(value).__name__):
                document = json.loads(json.dumps(original))
                if field == "schema_version":
                    document[field] = value
                else:
                    document["artifacts"][0]["representations"][0][field] = value
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "VERSIONS.json"
                    write_json(path, document)
                    report, versions = registry.validate_theory_index(path)
                self.assertFalse(report.ok)
                self.assertFalse(
                    any(
                        version.get("version_id") == "zenodo-v1"
                        for version in versions
                    )
                )

    def test_local_git_resolver_recomputes_cataloged_theory_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "test@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Test Runner"],
                check=True,
            )
            paper = source / "paper.md"
            paper.write_text("frozen theory bytes\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "paper.md"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-q", "-m", "freeze theory"],
                check=True,
            )
            commit = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip()
            blob = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", f"{commit}:paper.md"],
                text=True,
            ).strip()
            subprocess.run(
                ["git", "-C", str(source), "tag", "theory-v1", commit], check=True
            )
            versions = [
                {
                    "version_id": "test-drafting-v1",
                    "artifact_id": "test-theory",
                    "version_labels": {"internal": "v1"},
                    "provenance_role": "consulted-drafting",
                    "publication": None,
                    "source": {
                        "repository_id": "source",
                        "repository_url": None,
                        "commit": commit,
                        "tag": "theory-v1",
                        "tag_signature": "unverified",
                    },
                    "representations": [
                        {
                            "kind": "markdown",
                            "path": "paper.md",
                            "git_blob_sha1": blob,
                            "sha256": registry.sha256_file(paper),
                        }
                    ],
                    "notes": ["Synthetic resolver fixture."],
                }
            ]
            report = registry.Report(subject=str(source))
            registry.validate_theory_source_checkout(source, versions, report)
            self.assertTrue(report.ok, report.errors)
            self.assertEqual(report.facts["resolved_representation_count"], 1)

    def test_tree_digest_binds_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "run.sh"
            script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            script.chmod(0o644)
            regular_digest, regular_records = registry.hash_tree(root)
            script.chmod(0o755)
            executable_digest, executable_records = registry.hash_tree(root)
            self.assertNotEqual(regular_digest, executable_digest)
            self.assertEqual(regular_records[0]["mode"], "100644")
            self.assertEqual(executable_records[0]["mode"], "100755")


class RegistryValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "registry"
        (self.root / "runs").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_candidate_v2_is_not_a_legacy_registry_entry(self) -> None:
        entry = valid_registry_entry()
        entry["schema_version"] = registry.CANDIDATE_SCHEMA
        write_json(self.root / "runs" / "run-001.json", entry)
        report, entries = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertEqual(entries, [])
        self.assertTrue(any("SCHEMA_VERSION" in error for error in report.errors))

    def test_valid_entry_builds_deterministic_comparison_index(self) -> None:
        entry = valid_registry_entry()
        write_json(self.root / "runs" / "run-001.json", entry)
        report, entries = registry.collect_registry(self.root)
        self.assertTrue(report.ok, report.errors)
        first = registry.build_index_documents(entries)
        second = registry.build_index_documents(reversed(entries))
        self.assertEqual(first, second)
        index = json.loads(first[0])
        self.assertEqual(index["entries"][0]["scenario_pass_count"], 6)
        self.assertRegex(index["entries"][0]["comparison_key"], r"^sha256:[0-9a-f]{64}$")

    def test_duplicate_run_ids_are_rejected(self) -> None:
        first = valid_registry_entry("same-run")
        second = valid_registry_entry("same-run")
        second["entry_id"] = "another-entry"
        write_json(self.root / "runs" / "one.json", first)
        write_json(self.root / "runs" / "two.json", second)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(any("DUPLICATE_RUN" in error for error in report.errors))

    def test_evaluated_run_must_include_every_scenario(self) -> None:
        entry = valid_registry_entry()
        del entry["evaluation_summary"]["scenarios"]["S6"]
        write_json(self.root / "runs" / "run-001.json", entry)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(any("SCENARIOS" in error for error in report.errors))

    def test_authority_effect_key_omits_run_local_assignment(self) -> None:
        first = valid_registry_entry("authority-a")
        second = valid_registry_entry("authority-b")
        for entry in (first, second):
            entry["experiment"]["comparison_intent"] = "authority-effect"
        second["authority_evidence"]["input_condition"] = "standardized-interactive"
        second["authority_evidence"]["condition_protocol_sha256"] = (
            "sha256:" + ("b" * 64)
        )
        second["authority_evidence"]["assignment_sha256"] = (
            "sha256:" + ("c" * 64)
        )
        self.assertEqual(
            registry._comparison_key(first), registry._comparison_key(second)
        )
        second["authority_evidence"]["boundary_design_sha256"] = (
            "sha256:" + ("d" * 64)
        )
        self.assertNotEqual(
            registry._comparison_key(first), registry._comparison_key(second)
        )

    def test_system_effect_key_uses_content_not_bundle_identity(self) -> None:
        first = valid_registry_entry("system-a")
        second = valid_registry_entry("system-b")
        for entry in (first, second):
            entry["experiment"]["comparison_intent"] = "system-effect"
            entry["experiment"]["knowledge_arm"] = "not-applicable"
        first["experiment"]["system_condition"] = "corridor"
        second["experiment"]["system_condition"] = "no-corridor"
        second["experiment"]["input_bundle_sha256"] = "sha256:" + ("b" * 64)
        self.assertEqual(
            registry._comparison_key(first), registry._comparison_key(second)
        )
        second["experiment"]["treatment_inputs_sha256"] = (
            "sha256:" + ("c" * 64)
        )
        self.assertNotEqual(
            registry._comparison_key(first), registry._comparison_key(second)
        )

    def test_malformed_nested_registry_object_is_reported_not_raised(self) -> None:
        write_json(
            self.root / "runs" / "malformed.json",
            {
                "schema_version": registry.REGISTRY_SCHEMA,
                "entry_id": "malformed",
                "run_id": "malformed",
                "status": {},
                "experiment": [],
            },
        )
        report, entries = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertEqual(entries, [])

    def test_malformed_scenario_status_is_reported_not_raised(self) -> None:
        entry = valid_registry_entry()
        entry["evaluation_summary"]["scenarios"]["S1"] = []
        write_json(self.root / "runs" / "malformed-scenario.json", entry)
        report, entries = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertEqual(entries, [])

    def test_conflicting_digest_for_same_provenance_is_rejected(self) -> None:
        first = valid_registry_entry("provenance-a")
        second = valid_registry_entry("provenance-b")
        second["source"] = dict(first["source"])
        second["artifact_tree_sha256"] = "sha256:" + ("b" * 64)
        write_json(self.root / "runs" / "one.json", first)
        write_json(self.root / "runs" / "two.json", second)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(any("CONFLICTING_ARTIFACT" in error for error in report.errors))

    def test_public_complete_rejects_any_redacted_interaction(self) -> None:
        entry = valid_registry_entry()
        entry["authority_evidence"]["redacted_interaction_count"] = 1
        write_json(self.root / "runs" / "run-001.json", entry)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(
            any("AUTHORITY_PUBLICATION_STATUS" in error for error in report.errors)
        )

    def test_diagnosis_assessment_ids_cannot_be_reused(self) -> None:
        entry = valid_registry_entry()
        for scenario_id in registry.SCENARIO_IDS:
            entry["evaluation_summary"]["diagnoses"][scenario_id]["subject"][
                "assessment_id"
            ] = "reused-subject"
        entry["evaluation_summary"]["diagnoses_sha256"] = registry.sha256_json_value(
            entry["evaluation_summary"]["diagnoses"]
        )
        write_json(self.root / "runs" / "run-001.json", entry)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(any("DUPLICATE_ASSESSMENT" in error for error in report.errors))

    def test_diagnosis_roles_must_identify_ai_subject_and_human_evaluator(self) -> None:
        entry = valid_registry_entry()
        entry["evaluation_summary"]["diagnoses"]["S1"]["subject"][
            "actor_type"
        ] = "human"
        entry["evaluation_summary"]["diagnoses_sha256"] = registry.sha256_json_value(
            entry["evaluation_summary"]["diagnoses"]
        )
        write_json(self.root / "runs" / "run-001.json", entry)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(any("DIAGNOSIS_ACTOR" in error for error in report.errors))

    def test_execution_fidelity_is_not_accepted_as_a_drift_factor(self) -> None:
        report = registry.Report(subject="diagnosis")
        registry._validate_registry_diagnosis(
            {
                "actor_id": "test-builder",
                "actor_type": "ai",
                "theory_version_id": None,
                "verdict": "drift",
                "classification_status": "classified",
                "failure_factors": ["X"],
            },
            report,
            "diagnosis",
        )
        self.assertFalse(report.ok)
        self.assertTrue(any("FAILURE_FACTORS" in error for error in report.errors))

    def test_methodology_provenance_does_not_claim_theory_exposure(self) -> None:
        entry = valid_registry_entry()
        entry["experiment"]["knowledge_arm"] = "methodology"
        entry["methodology_ref"] = {
            "artifact_id": "corridor-method",
            "derived_from_theory_version_id": "analysis-v1",
            "source_commit": COMMIT,
            "content_sha256": TEST_DIGEST,
        }
        write_json(self.root / "runs" / "run-001.json", entry)
        report, _ = registry.collect_registry(self.root)
        self.assertTrue(report.ok, report.errors)

        entry["theory_ref"] = dict(entry["analysis_theory_ref"])
        write_json(self.root / "runs" / "run-001.json", entry)
        report, _ = registry.collect_registry(self.root)
        self.assertFalse(report.ok)
        self.assertTrue(any("KNOWLEDGE_REF_MATRIX" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()
