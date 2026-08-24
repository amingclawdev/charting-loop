from __future__ import annotations

import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from corridor_kit import (
    ACCEPTANCE_SCHEMA,
    AUTHORING_SCHEMA,
    CAPABILITY_SCHEMA,
    FACT_CANDIDATES_SCHEMA,
    EXECUTION_TEST_CONTRACT_SCHEMA,
    EXECUTION_TEST_QA_ASSESSMENT_SCHEMA,
    EXECUTION_TEST_RECEIPT_SCHEMA,
    KIT_VERSION,
    WITNESSES_SCHEMA,
    WORK_BACKLOG_SCHEMA,
    CorridorKitError,
    GraphBuildSession,
    append_admitted_facts,
    append_graph_record,
    append_position_event,
    counterfactual_transition,
    capture_command,
    compile_typed_rule_ir,
    create_scaffold,
    freeze_submission,
    graph_doctor,
    initialize_graph,
    load_graph_index,
    list_submissions,
    public_world_inventory,
    project_witness_obligation_templates,
    query_graph,
    regular_tree_manifest,
    replay_graph,
    restore_submission,
    runtime_guide,
    semantic_edge_id,
    sha256_bytes,
    sha256_json,
    starter_witnesses,
    validate_acceptance_file,
    validate_acceptance_ledger,
    validate_authoring_directory,
    validate_capability_registry,
    validate_fact_candidates,
    validate_work_backlog,
    validate_work_files,
    validate_witnesses,
    verify_submission,
)
from corridor_kit.domain.binary import (
    binary_diff,
    binary_replay_record,
    builtin_binary_registry,
    elf_inventory,
)
from corridor_kit.runtime import load_position_timeline, project_position
from corridor_kit.core import MAX_JSON_BYTES, load_json
from corridor_kit.acceptance import qa_assessment_decision
from corridor_kit.runtime import validate_qa_assessment_path
from corridor_kit.scaffold import validate_method_capsule
from corridor_kit.graph import freeze_rule_candidate, ratify_rule_candidate


def valid_ledger() -> dict[str, object]:
    obligations = {
        "positive": ["success witness"],
        "negative": ["rejection witness"],
        "boundary": ["limit witness"],
        "state": ["before/after witness"],
        "temporal": ["ordering witness"],
        "coupled": ["joint-rule witness"],
    }
    return {
        "schema_version": ACCEPTANCE_SCHEMA,
        "coverage": {
            "status": "complete",
            "unmapped_clauses": [],
            "ambiguous_clauses": [],
        },
        "construction_readiness": {
            "status": "ready",
            "coupled_acceptance_ids": ["AC-1", "AC-2"],
            "replay_entrypoint": "python3 task_adapter.py check",
            "unresolved_constraints": [],
        },
        "items": [
            {
                "acceptance_id": "AC-1",
                "source_ref": "instruction#requirement-1",
                "statement": "The first public requirement is satisfied.",
                "required": True,
                "definition_state": "defined",
                "scope": {"kind": "whole-task"},
                "rule": {"predicate": "first_requirement_holds"},
                "relations": [{"type": "requires", "target_id": "AC-2"}],
                "verification_obligations": obligations,
            },
            {
                "acceptance_id": "AC-2",
                "source_ref": "specification#requirement-2",
                "statement": "The second public requirement is satisfied.",
                "required": True,
                "definition_state": "defined",
                "scope": {"kind": "whole-task"},
                "rule": {"predicate": "second_requirement_holds"},
                "relations": [],
                "verification_obligations": obligations,
            },
        ],
    }


def valid_capabilities() -> dict[str, object]:
    return builtin_binary_registry()


def valid_work_backlog() -> dict[str, object]:
    return {
        "schema_version": WORK_BACKLOG_SCHEMA,
        "state": "compiled",
        "acceptance_ledger_digest": sha256_json(valid_ledger()),
        "rows": [
            {
                "row_id": "ROW-1",
                "title": "Establish the second requirement",
                "acceptance_ids": ["AC-2"],
                "depends_on": [],
                "scope": {"kind": "whole-task"},
                "done_when": ["AC-2 has replayable evidence."],
                "capability_ids": ["binary.elf-inventory"],
                "reminders": [
                    {
                        "reminder_id": "REM-1",
                        "when": "before_complete",
                        "message": "Replay the read-only inventory before completing.",
                        "acceptance_ids": ["AC-2"],
                    }
                ],
            },
            {
                "row_id": "ROW-2",
                "title": "Establish the first requirement",
                "acceptance_ids": ["AC-1"],
                "depends_on": ["ROW-1"],
                "scope": {"kind": "whole-task"},
                "done_when": ["AC-1 has replayable evidence."],
                "capability_ids": ["binary.diff-ranges"],
                "reminders": [
                    {
                        "reminder_id": "REM-2",
                        "when": "before_mutation",
                        "message": "Compare the exact before and candidate bytes.",
                        "acceptance_ids": ["AC-1"],
                    }
                ],
            },
        ],
    }


class AcceptanceLedgerTests(unittest.TestCase):
    def test_valid_complete_ready_ledger(self) -> None:
        report = validate_acceptance_ledger(valid_ledger())
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(report.facts["task_ready"])
        self.assertEqual(report.facts["required_acceptance_ids"], ["AC-1", "AC-2"])

    def test_all_items_need_all_behavioral_verification_partitions(self) -> None:
        ledger = valid_ledger()
        ledger["items"][0]["verification_obligations"]["negative"] = []
        report = validate_acceptance_ledger(ledger)
        self.assertIn(
            "VERIFICATION_OBLIGATION_REQUIRED",
            {item["code"] for item in report.errors},
        )

        ledger = valid_ledger()
        ledger["items"][0]["required"] = False
        ledger["items"][0]["verification_obligations"]["negative"] = []
        report = validate_acceptance_ledger(ledger)
        self.assertIn(
            "VERIFICATION_OBLIGATION_REQUIRED",
            {item["code"] for item in report.errors},
        )

    def test_aliases_and_unknown_targets_are_rejected(self) -> None:
        ledger = valid_ledger()
        ledger["schema"] = ledger.pop("schema_version")
        relation = ledger["items"][0]["relations"][0]
        relation["target_acceptance_id"] = relation.pop("target_id")
        report = validate_acceptance_ledger(ledger)
        codes = {error["code"] for error in report.errors}
        self.assertIn("EXACT_FIELDS_REQUIRED", codes)
        self.assertIn("SCHEMA_VERSION", codes)
        self.assertIn("NONEMPTY_STRING_REQUIRED", codes)

    def test_ready_requires_complete_coverage_and_replay(self) -> None:
        ledger = valid_ledger()
        ledger["coverage"] = {
            "status": "incomplete",
            "unmapped_clauses": [
                {"source_ref": "spec#x", "statement": "x", "reason": "not mapped"}
            ],
            "ambiguous_clauses": [],
        }
        ledger["construction_readiness"]["replay_entrypoint"] = ""
        report = validate_acceptance_ledger(ledger)
        codes = {error["code"] for error in report.errors}
        self.assertIn("READY_REPLAY_ENTRYPOINT_REQUIRED", codes)
        self.assertIn("READY_REQUIRES_COMPLETE_COVERAGE", codes)

    def test_mapped_ambiguity_is_not_an_unmapped_clause(self) -> None:
        ledger = valid_ledger()
        ledger["coverage"]["ambiguous_clauses"] = [
            {
                "source_ref": "specification#requirement-2",
                "statement": "The second requirement uses an undefined threshold.",
                "reason": "The public source does not define the threshold.",
            }
        ]
        ledger["items"][1]["definition_state"] = "ambiguous"
        ledger["construction_readiness"] = {
            "status": "unresolved",
            "coupled_acceptance_ids": ["AC-1", "AC-2"],
            "replay_entrypoint": "",
            "unresolved_constraints": ["AC-2 threshold is undefined"],
        }

        report = validate_acceptance_ledger(ledger)

        self.assertTrue(report.ok, report.errors)
        self.assertEqual("complete", report.facts["source_mapping_status"])
        self.assertTrue(report.facts["source_mapping_complete"])
        self.assertEqual("incomplete", report.facts["definition_closure_status"])
        self.assertFalse(report.facts["definition_closure_complete"])
        self.assertFalse(report.facts["task_ready"])

    def test_ready_requires_definition_closure(self) -> None:
        ledger = valid_ledger()
        ledger["coverage"]["ambiguous_clauses"] = [
            {
                "source_ref": "instruction#requirement-1",
                "statement": "The first requirement has two possible meanings.",
                "reason": "The public wording is ambiguous.",
            }
        ]
        ledger["items"][0]["definition_state"] = "ambiguous"

        report = validate_acceptance_ledger(ledger)

        self.assertIn(
            "READY_REQUIRES_DEFINITION_CLOSURE",
            {error["code"] for error in report.errors},
        )

    def test_duplicate_json_keys_and_symlink_inputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema_version":"one","schema_version":"two"}')
            report = validate_acceptance_file(duplicate)
            self.assertFalse(report.ok)
            self.assertEqual(report.errors[0]["code"], "JSON_INPUT")

            target = root / "target.json"
            target.write_text(json.dumps(valid_ledger()))
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaises(CorridorKitError):
                load_json(link)


class ScaffoldTests(unittest.TestCase):
    def test_scaffold_is_atomic_task_neutral_and_honestly_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = create_scaffold(root / "first")
            second = create_scaffold(root / "second")
            draft = validate_acceptance_file(
                first / "ACCEPTANCE.json", allow_draft=True
            )
            final = validate_acceptance_file(first / "ACCEPTANCE.json")
            self.assertTrue(draft.ok, draft.errors)
            self.assertFalse(draft.facts["task_ready"])
            self.assertEqual(draft.facts["coverage_status"], "incomplete")
            self.assertEqual(draft.facts["construction_readiness_status"], "unresolved")
            self.assertFalse(final.ok)
            self.assertIn("ITEMS_NONEMPTY", {item["code"] for item in final.errors})
            self.assertEqual(
                (first / "KIT.json").read_bytes(), (second / "KIT.json").read_bytes()
            )
            self.assertTrue((first / "WORK_ITEMS.json").is_file())
            self.assertTrue((first / "CAPABILITIES.json").is_file())
            self.assertEqual(
                load_json(first / "AUTHORING.json")["schema_version"],
                AUTHORING_SCHEMA,
            )
            self.assertEqual(
                load_json(first / "WITNESSES.json"),
                starter_witnesses(),
            )
            for name in ("AUTHORING.json", "WITNESSES.json"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            self.assertEqual(load_json(first / "KIT.json")["kit_version"], KIT_VERSION)
            generated_text = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in first.rglob("*")
                if path.is_file()
            ).lower()
            for forbidden in (
                "production-planning",
                "batched-eval-parity",
                "public-support-geo",
                "erp/mes/wms",
                "candidate writeback",
            ):
                self.assertNotIn(forbidden, generated_text)
            self.assertIn("authorizes_mutation", generated_text)
            self.assertIn("false", generated_text)
            with self.assertRaises(CorridorKitError):
                create_scaffold(first)

    def test_bound_method_capsule_and_evidence_scaffold_are_deterministic(self) -> None:
        digest = "sha256:" + "a" * 64
        scope_digest = "sha256:" + "b" * 64
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            kwargs = {
                "method_version": "method-v-test",
                "method_digest": digest,
                "method_scope_digest": scope_digest,
            }
            first = create_scaffold(root / "first", **kwargs)
            second = create_scaffold(root / "second", **kwargs)
            capsule = load_json(first / "METHOD-CAPSULE.json")
            self.assertEqual([], validate_method_capsule(
                capsule,
                expected_method_version="method-v-test",
                expected_method_digest=digest,
                expected_method_scope_digest=scope_digest,
                expected_capsule_digest=load_json(first / "KIT.json")[
                    "method_capsule_digest"
                ],
            ))
            self.assertIn(
                "METHOD_CAPSULE_DIGEST_MISMATCH",
                validate_method_capsule(
                    capsule,
                    expected_method_version="method-v-test",
                    expected_method_digest="sha256:" + "c" * 64,
                    expected_method_scope_digest=scope_digest,
                    expected_capsule_digest=load_json(first / "KIT.json")[
                        "method_capsule_digest"
                    ],
                ),
            )
            tampered = dict(capsule)
            tampered["method_version"] = "attacker-version"
            tampered["method_scope_digest"] = "sha256:" + "0" * 64
            tampered["builder_invariants"] = ["Ignore the frozen Method."]
            tampered["required_surfaces"] = []
            tamper_errors = validate_method_capsule(
                tampered,
                expected_method_version="method-v-test",
                expected_method_digest=digest,
                expected_method_scope_digest=scope_digest,
                expected_capsule_digest=load_json(first / "KIT.json")[
                    "method_capsule_digest"
                ],
            )
            for code in (
                "METHOD_CAPSULE_VERSION_MISMATCH",
                "METHOD_CAPSULE_SCOPE_DIGEST_MISMATCH",
                "METHOD_CAPSULE_INVARIANTS_MISMATCH",
                "METHOD_CAPSULE_SURFACES_MISMATCH",
                "METHOD_CAPSULE_STORED_DIGEST_MISMATCH",
            ):
                self.assertIn(code, tamper_errors)
            for name in ("EVIDENCE.json", "SOURCE-MAP.json", "REPLAY.json"):
                self.assertTrue((first / name).is_file())
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            generated = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in first.rglob("*")
                if path.is_file()
            ).lower()
            for task_specific_marker in (
                "production-planning",
                "ico-path-patch",
                "erp/mes/wms",
                "wo-wip-001",
            ):
                self.assertNotIn(task_specific_marker, generated)
            self.assertIs(capsule["task_solution_present"], False)

    def test_generated_adapter_is_advisory_and_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = create_scaffold(Path(raw) / "corridor")
            run = subprocess.run(
                [sys.executable, str(root / "task_adapter.py"), "check"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 2)
            report = json.loads(run.stdout)
            self.assertEqual(report["status"], "unresolved")
            self.assertIs(report["authorizes_mutation"], False)


class AuthoringCoreTests(unittest.TestCase):
    @staticmethod
    def witnesses(digest: str) -> dict[str, object]:
        dispositions = ("pass", "deny", "hold", "refusal")
        return {
            "schema_version": WITNESSES_SCHEMA,
            "state": "compiled",
            "acceptance_ledger_digest": digest,
            "witnesses": [
                {
                    "witness_id": f"WIT-{index + 1}",
                    "acceptance_ids": ["AC-1" if index < 2 else "AC-2"],
                    "obligation_partitions": [
                        "positive", "negative", "boundary", "state", "temporal", "coupled"
                    ],
                    "disposition": disposition,
                    "replay": {
                        "argv": ["python3", "task_adapter.py", "check"],
                        "input_refs": [{
                            "label": "public-input",
                            "ref": "public:input.json",
                            "sha256": "sha256:" + "1" * 64,
                        }],
                        "result_ref": {
                            "ref": f"evidence:witness-{index + 1}.json",
                            "sha256": "sha256:" + str(index + 2) * 64,
                        },
                        "shell": False,
                    },
                }
                for index, disposition in enumerate(dispositions)
            ],
            "boundaries": starter_witnesses()["boundaries"],
        }

    def test_bounded_witnesses_accept_all_dispositions_without_inferring_pass(self) -> None:
        digest = "sha256:" + "a" * 64
        witnesses = self.witnesses(digest)

        report = validate_witnesses(
            witnesses,
            known_acceptance_ids={"AC-1", "AC-2"},
            expected_acceptance_digest=digest,
        )

        self.assertTrue(report.ok, report.errors)
        self.assertTrue(report.facts["coverage_complete"])
        self.assertEqual(
            set(report.facts["coverage_by_disposition"]),
            {"pass", "deny", "hold", "refusal"},
        )
        self.assertIs(report.facts["pass_inferred"], False)
        self.assertEqual(report.facts["task_answer"], "not_inferred")
        self.assertEqual(
            report.facts["officially_deliverable"],
            {
                "owner": "external_evaluator",
                "authority": "external",
                "status": "not_assessed",
            },
        )

        unknown = self.witnesses(digest)
        unknown["witnesses"][0]["acceptance_ids"] = ["AC-UNKNOWN"]
        unknown["witnesses"][0]["disposition"] = "success"
        unknown["witnesses"][0]["obligation_partitions"] = ["oracle"]
        unknown["witnesses"][0]["replay"]["shell"] = True
        unknown["witnesses"][0]["replay"]["input_refs"] = []
        unknown["task_answer"] = "PASS"
        codes = {
            error["code"]
            for error in validate_witnesses(
                unknown,
                known_acceptance_ids={"AC-1", "AC-2"},
                expected_acceptance_digest=digest,
            ).errors
        }
        for code in (
            "EXACT_FIELDS_REQUIRED",
            "UNKNOWN_ACCEPTANCE_ID",
            "WITNESS_DISPOSITION",
            "UNKNOWN_OBLIGATION_PARTITION",
            "REPLAY_SHELL_FORBIDDEN",
            "INPUT_REFERENCE_REQUIRED",
        ):
            self.assertIn(code, codes)

    def test_aggregate_authoring_validation_reuses_surfaces_and_exact_joins(self) -> None:
        method_digest = "sha256:" + "a" * 64
        scope_digest = "sha256:" + "b" * 64
        with tempfile.TemporaryDirectory() as raw:
            root = create_scaffold(
                Path(raw) / "corridor",
                method_version="method-v-test",
                method_digest=method_digest,
                method_scope_digest=scope_digest,
            )
            ledger = valid_ledger()
            (root / "ACCEPTANCE.json").write_text(json.dumps(ledger))
            (root / "WORK_ITEMS.json").write_text(json.dumps(valid_work_backlog()))
            (root / "CAPABILITIES.json").write_text(json.dumps(valid_capabilities()))
            (root / "WITNESSES.json").write_text(
                json.dumps(self.witnesses(sha256_json(ledger)))
            )

            report = validate_authoring_directory(
                root,
                expected_method_version="method-v-test",
                expected_method_digest=method_digest,
                expected_method_scope_digest=scope_digest,
            )

            self.assertTrue(report["structurally_valid"], report)
            self.assertTrue(report["task_ready"], report)
            self.assertEqual(
                {join["status"] for join in report["identity_joins"]},
                {"matched"},
            )
            for surface in report["surfaces"].values():
                self.assertRegex(surface["file_sha256"], r"\Asha256:[0-9a-f]{64}\Z")
                self.assertRegex(
                    surface["canonical_json_sha256"],
                    r"\Asha256:[0-9a-f]{64}\Z",
                )
            self.assertEqual(report, validate_authoring_directory(
                root,
                expected_method_version="method-v-test",
                expected_method_digest=method_digest,
                expected_method_scope_digest=scope_digest,
            ))

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "corridor_kit",
                    "authoring",
                    "validate",
                    str(root),
                    "--expected-method-version",
                    "method-v-test",
                    "--expected-method-digest",
                    method_digest,
                    "--expected-method-scope-digest",
                    scope_digest,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["task_ready"])

    def test_aggregate_fails_closed_on_missing_malformed_symlink_and_digest_mismatch(self) -> None:
        cases = ("missing", "malformed", "symlink", "digest")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as raw:
                root = create_scaffold(Path(raw) / "corridor")
                if case == "missing":
                    (root / "WITNESSES.json").unlink()
                elif case == "malformed":
                    (root / "CAPABILITIES.json").write_text('{"schema_version":')
                elif case == "symlink":
                    authoring = root / "AUTHORING.json"
                    saved = root / "saved-authoring.json"
                    authoring.replace(saved)
                    authoring.symlink_to(saved)
                else:
                    kit = load_json(root / "KIT.json")
                    kit["method_capsule_digest"] = "sha256:" + "0" * 64
                    (root / "KIT.json").write_text(json.dumps(kit))

                report = validate_authoring_directory(root, allow_draft=True)
                self.assertFalse(report["structurally_valid"], report)
                if case == "digest":
                    self.assertIn(
                        "mismatch",
                        {join["status"] for join in report["identity_joins"]},
                    )


