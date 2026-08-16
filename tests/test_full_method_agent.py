from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmark_agents import contract


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def complete_assessment(
    digest: str,
    *,
    outcome: str = "pass",
    acceptance_ids: tuple[str, ...] = ("ACCEPT-1",),
) -> dict[str, object]:
    return {
        "schema_version": contract.ASSESSMENT_SCHEMA,
        "outcome": outcome,
        "summary": "The complete public acceptance map was assessed.",
        "corridor_digest": digest,
        "coverage_complete": True,
        "acceptance_results": [
            {
                "acceptance_id": acceptance_id,
                "applicability": "applicable",
                "status": "pass",
                "evidence": f"Observed passing evidence for {acceptance_id}.",
                "replay": f"Replay the check for {acceptance_id}.",
            }
            for acceptance_id in acceptance_ids
        ],
        "unmapped_requirements": [],
        "unresolved_relations": [],
        "checks": [
            {
                "name": "source coverage",
                "status": "pass",
                "evidence": "Every public normative clause is mapped.",
            }
        ],
        "witnesses": [],
    }


class FullMethodContractTests(unittest.TestCase):
    def test_protocol_and_runbook_fix_the_claim_and_visibility_boundaries(self) -> None:
        protocol = (
            REPOSITORY_ROOT
            / "protocol"
            / "TASK-CONDITIONED-CORRIDOR-BENCHMARK-V3.md"
        ).read_text(encoding="utf-8")
        runbook = (
            REPOSITORY_ROOT / "docs" / "TERMINAL-BENCH-3-RUNBOOK.md"
        ).read_text(encoding="utf-8")

        for marker in (
            "terminal-bench/terminal-bench@3.0.0",
            "74 scored tasks",
            "4 tasks require a GPU",
            "Both Worker and QA receive the same absolute Corridor path",
            "QA never suppresses, replaces, or",
            "short-circuits the benchmark grader",
            "Do not ask the Builder to add a mandatory approval",
            "linear unlock",
            "authority\nlayer is Rule",
            "A Gate does not become a Rule",
            "declared chain",
            "jointly satisfiable",
            "leaderboard score is an end-to-end performance result",
            "ACCEPTANCE.json",
            "Closing one repair witness never implies whole-task closure",
        ):
            self.assertIn(marker, protocol)
        for marker in (
            'export PYTHONPATH="$CHARTING_LOOP_ROOT',
            "--print-config",
            "--upload --private",
            "CODEX_FORCE_AUTH_JSON=1",
            "Do not add a control arm to this job",
            "Do not call this a causal estimate",
        ):
            self.assertIn(marker, runbook)
        self.assertNotIn("--ae CODEX_FORCE_AUTH_JSON=1", runbook)

    def test_worker_and_qa_receive_same_corridor_identity(self) -> None:
        digest = "sha256:" + "a" * 64
        task = "Repair the live system and leave it verifiable."
        worker = contract.worker_prompt(task, digest)
        qa = contract.qa_prompt(
            task,
            digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
        )

        for prompt in (worker, qa):
            self.assertIn(task, prompt)
            self.assertIn(contract.CORRIDOR_PATH, prompt)
            self.assertIn(contract.FREEZE_PATH, prompt)
            self.assertIn(digest, prompt)
        self.assertIn("independent QA", qa)
        self.assertIn("Do not mutate", qa)
        self.assertIn(contract.QA_PATH, qa)
        self.assertIn(contract.ACCEPTANCE_PATH, worker)
        self.assertIn("ACCEPT-1", qa)
        self.assertIn("independently re-read", qa.lower())

    def test_builder_is_task_conditioned_but_must_not_build_a_gate(self) -> None:
        prompt = contract.builder_prompt("Find and repair the fault.")
        self.assertIn("Find and repair the fault.", prompt)
        self.assertIn(contract.METHOD_PATH, prompt)
        self.assertIn(contract.CORRIDOR_PATH, prompt)
        self.assertIn("do not carry out the official task", prompt)
        self.assertIn("do not install a mandatory workflow gate", prompt)
        self.assertIn("not a new governance dependency", prompt)
        self.assertIn(contract.ACCEPTANCE_PATH, prompt)
        self.assertIn(contract.ACCEPTANCE_SCHEMA, prompt)
        self.assertIn("Decompose every normative", prompt)

    def test_fail_requires_a_replayable_witness(self) -> None:
        digest = "sha256:" + "b" * 64
        assessment = complete_assessment(digest, outcome="fail")
        assessment["acceptance_results"][0]["status"] = "fail"
        self.assertIn(
            "FAIL_WITNESS_REQUIRED",
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="complete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
            ),
        )

        assessment["witnesses"] = [
            {
                "acceptance_id": "ACCEPT-1",
                "constraint": "The service must preserve identity.",
                "evidence": "Observed id changed from A to B.",
                "replay": "Read the before/after identity fields.",
            }
        ]
        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="complete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
            ),
        )

    def test_pass_requires_complete_exact_acceptance_coverage(self) -> None:
        digest = "sha256:" + "c" * 64
        assessment = complete_assessment(
            digest, acceptance_ids=("ACCEPT-1", "ACCEPT-2")
        )
        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="complete",
                expected_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
                required_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
            ),
        )

        missing = complete_assessment(digest)
        errors = contract.validate_qa_assessment(
            missing,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
            required_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
        )
        self.assertIn("ASSESSMENT_ACCEPTANCE_ID_MISSING_ACCEPT-2", errors)

        unknown = complete_assessment(
            digest, acceptance_ids=("ACCEPT-1", "UNKNOWN")
        )
        errors = contract.validate_qa_assessment(
            unknown,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn("ASSESSMENT_ACCEPTANCE_ID_UNKNOWN_UNKNOWN", errors)

        duplicate = complete_assessment(digest)
        duplicate["acceptance_results"].append(
            dict(duplicate["acceptance_results"][0])
        )
        errors = contract.validate_qa_assessment(
            duplicate,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn(
            "ASSESSMENT_ACCEPTANCE_ID_DUPLICATE_ACCEPT-1", errors
        )

    def test_incomplete_ledger_cannot_pass_but_can_be_not_assessed(self) -> None:
        digest = "sha256:" + "d" * 64
        assessment = complete_assessment(digest)
        errors = contract.validate_qa_assessment(
            assessment,
            expected_corridor_digest=digest,
            acceptance_ledger_status="incomplete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn("PASS_ACCEPTANCE_LEDGER_COMPLETE_REQUIRED", errors)

        assessment["outcome"] = "not_assessed"
        assessment["coverage_complete"] = False
        assessment["unmapped_requirements"] = ["public-spec.md#metrics"]
        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="incomplete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
            ),
        )

    def test_qa_json_rejects_duplicate_keys_and_non_finite_numbers(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate QA JSON key"):
            contract.load_qa_json_text('{"outcome":"pass","outcome":"fail"}')
        with self.assertRaisesRegex(ValueError, "non-finite QA JSON value"):
            contract.load_qa_json_text('{"value":NaN}')

    def test_corridor_digest_binds_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plain = root / "plain"
            executable = root / "executable"
            plain.mkdir()
            executable.mkdir()
            (plain / "tool").write_text("same bytes\n", encoding="utf-8")
            (executable / "tool").write_text("same bytes\n", encoding="utf-8")
            os.chmod(executable / "tool", 0o755)
            plain_manifest = contract.corridor_manifest(plain)
            executable_manifest = contract.corridor_manifest(executable)
            self.assertFalse(plain_manifest[0]["executable"])
            self.assertTrue(executable_manifest[0]["executable"])
            self.assertNotEqual(
                contract.corridor_digest(plain_manifest),
                contract.corridor_digest(executable_manifest),
            )

    def test_freezer_closes_bytes_and_falls_back_when_builder_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            (root / "method" / "METHOD.md").write_text("method\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            probe = json.loads(completed.stdout)
            self.assertTrue(probe["ok"])
            self.assertEqual("fallback", probe["builder_corridor_status"])

            manifest = json.loads((root / "FREEZE.json").read_text(encoding="utf-8"))
            self.assertEqual(contract.FREEZE_SCHEMA, manifest["schema_version"])
            self.assertEqual(probe["corridor_digest"], manifest["corridor_tree_sha256"])
            self.assertEqual("missing", probe["acceptance_ledger_status"])
            self.assertIn(
                "ACCEPTANCE_LEDGER_MISSING",
                probe["acceptance_ledger_errors"],
            )
            for path in [root / "FREEZE.json", *(root / "corridor").rglob("*")]:
                self.assertEqual(0, stat.S_IMODE(path.stat().st_mode) & 0o222)
                self.assertEqual(0o044, stat.S_IMODE(path.stat().st_mode) & 0o044)
            self.assertEqual(
                0o055,
                stat.S_IMODE((root / "corridor").stat().st_mode) & 0o055,
            )

            verified = subprocess.run(
                [sys.executable, "-c", contract.verify_freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, verified.returncode, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["ok"])

    def test_freezer_records_complete_acceptance_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            corridor = root / "corridor"
            corridor.mkdir()
            (root / "method" / "METHOD.md").write_text(
                "method\n", encoding="utf-8"
            )
            ledger = {
                "schema_version": contract.ACCEPTANCE_SCHEMA,
                "coverage": {
                    "status": "complete",
                    "unmapped_clauses": [],
                    "ambiguous_clauses": [],
                },
                "items": [
                    {
                        "acceptance_id": "ACCEPT-1",
                        "source_ref": "instruction.md#output",
                        "statement": "Write the required output.",
                        "required": True,
                        "definition_state": "defined",
                        "scope": {"path": "/app/output.json"},
                        "rule": {"kind": "file_exists"},
                        "relations": [],
                    }
                ],
            }
            (corridor / "ACCEPTANCE.json").write_text(
                json.dumps(ledger), encoding="utf-8"
            )
            completed = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            identity = json.loads(completed.stdout)
            self.assertEqual("complete", identity["acceptance_ledger_status"])
            self.assertEqual(["ACCEPT-1"], identity["acceptance_ids"])
            self.assertEqual(["ACCEPT-1"], identity["required_acceptance_ids"])
            self.assertEqual([], identity["acceptance_ledger_errors"])

    def test_harbor_adapter_preserves_role_and_verifier_boundaries(self) -> None:
        source = (REPOSITORY_ROOT / "benchmark_agents" / "harbor_agent.py").read_text(
            encoding="utf-8"
        )
        for marker in (
            "builder_prompt(",
            "worker_prompt(",
            "qa_prompt(",
            "repair_prompt(",
            "closure_prompt(",
            "await agent.resume(",
            'self._resume_role(\n                "worker",\n                worker,',
            'self._resume_role(\n                    "qa",\n                    qa,',
            'decision["repair_required"]',
            "subagent_trajectories",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("official verifier", source.lower())
        self.assertNotIn("verifier.run", source)


if __name__ == "__main__":
    unittest.main()
