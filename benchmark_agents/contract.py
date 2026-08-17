"""Pure prompt and evidence contracts for the full-method benchmark agent.

Nothing in this module imports Harbor.  The split is intentional: public tests can
verify the scientific contract without installing or authenticating a benchmark
runtime, while ``harbor_agent.py`` remains a thin orchestration adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import textwrap
from pathlib import Path
from typing import Any


RUNTIME_ROOT = "/tmp/charting-loop"
SDK_ROOT = "/opt/charting-loop-sdk"
SDK_PACKAGE_PATH = f"{SDK_ROOT}/corridor_kit"
POSITION_ROOT = "/tmp/charting-loop-position"
POSITION_PATH = f"{POSITION_ROOT}/POSITION.jsonl"
METHOD_PATH = f"{RUNTIME_ROOT}/method/METHOD.md"
CORRIDOR_PATH = f"{RUNTIME_ROOT}/corridor"
ACCEPTANCE_PATH = f"{CORRIDOR_PATH}/ACCEPTANCE.json"
WORK_PATH = f"{CORRIDOR_PATH}/WORK_ITEMS.json"
CAPABILITIES_PATH = f"{CORRIDOR_PATH}/CAPABILITIES.json"
FREEZE_PATH = f"{RUNTIME_ROOT}/FREEZE.json"
QA_PATH = f"{RUNTIME_ROOT}/qa/assessment.json"
CLOSURE_PATH = f"{RUNTIME_ROOT}/qa/closure.json"
SUBMISSION_ROOT = "/logs/agent/submissions"

FREEZE_SCHEMA = "charting-loop/frozen-task-corridor/v1"
ACCEPTANCE_SCHEMA = "charting-loop/task-acceptance-ledger/v1"
ASSESSMENT_SCHEMA = "charting-loop/corridor-qa-assessment/v3"
QA_OUTCOMES = frozenset({"pass", "fail", "blocked", "not_assessed"})
ACCEPTANCE_APPLICABILITY = frozenset(
    {"applicable", "not_applicable", "unknown"}
)
ACCEPTANCE_STATES = frozenset({"pass", "fail", "unknown", "not_reached"})
CONSTRUCTION_READINESS_STATES = frozenset({"ready", "unresolved"})
ASSESSMENT_CLOSURE_STATES = frozenset({"complete", "incomplete"})
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_QA_JSON_BYTES = 256 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON value for stable content-addressing."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def corridor_manifest(corridor: Path) -> list[dict[str, Any]]:
    """Return the deterministic regular-file manifest used by the freezer.

    Symlinks and special files are rejected because a frozen Corridor must be a
    closed byte set.  Directories are structural and are not separately hashed.
    """

    if corridor.is_symlink() or not corridor.is_dir():
        raise ValueError("corridor must be a real directory")
    files: list[dict[str, Any]] = []
    for path in sorted(corridor.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"corridor symlink is forbidden: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"corridor special file is forbidden: {path}")
        data = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(corridor).as_posix(),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "executable": bool(stat.S_IMODE(path.stat().st_mode) & 0o111),
            }
        )
    if not files:
        raise ValueError("corridor contains no regular files")
    return files


def corridor_digest(files: list[dict[str, Any]]) -> str:
    """Digest a manifest, including relative paths, sizes, and file hashes."""

    return sha256_bytes(canonical_json_bytes(files))


def freeze_program(runtime_root: str = RUNTIME_ROOT) -> str:
    """Return the root-run program that closes and freezes the Builder output.

    A missing or unsafe Builder output is replaced by an explicit fallback record.
    This keeps the benchmark trial progressing without pretending construction
    succeeded.  The fallback is visible to both downstream roles and in FREEZE.json.
    """

    return textwrap.dedent(
        f"""
        import hashlib
        import json
        import os
        import shutil
        import stat
        from pathlib import Path

        root = Path({runtime_root!r})
        corridor = root / "corridor"
        method = root / "method" / "METHOD.md"
        freeze = root / "FREEZE.json"
        schema = {FREEZE_SCHEMA!r}

        def digest(data):
            return "sha256:" + hashlib.sha256(data).hexdigest()

        def canonical(value):
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")

        def scan():
            if corridor.is_symlink() or not corridor.is_dir():
                raise ValueError("corridor must be a real directory")
            records = []
            for path in sorted(corridor.rglob("*"), key=lambda p: p.as_posix()):
                if path.is_symlink():
                    raise ValueError(f"corridor symlink is forbidden: {{path}}")
                if path.is_dir():
                    continue
                if not path.is_file():
                    raise ValueError(f"corridor special file is forbidden: {{path}}")
                data = path.read_bytes()
                records.append({{
                    "path": path.relative_to(corridor).as_posix(),
                    "bytes": len(data),
                    "sha256": digest(data),
                    "executable": bool(stat.S_IMODE(path.stat().st_mode) & 0o111),
                }})
            if not records:
                raise ValueError("corridor contains no regular files")
            return records

        def summarize_acceptance():
            path = corridor / "ACCEPTANCE.json"
            summary = {{
                "status": "missing",
                "schema_version": None,
                "acceptance_ids": [],
                "required_acceptance_ids": [],
                "unmapped_count": 0,
                "ambiguous_count": 0,
                "ambiguous_acceptance_ids": [],
                "source_mapping_status": "unknown",
                "definition_closure_status": "unknown",
                "construction_readiness_status": "unknown",
                "coupled_acceptance_ids": [],
                "unresolved_constraints": [],
                "errors": [],
            }}
            if path.is_symlink() or not path.is_file():
                summary["errors"].append("ACCEPTANCE_LEDGER_MISSING")
                return summary

            def reject_duplicates(pairs):
                value = {{}}
                for key, item in pairs:
                    if key in value:
                        raise ValueError(f"duplicate key: {{key}}")
                    value[key] = item
                return value

            try:
                ledger = json.loads(
                    path.read_text(encoding="utf-8"),
                    object_pairs_hook=reject_duplicates,
                    parse_constant=lambda item: (_ for _ in ()).throw(
                        ValueError(f"non-finite value: {{item}}")
                    ),
                )
            except Exception as exc:
                summary["status"] = "invalid"
                summary["errors"].append(
                    f"ACCEPTANCE_LEDGER_JSON:{{type(exc).__name__}}"
                )
                return summary

            if not isinstance(ledger, dict):
                summary["status"] = "invalid"
                summary["errors"].append("ACCEPTANCE_LEDGER_OBJECT_REQUIRED")
                return summary
            summary["schema_version"] = ledger.get("schema_version")
            if ledger.get("schema_version") != {ACCEPTANCE_SCHEMA!r}:
                summary["errors"].append("ACCEPTANCE_LEDGER_SCHEMA")

            coverage = ledger.get("coverage")
            if not isinstance(coverage, dict):
                summary["errors"].append("ACCEPTANCE_COVERAGE_OBJECT_REQUIRED")
                coverage = {{}}
            coverage_status = coverage.get("status")
            if coverage_status not in ("complete", "incomplete"):
                summary["errors"].append("ACCEPTANCE_COVERAGE_STATUS")
            for field in ("unmapped_clauses", "ambiguous_clauses"):
                values = coverage.get(field)
                if not isinstance(values, list):
                    summary["errors"].append(
                        "ACCEPTANCE_" + field.upper() + "_LIST_REQUIRED"
                    )
                    values = []
                summary[
                    "unmapped_count"
                    if field == "unmapped_clauses"
                    else "ambiguous_count"
                ] = len(values)
                for index, value in enumerate(values):
                    if not isinstance(value, dict):
                        summary["errors"].append(
                            f"ACCEPTANCE_{{field.upper()}}_{{index}}"
                        )
                        continue
                    for required_field in ("source_ref", "statement", "reason"):
                        item = value.get(required_field)
                        if not isinstance(item, str) or not item.strip():
                            summary["errors"].append(
                                f"ACCEPTANCE_{{field.upper()}}_"
                                f"{{required_field.upper()}}_{{index}}"
                            )

            items = ledger.get("items")
            if not isinstance(items, list) or not items:
                summary["errors"].append("ACCEPTANCE_ITEMS_NONEMPTY_LIST_REQUIRED")
                items = []
            seen = set()
            relation_targets = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    summary["errors"].append(f"ACCEPTANCE_ITEM_{{index}}")
                    continue
                acceptance_id = item.get("acceptance_id")
                if not isinstance(acceptance_id, str) or not acceptance_id.strip():
                    summary["errors"].append(f"ACCEPTANCE_ID_{{index}}")
                    continue
                if acceptance_id in seen:
                    summary["errors"].append(
                        f"ACCEPTANCE_ID_DUPLICATE:{{acceptance_id}}"
                    )
                    continue
                seen.add(acceptance_id)
                summary["acceptance_ids"].append(acceptance_id)
                if item.get("required") is True:
                    summary["required_acceptance_ids"].append(acceptance_id)
                elif item.get("required") is not False:
                    summary["errors"].append(
                        f"ACCEPTANCE_REQUIRED_BOOLEAN:{{acceptance_id}}"
                    )
                for field in ("source_ref", "statement"):
                    value = item.get(field)
                    if not isinstance(value, str) or not value.strip():
                        summary["errors"].append(
                            f"ACCEPTANCE_{{field.upper()}}:{{acceptance_id}}"
                        )
                if item.get("definition_state") not in (
                    "defined",
                    "ambiguous",
                ):
                    summary["errors"].append(
                        f"ACCEPTANCE_DEFINITION_STATE:{{acceptance_id}}"
                    )
                elif item.get("definition_state") == "ambiguous":
                    summary["ambiguous_acceptance_ids"].append(acceptance_id)
                for field in ("scope", "rule"):
                    value = item.get(field)
                    if not isinstance(value, dict) or not value:
                        summary["errors"].append(
                            f"ACCEPTANCE_{{field.upper()}}:{{acceptance_id}}"
                        )
                relations = item.get("relations")
                if not isinstance(relations, list):
                    summary["errors"].append(
                        f"ACCEPTANCE_RELATIONS:{{acceptance_id}}"
                    )
                    continue
                for relation_index, relation in enumerate(relations):
                    if not isinstance(relation, dict):
                        summary["errors"].append(
                            f"ACCEPTANCE_RELATION_{{acceptance_id}}_"
                            f"{{relation_index}}"
                        )
                        continue
                    if relation.get("type") not in (
                        "requires",
                        "subsumes",
                        "overlaps",
                        "conflicts",
                        "derived_from",
                    ):
                        summary["errors"].append(
                            f"ACCEPTANCE_RELATION_TYPE:{{acceptance_id}}"
                        )
                    target = relation.get("target_id")
                    if not isinstance(target, str) or not target.strip():
                        summary["errors"].append(
                            f"ACCEPTANCE_RELATION_TARGET:{{acceptance_id}}"
                        )
                    else:
                        relation_targets.append((acceptance_id, target))
            for source, target in relation_targets:
                if target not in seen:
                    summary["errors"].append(
                        f"ACCEPTANCE_RELATION_UNKNOWN:{{source}}:{{target}}"
                    )

            if coverage_status == "complete" and summary["unmapped_count"]:
                summary["errors"].append(
                    "ACCEPTANCE_COMPLETE_MAPPING_HAS_UNMAPPED_CLAUSES"
                )
            if coverage_status == "incomplete" and not summary["unmapped_count"]:
                summary["errors"].append(
                    "ACCEPTANCE_INCOMPLETE_MAPPING_NEEDS_UNMAPPED_CLAUSE"
                )
            summary["source_mapping_status"] = (
                "complete"
                if coverage_status == "complete" and not summary["unmapped_count"]
                else "incomplete"
            )
            summary["definition_closure_status"] = (
                "complete"
                if not summary["ambiguous_count"]
                and not summary["ambiguous_acceptance_ids"]
                else "incomplete"
            )

            readiness = ledger.get("construction_readiness")
            if not isinstance(readiness, dict):
                summary["errors"].append(
                    "ACCEPTANCE_CONSTRUCTION_READINESS_OBJECT_REQUIRED"
                )
                readiness = {{}}
            readiness_status = readiness.get("status")
            summary["construction_readiness_status"] = (
                readiness_status if isinstance(readiness_status, str) else "unknown"
            )
            if readiness_status not in ("ready", "unresolved"):
                summary["errors"].append(
                    "ACCEPTANCE_CONSTRUCTION_READINESS_STATUS"
                )
            coupled_ids = readiness.get("coupled_acceptance_ids")
            if not isinstance(coupled_ids, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in coupled_ids
            ):
                summary["errors"].append(
                    "ACCEPTANCE_COUPLED_IDS_LIST_REQUIRED"
                )
                coupled_ids = []
            elif len(set(coupled_ids)) != len(coupled_ids):
                summary["errors"].append("ACCEPTANCE_COUPLED_IDS_DUPLICATE")
            summary["coupled_acceptance_ids"] = coupled_ids
            for acceptance_id in coupled_ids:
                if acceptance_id not in seen:
                    summary["errors"].append(
                        f"ACCEPTANCE_COUPLED_ID_UNKNOWN:{{acceptance_id}}"
                    )
            unresolved = readiness.get("unresolved_constraints")
            if not isinstance(unresolved, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in unresolved
            ):
                summary["errors"].append(
                    "ACCEPTANCE_UNRESOLVED_CONSTRAINTS_LIST_REQUIRED"
                )
                unresolved = []
            summary["unresolved_constraints"] = unresolved
            replay_entrypoint = readiness.get("replay_entrypoint")
            if readiness_status == "ready":
                if unresolved:
                    summary["errors"].append(
                        "ACCEPTANCE_READY_WITH_UNRESOLVED_CONSTRAINTS"
                    )
                if coupled_ids and (
                    not isinstance(replay_entrypoint, str)
                    or not replay_entrypoint.strip()
                ):
                    summary["errors"].append(
                        "ACCEPTANCE_COUPLED_REPLAY_ENTRYPOINT_REQUIRED"
                    )
                if summary["source_mapping_status"] != "complete":
                    summary["errors"].append(
                        "ACCEPTANCE_READY_REQUIRES_SOURCE_MAPPING"
                    )
                if summary["definition_closure_status"] != "complete":
                    summary["errors"].append(
                        "ACCEPTANCE_READY_REQUIRES_DEFINITION_CLOSURE"
                    )
            elif readiness_status == "unresolved" and not unresolved:
                summary["errors"].append(
                    "ACCEPTANCE_UNRESOLVED_REASON_REQUIRED"
                )

            if summary["errors"]:
                summary["status"] = "invalid"
            elif (
                summary["source_mapping_status"] == "complete"
                and summary["definition_closure_status"] == "complete"
            ):
                summary["status"] = "complete"
            else:
                summary["status"] = "incomplete"
            return summary

        root.mkdir(parents=True, exist_ok=True)
        status = "frozen"
        failure = None
        try:
            files = scan()
        except Exception as exc:
            status = "fallback"
            failure = f"{{type(exc).__name__}}: {{exc}}"[:1000]
            if corridor.is_symlink():
                corridor.unlink()
            elif corridor.exists():
                shutil.rmtree(corridor)
            corridor.mkdir(parents=True, exist_ok=True)
            (corridor / "CORRIDOR.md").write_text(
                "# Corridor construction unavailable\\n\\n"
                "The Builder did not leave a safe, non-empty Corridor. "
                "Worker and QA receive this same frozen failure record.\\n",
                encoding="utf-8",
            )
            files = scan()

        acceptance = summarize_acceptance()
        manifest = {{
            "schema_version": schema,
            "builder_corridor_status": status,
            "builder_failure": failure,
            "method_sha256": digest(method.read_bytes()) if method.is_file() else None,
            "corridor_tree_sha256": digest(canonical(files)),
            "acceptance_ledger": acceptance,
            "files": files,
        }}
        freeze.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\\n",
            encoding="utf-8",
        )

        # Root ownership plus world-readable closed modes lets downstream roles use
        # the same files even when Harbor runs them as a non-root user. Executable
        # Builder tools remain executable; ordinary files never gain that bit.
        for path in [corridor, *sorted(corridor.rglob("*")), freeze, method]:
            if not path.exists() or path.is_symlink():
                continue
            current = stat.S_IMODE(path.stat().st_mode)
            if path.is_dir():
                mode = 0o555
            elif path in (freeze, method):
                mode = 0o444
            else:
                mode = 0o555 if current & 0o111 else 0o444
            os.chmod(path, mode)
            try:
                os.chown(path, 0, 0)
            except PermissionError:
                pass

        print(json.dumps({{
            "ok": True,
            "corridor_digest": manifest["corridor_tree_sha256"],
            "builder_corridor_status": status,
            "acceptance_ledger_status": acceptance["status"],
            "acceptance_ids": acceptance["acceptance_ids"],
            "required_acceptance_ids": acceptance["required_acceptance_ids"],
            "acceptance_ledger_errors": acceptance["errors"],
            "source_mapping_status": acceptance["source_mapping_status"],
            "definition_closure_status": acceptance[
                "definition_closure_status"
            ],
            "unmapped_count": acceptance["unmapped_count"],
            "ambiguous_count": acceptance["ambiguous_count"],
            "ambiguous_acceptance_ids": acceptance[
                "ambiguous_acceptance_ids"
            ],
            "construction_readiness_status": acceptance[
                "construction_readiness_status"
            ],
            "coupled_acceptance_ids": acceptance["coupled_acceptance_ids"],
            "unresolved_constraints": acceptance["unresolved_constraints"],
            "file_count": len(files),
        }}, sort_keys=True))
        """
    ).strip()


def verify_freeze_program(runtime_root: str = RUNTIME_ROOT) -> str:
    """Return a read-only probe that recomputes the frozen Corridor digest."""

    return textwrap.dedent(
        f"""
        import hashlib
        import json
        import stat
        from pathlib import Path

        root = Path({runtime_root!r})
        corridor = root / "corridor"
        freeze = root / "FREEZE.json"

        def digest(data):
            return "sha256:" + hashlib.sha256(data).hexdigest()

        def canonical(value):
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")

        manifest = json.loads(freeze.read_text(encoding="utf-8"))
        files = []
        violations = []
        if corridor.is_symlink() or not corridor.is_dir():
            violations.append("corridor_not_real_directory")
        else:
            for path in sorted(corridor.rglob("*"), key=lambda p: p.as_posix()):
                if path.is_symlink():
                    violations.append("symlink:" + path.as_posix())
                    continue
                if path.is_dir():
                    if stat.S_IMODE(path.stat().st_mode) & 0o222:
                        violations.append("writable:" + path.as_posix())
                    if stat.S_IMODE(path.stat().st_mode) & 0o055 != 0o055:
                        violations.append("not_traversable:" + path.as_posix())
                    continue
                if not path.is_file():
                    violations.append("special:" + path.as_posix())
                    continue
                if stat.S_IMODE(path.stat().st_mode) & 0o222:
                    violations.append("writable:" + path.as_posix())
                if stat.S_IMODE(path.stat().st_mode) & 0o044 != 0o044:
                    violations.append("not_readable:" + path.as_posix())
                data = path.read_bytes()
                files.append({{
                    "path": path.relative_to(corridor).as_posix(),
                    "bytes": len(data),
                    "sha256": digest(data),
                    "executable": bool(stat.S_IMODE(path.stat().st_mode) & 0o111),
                }})

        actual = digest(canonical(files))
        expected = manifest.get("corridor_tree_sha256")
        if files != manifest.get("files"):
            violations.append("manifest_file_mismatch")
        if actual != expected:
            violations.append("corridor_digest_mismatch")
        if stat.S_IMODE(freeze.stat().st_mode) & 0o222:
            violations.append("freeze_manifest_writable")
        print(json.dumps({{
            "ok": not violations,
            "corridor_digest": actual,
            "expected_digest": expected,
            "violations": violations,
        }}, sort_keys=True))
        raise SystemExit(0 if not violations else 2)
        """
    ).strip()


def remote_json_read_program(path: str) -> str:
    """Return a bounded JSON-file reader for an in-trial evidence artifact."""

    return textwrap.dedent(
        f"""
        from pathlib import Path
        path = Path({path!r})
        if path.is_symlink() or not path.is_file():
            raise SystemExit(2)
        if path.stat().st_size > {MAX_QA_JSON_BYTES}:
            raise SystemExit(3)
        print(path.read_text(encoding="utf-8"))
        """
    ).strip()


def load_qa_json_text(text: str) -> Any:
    """Parse bounded QA JSON without duplicate keys or non-finite numbers."""

    if len(text.encode("utf-8")) > MAX_QA_JSON_BYTES:
        raise ValueError("QA JSON exceeds the size limit")

    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate QA JSON key: {key}")
            value[key] = item
        return value

    return json.loads(
        text,
        object_pairs_hook=reject_duplicate_pairs,
        parse_constant=lambda item: (_ for _ in ()).throw(
            ValueError(f"non-finite QA JSON value: {item}")
        ),
    )


def _task_block(task_instruction: str) -> str:
    task = task_instruction.strip()
    return f"<official_task>\n{task}\n</official_task>"


def builder_prompt(task_instruction: str) -> str:
    """Prompt the construction role with the method and official task goal."""

    acceptance_template = json.dumps(
        {
            "schema_version": ACCEPTANCE_SCHEMA,
            "coverage": {
                "status": "complete|incomplete",
                "unmapped_clauses": [],
                "ambiguous_clauses": [],
            },
            "construction_readiness": {
                "status": "ready|unresolved",
                "coupled_acceptance_ids": ["ACCEPT-..."],
                "replay_entrypoint": "./validate-or-plan ...",
                "unresolved_constraints": [],
            },
            "items": [
                {
                    "acceptance_id": "ACCEPT-...",
                    "source_ref": "public-source#locator",
                    "statement": "one atomic normative requirement",
                    "required": True,
                    "definition_state": "defined|ambiguous",
                    "scope": {"kind": "task-specific scope"},
                    "rule": {"kind": "task-specific decision rule"},
                    "relations": [
                        {"type": "requires", "target_id": "ACCEPT-..."}
                    ],
                }
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
    work_template = json.dumps(
        {
            "schema_version": "charting-loop/task-work-backlog/v1",
            "state": "compiled",
            "acceptance_ledger_digest": "sha256:<canonical ACCEPTANCE.json digest>",
            "rows": [
                {
                    "row_id": "ROW-...",
                    "title": "bounded work outcome",
                    "acceptance_ids": ["ACCEPT-..."],
                    "depends_on": [],
                    "scope": {"kind": "task-specific scope"},
                    "done_when": ["replayable condition"],
                    "capability_ids": ["selected.capability-id"],
                    "reminders": [
                        {
                            "reminder_id": "REM-...",
                            "when": "on_ready|on_enter|before_mutation|before_complete|on_blocked",
                            "message": "advisory task reminder",
                            "acceptance_ids": ["ACCEPT-..."],
                        }
                    ],
                }
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
    capability_template = json.dumps(
        {
            "schema_version": "charting-loop/capability-registry/v1",
            "state": "compiled",
            "registry_version": "1.0.0",
            "capabilities": [
                {
                    "capability_id": "selected.capability-id",
                    "version": "1.0.0",
                    "digest": "sha256:<64 lowercase hex>",
                    "summary": "bounded reusable operation",
                    "entrypoint": "shell-free documented entrypoint",
                    "input_contract": {"input": "declared input"},
                    "output_contract": {"output": "declared output"},
                    "side_effects": "none|read_only|mutating",
                    "applicability": {
                        "domains": ["declared domain"],
                        "signals": ["public applicability signal"],
                    },
                }
            ],
        },
        indent=2,
        ensure_ascii=False,
    )

    return f"""You are the Builder for one fresh Terminal-Bench trial.

