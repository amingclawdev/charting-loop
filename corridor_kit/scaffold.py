"""Create an honest, task-neutral starting tree for one new Corridor."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .acceptance import ACCEPTANCE_SCHEMA, validate_acceptance_ledger
from .capabilities import starter_capability_registry, validate_capability_registry
from .core import KIT_VERSION, CorridorKitError, atomic_write_bytes, atomic_write_json, sha256_json
from .runtime import starter_work_backlog, validate_work_backlog


SCAFFOLD_SCHEMA = "charting-loop/corridor-kit-scaffold/v1"
METHOD_CAPSULE_SCHEMA = "charting-loop/method-capsule/v1"
EVIDENCE_SCAFFOLD_SCHEMA = "charting-loop/behavior-evidence/v1"
SOURCE_MAP_SCHEMA = "charting-loop/source-map/v1"
REPLAY_SCAFFOLD_SCHEMA = "charting-loop/unprivileged-replay/v1"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def method_capsule(
    *,
    method_version: str | None = None,
    method_digest: str | None = None,
    method_scope_digest: str | None = None,
) -> dict[str, Any]:
    """Return the compact, task-neutral Builder subset of the frozen Method."""

    bound = bool(
        isinstance(method_version, str)
        and method_version.strip()
        and isinstance(method_digest, str)
        and SHA256_RE.fullmatch(method_digest)
        and isinstance(method_scope_digest, str)
        and SHA256_RE.fullmatch(method_scope_digest)
    )
    return {
        "schema_version": METHOD_CAPSULE_SCHEMA,
        "binding_state": "bound" if bound else "unbound",
        "method_version": method_version or "",
        "method_digest": method_digest or "",
        "method_scope_digest": method_scope_digest or "",
        "builder_invariants": [
            "Compile public task Rules into atomic acceptance items with exact source references.",
            "Keep Position evidence separate from Rule authority and project Direction at the current Position.",
            "Map every acceptance item into bounded work rows with replayable done-when evidence.",
            "Record positive, negative, boundary, state, temporal, and coupled obligations.",
            "Keep the Corridor advisory; it must not become a task-execution Gate or authority source.",
            "Freeze no stored answer, evaluator material, credentials, or outcome-derived repair.",
        ],
        "required_surfaces": [
            "ACCEPTANCE.json",
            "WORK_ITEMS.json",
            "CAPABILITIES.json",
            "SOURCE-MAP.json",
            "EVIDENCE.json",
            "REPLAY.json",
        ],
        "task_solution_present": False,
        "authorizes_mutation": False,
        "blocking_gate": False,
    }


def validate_method_capsule(
    value: Any, *, expected_method_digest: str
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["METHOD_CAPSULE_OBJECT_REQUIRED"]
    if value.get("schema_version") != METHOD_CAPSULE_SCHEMA:
        errors.append("METHOD_CAPSULE_SCHEMA")
    if value.get("binding_state") != "bound":
        errors.append("METHOD_CAPSULE_BOUND_REQUIRED")
    if value.get("method_digest") != expected_method_digest:
        errors.append("METHOD_CAPSULE_DIGEST_MISMATCH")
    if value.get("task_solution_present") is not False:
        errors.append("METHOD_CAPSULE_SOLUTION_BOUNDARY")
    if value.get("authorizes_mutation") is not False:
        errors.append("METHOD_CAPSULE_AUTHORITY_BOUNDARY")
    if value.get("blocking_gate") is not False:
        errors.append("METHOD_CAPSULE_GATE_BOUNDARY")
    return errors


def starter_acceptance_ledger() -> dict[str, Any]:
    """Return a structurally honest draft that cannot imply task readiness."""

    return {
        "schema_version": ACCEPTANCE_SCHEMA,
        "coverage": {
            "status": "incomplete",
            "unmapped_clauses": [
                {
                    "source_ref": "public task sources",
                    "statement": "Task clauses have not yet been mapped into atomic acceptance items.",
                    "reason": "This is the uncompiled starter emitted before task inspection.",
                }
            ],
            "ambiguous_clauses": [],
        },
        "construction_readiness": {
            "status": "unresolved",
            "coupled_acceptance_ids": [],
            "replay_entrypoint": "",
            "unresolved_constraints": [
                "Task-specific acceptance, coupled constraints, and replay checks have not yet been compiled."
            ],
        },
        "items": [],
    }


STARTER_README = """# Task-specific Corridor (uncompiled starter)

