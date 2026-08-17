from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from corridor_kit import (
    ACCEPTANCE_SCHEMA,
    CorridorKitError,
    capture_command,
    create_scaffold,
    public_world_inventory,
    regular_tree_manifest,
    validate_acceptance_file,
    validate_acceptance_ledger,
)
from corridor_kit.core import load_json


def valid_ledger() -> dict[str, object]:
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
            },
        ],
    }


class AcceptanceLedgerTests(unittest.TestCase):
    def test_valid_complete_ready_ledger(self) -> None:
        report = validate_acceptance_ledger(valid_ledger())
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(report.facts["task_ready"])
        self.assertEqual(report.facts["required_acceptance_ids"], ["AC-1", "AC-2"])

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
            path.read_text(encoding="utf-8") for path in package.glob("*.py")
        )
        self.assertNotIn("import aming_claw", source)
        self.assertNotIn("from aming_claw", source)
        self.assertNotIn("import harbor", source)
        self.assertNotIn("from harbor", source)
        self.assertNotIn("planner_service", source)
        self.assertNotIn("evalbench", source)


if __name__ == "__main__":
    unittest.main()