Read the frozen method at {METHOD_PATH}. The official task is included below because
this is a task-conditioned Corridor: without the goal and public task environment,
you cannot compile the relevant constraints into a useful navigation aid.

The runner uploaded a frozen task-neutral Corridor SDK read-only at
{SDK_PACKAGE_PATH}. Initialize its honest starter under Builder scratch with
`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit init <new-scratch-path>`, inspect
`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit capabilities builtins`, and copy only
selected task-neutral mechanics plus task-specific adapters into the Corridor. Do not
rebuild generic hashing, work-row, timeline, ELF inventory, binary-diff, or replay
plumbing when the frozen SDK already provides it.

{_task_block(task_instruction)}

Construct a reusable task-specific Corridor under {CORRIDOR_PATH}. It may contain
documentation, diagnostic commands, validators, planners, or a service. Inspect the
public task environment as needed, but do not carry out the official task or mutate
its target state. Do not read verifier/oracle material that the official task does
not expose to ordinary agents.

Create {ACCEPTANCE_PATH} using this exact field contract (replace example values,
never field names):

{acceptance_template}

Create {WORK_PATH} using this exact field contract. Bind every acceptance ID without
leaving an item unbound:

{work_template}

Create {CAPABILITIES_PATH} using this exact field contract. Include only capabilities
selected by a row. Reusable mechanics may never contain a task answer, fixed task
offset, hidden verifier Fact, or outcome-derived repair:

{capability_template}

The top-level field is exactly `schema_version`, never `schema`. Every relation
target field is exactly `target_id`, never `target_acceptance_id` or another alias.
Decompose every normative
clause in the public task instruction and public task specification into an atomic
item with a stable `acceptance_id`, exact `source_ref`, normalized `statement`,
`required` boolean, `definition_state` (`defined|ambiguous`), non-empty task
`scope`, non-empty decision `rule`, and typed `relations` (`requires`,
`subsumes`, `overlaps`, `conflicts`, or `derived_from`). The top-level
`coverage` object must declare `status` and list all `unmapped_clauses` and
`ambiguous_clauses`, each with source_ref, statement, and reason. Mark coverage
complete only after re-reading the original public sources and mapping every
normative clause. Do not invent precedence for overlap or conflict.

`coverage.status` reports source-clause mapping only; it does not claim that a
candidate solution is feasible or optimal. A mapped clause may remain explicitly
ambiguous: keep it in `ambiguous_clauses`, mark its item `definition_state` as
`ambiguous`, and still report source mapping complete when nothing is unmapped.
Definition closure remains incomplete until those ambiguities are resolved. Use the separate
`construction_readiness` object for that. If hard requirements interact (for
example capacity, scheduling, inventory, identity, and priority/objective rules),
list their IDs in `coupled_acceptance_ids`. Mark construction `ready` only when the
Corridor has one replayable executable entrypoint that evaluates the coupled hard
constraints and objective together. Otherwise mark it `unresolved` and name every
missing proof in `unresolved_constraints`. Never recommend a candidate or claim
whole-task readiness while a required coupled constraint or objective is unknown.