class QaAssessmentSemanticTests(unittest.TestCase):
    @staticmethod
    def assessment(digest: str, *, outcome: str = "pass") -> dict[str, object]:
        return {
            "schema_version": "charting-loop/corridor-qa-assessment/v3",
            "outcome": outcome,
            "summary": "Audited the complete acceptance set.",
            "corridor_digest": digest,
            "source_mapping_complete": True,
            "definition_closure_complete": True,
            "assessment_closure": "complete",
            "assessed_scope": "complete",
            "scope_limitations": [],
            "acceptance_results": [{
                "acceptance_id": "ACCEPT-1",
                "applicability": "applicable",
                "status": "pass",
                "evidence": "Observed the required behavior.",
                "replay": "Repeat the public check.",
            }],
            "unmapped_requirements": [],
            "unresolved_relations": [],
            "checks": [{
                "name": "public check",
                "status": "pass",
                "evidence": "The public check passed.",
            }],
            "witnesses": [],
        }

    @staticmethod
    def expected(digest: str) -> dict[str, object]:
        return {
            "expected_corridor_digest": digest,
            "acceptance_ledger_status": "complete",
            "expected_acceptance_ids": ["ACCEPT-1"],
            "required_acceptance_ids": ["ACCEPT-1"],
            "source_mapping_status": "complete",
            "definition_closure_status": "complete",
            "construction_readiness_status": "ready",
        }

    @staticmethod
    def freeze(digest: str) -> dict[str, object]:
        return {
            "schema_version": "charting-loop/frozen-task-corridor/v1",
            "corridor_tree_sha256": digest,
            "acceptance_ledger": {
                "status": "complete",
                "acceptance_ids": ["ACCEPT-1"],
                "required_acceptance_ids": ["ACCEPT-1"],
                "source_mapping_status": "complete",
                "definition_closure_status": "complete",
                "construction_readiness_status": "ready",
            },
        }

    def test_contradiction_normalizes_to_not_assessed_and_partial_scope_is_explicit(self) -> None:
        digest = "sha256:" + "d" * 64
        contradictory = self.assessment(digest, outcome="not_assessed")
        contradictory["definition_closure_complete"] = False
        decision = qa_assessment_decision(contradictory, **self.expected(digest))
        self.assertFalse(decision["valid"])
        self.assertEqual("not_assessed", decision["outcome"])
        self.assertFalse(decision["repair_required"])
        self.assertIn(
            "ASSESSMENT_DEFINITION_AND_CLOSURE_CONTRADICTION",
            decision["errors"],
        )

        partial = dict(contradictory)
        partial["assessed_scope"] = "partial"
        partial["scope_limitations"] = ["One public relation remains unresolved."]
        partial["unresolved_relations"] = ["ACCEPT-1 relation remains unresolved."]
        decision = qa_assessment_decision(partial, **self.expected(digest))
        self.assertTrue(decision["valid"], decision["errors"])
        self.assertEqual("not_assessed", decision["outcome"])

    def test_presubmit_path_uses_freeze_identity_and_preserves_raw_report(self) -> None:
        digest = "sha256:" + "e" * 64
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assessment_path = root / "assessment.json"
            freeze_path = root / "FREEZE.json"
            assessment_path.write_text(
                json.dumps(self.assessment(digest)), encoding="utf-8"
            )
            before = assessment_path.read_bytes()
            freeze_path.write_text(
                json.dumps(self.freeze(digest)), encoding="utf-8"
            )

            report = validate_qa_assessment_path(assessment_path, freeze_path)
            direct = qa_assessment_decision(
                self.assessment(digest), **self.expected(digest)
            )
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(direct["valid"], report["valid"])
            self.assertEqual(direct["outcome"], report["outcome"])
            self.assertEqual(direct["errors"], report["errors"])
            self.assertTrue(report["raw_preserved"])
            self.assertEqual(before, assessment_path.read_bytes())
            self.assertRegex(report["raw_sha256"], r"^sha256:[0-9a-f]{64}$")

    def test_presubmit_rejects_noncanonical_freeze_identity(self) -> None:
        digest = "sha256:" + "e" * 64
        flat_only = {
            "corridor_digest": digest,
            "acceptance_ledger_status": "complete",
            "acceptance_ids": ["ACCEPT-1"],
            "required_acceptance_ids": ["ACCEPT-1"],
            "source_mapping_status": "complete",
            "definition_closure_status": "complete",
            "construction_readiness_status": "ready",
        }
        malformed_shapes: list[object] = [
            {},
            {
                "schema_version": "charting-loop/frozen-task-corridor/v1",
                "corridor_tree_sha256": digest,
                "acceptance_ledger": [],
            },
            flat_only,
        ]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assessment_path = root / "assessment.json"
            freeze_path = root / "FREEZE.json"
            assessment_path.write_text(
                json.dumps(self.assessment(digest)), encoding="utf-8"
            )
            before = assessment_path.read_bytes()
            for freeze in malformed_shapes:
                freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
                report = validate_qa_assessment_path(assessment_path, freeze_path)
                self.assertFalse(report["valid"])
                self.assertEqual(["FREEZE_IDENTITY"], report["errors"])
                self.assertEqual("not_assessed", report["outcome"])
                self.assertFalse(report["repair_required"])
                self.assertEqual(before, assessment_path.read_bytes())

            freeze_path.write_text("{", encoding="utf-8")
            report = validate_qa_assessment_path(assessment_path, freeze_path)
            self.assertFalse(report["valid"])
            self.assertEqual(["FREEZE_IDENTITY"], report["errors"])
            self.assertEqual("not_assessed", report["outcome"])
            self.assertEqual(before, assessment_path.read_bytes())

    def test_presubmit_and_intake_share_strict_json_semantics(self) -> None:
        digest = "sha256:" + "f" * 64
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assessment_path = root / "assessment.json"
            freeze_path = root / "FREEZE.json"
            valid = json.dumps(self.assessment(digest))
            duplicated = valid[:-1] + ',"summary":"duplicate"}'
            assessment_path.write_text(duplicated, encoding="utf-8")
            freeze_path.write_text(
                json.dumps(self.freeze(digest)), encoding="utf-8"
            )

            before = assessment_path.read_bytes()
            duplicate_report = validate_qa_assessment_path(
                assessment_path, freeze_path
            )
            self.assertFalse(duplicate_report["valid"])
            self.assertEqual("not_assessed", duplicate_report["outcome"])
            self.assertFalse(duplicate_report["repair_required"])
            self.assertEqual(before, assessment_path.read_bytes())

            assessment_path.write_text(
                valid[:-1] + ',"non_finite":NaN}', encoding="utf-8"
            )
            non_finite_report = validate_qa_assessment_path(
                assessment_path, freeze_path
            )
            self.assertFalse(non_finite_report["valid"])
            self.assertEqual("not_assessed", non_finite_report["outcome"])
            self.assertRegex(
                non_finite_report["raw_sha256"], r"^sha256:[0-9a-f]{64}$"
            )

    def test_witnessed_failure_can_request_repair(self) -> None:
        digest = "sha256:" + "f" * 64
        value = self.assessment(digest, outcome="fail")
        value["acceptance_results"][0]["status"] = "fail"
        value["witnesses"] = [{
            "acceptance_id": "ACCEPT-1",
            "constraint": "The public output must retain its identity.",
            "evidence": "The observed identity changed.",
            "replay": "Read the public before/after identity.",
        }]
        decision = qa_assessment_decision(value, **self.expected(digest))
        self.assertTrue(decision["valid"], decision["errors"])
        self.assertTrue(decision["repair_required"])


class CoreMechanicsTests(unittest.TestCase):
    def test_manifest_is_sorted_deterministic_and_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "z.txt").write_text("z")
            (root / "a").mkdir()
            (root / "a" / "b.txt").write_text("b")
            first = regular_tree_manifest(root)
            second = regular_tree_manifest(root)
            self.assertEqual(first, second)
            self.assertEqual(
                [item["path"] for item in first["files"]], ["a/b.txt", "z.txt"]
            )
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "volatile.pyc").write_bytes(os.urandom(16))
            self.assertEqual(first, regular_tree_manifest(root))
            (root / "z.txt").write_text("changed")
            self.assertNotEqual(first["tree_digest"], regular_tree_manifest(root)["tree_digest"])
            (root / "unsafe").symlink_to(root / "z.txt")
            with self.assertRaises(CorridorKitError):
                regular_tree_manifest(root)

    def test_public_world_inventory_uses_labels_not_host_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "one.txt").write_text("one")
            specification = root / "SPEC.md"
            specification.write_text("rules")
            inventory = public_world_inventory(
                {"source": source, "specification": specification}
            )
            encoded = json.dumps(inventory, sort_keys=True)
            self.assertNotIn(raw, encoded)
            self.assertEqual(
                [item["source_id"] for item in inventory["sources"]],
                ["source", "specification"],
            )

    def test_capture_does_not_interpret_shell_metacharacters(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            sentinel = root / "must-not-exist"
            literal = f"$(touch {sentinel}); echo injected"
            report = capture_command(
                [sys.executable, "-c", "import sys; print(sys.argv[1])", literal],
                root / "capture",
                cwd=root,
                timeout_seconds=10,
            )
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["exit_code"], 0)
            self.assertFalse(sentinel.exists())
            self.assertEqual((root / "capture" / "stdout.txt").read_text().strip(), literal)
            request = json.loads((root / "capture" / "request.json").read_text())
            self.assertIs(request["shell"], False)

    def test_runtime_code_has_no_private_or_benchmark_dependency(self) -> None:
        package = Path(__file__).resolve().parents[1] / "corridor_kit"
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in package.rglob("*.py")
        )
        self.assertNotIn("import aming_claw", source)
        self.assertNotIn("from aming_claw", source)
        self.assertNotIn("import harbor", source)
        self.assertNotIn("from harbor", source)
        self.assertNotIn("planner_service", source)
        self.assertNotIn("evalbench", source)