This directory was initialized from the frozen, task-neutral Corridor kit. It is an
advisory aid, not an answer, an authority source, or a mandatory workflow gate.

Before the Corridor is frozen, the Builder must:

1. Re-read every public task source and replace the starter gap in `ACCEPTANCE.json`
   with atomic acceptance items using exact source references, scope, Rule, typed
   relations, and explicit positive, negative, boundary, state, temporal, and coupled
   verification obligations. When a partition does not apply, record that reason
   explicitly instead of leaving it absent.
2. Record interacting hard requirements in `construction_readiness`, then implement
   one replayable task adapter that evaluates those requirements together.
3. Compile `WORK_ITEMS.json` into bounded rows that cover every acceptance ID. Give
   each row dependencies, scope, done-when conditions, selected capability IDs, and
   advisory reminders. Compile `CAPABILITIES.json` with exact versions, digests,
   input/output contracts, applicability signals, and side-effect declarations.
4. Keep task observations and command output under builder scratch during construction;
   include only reusable task diagnostics, tests, and documentation in this directory.
5. Run strict validation without draft mode. Incomplete or unresolved output is an
   honest diagnostic, not permission to claim success.

After runner-owned freezing, both Worker and QA receive these same bytes and the same
digest. Each role independently checks the public task sources. QA treats Corridor
output as evidence to audit, never as proof of its own completeness.

The runner keeps the mutable Position timeline outside these frozen bytes. Runtime
Guide and reminder views are deterministic projections over the frozen work rows,
frozen capability registry, and that RAW timeline. They remain advisory and never
authorize mutation or block the external evaluator.

The generated `task_adapter.py` reports `unresolved` until the Builder replaces its
task-specific functions. It never mutates the target by itself.
"""


STARTER_ADAPTER = '''#!/usr/bin/env python3
"""Task adapter boundary generated by corridor-kit; replace during construction."""

from __future__ import annotations

import argparse
import json


def unresolved(command: str) -> dict[str, object]:
    return {
        "schema_version": "charting-loop/task-adapter-report/v1",
        "status": "unresolved",
        "command": command,
        "reason": "The Builder has not compiled the task-specific adapter.",
        "authorizes_mutation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory task-specific Corridor adapter")
    parser.add_argument("command", choices=("survey", "check", "guide"))
    args = parser.parse_args()
    print(json.dumps(unresolved(args.command), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
'''


FIXTURES_README = """# Task-specific fixtures

The Builder may add synthetic or public-source-derived fixtures here. Do not copy a
prior benchmark's fixtures, hidden verifier material, candidate answer, or writeback.
"""


EVIDENCE_README = """# Evidence interface