Compile the acceptance graph into bounded work rows. Dependencies must be acyclic;
every acceptance and capability ID must resolve; and each row needs explicit task
scope and replayable done-when conditions. Reminders are advisory and must never
become approval, pre-mutation, or workflow Gates. Before finishing, run:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit validate {ACCEPTANCE_PATH}`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit validate-capabilities {CAPABILITIES_PATH}`

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit validate-work {WORK_PATH} --acceptance {ACCEPTANCE_PATH} --capabilities {CAPABILITIES_PATH}`

Build in bounded milestones: first write the exact acceptance ledger and a minimal
README, then make the global replay check executable, then deepen diagnostics only
if time remains. A partial but honest `unresolved` Corridor is preferable to an
invalid ledger or an unproved readiness claim.

Builder, Worker, QA, repair, and closure share the official task's single total
clock. There is no Builder-owned time slice to exhaust. Finish and hand off as soon
as a useful, valid Corridor is frozen-ready so that later roles retain time.

Experimental constraint: do not install a mandatory workflow gate, approval gate,
or pre-mutation gate that can block the later Worker from continuing. A Corridor may
diagnose, plan, validate, warn, or refuse an explicitly requested unsafe operation;
it must remain an aid the Worker chooses to call, not a new governance dependency.

Write only the Corridor and Builder scratch data under {RUNTIME_ROOT}. Leave a clear
README or entrypoint. Do not put a final task answer or precomputed writeback in the
Corridor. When finished, report what you built; the harness will freeze the bytes.
"""


def worker_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    construction_readiness_status: str = "unknown",
    work_backlog_status: str = "unknown",
    current_row_id: str | None = None,
    remaining_seconds: int | None = None,
) -> str:
    """Prompt the execution role with the exact frozen Corridor identity."""

    return f"""You are the Worker responsible for completing the official task.

{_task_block(task_instruction)}

The Builder's frozen task-conditioned Corridor is available read-only at
{CORRIDOR_PATH}. Its freeze manifest is {FREEZE_PATH}, and the harness-verified
Corridor digest is {corridor_digest_value}. Read the Corridor before acting and use
its diagnostics/planner/validator when relevant. The Corridor is an aid, not hidden
authority or a stored answer: inspect the live task state, obey the official task,
and independently verify every mutation.

Read the frozen task acceptance ledger at {ACCEPTANCE_PATH}. Use its stable
acceptance IDs to plan and verify the whole task, not only the first reproduced
failure. Re-check public source requirements when the ledger is ambiguous or
incomplete. The freeze manifest reports construction readiness
`{construction_readiness_status}`. Source coverage is not solution qualification:
when readiness is not `ready`, or any required coupled feasibility/objective check
returns unknown, do not trust a recommended candidate as globally valid. Complete
the missing live reasoning yourself and require replayable evidence before mutation.

The frozen work-backlog status is `{work_backlog_status}` and the runner's initial
current-row projection is {json.dumps(current_row_id)}. When the work and capability
files validate, query the same runner-owned Position timeline and advisory Guide with:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit runtime guide --work {WORK_PATH} --capabilities {CAPABILITIES_PATH} --timeline {POSITION_PATH}`