class WorkRowsAndRuntimeTests(unittest.TestCase):
    def test_joined_work_backlog_and_capability_registry_are_strict(self) -> None:
        capabilities = valid_capabilities()
        capability_report = validate_capability_registry(capabilities)
        self.assertTrue(capability_report.ok, capability_report.errors)
        self.assertEqual(CAPABILITY_SCHEMA, capabilities["schema_version"])
        self.assertEqual(
            {"binary.elf-inventory", "binary.diff-ranges", "binary.replay-record"},
            set(capability_report.facts["capability_ids"]),
        )

        work = valid_work_backlog()
        report = validate_work_backlog(
            work,
            acceptance_ids={"AC-1", "AC-2"},
            capability_ids=set(capability_report.facts["capability_ids"]),
        )
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(["ROW-1", "ROW-2"], report.facts["row_ids"])
        self.assertIs(report.facts["authorizes_mutation"], False)

        work["rows"][0]["depends_on"] = ["ROW-2"]
        report = validate_work_backlog(
            work,
            acceptance_ids={"AC-1", "AC-2"},
            capability_ids=set(capability_report.facts["capability_ids"]),
        )
        self.assertIn("ROW_DEPENDENCY_CYCLE", {item["code"] for item in report.errors})

    def test_file_join_rejects_dangling_capability_and_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ledger = valid_ledger()
            capabilities = valid_capabilities()
            work = valid_work_backlog()
            (root / "ACCEPTANCE.json").write_text(json.dumps(ledger))
            (root / "CAPABILITIES.json").write_text(json.dumps(capabilities))
            (root / "WORK_ITEMS.json").write_text(json.dumps(work))
            report = validate_work_files(
                root / "WORK_ITEMS.json",
                acceptance_path=root / "ACCEPTANCE.json",
                capability_path=root / "CAPABILITIES.json",
            )
            self.assertTrue(report.ok, report.errors)
            self.assertTrue(report.facts["task_ready"])

            work["rows"][0]["capability_ids"] = ["binary.unknown"]
            work["rows"][1]["acceptance_ids"] = ["AC-UNKNOWN"]
            (root / "WORK_ITEMS.json").write_text(json.dumps(work))
            report = validate_work_files(
                root / "WORK_ITEMS.json",
                acceptance_path=root / "ACCEPTANCE.json",
                capability_path=root / "CAPABILITIES.json",
            )
            codes = {item["code"] for item in report.errors}
            self.assertIn("UNKNOWN_CAPABILITY_ID", codes)
            self.assertIn("UNKNOWN_ACCEPTANCE_ID", codes)
            self.assertIn("UNBOUND_ACCEPTANCE_ID", codes)

    def test_hash_linked_timeline_projects_one_advisory_current_guide(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            timeline = Path(raw) / "POSITION.jsonl"
            work = valid_work_backlog()
            capabilities = valid_capabilities()
            first = append_position_event(
                timeline,
                actor="runner",
                event_type="run_initialized",
                status="observed",
            )
            started = append_position_event(
                timeline,
                actor="worker",
                event_type="row_started",
                status="in_progress",
                row_id="ROW-1",
            )
            self.assertEqual(first["event_hash"], started["previous_event_hash"])
            events = load_position_timeline(timeline)
            current = project_position(work, events)
            self.assertEqual("ROW-1", current["current_row_id"])

            append_position_event(
                timeline,
                actor="runner",
                event_type="row_completed",
                status="done",
                row_id="ROW-1",
                details={"evidence_ref": "artifact:row-1"},
            )
            ledger = valid_ledger()
            guide = runtime_guide(
                work, ledger, capabilities, load_position_timeline(timeline)
            )
            self.assertEqual("compiled", guide["work_state"])
            self.assertEqual("compiled", guide["capability_state"])
            self.assertEqual("ROW-2", guide["current_row"]["row_id"])
            self.assertEqual(["binary.diff-ranges"], [item["capability_id"] for item in guide["capabilities"]])
            self.assertEqual("ROW-2", guide["work_row_guidance"]["row_id"])
            self.assertEqual(
                ["binary.diff-ranges"],
                guide["work_row_guidance"]["selected_capability_ids"],
            )
            self.assertIn("REM-2", {item["reminder_id"] for item in guide["reminders"]})
            self.assertIs(guide["advisory_only"], True)
            self.assertIs(guide["authorizes_mutation"], False)
            self.assertIs(guide["blocking_gate"], False)
            self.assertEqual(
                guide["position"]["position_ref"],
                sha256_json(guide["position"]["checkpoint"]),
            )
            self.assertEqual(
                guide["position"]["position_ref"],
                guide["direction"]["base_position_ref"],
            )
            self.assertEqual(
                guide["direction"]["direction_digest"],
                guide["entrance"]["direction_digest"],
            )
            self.assertFalse(guide["direction"]["hypothetical"])

            tampered_position = json.loads(json.dumps(guide["position"]))
            tampered_position["current_row_id"] = "ROW-1"
            with self.assertRaises(CorridorKitError):
                counterfactual_transition(
                    work,
                    ledger,
                    capabilities,
                    load_position_timeline(timeline),
                    substituted_position=tampered_position,
                )

            unbound_ledger = valid_ledger()
            unbound_ledger["items"][0]["rule"] = {"predicate": "unbound_rule"}
            with self.assertRaises(CorridorKitError):
                runtime_guide(
                    work,
                    unbound_ledger,
                    capabilities,
                    load_position_timeline(timeline),
                )

            alternate_ledger = valid_ledger()
            alternate_ledger["items"][0]["rule"] = {"predicate": "alternate_rule"}
            transition = counterfactual_transition(
                work,
                ledger,
                capabilities,
                load_position_timeline(timeline),
                substituted_acceptance=alternate_ledger,
            )
            repeated = counterfactual_transition(
                work,
                ledger,
                capabilities,
                load_position_timeline(timeline),
                substituted_acceptance=alternate_ledger,
            )
            self.assertEqual(transition, repeated)
            self.assertTrue(transition["hypothetical"])
            self.assertTrue(transition["read_only"])
            for field in (
                "authorizes_mutation",
                "blocking_gate",
                "may_admit_fact",
                "may_advance_position",
                "may_mutate_acceptance",
                "may_append_timeline",
                "may_establish_authority",
                "may_establish_pass_or_closure",
            ):
                self.assertFalse(transition[field])

            with self.assertRaises(CorridorKitError):
                append_position_event(
                    timeline,
                    actor="worker",
                    event_type="row_started",
                    status="done",
                    row_id="ROW-2",
                )

    def test_runner_admits_bound_candidates_and_reprojects_direction(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            timeline = Path(raw) / "POSITION.jsonl"
            work = valid_work_backlog()
            ledger = valid_ledger()
            capabilities = valid_capabilities()
            append_position_event(
                timeline,
                actor="runner",
                event_type="row_started",
                status="in_progress",
                row_id="ROW-1",
            )
            before = runtime_guide(
                work, ledger, capabilities, load_position_timeline(timeline)
            )
            timeline_bytes_before_admission = timeline.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "validated runner admission"):
                append_position_event(
                    timeline,
                    actor="runner",
                    event_type="facts_admitted",
                    status="admitted",
                    row_id="ROW-1",
                    details={},
                )
            self.assertEqual(timeline_bytes_before_admission, timeline.read_bytes())

            duplicate_timeline = Path(raw) / "DUPLICATE-POSITION.jsonl"
            duplicate_line = timeline.read_text(encoding="utf-8").rstrip("\n").replace(
                '"actor":"runner"',
                '"actor":"runner","actor":"runner"',
                1,
            )
            duplicate_timeline.write_text(duplicate_line + "\n", encoding="utf-8")
            duplicate_bytes = duplicate_timeline.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "duplicate timeline JSON key"):
                load_position_timeline(duplicate_timeline)
            with self.assertRaisesRegex(CorridorKitError, "duplicate timeline JSON key"):
                append_position_event(
                    duplicate_timeline,
                    actor="runner",
                    event_type="row_progress",
                    status="in_progress",
                    row_id="ROW-1",
                )
            self.assertEqual(duplicate_bytes, duplicate_timeline.read_bytes())

            corridor_digest = "sha256:" + "c" * 64
            candidate_ref = "worker-snapshot-0001"
            value = {
                "schema_version": FACT_CANDIDATES_SCHEMA,
                "candidates": [{
                    "candidate_id": "OBS-1",
                    "role": "worker",
                    "corridor_digest": corridor_digest,
                    "position_ref": before["position"]["position_ref"],
                    "row_id": "ROW-1",
                    "acceptance_id": "AC-2",
                    "obligation_partition": "negative",
                    "observation": "The invalid candidate was rejected.",
                    "source_ref": "public:task#requirement-2",
                    "witness_ref": "evidence:negative-1",
                    "replay_ref": "replay:negative-1",
                    "candidate_ref": candidate_ref,
                }],
            }
            report = validate_fact_candidates(
                value,
                work=work,
                acceptance=ledger,
                expected_corridor_digest=corridor_digest,
                expected_position_ref=before["position"]["position_ref"],
                expected_role="worker",
                expected_candidate_ref=candidate_ref,
            )
            self.assertTrue(report.ok, report.errors)
            admitted = append_admitted_facts(
                timeline,
                actor="runner",
                candidates=value,
                work=work,
                acceptance=ledger,
                expected_corridor_digest=corridor_digest,
                expected_position_ref=before["position"]["position_ref"],
                expected_role="worker",
                expected_candidate_ref=candidate_ref,
            )
            self.assertEqual(1, admitted["admitted"])
            after = runtime_guide(
                work, ledger, capabilities, load_position_timeline(timeline)
            )
            self.assertNotEqual(
                before["direction"]["direction_digest"],
                after["direction"]["direction_digest"],
            )
            self.assertEqual(
                before["direction"]["rule_closure_digest"],
                after["direction"]["rule_closure_digest"],
            )
            self.assertEqual(1, len(after["position"]["current_row_facts"]))
            self.assertIn(
                {"acceptance_id": "AC-2", "partition": "positive"},
                after["direction"]["witness_gaps"],
            )
            self.assertEqual(
                admitted["event"]["event_hash"],
                after["position"]["current_row_facts"][0]["admission_event_hash"],
            )

            timeline_bytes = timeline.read_bytes()
            replayed = append_admitted_facts(
                timeline,
                actor="runner",
                candidates=value,
                work=work,
                acceptance=ledger,
                expected_corridor_digest=corridor_digest,
                expected_position_ref=before["position"]["position_ref"],
                expected_role="worker",
                expected_candidate_ref=candidate_ref,
            )
            self.assertEqual(0, replayed["admitted"])
            self.assertTrue(replayed["idempotent"])
            self.assertEqual(timeline_bytes, timeline.read_bytes())

            with self.assertRaises(CorridorKitError):
                append_admitted_facts(
                    timeline,
                    actor="worker",
                    candidates=value,
                    work=work,
                    acceptance=ledger,
                    expected_corridor_digest=corridor_digest,
                    expected_position_ref=before["position"]["position_ref"],
                    expected_role="worker",
                    expected_candidate_ref=candidate_ref,
                )

            forged_timeline = Path(raw) / "FORGED-POSITION.jsonl"
            forged_events = load_position_timeline(timeline)
            forged_events[-1]["actor"] = "worker"
            unsigned = {
                key: value
                for key, value in forged_events[-1].items()
                if key != "event_hash"
            }
            forged_events[-1]["event_hash"] = sha256_json(unsigned)
            forged_timeline.write_text(
                "".join(
                    json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
                    for event in forged_events
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CorridorKitError, "invalid runner identity"):
                runtime_guide(
                    work,
                    ledger,
                    capabilities,
                    load_position_timeline(forged_timeline),
                )
            self.assertEqual(timeline_bytes, timeline.read_bytes())

            stale = json.loads(json.dumps(value))
            stale["candidates"][0]["candidate_id"] = "OBS-2"
            with self.assertRaises(CorridorKitError):
                append_admitted_facts(
                    timeline,
                    actor="runner",
                    candidates=stale,
                    work=work,
                    acceptance=ledger,
                    expected_corridor_digest=corridor_digest,
                    expected_position_ref=before["position"]["position_ref"],
                    expected_role="worker",
                    expected_candidate_ref=candidate_ref,
                )


class BinaryCapabilityTests(unittest.TestCase):
    @staticmethod
    def _elf_bytes() -> bytes:
        identity = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\0" * 8
        header = struct.pack(
            "<HHIQQQIHHHHHH",
            2,
            62,
            1,
            0x400000,
            64,
            0,
            0,
            64,
            56,
            0,
            64,
            0,
            0,
        )
        return identity + header

    def test_binary_pack_is_read_only_task_neutral_and_replayable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            before = root / "before"
            after = root / "after"
            before.write_bytes(self._elf_bytes())
            changed = bytearray(self._elf_bytes())
            changed[-1] = 1
            after.write_bytes(changed)

            inventory = elf_inventory(before)
            self.assertEqual("x86-64", inventory["machine"])
            self.assertEqual(64, inventory["elf_class"])
            self.assertEqual("none", inventory["side_effects"])

            difference = binary_diff(before, after)
            self.assertEqual(1, difference["changed_byte_count"])
            self.assertEqual(
                [{"start": 63, "end_exclusive": 64, "length": 1}],
                difference["changed_ranges"],
            )
            replay = binary_replay_record(
                ["./check", "./program"], {"program": before}
            )
            self.assertIs(replay["shell"], False)
            self.assertEqual("not_executed", replay["side_effects"])
            self.assertRegex(replay["replay_digest"], r"^sha256:[0-9a-f]{64}$")


class SubmissionSnapshotTests(unittest.TestCase):
    def test_versions_are_monotonic_immutable_and_latest_restores(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            store = base / "store"
            output = base / "answer.bin"
            checksum = base / "answer.sha256"
            output.write_bytes(b"version-one")
            checksum.write_text("one\n", encoding="utf-8")

            first = freeze_submission(
                store, role="worker", paths=[output, checksum]
            )
            output.write_bytes(b"version-two")
            checksum.write_text("two\n", encoding="utf-8")
            second = freeze_submission(
                store, role="worker", paths=[output, checksum]
            )

            self.assertEqual(1, first["sequence"])
            self.assertEqual(2, second["sequence"])
            self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
            history = list_submissions(store, role="worker")
            self.assertEqual(
                [first["snapshot_id"], second["snapshot_id"]],
                [item["snapshot_id"] for item in history["snapshots"]],
            )

            output.write_bytes(b"unfinished-repair")
            checksum.write_text("unfinished\n", encoding="utf-8")
            restored = restore_submission(store, role="worker")
            self.assertEqual(second["snapshot_id"], restored["snapshot_id"])
            self.assertEqual(b"version-two", output.read_bytes())
            self.assertEqual("two\n", checksum.read_text(encoding="utf-8"))

            first_report = verify_submission(
                store, role="worker", snapshot_id=first["snapshot_id"]
            )
            self.assertFalse(first_report["latest"])
            first_blob = (
                store
                / "snapshots"
                / "worker"
                / first["snapshot_id"]
                / "files"
                / "0000.bin"
            )
            self.assertEqual(b"version-one", first_blob.read_bytes())

    def test_revision_telemetry_distinguishes_change_from_validation_refreeze(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            store = base / "store"
            output = base / "answer"
            output.write_text("one", encoding="utf-8")
            first = freeze_submission(store, role="worker", paths=[output])
            output.write_text("two", encoding="utf-8")
            second = freeze_submission(store, role="worker", paths=[output])
            third = freeze_submission(store, role="worker", paths=[output])

            self.assertEqual("initial", first["revision_kind"])
            self.assertEqual("content_revision", second["revision_kind"])
            self.assertEqual(1, second["content_revision_index"])
            self.assertEqual("validation_refreeze", third["revision_kind"])
            self.assertFalse(third["content_changed"])
            self.assertEqual(0, third["changed_file_count"])
            history = list_submissions(store, role="worker")["revision_progress"]
            self.assertEqual(3, history["snapshot_count"])
            self.assertEqual(2, history["checkpoint_advance_count"])
            self.assertEqual(1, history["content_revision_count"])
            self.assertEqual(1, history["validation_refreeze_count"])
            self.assertEqual(third["last_frozen_at"], history["last_frozen_at"])

    def test_corrupt_or_unsafe_snapshots_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            store = base / "store"
            output = base / "answer"
            output.write_text("safe", encoding="utf-8")
            frozen = freeze_submission(store, role="worker", paths=[output])
            blob = (
                store
                / "snapshots"
                / "worker"
                / frozen["snapshot_id"]
                / "files"
                / "0000.bin"
            )
            blob.chmod(0o600)
            blob.write_text("corrupt", encoding="utf-8")
            with self.assertRaisesRegex(CorridorKitError, "identity mismatch"):
                restore_submission(store, role="worker")

            relative = Path("relative-output")
            with self.assertRaisesRegex(CorridorKitError, "absolute"):
                freeze_submission(base / "other", role="worker", paths=[relative])

            target = base / "target"
            target.write_text("target", encoding="utf-8")
            link = base / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(CorridorKitError, "symlink"):
                freeze_submission(base / "third", role="worker", paths=[link])

    def test_latest_reference_must_exactly_match_selected_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            store = base / "store"
            output = base / "answer"
            output.write_text("complete", encoding="utf-8")
            frozen = freeze_submission(store, role="worker", paths=[output])
            latest_path = store / "latest" / "worker.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            latest["sequence"] = 99
            latest_path.write_text(json.dumps(latest), encoding="utf-8")

            with self.assertRaisesRegex(
                CorridorKitError, "latest submission reference mismatch"
            ):
                verify_submission(store, role="worker")
            with self.assertRaisesRegex(
                CorridorKitError, "latest submission reference mismatch"
            ):
                restore_submission(
                    store, role="worker", snapshot_id=frozen["snapshot_id"]
                )

    def test_restore_preflights_all_targets_before_first_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            store = base / "store"
            first = base / "first" / "answer"
            second = base / "second" / "answer"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("frozen-first", encoding="utf-8")
            second.write_text("frozen-second", encoding="utf-8")
            freeze_submission(store, role="worker", paths=[first, second])

            first.write_text("live-first", encoding="utf-8")
            second.write_text("live-second", encoding="utf-8")
            second.unlink()
            second.parent.rmdir()
            with self.assertRaisesRegex(CorridorKitError, "real directory"):
                restore_submission(store, role="worker")

            self.assertEqual("live-first", first.read_text(encoding="utf-8"))

    def test_cli_freeze_list_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            store = base / "store"
            output = base / "answer"
            output.write_text("frozen", encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "corridor_kit",
                "submission",
                "freeze",
                "--root",
                str(store),
                "--role",
                "worker",
                "--path",
                str(output),
            ]
            result = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["sequence"])
            output.write_text("unfinished", encoding="utf-8")
            restore = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "corridor_kit",
                    "submission",
                    "restore",
                    "--root",
                    str(store),
                    "--role",
                    "worker",
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, restore.returncode, restore.stderr)
            self.assertEqual("frozen", output.read_text(encoding="utf-8"))


class TypedRuleCompilerTests(unittest.TestCase):
    @staticmethod
    def _ir(*, rule_kind: str = "conditional", operators: list[str] | None = None):
        return {
            "schema_version": "charting-loop/typed-rule-ir/v1",
            "task_source_ref": "public-task:requirements",
            "task_source_digest": "sha256:" + "1" * 64,
            "method_digest": "sha256:" + "2" * 64,
            "compiler_config_digest": "sha256:" + "3" * 64,
            "rules": [
                {
                    "rule_id": "R-COVERAGE",
                    "statement": "Each declared item must satisfy both public branches.",
                    "source_ref": "public-task:requirement-1",
                    "source_digest": "sha256:" + "4" * 64,
                    "semantics": {
                        "rule_kind": rule_kind,
                        "compilation_status": "complete",
                        "compile_issues": [],
                        "quantifier": {
                            "mode": "all",
                            "subject_axis": "item",
                            "subjects": ["item-a", "item-b", "item-c"],
                        },
                        "conditions": [
                            {
                                "condition_id": "branch-open",
                                "predicate": "the item is open",
                                "expected_outcome": "the open form is preserved",
                                "required_witness_operators": operators
                                or ["equals"],
                            },
                            {
                                "condition_id": "branch-closed",
                                "predicate": "the item is closed",
                                "expected_outcome": "the closed form is preserved",
                                "required_witness_operators": operators
                                or ["equals"],
                            },
                        ],
                        "checklist_projection": {
                            "projection_mode": "per_subject",
                            "behavioral_partitions": ["positive", "boundary"],
                            "evidence_requirement": "Replay both public branches.",
                            "decision_rule": {
                                "pass": "the required operator confirms the expected outcome",
                                "fail": "the operator contradicts the expected outcome",
                                "unknown": "the operator witness is absent or unresolved",
                            },
                        },
                        "dependencies": [],
                    },
                }
            ],
        }

    @staticmethod
    def _v2_ir(*, requirement_level: str = "required") -> dict:
        clause_text = "Each public item must retain both declared branches."
        source_digest = "sha256:" + "4" * 64
        return {
            "schema_version": "charting-loop/typed-rule-ir/v2",
            "source_bundle": {
                "schema_version": "charting-loop/task-source-bundle/v1",
                "closure_status": "complete",
                "sources": [
                    {
                        "source_id": "SRC-INSTRUCTION",
                        "source_ref": "public-task:requirements",
                        "source_digest": source_digest,
                        "role": "instruction",
                        "retrieval_status": "available",
                    }
                ],
            },
            "source_clause_inventory": [
                {
                    "clause_id": "CLAUSE-001",
                    "source_id": "SRC-INSTRUCTION",
                    "clause_text": clause_text,
                    "clause_digest": sha256_bytes(clause_text.encode("utf-8")),
                    "requirement_level": requirement_level,
                    "mapping_status": "mapped",
                    "rule_ids": ["R-COVERAGE"],
                    "issue": "",
                }
            ],
            "revision": {
                "revision_id": "IR-REV-001",
                "revision_kind": "first_attempt",
                "parent_ir_digest": None,
                "qa_witness_refs": [],
            },
            "method_digest": "sha256:" + "2" * 64,
            "compiler_config_digest": "sha256:" + "3" * 64,
            "rules": [
                {
                    "rule_id": "R-COVERAGE",
                    "statement": clause_text,
                    "source_ref": "public-task:requirements",
                    "source_digest": source_digest,
                    "source_clause_ids": ["CLAUSE-001"],
                    "semantics": {
                        "schema_version": "charting-loop/typed-rule-semantics/v2",
                        "requirement_level": requirement_level,
                        "applicability": {
                            "mode": "conditional",
                            "predicate": "the public item is present",
                        },
                        "rule_kind": "conditional",
                        "compilation_status": "complete",
                        "compile_issues": [],
                        "quantifier": {
                            "mode": "all",
                            "subject_axis": "item",
                            "subjects": ["item-a", "item-b"],
                            "domain_kind": "closed_enumeration",
                            "domain_source": "public_source",
                            "domain_predicate": "the two public items named by the source",
                        },
                        "conditions": [
                            {
                                "condition_id": "branch-preservation",
                                "predicate": "the public item is present",
                                "expected_outcome": "both declared branches are retained",
                                "required_witness_operators": ["equals"],
                            }
                        ],
                        "checklist_projection": {
                            "projection_mode": "per_subject",
                            "behavioral_partitions": ["positive", "boundary"],
                            "evidence_requirement": "Replay each public item.",
                            "decision_rule": {
                                "pass": "the witness confirms both branches",
                                "fail": "the witness contradicts either branch",
                                "unknown": "the witness is absent or unresolved",
                            },
                        },
                        "dependencies": [],
                    },
                }
            ],
        }

    @staticmethod
    def _v3_ir() -> dict:
        source_one = "✓ Every item must exist. Before release, verify every item."
        source_two = "Evidence must be recorded."
        clause_one = "✓ Every item must exist."
        clause_two_a = "Before release, verify every item."
        clause_two_b = source_two

        def source_slice(
            slice_id: str, source_id: str, content: str, text: str
        ) -> dict:
            content_bytes = content.encode("utf-8")
            text_bytes = text.encode("utf-8")
            start = content_bytes.index(text_bytes)
            end = start + len(text_bytes)
            return {
                "slice_id": slice_id,
                "source_id": source_id,
                "byte_start": start,
                "byte_end": end,
                "slice_digest": sha256_bytes(text_bytes),
            }

        slices = {
            "SL-EXIST": source_slice(
                "SL-EXIST", "SRC-INSTRUCTION", source_one, clause_one
            ),
            "SL-VERIFY": source_slice(
                "SL-VERIFY", "SRC-INSTRUCTION", source_one, clause_two_a
            ),
            "SL-EVIDENCE": source_slice(
                "SL-EVIDENCE", "SRC-SPEC", source_two, clause_two_b
            ),
        }

        def semantics(*, dependency: dict | None = None) -> dict:
            return {
                "schema_version": "charting-loop/typed-rule-semantics/v3",
                "requirement_level": "required",
                "applicability": {"mode": "always", "predicate": "the task runs"},
                "rule_kind": "conditional",
                "compilation_status": "complete",
                "compile_issues": [],
                "quantifier": {
                    "mode": "all",
                    "subject_axis": "item",
                    "subjects": ["declared-items"],
                    "domain_kind": "source_defined",
                    "domain_source": "public_source",
                    "domain_predicate": "every item declared by the public sources",
                },
                "conditions": [
                    {
                        "condition_id": "public-obligation",
                        "predicate": "the item is in the source-defined domain",
                        "expected_outcome": "the declared obligation is witnessed",
                        "required_witness_operators": ["exists"],
                    }
                ],
                "checklist_projection": {
                    "projection_mode": "aggregate",
                    "behavioral_partitions": ["positive", "boundary"],
                    "evidence_requirement": "Record a replayable source-bound witness.",
                    "decision_rule": {
                        "pass": "the witness satisfies the declared outcome",
                        "fail": "the witness contradicts the declared outcome",
                        "unknown": "the witness is absent or unresolved",
                    },
                },
                "dependencies": [dependency] if dependency is not None else [],
            }

        direct_dependency = {
            "relationship": "requires",
            "target_rule_id": "R-EXIST",
            "provenance": {
                "kind": "direct",
                "source_slice_ids": ["SL-VERIFY"],
                "derivation_kind": None,
                "input_rule_provenance_digests": {},
            },
        }
        return {
            "schema_version": "charting-loop/typed-rule-ir/v3",
            "source_bundle": {
                "schema_version": "charting-loop/task-source-bundle/v2",
                "closure_status": "complete",
                "sources": [
                    {
                        "source_id": "SRC-INSTRUCTION",
                        "source_ref": "public-task:requirements",
                        "source_digest": sha256_bytes(source_one.encode("utf-8")),
                        "role": "instruction",
                        "retrieval_status": "available",
                        "content_encoding": "utf-8",
                        "content_utf8": source_one,
                    },
                    {
                        "source_id": "SRC-SPEC",
                        "source_ref": "public-task:named-spec",
                        "source_digest": sha256_bytes(source_two.encode("utf-8")),
                        "role": "authoritative_specification",
                        "retrieval_status": "available",
                        "content_encoding": "utf-8",
                        "content_utf8": source_two,
                    },
                ],
            },
            "source_clause_inventory": [
                {
                    "clause_id": "CLAUSE-EXIST",
                    "clause_order_key": "CLAUSE-ORDER-0001",
                    "source_slices": [slices["SL-EXIST"]],
                    "clause_text": clause_one,
                    "clause_digest": sha256_bytes(clause_one.encode("utf-8")),
                    "requirement_level": "required",
                    "mapping_status": "mapped",
                    "rule_ids": ["R-EXIST"],
                    "required_semantic_roles": [
                        "obligation",
                        "domain",
                        "quantifier",
                    ],
                    "issue": "",
                },
                {
                    "clause_id": "CLAUSE-VERIFY",
                    "clause_order_key": "CLAUSE-ORDER-0002",
                    "source_slices": [slices["SL-VERIFY"], slices["SL-EVIDENCE"]],
                    "clause_text": clause_two_a + clause_two_b,
                    "clause_digest": sha256_bytes(
                        (clause_two_a + clause_two_b).encode("utf-8")
                    ),
                    "requirement_level": "required",
                    "mapping_status": "mapped",
                    "rule_ids": ["R-VERIFY"],
                    "required_semantic_roles": [
                        "obligation",
                        "condition",
                        "outcome",
                        "witness_requirement",
                        "relationship",
                    ],
                    "issue": "",
                },
            ],
            "revision": {
                "revision_id": "IR-REV-V3",
                "revision_kind": "first_attempt",
                "parent_ir_digest": None,
                "qa_witness_refs": [],
            },
            "method_digest": "sha256:" + "2" * 64,
            "compiler_config_digest": "sha256:" + "3" * 64,
            "rules": [
                {
                    "rule_id": "R-EXIST",
                    "statement": clause_one,
                    "source_clause_ids": ["CLAUSE-EXIST"],
                    "source_slices": [
                        {"slice_id": "SL-EXIST", "semantic_role": "obligation"},
                        {"slice_id": "SL-EXIST", "semantic_role": "domain"},
                        {"slice_id": "SL-EXIST", "semantic_role": "quantifier"},
                    ],
                    "semantics": semantics(),
                },
                {
                    "rule_id": "R-VERIFY",
                    "statement": clause_two_a + " " + clause_two_b,
                    "source_clause_ids": ["CLAUSE-VERIFY"],
                    "source_slices": [
                        {"slice_id": "SL-VERIFY", "semantic_role": "obligation"},
                        {"slice_id": "SL-VERIFY", "semantic_role": "condition"},
                        {"slice_id": "SL-VERIFY", "semantic_role": "outcome"},
                        {"slice_id": "SL-VERIFY", "semantic_role": "relationship"},
                        {
                            "slice_id": "SL-EVIDENCE",
                            "semantic_role": "witness_requirement",
                        },
                    ],
                    "semantics": semantics(dependency=direct_dependency),
                },
            ],
        }

    @classmethod
    def _v4_ir(cls) -> dict:
        value = json.loads(json.dumps(cls._v3_ir()))
        value["schema_version"] = "charting-loop/typed-rule-ir/v4"
        legacy_sources = value["source_bundle"]["sources"]
        sources = []
        for source in legacy_sources:
            extractor_digest = "sha256:" + "5" * 64
            extraction_content = source["content_utf8"]
            artifact_digest = sha256_bytes(extraction_content.encode("utf-8"))
            sources.append(
                {
                    "source_id": source["source_id"],
                    "source_ref": source["source_ref"],
                    "plane": "normative_rule",
                    "role": source["role"],
                    "byte_status": "available",
                    "byte_digest": source["source_digest"],
                    "byte_size": len(source["content_utf8"].encode("utf-8")),
                    "media_type": "text/plain",
                    "content_encoding": "utf-8",
                    "content_utf8": source["content_utf8"],
                    "semantic_extraction_status": "complete",
                    "extractor": {
                        "identity": "test.source-clause-extractor",
                        "version": "1",
                        "digest": extractor_digest,
                    },
                    "extraction_artifact": {
                        "ref": f"memory:{source['source_id']}:clauses",
                        "digest": artifact_digest,
                        "source_byte_digest": source["source_digest"],
                        "content_encoding": "utf-8",
                        "content_utf8": extraction_content,
                        "byte_size": len(extraction_content.encode("utf-8")),
                    },
                }
            )
        snapshot = {
            "schema_version": "charting-loop/authority-snapshot/v3",
            "snapshot_id": "AUTHORITY-SNAPSHOT-001",
            "snapshot_revision": 1,
            "parent_snapshot_digest": None,
            "manifest_digest": None,
            "freeze_receipt": {
                "actor_role": "runner",
                "ref": "runner-freeze:test-001",
                "digest": "sha256:" + "7" * 64,
            },
            "closure_status": "complete",
            "sources": sources,
        }
        manifest = {
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_revision": snapshot["snapshot_revision"],
            "parent_snapshot_digest": snapshot["parent_snapshot_digest"],
            "sources": [
                {
                    "source_id": source["source_id"],
                    "source_ref": source["source_ref"],
                    "plane": source["plane"],
                    "role": source["role"],
                    "byte_status": source["byte_status"],
                    "byte_digest": source["byte_digest"],
                    "byte_size": source["byte_size"],
                    "media_type": source["media_type"],
                    "semantic_extraction_status": source[
                        "semantic_extraction_status"
                    ],
                    "extractor_digest": source["extractor"]["digest"],
                    "extraction_artifact_digest": source["extraction_artifact"][
                        "digest"
                    ],
                }
                for source in sources
            ],
        }
        snapshot["manifest_digest"] = sha256_json(manifest)
        snapshot["freeze_receipt"]["digest"] = sha256_json(
            {
                "actor_role": "runner",
                "ref": snapshot["freeze_receipt"]["ref"],
                "manifest_digest": snapshot["manifest_digest"],
            }
        )
        value["source_bundle"] = snapshot
        value["revision"]["revision_id"] = "IR-REV-V4"
        for clause in value["source_clause_inventory"]:
            for source_slice in clause["source_slices"]:
                source_slice["representation"] = "source_bytes"
            roles = set(clause["required_semantic_roles"])
            roles.update(
                {
                    "obligation",
                    "domain",
                    "quantifier",
                    "condition",
                    "outcome",
                    "evidence_requirement",
                    "witness_requirement",
                }
            )
            clause["required_semantic_roles"] = sorted(roles)
        for rule in value["rules"]:
            semantics = rule["semantics"]
            semantics["schema_version"] = "charting-loop/typed-rule-semantics/v4"
            for condition in semantics["conditions"]:
                condition["condition_kind"] = "static"
            primary_slice = rule["source_slices"][0]["slice_id"]
            bound_roles = {item["semantic_role"] for item in rule["source_slices"]}
            for role in (
                "obligation",
                "domain",
                "quantifier",
                "condition",
                "outcome",
                "evidence_requirement",
                "witness_requirement",
            ):
                if role not in bound_roles:
                    rule["source_slices"].append(
                        {"slice_id": primary_slice, "semantic_role": role}
                    )
            semantics["guidance"] = [
                {
                    "guidance_id": f"GUIDANCE-{rule['rule_id']}",
                    "trigger": "before assessing this Rule",
                    "action": "re-read its bound source slices",
                    "source_slice_ids": [primary_slice],
                }
            ]
            for dependency in semantics["dependencies"]:
                dependency["alignment"] = {
                    "mode": "keyed",
                    "source_endpoint": "dependant",
                    "target_endpoint": "prerequisite",
                    "key_pairs": [
                        {"source_key": "subject_id", "target_key": "subject_id"}
                    ],
                    "source_scope": [],
                    "target_scope": [],
                    "source_cardinality": {"minimum": 1, "maximum": 1},
                    "target_cardinality": {"minimum": 1, "maximum": 1},
                    "membership_ref": None,
                    "explicit_pairs": [],
                    "rationale": None,
                }
        return value

    @staticmethod
    def _refresh_v4_snapshot(snapshot: dict) -> None:
        manifest = {
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_revision": snapshot["snapshot_revision"],
            "parent_snapshot_digest": snapshot["parent_snapshot_digest"],
            "sources": [
                {
                    "source_id": source["source_id"],
                    "source_ref": source["source_ref"],
                    "plane": source["plane"],
                    "role": source["role"],
                    "byte_status": source["byte_status"],
                    "byte_digest": source["byte_digest"],
                    "byte_size": source["byte_size"],
                    "media_type": source["media_type"],
                    "semantic_extraction_status": source[
                        "semantic_extraction_status"
                    ],
                    "extractor_digest": (
                        source["extractor"]["digest"] if source["extractor"] else None
                    ),
                    "extraction_artifact_digest": (
                        source["extraction_artifact"]["digest"]
                        if source["extraction_artifact"]
                        else None
                    ),
                }
                for source in snapshot["sources"]
            ],
        }
        snapshot["manifest_digest"] = sha256_json(manifest)
        snapshot["freeze_receipt"]["digest"] = sha256_json(
            {
                "actor_role": "runner",
                "ref": snapshot["freeze_receipt"]["ref"],
                "manifest_digest": snapshot["manifest_digest"],
            }
        )

    @staticmethod
    def _append_v4_candidate(path: Path, ir: dict) -> tuple[dict, dict, dict]:
        report = compile_typed_rule_ir(ir)
        snapshot = append_graph_record(
            path,
            record_type="authority_snapshot",
            actor="runner",
            body=report["authority_snapshot_template"],
        )["record"]
        for body in report["source_artifact_templates"]:
            append_graph_record(
                path, record_type="task_source_artifact", actor="runner", body=body
            )
        for body in report["source_clause_templates"]:
            append_graph_record(
                path, record_type="source_clause", actor="worker", body=body
            )
        rule_records = {}
        for body in report["rule_bodies"]:
            record = append_graph_record(
                path, record_type="rule_proposal", actor="worker", body=body
            )["record"]
            rule_records[body["rule_id"]] = record["record_id"]
        candidate_body = {
            "schema_version": "charting-loop/rule-candidate-report/v1",
            "authority_snapshot_record_id": snapshot["record_id"],
            "typed_rule_ir": ir,
            "compile_report": report,
            "rule_record_ids": rule_records,
        }
        candidate = append_graph_record(
            path,
            record_type="rule_candidate_report",
            actor="runner",
            body={
                **candidate_body,
                "candidate_report_digest": sha256_json(candidate_body),
            },
        )["record"]
        return report, candidate, rule_records

    @staticmethod
    def _ratify_v4_candidate(
        path: Path, report: dict, candidate: dict, rule_records: dict
    ) -> list[str]:
        qa_body = {
            "schema_version": "charting-loop/rule-qa-assessment/v1",
            "candidate_report_record_id": candidate["record_id"],
            "candidate_report_digest": candidate["body"][
                "candidate_report_digest"
            ],
            "outcome": "pass",
            "findings": [],
        }
        qa = append_graph_record(
            path,
            record_type="rule_qa_assessment",
            actor="qa",
            body={**qa_body, "assessment_digest": sha256_json(qa_body)},
        )["record"]
        closures = []
        for body in report["rule_bodies"]:
            payload = {
                "rule_id": body["rule_id"],
                "rule_record_id": rule_records[body["rule_id"]],
                "candidate_report_record_id": candidate["record_id"],
                "candidate_report_digest": candidate["body"][
                    "candidate_report_digest"
                ],
                "candidate_revision_digest": report["candidate_revision_digest"],
                "authority_snapshot_digest": report["authority_snapshot_digest"],
                "reverse_projection_digest": report[
                    "reverse_semantic_projection_digest"
                ],
                "semantic_delta_digest": report["semantic_delta_digest"],
                "qa_assessment_ref": qa["record_id"],
                "qa_assessment_digest": qa["body"]["assessment_digest"],
                "ratifier_ref": "runner:test-v4",
            }
            closure = sha256_json(payload)
            append_graph_record(
                path,
                record_type="rule_ratification",
                actor="runner",
                body={
                    "rule_id": body["rule_id"],
                    "rule_record_id": rule_records[body["rule_id"]],
                    "authority_ref": body["source_ref"],
                    "authority_digest": body["source_digest"],
                    "receipt_ref": f"ratification:{body['rule_id']}",
                    "ratification_schema": "charting-loop/rule-ratification/v2",
                    **{
                        key: item
                        for key, item in payload.items()
                        if key not in {"rule_id", "rule_record_id"}
                    },
                    "rule_closure_digest": closure,
                },
            )
            closures.append(closure)
        return closures

    def test_runner_freezes_candidate_then_materializes_only_passing_rule_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            candidate = freeze_rule_candidate(path, typed_rule_ir=self._v4_ir())
            before = replay_graph(path)
            self.assertEqual(0, before["rule_closure_count"])
            self.assertEqual(0, before["acceptance_checklist_item_count"])

            closure = ratify_rule_candidate(
                path,
                candidate_report_record_id=candidate["candidate_report_record_id"],
                candidate_report_digest=candidate["candidate_report_digest"],
                outcome="pass",
                findings=[],
                ratifier_ref="runner:test-four-stage",
            )
            after = replay_graph(path)
            self.assertTrue(closure["rule_closure_established"])
            self.assertEqual(
                len(candidate["compile_report"]["rule_bodies"]),
                after["rule_closure_count"],
            )
            self.assertEqual(
                len(candidate["compile_report"]["checklist_templates"]),
                after["acceptance_checklist_item_count"],
            )
            self.assertEqual(
                candidate["compile_report"]["typed_dependency_count"],
                after["typed_dependency_count"],
            )
            rule_id = candidate["compile_report"]["rule_bodies"][0]["rule_id"]
            expected_closure = closure["rule_closure_digests"][rule_id]
            indexed_closure = query_graph(
                path,
                kind="rule-closure",
                ref=rule_id,
                expected_digest=expected_closure,
            )
            self.assertEqual("successor_established", indexed_closure["status"])
            self.assertTrue(indexed_closure["digest_matches"])
            self.assertFalse(indexed_closure["authorizes_mutation"])
            checklist_id = candidate["compile_report"]["checklist_templates"][0][
                "checklist_item_id"
            ]
            source_trace = query_graph(path, kind="source-trace", ref=checklist_id)
            self.assertEqual([rule_id], source_trace["rule_ids"])
            self.assertTrue(source_trace["source_clause_ids"])
            self.assertTrue(source_trace["source_ids"])

    def test_nonpassing_compile_qa_never_materializes_rule_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            candidate = freeze_rule_candidate(path, typed_rule_ir=self._v4_ir())
            result = ratify_rule_candidate(
                path,
                candidate_report_record_id=candidate["candidate_report_record_id"],
                candidate_report_digest=candidate["candidate_report_digest"],
                outcome="fail",
                findings=["CL-VERIFY omits the trailing temporal qualification."],
                ratifier_ref="runner:test-four-stage",
            )
            replay = replay_graph(path)
            self.assertFalse(result["rule_closure_established"])
            self.assertEqual(0, replay["rule_closure_count"])
            self.assertEqual(0, replay["acceptance_checklist_item_count"])

    def test_freeze_and_ratify_each_use_one_load_validation_and_write(self) -> None:
        import corridor_kit.graph as graph_module

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)

            def counted(action):
                with (
                    mock.patch.object(
                        graph_module,
                        "_read_graph_records",
                        wraps=graph_module._read_graph_records,
                    ) as reads,
                    mock.patch.object(
                        graph_module,
                        "validate_graph_records",
                        wraps=graph_module.validate_graph_records,
                    ) as validations,
                    mock.patch.object(
                        graph_module,
                        "atomic_write_bytes",
                        wraps=graph_module.atomic_write_bytes,
                    ) as writes,
                ):
                    result = action()
                    self.assertEqual(1, reads.call_count)
                    self.assertEqual(1, validations.call_count)
                    self.assertEqual(1, writes.call_count)
                    return result

            candidate = counted(
                lambda: freeze_rule_candidate(path, typed_rule_ir=self._v4_ir())
            )
            counted(
                lambda: ratify_rule_candidate(
                    path,
                    candidate_report_record_id=candidate[
                        "candidate_report_record_id"
                    ],
                    candidate_report_digest=candidate["candidate_report_digest"],
                    outcome="pass",
                    findings=[],
                    ratifier_ref="runner:test-batch-counts",
                )
            )

    def test_v4_bidirectional_compile_has_no_implicit_cartesian_projection(self) -> None:
        report = compile_typed_rule_ir(self._v4_ir())
        self.assertEqual("charting-loop/typed-rule-compilation/v4", report["schema_version"])
        self.assertTrue(report["compilation_complete"], report["compile_issues"])
        self.assertEqual([], report["semantic_delta"])
        self.assertEqual([], report["relationship_alignment_issues"])
        self.assertEqual(1, len(report["typed_dependency_templates"]))
        self.assertEqual(
            "keyed",
            report["typed_dependency_templates"][0]["relationship_alignment"]["mode"],
        )
        self.assertTrue(report["candidate_revision_digest"].startswith("sha256:"))
        self.assertTrue(report["reverse_semantic_projection_digest"].startswith("sha256:"))
        self.assertEqual(1, len(report["semantic_edge_templates"]))
        edge = report["semantic_edge_templates"][0]
        self.assertEqual("source_bound", edge["relationship_expectation_status"])
        self.assertEqual(
            [report["typed_dependency_templates"][0]["dependency_id"]],
            edge["typed_expansion_ids"],
        )
        self.assertTrue(edge["relationship_source_bindings"])
        self.assertTrue(report["witness_obligation_templates"])
        self.assertTrue(
            all(
                obligation["witness_families"] == ["declared_condition"]
                for obligation in report["witness_obligation_templates"]
            )
        )

    def test_v4_active_context_reverse_edge_and_direction_witness_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            report, candidate, rule_records = self._append_v4_candidate(
                path, self._v4_ir()
            )
            closure_digests = self._ratify_v4_candidate(
                path, report, candidate, rule_records
            )
            checklist_by_id = {}
            for template in report["checklist_templates"]:
                checklist_by_id[template["checklist_item_id"]] = template
                append_graph_record(
                    path,
                    record_type="acceptance_checklist_item",
                    actor="runner",
                    body={
                        **template,
                        "source_rule_record_id": rule_records[
                            template["source_rule_id"]
                        ],
                    },
                )
            for template in report["rule_dependency_templates"]:
                append_graph_record(
                    path,
                    record_type="rule_dependency",
                    actor="runner",
                    body=template,
                )
            for template in report["typed_dependency_templates"]:
                append_graph_record(
                    path,
                    record_type="typed_dependency",
                    actor="runner",
                    body={
                        **template,
                        "source_rule_record_id": rule_records[
                            template["source_rule_id"]
                        ],
                        "target_rule_record_id": rule_records[
                            template["target_rule_id"]
                        ],
                    },
                )
            dependency = report["typed_dependency_templates"][0]
            if dependency["relationship"] == "requires":
                dependant = dependency["from_ref"]
                prerequisite = dependency["to_ref"]
            else:
                dependant = dependency["to_ref"]
                prerequisite = dependency["from_ref"]
            checklist_ids = sorted(checklist_by_id)
            position_body = {
                "position_id": "P-ACTIVE-CONTEXT",
                "previous_position_ref": None,
                "task_identity": {"task_ref": "public/v4-example"},
                "scope": {"working_set": ["/workspace"]},
                "role_assignments": {"executor": "worker", "reviewer": "qa"},
                "rule_record_ids": sorted(rule_records.values()),
                "rule_closure_digests": closure_digests,
                "fact_receipt_ids": [],
                "artifact_record_ids": [],
                "checkpoint_kind": "row_progress",
                "checklist_item_ids": checklist_ids,
                "ready_item_ids": [prerequisite],
                "blocked_item_ids": [dependant],
                "unresolved_checklist_item_ids": checklist_ids,
                "checklist_assessments": {
                    item_id: {
                        "status": "unknown",
                        "applicability_status": "applicable",
                        "witness_fact_receipt_ids": [],
                    }
                    for item_id in checklist_ids
                },
            }
            initial_position = append_graph_record(
                path,
                record_type="position_checkpoint",
                actor="worker",
                body=position_body,
            )["record"]
            ready_rule_id = checklist_by_id[prerequisite]["source_rule_id"]
            applicability_fact = append_graph_record(
                path,
                record_type="fact_proposal",
                actor="worker",
                body={
                    "fact_id": "F-UNRELATED-N-A",
                    "statement": "An unrelated observation exists.",
                    "evidence_ref": "probe:unrelated",
                    "evidence_digest": "sha256:" + "6" * 64,
                    "position_ref": initial_position["record_id"],
                },
            )["record"]
            applicability_receipt = append_graph_record(
                path,
                record_type="fact_admission",
                actor="worker",
                body={
                    "fact_id": "F-UNRELATED-N-A",
                    "fact_record_id": applicability_fact["record_id"],
                    "admission_rule_id": ready_rule_id,
                    "admission_rule_record_id": rule_records[ready_rule_id],
                    "admitter_ref": "worker:test",
                    "receipt_ref": "receipt:unrelated",
                },
            )["record"]
            position = append_graph_record(
                path,
                record_type="position_checkpoint",
                actor="worker",
                body={
                    **position_body,
                    "position_id": "P-ACTIVE-CONTEXT-WITH-FACT",
                    "previous_position_ref": initial_position["record_id"],
                    "fact_receipt_ids": [applicability_receipt["record_id"]],
                },
            )["record"]
            direction_body = {
                "direction_id": "D-UNBOUND",
                "position_ref": position["record_id"],
                "statement": "Project the ready Rule before choosing an action.",
                "rule_record_ids": sorted(rule_records.values()),
                "rule_closure_digests": closure_digests,
                "fact_receipt_ids": [applicability_receipt["record_id"]],
                "evidence_refs": [],
                "checklist_item_ids": checklist_ids,
                "ready_item_ids": [prerequisite],
                "blocked_item_ids": [dependant],
                "unresolved_checklist_item_ids": checklist_ids,
            }
            append_graph_record(
                path,
                record_type="direction_proposal",
                actor="worker",
                body=direction_body,
            )
            self.assertIn(
                "direction_semantic_bindings_missing",
                graph_doctor(path)["incomplete_reasons"],
            )

            active = query_graph(path, kind="active-context")
            edge_id = report["semantic_edge_templates"][0]["semantic_edge_id"]
            self.assertEqual([edge_id], active["semantic_edge_ids"])
            self.assertIn(
                edge_id,
                active["compact_hard_constraint_ids"]["semantic_edge_ids"],
            )
            trace = query_graph(path, kind="edge-source-trace", ref=edge_id)
            self.assertEqual(
                "source_bound",
                trace["semantic_edge"]["relationship_expectation_status"],
            )
            bounded = query_graph(path, kind="active-context", max_chars=512)
            self.assertEqual("truncated", bounded["status"])
            self.assertTrue(bounded["omitted_detail_ids"])
            self.assertEqual(
                active["compact_hard_constraint_ids"],
                bounded["compact_hard_constraint_ids"],
            )

            witness_ids = sorted(
                item["witness_obligation_id"]
                for item in report["witness_obligation_templates"]
                if item["checklist_item_id"] == prerequisite
            )
            invalid = {
                **direction_body,
                "direction_id": "D-INVALID-WITNESS",
                "semantic_bindings": [
                    {
                        "position_ref": position["record_id"],
                        "rule_id": ready_rule_id,
                        "rule_record_id": rule_records[ready_rule_id],
                        "semantic_edge_ids": [edge_id],
                        "checklist_item_id": prerequisite,
                        "witness_obligation_ids": [],
                    }
                ],
            }
            before = path.read_bytes()
            with self.assertRaisesRegex(
                CorridorKitError, "witness obligations do not match"
            ):
                append_graph_record(
                    path,
                    record_type="direction_proposal",
                    actor="worker",
                    body=invalid,
                )
            self.assertEqual(before, path.read_bytes())
            bound_direction = append_graph_record(
                path,
                record_type="direction_proposal",
                actor="worker",
                body={
                    **direction_body,
                    "direction_id": "D-BOUND",
                    "semantic_bindings": [
                        {
                            "position_ref": position["record_id"],
                            "rule_id": ready_rule_id,
                            "rule_record_id": rule_records[ready_rule_id],
                            "semantic_edge_ids": [edge_id],
                            "checklist_item_id": prerequisite,
                            "witness_obligation_ids": witness_ids,
                        }
                    ],
                },
            )["record"]
            append_graph_record(
                path,
                record_type="direction_snapshot",
                actor="worker",
                body={
                    "position_ref": position["record_id"],
                    "direction_record_ids": [bound_direction["record_id"]],
                    "selected_direction_record_id": bound_direction["record_id"],
                },
            )
            self.assertNotIn(
                "direction_semantic_bindings_missing",
                graph_doctor(path)["incomplete_reasons"],
            )
            self.assertIn(
                "execution_test_contract_missing",
                graph_doctor(path)["incomplete_reasons"],
            )

            before_fixture = Path(temporary) / "before-fixture.json"
            before_fixture.write_text('{"world":"before"}\n', encoding="utf-8")
            after_fixture = Path(temporary) / "after-fixture.json"
            after_fixture.write_text('{"world":"after"}\n', encoding="utf-8")
            source_slice_id = next(
                item["slice_id"]
                for rule in self._v4_ir()["rules"]
                if rule["rule_id"] == ready_rule_id
                for item in rule["source_slices"]
            )
            cases = []
            for case_kind in ("positive", "boundary"):
                fixture = (
                    before_fixture if case_kind == "positive" else after_fixture
                )
                cases.append(
                    {
                        "probe_id": f"PROBE-{case_kind.upper()}",
                        "checklist_item_id": prerequisite,
                        "case_kind": case_kind,
                        "source_slice_ids": [source_slice_id],
                        "operator": "code_test",
                        "fixture_artifacts": [
                            {
                                "path": str(fixture),
                                "digest": sha256_bytes(fixture.read_bytes()),
                            }
                        ],
                        "command": f"python3 {fixture}",
                        "oracle": (
                            "The source-bound obligation holds in this exact world."
                            if case_kind == "positive"
                            else "The boundary world is rejected without weakening the Rule."
                        ),
                        "dependency_refs": [dependency["dependency_id"]],
                        "predecessor_probe_ids": (
                            []
                            if case_kind == "positive"
                            else ["PROBE-POSITIVE"]
                        ),
                        "pre_action_status": "not_run_yet",
                        "applicability_predicate": None,
                        "non_applicability_fact_receipt_ids": [],
                        "unsupported_reason": None,
                    }
                )
            contract_body = {
                "schema_version": EXECUTION_TEST_CONTRACT_SCHEMA,
                "contract_id": "EXECUTION-CONTRACT-001",
                "position_ref": position["record_id"],
                "direction_record_id": bound_direction["record_id"],
                "execution_kind": "task_mutation",
                "selected_checklist_item_ids": [prerequisite],
                "selected_rule_record_ids": [rule_records[ready_rule_id]],
                "semantic_edge_ids": [edge_id],
                "witness_obligation_ids": witness_ids,
                "probe_cases": cases,
                "exemption_reason": None,
            }
            invalid_na_contract = json.loads(json.dumps(contract_body))
            invalid_na_contract["contract_id"] = "EXECUTION-CONTRACT-INVALID-N-A"
            invalid_boundary = invalid_na_contract["probe_cases"][1]
            invalid_boundary["pre_action_status"] = "not_applicable"
            invalid_boundary["applicability_predicate"] = "an unrelated predicate"
            invalid_boundary["non_applicability_fact_receipt_ids"] = [
                applicability_receipt["record_id"]
            ]
            invalid_boundary["unsupported_reason"] = (
                "The unrelated Fact supposedly makes the boundary inapplicable."
            )
            invalid_na_contract["contract_digest"] = sha256_json(invalid_na_contract)
            with self.assertRaisesRegex(
                CorridorKitError, "conditional Rule applicability predicate"
            ):
                append_graph_record(
                    path,
                    record_type="execution_test_contract",
                    actor="worker",
                    body=invalid_na_contract,
                )
            contract_body["contract_digest"] = sha256_json(contract_body)
            contract_record = append_graph_record(
                path,
                record_type="execution_test_contract",
                actor="worker",
                body=contract_body,
            )["record"]
            self.assertIn(
                "execution_test_contract_qa_missing",
                graph_doctor(path)["incomplete_reasons"],
            )
            missing_qa_path = Path(temporary) / "missing-qa-graph.jsonl"
            missing_qa_path.write_bytes(path.read_bytes())
            missing_qa_receipt = {
                "schema_version": EXECUTION_TEST_RECEIPT_SCHEMA,
                "contract_record_id": contract_record["record_id"],
                "contract_digest": contract_body["contract_digest"],
                "probe_id": cases[0]["probe_id"],
                "outcome": "passed",
                "pre_action_qa_status": "missing",
                "pre_action_qa_assessment_record_id": None,
                "command_digest": sha256_json({"command": cases[0]["command"]}),
                "result_digest": sha256_bytes(b"probe passed\n"),
            }
            missing_qa_receipt["receipt_digest"] = sha256_json(missing_qa_receipt)
            append_graph_record(
                missing_qa_path,
                record_type="execution_test_receipt",
                actor="worker",
                body=missing_qa_receipt,
            )
            missing_qa_doctor = graph_doctor(missing_qa_path)
            self.assertTrue(missing_qa_doctor["structurally_valid"])
            self.assertFalse(missing_qa_doctor["blocking_gate"])
            self.assertIn(
                "execution_test_receipt_without_preaction_qa:PROBE-POSITIVE",
                missing_qa_doctor["incomplete_reasons"],
            )
            assessment_body = {
                "schema_version": EXECUTION_TEST_QA_ASSESSMENT_SCHEMA,
                "contract_record_id": contract_record["record_id"],
                "contract_digest": contract_body["contract_digest"],
                "outcome": "pass",
                "findings": [],
            }
            assessment_body["assessment_digest"] = sha256_json(assessment_body)
            assessment_record = append_graph_record(
                path,
                record_type="execution_test_qa_assessment",
                actor="qa",
                body=assessment_body,
            )["record"]
            with self.assertRaisesRegex(
                CorridorKitError, "must precede execution receipts"
            ):
                append_graph_record(
                    missing_qa_path,
                    record_type="execution_test_qa_assessment",
                    actor="qa",
                    body=assessment_body,
                )

            def receipt_for(case: dict[str, object]) -> dict[str, object]:
                receipt_body = {
                    "schema_version": EXECUTION_TEST_RECEIPT_SCHEMA,
                    "contract_record_id": contract_record["record_id"],
                    "contract_digest": contract_body["contract_digest"],
                    "probe_id": case["probe_id"],
                    "outcome": "passed",
                    "pre_action_qa_status": "pass",
                    "pre_action_qa_assessment_record_id": assessment_record[
                        "record_id"
                    ],
                    "command_digest": sha256_json({"command": case["command"]}),
                    "result_digest": sha256_bytes(b"probe passed\n"),
                }
                receipt_body["receipt_digest"] = sha256_json(receipt_body)
                return receipt_body

            out_of_order_path = Path(temporary) / "out-of-order-graph.jsonl"
            out_of_order_path.write_bytes(path.read_bytes())
            for case in reversed(cases):
                append_graph_record(
                    out_of_order_path,
                    record_type="execution_test_receipt",
                    actor="worker",
                    body=receipt_for(case),
                )
            self.assertIn(
                "execution_test_receipt_dependency_out_of_order:PROBE-BOUNDARY:PROBE-POSITIVE",
                graph_doctor(out_of_order_path)["incomplete_reasons"],
            )

            for case in cases:
                append_graph_record(
                    path,
                    record_type="execution_test_receipt",
                    actor="worker",
                    body=receipt_for(case),
                )
            doctor = graph_doctor(path)
            self.assertEqual(
                contract_record["record_id"],
                doctor["execution_test_contract"]["contract_record_id"],
            )
            self.assertEqual("pass", doctor["execution_test_contract"]["qa_outcome"])
            self.assertEqual(2, doctor["execution_test_contract"]["receipt_count"])
            self.assertFalse(
                any(
                    reason.startswith("execution_test_")
                    for reason in doctor["incomplete_reasons"]
                ),
                doctor["incomplete_reasons"],
            )
            active_with_tests = query_graph(path, kind="active-context")
            self.assertEqual(
                [contract_record["record_id"]],
                active_with_tests["execution_test_contract_ids"],
            )

    def test_v4_witness_families_require_explicit_semantics(self) -> None:
        value = self._v4_ir()
        ordinary_rule = value["rules"][0]
        ordinary = project_witness_obligation_templates(
            rule_id=ordinary_rule["rule_id"],
            statement=ordinary_rule["statement"],
            semantics=ordinary_rule["semantics"],
        )
        self.assertTrue(ordinary)
        self.assertTrue(
            all(
                "namespace_disjointness" not in item["witness_families"]
                for item in ordinary
            )
        )

        explicit_semantics = json.loads(json.dumps(ordinary_rule["semantics"]))
        explicit_semantics["conditions"][0][
            "required_witness_operators"
        ] = ["namespace_disjoint"]
        explicit = project_witness_obligation_templates(
            rule_id=ordinary_rule["rule_id"],
            statement=ordinary_rule["statement"],
            semantics=explicit_semantics,
        )
        condition_id = explicit_semantics["conditions"][0]["condition_id"]
        self.assertTrue(
            all(
                "namespace_disjointness" in item["witness_families"]
                for item in explicit
                if item["condition_id"] == condition_id
            )
        )

    def test_v4_reverse_projection_exposes_missing_semantic_role(self) -> None:
        value = self._v4_ir()
        value["rules"][0]["source_slices"] = [
            item
            for item in value["rules"][0]["source_slices"]
            if item["semantic_role"] != "outcome"
        ]
        report = compile_typed_rule_ir(value)
        self.assertFalse(report["compilation_complete"])
        self.assertEqual("R-EXIST", report["semantic_delta"][0]["rule_id"])
        self.assertIn(
            "outcome", report["semantic_delta"][0]["missing_semantic_roles"]
        )

    def test_v4_separates_available_bytes_from_incomplete_extraction(self) -> None:
        value = self._v4_ir()
        source = value["source_bundle"]["sources"][0]
        source["semantic_extraction_status"] = "incomplete"
        source["extractor"] = None
        source["extraction_artifact"] = None
        value["source_bundle"]["closure_status"] = "unresolved"
        manifest = {
            "snapshot_id": value["source_bundle"]["snapshot_id"],
            "snapshot_revision": 1,
            "parent_snapshot_digest": None,
            "sources": [
                {
                    "source_id": item["source_id"],
                    "source_ref": item["source_ref"],
                    "plane": item["plane"],
                    "role": item["role"],
                    "byte_status": item["byte_status"],
                    "byte_digest": item["byte_digest"],
                    "byte_size": item["byte_size"],
                    "media_type": item["media_type"],
                    "semantic_extraction_status": item["semantic_extraction_status"],
                    "extractor_digest": item["extractor"]["digest"] if item["extractor"] else None,
                    "extraction_artifact_digest": item["extraction_artifact"]["digest"] if item["extraction_artifact"] else None,
                }
                for item in value["source_bundle"]["sources"]
            ],
        }
        value["source_bundle"]["manifest_digest"] = sha256_json(manifest)
        value["source_bundle"]["freeze_receipt"]["digest"] = sha256_json(
            {
                "actor_role": "runner",
                "ref": value["source_bundle"]["freeze_receipt"]["ref"],
                "manifest_digest": value["source_bundle"]["manifest_digest"],
            }
        )
        report = compile_typed_rule_ir(value)
        self.assertFalse(report["compilation_complete"])
        self.assertEqual("available", source["byte_status"])
        self.assertEqual("incomplete", source["semantic_extraction_status"])

    def test_v4_binary_extraction_and_non_normative_planes_are_accounted_separately(self) -> None:
        value = self._v4_ir()
        source = value["source_bundle"]["sources"][0]
        source["media_type"] = "application/pdf"
        source["content_encoding"] = None
        source["content_utf8"] = None
        for clause in value["source_clause_inventory"]:
            for source_slice in clause["source_slices"]:
                if source_slice["source_id"] == source["source_id"]:
                    source_slice["representation"] = "extraction_artifact"
        fact_bytes = b"public world fact"
        value["source_bundle"]["sources"].append(
            {
                "source_id": "SRC-WORLD-FACT",
                "source_ref": "memory:world-fact",
                "plane": "public_task_fact",
                "role": "task_world",
                "byte_status": "available",
                "byte_digest": sha256_bytes(fact_bytes),
                "byte_size": len(fact_bytes),
                "media_type": "text/plain",
                "content_encoding": "utf-8",
                "content_utf8": fact_bytes.decode(),
                "semantic_extraction_status": "not_required",
                "extractor": None,
                "extraction_artifact": None,
            }
        )
        self._refresh_v4_snapshot(value["source_bundle"])
        report = compile_typed_rule_ir(value)
        self.assertTrue(report["compilation_complete"], report["compile_issues"])
        self.assertEqual([], report["unaccounted_normative_ranges"])
        self.assertEqual(3, report["source_closure"]["source_count"])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            self._append_v4_candidate(path, value)
            doctor = graph_doctor(path)
            self.assertNotIn(
                "SRC-WORLD-FACT",
                doctor["source_provenance"]["uninventoried_source_ids"],
            )

    def test_v4_ruleclosure_rejects_nonzero_delta_or_missing_qa(self) -> None:
        value = self._v4_ir()
        value["rules"][0]["source_slices"] = [
            item
            for item in value["rules"][0]["source_slices"]
            if item["semantic_role"] != "outcome"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            report, candidate, rule_records = self._append_v4_candidate(path, value)
            body = report["rule_bodies"][0]
            closure_payload = {
                "rule_id": body["rule_id"],
                "rule_record_id": rule_records[body["rule_id"]],
                "candidate_report_record_id": candidate["record_id"],
                "candidate_report_digest": candidate["body"][
                    "candidate_report_digest"
                ],
                "candidate_revision_digest": report["candidate_revision_digest"],
                "authority_snapshot_digest": report["authority_snapshot_digest"],
                "reverse_projection_digest": report[
                    "reverse_semantic_projection_digest"
                ],
                "semantic_delta_digest": report["semantic_delta_digest"],
                "qa_assessment_ref": "sha256:" + "8" * 64,
                "qa_assessment_digest": "sha256:" + "9" * 64,
                "ratifier_ref": "runner:test-invalid",
            }
            with self.assertRaisesRegex(
                CorridorKitError, "complete zero-delta compile report"
            ):
                append_graph_record(
                    path,
                    record_type="rule_ratification",
                    actor="runner",
                    body={
                        "rule_id": body["rule_id"],
                        "rule_record_id": rule_records[body["rule_id"]],
                        "authority_ref": body["source_ref"],
                        "authority_digest": body["source_digest"],
                        "receipt_ref": "ratification:invalid",
                        "ratification_schema": "charting-loop/rule-ratification/v2",
                        **{
                            key: item
                            for key, item in closure_payload.items()
                            if key not in {"rule_id", "rule_record_id"}
                        },
                        "rule_closure_digest": sha256_json(closure_payload),
                    },
                )

    def test_v4_graph_rejects_cross_key_edge_and_doctor_requires_exact_edge_set(self) -> None:
        value = self._v4_ir()
        for rule in value["rules"]:
            rule["semantics"]["quantifier"]["subjects"] = ["a", "b"]
            rule["semantics"]["checklist_projection"][
                "projection_mode"
            ] = "per_subject"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            report, candidate, rule_records = self._append_v4_candidate(path, value)
            self._ratify_v4_candidate(path, report, candidate, rule_records)
            for body in report["checklist_templates"]:
                append_graph_record(
                    path,
                    record_type="acceptance_checklist_item",
                    actor="worker",
                    body={
                        **body,
                        "source_rule_record_id": rule_records[
                            body["source_rule_id"]
                        ],
                    },
                )
            dependencies = report["typed_dependency_templates"]
            self.assertEqual(2, len(dependencies))
            first, second = dependencies
            invalid = {
                **first,
                "dependency_id": "DEP-CROSS-KEY",
                "to_ref": second["to_ref"],
                "source_rule_record_id": rule_records[first["source_rule_id"]],
                "target_rule_record_id": rule_records[first["target_rule_id"]],
            }
            with self.assertRaisesRegex(CorridorKitError, "outside relationship alignment"):
                append_graph_record(
                    path,
                    record_type="typed_dependency",
                    actor="worker",
                    body=invalid,
                )
            append_graph_record(
                path,
                record_type="typed_dependency",
                actor="worker",
                body={
                    **first,
                    "source_rule_record_id": rule_records[first["source_rule_id"]],
                    "target_rule_record_id": rule_records[first["target_rule_id"]],
                },
            )
            doctor = graph_doctor(path)
            issues = doctor["source_provenance"][
                "relationship_alignment_edge_issues"
            ]
            self.assertEqual(1, len(issues))
            self.assertEqual(1, len(issues[0]["missing_pairs"]))

    def test_v4_ruleclosure_must_precede_position_and_effective_direction(self) -> None:
        ir = self._v4_ir()
        report = compile_typed_rule_ir(ir)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            snapshot_record = append_graph_record(
                path,
                record_type="authority_snapshot",
                actor="runner",
                body=report["authority_snapshot_template"],
            )["record"]
            for body in report["source_artifact_templates"]:
                append_graph_record(
                    path, record_type="task_source_artifact", actor="runner", body=body
                )
            for body in report["source_clause_templates"]:
                append_graph_record(
                    path, record_type="source_clause", actor="worker", body=body
                )
            rule_records = {}
            closure_digests = []
            for body in report["rule_bodies"]:
                proposal = append_graph_record(
                    path, record_type="rule_proposal", actor="worker", body=body
                )
                rule_record_id = proposal["record"]["record_id"]
                rule_records[body["rule_id"]] = rule_record_id
            candidate_without_digest = {
                "schema_version": "charting-loop/rule-candidate-report/v1",
                "authority_snapshot_record_id": snapshot_record["record_id"],
                "typed_rule_ir": ir,
                "compile_report": report,
                "rule_record_ids": rule_records,
            }
            candidate = append_graph_record(
                path,
                record_type="rule_candidate_report",
                actor="runner",
                body={
                    **candidate_without_digest,
                    "candidate_report_digest": sha256_json(candidate_without_digest),
                },
            )["record"]
            first_body = report["rule_bodies"][0]
            missing_qa_payload = {
                "rule_id": first_body["rule_id"],
                "rule_record_id": rule_records[first_body["rule_id"]],
                "candidate_report_record_id": candidate["record_id"],
                "candidate_report_digest": candidate["body"][
                    "candidate_report_digest"
                ],
                "candidate_revision_digest": report["candidate_revision_digest"],
                "authority_snapshot_digest": report["authority_snapshot_digest"],
                "reverse_projection_digest": report[
                    "reverse_semantic_projection_digest"
                ],
                "semantic_delta_digest": report["semantic_delta_digest"],
                "qa_assessment_ref": "sha256:" + "8" * 64,
                "qa_assessment_digest": "sha256:" + "9" * 64,
                "ratifier_ref": "runner:missing-qa",
            }
            with self.assertRaisesRegex(CorridorKitError, "passing QA assessment"):
                append_graph_record(
                    path,
                    record_type="rule_ratification",
                    actor="runner",
                    body={
                        "rule_id": first_body["rule_id"],
                        "rule_record_id": rule_records[first_body["rule_id"]],
                        "authority_ref": first_body["source_ref"],
                        "authority_digest": first_body["source_digest"],
                        "receipt_ref": "ratification:missing-qa",
                        "ratification_schema": "charting-loop/rule-ratification/v2",
                        **{
                            key: item
                            for key, item in missing_qa_payload.items()
                            if key not in {"rule_id", "rule_record_id"}
                        },
                        "rule_closure_digest": sha256_json(missing_qa_payload),
                    },
                )
            qa_without_digest = {
                "schema_version": "charting-loop/rule-qa-assessment/v1",
                "candidate_report_record_id": candidate["record_id"],
                "candidate_report_digest": candidate["body"][
                    "candidate_report_digest"
                ],
                "outcome": "pass",
                "findings": [],
            }
            qa = append_graph_record(
                path,
                record_type="rule_qa_assessment",
                actor="qa",
                body={
                    **qa_without_digest,
                    "assessment_digest": sha256_json(qa_without_digest),
                },
            )["record"]
            for body in report["rule_bodies"]:
                rule_record_id = rule_records[body["rule_id"]]
                closure_payload = {
                    "rule_id": body["rule_id"],
                    "rule_record_id": rule_record_id,
                    "candidate_report_record_id": candidate["record_id"],
                    "candidate_report_digest": candidate["body"][
                        "candidate_report_digest"
                    ],
                    "candidate_revision_digest": report["candidate_revision_digest"],
                    "authority_snapshot_digest": report["authority_snapshot_digest"],
                    "reverse_projection_digest": report[
                        "reverse_semantic_projection_digest"
                    ],
                    "semantic_delta_digest": report["semantic_delta_digest"],
                    "qa_assessment_ref": qa["record_id"],
                    "qa_assessment_digest": qa["body"]["assessment_digest"],
                    "ratifier_ref": "runner:test-v4",
                }
                closure_digest = sha256_json(closure_payload)
                closure_digests.append(closure_digest)
                append_graph_record(
                    path,
                    record_type="rule_ratification",
                    actor="runner",
                    body={
                        "rule_id": body["rule_id"],
                        "rule_record_id": rule_record_id,
                        "authority_ref": body["source_ref"],
                        "authority_digest": body["source_digest"],
                        "receipt_ref": f"ratification:{body['rule_id']}",
                        "ratification_schema": "charting-loop/rule-ratification/v2",
                        **{
                            key: value
                            for key, value in closure_payload.items()
                            if key not in {"rule_id", "rule_record_id"}
                        },
                        "rule_closure_digest": closure_digest,
                    },
                )
            position_body = {
                "position_id": "POSITION-V4-001",
                "previous_position_ref": None,
                "task_identity": {"task": "synthetic-v4"},
                "scope": {"kind": "whole-task"},
                "role_assignments": {"worker": "test"},
                "rule_record_ids": list(rule_records.values()),
                "fact_receipt_ids": [],
                "artifact_record_ids": [],
            }
            with self.assertRaisesRegex(CorridorKitError, "RuleClosure digests"):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body=position_body,
                )
            position = append_graph_record(
                path,
                record_type="position_checkpoint",
                actor="worker",
                body={**position_body, "rule_closure_digests": closure_digests},
            )
            direction_body = {
                "direction_id": "DIRECTION-V4-001",
                "position_ref": position["record"]["record_id"],
                "statement": "execute the ready synthetic row",
                "rule_record_ids": list(rule_records.values()),
                "fact_receipt_ids": [],
                "evidence_refs": [],
            }
            with self.assertRaisesRegex(CorridorKitError, "RuleClosure digests"):
                append_graph_record(
                    path,
                    record_type="direction_proposal",
                    actor="worker",
                    body=direction_body,
                )
            append_graph_record(
                path,
                record_type="direction_proposal",
                actor="worker",
                body={**direction_body, "rule_closure_digests": closure_digests},
            )
            doctor = graph_doctor(path)
            self.assertEqual([], doctor["rule_ratification"]["missing_or_stale_rule_ids"])

    def test_v3_binds_exact_disjoint_cross_source_slices_and_edge_provenance(self) -> None:
        report = compile_typed_rule_ir(self._v3_ir())
        self.assertEqual("charting-loop/typed-rule-compilation/v3", report["schema_version"])
        self.assertTrue(report["compilation_complete"])
        self.assertEqual("exact_byte_slices", report["source_closure"]["source_provenance_status"])
        self.assertEqual(3, report["source_closure"]["source_slice_count"])
        self.assertEqual(2, len(report["source_artifact_templates"]))
        self.assertEqual(2, len(report["source_clause_templates"]))
        dependency = report["rule_dependency_templates"][0]
        self.assertEqual("direct", dependency["edge_provenance"]["kind"])
        self.assertIn("source_rule_provenance_digest", dependency)
        self.assertTrue(
            all(
                item["target_rule_id"] == "R-EXIST"
                and item["edge_provenance"] == dependency["edge_provenance"]
                for item in report["typed_dependency_templates"]
            )
        )

    def test_v3_clause_order_is_explicit_and_not_list_position_authority(self) -> None:
        value = self._v3_ir()
        expected = compile_typed_rule_ir(value)
        value["source_clause_inventory"].reverse()
        self.assertEqual(expected, compile_typed_rule_ir(value))

        duplicate_order = self._v3_ir()
        duplicate_order["source_clause_inventory"][1]["clause_order_key"] = (
            duplicate_order["source_clause_inventory"][0]["clause_order_key"]
        )
        with self.assertRaisesRegex(CorridorKitError, "order key is duplicated"):
            compile_typed_rule_ir(duplicate_order)

    def test_v3_rule_provenance_digest_binds_exact_source_bytes(self) -> None:
        original = compile_typed_rule_ir(self._v3_ir())
        changed = self._v3_ir()
        source = changed["source_bundle"]["sources"][0]
        source["content_utf8"] = source["content_utf8"].replace("✓", "★", 1)
        source["source_digest"] = sha256_bytes(source["content_utf8"].encode("utf-8"))
        clause = changed["source_clause_inventory"][0]
        clause["clause_text"] = clause["clause_text"].replace("✓", "★", 1)
        clause["clause_digest"] = sha256_bytes(clause["clause_text"].encode("utf-8"))
        source_slice = clause["source_slices"][0]
        source_slice["slice_digest"] = sha256_bytes(
            clause["clause_text"].encode("utf-8")
        )
        revised = compile_typed_rule_ir(changed)
        original_rule = next(
            body for body in original["rule_bodies"] if body["rule_id"] == "R-EXIST"
        )
        revised_rule = next(
            body for body in revised["rule_bodies"] if body["rule_id"] == "R-EXIST"
        )
        self.assertNotEqual(
            original_rule["rule_source_provenance_digest"],
            revised_rule["rule_source_provenance_digest"],
        )

    def test_v3_graph_rejects_duplicate_clause_order_identity_without_writing(self) -> None:
        report = compile_typed_rule_ir(self._v3_ir())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            for body in report["source_artifact_templates"]:
                append_graph_record(
                    path,
                    record_type="task_source_artifact",
                    actor="worker",
                    body=body,
                )
            first, second = report["source_clause_templates"]
            append_graph_record(
                path, record_type="source_clause", actor="worker", body=first
            )
            before = path.read_bytes()
            duplicate = {**second, "clause_order_key": first["clause_order_key"]}
            with self.assertRaisesRegex(CorridorKitError, "order key is duplicated"):
                append_graph_record(
                    path,
                    record_type="source_clause",
                    actor="worker",
                    body=duplicate,
                )
            self.assertEqual(before, path.read_bytes())

    def test_v3_rejects_misaligned_digest_mismatch_and_missing_roles(self) -> None:
        misaligned = self._v3_ir()
        misaligned["source_clause_inventory"][0]["source_slices"][0]["byte_start"] = 1
        with self.assertRaisesRegex(CorridorKitError, "UTF-8 code points"):
            compile_typed_rule_ir(misaligned)

        bad_digest = self._v3_ir()
        bad_digest["source_clause_inventory"][1]["source_slices"][0][
            "slice_digest"
        ] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(CorridorKitError, "digest does not match frozen bytes"):
            compile_typed_rule_ir(bad_digest)

        missing_role = self._v3_ir()
        missing_role["rules"][1]["source_slices"] = [
            item
            for item in missing_role["rules"][1]["source_slices"]
            if item["semantic_role"] != "relationship"
        ]
        with self.assertRaisesRegex(CorridorKitError, "semantic roles are not mapped"):
            compile_typed_rule_ir(missing_role)

    def test_v3_derived_edge_requires_both_current_endpoint_provenance_digests(self) -> None:
        value = self._v3_ir()
        provenance_digests = {
            rule["rule_id"]: rule["rule_source_provenance_digest"]
            for rule in compile_typed_rule_ir(value)["rule_bodies"]
        }
        provenance = value["rules"][1]["semantics"]["dependencies"][0]["provenance"]
        provenance.update(
            {
                "kind": "derived",
                "source_slice_ids": [],
                "derivation_kind": "ordering",
                "input_rule_provenance_digests": provenance_digests,
            }
        )
        self.assertTrue(compile_typed_rule_ir(value)["compilation_complete"])
        provenance["input_rule_provenance_digests"].pop("R-EXIST")
        with self.assertRaisesRegex(CorridorKitError, "both current endpoint"):
            compile_typed_rule_ir(value)

    def test_v3_supports_one_clause_to_many_rules_and_many_clauses_to_one_rule(self) -> None:
        value = self._v3_ir()
        value["source_clause_inventory"][0]["rule_ids"].append("R-VERIFY")
        value["rules"][1]["source_clause_ids"].insert(0, "CLAUSE-EXIST")
        value["rules"][1]["source_slices"].insert(
            0, {"slice_id": "SL-EXIST", "semantic_role": "obligation"}
        )
        report = compile_typed_rule_ir(value)
        self.assertTrue(report["compilation_complete"])
        verify_rule = next(
            body for body in report["rule_bodies"] if body["rule_id"] == "R-VERIFY"
        )
        self.assertEqual(
            ["CLAUSE-EXIST", "CLAUSE-VERIFY"], verify_rule["source_clause_ids"]
        )

    def test_v3_unavailable_named_source_remains_unresolved_without_fabricated_bytes(self) -> None:
        value = self._v3_ir()
        source = value["source_bundle"]["sources"][1]
        source.update(
            {
                "source_digest": None,
                "retrieval_status": "unavailable",
                "content_encoding": None,
                "content_utf8": None,
            }
        )
        value["source_bundle"]["closure_status"] = "unresolved"
        clause = value["source_clause_inventory"][1]
        clause["source_slices"] = clause["source_slices"][:1]
        clause["clause_text"] = "Before release, verify every item."
        clause["clause_digest"] = sha256_bytes(clause["clause_text"].encode("utf-8"))
        clause["required_semantic_roles"].remove("witness_requirement")
        value["rules"][1]["source_slices"] = [
            binding
            for binding in value["rules"][1]["source_slices"]
            if binding["slice_id"] != "SL-EVIDENCE"
        ]
        report = compile_typed_rule_ir(value)
        self.assertFalse(report["compilation_complete"])
        self.assertEqual("unresolved", report["source_closure"]["bundle_status"])
        self.assertIsNone(report["source_artifact_templates"][1]["content_utf8"])

    def test_v3_graph_doctor_reports_exact_source_closure_and_stale_edge_revision(self) -> None:
        report = compile_typed_rule_ir(self._v3_ir())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            for body in report["source_artifact_templates"]:
                append_graph_record(
                    path,
                    record_type="task_source_artifact",
                    actor="worker",
                    body=body,
                )
            for body in report["source_clause_templates"]:
                append_graph_record(
                    path,
                    record_type="source_clause",
                    actor="worker",
                    body=body,
                )
            rule_records = {}
            rule_bodies = {body["rule_id"]: body for body in report["rule_bodies"]}
            for body in report["rule_bodies"]:
                proposal = append_graph_record(
                    path,
                    record_type="rule_proposal",
                    actor="worker",
                    body=body,
                )
                rule_records[body["rule_id"]] = proposal["record"]["record_id"]
                append_graph_record(
                    path,
                    record_type="rule_ratification",
                    actor="worker",
                    body={
                        "rule_id": body["rule_id"],
                        "rule_record_id": proposal["record"]["record_id"],
                        "authority_ref": body["source_ref"],
                        "authority_digest": body["source_digest"],
                        "receipt_ref": f"source-compile:{body['rule_id']}",
                    },
                )
            for body in report["checklist_templates"]:
                append_graph_record(
                    path,
                    record_type="acceptance_checklist_item",
                    actor="worker",
                    body={
                        **body,
                        "source_rule_record_id": rule_records[body["source_rule_id"]],
                    },
                )
            for body in report["rule_dependency_templates"]:
                append_graph_record(
                    path,
                    record_type="rule_dependency",
                    actor="worker",
                    body=body,
                )
            for body in report["typed_dependency_templates"]:
                append_graph_record(
                    path,
                    record_type="typed_dependency",
                    actor="worker",
                    body={
                        **body,
                        "source_rule_record_id": rule_records[body["source_rule_id"]],
                        "target_rule_record_id": rule_records[body["target_rule_id"]],
                    },
                )
            before_contradiction = path.read_bytes()
            contradictory = json.loads(
                json.dumps(report["typed_dependency_templates"][0])
            )
            contradictory.update(
                {
                    "dependency_id": "DEP-CONTRADICTORY-DIRECTION",
                    "target_rule_id": "R-VERIFY",
                    "source_rule_record_id": rule_records["R-VERIFY"],
                    "target_rule_record_id": rule_records["R-VERIFY"],
                    "target_rule_provenance_digest": rule_bodies["R-VERIFY"][
                        "rule_source_provenance_digest"
                    ],
                }
            )
            with self.assertRaisesRegex(
                CorridorKitError, "contradicts its source Rule semantics"
            ):
                append_graph_record(
                    path,
                    record_type="typed_dependency",
                    actor="worker",
                    body=contradictory,
                )
            self.assertEqual(before_contradiction, path.read_bytes())
            doctor = graph_doctor(path)
            self.assertEqual("exact_byte_slices", doctor["source_provenance"]["status"])
            self.assertEqual([], doctor["source_provenance"]["semantic_role_issues"])
            self.assertEqual(
                [], doctor["source_provenance"]["provenance_less_dependency_ids"]
            )

            revised_ir = self._v3_ir()
            revised_report = compile_typed_rule_ir(revised_ir)
            revised = next(
                json.loads(json.dumps(body))
                for body in revised_report["rule_bodies"]
                if body["rule_id"] == "R-EXIST"
            )
            revised["supersedes_record_id"] = rule_records["R-EXIST"]
            append_graph_record(
                path,
                record_type="rule_revision",
                actor="worker",
                body=revised,
            )
            stale = graph_doctor(path)
            self.assertTrue(stale["source_provenance"]["stale_dependency_provenance_ids"])
            self.assertEqual("unresolved", stale["source_provenance"]["status"])

            revised_record_id = replay_graph(path)["records"][-1]["record_id"]
            append_graph_record(
                path,
                record_type="rule_ratification",
                actor="runner",
                body={
                    "rule_id": revised["rule_id"],
                    "rule_record_id": revised_record_id,
                    "authority_ref": revised["source_ref"],
                    "authority_digest": revised["source_digest"],
                    "receipt_ref": "source-compile:R-EXIST:revision-2",
                },
            )
            index = load_graph_index(path)
            old_dependency = report["rule_dependency_templates"][0]
            indexed_edges = [
                *index.neighbors(old_dependency["from_rule_id"])["inbound"],
                *index.neighbors(old_dependency["from_rule_id"])["outbound"],
            ]
            self.assertFalse(
                any(edge["source"] == "rule_dependency" for edge in indexed_edges)
            )
            stale_edge_id = semantic_edge_id(
                from_rule_id=old_dependency["from_rule_id"],
                to_rule_id=old_dependency["to_rule_id"],
                declared_relationship=old_dependency["relationship"],
            )
            active = index.active_context()
            self.assertNotIn(stale_edge_id, active["semantic_edge_ids"])
            self.assertNotIn(
                stale_edge_id,
                active["compact_hard_constraint_ids"]["semantic_edge_ids"],
            )
            self.assertIn(stale_edge_id, active["stale_semantic_edge_ids"])
            self.assertIn(stale_edge_id, active["unresolved_mismatch_ids"])
            self.assertNotIn(
                report["typed_dependency_templates"][0]["dependency_id"],
                active["compact_hard_constraint_ids"]["typed_expansion_ids"],
            )
            with self.assertRaisesRegex(
                CorridorKitError, "unknown semantic edge"
            ):
                index.edge_source_trace(stale_edge_id)

            current_checklist_ids = active["related_checklist_item_ids"]
            position = append_graph_record(
                path,
                record_type="position_checkpoint",
                actor="worker",
                body={
                    "position_id": "P-AFTER-RULE-REVISION",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "public/v3-stale-edge"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": sorted(
                        [revised_record_id, rule_records["R-VERIFY"]]
                    ),
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "row_progress",
                    "checklist_item_ids": current_checklist_ids,
                    "ready_item_ids": current_checklist_ids,
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": current_checklist_ids,
                    "checklist_assessments": {
                        item_id: {
                            "status": "unknown",
                            "applicability_status": "applicable",
                            "witness_fact_receipt_ids": [],
                        }
                        for item_id in current_checklist_ids
                    },
                },
            )["record"]
            verify_checklist = next(
                item
                for item in report["checklist_templates"]
                if item["source_rule_id"] == "R-VERIFY"
                and item["checklist_item_id"] in current_checklist_ids
            )
            before_stale_direction = path.read_bytes()
            with self.assertRaisesRegex(
                CorridorKitError,
                "semantic edge bindings do not match",
            ):
                append_graph_record(
                    path,
                    record_type="direction_proposal",
                    actor="worker",
                    body={
                        "direction_id": "D-STALE-EDGE",
                        "position_ref": position["record_id"],
                        "statement": "Do not follow a stale dependency edge.",
                        "rule_record_ids": sorted(
                            [revised_record_id, rule_records["R-VERIFY"]]
                        ),
                        "fact_receipt_ids": [],
                        "evidence_refs": [],
                        "checklist_item_ids": current_checklist_ids,
                        "ready_item_ids": current_checklist_ids,
                        "blocked_item_ids": [],
                        "unresolved_checklist_item_ids": current_checklist_ids,
                        "semantic_bindings": [
                            {
                                "position_ref": position["record_id"],
                                "rule_id": "R-VERIFY",
                                "rule_record_id": rule_records["R-VERIFY"],
                                "semantic_edge_ids": [stale_edge_id],
                                "checklist_item_id": verify_checklist[
                                    "checklist_item_id"
                                ],
                                "witness_obligation_ids": [],
                            }
                        ],
                    },
                )
            self.assertEqual(before_stale_direction, path.read_bytes())

            replacement = append_graph_record(
                path,
                record_type="rule_dependency",
                actor="worker",
                body=old_dependency,
            )["record"]
            self.assertEqual(
                revised_record_id,
                replacement["body"]["target_rule_record_id"],
            )
            dependency_history = [
                record["body"]
                for record in replay_graph(path)["records"]
                if record["record_type"] == "rule_dependency"
            ]
            self.assertEqual(2, len(dependency_history))
            self.assertEqual(
                rule_records["R-EXIST"],
                dependency_history[0]["target_rule_record_id"],
            )
            self.assertEqual(
                revised_record_id,
                dependency_history[1]["target_rule_record_id"],
            )
            repaired_index = load_graph_index(path)
            repaired_active = repaired_index.active_context()
            self.assertIn(stale_edge_id, repaired_active["semantic_edge_ids"])
            self.assertNotIn(
                stale_edge_id, repaired_active["stale_semantic_edge_ids"]
            )
            self.assertEqual(
                revised_record_id,
                repaired_index.edge_source_trace(stale_edge_id)[
                    "semantic_edge"
                ][
                    "to_rule_record_id"
                ],
            )

    def test_compiler_projects_every_subject_condition_cell_and_freezes_probe(self) -> None:
        report = compile_typed_rule_ir(self._ir())
        self.assertEqual(6, report["coverage_cell_count"])
        self.assertEqual(
            6,
            len(
                {
                    item["checklist_item_id"]
                    for item in report["checklist_templates"]
                }
            ),
        )
        cells = {
            (
                item["coverage_cell"]["subject_id"],
                item["coverage_cell"]["condition_id"],
            )
            for item in report["checklist_templates"]
        }
        self.assertEqual(
            {
                (subject, condition)
                for subject in ("item-a", "item-b", "item-c")
                for condition in ("branch-open", "branch-closed")
            },
            cells,
        )
        manifest = report["compile_probe_manifest"]
        self.assertEqual("fresh_task_pre_experiment", manifest["run_classification"])
        self.assertTrue(manifest["fresh_efficacy_or_transfer_claim_allowed"])
        self.assertIn("official_verifier_output", manifest["input_policy"]["forbidden"])
        regression = compile_typed_rule_ir(
            self._ir(), run_classification="same_task_regression"
        )
        self.assertFalse(
            regression["compile_probe_manifest"][
                "fresh_efficacy_or_transfer_claim_allowed"
            ]
        )
        self.assertFalse(report["task_truth_assessed"])
        self.assertFalse(report["blocking_gate"])

    def test_temporal_rule_rejects_a_timeless_surrogate_operator(self) -> None:
        value = self._ir(rule_kind="temporal_conditional", operators=["set_equality"])
        with self.assertRaisesRegex(
            CorridorKitError, "requires a temporal witness operator"
        ):
            compile_typed_rule_ir(value)

    def test_ambiguous_rule_remains_explicit_instead_of_becoming_complete(self) -> None:
        value = self._ir()
        semantics = value["rules"][0]["semantics"]
        semantics["compilation_status"] = "ambiguous"
        semantics["compile_issues"] = [
            "The public source does not define which branch owns the boundary."
        ]
        report = compile_typed_rule_ir(value)
        self.assertFalse(report["compilation_complete"])
        self.assertEqual("ambiguous", report["compile_issues"][0]["status"])
        self.assertTrue(
            all(
                item["compilation_status"] == "ambiguous"
                for item in report["checklist_templates"]
            )
        )

    def test_compiler_projects_rule_dependencies_into_ordering_edges(self) -> None:
        value = self._ir()
        base = json.loads(json.dumps(value["rules"][0]))
        base["rule_id"] = "R-BASE"
        base["statement"] = "Establish the shared prerequisite."
        base["source_ref"] = "public-task:prerequisite"
        base["semantics"]["quantifier"] = {
            "mode": "all",
            "subject_axis": "task",
            "subjects": ["whole-task"],
        }
        base["semantics"]["conditions"] = [
            {
                "condition_id": "prerequisite",
                "predicate": "the task begins",
                "expected_outcome": "the prerequisite exists",
                "required_witness_operators": ["exists"],
            }
        ]
        base["semantics"]["checklist_projection"]["projection_mode"] = "aggregate"
        value["rules"][0]["semantics"]["dependencies"] = [
            {"relationship": "requires", "target_rule_id": "R-BASE"}
        ]
        value["rules"].append(base)

        report = compile_typed_rule_ir(value)
        self.assertEqual(1, report["rule_dependency_count"])
        self.assertEqual(6, report["typed_dependency_count"])
        self.assertTrue(
            all(
                item["relationship"] == "requires"
                and item["dependency_kind"] == "work"
                and item["source_rule_id"] == "R-COVERAGE"
                for item in report["typed_dependency_templates"]
            )
        )

    def test_v2_compiler_binds_closed_sources_clauses_and_first_revision(self) -> None:
        report = compile_typed_rule_ir(self._v2_ir())
        self.assertEqual("charting-loop/typed-rule-compilation/v2", report["schema_version"])
        self.assertTrue(report["compilation_complete"])
        self.assertTrue(report["source_closure_assessed"])
        self.assertEqual("complete", report["source_closure"]["bundle_status"])
        self.assertEqual(1, report["source_closure"]["mapped_clause_count"])
        self.assertEqual("first_attempt", report["revision"]["revision_kind"])
        self.assertEqual(
            "charting-loop/compile-probe-manifest/v2",
            report["compile_probe_manifest"]["schema_version"],
        )
        self.assertIn(
            "task_solution", report["compile_probe_manifest"]["input_policy"]["forbidden"]
        )
        self.assertIn(
            "independent_source_qa",
            report["compile_probe_manifest"]["input_policy"]["forbidden"],
        )
        self.assertNotIn(
            "independent_source_qa",
            report["compile_probe_manifest"]["input_policy"]["allowed"],
        )
        self.assertTrue(
            all(item["requirement_level"] == "required" for item in report["checklist_templates"])
        )

    def test_v2_source_closure_and_optional_clauses_cannot_silently_disappear(self) -> None:
        value = self._v2_ir(requirement_level="optional")
        value["source_bundle"]["sources"].append(
            {
                "source_id": "SRC-NAMED-PACKET",
                "source_ref": "public-task:named-packet",
                "source_digest": None,
                "role": "authoritative_specification",
                "retrieval_status": "unavailable",
            }
        )
        value["source_bundle"]["closure_status"] = "unresolved"
        report = compile_typed_rule_ir(value)
        self.assertFalse(report["compilation_complete"])
        self.assertEqual("unresolved", report["source_closure"]["bundle_status"])
        self.assertTrue(
            all(item["requirement_level"] == "optional" for item in report["checklist_templates"])
        )

        value = self._v2_ir()
        value["source_bundle"]["sources"].append(
            {
                "source_id": "SRC-SECOND-SPEC",
                "source_ref": "public-task:second-spec",
                "source_digest": "sha256:" + "9" * 64,
                "role": "authoritative_specification",
                "retrieval_status": "available",
            }
        )
        with self.assertRaisesRegex(
            CorridorKitError, "available task sources lack clause inventory entries"
        ):
            compile_typed_rule_ir(value)

    def test_v2_rejects_unmapped_known_clause_and_vacuous_output_domain(self) -> None:
        value = self._v2_ir()
        value["source_clause_inventory"][0].update(
            {"mapping_status": "unmapped", "rule_ids": [], "issue": "not compiled"}
        )
        with self.assertRaisesRegex(CorridorKitError, "source_clause_ids do not match"):
            compile_typed_rule_ir(value)

        value = self._v2_ir()
        value["rules"][0]["semantics"]["quantifier"]["domain_source"] = "produced_output"
        with self.assertRaisesRegex(CorridorKitError, "cannot define its domain"):
            compile_typed_rule_ir(value)

    def test_v2_semantic_repair_requires_parent_digest_and_qa_witness(self) -> None:
        value = self._v2_ir()
        value["revision"] = {
            "revision_id": "IR-REV-002",
            "revision_kind": "semantic_repair",
            "parent_ir_digest": "sha256:" + "8" * 64,
            "qa_witness_refs": ["qa:source-audit:missing-clause"],
        }
        report = compile_typed_rule_ir(value, run_classification="same_task_regression")
        self.assertEqual("semantic_repair", report["revision"]["revision_kind"])
        self.assertIn(
            "independent_source_qa",
            report["compile_probe_manifest"]["input_policy"]["allowed"],
        )
        self.assertNotIn(
            "independent_source_qa",
            report["compile_probe_manifest"]["input_policy"]["forbidden"],
        )
        self.assertFalse(
            report["compile_probe_manifest"]["fresh_efficacy_or_transfer_claim_allowed"]
        )

        value["revision"]["qa_witness_refs"] = []
        with self.assertRaisesRegex(CorridorKitError, "must bind at least one QA witness"):
            compile_typed_rule_ir(value)


