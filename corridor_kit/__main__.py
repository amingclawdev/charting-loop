"""Command-line entrypoint for the portable Corridor kit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .acceptance import validate_acceptance_file
from .capabilities import validate_capability_file
from .core import (
    KIT_VERSION,
    CorridorKitError,
    atomic_write_json,
    capture_command,
    load_json,
    public_world_inventory,
    regular_tree_manifest,
)
from .scaffold import create_scaffold, validate_method_capsule
from .domain.binary import (
    binary_diff,
    binary_replay_record,
    builtin_binary_registry,
    elf_inventory,
)
from .runtime import (
    append_position_event,
    counterfactual_transition,
    load_position_timeline,
    load_runtime_guide,
    validate_qa_assessment_path,
    validate_work_files,
)
from .submission import (
    freeze_submission,
    list_submissions,
    restore_submission,
    verify_submission,
)


def _emit(value: Any, output: Path | None = None) -> None:
    if output is None:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(output, value)


def _labeled_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        label, separator, raw_path = value.partition("=")
        if not separator or not label or not raw_path:
            raise CorridorKitError("--root values must use LABEL=PATH")
        if label in roots:
            raise CorridorKitError(f"duplicate public-root label: {label}")
        roots[label] = Path(raw_path)
    return roots


def _json_object(raw: str, *, name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorridorKitError(f"{name} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CorridorKitError(f"{name} must be a JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m corridor_kit",
        description="Task-neutral mechanics for building advisory Corridors",
    )
    parser.add_argument("--version", action="version", version=KIT_VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create an honest uncompiled starter")
    init.add_argument("output", type=Path)
    init.add_argument("--method-version")
    init.add_argument("--method-digest")
    init.add_argument("--method-scope-digest")

    capsule = commands.add_parser("validate-capsule", help="verify a Method capsule binding")
    capsule.add_argument("capsule", type=Path)
    capsule.add_argument("--kit", required=True, type=Path)
    capsule.add_argument("--expected-method-version", required=True)
    capsule.add_argument("--expected-method-digest", required=True)
    capsule.add_argument("--expected-method-scope-digest", required=True)
    capsule.add_argument("--output", type=Path)

    qa = commands.add_parser("qa", help="validate an advisory QA assessment")
    qa_commands = qa.add_subparsers(dest="qa_command", required=True)
    qa_validate = qa_commands.add_parser(
        "validate", help="classify a QA report against the frozen Corridor manifest"
    )
    qa_validate.add_argument("--path", required=True, type=Path)
    qa_validate.add_argument("--freeze", required=True, type=Path)
    qa_validate.add_argument("--output", type=Path)

    validate = commands.add_parser("validate", help="validate an acceptance ledger")
    validate.add_argument("ledger", type=Path)
    validate.add_argument("--allow-draft", action="store_true")
    validate.add_argument("--output", type=Path)

    validate_work = commands.add_parser(
        "validate-work", help="validate work rows against acceptance and capabilities"
    )
    validate_work.add_argument("work", type=Path)
    validate_work.add_argument("--acceptance", required=True, type=Path)
    validate_work.add_argument("--capabilities", required=True, type=Path)
    validate_work.add_argument("--allow-draft", action="store_true")
    validate_work.add_argument("--output", type=Path)

    validate_capabilities = commands.add_parser(
        "validate-capabilities", help="validate a capability registry"
    )
    validate_capabilities.add_argument("registry", type=Path)
    validate_capabilities.add_argument("--allow-draft", action="store_true")
    validate_capabilities.add_argument("--output", type=Path)

    capability = commands.add_parser("capabilities", help="inspect frozen capability packs")
    capability_commands = capability.add_subparsers(dest="capability_command", required=True)
    capability_builtins = capability_commands.add_parser(
        "builtins", help="emit the task-neutral binary capability registry"
    )
    capability_builtins.add_argument("--output", type=Path)

    manifest = commands.add_parser("manifest", help="hash a closed regular-file tree")
    manifest.add_argument("root", type=Path)
    manifest.add_argument("--output", type=Path)

    survey = commands.add_parser("survey", help="inventory labeled public roots")
    survey.add_argument("--root", action="append", required=True, dest="roots")
    survey.add_argument("--output", type=Path)

    capture = commands.add_parser(
        "capture", help="run argv directly and retain replayable stdout/stderr"
    )
    capture.add_argument("--output", required=True, type=Path)
    capture.add_argument("--cwd", type=Path)
    capture.add_argument("--timeout", type=float)
    capture.add_argument("argv", nargs=argparse.REMAINDER)

    timeline = commands.add_parser("timeline", help="append or inspect RAW Position events")
    timeline_commands = timeline.add_subparsers(dest="timeline_command", required=True)
    timeline_append = timeline_commands.add_parser("append", help="append one hash-linked observation")
    timeline_append.add_argument("timeline", type=Path)
    timeline_append.add_argument("--work", required=True, type=Path)
    timeline_append.add_argument("--actor", required=True)
    timeline_append.add_argument("--event-type", required=True)
    timeline_append.add_argument("--status", required=True)
    timeline_append.add_argument("--row-id")
    timeline_append.add_argument("--details-json", default="{}")
    timeline_append.add_argument("--observed-at")
    timeline_list = timeline_commands.add_parser("list", help="verify and list the complete chain")
    timeline_list.add_argument("timeline", type=Path)

    runtime = commands.add_parser("runtime", help="project current row, Guide, or reminders")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    for command_name in ("current", "guide", "reminders", "counterfactual"):
        command = runtime_commands.add_parser(command_name)
        command.add_argument("--work", required=True, type=Path)
        command.add_argument("--acceptance", required=True, type=Path)
        command.add_argument("--capabilities", required=True, type=Path)
        command.add_argument("--timeline", required=True, type=Path)
        if command_name == "counterfactual":
            command.add_argument("--substitute-position", type=Path)
            command.add_argument("--substitute-acceptance", type=Path)

    binary = commands.add_parser("binary", help="generic read-only binary capability pack")
    binary_commands = binary.add_subparsers(dest="binary_command", required=True)
    inventory = binary_commands.add_parser("inventory", help="inventory an ELF header")
    inventory.add_argument("path", type=Path)
    diff = binary_commands.add_parser("diff", help="report changed binary byte ranges")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    replay = binary_commands.add_parser("replay", help="bind argv to labeled input identities")
    replay.add_argument("--input", action="append", required=True, dest="inputs")
    replay.add_argument("argv", nargs=argparse.REMAINDER)

    submission = commands.add_parser(
        "submission", help="freeze, verify, list, or restore task-declared versions"
    )
    submission_commands = submission.add_subparsers(
        dest="submission_command", required=True
    )
    submission_freeze = submission_commands.add_parser(
        "freeze", help="atomically freeze one complete submission version"
    )
    submission_freeze.add_argument("--root", required=True, type=Path)
    submission_freeze.add_argument("--role", required=True, choices=("worker", "qa"))
    submission_freeze.add_argument("--path", action="append", required=True, dest="paths")
    for command_name in ("verify", "list", "restore"):
        command = submission_commands.add_parser(command_name)
        command.add_argument("--root", required=True, type=Path)
        command.add_argument("--role", required=True, choices=("worker", "qa"))
        if command_name in ("verify", "restore"):
            command.add_argument("--snapshot-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            created = create_scaffold(
                args.output,
                method_version=args.method_version,
                method_digest=args.method_digest,
                method_scope_digest=args.method_scope_digest,
            )
            _emit({"ok": True, "kit_version": KIT_VERSION, "output": str(created)})
            return 0
        if args.command == "validate-capsule":
            kit = load_json(args.kit)
            errors = validate_method_capsule(
                load_json(args.capsule),
                expected_method_version=args.expected_method_version,
                expected_method_digest=args.expected_method_digest,
                expected_method_scope_digest=args.expected_method_scope_digest,
                expected_capsule_digest=(
                    kit.get("method_capsule_digest")
                    if isinstance(kit, dict)
                    else ""
                ),
            )
            report = {"ok": not errors, "errors": errors}
            _emit(report, args.output)
            return 0 if not errors else 1
        if args.command == "qa" and args.qa_command == "validate":
            report = validate_qa_assessment_path(args.path, args.freeze)
            _emit(report, args.output)
            return 0 if report["valid"] else 1
        if args.command == "validate":
            report = validate_acceptance_file(
                args.ledger, allow_draft=args.allow_draft
            ).as_dict()
            _emit(report, args.output)
            return 0 if report["ok"] else 1
        if args.command == "validate-work":
            report = validate_work_files(
                args.work,
                acceptance_path=args.acceptance,
                capability_path=args.capabilities,
                allow_draft=args.allow_draft,
            ).as_dict()
            _emit(report, args.output)
            return 0 if report["ok"] else 1
        if args.command == "validate-capabilities":
            report = validate_capability_file(
                args.registry, allow_draft=args.allow_draft
            ).as_dict()
            _emit(report, args.output)
            return 0 if report["ok"] else 1
        if args.command == "capabilities" and args.capability_command == "builtins":
            _emit(builtin_binary_registry(), args.output)
            return 0
        if args.command == "manifest":
            _emit(regular_tree_manifest(args.root), args.output)
            return 0
        if args.command == "survey":
            _emit(public_world_inventory(_labeled_roots(args.roots)), args.output)
            return 0
        if args.command == "capture":
            command = list(args.argv)
            if command and command[0] == "--":
                command = command[1:]
            report = capture_command(
                command,
                args.output,
                cwd=args.cwd,
                timeout_seconds=args.timeout,
            )
            _emit(report)
            return 0 if report["status"] == "completed" and report["exit_code"] == 0 else 1
        if args.command == "timeline" and args.timeline_command == "append":
            work = load_json(args.work)
            if args.row_id is not None:
                known = {
                    item.get("row_id")
                    for item in work.get("rows", [])
                    if isinstance(item, dict)
                }
                if args.row_id not in known:
                    raise CorridorKitError(f"unknown work row: {args.row_id}")
            event = append_position_event(
                args.timeline,
                actor=args.actor,
                event_type=args.event_type,
                status=args.status,
                row_id=args.row_id,
                details=_json_object(args.details_json, name="--details-json"),
                observed_at=args.observed_at,
            )
            _emit(event)
            return 0
        if args.command == "timeline" and args.timeline_command == "list":
            events = load_position_timeline(args.timeline)
            _emit({"ok": True, "event_count": len(events), "events": events})
            return 0
        if args.command == "runtime":
            if args.runtime_command == "counterfactual":
                report = counterfactual_transition(
                    load_json(args.work),
                    load_json(args.acceptance),
                    load_json(args.capabilities),
                    load_position_timeline(args.timeline),
                    substituted_position=(
                        load_json(args.substitute_position)
                        if args.substitute_position is not None
                        else None
                    ),
                    substituted_acceptance=(
                        load_json(args.substitute_acceptance)
                        if args.substitute_acceptance is not None
                        else None
                    ),
                )
                _emit(report)
                return 0
            guide = load_runtime_guide(
                args.work, args.acceptance, args.capabilities, args.timeline
            )
            if args.runtime_command == "guide":
                _emit(guide)
            elif args.runtime_command == "current":
                _emit(guide["position"])
            else:
                _emit({
                    "schema_version": "charting-loop/runtime-reminders/v1",
                    "current_row_id": guide["position"]["current_row_id"],
                    "reminders": guide["reminders"],
                    "advisory_only": True,
                    "authorizes_mutation": False,
                })
            return 0
        if args.command == "binary":
            if args.binary_command == "inventory":
                _emit(elf_inventory(args.path))
            elif args.binary_command == "diff":
                _emit(binary_diff(args.before, args.after))
            else:
                command = list(args.argv)
                if command and command[0] == "--":
                    command = command[1:]
                _emit(binary_replay_record(command, _labeled_roots(args.inputs)))
            return 0
        if args.command == "submission":
            if args.submission_command == "freeze":
                _emit(
                    freeze_submission(
                        args.root,
                        role=args.role,
                        paths=[Path(value) for value in args.paths],
                    )
                )
            elif args.submission_command == "verify":
                _emit(
                    verify_submission(
                        args.root, role=args.role, snapshot_id=args.snapshot_id
                    )
                )
            elif args.submission_command == "list":
                _emit(list_submissions(args.root, role=args.role))
            else:
                _emit(
                    restore_submission(
                        args.root, role=args.role, snapshot_id=args.snapshot_id
                    )
                )
            return 0
    except CorridorKitError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
