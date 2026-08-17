"""Command-line entrypoint for the portable Corridor kit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .acceptance import validate_acceptance_file
from .core import (
    KIT_VERSION,
    CorridorKitError,
    atomic_write_json,
    capture_command,
    public_world_inventory,
    regular_tree_manifest,
)
from .scaffold import create_scaffold


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m corridor_kit",
        description="Task-neutral mechanics for building advisory Corridors",
    )
    parser.add_argument("--version", action="version", version=KIT_VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create an honest uncompiled starter")
    init.add_argument("output", type=Path)

    validate = commands.add_parser("validate", help="validate an acceptance ledger")
    validate.add_argument("ledger", type=Path)
    validate.add_argument("--allow-draft", action="store_true")
    validate.add_argument("--output", type=Path)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            created = create_scaffold(args.output)
            _emit({"ok": True, "kit_version": KIT_VERSION, "output": str(created)})
            return 0
        if args.command == "validate":
            report = validate_acceptance_file(
                args.ledger, allow_draft=args.allow_draft
            ).as_dict()
            _emit(report, args.output)
            return 0 if report["ok"] else 1
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
    except CorridorKitError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