class GraphKernelTests(unittest.TestCase):
    def _append(self, path: Path, record_type: str, body: dict, actor: str = "worker"):
        return append_graph_record(
            path, record_type=record_type, actor=actor, body=body
        )["record"]

    def _ratified_rule(
        self, path: Path, rule_id: str, statement: str, digest_digit: str
    ) -> dict:
        digest = "sha256:" + digest_digit * 64
        rule = self._append(
            path,
            "rule_proposal",
            {
                "rule_id": rule_id,
                "statement": statement,
                "source_ref": f"official-task:{rule_id}",
                "source_digest": digest,
            },
        )
        self._append(
            path,
            "rule_ratification",
            {
                "rule_id": rule_id,
                "rule_record_id": rule["record_id"],
                "authority_ref": "official-task",
                "authority_digest": digest,
                "receipt_ref": f"receipt:{rule_id}",
            },
            actor="runner",
        )
        return rule

    def _checklist(
        self,
        path: Path,
        *,
        item_id: str,
        rule_id: str,
        rule_record_id: str,
        partitions: list[str],
        required_partitions: list[str],
    ) -> dict:
        return self._append(
            path,
            "acceptance_checklist_item",
            {
                "checklist_item_id": item_id,
                "source_rule_id": rule_id,
                "source_rule_record_id": rule_record_id,
                "obligation": "Exercise every declared behavior and retain evidence.",
                "scope": {
                    "artifact": "official-output",
                    "required_partitions": required_partitions,
                },
                "quantifier": "all",
                "behavioral_partitions": partitions,
                "evidence_requirement": "An admitted replay receipt for each partition.",
                "decision_rule": {
                    "pass": "all required partitions have admitted witnesses",
                    "fail": "a required partition contradicts the obligation",
                    "unknown": "any required partition lacks an admitted witness",
                },
                "compilation_status": "complete",
            },
        )

    def test_graph_replays_authority_position_and_direction_without_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            source_digest = "sha256:" + "1" * 64
            accept = self._append(
                path,
                "rule_proposal",
                {
                    "rule_id": "R-ADMIT",
                    "statement": "Evidence may become a Fact only with a replay receipt.",
                    "source_ref": "official-task:admission",
                    "source_digest": source_digest,
                },
            )
            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": "R-ADMIT",
                    "rule_record_id": accept["record_id"],
                    "authority_ref": "official-task",
                    "authority_digest": source_digest,
                    "receipt_ref": "receipt:admit-rule",
                },
                actor="runner",
            )
            task_rule = self._append(
                path,
                "rule_proposal",
                {
                    "rule_id": "R-TASK",
                    "statement": "Complete every official deliverable.",
                    "source_ref": "official-task:deliverables",
                    "source_digest": source_digest,
                },
            )
            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": "R-TASK",
                    "rule_record_id": task_rule["record_id"],
                    "authority_ref": "official-task",
                    "authority_digest": source_digest,
                    "receipt_ref": "receipt:task-rule",
                },
                actor="runner",
            )
            self._append(
                path,
                "rule_dependency",
                {
                    "from_rule_id": "R-TASK",
                    "to_rule_id": "R-ADMIT",
                    "relationship": "requires",
                },
            )
            intake_position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-INTAKE",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "terminal-bench/example"},
                    "scope": {"working_set": ["/app"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [accept["record_id"], task_rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                },
            )
            fact = self._append(
                path,
                "fact_proposal",
                {
                    "fact_id": "F-1",
                    "statement": "The target artifact exists.",
                    "evidence_ref": "probe:stat",
                    "evidence_digest": "sha256:" + "2" * 64,
                    "position_ref": intake_position["record_id"],
                },
            )
            receipt = self._append(
                path,
                "fact_admission",
                {
                    "fact_id": "F-1",
                    "fact_record_id": fact["record_id"],
                    "admission_rule_id": "R-ADMIT",
                    "admission_rule_record_id": accept["record_id"],
                    "admitter_ref": "worker:replay",
                    "receipt_ref": "receipt:fact-1",
                },
            )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-1",
                    "previous_position_ref": intake_position["record_id"],
                    "task_identity": {"task_ref": "terminal-bench/example"},
                    "scope": {"working_set": ["/app"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [accept["record_id"], task_rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "artifact_record_ids": [],
                },
            )
            direction = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-1",
                    "position_ref": position["record_id"],
                    "statement": "Inspect all deliverables before editing.",
                    "rule_record_ids": [task_rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "evidence_refs": ["probe:stat"],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position["record_id"],
                    "direction_record_ids": [direction["record_id"]],
                    "selected_direction_record_id": direction["record_id"],
                },
            )
            report = replay_graph(path)
            self.assertTrue(report["structurally_valid"])
            self.assertEqual(report["latest_position_ref"], position["record_id"])
            self.assertFalse(report["task_truth_assessed"])
            self.assertFalse(report["pass_assessed"])
            self.assertFalse(report["authorizes_mutation"])
            self.assertFalse(report["blocking_gate"])

    def test_graph_rejects_unratified_rules_unknown_positions_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            source_digest = "sha256:" + "4" * 64
            rule = self._append(
                path,
                "rule_proposal",
                {
                    "rule_id": "R-1",
                    "statement": "Use the official task requirements.",
                    "source_ref": "official-task",
                    "source_digest": source_digest,
                },
            )
            before = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "ratified Rule closure"):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-1",
                        "previous_position_ref": None,
                        "task_identity": {"task_ref": "terminal-bench/example"},
                        "scope": {"working_set": ["/app"]},
                        "role_assignments": {"executor": "worker"},
                        "rule_record_ids": [rule["record_id"]],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": [],
                    },
                )
            self.assertEqual(before, path.read_bytes())
            with self.assertRaisesRegex(CorridorKitError, "unknown Position"):
                append_graph_record(
                    path,
                    record_type="fact_proposal",
                    actor="worker",
                    body={
                        "fact_id": "F-UNKNOWN",
                        "statement": "An observation.",
                        "evidence_ref": "probe:unknown",
                        "evidence_digest": "sha256:" + "5" * 64,
                        "position_ref": "sha256:" + "0" * 64,
                    },
                )
            self.assertEqual(before, path.read_bytes())
            with self.assertRaisesRegex(CorridorKitError, "current rule source"):
                append_graph_record(
                    path,
                    record_type="rule_ratification",
                    actor="runner",
                    body={
                        "rule_id": "R-1",
                        "rule_record_id": rule["record_id"],
                        "authority_ref": "official-task",
                        "authority_digest": "sha256:" + "6" * 64,
                        "receipt_ref": "receipt:mismatched-source",
                    },
                )
            self.assertEqual(before, path.read_bytes())
            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": "R-1",
                    "rule_record_id": rule["record_id"],
                    "authority_ref": "official-task",
                    "authority_digest": source_digest,
                    "receipt_ref": "receipt:r-1",
                },
                actor="runner",
            )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-1",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "terminal-bench/example"},
                    "scope": {"working_set": ["/app"]},
                    "role_assignments": {"executor": "worker"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                },
            )
            before_duplicate = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "already exists"):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-1",
                        "previous_position_ref": position["record_id"],
                        "task_identity": {"task_ref": "terminal-bench/example"},
                        "scope": {"working_set": ["/app", "/tmp"]},
                        "role_assignments": {"executor": "worker"},
                        "rule_record_ids": [rule["record_id"]],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": [],
                    },
                )
            self.assertEqual(before_duplicate, path.read_bytes())
            direction = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-1",
                    "position_ref": position["record_id"],
                    "statement": "Inspect the current artifact.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "evidence_refs": [],
                },
            )
            before_duplicate = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "already exists"):
                append_graph_record(
                    path,
                    record_type="direction_proposal",
                    actor="worker",
                    body={
                        "direction_id": "D-1",
                        "position_ref": position["record_id"],
                        "statement": "Choose a conflicting next action.",
                        "rule_record_ids": [rule["record_id"]],
                        "fact_receipt_ids": [],
                        "evidence_refs": ["probe:alternate"],
                    },
                )
            self.assertEqual(before_duplicate, path.read_bytes())
            self.assertEqual("D-1", direction["body"]["direction_id"])
            revised = self._append(
                path,
                "rule_revision",
                {
                    "rule_id": "R-1",
                    "supersedes_record_id": rule["record_id"],
                    "statement": "Use the revised official task requirements.",
                    "source_ref": "official-task:revision-2",
                    "source_digest": "sha256:" + "7" * 64,
                },
            )
            before_unratified_revision = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "ratified Rule closure"):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-2",
                        "previous_position_ref": position["record_id"],
                        "task_identity": {"task_ref": "terminal-bench/example"},
                        "scope": {"working_set": ["/app"]},
                        "role_assignments": {"executor": "worker"},
                        "rule_record_ids": [revised["record_id"]],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": [],
                    },
                )
            self.assertEqual(before_unratified_revision, path.read_bytes())

    def test_graph_invalid_append_is_zero_write_and_exact_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            body = {
                "rule_id": "R-1",
                "statement": "Use the official task.",
                "source_ref": "official-task",
                "source_digest": "sha256:" + "3" * 64,
            }
            first = append_graph_record(
                path, record_type="rule_proposal", actor="worker", body=body
            )
            before = path.read_bytes()
            repeated = append_graph_record(
                path, record_type="rule_proposal", actor="worker", body=body
            )
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(CorridorKitError, "ratified Rule closure"):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-1",
                        "previous_position_ref": None,
                        "task_identity": {"task_ref": "terminal-bench/example"},
                        "scope": {"working_set": ["/app"]},
                        "role_assignments": {"executor": "worker"},
                        "rule_record_ids": [first["record"]["record_id"]],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": ["sha256:" + "9" * 64],
                    },
                )
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(CorridorKitError, "current rule"):
                append_graph_record(
                    path,
                    record_type="rule_ratification",
                    actor="runner",
                    body={
                        "rule_id": "R-1",
                        "rule_record_id": "sha256:" + "0" * 64,
                        "authority_ref": "official-task",
                        "authority_digest": "sha256:" + "3" * 64,
                        "receipt_ref": "receipt:bad",
                    },
                )
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(first["record"]["sequence"], 1)

    def test_graph_doctor_detects_an_omitted_universal_partition_without_claiming_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            rule = self._ratified_rule(
                path, "R-UNIVERSAL", "The output must work for every declared input class.", "8"
            )
            self._checklist(
                path,
                item_id="C-UNIVERSAL",
                rule_id="R-UNIVERSAL",
                rule_record_id=rule["record_id"],
                partitions=["observed"],
                required_partitions=["observed", "unobserved"],
            )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-UNIVERSAL",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "public/example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "acceptance_assessment",
                    "checklist_item_ids": ["C-UNIVERSAL"],
                    "ready_item_ids": ["C-UNIVERSAL"],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": ["C-UNIVERSAL"],
                    "checklist_assessments": {
                        "C-UNIVERSAL": {
                            "status": "unknown",
                            "witness_fact_receipt_ids": [],
                        }
                    },
                },
            )
            direction = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-UNIVERSAL",
                    "position_ref": position["record_id"],
                    "statement": "Probe every required behavior before completion.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "evidence_refs": [],
                    "checklist_item_ids": ["C-UNIVERSAL"],
                    "ready_item_ids": ["C-UNIVERSAL"],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": ["C-UNIVERSAL"],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position["record_id"],
                    "direction_record_ids": [direction["record_id"]],
                    "selected_direction_record_id": direction["record_id"],
                },
            )

            report = graph_doctor(path)
            self.assertEqual("structurally_valid_but_incomplete", report["classification"])
            self.assertIn(
                "checklist_partition_coverage_missing:C-UNIVERSAL:unobserved",
                report["incomplete_reasons"],
            )
            self.assertFalse(report["task_truth_assessed"])
            self.assertFalse(report["pass_assessed"])
            self.assertFalse(report["blocking_gate"])

    def test_graph_doctor_detects_a_missing_typed_rule_coverage_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            compilation = compile_typed_rule_ir(TypedRuleCompilerTests._ir())
            rule_body = compilation["rule_bodies"][0]
            rule = self._append(path, "rule_proposal", rule_body)
            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": rule_body["rule_id"],
                    "rule_record_id": rule["record_id"],
                    "authority_ref": rule_body["source_ref"],
                    "authority_digest": rule_body["source_digest"],
                    "receipt_ref": "receipt:typed-rule",
                },
                actor="runner",
            )
            first = dict(compilation["checklist_templates"][0])
            first["source_rule_record_id"] = rule["record_id"]
            self._append(path, "acceptance_checklist_item", first)

            report = graph_doctor(path)
            coverage = report["typed_rule_coverage"][rule_body["rule_id"]]
            self.assertEqual(5, len(coverage["missing_checklist_item_ids"]))
            for item_id in coverage["missing_checklist_item_ids"]:
                self.assertIn(
                    f"typed_rule_coverage_cell_missing:R-COVERAGE:{item_id}",
                    report["incomplete_reasons"],
                )
            self.assertEqual(
                "structurally_valid_but_incomplete", report["classification"]
            )
            self.assertFalse(report["blocking_gate"])

    def test_graph_doctor_detects_temporal_witness_operator_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            ir = TypedRuleCompilerTests._ir(
                rule_kind="temporal_conditional", operators=["ordered_before"]
            )
            semantics = ir["rules"][0]["semantics"]
            semantics["quantifier"]["subjects"] = ["artifact"]
            semantics["conditions"] = [semantics["conditions"][0]]
            compilation = compile_typed_rule_ir(ir)
            rule_body = compilation["rule_bodies"][0]
            rule = self._append(path, "rule_proposal", rule_body)
            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": rule_body["rule_id"],
                    "rule_record_id": rule["record_id"],
                    "authority_ref": rule_body["source_ref"],
                    "authority_digest": rule_body["source_digest"],
                    "receipt_ref": "receipt:temporal-rule",
                },
                actor="runner",
            )
            item = dict(compilation["checklist_templates"][0])
            item["source_rule_record_id"] = rule["record_id"]
            self._append(path, "acceptance_checklist_item", item)
            item_id = item["checklist_item_id"]
            initial = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-TEMPORAL-0",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "public/temporal-example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "acceptance_assessment",
                    "checklist_item_ids": [item_id],
                    "ready_item_ids": [item_id],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [item_id],
                    "checklist_assessments": {
                        item_id: {
                            "status": "unknown",
                            "witness_fact_receipt_ids": [],
                        }
                    },
                },
            )
            fact = self._append(
                path,
                "fact_proposal",
                {
                    "fact_id": "F-TIMELESS-UNION",
                    "statement": "The combined set contains the expected members.",
                    "evidence_ref": "probe:set-union",
                    "evidence_digest": "sha256:" + "7" * 64,
                    "position_ref": initial["record_id"],
                    "witness_bindings": [
                        {
                            "checklist_item_id": item_id,
                            "source_rule_semantics_digest": item[
                                "source_rule_semantics_digest"
                            ],
                            "operators": ["set_equality"],
                        }
                    ],
                },
            )
            receipt = self._append(
                path,
                "fact_admission",
                {
                    "fact_id": "F-TIMELESS-UNION",
                    "fact_record_id": fact["record_id"],
                    "admission_rule_id": rule_body["rule_id"],
                    "admission_rule_record_id": rule["record_id"],
                    "admitter_ref": "worker:replay",
                    "receipt_ref": "receipt:timeless-union",
                },
            )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-TEMPORAL-1",
                    "previous_position_ref": initial["record_id"],
                    "task_identity": {"task_ref": "public/temporal-example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "acceptance_assessment",
                    "checklist_item_ids": [item_id],
                    "ready_item_ids": [],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [],
                    "checklist_assessments": {
                        item_id: {
                            "status": "pass",
                            "witness_fact_receipt_ids": [receipt["record_id"]],
                        }
                    },
                },
            )
            direction = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-TEMPORAL",
                    "position_ref": position["record_id"],
                    "statement": "Re-check the declared temporal relationship.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "evidence_refs": ["probe:set-union"],
                    "checklist_item_ids": [item_id],
                    "ready_item_ids": [],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position["record_id"],
                    "direction_record_ids": [direction["record_id"]],
                    "selected_direction_record_id": direction["record_id"],
                },
            )

            report = graph_doctor(path)
            self.assertIn(
                f"checklist_witness_operators_missing:{item_id}:ordered_before",
                report["incomplete_reasons"],
            )
            self.assertEqual(
                "structurally_valid_but_incomplete", report["classification"]
            )
            self.assertFalse(report["task_truth_assessed"])
            self.assertFalse(report["pass_assessed"])
            self.assertFalse(report["blocking_gate"])

    def test_v2_optional_not_applicable_requires_fact_and_resolves_without_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            ir = TypedRuleCompilerTests._v2_ir(requirement_level="optional")
            semantics = ir["rules"][0]["semantics"]
            semantics["quantifier"]["subjects"] = ["optional-item"]
            compilation = compile_typed_rule_ir(ir)
            rule_body = compilation["rule_bodies"][0]
            rule = self._append(path, "rule_proposal", rule_body)
            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": rule_body["rule_id"],
                    "rule_record_id": rule["record_id"],
                    "authority_ref": rule_body["source_ref"],
                    "authority_digest": rule_body["source_digest"],
                    "receipt_ref": "receipt:optional-rule",
                },
                actor="runner",
            )
            item = dict(compilation["checklist_templates"][0])
            item["source_rule_record_id"] = rule["record_id"]
            self._append(path, "acceptance_checklist_item", item)
            item_id = item["checklist_item_id"]
            initial = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-OPTIONAL-0",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "public/optional-example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "acceptance_assessment",
                    "checklist_item_ids": [item_id],
                    "ready_item_ids": [item_id],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [item_id],
                    "checklist_assessments": {
                        item_id: {
                            "status": "unknown",
                            "applicability_status": "unresolved",
                            "witness_fact_receipt_ids": [],
                        }
                    },
                },
            )
            before_invalid = path.read_bytes()
            with self.assertRaisesRegex(
                CorridorKitError, "requires unknown status and a Fact witness"
            ):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-OPTIONAL-INVALID",
                        "previous_position_ref": initial["record_id"],
                        "task_identity": {"task_ref": "public/optional-example"},
                        "scope": {"working_set": ["/workspace"]},
                        "role_assignments": {"executor": "worker", "reviewer": "qa"},
                        "rule_record_ids": [rule["record_id"]],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": [],
                        "checkpoint_kind": "acceptance_assessment",
                        "checklist_item_ids": [item_id],
                        "ready_item_ids": [],
                        "blocked_item_ids": [],
                        "unresolved_checklist_item_ids": [],
                        "checklist_assessments": {
                            item_id: {
                                "status": "unknown",
                                "applicability_status": "not_applicable",
                                "witness_fact_receipt_ids": [],
                            }
                        },
                    },
                )
            self.assertEqual(before_invalid, path.read_bytes())
            fact = self._append(
                path,
                "fact_proposal",
                {
                    "fact_id": "F-OPTIONAL-ABSENT",
                    "statement": "The conditional optional item is absent.",
                    "evidence_ref": "probe:optional-absence",
                    "evidence_digest": "sha256:" + "7" * 64,
                    "position_ref": initial["record_id"],
                },
            )
            receipt = self._append(
                path,
                "fact_admission",
                {
                    "fact_id": "F-OPTIONAL-ABSENT",
                    "fact_record_id": fact["record_id"],
                    "admission_rule_id": rule_body["rule_id"],
                    "admission_rule_record_id": rule["record_id"],
                    "admitter_ref": "worker:applicability-probe",
                    "receipt_ref": "receipt:optional-absence",
                },
            )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-OPTIONAL-1",
                    "previous_position_ref": initial["record_id"],
                    "task_identity": {"task_ref": "public/optional-example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "acceptance_assessment",
                    "checklist_item_ids": [item_id],
                    "ready_item_ids": [],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [],
                    "checklist_assessments": {
                        item_id: {
                            "status": "unknown",
                            "applicability_status": "not_applicable",
                            "witness_fact_receipt_ids": [receipt["record_id"]],
                        }
                    },
                },
            )
            direction = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-OPTIONAL-CLOSED",
                    "position_ref": position["record_id"],
                    "statement": "Continue with the remaining applicable Rules.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "evidence_refs": ["probe:optional-absence"],
                    "checklist_item_ids": [item_id],
                    "ready_item_ids": [],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position["record_id"],
                    "direction_record_ids": [direction["record_id"]],
                    "selected_direction_record_id": direction["record_id"],
                },
            )
            report = graph_doctor(path)
            self.assertEqual("acceptance_assessed_complete", report["classification"])
            self.assertNotIn(
                f"checklist_not_passed:{item_id}", report["incomplete_reasons"]
            )
            self.assertFalse(report["pass_assessed"])
            self.assertFalse(report["blocking_gate"])

    def test_dependency_frontier_reprojection_and_invalidation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            rule = self._ratified_rule(
                path, "R-WORK", "Verify prerequisites before dependent work.", "9"
            )
            self._checklist(
                path,
                item_id="C-FIRST",
                rule_id="R-WORK",
                rule_record_id=rule["record_id"],
                partitions=["first"],
                required_partitions=["first"],
            )
            self._checklist(
                path,
                item_id="C-SECOND",
                rule_id="R-WORK",
                rule_record_id=rule["record_id"],
                partitions=["second"],
                required_partitions=["second"],
            )
            self._append(
                path,
                "typed_dependency",
                {
                    "dependency_id": "DEP-ORDER",
                    "dependency_kind": "work",
                    "from_ref": "C-SECOND",
                    "to_ref": "C-FIRST",
                    "relationship": "requires",
                    "source_rule_id": "R-WORK",
                    "source_rule_record_id": rule["record_id"],
                },
            )
            before_cycle = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "hard dependency graph contains a cycle"):
                append_graph_record(
                    path,
                    record_type="typed_dependency",
                    actor="worker",
                    body={
                        "dependency_id": "DEP-CYCLE",
                        "dependency_kind": "work",
                        "from_ref": "C-FIRST",
                        "to_ref": "C-SECOND",
                        "relationship": "requires",
                        "source_rule_id": "R-WORK",
                        "source_rule_record_id": rule["record_id"],
                    },
                )
            self.assertEqual(before_cycle, path.read_bytes())
            self._append(
                path,
                "typed_dependency",
                {
                    "dependency_id": "DEP-INVALIDATE",
                    "dependency_kind": "work",
                    "from_ref": "C-FIRST",
                    "to_ref": "C-SECOND",
                    "relationship": "invalidates",
                    "source_rule_id": "R-WORK",
                    "source_rule_record_id": rule["record_id"],
                },
            )
            self._append(
                path,
                "typed_dependency",
                {
                    "dependency_id": "DEP-CONFLICT",
                    "dependency_kind": "work",
                    "from_ref": "C-FIRST",
                    "to_ref": "C-SECOND",
                    "relationship": "conflicts",
                    "source_rule_id": "R-WORK",
                    "source_rule_record_id": rule["record_id"],
                },
            )
            conflict_position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-CONFLICT",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "public/example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "row_progress",
                    "checklist_item_ids": ["C-FIRST", "C-SECOND"],
                    "ready_item_ids": [],
                    "blocked_item_ids": ["C-FIRST", "C-SECOND"],
                    "unresolved_checklist_item_ids": ["C-FIRST", "C-SECOND"],
                    "checklist_assessments": {
                        item: {"status": "unknown", "witness_fact_receipt_ids": []}
                        for item in ("C-FIRST", "C-SECOND")
                    },
                },
            )
            self._append(
                path,
                "dependency_resolution",
                {
                    "dependency_id": "DEP-CONFLICT",
                    "resolution": "precedence",
                    "winner_ref": "C-FIRST",
                    "authority_rule_id": "R-WORK",
                    "authority_rule_record_id": rule["record_id"],
                    "receipt_ref": "receipt:conflict-precedence",
                },
                actor="runner",
            )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-READY",
                    "previous_position_ref": conflict_position["record_id"],
                    "task_identity": {"task_ref": "public/example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "row_progress",
                    "checklist_item_ids": ["C-FIRST", "C-SECOND"],
                    "ready_item_ids": ["C-FIRST"],
                    "blocked_item_ids": ["C-SECOND"],
                    "unresolved_checklist_item_ids": ["C-FIRST", "C-SECOND"],
                    "checklist_assessments": {
                        item: {"status": "unknown", "witness_fact_receipt_ids": []}
                        for item in ("C-FIRST", "C-SECOND")
                    },
                },
            )
            premature = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-PREMATURE",
                    "position_ref": position["record_id"],
                    "statement": "Start only the ready prerequisite; acceptance remains unknown.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "evidence_refs": [],
                    "checklist_item_ids": ["C-FIRST", "C-SECOND"],
                    "ready_item_ids": ["C-FIRST"],
                    "blocked_item_ids": ["C-SECOND"],
                    "unresolved_checklist_item_ids": ["C-FIRST", "C-SECOND"],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position["record_id"],
                    "direction_record_ids": [premature["record_id"]],
                    "selected_direction_record_id": premature["record_id"],
                },
            )
            premature_report = graph_doctor(path)
            self.assertEqual(
                "structurally_valid_but_incomplete",
                premature_report["classification"],
            )
            self.assertIn(
                "checklist_not_passed:C-FIRST",
                premature_report["incomplete_reasons"],
            )
            before = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "Direction ready_item_ids"):
                append_graph_record(
                    path,
                    record_type="direction_proposal",
                    actor="worker",
                    body={
                        "direction_id": "D-STALE",
                        "position_ref": position["record_id"],
                        "statement": "Skip the prerequisite.",
                        "rule_record_ids": [rule["record_id"]],
                        "fact_receipt_ids": [],
                        "evidence_refs": [],
                        "checklist_item_ids": ["C-FIRST", "C-SECOND"],
                        "ready_item_ids": ["C-SECOND"],
                        "blocked_item_ids": ["C-FIRST"],
                        "unresolved_checklist_item_ids": ["C-FIRST", "C-SECOND"],
                    },
                )
            self.assertEqual(before, path.read_bytes())

            # A changed upstream assessment may not carry a dependent PASS forward.
            before = path.read_bytes()
            with self.assertRaisesRegex(CorridorKitError, "invalidate downstream"):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-BAD-CARRY",
                        "previous_position_ref": position["record_id"],
                        "task_identity": {"task_ref": "public/example"},
                        "scope": {"working_set": ["/workspace"]},
                        "role_assignments": {"executor": "worker", "reviewer": "qa"},
                        "rule_record_ids": [rule["record_id"]],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": [],
                        "checkpoint_kind": "acceptance_assessment",
                        "checklist_item_ids": ["C-FIRST", "C-SECOND"],
                        "ready_item_ids": [],
                        "blocked_item_ids": [],
                        "unresolved_checklist_item_ids": [],
                        "checklist_assessments": {
                            "C-FIRST": {"status": "pass", "witness_fact_receipt_ids": []},
                            "C-SECOND": {"status": "pass", "witness_fact_receipt_ids": []},
                        },
                    },
                )
            self.assertEqual(before, path.read_bytes())

            doctor = graph_doctor(path)
            self.assertEqual("structurally_valid_but_incomplete", doctor["classification"])
            self.assertEqual(["C-FIRST"], doctor["ready_item_ids"])
            self.assertEqual(["C-SECOND"], doctor["blocked_item_ids"])
            self.assertLess(
                doctor["hard_dependency_topological_order"].index("C-FIRST"),
                doctor["hard_dependency_topological_order"].index("C-SECOND"),
            )

    def test_position_binds_only_the_complete_latest_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            rule = self._ratified_rule(
                path, "R-ARTIFACT", "Track the current declared artifact.", "d"
            )
            self._checklist(
                path,
                item_id="C-ARTIFACT",
                rule_id="R-ARTIFACT",
                rule_record_id=rule["record_id"],
                partitions=["current-revision"],
                required_partitions=["current-revision"],
            )

            def position_body(
                position_id: str,
                previous_position_ref: str | None,
                artifact_record_ids: list[str],
            ) -> dict:
                return {
                    "position_id": position_id,
                    "previous_position_ref": previous_position_ref,
                    "task_identity": {"task_ref": "public/example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {
                        "executor": "worker",
                        "reviewer": "qa",
                    },
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": artifact_record_ids,
                    "checkpoint_kind": "row_progress",
                    "checklist_item_ids": ["C-ARTIFACT"],
                    "ready_item_ids": ["C-ARTIFACT"],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": ["C-ARTIFACT"],
                    "checklist_assessments": {
                        "C-ARTIFACT": {
                            "status": "unknown",
                            "witness_fact_receipt_ids": [],
                        }
                    },
                }

            intake = self._append(
                path, "position_checkpoint", position_body("P-INTAKE", None, [])
            )
            artifact_v1 = self._append(
                path,
                "artifact_revision",
                {
                    "artifact_id": "A-OUTPUT",
                    "path": "/workspace/output",
                    "digest": "sha256:" + "1" * 64,
                    "position_ref": intake["record_id"],
                    "revision": 1,
                },
            )
            before_omission = path.read_bytes()
            with self.assertRaisesRegex(
                CorridorKitError, "whole current latest artifact revision set"
            ):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body=position_body("P-OMITS-A1", intake["record_id"], []),
                )
            self.assertEqual(before_omission, path.read_bytes())

            position_v1 = self._append(
                path,
                "position_checkpoint",
                position_body("P-A1", intake["record_id"], [artifact_v1["record_id"]]),
            )
            direction_v1 = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-A1",
                    "position_ref": position_v1["record_id"],
                    "statement": "Continue from the first artifact revision.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "evidence_refs": [],
                    "checklist_item_ids": ["C-ARTIFACT"],
                    "ready_item_ids": ["C-ARTIFACT"],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": ["C-ARTIFACT"],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position_v1["record_id"],
                    "direction_record_ids": [direction_v1["record_id"]],
                    "selected_direction_record_id": direction_v1["record_id"],
                },
            )
            artifact_v2 = self._append(
                path,
                "artifact_revision",
                {
                    "artifact_id": "A-OUTPUT",
                    "path": "/workspace/output",
                    "digest": "sha256:" + "2" * 64,
                    "position_ref": position_v1["record_id"],
                    "revision": 2,
                },
            )
            before_stale = path.read_bytes()
            with self.assertRaisesRegex(
                CorridorKitError, "whole current latest artifact revision set"
            ):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body=position_body(
                        "P-STALE-A1",
                        position_v1["record_id"],
                        [artifact_v1["record_id"]],
                    ),
                )
            self.assertEqual(before_stale, path.read_bytes())

            position_v2 = self._append(
                path,
                "position_checkpoint",
                position_body(
                    "P-A2", position_v1["record_id"], [artifact_v2["record_id"]]
                ),
            )
            before_reprojection = graph_doctor(path)
            self.assertEqual(position_v2["record_id"], before_reprojection["latest_position_ref"])
            self.assertIn(
                "no_direction_for_latest_position",
                before_reprojection["incomplete_reasons"],
            )
            direction_v2 = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-A2",
                    "position_ref": position_v2["record_id"],
                    "statement": "Continue from the current artifact revision.",
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "evidence_refs": [],
                    "checklist_item_ids": ["C-ARTIFACT"],
                    "ready_item_ids": ["C-ARTIFACT"],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": ["C-ARTIFACT"],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": position_v2["record_id"],
                    "direction_record_ids": [direction_v2["record_id"]],
                    "selected_direction_record_id": direction_v2["record_id"],
                },
            )
            doctor = graph_doctor(path)
            self.assertEqual(position_v2["record_id"], doctor["latest_position_ref"])
            self.assertEqual(direction_v2["record_id"], doctor["direction_digest"])
            self.assertNotIn(
                "no_direction_for_latest_position", doctor["incomplete_reasons"]
            )

    def test_graph_doctor_complete_is_witness_bound_but_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            admit_rule = self._ratified_rule(
                path, "R-ADMIT", "Admit only replay-bound evidence.", "a"
            )
            task_rule = self._ratified_rule(
                path, "R-TASK", "Produce the declared output.", "b"
            )
            self._checklist(
                path,
                item_id="C-ADMIT",
                rule_id="R-ADMIT",
                rule_record_id=admit_rule["record_id"],
                partitions=["receipt"],
                required_partitions=["receipt"],
            )
            self._checklist(
                path,
                item_id="C-TASK",
                rule_id="R-TASK",
                rule_record_id=task_rule["record_id"],
                partitions=["declared-output"],
                required_partitions=["declared-output"],
            )
            intake = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-INTAKE-NEW",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "public/example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [admit_rule["record_id"], task_rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "row_progress",
                    "checklist_item_ids": ["C-ADMIT", "C-TASK"],
                    "ready_item_ids": ["C-ADMIT", "C-TASK"],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": ["C-ADMIT", "C-TASK"],
                    "checklist_assessments": {
                        "C-ADMIT": {"status": "unknown", "witness_fact_receipt_ids": []},
                        "C-TASK": {"status": "unknown", "witness_fact_receipt_ids": []}
                    },
                },
            )
            fact = self._append(
                path,
                "fact_proposal",
                {
                    "fact_id": "F-OUTPUT",
                    "statement": "The declared output passed its replay.",
                    "evidence_ref": "replay:output",
                    "evidence_digest": "sha256:" + "c" * 64,
                    "position_ref": intake["record_id"],
                },
            )
            receipt = self._append(
                path,
                "fact_admission",
                {
                    "fact_id": "F-OUTPUT",
                    "fact_record_id": fact["record_id"],
                    "admission_rule_id": "R-ADMIT",
                    "admission_rule_record_id": admit_rule["record_id"],
                    "admitter_ref": "worker:replay",
                    "receipt_ref": "receipt:output",
                },
            )
            before_omission = path.read_bytes()
            with self.assertRaisesRegex(
                CorridorKitError, "whole current admitted Fact receipt set"
            ):
                append_graph_record(
                    path,
                    record_type="position_checkpoint",
                    actor="worker",
                    body={
                        "position_id": "P-OMITS-ADMITTED-FACT",
                        "previous_position_ref": intake["record_id"],
                        "task_identity": {"task_ref": "public/example"},
                        "scope": {"working_set": ["/workspace"]},
                        "role_assignments": {
                            "executor": "worker",
                            "reviewer": "qa",
                        },
                        "rule_record_ids": [
                            admit_rule["record_id"],
                            task_rule["record_id"],
                        ],
                        "fact_receipt_ids": [],
                        "artifact_record_ids": [],
                        "checkpoint_kind": "row_progress",
                        "checklist_item_ids": ["C-ADMIT", "C-TASK"],
                        "ready_item_ids": ["C-ADMIT", "C-TASK"],
                        "blocked_item_ids": [],
                        "unresolved_checklist_item_ids": ["C-ADMIT", "C-TASK"],
                        "checklist_assessments": {
                            "C-ADMIT": {
                                "status": "unknown",
                                "witness_fact_receipt_ids": [],
                            },
                            "C-TASK": {
                                "status": "unknown",
                                "witness_fact_receipt_ids": [],
                            },
                        },
                    },
                )
            self.assertEqual(before_omission, path.read_bytes())
            accepted = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-ACCEPTED",
                    "previous_position_ref": intake["record_id"],
                    "task_identity": {"task_ref": "public/example"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [admit_rule["record_id"], task_rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "artifact_record_ids": [],
                    "checkpoint_kind": "acceptance_assessment",
                    "checklist_item_ids": ["C-ADMIT", "C-TASK"],
                    "ready_item_ids": [],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [],
                    "checklist_assessments": {
                        "C-ADMIT": {
                            "status": "pass",
                            "witness_fact_receipt_ids": [receipt["record_id"]],
                        },
                        "C-TASK": {
                            "status": "pass",
                            "witness_fact_receipt_ids": [receipt["record_id"]],
                        }
                    },
                },
            )
            before_direction = graph_doctor(path)
            self.assertEqual(
                "structurally_valid_but_incomplete",
                before_direction["classification"],
            )
            self.assertIn(
                "no_direction_for_latest_position",
                before_direction["incomplete_reasons"],
            )
            direction = self._append(
                path,
                "direction_proposal",
                {
                    "direction_id": "D-DONE",
                    "position_ref": accepted["record_id"],
                    "statement": "Return the verified output.",
                    "rule_record_ids": [task_rule["record_id"]],
                    "fact_receipt_ids": [receipt["record_id"]],
                    "evidence_refs": ["replay:output"],
                    "checklist_item_ids": ["C-ADMIT", "C-TASK"],
                    "ready_item_ids": [],
                    "blocked_item_ids": [],
                    "unresolved_checklist_item_ids": [],
                },
            )
            self._append(
                path,
                "direction_snapshot",
                {
                    "position_ref": accepted["record_id"],
                    "direction_record_ids": [direction["record_id"]],
                    "selected_direction_record_id": direction["record_id"],
                },
            )

            report = graph_doctor(path)
            self.assertEqual("acceptance_assessed_complete", report["classification"])
            self.assertTrue(report["structurally_valid"])
            self.assertIsNotNone(report["acceptance_root"])
            self.assertFalse(report["task_truth_assessed"])
            self.assertFalse(report["pass_assessed"])
            self.assertFalse(report["authorizes_mutation"])

            path.write_text("{}\n", encoding="utf-8")
            invalid = graph_doctor(path)
            self.assertEqual("structurally_invalid", invalid["classification"])
            self.assertFalse(invalid["blocking_gate"])

    def test_graph_index_normalizes_relationships_and_matches_doctor_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            rule = self._ratified_rule(
                path, "R-INDEX", "Run prerequisites in declared order.", "e"
            )
            for item_id in ("C-FIRST", "C-SECOND", "C-THIRD"):
                self._checklist(
                    path,
                    item_id=item_id,
                    rule_id="R-INDEX",
                    rule_record_id=rule["record_id"],
                    partitions=[item_id.lower()],
                    required_partitions=[item_id.lower()],
                )
            position = self._append(
                path,
                "position_checkpoint",
                {
                    "position_id": "P-INDEX",
                    "previous_position_ref": None,
                    "task_identity": {"task_ref": "terminal-bench/index"},
                    "scope": {"working_set": ["/workspace"]},
                    "role_assignments": {"executor": "worker", "reviewer": "qa"},
                    "rule_record_ids": [rule["record_id"]],
                    "fact_receipt_ids": [],
                    "artifact_record_ids": [],
                },
            )
            self._append(
                path,
                "fact_proposal",
                {
                    "fact_id": "F-READY",
                    "statement": "The prerequisite evidence is available.",
                    "evidence_ref": "probe:index-ready",
                    "evidence_digest": "sha256:" + "9" * 64,
                    "position_ref": position["record_id"],
                },
            )
            for dependency in (
                {
                    "dependency_id": "DEP-REQUIRES",
                    "dependency_kind": "work",
                    "from_ref": "C-SECOND",
                    "to_ref": "C-FIRST",
                    "relationship": "requires",
                    "source_rule_id": "R-INDEX",
                    "source_rule_record_id": rule["record_id"],
                },
                {
                    "dependency_id": "DEP-PRECONDITION",
                    "dependency_kind": "work",
                    "from_ref": "C-SECOND",
                    "to_ref": "C-THIRD",
                    "relationship": "precondition_for",
                    "source_rule_id": "R-INDEX",
                    "source_rule_record_id": rule["record_id"],
                },
                {
                    "dependency_id": "DEP-PRODUCES-FACT",
                    "dependency_kind": "evidence",
                    "from_ref": "F-READY",
                    "to_ref": "C-THIRD",
                    "relationship": "produces_fact_for",
                    "source_rule_id": "R-INDEX",
                    "source_rule_record_id": rule["record_id"],
                },
                {
                    "dependency_id": "DEP-INVALIDATES",
                    "dependency_kind": "work",
                    "from_ref": "C-FIRST",
                    "to_ref": "C-THIRD",
                    "relationship": "invalidates",
                    "source_rule_id": "R-INDEX",
                    "source_rule_record_id": rule["record_id"],
                },
                {
                    "dependency_id": "DEP-CONFLICTS",
                    "dependency_kind": "work",
                    "from_ref": "C-FIRST",
                    "to_ref": "C-THIRD",
                    "relationship": "conflicts",
                    "source_rule_id": "R-INDEX",
                    "source_rule_record_id": rule["record_id"],
                },
            ):
                self._append(path, "typed_dependency", dependency)

            index = load_graph_index(path)
            graph_bytes_before_queries = path.read_bytes()
            topology = index.topology()
            self.assertLess(
                topology["topological_order"].index("C-FIRST"),
                topology["topological_order"].index("C-SECOND"),
            )
            self.assertLess(
                topology["topological_order"].index("C-SECOND"),
                topology["topological_order"].index("C-THIRD"),
            )
            self.assertEqual(
                ["C-FIRST", "C-SECOND", "F-READY"],
                index.prerequisite_closure("C-THIRD")["prerequisite_refs"],
            )
            self.assertEqual(
                ["C-FIRST", "C-SECOND", "C-THIRD"],
                index.path("C-FIRST", "C-THIRD")["path"],
            )
            impact = index.impact("C-FIRST")
            self.assertEqual(["C-SECOND", "C-THIRD"], impact["dependant_refs"])
            self.assertEqual(["C-THIRD"], impact["invalidated_refs"])
            self.assertEqual(["C-THIRD"], impact["conflict_refs"])
            self.assertEqual(
                ["F-READY", "C-THIRD"],
                index.path("F-READY", "C-THIRD")["path"],
            )
            self.assertLess(
                topology["topological_order"].index("F-READY"),
                topology["topological_order"].index("C-THIRD"),
            )
            self.assertEqual(
                topology["topological_order"],
                graph_doctor(path)["hard_dependency_topological_order"],
            )
            replay = replay_graph(path)
            self.assertEqual(
                topology["topological_order"],
                replay["graph_index"]["topological_order"],
            )
            self.assertEqual(
                index.frontier()["ready_item_ids"],
                replay["graph_index"]["frontier"]["ready_item_ids"],
            )
            self.assertEqual(
                index.rule_closure("R-INDEX")["closure_identity"],
                replay["graph_index"]["rule_closures"]["R-INDEX"][
                    "closure_identity"
                ],
            )
            closure = index.rule_closure("R-INDEX")
            self.assertEqual("legacy_ratified", closure["status"])
            self.assertFalse(closure["authorizes_mutation"])
            self.assertNotEqual(index.graph_digest, index.graph_bytes_digest)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "corridor_kit",
                    "graph",
                    "query",
                    str(path),
                    "--kind",
                    "path",
                    "--ref",
                    "C-FIRST",
                    "--target-ref",
                    "C-THIRD",
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(
                ["C-FIRST", "C-SECOND", "C-THIRD"],
                json.loads(completed.stdout)["path"],
            )
            self.assertEqual(graph_bytes_before_queries, path.read_bytes())

    def test_rule_closure_diff_and_revision_invalidation_impact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            base = self._ratified_rule(
                path, "R-BASE", "Establish the prerequisite.", "a"
            )
            dependant = self._ratified_rule(
                path, "R-DEPENDANT", "Consume the prerequisite.", "b"
            )
            self._checklist(
                path,
                item_id="C-BASE-V1",
                rule_id="R-BASE",
                rule_record_id=base["record_id"],
                partitions=["base-v1"],
                required_partitions=["base-v1"],
            )
            self._append(
                path,
                "rule_dependency",
                {
                    "from_rule_id": "R-DEPENDANT",
                    "to_rule_id": "R-BASE",
                    "relationship": "requires",
                },
            )
            revised = self._append(
                path,
                "rule_revision",
                {
                    "rule_id": "R-BASE",
                    "statement": "Establish the revised prerequisite.",
                    "source_ref": "official-task:R-BASE",
                    "source_digest": "sha256:" + "a" * 64,
                    "supersedes_record_id": base["record_id"],
                },
            )
            invalidated = load_graph_index(path).rule_closure("R-BASE")
            self.assertEqual("invalidated", invalidated["status"])
            self.assertTrue(invalidated["invalidation_impact"]["invalidated"])
            self.assertEqual(
                ["R-DEPENDANT"],
                invalidated["invalidation_impact"]["affected_dependant_refs"],
            )
            self.assertIsNone(invalidated["closure_contents"])
            self.assertIsNotNone(
                invalidated["closure_diff"]["previous_closure_contents"]
            )

            self._append(
                path,
                "rule_ratification",
                {
                    "rule_id": "R-BASE",
                    "rule_record_id": revised["record_id"],
                    "authority_ref": "official-task",
                    "authority_digest": "sha256:" + "a" * 64,
                    "receipt_ref": "receipt:R-BASE:v2",
                },
                actor="runner",
            )
            self._checklist(
                path,
                item_id="C-BASE-V2",
                rule_id="R-BASE",
                rule_record_id=revised["record_id"],
                partitions=["base-v2"],
                required_partitions=["base-v2"],
            )
            current = load_graph_index(path).rule_closure("R-BASE")
            self.assertEqual("legacy_ratified", current["status"])
            self.assertTrue(current["closure_diff"]["rule_record_changed"])
            self.assertEqual(
                ["C-BASE-V2"],
                current["closure_diff"]["added_checklist_item_ids"],
            )
            self.assertEqual(
                ["C-BASE-V1"],
                current["closure_diff"]["removed_checklist_item_ids"],
            )
            self.assertEqual(2, len(current["closure_history"]))
            self.assertFalse(current["authorizes_mutation"])

    def test_graph_build_session_validates_and_writes_once_with_zero_write_failures(self) -> None:
        import corridor_kit.graph as graph_module

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "GRAPH.jsonl"
            initialize_graph(path)
            with (
                mock.patch.object(
                    graph_module,
                    "_read_graph_records",
                    wraps=graph_module._read_graph_records,
                ) as read_records,
                mock.patch.object(
                    graph_module,
                    "validate_graph_records",
                    wraps=graph_module.validate_graph_records,
                ) as validate_records,
                mock.patch.object(
                    graph_module,
                    "atomic_write_bytes",
                    wraps=graph_module.atomic_write_bytes,
                ) as write_bytes,
            ):
                session = GraphBuildSession(path)
                session.append(
                    record_type="rule_proposal",
                    actor="worker",
                    body={
                        "rule_id": "R-BATCH",
                        "statement": "Build the whole candidate before committing.",
                        "source_ref": "official-task:batch",
                        "source_digest": "sha256:" + "f" * 64,
                    },
                )
                committed = session.commit()
                self.assertEqual(1, committed["record_count"])
                self.assertEqual(1, read_records.call_count)
                self.assertEqual(1, validate_records.call_count)
                self.assertEqual(1, write_bytes.call_count)

            before = path.read_bytes()
            invalid = GraphBuildSession(path)
            invalid.append(record_type="rule_proposal", actor="worker", body={})
            with self.assertRaises(CorridorKitError):
                invalid.commit()
            self.assertEqual(before, path.read_bytes())

            oversized = GraphBuildSession(path)
            oversized.append(
                record_type="rule_proposal",
                actor="worker",
                body={
                    "rule_id": "R-OVERSIZED",
                    "statement": "x" * MAX_JSON_BYTES,
                    "source_ref": "official-task:oversized",
                    "source_digest": "sha256:" + "a" * 64,
                },
            )
            with self.assertRaisesRegex(CorridorKitError, "candidate exceeds"):
                oversized.commit()
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