Task diagnostics may emit replay reports here or into runner-owned scratch. Reports
must identify the command, public inputs, result, and acceptance IDs they bear on.
They are evidence for Worker and QA, not self-issued acceptance or authority.
"""


def _write_scaffold_tree(
    root: Path,
    *,
    method_version: str | None = None,
    method_digest: str | None = None,
    method_scope_digest: str | None = None,
) -> None:
    (root / "fixtures").mkdir()
    (root / "evidence").mkdir()
    ledger = starter_acceptance_ledger()
    work = starter_work_backlog()
    capabilities = starter_capability_registry()
    capsule = method_capsule(
        method_version=method_version,
        method_digest=method_digest,
        method_scope_digest=method_scope_digest,
    )
    evidence = {
        "schema_version": EVIDENCE_SCAFFOLD_SCHEMA,
        "records": [],
        "required_fields": [
            "evidence_id",
            "acceptance_ids",
            "obligation_kind",
            "command",
            "inputs",
            "result",
            "replay",
        ],
        "advisory_only": True,
    }
    source_map = {
        "schema_version": SOURCE_MAP_SCHEMA,
        "status": "uncompiled",
        "sources": [],
        "unmapped": ["public task sources"],
    }
    replay = {
        "schema_version": REPLAY_SCAFFOLD_SCHEMA,
        "commands": [],
        "shell": False,
        "privilege": "unprivileged",
        "side_effects": "none_until_task_specific_compilation",
        "authorizes_mutation": False,
    }
    report = validate_acceptance_ledger(ledger, allow_draft=True)
    if not report.ok:
        raise CorridorKitError(f"internal starter ledger is invalid: {report.errors}")
    work_report = validate_work_backlog(work, allow_draft=True)
    if not work_report.ok:
        raise CorridorKitError(f"internal starter work backlog is invalid: {work_report.errors}")
    capability_report = validate_capability_registry(capabilities, allow_draft=True)
    if not capability_report.ok:
        raise CorridorKitError(
            f"internal starter capability registry is invalid: {capability_report.errors}"
        )
    atomic_write_json(root / "ACCEPTANCE.json", ledger)
    atomic_write_json(root / "WORK_ITEMS.json", work)
    atomic_write_json(root / "CAPABILITIES.json", capabilities)
    atomic_write_json(root / "METHOD-CAPSULE.json", capsule)
    atomic_write_json(root / "EVIDENCE.json", evidence)
    atomic_write_json(root / "SOURCE-MAP.json", source_map)
    atomic_write_json(root / "REPLAY.json", replay)
    atomic_write_bytes(root / "README.md", STARTER_README.encode("utf-8"))
    atomic_write_bytes(
        root / "task_adapter.py", STARTER_ADAPTER.encode("utf-8"), mode=0o755
    )
    atomic_write_bytes(
        root / "fixtures" / "README.md", FIXTURES_README.encode("utf-8")
    )
    atomic_write_bytes(
        root / "evidence" / "README.md", EVIDENCE_README.encode("utf-8")
    )
    identity_input = {
        "acceptance": ledger,
        "work": work,
        "capabilities": capabilities,
        "method_capsule": capsule,
        "evidence": evidence,
        "source_map": source_map,
        "replay": replay,
        "readme": STARTER_README,
        "adapter": STARTER_ADAPTER,
        "fixtures_readme": FIXTURES_README,
        "evidence_readme": EVIDENCE_README,
    }
    atomic_write_json(
        root / "KIT.json",
        {
            "schema_version": SCAFFOLD_SCHEMA,
            "kit_version": KIT_VERSION,
            "state": "uncompiled",
            "task_specific": False,
            "authorizes_mutation": False,
            "worker_and_qa_shared_after_freeze": True,
            "method_capsule_digest": sha256_json(capsule),
            "method_capsule_binding_state": capsule["binding_state"],
            "starter_digest": sha256_json(identity_input),
            "generated_files": [
                "ACCEPTANCE.json",
                "WORK_ITEMS.json",
                "CAPABILITIES.json",
                "METHOD-CAPSULE.json",
                "EVIDENCE.json",
                "SOURCE-MAP.json",
                "REPLAY.json",
                "README.md",
                "task_adapter.py",
                "fixtures/README.md",
                "evidence/README.md",
            ],
        },
    )


def create_scaffold(
    output: Path,
    *,
    method_version: str | None = None,
    method_digest: str | None = None,
    method_scope_digest: str | None = None,
) -> Path:
    """Atomically install a new scaffold without replacing existing task data."""

    output = Path(output)
    if output.exists() or output.is_symlink():
        raise CorridorKitError(f"scaffold output already exists: {output}")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise CorridorKitError(f"scaffold parent must be a real directory: {parent}")
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        _write_scaffold_tree(
            staging,
            method_version=method_version,
            method_digest=method_digest,
            method_scope_digest=method_scope_digest,
        )
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output
