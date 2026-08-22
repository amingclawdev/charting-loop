from __future__ import annotations

import json
import os
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from corridor_kit import (
    ACCEPTANCE_SCHEMA,
    AUTHORING_SCHEMA,
    CAPABILITY_SCHEMA,
    FACT_CANDIDATES_SCHEMA,
    KIT_VERSION,
    WITNESSES_SCHEMA,
    WORK_BACKLOG_SCHEMA,
    CorridorKitError,
    append_admitted_facts,
    append_graph_record,
    append_position_event,
    counterfactual_transition,
    capture_command,
    create_scaffold,
    freeze_submission,
    initialize_graph,
    list_submissions,
    public_world_inventory,
    regular_tree_manifest,
    replay_graph,
    restore_submission,
    runtime_guide,
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
from corridor_kit.core import load_json
from corridor_kit.acceptance import qa_assessment_decision
from corridor_kit.runtime import validate_qa_assessment_path
from corridor_kit.scaffold import validate_method_capsule


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


class GraphKernelTests(unittest.TestCase):
    def _append(self, path: Path, record_type: str, body: dict, actor: str = "worker"):
        return append_graph_record(
            path, record_type=record_type, actor=actor, body=body
        )["record"]

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
            fact = self._append(
                path,
                "fact_proposal",
                {
                    "fact_id": "F-1",
                    "statement": "The target artifact exists.",
                    "evidence_ref": "probe:stat",
                    "evidence_digest": "sha256:" + "2" * 64,
                    "position_ref": "task-intake",
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
                    "previous_position_ref": None,
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
            with self.assertRaisesRegex(CorridorKitError, "unknown artifact"):
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


if __name__ == "__main__":
    unittest.main()
