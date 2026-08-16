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
METHOD_PATH = f"{RUNTIME_ROOT}/method/METHOD.md"
CORRIDOR_PATH = f"{RUNTIME_ROOT}/corridor"
FREEZE_PATH = f"{RUNTIME_ROOT}/FREEZE.json"
QA_PATH = f"{RUNTIME_ROOT}/qa/assessment.json"
CLOSURE_PATH = f"{RUNTIME_ROOT}/qa/closure.json"

FREEZE_SCHEMA = "charting-loop/frozen-task-corridor/v1"
ASSESSMENT_SCHEMA = "charting-loop/corridor-qa-assessment/v1"
QA_OUTCOMES = frozenset({"pass", "fail", "blocked", "not_assessed"})
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

        manifest = {{
            "schema_version": schema,
            "builder_corridor_status": status,
            "builder_failure": failure,
            "method_sha256": digest(method.read_bytes()) if method.is_file() else None,
            "corridor_tree_sha256": digest(canonical(files)),
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

    return f"""You are the Builder for one fresh Terminal-Bench trial.

Read the frozen method at {METHOD_PATH}. The official task is included below because
this is a task-conditioned Corridor: without the goal and public task environment,
you cannot compile the relevant constraints into a useful navigation aid.

{_task_block(task_instruction)}

Construct a reusable task-specific Corridor under {CORRIDOR_PATH}. It may contain
documentation, diagnostic commands, validators, planners, or a service. Inspect the
public task environment as needed, but do not carry out the official task or mutate
its target state. Do not read verifier/oracle material that the official task does
not expose to ordinary agents.

Experimental constraint: do not install a mandatory workflow gate, approval gate,
or pre-mutation gate that can block the later Worker from continuing. A Corridor may
diagnose, plan, validate, warn, or refuse an explicitly requested unsafe operation;
it must remain an aid the Worker chooses to call, not a new governance dependency.

Write only the Corridor and Builder scratch data under {RUNTIME_ROOT}. Leave a clear
README or entrypoint. Do not put a final task answer or precomputed writeback in the
Corridor. When finished, report what you built; the harness will freeze the bytes.
"""


def worker_prompt(task_instruction: str, corridor_digest_value: str) -> str:
    """Prompt the execution role with the exact frozen Corridor identity."""

    return f"""You are the Worker responsible for completing the official task.

{_task_block(task_instruction)}

The Builder's frozen task-conditioned Corridor is available read-only at
{CORRIDOR_PATH}. Its freeze manifest is {FREEZE_PATH}, and the harness-verified
Corridor digest is {corridor_digest_value}. Read the Corridor before acting and use
its diagnostics/planner/validator when relevant. The Corridor is an aid, not hidden
authority or a stored answer: inspect the live task state, obey the official task,
and independently verify every mutation.

Execute the task now. Do not wait for QA and do not create a gate around your work.
The harness will invoke an independent QA role afterward.
"""


def qa_prompt(task_instruction: str, corridor_digest_value: str) -> str:
    """Prompt an independent QA session that can use the same frozen Corridor."""

    return f"""You are the independent QA reviewer. Audit the Worker's current result.

{_task_block(task_instruction)}

You MUST read and may execute the same frozen, read-only Corridor at {CORRIDOR_PATH}.
The freeze manifest is {FREEZE_PATH}; the expected digest is
{corridor_digest_value}. Use the Corridor for global constraint checks and
counterfactual validation, not merely as prose context.

Do not mutate the official task state, repair the result, or alter the Corridor.
Diagnostic reads are allowed. Your only write is {QA_PATH}. Write one JSON object:

{{
  "schema_version": "{ASSESSMENT_SCHEMA}",
  "outcome": "pass|fail|blocked|not_assessed",
  "summary": "concise human-readable conclusion",
  "corridor_digest": "{corridor_digest_value}",
  "checks": [{{"name": "...", "status": "pass|fail|unknown", "evidence": "..."}}],
  "witnesses": [{{"constraint": "...", "evidence": "...", "replay": "..."}}]
}}

A fail verdict is valid only with at least one concrete witness whose constraint,
observed evidence, and safe replay procedure are all non-empty. If you cannot
produce such a witness, use blocked or not_assessed. QA is advisory: your verdict
must never prevent the official verifier from running.
"""


def repair_prompt(task_instruction: str, corridor_digest_value: str) -> str:
    """Resume the same Worker once when QA supplies a valid failure witness."""

    return f"""Resume as the SAME Worker for one bounded repair pass.

{_task_block(task_instruction)}

Read the independent QA assessment at {QA_PATH}. Re-read the same frozen Corridor
at {CORRIDOR_PATH}; its expected digest remains {corridor_digest_value}. Reproduce
each QA witness before changing anything. QA suggestions are not authority: reject
a locally plausible repair when the Corridor's complete constraints show it would
make the global result worse or infeasible.

Apply only repairs justified by reproduced witnesses, then verify the complete task
again. This is the single permitted repair pass. Do not create a new gate.
"""


def closure_prompt(task_instruction: str, corridor_digest_value: str) -> str:
    """Resume the same QA session to assess the one repair pass."""

    return f"""Resume as the SAME independent QA reviewer for closure verification.

{_task_block(task_instruction)}

The Worker has completed the single bounded repair pass. Re-read {QA_PATH}, inspect
the current task state, and use the same frozen Corridor at {CORRIDOR_PATH}. The
expected digest is still {corridor_digest_value}. Do not mutate task state or the
Corridor. Write the same JSON schema to {CLOSURE_PATH}; a fail still requires a
concrete constraint/evidence/replay witness. This closure is advisory and must not
gate the official verifier.
"""


def validate_qa_assessment(
    value: Any,
    *,
    expected_corridor_digest: str,
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

    checks = value.get("checks")
    if not isinstance(checks, list):
        errors.append("ASSESSMENT_CHECKS")
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
    if outcome == "fail" and not witnesses:
        errors.append("FAIL_WITNESS_REQUIRED")
    return errors
