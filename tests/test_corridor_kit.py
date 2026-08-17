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
    CAPABILITY_SCHEMA,
    WORK_BACKLOG_SCHEMA,
    CorridorKitError,
    append_position_event,
    capture_command,
    create_scaffold,
    freeze_submission,
    list_submissions,
    public_world_inventory,
    regular_tree_manifest,
    restore_submission,
    runtime_guide,
    sha256_json,
    validate_acceptance_file,
    validate_acceptance_ledger,
    validate_capability_registry,
    validate_work_backlog,
    validate_work_files,
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
            guide = runtime_guide(work, capabilities, load_position_timeline(timeline))
            self.assertEqual("compiled", guide["work_state"])
            self.assertEqual("compiled", guide["capability_state"])
            self.assertEqual("ROW-2", guide["current_row"]["row_id"])
            self.assertEqual(["binary.diff-ranges"], [item["capability_id"] for item in guide["capabilities"]])
            self.assertIn("REM-2", {item["reminder_id"] for item in guide["reminders"]})
            self.assertIs(guide["advisory_only"], True)
            self.assertIs(guide["authorizes_mutation"], False)
            self.assertIs(guide["blocking_gate"], False)

            with self.assertRaises(CorridorKitError):
                append_position_event(
                    timeline,
                    actor="worker",
                    event_type="row_started",
                    status="done",
                    row_id="ROW-2",
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


if __name__ == "__main__":
    unittest.main()