Use row acceptance bindings, dependencies, done-when conditions, bounded capabilities,
and reminders to avoid losing place. Re-check live state: row events and reminders are
RAW observations, not authority or proof of completion.

All roles share one task-level deadline. At this handoff the runner reports about
{json.dumps(remaining_seconds)} seconds remaining; this is a progress signal, not a
separate Worker budget. Establish a complete, scorable version early. As soon as
every official output path for one internally consistent version exists, freeze it
with the task-neutral SDK, listing every required output path explicitly:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit submission freeze --root {SUBMISSION_ROOT} --role worker --path <absolute-output-path> [--path <absolute-output-path> ...]`

Run that command again after every verified improvement. A snapshot is immutable;
the newest complete snapshot becomes the monotonic fallback. Include only official
deliverables or task-state files needed for grading, never credentials, logs, or
unrelated host files. Freezing is custody, not acceptance and not a Gate: continue
working after a snapshot when time remains.

Execute the task now. Do not wait for QA and do not create a gate around your work.
The harness will invoke an independent QA role afterward.
"""


def qa_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    source_mapping_status: str = "unknown",
    definition_closure_status: str = "unknown",
    construction_readiness_status: str = "unknown",
    work_backlog_status: str = "unknown",
    current_row_id: str | None = None,
    remaining_seconds: int | None = None,
) -> str:
    """Prompt an independent QA session that can use the same frozen Corridor."""

    return f"""You are the independent QA reviewer. Audit the Worker's current result.

{_task_block(task_instruction)}

You MUST read and may execute the same frozen, read-only Corridor at {CORRIDOR_PATH}.
The freeze manifest is {FREEZE_PATH}; the expected digest is
{corridor_digest_value}. Use the Corridor for global constraint checks and
counterfactual validation, not merely as prose context.

The frozen work-backlog status is `{work_backlog_status}` and the runner's current-row
projection before QA is {json.dumps(current_row_id)}. Query the same read-only rows,
capabilities, Position timeline, Guide, and reminders used by Worker with:

`PYTHONPATH={SDK_ROOT} python3 -m corridor_kit runtime guide --work {WORK_PATH} --capabilities {CAPABILITIES_PATH} --timeline {POSITION_PATH}`

Audit row done-when evidence and replay applicable capabilities, but never treat a
row state or reminder as sufficient acceptance evidence.

All roles share one task-level deadline. At this handoff the runner reports about
{json.dumps(remaining_seconds)} seconds remaining; this is not a QA-owned time
slice. Preserve a valid assessment early and deepen it only while time remains. The
runner will freeze each completed QA assessment as audit evidence. QA remains
advisory and cannot delete, replace, or block the newest complete Worker snapshot.

Do not mutate the official task state, repair the result, or alter the Corridor.
Diagnostic reads are allowed. Your only write is {QA_PATH}. Write one JSON object:

{{
  "schema_version": "{ASSESSMENT_SCHEMA}",
  "outcome": "pass|fail|blocked|not_assessed",
  "summary": "concise human-readable conclusion",
  "corridor_digest": "{corridor_digest_value}",
  "source_mapping_complete": true,
  "definition_closure_complete": true,
  "assessment_closure": "complete|incomplete",
  "acceptance_results": [{{
    "acceptance_id": "...",
    "applicability": "applicable|not_applicable|unknown",
    "status": "pass|fail|unknown|not_reached",
    "evidence": "...",
    "replay": "..."
  }}],
  "unmapped_requirements": [],
  "unresolved_relations": [],
  "checks": [{{"name": "...", "status": "pass|fail|unknown", "evidence": "..."}}],
  "witnesses": [{{
    "acceptance_id": "...",
    "constraint": "...",
    "evidence": "...",
    "replay": "..."
  }}]
}}

The freeze manifest reports acceptance-ledger status
`{acceptance_ledger_status}` and the expected acceptance IDs are
{json.dumps(expected_acceptance_ids, ensure_ascii=False)}. Its source-mapping status
is `{source_mapping_status}`, definition-closure status is
`{definition_closure_status}`, and separate construction-readiness status is
`{construction_readiness_status}`. `source_mapping_complete` means every public
normative clause has a ledger location; it does not mean every mapped clause is
unambiguous. `definition_closure_complete` means no required definition or relation
remains ambiguous. `assessment_closure` means QA has reached a supported
applicability and status for every expected item. Do not collapse these three
claims. Source mapping is not proof of joint feasibility or objective optimality.
If definition closure or readiness is unresolved, or a required coupled check
remains unknown, you may not pass the task. Emit exactly one result
for every expected ID. Independently re-read the original public task sources to
look for omissions; the Corridor is a frozen map, not authority that its own map is
complete. A pass is permitted only when the frozen ledger is complete, the expected
ID set is exact, every applicable item passes, every inapplicable item is justified,
and no requirement or relation remains unmapped, unresolved, unknown, or not
reached. Witness closure is not task closure.

A fail verdict is valid only with at least one concrete witness tied to an
acceptance ID whose constraint, observed evidence, and safe replay procedure are all
non-empty. If complete task closure cannot be established, use blocked or
not_assessed.

Persist evidence witness-first. As soon as you establish an invalid acceptance
ledger, an unresolved required coupled check, or one concrete failure witness, write
a schema-valid provisional assessment covering every expected ID. Write it to a
temporary file in the QA directory and atomically rename it to {QA_PATH}; continue
deepening the audit only after that durable checkpoint, and atomically replace it
with richer evidence. Do not postpone the first valid assessment until the end of
your session. QA is advisory: your verdict must never prevent the official verifier
from running.
"""


def repair_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    remaining_seconds: int | None = None,
) -> str:
    """Resume the same Worker once when QA supplies a valid failure witness."""

    return f"""Resume as the SAME Worker for one bounded repair pass.

{_task_block(task_instruction)}

Read the independent QA assessment at {QA_PATH}. Re-read the same frozen Corridor
at {CORRIDOR_PATH}; its expected digest remains {corridor_digest_value}. Reproduce
each QA witness before changing anything. QA suggestions are not authority: reject
a locally plausible repair when the Corridor's complete constraints show it would
make the global result worse or infeasible.

Apply only repairs justified by reproduced witnesses, then verify the complete task
again against every stable acceptance ID in {ACCEPTANCE_PATH}; closing the reported
witness alone is insufficient. This is the single permitted repair pass. Do not
create a new gate.

The shared task clock has about {json.dumps(remaining_seconds)} seconds remaining;
there is no repair-owned time slice. The prior Worker snapshot remains protected.
Only after the repaired result is again complete and scorable, freeze a newer
Worker version with the same `corridor_kit submission freeze` command and the full
set of official output paths. If the repair stays incomplete, do not advance the
snapshot: the runner will restore the last complete Worker version.

Re-query the shared advisory runtime Guide at {POSITION_PATH}; row state helps recover
Position but does not authorize repair.
"""


def closure_prompt(
    task_instruction: str,
    corridor_digest_value: str,
    *,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    source_mapping_status: str = "unknown",
    definition_closure_status: str = "unknown",
    construction_readiness_status: str = "unknown",
    remaining_seconds: int | None = None,
) -> str:
    """Resume the same QA session to assess the one repair pass."""

    return f"""Resume as the SAME independent QA reviewer for closure verification.

{_task_block(task_instruction)}

The Worker has completed the single bounded repair pass. Re-read {QA_PATH}, inspect
the current task state, and use the same frozen Corridor at {CORRIDOR_PATH}. The
expected digest is still {corridor_digest_value}. Do not mutate task state or the
Corridor. Re-evaluate every expected acceptance ID
{json.dumps(expected_acceptance_ids, ensure_ascii=False)} and independently re-check
the public source for omissions; closing the prior witness does not close the task.
The frozen ledger status is `{acceptance_ledger_status}`. Write the same JSON
schema to {CLOSURE_PATH}. Its frozen source-mapping, definition-closure, and
construction-readiness statuses remain `{source_mapping_status}`,
`{definition_closure_status}`, and `{construction_readiness_status}` respectively;
report those dimensions separately from assessment closure. A fail still requires a concrete
acceptance-ID/constraint/evidence/replay witness. This closure is advisory and must
not gate the official verifier.

The shared task clock has about {json.dumps(remaining_seconds)} seconds remaining;
there is no closure-owned time slice. Write a complete atomic closure assessment
early. The runner freezes it as audit evidence and then restores/promotes the newest
complete Worker submission for official grading regardless of the QA verdict.

Re-query the same runtime Guide and Position timeline at {POSITION_PATH}; row progress
and reminders remain RAW, advisory evidence rather than acceptance authority.
"""


def validate_qa_assessment(
    value: Any,
    *,
    expected_corridor_digest: str,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    required_acceptance_ids: list[str],
    source_mapping_status: str = "complete",
    definition_closure_status: str = "complete",
    construction_readiness_status: str = "ready",
) -> list[str]:
    """Validate the QA artifact and return stable error codes.

    The decision to repair is ``not errors and outcome == 'fail'``.  Invalid or
    witness-free failures therefore cannot silently trigger mutation.
    """

    errors: list[str] = []
    if not isinstance(value, dict):
        return ["ASSESSMENT_OBJECT_REQUIRED"]
    if value.get("schema_version") != ASSESSMENT_SCHEMA:
        errors.append("ASSESSMENT_SCHEMA")
    outcome = value.get("outcome")
    if outcome not in QA_OUTCOMES:
        errors.append("ASSESSMENT_OUTCOME")
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("ASSESSMENT_SUMMARY")
    digest = value.get("corridor_digest")
    if digest != expected_corridor_digest or not isinstance(digest, str):
        errors.append("ASSESSMENT_CORRIDOR_DIGEST")
    elif not SHA256_RE.fullmatch(digest):
        errors.append("ASSESSMENT_CORRIDOR_DIGEST_FORMAT")

    source_mapping_complete = value.get("source_mapping_complete")
    if not isinstance(source_mapping_complete, bool):
        errors.append("ASSESSMENT_SOURCE_MAPPING_COMPLETE")
    definition_closure_complete = value.get("definition_closure_complete")
    if not isinstance(definition_closure_complete, bool):
        errors.append("ASSESSMENT_DEFINITION_CLOSURE_COMPLETE")
    assessment_closure = value.get("assessment_closure")
    if assessment_closure not in ASSESSMENT_CLOSURE_STATES:
        errors.append("ASSESSMENT_CLOSURE")

    expected_ids = set(expected_acceptance_ids)
    if len(expected_ids) != len(expected_acceptance_ids):
        errors.append("EXPECTED_ACCEPTANCE_IDS_DUPLICATE")
    required_ids = set(required_acceptance_ids)
    if not required_ids.issubset(expected_ids):
        errors.append("REQUIRED_ACCEPTANCE_IDS_UNKNOWN")

    acceptance_results = value.get("acceptance_results")
    results_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(acceptance_results, list):
        errors.append("ASSESSMENT_ACCEPTANCE_RESULTS")
        acceptance_results = []
    for index, result in enumerate(acceptance_results):
        if not isinstance(result, dict):
            errors.append(f"ASSESSMENT_ACCEPTANCE_RESULT_{index}")
            continue
        acceptance_id = result.get("acceptance_id")
        if not isinstance(acceptance_id, str) or not acceptance_id.strip():
            errors.append(f"ASSESSMENT_ACCEPTANCE_ID_{index}")
            continue
        if acceptance_id in results_by_id:
            errors.append(f"ASSESSMENT_ACCEPTANCE_ID_DUPLICATE_{acceptance_id}")
            continue
        results_by_id[acceptance_id] = result
        if result.get("applicability") not in ACCEPTANCE_APPLICABILITY:
            errors.append(f"ASSESSMENT_APPLICABILITY_{acceptance_id}")
        if result.get("status") not in ACCEPTANCE_STATES:
            errors.append(f"ASSESSMENT_ACCEPTANCE_STATUS_{acceptance_id}")
        for field in ("evidence", "replay"):
            item = result.get(field)
            if not isinstance(item, str) or not item.strip():
                errors.append(
                    f"ASSESSMENT_ACCEPTANCE_{field.upper()}_{acceptance_id}"
                )

    actual_ids = set(results_by_id)
    for acceptance_id in sorted(expected_ids - actual_ids):
        errors.append(f"ASSESSMENT_ACCEPTANCE_ID_MISSING_{acceptance_id}")
    for acceptance_id in sorted(actual_ids - expected_ids):
        errors.append(f"ASSESSMENT_ACCEPTANCE_ID_UNKNOWN_{acceptance_id}")

    collection_values: dict[str, list[Any]] = {}
    for field, code in (
        ("unmapped_requirements", "ASSESSMENT_UNMAPPED_REQUIREMENTS"),
        ("unresolved_relations", "ASSESSMENT_UNRESOLVED_RELATIONS"),
    ):
        items = value.get(field)
        if not isinstance(items, list):
            errors.append(code)
            continue
        collection_values[field] = items
        for index, item in enumerate(items):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"{code}_{index}")
    if source_mapping_complete is True and collection_values.get(
        "unmapped_requirements"
    ):
        errors.append("ASSESSMENT_SOURCE_MAPPING_CONTRADICTION")
    if definition_closure_complete is True and collection_values.get(
        "unresolved_relations"
    ):
        errors.append("ASSESSMENT_DEFINITION_CLOSURE_CONTRADICTION")
    if source_mapping_complete is True and source_mapping_status != "complete":
        errors.append("ASSESSMENT_SOURCE_MAPPING_EXCEEDS_FROZEN_LEDGER")
    if (
        definition_closure_complete is True
        and definition_closure_status != "complete"
    ):
        errors.append("ASSESSMENT_DEFINITION_CLOSURE_EXCEEDS_FROZEN_LEDGER")

    checks = value.get("checks")
    if not isinstance(checks, list):
        errors.append("ASSESSMENT_CHECKS")
        checks = []
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"ASSESSMENT_CHECK_{index}")
                continue
            if not isinstance(check.get("name"), str) or not check["name"].strip():
                errors.append(f"ASSESSMENT_CHECK_NAME_{index}")
            if check.get("status") not in {"pass", "fail", "unknown"}:
                errors.append(f"ASSESSMENT_CHECK_STATUS_{index}")
            if not isinstance(check.get("evidence"), str):
                errors.append(f"ASSESSMENT_CHECK_EVIDENCE_{index}")

    if assessment_closure == "complete":
        closure_unresolved = any(
            result.get("applicability") == "unknown"
            or (
                result.get("applicability") == "applicable"
                and result.get("status") in {"unknown", "not_reached"}
            )
            for result in results_by_id.values()
        ) or any(
            isinstance(check, dict) and check.get("status") == "unknown"
            for check in checks
        )
        if closure_unresolved or actual_ids != expected_ids:
            errors.append("ASSESSMENT_CLOSURE_CONTRADICTION")

    witnesses = value.get("witnesses")
    if not isinstance(witnesses, list):
        errors.append("ASSESSMENT_WITNESSES")
        witnesses = []
    for index, witness in enumerate(witnesses):
        if not isinstance(witness, dict):
            errors.append(f"ASSESSMENT_WITNESS_{index}")
            continue
        for field in ("constraint", "evidence", "replay"):
            item = witness.get(field)
            if not isinstance(item, str) or not item.strip():
                errors.append(f"ASSESSMENT_WITNESS_{field.upper()}_{index}")
    witness_acceptance_ids: set[str] = set()
    for index, witness in enumerate(witnesses):
        if not isinstance(witness, dict):
            continue
        acceptance_id = witness.get("acceptance_id")
        if not isinstance(acceptance_id, str) or not acceptance_id.strip():
            errors.append(f"ASSESSMENT_WITNESS_ACCEPTANCE_ID_{index}")
        elif acceptance_id not in expected_ids:
            errors.append(f"ASSESSMENT_WITNESS_ACCEPTANCE_ID_UNKNOWN_{index}")
        else:
            witness_acceptance_ids.add(acceptance_id)

    if outcome == "fail":
        if not witnesses:
            errors.append("FAIL_WITNESS_REQUIRED")
        failed_acceptance_ids = {
            acceptance_id
            for acceptance_id, result in results_by_id.items()
            if result.get("status") == "fail"
        }
        if not failed_acceptance_ids:
            errors.append("FAIL_ACCEPTANCE_RESULT_REQUIRED")
        elif not (failed_acceptance_ids & witness_acceptance_ids):
            errors.append("FAIL_WITNESS_ACCEPTANCE_MISMATCH")

    if outcome == "pass":
        if construction_readiness_status != "ready":
            errors.append("PASS_CONSTRUCTION_READINESS_REQUIRED")
        if acceptance_ledger_status != "complete":
            errors.append("PASS_ACCEPTANCE_LEDGER_COMPLETE_REQUIRED")
        if source_mapping_status != "complete":
            errors.append("PASS_FROZEN_SOURCE_MAPPING_REQUIRED")
        if definition_closure_status != "complete":
            errors.append("PASS_FROZEN_DEFINITION_CLOSURE_REQUIRED")
        if not expected_ids:
            errors.append("PASS_ACCEPTANCE_IDS_REQUIRED")
        if source_mapping_complete is not True:
            errors.append("PASS_SOURCE_MAPPING_COMPLETE_REQUIRED")
        if definition_closure_complete is not True:
            errors.append("PASS_DEFINITION_CLOSURE_COMPLETE_REQUIRED")
        if assessment_closure != "complete":
            errors.append("PASS_ASSESSMENT_CLOSURE_REQUIRED")
        if value.get("unmapped_requirements") != []:
            errors.append("PASS_UNMAPPED_REQUIREMENTS_EMPTY_REQUIRED")
        if value.get("unresolved_relations") != []:
            errors.append("PASS_UNRESOLVED_RELATIONS_EMPTY_REQUIRED")
        for acceptance_id in sorted(expected_ids & actual_ids):
            result = results_by_id[acceptance_id]
            applicability = result.get("applicability")
            state = result.get("status")
            if applicability == "applicable" and state != "pass":
                errors.append(f"PASS_ACCEPTANCE_NOT_PASS_{acceptance_id}")
            elif (
                applicability == "not_applicable"
                and state != "not_reached"
            ):
                errors.append(
                    f"PASS_INAPPLICABLE_NOT_NOT_REACHED_{acceptance_id}"
                )
            elif applicability == "unknown":
                errors.append(f"PASS_APPLICABILITY_UNKNOWN_{acceptance_id}")
    return errors
