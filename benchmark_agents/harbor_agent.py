"""Harbor adapter for the task-conditioned full Charting Loop method.

Import with::

    benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent

The adapter deliberately leaves benchmark grading to Harbor.  Its responsibility is
only the construction/execution/review sequence and a complete multi-agent ATIF
record.  All model calls occur inside the scored trial.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Agent, FinalMetrics, Step, Trajectory
from harbor.models.trial.paths import EnvironmentPaths
from harbor.utils.trajectory_utils import format_trajectory_json

from corridor_kit import KIT_VERSION, regular_tree_manifest

from benchmark_agents.contract import (
    ACCEPTANCE_PATH,
    CLOSURE_PATH,
    CAPABILITIES_PATH,
    FREEZE_PATH,
    CORRIDOR_PATH,
    GRAPH_PATH,
    STUDY_PROFILE_PATH,
    TYPED_RULE_IR_PATH,
    TYPED_RULE_REPORT_PATH,
    EXECUTION_TEST_ROOT,
    EXECUTION_TEST_QA_PATH,
    METHOD_PATH,
    METHOD_CONTENT_SHA256,
    METHOD_SCOPE_SHA256,
    METHOD_VERSION_ID,
    QA_PATH,
    POSITION_PATH,
    POSITION_ROOT,
    RUNTIME_ROOT,
    SUBMISSION_ROOT,
    SDK_PACKAGE_PATH,
    SDK_ROOT,
    WORK_PATH,
    WORKER_FACTS_PATH,
    builder_prompt,
    closure_prompt,
    freeze_program,
    load_qa_json_text,
    qa_prompt,
    private_custody_program,
    remote_json_read_program,
    repair_prompt,
    validate_qa_assessment,
    verify_freeze_program,
    worker_prompt,
    graph_study_profile,
    graph_compile_qa_prompt,
    graph_compile_failure_qa_prompt,
    graph_compile_repair_prompt,
    graph_compile_failure_repair_prompt,
    graph_implementation_prompt,
    graph_execution_test_plan_prompt,
    graph_execution_test_qa_prompt,
    graph_execution_test_repair_prompt,
    graph_result_repair_test_plan_prompt,
    graph_qa_prompt,
    graph_repair_prompt,
    graph_worker_prompt,
    validate_graph_compile_audit,
    validate_graph_compile_failure_audit,
    validate_execution_test_audit,
    validate_graph_audit,
)


AGENT_VERSION = "0.9.0"
GRAPH_AGENT_VERSION = "1.2.1"
METHOD_SOURCE_COMMIT = "3c3813444a7d43d0a56837e9cb960be86ce26d06"
METHOD_SOURCE_PATH = "method-paper/METHOD.md"
METHOD_SCOPE_PATH = "method-paper/SCOPE-DATUM.md"
ROLE_ORDER = ("builder", "worker", "qa")
DEFAULT_TASK_TIMEOUT_SECONDS = 5400
FINALIZATION_RESERVE_SECONDS = 30
TASK_TIMEOUT_RE = re.compile(
    r"\b(?:you\s+have|time(?:out| limit)|budget)\D{0,24}(\d{2,6})\s*seconds?\b",
    re.IGNORECASE,
)
PHASE_TOKEN_ENV = "CHARTING_LOOP_PHASE_TOKEN"
PHASE_NO_BYTECODE_EXPORT = "export PYTHONDONTWRITEBYTECODE=1"
QA_FACTS_PATH = "/tmp/charting-loop-qa-fact-candidates.json"


def _task_timeout_seconds(instruction: str) -> int:
    """Resolve one total task clock, preferring an explicit public instruction."""

    matches = [int(value) for value in TASK_TIMEOUT_RE.findall(instruction)]
    valid = [value for value in matches if value > FINALIZATION_RESERVE_SECONDS]
    return valid[-1] if valid else DEFAULT_TASK_TIMEOUT_SECONDS


def _remaining_seconds(deadline: float) -> int:
    return max(0, int(deadline - asyncio.get_running_loop().time()))


def _builder_freeze_metrics(
    freeze: dict[str, Any],
    *,
    elapsed_seconds: float,
    runtime_guide: dict[str, Any],
) -> dict[str, Any]:
    """Name a first-valid freeze only when all frozen readiness facts support it."""

    valid = bool(
        freeze.get("builder_corridor_status") == "frozen"
        and freeze.get("method_capsule_status") == "complete"
        and freeze.get("method_capsule_errors") == []
        and freeze.get("method_capsule_digest_matches_stored") is True
        and isinstance(freeze.get("method_capsule_digest"), str)
        and freeze.get("method_capsule_digest")
        == freeze.get("method_capsule_expected_digest")
        and freeze.get("method_capsule_digest")
        == freeze.get("method_capsule_stored_digest")
        and freeze.get("acceptance_ledger_status") == "complete"
        and freeze.get("source_mapping_status") == "complete"
        and freeze.get("definition_closure_status") == "complete"
        and freeze.get("construction_readiness_status") == "ready"
        and freeze.get("acceptance_ledger_errors") == []
        and runtime_guide.get("available") is True
        and runtime_guide.get("status") == "compiled"
        and runtime_guide.get("work_validation_ok") is True
        and runtime_guide.get("work_state") == "compiled"
        and runtime_guide.get("capability_state") == "compiled"
        and isinstance(runtime_guide.get("current_row_id"), str)
        and bool(runtime_guide.get("current_row_id"))
        and isinstance(runtime_guide.get("direction_digest"), str)
        and bool(runtime_guide.get("direction_digest"))
        and runtime_guide.get("advisory_only") is True
        and runtime_guide.get("authorizes_mutation") is False
    )
    elapsed = round(elapsed_seconds, 3)
    return {
        "freeze_elapsed_seconds": elapsed,
        "first_valid_freeze_recorded": valid,
        "first_valid_freeze_elapsed_seconds": elapsed if valid else None,
        "method_capsule_status": freeze.get("method_capsule_status", "missing"),
        "method_capsule_errors": freeze.get("method_capsule_errors", []),
        "method_capsule_digest": freeze.get("method_capsule_digest"),
        "method_capsule_expected_digest": freeze.get(
            "method_capsule_expected_digest"
        ),
        "method_capsule_stored_digest": freeze.get(
            "method_capsule_stored_digest"
        ),
        "method_capsule_digest_matches_stored": bool(
            freeze.get("method_capsule_digest_matches_stored")
        ),
        "work_backlog_status": runtime_guide.get("status", "invalid_or_missing"),
        "work_validation_ok": runtime_guide.get("work_validation_ok") is True,
        "capability_registry_status": runtime_guide.get(
            "capability_state", "missing"
        ),
        "runtime_guide_available": runtime_guide.get("available") is True,
        "runtime_guide_direction_digest": runtime_guide.get("direction_digest"),
    }


def _role_metrics_program(role_dir: str, corridor_path: str) -> str:
    """Return a private-log parser for construction latency and artifact size."""

    return f"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

role_dir = Path({role_dir!r})
corridor = Path({corridor_path!r})

def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

tool_started = {{}}
tool_wall = 0.0
agent_messages = 0
tool_calls = 0
session_started = None
session_completed = None
for path in sorted((role_dir / "sessions").rglob("*.jsonl")):
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        when = stamp(event.get("timestamp"))
        kind = payload.get("type")
        if kind == "task_started":
            session_started = stamp(payload.get("started_at")) or when
        elif kind == "task_complete":
            session_completed = stamp(payload.get("completed_at")) or when
        elif kind == "agent_message":
            agent_messages += 1
        elif kind == "custom_tool_call":
            tool_calls += 1
            if isinstance(payload.get("call_id"), str) and when is not None:
                tool_started[payload["call_id"]] = when
        elif kind == "custom_tool_call_output":
            call_id = payload.get("call_id")
            if isinstance(call_id, str) and when is not None and call_id in tool_started:
                tool_wall += max(0.0, when - tool_started.pop(call_id))

generated_files = 0
generated_bytes = 0
if corridor.is_dir() and not corridor.is_symlink():
    for path in corridor.rglob("*"):
        if path.is_file() and not path.is_symlink():
            generated_files += 1
            generated_bytes += path.stat().st_size
total_wall = (
    max(0.0, session_completed - session_started)
    if session_started is not None and session_completed is not None
    else None
)
capsule = {{}}
kit = {{}}
parse_errors = {{}}

def reject_duplicates(pairs):
    value = {{}}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate key: {{key}}")
        value[key] = item
    return value

for path, target in ((corridor / "METHOD-CAPSULE.json", capsule), (corridor / "KIT.json", kit)):
    if path.is_file() and not path.is_symlink():
        try:
            value = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=reject_duplicates,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ValueError(f"non-finite value: {{item}}")
                ),
            )
            if isinstance(value, dict):
                target.update(value)
            else:
                parse_errors[path.name] = "object_required"
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parse_errors[path.name] = type(exc).__name__
actual_capsule_digest = None
if capsule and "METHOD-CAPSULE.json" not in parse_errors:
    actual_capsule_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            capsule,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
stored_capsule_digest = kit.get("method_capsule_digest")
print(json.dumps({{
    "schema_version": "charting-loop/role-construction-metrics/v1",
    "turn_count": agent_messages,
    "tool_call_count": tool_calls,
    "tool_wall_seconds": round(tool_wall, 3),
    "inference_wall_seconds": (
        round(max(0.0, total_wall - tool_wall), 3) if total_wall is not None else None
    ),
    "total_wall_seconds": round(total_wall, 3) if total_wall is not None else None,
    "generated_file_count": generated_files,
    "generated_bytes": generated_bytes,
    "method_capsule": {{
        "schema_version": capsule.get("schema_version"),
        "binding_state": capsule.get("binding_state"),
        "method_version": capsule.get("method_version"),
        "method_digest": capsule.get("method_digest"),
        "method_scope_digest": capsule.get("method_scope_digest"),
        "capsule_digest": actual_capsule_digest,
        "stored_capsule_digest": stored_capsule_digest,
        "capsule_digest_matches_stored": (
            actual_capsule_digest is not None
            and actual_capsule_digest == stored_capsule_digest
        ),
        "parse_errors": parse_errors,
        "scaffold_digest": kit.get("starter_digest"),
    }},
    "metrics_are_descriptive": True,
}}, sort_keys=True))
"""


def _codex_runtime_discovery_command() -> str:
    """Resolve Codex and Node using the default agent user's runtime home."""

    return (
        "set -eu; "
        'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; export NVM_DIR; '
        'if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi; '
        'NODE_BIN="$(command -v node)"; CODEX_BIN="$(command -v codex)"; '
        'test -x "$NODE_BIN"; test -e "$CODEX_BIN"; '
        'codex --version >/dev/null; '
        'printf "%s\\n%s\\n" "$NODE_BIN" "$CODEX_BIN"'
    )


def _parse_codex_runtime_paths(stdout: str | None) -> tuple[str, str]:
    paths = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if len(paths) != 2 or any(not path.startswith("/") for path in paths):
        raise RuntimeError("Codex runtime discovery did not return two absolute paths")
    return paths[0], paths[1]


def _codex_runtime_binding_command(
    *,
    node_bin: str,
    codex_bin: str,
    stable_bin_dir: str = "/usr/local/bin",
) -> str:
    """Bind discovered runtime paths into a fresh-shell stable PATH."""

    source_node = shlex.quote(node_bin)
    source_codex = shlex.quote(codex_bin)
    bin_dir = shlex.quote(stable_bin_dir)
    fresh_path = shlex.quote(f"{stable_bin_dir}:/usr/bin:/bin")
    return (
        "set -eu; "
        f"NODE_BIN={source_node}; CODEX_BIN={source_codex}; STABLE_BIN_DIR={bin_dir}; "
        'test -x "$NODE_BIN"; test -e "$CODEX_BIN"; '
        'install -d -m 0755 "$STABLE_BIN_DIR"; '
        'ln -sf "$NODE_BIN" "$STABLE_BIN_DIR/node"; '
        'ln -sf "$CODEX_BIN" "$STABLE_BIN_DIR/codex"; '
        f"PATH={fresh_path} sh -c "
        + shlex.quote(
            "command -v node >/dev/null && "
            "command -v codex >/dev/null && codex --version"
        )
    )


def _phase_quiescence_program(token: str, *, terminate: bool) -> str:
    """Return a Linux /proc probe that only targets one phase token."""

    return f"""
import json
import os
import signal
import time
from pathlib import Path

token = {token!r}
needle = ({PHASE_TOKEN_ENV!r} + "=" + token).encode()

def scan():
    matches = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "environ").read_bytes().split(b"\\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if needle in fields:
            matches.append(int(entry.name))
    return sorted(matches)

def signal_exact(pids, sig):
    groups = set()
    for pid in pids:
        try:
            groups.add(os.getpgid(pid))
        except ProcessLookupError:
            pass
    for pgid in sorted(groups):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass

initial = scan()
term_pids = []
kill_pids = []
if {terminate!r} and initial:
    term_pids = initial
    signal_exact(term_pids, signal.SIGTERM)
    for _ in range(20):
        if not scan():
            break
        time.sleep(0.1)
    remaining = scan()
    if remaining:
        kill_pids = remaining
        signal_exact(kill_pids, signal.SIGKILL)
        for _ in range(30):
            if not scan():
                break
            time.sleep(0.1)

remaining = scan()
print(json.dumps({{
    "schema_version": "charting-loop/phase-quiescence/v1",
    "initial_pids": initial,
    "term_signal_pids": term_pids,
    "kill_signal_pids": kill_pids,
    "remaining_pids": remaining,
    "quiescent": not remaining,
}}, sort_keys=True))
""".strip()


class _PhaseCodex(Codex):
    """Codex child whose paid command has an owned remote process identity."""

    def begin_phase(self, phase: str) -> None:
        token = uuid.uuid4().hex
        self._phase_label = phase
        self._phase_token = token
        self._phase_token_hash = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
        self._phase_identity_path = f"/tmp/charting-loop-phase-{token}.json"
        self._last_phase_isolation: dict[str, Any] | None = None

    @staticmethod
    def _is_paid_codex_command(command: str) -> bool:
        return (
            "codex exec " in command
            and "--dangerously-bypass-approvals-and-sandbox" in command
            and "--json" in command
        )

    def _owned_command(self, command: str) -> str:
        token = getattr(self, "_phase_token", "")
        identity_path = getattr(self, "_phase_identity_path", "")
        token_hash = getattr(self, "_phase_token_hash", "")
        phase = getattr(self, "_phase_label", "")
        if not token or not identity_path or not phase:
            raise RuntimeError("Phase identity was not initialized before Codex launch")
        identity = (
            '{"schema_version":"charting-loop/phase-process/v1",'
            f'"phase":{json.dumps(phase)},"token_hash":{json.dumps(token_hash)},'
            '"pid":%s,"pgid":%s,"state":"running"}\\n'
        )
        session_command = (
            f"printf {shlex.quote(identity)} \"$$\" \"$$\" "
            f"> {shlex.quote(identity_path)}; "
            f"exec bash -o pipefail -c {shlex.quote(command)}"
        )
        return (
            "command -v setsid >/dev/null 2>&1 || "
            "{ echo 'setsid is required for phase isolation' >&2; exit 125; }; "
            "command -v bash >/dev/null 2>&1 || "
            "{ echo 'bash is required for phase status propagation' >&2; exit 125; }; "
            f"rm -f {shlex.quote(identity_path)}; "
            f"export {PHASE_TOKEN_ENV}={shlex.quote(token)}; "
            f"{PHASE_NO_BYTECODE_EXPORT}; "
            f"exec setsid -w bash -o pipefail -c "
            f"{shlex.quote(session_command)}"
        )

    @staticmethod
    def _prompt_file_command(command: str, prompt_path: str) -> tuple[str, str]:
        """Move Harbor's rendered Codex prompt out of the remote exec argv."""

        output_marker = " 2>&1 </dev/null | tee "
        invocation, marker, output_path = command.rpartition(output_marker)
        if not marker or not output_path.strip():
            raise RuntimeError("Paid Codex command output boundary was not recognized")
        prefix, prompt_marker, escaped_prompt = invocation.rpartition("-- ")
        if not prompt_marker:
            raise RuntimeError("Paid Codex command prompt boundary was not recognized")
        prompt_tokens = shlex.split(escaped_prompt)
        if len(prompt_tokens) != 1 or not prompt_tokens[0]:
            raise RuntimeError("Paid Codex command must contain one non-empty prompt")
        staged_command = (
            f"{prefix}-- - 2>&1 <{shlex.quote(prompt_path)} | tee {output_path}"
        )
        return staged_command, prompt_tokens[0]

    async def ensure_phase_quiescent(
        self,
        environment: BaseEnvironment,
        *,
        terminate: bool = True,
    ) -> dict[str, Any]:
        token = getattr(self, "_phase_token", "")
        token_hash = getattr(self, "_phase_token_hash", "")
        phase = getattr(self, "_phase_label", "")
        if not token:
            return {
                "schema_version": "charting-loop/phase-isolation/v1",
                "phase": phase,
                "token_hash": token_hash,
                "quiescent": False,
                "error": "phase_identity_missing",
            }
        result = await self.exec_as_root(
            environment,
            command=f"python3 -c {shlex.quote(_phase_quiescence_program(token, terminate=terminate))}",
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Phase quiescence probe returned no result")
        probe = json.loads(lines[-1])
        isolation = {
            "schema_version": "charting-loop/phase-isolation/v1",
            "phase": phase,
            "token_hash": token_hash,
            "identity_path": getattr(self, "_phase_identity_path", ""),
            **probe,
        }
        self._last_phase_isolation = isolation
        return isolation

    async def exec_as_agent(
        self,
        environment: BaseEnvironment,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        paid_command = self._is_paid_codex_command(command)
        if paid_command:
            token = getattr(self, "_phase_token", "")
            if not token:
                raise RuntimeError("Phase identity was not initialized before prompt staging")
            remote_prompt_path = f"/tmp/codex-secrets/phase-prompt-{token}.txt"
            command, prompt_text = self._prompt_file_command(
                command, remote_prompt_path
            )
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as prompt_file:
                prompt_file.write(prompt_text)
                prompt_file.flush()
                await environment.upload_file(
                    Path(prompt_file.name), remote_prompt_path
                )
            owner = getattr(environment, "default_user", None)
            owner_command = (
                f"chown {shlex.quote(str(owner))} {shlex.quote(remote_prompt_path)}; "
                if owner is not None
                else ""
            )
            await self.exec_as_root(
                environment,
                command=owner_command
                + f"chmod 0400 {shlex.quote(remote_prompt_path)}",
            )
            owned_command = self._owned_command(command)
        else:
            owned_command = command
        try:
            return await super().exec_as_agent(
                environment,
                command=owned_command,
                env=env,
                cwd=cwd,
                timeout_sec=timeout_sec,
            )
        except asyncio.CancelledError:
            if paid_command:
                cleanup = asyncio.create_task(
                    self.ensure_phase_quiescent(environment, terminate=True)
                )
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
            raise


def _sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _git_blob(repository_root: Path, commit: str, path: str) -> bytes:
    """Read one blob from an exact commit without consulting mutable worktree bytes."""

    commit_check = subprocess.run(
        ["git", "-C", str(repository_root), "cat-file", "-e", f"{commit}^{{commit}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if commit_check.returncode != 0:
        raise RuntimeError("Frozen method source_commit is not an available commit")
    shown = subprocess.run(
        ["git", "-C", str(repository_root), "show", f"{commit}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if shown.returncode != 0:
        raise RuntimeError(f"Frozen method blob is unavailable: {path}")
    return shown.stdout


def _resolve_frozen_method(repository_root: Path) -> bytes:
    """Resolve the exact v7 bytes or fail before a paid model call."""

    index_path = repository_root / "method-paper" / "VERSIONS.json"
    document = json.loads(index_path.read_text(encoding="utf-8"))
    versions = document.get("versions")
    matches = (
        [item for item in versions if item.get("version_id") == METHOD_VERSION_ID]
        if isinstance(versions, list)
        and all(isinstance(item, dict) for item in versions)
        else []
    )
    if len(matches) != 1:
        raise RuntimeError(f"Frozen method identity must resolve once: {METHOD_VERSION_ID}")
    version = matches[0]
    expected = {
        "status": "frozen",
        "study_eligible": True,
        "adoption_eligible": False,
        "builder_eligible": False,
        "source_commit": METHOD_SOURCE_COMMIT,
        "path": METHOD_SOURCE_PATH,
        "content_sha256": METHOD_CONTENT_SHA256,
        "scope_datum_path": METHOD_SCOPE_PATH,
        "scope_datum_sha256": METHOD_SCOPE_SHA256,
    }
    mismatches = [key for key, value in expected.items() if version.get(key) != value]
    if mismatches:
        raise RuntimeError(
            "Frozen method catalog binding changed: " + ", ".join(mismatches)
        )
    method_bytes = _git_blob(repository_root, METHOD_SOURCE_COMMIT, METHOD_SOURCE_PATH)
    scope_bytes = _git_blob(repository_root, METHOD_SOURCE_COMMIT, METHOD_SCOPE_PATH)
    if _sha256_bytes(method_bytes) != METHOD_CONTENT_SHA256:
        raise RuntimeError("Frozen METHOD.md Git blob does not match the v7 digest")
    if _sha256_bytes(scope_bytes) != METHOD_SCOPE_SHA256:
        raise RuntimeError("Frozen SCOPE-DATUM.md Git blob does not match the v7 digest")
    return method_bytes


class ChartingLoopFullMethodAgent(Codex):
    """Build, freeze, use, and independently audit one Corridor per trial."""

    SUPPORTS_HANDOFF = False
    ROLE_SEQUENCE = ROLE_ORDER
    ORCHESTRATION_MESSAGE = (
        "Deterministic orchestration: Builder -> frozen Corridor -> Worker -> "
        "independent Corridor-visible QA -> optional same-Worker repair and "
        "same-QA closure."
    )
    ORCHESTRATION_METHOD = "task-conditioned-corridor"

    @staticmethod
    def name() -> str:
        return "charting-loop-full-method"

    def version(self) -> str:
        return AGENT_VERSION

    @property
    def _method_source(self) -> bytes:
        return _resolve_frozen_method(Path(__file__).resolve().parents[1])

    @property
    def _sdk_source(self) -> Path:
        path = Path(__file__).resolve().parents[1] / "corridor_kit"
        if not path.is_dir() or path.is_symlink():
            raise FileNotFoundError(f"Corridor SDK source missing: {path}")
        return path

    def _sdk_manifest(self) -> dict[str, Any]:
        return regular_tree_manifest(self._sdk_source)

    def _child_agent(self, role: str) -> Codex:
        child = _PhaseCodex(
            logs_dir=self.logs_dir / "phases" / role,
            model_name=self.model_name,
            logger=self.logger,
            mcp_servers=self.mcp_servers,
            skills_dir=self.skills_dir,
            extra_env=self.extra_env,
            config=self.config_source,
            **self._flag_kwargs,
        )
        child._OUTPUT_FILENAME = f"codex-{role}.txt"
        child.session_id = f"{self.session_id or 'trial'}-{role}"
        child.context_id = self.context_id
        return child

    async def _append_position_event(
        self,
        environment: BaseEnvironment,
        *,
        actor: str,
        event_type: str,
        status: str,
        row_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one runner-held RAW observation and leave the ledger read-only."""

        details_json = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
        program = (
            "import json; from pathlib import Path; "
            "from corridor_kit.runtime import append_position_event; "
            "event=append_position_event("
            f"Path({POSITION_PATH!r}), actor={actor!r}, event_type={event_type!r}, "
            f"status={status!r}, row_id={row_id!r}, details=json.loads({details_json!r})); "
            "print(json.dumps(event, sort_keys=True))"
        )
        result = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -c {shlex.quote(program)} && "
                f"chmod 0444 {shlex.quote(POSITION_PATH)}"
            ),
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            raise RuntimeError("Position timeline append failed")
        return json.loads(lines[-1])

    async def _runtime_guide(self, environment: BaseEnvironment) -> dict[str, Any]:
        """Read the frozen runtime projection without making it a phase gate."""

        validation = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit validate-work "
                f"{shlex.quote(WORK_PATH)} "
                f"--acceptance {shlex.quote(ACCEPTANCE_PATH)} "
                f"--capabilities {shlex.quote(CAPABILITIES_PATH)}"
            ),
        )
        try:
            validation_report = json.loads(validation.stdout or "{}")
        except (TypeError, json.JSONDecodeError):
            validation_report = {}
        result = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit runtime guide "
                f"--work {shlex.quote(WORK_PATH)} "
                f"--acceptance {shlex.quote(ACCEPTANCE_PATH)} "
                f"--capabilities {shlex.quote(CAPABILITIES_PATH)} "
                f"--timeline {shlex.quote(POSITION_PATH)}"
            ),
        )
        if result.return_code != 0 or not result.stdout:
            return {
                "available": False,
                "status": "invalid_or_missing",
                "current_row_id": None,
            }
        try:
            guide = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            return {
                "available": False,
                "status": "unreadable",
                "current_row_id": None,
            }
        return {
            "available": True,
            "status": (
                "compiled"
                if validation.return_code == 0
                and guide.get("work_state") == "compiled"
                and guide.get("capability_state") == "compiled"
                else "invalid_or_uncompiled"
            ),
            "work_validation_ok": validation.return_code == 0
            and validation_report.get("ok") is True,
            "work_validation_error_count": len(
                validation_report.get("errors", [])
                if isinstance(validation_report.get("errors"), list)
                else []
            ),
            "work_state": guide.get("work_state"),
            "capability_state": guide.get("capability_state"),
            "current_row_id": guide.get("position", {}).get("current_row_id"),
            "work_backlog_digest": guide.get("position", {}).get(
                "work_backlog_digest"
            ),
            "timeline_head": guide.get("position", {}).get("timeline_head"),
            "position_ref": guide.get("position", {}).get("position_ref"),
            "direction_digest": guide.get("direction", {}).get(
                "direction_digest"
            ),
            "rule_closure_digest": guide.get("direction", {}).get(
                "rule_closure_digest"
            ),
            "admitted_fact_digest": guide.get("direction", {}).get(
                "admitted_fact_digest"
            ),
            "current_row_fact_count": len(
                guide.get("direction", {}).get("current_row_facts", [])
            ),
            "witness_gap_count": len(
                guide.get("direction", {}).get("witness_gaps", [])
            ),
            "entrance_ref": guide.get("entrance", {}).get("entrance_ref"),
            "reminder_count": len(guide.get("reminders", [])),
            "capability_ids": [
                item.get("capability_id")
                for item in guide.get("capabilities", [])
                if isinstance(item, dict)
            ],
            "advisory_only": guide.get("advisory_only") is True,
            "authorizes_mutation": guide.get("authorizes_mutation") is True,
        }

    async def _record_position_event(
        self,
        metadata: dict[str, Any],
        environment: BaseEnvironment,
        **event: Any,
    ) -> None:
        """Retain evidence loss without turning the advisory timeline into a gate."""

        try:
            appended = await self._append_position_event(environment, **event)
        except Exception as exc:
            metadata.setdefault("position_timeline_errors", []).append(
                {
                    "event_type": event.get("event_type"),
                    "error_type": type(exc).__name__,
                }
            )
        else:
            metadata.setdefault("position_events", []).append(
                {
                    "event_id": appended["event_id"],
                    "event_type": appended["event_type"],
                    "event_hash": appended["event_hash"],
                }
            )

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        discovered = await self.exec_as_agent(
            environment,
            command=_codex_runtime_discovery_command(),
        )
        node_bin, codex_bin = _parse_codex_runtime_paths(discovered.stdout)
        await self.exec_as_root(
            environment,
            command=_codex_runtime_binding_command(
                node_bin=node_bin,
                codex_bin=codex_bin,
            ),
        )
        method_source = self._method_source

        sdk_manifest = self._sdk_manifest()
        self._sdk_identity = {
            "kit_version": KIT_VERSION,
            "tree_digest": sdk_manifest["tree_digest"],
            "file_count": len(sdk_manifest["files"]),
        }
        corridor_dir = str(PurePosixPath(RUNTIME_ROOT) / "corridor")
        scratch_dir = str(PurePosixPath(RUNTIME_ROOT) / "builder-scratch")
        method_dir = str(PurePosixPath(METHOD_PATH).parent)
        user = shlex.quote(str(environment.default_user or "root"))
        await self.exec_as_root(
            environment,
            command=(
                f"install -d -m 0755 {shlex.quote(RUNTIME_ROOT)} "
                f"{shlex.quote(method_dir)} {shlex.quote(corridor_dir)} "
                f"{shlex.quote(scratch_dir)} {shlex.quote(SDK_PACKAGE_PATH)} "
                f"{shlex.quote(POSITION_ROOT)} {shlex.quote(SUBMISSION_ROOT)}"
            ),
        )
        with tempfile.NamedTemporaryFile(prefix="charting-loop-method-", suffix=".md") as method_file:
            method_file.write(method_source)
            method_file.flush()
            await self._upload_agent_owned_file(
                environment,
                Path(method_file.name),
                METHOD_PATH,
            )
        sdk_parents = sorted(
            {
                PurePosixPath(SDK_PACKAGE_PATH, item["path"]).parent.as_posix()
                for item in sdk_manifest["files"]
            }
        )
        if sdk_parents:
            await self.exec_as_root(
                environment,
                command="install -d -m 0755 "
                + " ".join(shlex.quote(path) for path in sdk_parents),
            )
        for item in sdk_manifest["files"]:
            relative = Path(item["path"])
            await self._upload_agent_owned_file(
                environment,
                self._sdk_source / relative,
                PurePosixPath(SDK_PACKAGE_PATH, item["path"]).as_posix(),
            )
        remote_manifest = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -m corridor_kit manifest {shlex.quote(SDK_PACKAGE_PATH)}"
            ),
        )
        remote_lines = [
            line for line in (remote_manifest.stdout or "").splitlines() if line.strip()
        ]
        if remote_manifest.return_code != 0 or not remote_lines:
            raise RuntimeError("Corridor SDK remote manifest failed")
        remote_identity = json.loads("\n".join(remote_lines))
        if remote_identity.get("tree_digest") != sdk_manifest["tree_digest"]:
            raise RuntimeError("Corridor SDK upload digest mismatch")
        await self.exec_as_root(
            environment,
            command=(
                f"chown -R 0:0 {shlex.quote(SDK_ROOT)} && "
                f"find {shlex.quote(SDK_ROOT)} -type d -exec chmod 0555 {{}} + && "
                f"find {shlex.quote(SDK_ROOT)} -type f -exec chmod 0444 {{}} +"
            ),
        )
        initialized = await self.exec_as_root(
            environment,
            command=(
                f"rmdir {shlex.quote(corridor_dir)} && "
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit init "
                f"{shlex.quote(corridor_dir)} "
                f"--method-version {shlex.quote(METHOD_VERSION_ID)} "
                f"--method-digest {shlex.quote(METHOD_CONTENT_SHA256)} "
                f"--method-scope-digest {shlex.quote(METHOD_SCOPE_SHA256)} && "
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit validate-capsule "
                f"{shlex.quote(corridor_dir + '/METHOD-CAPSULE.json')} "
                f"--kit {shlex.quote(corridor_dir + '/KIT.json')} "
                f"--expected-method-version {shlex.quote(METHOD_VERSION_ID)} "
                f"--expected-method-digest {shlex.quote(METHOD_CONTENT_SHA256)} "
                "--expected-method-scope-digest "
                f"{shlex.quote(METHOD_SCOPE_SHA256)}"
            ),
        )
        if initialized.return_code != 0:
            raise RuntimeError(
                "Corridor SDK starter initialization failed: "
                + (initialized.stderr or initialized.stdout or "no output")[-2000:]
            )
        await self._append_position_event(
            environment,
            actor="runner",
            event_type="run_initialized",
            status="observed",
            details={"sdk_tree_digest": sdk_manifest["tree_digest"]},
        )
        await self.exec_as_root(
            environment,
            command=(
                f"chown -R 0:0 {shlex.quote(RUNTIME_ROOT)} && "
                f"chmod 0555 {shlex.quote(RUNTIME_ROOT)} "
                f"{shlex.quote(method_dir)} && "
                f"chmod 0444 {shlex.quote(METHOD_PATH)} && "
                f"chown {user} {shlex.quote(corridor_dir)} "
                f"{shlex.quote(scratch_dir)} {shlex.quote(SUBMISSION_ROOT)} && "
                f"chmod 0700 {shlex.quote(corridor_dir)} "
                f"{shlex.quote(scratch_dir)} {shlex.quote(SUBMISSION_ROOT)} && "
                f"chown -R 0:0 {shlex.quote(POSITION_ROOT)} && "
                f"chmod 0555 {shlex.quote(POSITION_ROOT)} && "
                f"chmod 0444 {shlex.quote(POSITION_PATH)}"
            ),
        )

    async def _reset_live_session(self, environment: BaseEnvironment) -> None:
        await self.exec_as_agent(
            environment,
            command=f"rm -rf {shlex.quote(str(EnvironmentPaths.agent_dir / 'sessions'))}",
        )

    async def _archive_role(
        self,
        environment: BaseEnvironment,
        role: str,
        output_filename: str,
    ) -> None:
        agent_dir = PurePosixPath(EnvironmentPaths.agent_dir)
        role_dir = agent_dir / "phases" / role
        sessions = agent_dir / "sessions"
        output = agent_dir / output_filename
        command = (
            f"rm -rf {shlex.quote(role_dir.as_posix())} && "
            f"mkdir -p {shlex.quote(role_dir.as_posix())} && "
            f"if test -d {shlex.quote(sessions.as_posix())}; then "
            f"cp -R {shlex.quote(sessions.as_posix())} "
            f"{shlex.quote((role_dir / 'sessions').as_posix())}; fi && "
            f"if test -f {shlex.quote(output.as_posix())}; then "
            f"cp {shlex.quote(output.as_posix())} "
            f"{shlex.quote((role_dir / 'codex.txt').as_posix())}; fi"
        )
        await self.exec_as_agent(environment, command=command)

    async def _collect_role_metrics(
        self, environment: BaseEnvironment, *, role: str
    ) -> dict[str, Any]:
        agent_dir = PurePosixPath(EnvironmentPaths.agent_dir)
        role_dir = (agent_dir / "phases" / role).as_posix()
        result = await self.exec_as_agent(
            environment,
            command=(
                "python3 -c "
                + shlex.quote(_role_metrics_program(role_dir, CORRIDOR_PATH))
            ),
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            return {"available": False, "error": "role_metrics_unavailable"}
        try:
            return {"available": True, **json.loads(lines[-1])}
        except json.JSONDecodeError:
            return {"available": False, "error": "role_metrics_unreadable"}

    async def _restore_role(
        self,
        environment: BaseEnvironment,
        role: str,
    ) -> None:
        agent_dir = PurePosixPath(EnvironmentPaths.agent_dir)
        saved = agent_dir / "phases" / role / "sessions"
        live = agent_dir / "sessions"
        await self.exec_as_agent(
            environment,
            command=(
                f"test -d {shlex.quote(saved.as_posix())} && "
                f"rm -rf {shlex.quote(live.as_posix())} && "
                f"cp -R {shlex.quote(saved.as_posix())} "
                f"{shlex.quote(live.as_posix())}"
            ),
        )

    async def _run_new_role(
        self,
        role: str,
        agent: Codex,
        prompt: str,
        environment: BaseEnvironment,
        *,
        deadline: float,
    ) -> tuple[AgentContext, dict[str, Any]]:
        phase_context = AgentContext()
        remaining_at_start = max(
            0.0, deadline - asyncio.get_running_loop().time()
        )
        outcome: dict[str, Any] = {
            "phase": role,
            "role": role,
            "mode": "new",
            "deadline_scope": "task",
            "remaining_seconds_at_start": round(remaining_at_start, 3),
            "status": "completed",
            "archived": False,
            "quiescent": False,
        }
        cancelled: asyncio.CancelledError | None = None
        begin_phase = getattr(agent, "begin_phase", None)
        if begin_phase is None:
            outcome["status"] = "isolation_failed"
            outcome["isolation_error"] = "phase_agent_has_no_identity_boundary"
            return phase_context, outcome
        begin_phase(role)
        phase_started_at = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout_at(deadline):
                await self._reset_live_session(environment)
                await agent.run(prompt, environment, phase_context)
        except TimeoutError:
            outcome["status"] = "task_deadline_reached"
        except asyncio.CancelledError as exc:
            outcome["status"] = "cancelled"
            cancelled = exc
        except Exception as exc:
            outcome["status"] = "failed"
            outcome["error_type"] = type(exc).__name__
        finally:
            try:
                isolation = await agent.ensure_phase_quiescent(
                    environment,
                    terminate=True,
                )
                outcome["process_isolation"] = isolation
                outcome["quiescent"] = bool(isolation.get("quiescent"))
            except Exception as exc:
                outcome["isolation_error_type"] = type(exc).__name__
                outcome["quiescent"] = False
            if outcome["quiescent"]:
                try:
                    await self._archive_role(
                        environment,
                        role,
                        agent._OUTPUT_FILENAME,
                    )
                    outcome["archived"] = True
                    outcome["role_metrics"] = await self._collect_role_metrics(
                        environment, role=role
                    )
                except Exception as exc:
                    outcome["archive_error_type"] = type(exc).__name__
            else:
                outcome["execution_status"] = outcome["status"]
                outcome["status"] = "isolation_failed"
        if cancelled is not None:
            raise cancelled
        outcome["elapsed_seconds"] = round(
            asyncio.get_running_loop().time() - phase_started_at, 3
        )
        return phase_context, outcome

    async def _resume_role(
        self,
        role: str,
        agent: Codex,
        prompt: str,
        environment: BaseEnvironment,
        *,
        phase: str,
        deadline: float,
    ) -> tuple[AgentContext, dict[str, Any]]:
        phase_context = AgentContext()
        remaining_at_start = max(
            0.0, deadline - asyncio.get_running_loop().time()
        )
        outcome: dict[str, Any] = {
            "phase": phase,
            "role": role,
            "mode": "resume",
            "deadline_scope": "task",
            "remaining_seconds_at_start": round(remaining_at_start, 3),
            "status": "completed",
            "archived": False,
            "quiescent": False,
        }
        cancelled: asyncio.CancelledError | None = None
        begin_phase = getattr(agent, "begin_phase", None)
        if begin_phase is None:
            outcome["status"] = "isolation_failed"
            outcome["isolation_error"] = "phase_agent_has_no_identity_boundary"
            return phase_context, outcome
        begin_phase(phase)
        try:
            async with asyncio.timeout_at(deadline):
                await self._restore_role(environment, role)
                await agent.resume(prompt, environment, phase_context)
        except TimeoutError:
            outcome["status"] = "timed_out"
        except asyncio.CancelledError as exc:
            outcome["status"] = "cancelled"
            cancelled = exc
        except Exception as exc:
            outcome["status"] = "failed"
            outcome["error_type"] = type(exc).__name__
        finally:
            try:
                isolation = await agent.ensure_phase_quiescent(
                    environment,
                    terminate=True,
                )
                outcome["process_isolation"] = isolation
                outcome["quiescent"] = bool(isolation.get("quiescent"))
            except Exception as exc:
                outcome["isolation_error_type"] = type(exc).__name__
                outcome["quiescent"] = False
            if outcome["quiescent"]:
                try:
                    await self._archive_role(
                        environment,
                        role,
                        agent._OUTPUT_FILENAME,
                    )
                    outcome["archived"] = True
                except Exception as exc:
                    outcome["archive_error_type"] = type(exc).__name__
            else:
                outcome["execution_status"] = outcome["status"]
                outcome["status"] = "isolation_failed"
        if cancelled is not None:
            raise cancelled
        return phase_context, outcome

    async def _freeze_corridor(self, environment: BaseEnvironment) -> dict[str, Any]:
        result = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -c {shlex.quote(freeze_program())}"
            ),
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("Corridor freezer returned no identity")
        identity = json.loads(lines[-1])
        digest = identity.get("corridor_digest")
        if not isinstance(digest, str):
            raise RuntimeError("Corridor freezer returned no digest")

        # Lock the complete construction area.  The QA evidence directory is
        # created only after Worker returns, so Worker cannot pre-populate QA's
        # result.  It is re-sealed before any repair continuation.
        await self.exec_as_root(
            environment,
            command=(
                f"chown -R 0:0 {shlex.quote(RUNTIME_ROOT)} && "
                f"chmod -R a-w {shlex.quote(RUNTIME_ROOT)}"
            ),
        )
        await self._verify_freeze(environment, expected_digest=digest)
        return identity

    async def _open_qa_directory(self, environment: BaseEnvironment) -> None:
        qa_dir = PurePosixPath(QA_PATH).parent.as_posix()
        user = shlex.quote(str(environment.default_user or "root"))
        await self.exec_as_root(
            environment,
            command=(
                f"mkdir -p {shlex.quote(qa_dir)} && "
                f"chown {user} {shlex.quote(qa_dir)} && "
                f"chmod 0700 {shlex.quote(qa_dir)}"
            ),
        )

    async def _seal_qa_directory(self, environment: BaseEnvironment) -> None:
        qa_dir = PurePosixPath(QA_PATH).parent.as_posix()
        await self.exec_as_root(
            environment,
            command=(
                f"if test -d {shlex.quote(qa_dir)}; then "
                f"chown -R 0:0 {shlex.quote(qa_dir)} && "
                f"find {shlex.quote(qa_dir)} -type d -exec chmod 0555 {{}} + && "
                f"find {shlex.quote(qa_dir)} -type f -exec chmod 0444 {{}} +; "
                "fi"
            ),
        )

    async def _prepare_worker_fact_path(self, environment: BaseEnvironment) -> None:
        """Create one role-writable candidate file without granting timeline access."""

        user = shlex.quote(str(environment.default_user or "root"))
        await self.exec_as_root(
            environment,
            command=(
                f"rm -f {shlex.quote(WORKER_FACTS_PATH)} && "
                f"install -m 0600 -o {user} /dev/null {shlex.quote(WORKER_FACTS_PATH)}"
            ),
        )

    async def _seal_worker_fact_path(self, environment: BaseEnvironment) -> None:
        await self.exec_as_root(
            environment,
            command=(
                f"if test -f {shlex.quote(WORKER_FACTS_PATH)}; then "
                f"chown 0:0 {shlex.quote(WORKER_FACTS_PATH)} && "
                f"chmod 0400 {shlex.quote(WORKER_FACTS_PATH)}; fi"
            ),
        )

    async def _write_root_json(
        self, environment: BaseEnvironment, *, path: str, value: dict[str, Any]
    ) -> None:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        transfer_id = uuid.uuid4().hex
        remote_source = f"/tmp/charting-loop-root-json-{transfer_id}.json"
        remote_target = f"{path}.tmp-{transfer_id}"
        program = (
            "import json, os; from pathlib import Path; "
            f"source=Path({remote_source!r}); target=Path({path!r}); "
            f"temporary=Path({remote_target!r}); "
            "data=source.read_bytes(); value=json.loads(data.decode('utf-8')); "
            "canonical=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\\n').encode('utf-8'); "
            "assert data == canonical, 'uploaded JSON is not canonical'; "
            "temporary.write_bytes(data); temporary.chmod(0o400); "
            "os.replace(temporary,target); target.chmod(0o400)"
        )
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix="charting-loop-root-json-", suffix=".json"
            ) as payload_file:
                payload_file.write(encoded.encode("utf-8"))
                payload_file.flush()
                await environment.upload_file(Path(payload_file.name), remote_source)
            result = await self.exec_as_root(
                environment,
                command=(
                    f"python3 -c {shlex.quote(program)}; status=$?; "
                    f"rm -f {shlex.quote(remote_source)} {shlex.quote(remote_target)}; "
                    "exit $status"
                ),
            )
            if result.return_code != 0:
                raise RuntimeError(
                    f"Root JSON write failed for {path}: "
                    f"{(result.stderr or '').strip()}"
                )
        except BaseException:
            try:
                await self.exec_as_root(
                    environment,
                    command=(
                        f"rm -f {shlex.quote(remote_source)} "
                        f"{shlex.quote(remote_target)}"
                    ),
                )
            except Exception:
                pass
            raise

    async def _admit_fact_file(
        self,
        environment: BaseEnvironment,
        *,
        path: str,
        role: str,
        candidate_ref: str,
        corridor_digest: str,
        guide: dict[str, Any],
    ) -> dict[str, Any]:
        """Admit candidates advisory-first; malformed input never stops the task."""

        position_ref = guide.get("position_ref")
        row_id = guide.get("current_row_id")
        if not isinstance(position_ref, str) or not position_ref:
            return {"ok": False, "admitted": 0, "status": "position_unavailable"}
        present = await self.exec_as_root(
            environment,
            command=f"test -s {shlex.quote(path)}",
        )
        if present.return_code != 0:
            return {"ok": True, "admitted": 0, "status": "no_candidates"}
        result = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit timeline admit-facts "
                f"{shlex.quote(POSITION_PATH)} --candidate {shlex.quote(path)} "
                f"--work {shlex.quote(WORK_PATH)} --acceptance {shlex.quote(ACCEPTANCE_PATH)} "
                f"--actor runner --expected-corridor-digest {shlex.quote(corridor_digest)} "
                f"--expected-position-ref {shlex.quote(position_ref)} "
                f"--expected-role {shlex.quote(role)} "
                f"--expected-candidate-ref {shlex.quote(candidate_ref)}"
            ),
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            return {
                "ok": False,
                "admitted": 0,
                "status": "candidate_rejected",
                "error": (result.stderr or result.stdout or "no output")[-2000:],
                "row_id": row_id,
            }
        try:
            return {"status": "admitted", **json.loads(lines[-1])}
        except json.JSONDecodeError:
            return {"ok": False, "admitted": 0, "status": "admission_unreadable"}

    async def _admit_qa_witnesses(
        self,
        environment: BaseEnvironment,
        *,
        assessment: dict[str, Any] | None,
        decision: dict[str, Any],
        candidate_ref: str | None,
        corridor_digest: str,
        guide: dict[str, Any],
    ) -> dict[str, Any]:
        if decision.get("valid") is not True:
            return {"ok": True, "admitted": 0, "status": "invalid_assessment"}
        if decision.get("outcome") != "fail":
            return {"ok": True, "admitted": 0, "status": "non_failure_assessment"}
        if not isinstance(candidate_ref, str) or not candidate_ref:
            return {"ok": True, "admitted": 0, "status": "no_verified_worker_snapshot"}
        witnesses = assessment.get("witnesses", []) if isinstance(assessment, dict) else []
        candidates: list[dict[str, str]] = []
        for index, witness in enumerate(witnesses if isinstance(witnesses, list) else []):
            if not isinstance(witness, dict):
                continue
            candidates.append(
                {
                    "candidate_id": f"QA-{index + 1:04d}",
                    "role": "qa",
                    "corridor_digest": corridor_digest,
                    "position_ref": witness.get("position_ref"),
                    "row_id": witness.get("row_id"),
                    "acceptance_id": witness.get("acceptance_id"),
                    "obligation_partition": witness.get("obligation_partition"),
                    "observation": witness.get("evidence"),
                    "source_ref": witness.get("source_ref"),
                    "witness_ref": witness.get("witness_ref"),
                    "replay_ref": witness.get("replay"),
                    "candidate_ref": witness.get("candidate_ref"),
                }
            )
        if not candidates:
            return {"ok": True, "admitted": 0, "status": "no_candidates"}
        await self._write_root_json(
            environment,
            path=QA_FACTS_PATH,
            value={
                "schema_version": "charting-loop/fact-candidates/v1",
                "candidates": candidates,
            },
        )
        return await self._admit_fact_file(
            environment,
            path=QA_FACTS_PATH,
            role="qa",
            candidate_ref=candidate_ref,
            corridor_digest=corridor_digest,
            guide=guide,
        )

    async def _freeze_submission_paths(
        self,
        environment: BaseEnvironment,
        *,
        role: str,
        paths: list[str],
    ) -> dict[str, Any]:
        """Freeze declared paths without granting the runner extra OS authority."""

        command = (
            f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
            "python3 -m corridor_kit submission freeze "
            f"--root {shlex.quote(SUBMISSION_ROOT)} --role {shlex.quote(role)} "
            + " ".join(f"--path {shlex.quote(path)}" for path in paths)
        )
        result = await environment.exec(
            command=command,
            user=environment.default_user,
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            return {
                "ok": False,
                "role": role,
                "status": "snapshot_not_created",
                "error": (result.stderr or result.stdout or "no output")[-2000:],
            }
        try:
            snapshot = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            return {
                "ok": False,
                "role": role,
                "status": "snapshot_unreadable",
            }
        return {"status": "snapshot_created", **snapshot}

    async def _validate_qa_presubmit(
        self, environment: BaseEnvironment, *, path: str
    ) -> dict[str, Any]:
        """Run the SDK validator before custody; invalid QA remains advisory."""

        result = await environment.exec(
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit qa validate "
                f"--path {shlex.quote(path)} --freeze {shlex.quote(FREEZE_PATH)}"
            ),
            user=environment.default_user,
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            return {
                "schema_version": "charting-loop/qa-assessment-decision/v1",
                "valid": False,
                "errors": ["ASSESSMENT_PRESUBMIT_UNREADABLE"],
                "reported_outcome": None,
                "outcome": "not_assessed",
                "repair_required": False,
                "raw_preserved": True,
                "advisory_only": True,
                "blocking_gate": False,
                "authorizes_mutation": False,
            }
        try:
            return json.loads("\n".join(lines))
        except json.JSONDecodeError:
            return {
                "schema_version": "charting-loop/qa-assessment-decision/v1",
                "valid": False,
                "errors": ["ASSESSMENT_PRESUBMIT_JSON"],
                "reported_outcome": None,
                "outcome": "not_assessed",
                "repair_required": False,
                "raw_preserved": True,
                "advisory_only": True,
                "blocking_gate": False,
                "authorizes_mutation": False,
            }

    async def _restore_latest_worker_submission(
        self, environment: BaseEnvironment
    ) -> dict[str, Any]:
        """Promote the newest verified Worker version using Worker authority."""

        result = await environment.exec(
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit submission restore "
                f"--root {shlex.quote(SUBMISSION_ROOT)} --role worker"
            ),
            user=environment.default_user,
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            return {
                "ok": False,
                "status": "no_verified_worker_snapshot",
                "error": (result.stderr or result.stdout or "no output")[-2000:],
            }
        try:
            restored = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            return {"ok": False, "status": "worker_snapshot_restore_unreadable"}
        return {"status": "worker_snapshot_restored", **restored}

    async def _worker_revision_progress(
        self, environment: BaseEnvironment
    ) -> dict[str, Any]:
        """Return solution-free Worker checkpoint/revision telemetry."""

        result = await environment.exec(
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                "python3 -m corridor_kit submission list "
                f"--root {shlex.quote(SUBMISSION_ROOT)} --role worker"
            ),
            user=environment.default_user,
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            return {
                "available": False,
                "snapshot_count": 0,
                "checkpoint_advance_count": 0,
                "content_revision_count": 0,
                "validation_refreeze_count": 0,
                "last_frozen_at": None,
                "snapshots": [],
            }
        try:
            history = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            return {"available": False, "error": "revision_history_unreadable"}
        progress = history.get("revision_progress")
        if not isinstance(progress, dict):
            return {"available": False, "error": "revision_progress_missing"}
        return {"available": True, **progress}

    async def _verify_freeze(
        self,
        environment: BaseEnvironment,
        *,
        expected_digest: str,
    ) -> None:
        result = await environment.exec(
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -c {shlex.quote(verify_freeze_program())}"
            ),
            user=environment.default_user,
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if result.return_code != 0 or not lines:
            raise RuntimeError(
                "Frozen Corridor verification failed: "
                + (result.stderr or result.stdout or "no probe output")
            )
        probe = json.loads(lines[-1])
        if not probe.get("ok") or probe.get("corridor_digest") != expected_digest:
            raise RuntimeError(f"Frozen Corridor identity changed: {probe}")

    async def _archive_private_custody(
        self, environment: BaseEnvironment, *, expected_digest: str
    ) -> dict[str, Any]:
        """Capture direct private evidence before Harbor releases the environment."""

        agent_dir = PurePosixPath(EnvironmentPaths.agent_dir).as_posix()
        result = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} python3 -c "
            + shlex.quote(
                private_custody_program(
                    agent_dir=agent_dir,
                    expected_corridor_digest=expected_digest,
                )
            )),
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        if not lines:
            return {
                "ok": False,
                "source_kind": "direct_runtime_capture_failed",
                "custody_status": "capture_failed",
                "direct_byte_match": False,
                "direct_download": False,
                "recovered": False,
                "error_type": "custody_program_unreadable",
            }
        try:
            report = json.loads(lines[-1])
        except json.JSONDecodeError:
            return {
                "ok": False,
                "source_kind": "direct_runtime_capture_failed",
                "custody_status": "capture_failed",
                "direct_byte_match": False,
                "direct_download": False,
                "recovered": False,
                "error_type": "custody_manifest_unreadable",
            }
        return {
            key: report.get(key)
            for key in (
                "ok",
                "schema_version",
                "private",
                "public_release_allowed",
                "source_kind",
                "custody_status",
                "direct_byte_match",
                "direct_download",
                "recovered",
                "expected_corridor_digest",
                "copied_corridor_digest",
                "tree_digest",
                "captured_at",
                "error_type",
                "already_captured",
                "preserved_existing",
                "existing_bytes_revalidated",
                "builder_recovery_evidence",
            )
            if key in report
        } | {
            "file_count": len(report.get("files", [])),
            "corridor_file_count": len(report.get("corridor_files", [])),
        }

    async def _read_assessment(
        self,
        environment: BaseEnvironment,
        *,
        path: str,
        expected_digest: str,
        acceptance_ledger_status: str,
        expected_acceptance_ids: list[str],
        required_acceptance_ids: list[str],
        source_mapping_status: str,
        definition_closure_status: str,
        construction_readiness_status: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        result = await environment.exec(
            command=f"python3 -c {shlex.quote(remote_json_read_program(path))}",
            user=environment.default_user,
        )
        if result.return_code != 0 or not result.stdout:
            return None, {
                "valid": False,
                "errors": ["ASSESSMENT_UNREADABLE"],
                "reported_outcome": None,
                "outcome": "not_assessed",
                "repair_required": False,
            }
        try:
            value = load_qa_json_text(result.stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, {
                "valid": False,
                "errors": ["ASSESSMENT_JSON"],
                "reported_outcome": None,
                "outcome": "not_assessed",
                "repair_required": False,
            }
        errors = validate_qa_assessment(
            value,
            expected_corridor_digest=expected_digest,
            acceptance_ledger_status=acceptance_ledger_status,
            expected_acceptance_ids=expected_acceptance_ids,
            required_acceptance_ids=required_acceptance_ids,
            source_mapping_status=source_mapping_status,
            definition_closure_status=definition_closure_status,
            construction_readiness_status=construction_readiness_status,
        )
        reported_outcome = (
            value.get("outcome") if isinstance(value, dict) else None
        )
        return value, {
            "valid": not errors,
            "errors": errors,
            "reported_outcome": reported_outcome,
            "outcome": reported_outcome if not errors else "not_assessed",
            "repair_required": not errors and reported_outcome == "fail",
        }

    @staticmethod
    def _record_phase_outcome(
        metadata: dict[str, Any],
        outcome: dict[str, Any],
        context: AgentContext,
    ) -> None:
        metadata["phase_runs"].append(outcome)
        metadata["phase_events"].append(
            f"{outcome['phase']}_{outcome['status']}"
        )
        context.metadata = metadata
        if not outcome.get("quiescent"):
            raise RuntimeError(
                "Phase process quiescence could not be proven; "
                f"refusing to continue after {outcome['phase']}"
            )

    async def _run_task(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not self.model_name:
            raise ValueError("Model name is required")

        builder = self._child_agent("builder")
        worker = self._child_agent("worker")
        qa = self._child_agent("qa")
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        task_timeout_seconds = _task_timeout_seconds(instruction)
        task_deadline = started_at + task_timeout_seconds
        execution_deadline = task_deadline - FINALIZATION_RESERVE_SECONDS
        method_text = self._method_source.decode("utf-8")
        metadata: dict[str, Any] = {
            "schema_version": "charting-loop/full-method-run/v3",
            "method": "task-conditioned-corridor",
            "method_version_id": METHOD_VERSION_ID,
            "method_source_commit": METHOD_SOURCE_COMMIT,
            "method_content_sha256": METHOD_CONTENT_SHA256,
            "method_scope_sha256": METHOD_SCOPE_SHA256,
            "method_prompt_injection": {
                "roles": ["worker", "qa"],
                "mode": "exact_frozen_bytes",
                "version": METHOD_VERSION_ID,
                "digest": METHOD_CONTENT_SHA256,
            },
            "method_study_eligible": True,
            "reportable_study": True,
            "roles": ["builder", "worker", "qa"],
            "phase_events": [],
            "phase_runs": [],
            "deadline_policy": "single_task_deadline",
            "task_timeout_seconds": task_timeout_seconds,
            "finalization_reserve_seconds": FINALIZATION_RESERVE_SECONDS,
            "phase_time_allocations": None,
            "corridor_sdk": dict(getattr(self, "_sdk_identity", {})),
            "submission_root": SUBMISSION_ROOT,
            "submission_snapshots": [],
            "position_timeline_path": POSITION_PATH,
            "position_events": [],
            "position_timeline_errors": [],
            "runtime_guide_projections": [],
            "qa_is_advisory": True,
            "last_worker_snapshot_owns_fallback": True,
            "grading_owned_by_harbor": True,
        }
        context.metadata = metadata

        _, builder_run = await self._run_new_role(
            "builder",
            builder,
            builder_prompt(instruction),
            environment,
            deadline=execution_deadline,
        )
        self._record_phase_outcome(metadata, builder_run, context)
        await self._record_position_event(
            metadata,
            environment,
            actor="runner",
            event_type="builder_completed",
            status=builder_run["status"],
            details={"quiescent": bool(builder_run.get("quiescent"))},
        )

        freeze = await self._freeze_corridor(environment)
        digest = str(freeze["corridor_digest"])
        metadata["corridor_digest"] = digest
        builder_metrics = dict(builder_run.get("role_metrics", {}))
        freeze_elapsed_seconds = loop.time() - started_at
        builder_metrics["frozen_corridor_digest"] = digest
        metadata["builder_corridor_status"] = freeze.get("builder_corridor_status")
        metadata["method_capsule_status"] = freeze.get("method_capsule_status")
        metadata["method_capsule_errors"] = freeze.get(
            "method_capsule_errors", []
        )
        metadata["method_capsule_digest_matches_stored"] = bool(
            freeze.get("method_capsule_digest_matches_stored")
        )
        acceptance_ledger_status = str(
            freeze.get("acceptance_ledger_status", "missing")
        )
        expected_acceptance_ids = [
            str(item) for item in freeze.get("acceptance_ids", [])
        ]
        required_acceptance_ids = [
            str(item) for item in freeze.get("required_acceptance_ids", [])
        ]
        metadata["acceptance_ledger_status"] = acceptance_ledger_status
        metadata["acceptance_ids"] = expected_acceptance_ids
        metadata["required_acceptance_ids"] = required_acceptance_ids
        metadata["acceptance_ledger_errors"] = freeze.get(
            "acceptance_ledger_errors", []
        )
        source_mapping_status = str(
            freeze.get("source_mapping_status", "unknown")
        )
        definition_closure_status = str(
            freeze.get("definition_closure_status", "unknown")
        )
        metadata["source_mapping_status"] = source_mapping_status
        metadata["definition_closure_status"] = definition_closure_status
        metadata["unmapped_count"] = freeze.get("unmapped_count", 0)
        metadata["ambiguous_count"] = freeze.get("ambiguous_count", 0)
        metadata["ambiguous_acceptance_ids"] = freeze.get(
            "ambiguous_acceptance_ids", []
        )
        construction_readiness_status = str(
            freeze.get("construction_readiness_status", "unknown")
        )
        metadata["construction_readiness_status"] = construction_readiness_status
        metadata["coupled_acceptance_ids"] = freeze.get(
            "coupled_acceptance_ids", []
        )
        metadata["unresolved_constraints"] = freeze.get(
            "unresolved_constraints", []
        )
        metadata["phase_events"].append("corridor_frozen")
        await self._record_position_event(
            metadata,
            environment,
            actor="runner",
            event_type="corridor_frozen",
            status=acceptance_ledger_status,
            details={"corridor_digest": digest},
        )
        worker_guide = await self._runtime_guide(environment)
        metadata["runtime_guide_projections"].append(
            {"phase": "worker", **worker_guide}
        )
        builder_metrics.update(
            _builder_freeze_metrics(
                freeze,
                elapsed_seconds=freeze_elapsed_seconds,
                runtime_guide=worker_guide,
            )
        )
        metadata["builder_construction_metrics"] = builder_metrics

        await self._verify_freeze(environment, expected_digest=digest)
        worker_candidate_ref = "worker-candidate:" + hashlib.sha256(
            f"{digest}:{worker_guide.get('position_ref')}".encode("utf-8")
        ).hexdigest()
        if _remaining_seconds(execution_deadline) > 0:
            await self._prepare_worker_fact_path(environment)
            try:
                _, worker_run = await self._run_new_role(
                    "worker",
                    worker,
                    worker_prompt(
                        instruction,
                        digest,
                        construction_readiness_status=construction_readiness_status,
                        work_backlog_status=str(worker_guide["status"]),
                        current_row_id=worker_guide.get("current_row_id"),
                        position_ref=worker_guide.get("position_ref"),
                        direction_digest=worker_guide.get("direction_digest"),
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                        fact_candidate_ref=worker_candidate_ref,
                    ),
                    environment,
                    deadline=execution_deadline,
                )
            finally:
                await self._seal_worker_fact_path(environment)
            self._record_phase_outcome(metadata, worker_run, context)
            metadata["worker_revision_progress"] = await self._worker_revision_progress(
                environment
            )
            worker_fact_admission = await self._admit_fact_file(
                environment,
                path=WORKER_FACTS_PATH,
                role="worker",
                candidate_ref=worker_candidate_ref,
                corridor_digest=digest,
                guide=worker_guide,
            )
            metadata["worker_fact_admission"] = worker_fact_admission
            await self._record_position_event(
                metadata,
                environment,
                actor="runner",
                event_type="worker_completed",
                status=worker_run["status"],
                details={"quiescent": bool(worker_run.get("quiescent"))},
            )
            if worker_fact_admission.get("admitted", 0) > 0:
                worker_guide = await self._runtime_guide(environment)
                metadata["runtime_guide_projections"].append(
                    {"phase": "post_worker_fact_admission", **worker_guide}
                )
        else:
            metadata["phase_events"].append("worker_skipped_task_deadline")
        qa_guide = await self._runtime_guide(environment)
        metadata["runtime_guide_projections"].append({"phase": "qa", **qa_guide})
        snapshots = metadata.get("worker_revision_progress", {}).get("snapshots", [])
        qa_candidate_ref = (
            str(snapshots[-1].get("snapshot_id"))
            if isinstance(snapshots, list) and snapshots and isinstance(snapshots[-1], dict)
            else None
        )

        decision: dict[str, Any] = {
            "valid": False,
            "errors": ["QA_SKIPPED_TASK_DEADLINE"],
            "reported_outcome": None,
            "outcome": "not_assessed",
            "repair_required": False,
        }
        if _remaining_seconds(execution_deadline) > 0:
            await self._verify_freeze(environment, expected_digest=digest)
            await self._open_qa_directory(environment)
            try:
                _, qa_run = await self._run_new_role(
                    "qa",
                    qa,
                    qa_prompt(
                        instruction,
                        digest,
                        acceptance_ledger_status=acceptance_ledger_status,
                        expected_acceptance_ids=expected_acceptance_ids,
                        source_mapping_status=source_mapping_status,
                        definition_closure_status=definition_closure_status,
                        construction_readiness_status=construction_readiness_status,
                        work_backlog_status=str(qa_guide["status"]),
                        current_row_id=qa_guide.get("current_row_id"),
                        position_ref=qa_guide.get("position_ref"),
                        direction_digest=qa_guide.get("direction_digest"),
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                        fact_candidate_ref=qa_candidate_ref,
                    ),
                    environment,
                    deadline=execution_deadline,
                )
                qa_presubmit = await self._validate_qa_presubmit(
                    environment, path=QA_PATH
                )
                metadata.setdefault("qa_presubmit_validations", []).append(
                    {"phase": "qa", **qa_presubmit}
                )
                qa_snapshot = await self._freeze_submission_paths(
                    environment, role="qa", paths=[QA_PATH]
                )
                metadata["submission_snapshots"].append(qa_snapshot)
            finally:
                await self._seal_qa_directory(environment)
            self._record_phase_outcome(metadata, qa_run, context)
            assessment, decision = await self._read_assessment(
                environment,
                path=QA_PATH,
                expected_digest=digest,
                acceptance_ledger_status=acceptance_ledger_status,
                expected_acceptance_ids=expected_acceptance_ids,
                required_acceptance_ids=required_acceptance_ids,
                source_mapping_status=source_mapping_status,
                definition_closure_status=definition_closure_status,
                construction_readiness_status=construction_readiness_status,
            )
            qa_fact_admission = await self._admit_qa_witnesses(
                environment,
                assessment=assessment,
                decision=decision,
                candidate_ref=qa_candidate_ref,
                corridor_digest=digest,
                guide=qa_guide,
            )
            metadata["qa_fact_admission"] = qa_fact_admission
            if decision.get("repair_required") and qa_fact_admission.get("admitted", 0) < 1:
                decision["repair_required"] = False
                decision.setdefault("errors", []).append(
                    "QA_FAILURE_WITNESS_NOT_ADMITTED_AS_FACT"
                )
            await self._record_position_event(
                metadata,
                environment,
                actor="runner",
                event_type="qa_completed",
                status=qa_run["status"],
                details={"quiescent": bool(qa_run.get("quiescent"))},
            )
            if qa_fact_admission.get("admitted", 0) > 0:
                qa_guide = await self._runtime_guide(environment)
                metadata["runtime_guide_projections"].append(
                    {"phase": "post_qa_fact_admission", **qa_guide}
                )
        else:
            metadata["phase_events"].append("qa_skipped_task_deadline")
        metadata["qa_decision"] = decision

        if decision["repair_required"] and _remaining_seconds(execution_deadline) > 0:
            await self._verify_freeze(environment, expected_digest=digest)
            _, repair_run = await self._resume_role(
                "worker",
                worker,
                repair_prompt(
                    instruction,
                    digest,
                    remaining_seconds=_remaining_seconds(execution_deadline),
                ),
                environment,
                phase="repair",
                deadline=execution_deadline,
            )
            self._record_phase_outcome(metadata, repair_run, context)
            await self._record_position_event(
                metadata,
                environment,
                actor="runner",
                event_type="repair_completed",
                status=repair_run["status"],
                details={"quiescent": bool(repair_run.get("quiescent"))},
            )
            metadata["worker_revision_progress"] = await self._worker_revision_progress(
                environment
            )

            if _remaining_seconds(execution_deadline) > 0:
                await self._verify_freeze(environment, expected_digest=digest)
                await self._open_qa_directory(environment)
                try:
                    _, closure_run = await self._resume_role(
                        "qa",
                        qa,
                        closure_prompt(
                            instruction,
                            digest,
                            acceptance_ledger_status=acceptance_ledger_status,
                            expected_acceptance_ids=expected_acceptance_ids,
                            source_mapping_status=source_mapping_status,
                            definition_closure_status=definition_closure_status,
                            construction_readiness_status=(
                                construction_readiness_status
                            ),
                            remaining_seconds=_remaining_seconds(
                                execution_deadline
                            ),
                        ),
                        environment,
                        phase="closure",
                        deadline=execution_deadline,
                    )
                    closure_presubmit = await self._validate_qa_presubmit(
                        environment, path=CLOSURE_PATH
                    )
                    metadata.setdefault("qa_presubmit_validations", []).append(
                        {"phase": "closure", **closure_presubmit}
                    )
                    closure_snapshot = await self._freeze_submission_paths(
                        environment, role="qa", paths=[CLOSURE_PATH]
                    )
                    metadata["submission_snapshots"].append(closure_snapshot)
                finally:
                    await self._seal_qa_directory(environment)
                self._record_phase_outcome(metadata, closure_run, context)
                await self._record_position_event(
                    metadata,
                    environment,
                    actor="runner",
                    event_type="closure_completed",
                    status=closure_run["status"],
                    details={"quiescent": bool(closure_run.get("quiescent"))},
                )
                _, closure = await self._read_assessment(
                    environment,
                    path=CLOSURE_PATH,
                    expected_digest=digest,
                    acceptance_ledger_status=acceptance_ledger_status,
                    expected_acceptance_ids=expected_acceptance_ids,
                    required_acceptance_ids=required_acceptance_ids,
                    source_mapping_status=source_mapping_status,
                    definition_closure_status=definition_closure_status,
                    construction_readiness_status=construction_readiness_status,
                )
                metadata["qa_closure"] = closure
            else:
                metadata["phase_events"].append("closure_skipped_task_deadline")
        elif decision["repair_required"]:
            metadata["phase_events"].append("repair_skipped_task_deadline")

        await self._verify_freeze(environment, expected_digest=digest)
        submission_fallback = await self._restore_latest_worker_submission(environment)
        metadata["submission_fallback"] = submission_fallback
        metadata["worker_revision_progress"] = await self._worker_revision_progress(
            environment
        )
        metadata["task_deadline_reached"] = loop.time() >= execution_deadline
        metadata["elapsed_seconds"] = round(loop.time() - started_at, 3)
        metadata["remaining_finalization_seconds"] = max(
            0.0, round(task_deadline - loop.time(), 3)
        )
        metadata["phase_events"].append("agent_returned_for_grading")
        context.metadata = metadata

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Run the task and always attempt private custody before teardown."""

        try:
            await self._run_task(instruction, environment, context)
        finally:
            metadata = dict(context.metadata or {})
            try:
                custody = await self._archive_private_custody(
                    environment,
                    expected_digest=str(metadata.get("corridor_digest", "")),
                )
            except Exception as exc:
                custody = {
                    "ok": False,
                    "source_kind": "direct_runtime_capture_failed",
                    "custody_status": "capture_failed",
                    "direct_byte_match": False,
                    "direct_download": False,
                    "recovered": False,
                    "error_type": type(exc).__name__,
                    "builder_recovery_evidence": "agent/phases/builder",
                }
            metadata["private_benchmark_custody"] = custody
            metadata.setdefault("phase_events", []).append(
                f"private_custody_{custody['custody_status']}"
            )
            context.metadata = metadata

    def _phase_trajectory(self, role: str) -> Trajectory | None:
        phase_dir = self.logs_dir / "phases" / role
        if not phase_dir.is_dir():
            return None
        parser = self._child_agent(role)
        phase_context = AgentContext()
        parser.populate_context_post_run(phase_context)
        trajectory_path = phase_dir / "trajectory.json"
        if not trajectory_path.is_file():
            return None
        trajectory = Trajectory.model_validate_json(
            trajectory_path.read_text(encoding="utf-8")
        )
        run_id = self.session_id or "trial"
        trajectory.trajectory_id = f"{run_id}:{role}"
        extra = dict(trajectory.agent.extra or {})
        extra["charting_loop_role"] = role
        trajectory.agent.extra = extra
        return trajectory

    @staticmethod
    def _sum_complete_metrics(
        trajectories: list[Trajectory],
        field: str,
    ) -> int | float | None:
        values: list[int | float] = []
        for trajectory in trajectories:
            metrics = trajectory.final_metrics
            value = getattr(metrics, field) if metrics is not None else None
            if value is None:
                return None
            values.append(value)
        return sum(values)

    def populate_context_post_run(self, context: AgentContext) -> None:
        """Write one ATIF-v1.7 root with the three complete role histories."""

        trajectories = [
            trajectory
            for role in self.ROLE_SEQUENCE
            if (trajectory := self._phase_trajectory(role)) is not None
        ]
        if not trajectories:
            return

        prompt_tokens = self._sum_complete_metrics(
            trajectories, "total_prompt_tokens"
        )
        completion_tokens = self._sum_complete_metrics(
            trajectories, "total_completion_tokens"
        )
        cached_tokens = self._sum_complete_metrics(
            trajectories, "total_cached_tokens"
        )
        cost_usd = self._sum_complete_metrics(trajectories, "total_cost_usd")
        total_steps = 1 + sum(len(trajectory.steps) for trajectory in trajectories)
        trajectory_ids = [
            trajectory.trajectory_id for trajectory in trajectories
        ]

        root = Trajectory(
            schema_version="ATIF-v1.7",
            session_id=self.session_id,
            trajectory_id=f"{self.session_id or 'trial'}:orchestrator",
            agent=Agent(
                name=self.name(),
                version=self.version(),
                model_name=self.model_name,
                extra={
                    "method": self.ORCHESTRATION_METHOD,
                    "role_count": len(trajectories),
                },
            ),
            steps=[
                Step(
                    step_id=1,
                    source="agent",
                    message=self.ORCHESTRATION_MESSAGE,
                    llm_call_count=0,
                    extra={"subagent_trajectory_ids": trajectory_ids},
                )
            ],
            notes=(
                "final_metrics.total_steps counts the deterministic root step plus "
                "all embedded role steps. Resumed Worker/QA trajectories contain "
                "their complete initial and continuation histories, so usage is not "
                "double-counted."
            ),
            final_metrics=FinalMetrics(
                total_prompt_tokens=prompt_tokens,
                total_completion_tokens=completion_tokens,
                total_cached_tokens=cached_tokens,
                total_cost_usd=cost_usd,
                total_steps=total_steps,
                extra={"embedded_role_count": len(trajectories)},
            ),
            extra={"orchestration": context.metadata or {}},
            subagent_trajectories=trajectories,
        )

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "trajectory.json").write_text(
            format_trajectory_json(root.to_json_dict()) + "\n",
            encoding="utf-8",
        )
        if prompt_tokens is not None:
            context.n_input_tokens = int(prompt_tokens)
        if completion_tokens is not None:
            context.n_output_tokens = int(completion_tokens)
        if cached_tokens is not None:
            context.n_cache_tokens = int(cached_tokens)
        if cost_usd is not None:
            context.cost_usd = float(cost_usd)


class _ChartingLoopGraphKernelAgent(ChartingLoopFullMethodAgent):
    """Task-clock Worker authoring with a shared task-neutral Graph Kernel."""

    ARM = ""
    ROLE_SEQUENCE = ("worker", "qa")
    ORCHESTRATION_MESSAGE = (
        "Deterministic orchestration: frozen Study profile plus shared Graph "
        "Kernel -> Worker compile -> compile QA/recompile -> RuleClosure -> "
        "Direction/test contract -> pre-action QA -> same-Worker implementation "
        "-> frozen-result QA/repair -> official scoring."
    )
    ORCHESTRATION_METHOD = "method-guided-graph-kernel"

    def version(self) -> str:
        return GRAPH_AGENT_VERSION

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        user = shlex.quote(str(environment.default_user or "root"))
        method_cleanup = (
            f"rm -f {shlex.quote(METHOD_PATH)} && " if self.ARM == "neutral" else ""
        )
        initialized = await self.exec_as_root(
            environment,
            command=(
                f"rm -rf {shlex.quote(str(PurePosixPath(GRAPH_PATH).parent))} && "
                f"install -d -m 0700 -o {user} "
                f"{shlex.quote(str(PurePosixPath(GRAPH_PATH).parent))} "
                f"{shlex.quote(EXECUTION_TEST_ROOT)} && "
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -m corridor_kit graph init {shlex.quote(GRAPH_PATH)} && "
                f"chown {user} {shlex.quote(GRAPH_PATH)} && "
                f"chmod 0600 {shlex.quote(GRAPH_PATH)} && "
                + method_cleanup
                + "true"
            ),
        )
        if initialized.return_code != 0:
            raise RuntimeError(
                "Graph Kernel initialization failed: "
                + (initialized.stderr or initialized.stdout or "no output")[-2000:]
            )

    async def _seal_graph_corridor(
        self, environment: BaseEnvironment
    ) -> dict[str, Any]:
        validation = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -m corridor_kit graph validate {shlex.quote(GRAPH_PATH)}"
            ),
        )
        validation_lines = [
            line for line in (validation.stdout or "").splitlines() if line.strip()
        ]
        try:
            graph_report = json.loads("\n".join(validation_lines))
        except (TypeError, json.JSONDecodeError):
            graph_report = {
                "ok": False,
                "structurally_valid": False,
                "error": (validation.stderr or validation.stdout or "unreadable")[-2000:],
            }
        doctor_report = await self._graph_doctor_report(
            environment, graph_path=GRAPH_PATH
        )
        raw_identity = await self.exec_as_root(
            environment,
            command=(
                "python3 -c "
                + shlex.quote(
                    "import hashlib,json; from pathlib import Path; "
                    f"p=Path({GRAPH_PATH!r}); b=p.read_bytes(); "
                    "print(json.dumps({'graph_bytes_digest':'sha256:'+hashlib.sha256(b).hexdigest(),"
                    "'graph_bytes':len(b)},sort_keys=True))"
                )
            ),
        )
        raw_lines = [line for line in (raw_identity.stdout or "").splitlines() if line.strip()]
        raw_report = json.loads(raw_lines[-1]) if raw_lines else {}
        await self.exec_as_root(
            environment,
            command=(
                f"chown -R 0:0 {shlex.quote(CORRIDOR_PATH)} && "
                f"find {shlex.quote(CORRIDOR_PATH)} -type d -exec chmod 0555 {{}} + && "
                f"find {shlex.quote(CORRIDOR_PATH)} -type f -exec chmod 0444 {{}} +"
            ),
        )
        manifest = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -m corridor_kit manifest {shlex.quote(CORRIDOR_PATH)}"
            ),
        )
        manifest_lines = [line for line in (manifest.stdout or "").splitlines() if line.strip()]
        if manifest.return_code != 0 or not manifest_lines:
            raise RuntimeError("Graph Corridor manifest failed")
        tree = json.loads("\n".join(manifest_lines))
        freeze = {
            "schema_version": "charting-loop/frozen-graph-kernel-run/v1",
            "corridor_digest": tree["tree_digest"],
            "corridor_files": tree["files"],
            "graph_bytes_digest": raw_report.get("graph_bytes_digest"),
            "graph_bytes": raw_report.get("graph_bytes"),
            "graph_validation": graph_report,
            "graph_doctor": doctor_report,
            "graph_structurally_valid": validation.return_code == 0
            and graph_report.get("ok") is True,
            "study_profile_path": STUDY_PROFILE_PATH,
            "advisory_only": True,
            "authorizes_mutation": False,
            "blocking_gate": False,
        }
        await self._write_root_json(environment, path=FREEZE_PATH, value=freeze)
        return freeze

    async def _graph_doctor_report(
        self, environment: BaseEnvironment, *, graph_path: str
    ) -> dict[str, Any]:
        """Run the read-only non-authoritative Doctor and retain its exact report."""

        result = await self.exec_as_root(
            environment,
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -m corridor_kit graph doctor {shlex.quote(graph_path)}"
            ),
        )
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        try:
            report = json.loads("\n".join(lines))
        except (TypeError, json.JSONDecodeError):
            report = {
                "schema_version": "charting-loop/graph-doctor-report/v1",
                "classification": "structurally_invalid",
                "structurally_valid": False,
                "errors": [(result.stderr or result.stdout or "unreadable")[-2000:]],
                "authorizes_mutation": False,
                "blocking_gate": False,
                "pass_assessed": False,
            }
        return report

    async def _freeze_graph_revision(
        self,
        environment: BaseEnvironment,
        *,
        iteration: int,
        worker_snapshot_ref: str,
        namespace: str = "result",
        include_execution_test_fixtures: bool = False,
    ) -> dict[str, Any]:
        """Copy one exact graph revision for QA without freezing the live graph."""

        revision_root = (
            PurePosixPath(RUNTIME_ROOT)
            / "graph-freezes"
            / f"{namespace}-{iteration:04d}"
        )
        frozen_graph_path = (revision_root / "GRAPH.jsonl").as_posix()
        manifest_path = (revision_root / "GRAPH-FREEZE.json").as_posix()
        copy_program = (
            "from pathlib import Path; "
            f"source=Path({GRAPH_PATH!r}); root=Path({revision_root.as_posix()!r}); "
            f"target=Path({frozen_graph_path!r}); "
            "assert source.is_file() and not source.is_symlink(); "
            "assert not root.exists(); root.mkdir(parents=True,mode=0o700); "
            "target.write_bytes(source.read_bytes()); target.chmod(0o444)"
        )
        prefreeze_doctor = await self._graph_doctor_report(
            environment, graph_path=GRAPH_PATH
        )
        copied = await self.exec_as_root(
            environment,
            command=f"python3 -c {shlex.quote(copy_program)}",
        )
        if copied.return_code != 0:
            return {
                "ok": False,
                "iteration": iteration,
                "worker_snapshot_ref": worker_snapshot_ref,
                "status": "graph_revision_copy_failed",
                "error": (copied.stderr or copied.stdout or "no output")[-2000:],
            }
        fixture_manifest_path: str | None = None
        if include_execution_test_fixtures:
            selected_contract_record_id = prefreeze_doctor.get(
                "execution_test_contract", {}
            ).get("contract_record_id")
            if not isinstance(selected_contract_record_id, str):
                return {
                    "ok": False,
                    "iteration": iteration,
                    "worker_snapshot_ref": worker_snapshot_ref,
                    "status": "execution_test_contract_identity_missing",
                }
            fixture_manifest_path = (
                revision_root / "EXECUTION-TEST-FIXTURES.json"
            ).as_posix()
            fixture_program = """
import hashlib
import json
from pathlib import Path

graph = Path(__GRAPH_PATH__)
root = Path(__FREEZE_ROOT__)
allowed_root = Path(__ALLOWED_ROOT__).resolve(strict=True)
records = [json.loads(line) for line in graph.read_text(encoding="utf-8").splitlines()]
contracts = [record for record in records if record.get("record_type") == "execution_test_contract"]
matching = [record for record in contracts if record.get("record_id") == __CONTRACT_RECORD_ID__]
if len(matching) != 1:
    raise RuntimeError("selected execution_test_contract is missing or duplicated")
contract = matching[0]
fixtures_by_identity = {}
for case in contract["body"].get("probe_cases", []):
    for item in case.get("fixture_artifacts", []):
        source = Path(item["path"])
        if not source.is_absolute() or source.is_symlink() or not source.is_file():
            raise RuntimeError(f"invalid execution test fixture: {source}")
        resolved = source.resolve(strict=True)
        try:
            resolved.relative_to(allowed_root)
        except ValueError as exc:
            raise RuntimeError(f"execution test fixture is outside the declared root: {source}") from exc
        data = resolved.read_bytes()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if digest != item["digest"]:
            raise RuntimeError(f"execution test fixture digest mismatch: {source}")
        frozen_dir = root / "fixtures"
        frozen_dir.mkdir(mode=0o700, exist_ok=True)
        frozen = frozen_dir / (hashlib.sha256(str(resolved).encode()).hexdigest() + resolved.suffix)
        frozen.write_bytes(data)
        frozen.chmod(0o444)
        identity = (str(resolved), digest)
        fixtures_by_identity[identity] = {"source_path": str(resolved), "frozen_path": str(frozen), "digest": digest, "bytes": len(data)}
manifest = {
    "schema_version": "charting-loop/execution-test-fixture-freeze/v1",
    "contract_record_id": contract["record_id"],
    "contract_digest": contract["body"]["contract_digest"],
    "fixtures": sorted(fixtures_by_identity.values(), key=lambda item: (item["source_path"], item["digest"])),
}
Path(__MANIFEST_PATH__).write_text(json.dumps(manifest, sort_keys=True) + "\\n", encoding="utf-8")
Path(__MANIFEST_PATH__).chmod(0o444)
""".replace("__GRAPH_PATH__", repr(frozen_graph_path)).replace(
                "__FREEZE_ROOT__", repr(revision_root.as_posix())
            ).replace("__ALLOWED_ROOT__", repr(EXECUTION_TEST_ROOT)).replace(
                "__MANIFEST_PATH__", repr(fixture_manifest_path)
            ).replace(
                "__CONTRACT_RECORD_ID__", repr(selected_contract_record_id)
            )
            fixtures_frozen = await self.exec_as_root(
                environment,
                command=f"python3 -c {shlex.quote(fixture_program)}",
            )
            if fixtures_frozen.return_code != 0:
                return {
                    "ok": False,
                    "iteration": iteration,
                    "worker_snapshot_ref": worker_snapshot_ref,
                    "status": "execution_test_fixture_freeze_failed",
                    "error": (
                        fixtures_frozen.stderr
                        or fixtures_frozen.stdout
                        or "no output"
                    )[-4000:],
                }
        qa_intake_doctor = await self._graph_doctor_report(
            environment, graph_path=frozen_graph_path
        )
        graph_digest = qa_intake_doctor.get("graph_digest")
        selected_frozen_contract_id = qa_intake_doctor.get(
            "execution_test_contract", {}
        ).get("contract_record_id")
        exact_bytes_match = (
            prefreeze_doctor.get("graph_bytes_digest")
            == qa_intake_doctor.get("graph_bytes_digest")
            and isinstance(prefreeze_doctor.get("graph_bytes_digest"), str)
        )
        if (
            qa_intake_doctor.get("classification") == "structurally_invalid"
            or qa_intake_doctor.get("structurally_valid") is not True
            or not isinstance(graph_digest, str)
            or not exact_bytes_match
            or (
                include_execution_test_fixtures
                and selected_frozen_contract_id != selected_contract_record_id
            )
        ):
            invalid_identity = {
                "schema_version": "charting-loop/frozen-graph-revision/v1",
                "iteration": iteration,
                "worker_snapshot_ref": worker_snapshot_ref,
                "graph_path": frozen_graph_path,
                "status": "graph_revision_invalid",
                "prefreeze_doctor": prefreeze_doctor,
                "qa_intake_doctor": qa_intake_doctor,
                "exact_graph_bytes_match": exact_bytes_match,
            }
            await self._write_root_json(
                environment,
                path=manifest_path,
                value=invalid_identity,
            )
            await self.exec_as_root(
                environment,
                command=(
                    f"chmod 0444 {shlex.quote(manifest_path)} && "
                    f"chmod 0555 {shlex.quote(revision_root.as_posix())}"
                ),
            )
            return {
                "ok": False,
                **invalid_identity,
                "manifest_path": manifest_path,
            }
        identity = {
            "schema_version": "charting-loop/frozen-graph-revision/v1",
            "iteration": iteration,
            "worker_snapshot_ref": worker_snapshot_ref,
            "graph_path": frozen_graph_path,
            "graph_digest": graph_digest,
            "head_record_id": qa_intake_doctor.get("head_record_id"),
            "record_count": qa_intake_doctor.get("record_count"),
            "doctor_schema_version": qa_intake_doctor.get("schema_version"),
            "doctor_code_digest": qa_intake_doctor.get("doctor_code_digest"),
            "doctor_report_digest": qa_intake_doctor.get("report_digest"),
            "doctor_classification": qa_intake_doctor.get("classification"),
            "graph_bytes_digest": qa_intake_doctor.get("graph_bytes_digest"),
            "position_ref": qa_intake_doctor.get("latest_position_ref"),
            "direction_digest": qa_intake_doctor.get("direction_digest"),
            "acceptance_root": qa_intake_doctor.get("acceptance_root"),
            "execution_test_contract_record_id": qa_intake_doctor.get(
                "execution_test_contract", {}
            ).get("contract_record_id"),
            "execution_test_contract_digest": qa_intake_doctor.get(
                "execution_test_contract", {}
            ).get("contract_digest"),
            "execution_test_fixture_manifest_path": fixture_manifest_path,
            "exact_graph_bytes_match": exact_bytes_match,
        }
        await self._write_root_json(
            environment,
            path=manifest_path,
            value=identity,
        )
        await self.exec_as_root(
            environment,
            command=(
                f"chmod 0444 {shlex.quote(manifest_path)} && "
                f"chmod 0555 {shlex.quote(revision_root.as_posix())}"
            ),
        )
        return {
            "ok": True,
            **identity,
            "manifest_path": manifest_path,
            "prefreeze_doctor": prefreeze_doctor,
            "qa_intake_doctor": qa_intake_doctor,
        }

    @staticmethod
    def _rule_compile_paths(iteration: int) -> tuple[str, str]:
        if iteration == 1:
            return TYPED_RULE_IR_PATH, TYPED_RULE_REPORT_PATH
        root = PurePosixPath(CORRIDOR_PATH) / "compile-revisions"
        return (
            (root / f"typed-rule-ir-{iteration:04d}.json").as_posix(),
            (root / f"typed-rule-report-{iteration:04d}.json").as_posix(),
        )

    @staticmethod
    def _rule_compile_candidate_metadata(
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Project transient candidate state into bounded immutable metadata."""

        scalar_fields = (
            "ok",
            "iteration",
            "status",
            "graph_path",
            "graph_digest",
            "head_record_id",
            "record_count",
            "candidate_report_record_id",
            "candidate_report_digest",
            "candidate_report_schema",
            "failed_candidate_id",
            "failure_classification",
            "failure_type",
            "failure_size",
            "failure_sha256",
            "failure_descriptor_path",
            "failure_descriptor_size",
            "failure_descriptor_sha256",
            "typed_rule_ir_path",
            "typed_rule_ir_size",
            "typed_rule_ir_sha256",
            "typed_rule_report_path",
            "compile_report_size",
            "compile_report_sha256",
            "custody_compressed_size",
            "custody_uncompressed_size",
        )
        projected = {
            field: candidate[field]
            for field in scalar_fields
            if isinstance(candidate.get(field), (bool, int, str))
        }
        for prefix in ("candidate", "doctor"):
            source = candidate.get(prefix)
            if not isinstance(source, dict):
                continue
            for field in (
                "ok",
                "structurally_valid",
                "classification",
                "graph_digest",
                "head_record_id",
                "record_count",
                "candidate_report_record_id",
                "candidate_report_digest",
            ):
                value = source.get(field)
                if isinstance(value, (bool, int, str)):
                    projected[f"{prefix}_{field}"] = value
        error = candidate.get("error")
        if isinstance(error, str):
            error_bytes = error.encode("utf-8")
            projected["error_size"] = len(error_bytes)
            projected["error_sha256"] = (
                "sha256:" + hashlib.sha256(error_bytes).hexdigest()
            )
        return projected

    async def _freeze_rule_compile_candidate(
        self,
        environment: BaseEnvironment,
        *,
        iteration: int,
        ir_path: str,
    ) -> dict[str, Any]:
        """Build and seal one prospective graph from Worker IR without touching live state."""

        candidate_root = (
            PurePosixPath(RUNTIME_ROOT)
            / "compile-candidates"
            / f"candidate-{iteration:04d}"
        )
        graph_path = (candidate_root / "GRAPH.jsonl").as_posix()
        candidate_ir_path = (candidate_root / "TYPED-RULE-IR.json").as_posix()
        candidate_report_path = (candidate_root / "TYPED-RULE-COMPILE.json").as_posix()
        build_program = "\n".join(
            [
                "import json",
                "from pathlib import Path",
                "from corridor_kit import CorridorKitError,canonical_json_bytes,sha256_bytes,sha256_json",
                "from corridor_kit.graph import freeze_rule_candidate,read_rule_candidate_payload",
                f"p=Path({graph_path!r})",
                f"ir=json.loads(Path({ir_path!r}).read_text(encoding='utf-8'))",
                "ir_bytes=canonical_json_bytes(ir)",
                f"Path({candidate_ir_path!r}).write_bytes(ir_bytes)",
                "try:",
                "    r=freeze_rule_candidate(p,typed_rule_ir=ir,include_compile_report=False)",
                "    d=read_rule_candidate_payload(p,candidate_report_record_id=r['candidate_report_record_id'],candidate_report_digest=r['candidate_report_digest'])",
                f"    Path({candidate_ir_path!r}).write_bytes(d['typed_rule_ir_bytes'])",
                f"    Path({candidate_report_path!r}).write_bytes(d['compile_report_bytes'])",
                f"    r.update({{'typed_rule_ir_path':{candidate_ir_path!r},'typed_rule_report_path':{candidate_report_path!r}}})",
                "except CorridorKitError as exc:",
                "    failure_bytes=str(exc).encode('utf-8')",
                f"    identity={{'schema_version':'charting-loop/rule-compile-failure/v1','status':'compile_candidate_semantic_rejected','iteration':{iteration!r},'failure_classification':'semantic_compile_rejected','failure_type':type(exc).__name__,'failure_size':len(failure_bytes),'failure_sha256':sha256_bytes(failure_bytes),'typed_rule_ir_size':len(ir_bytes),'typed_rule_ir_sha256':sha256_bytes(ir_bytes)}}",
                "    failed_candidate_id=sha256_json(identity)",
                "    descriptor={**identity,'failed_candidate_id':failed_candidate_id}",
                "    descriptor_bytes=canonical_json_bytes(descriptor)",
                f"    Path({candidate_report_path!r}).write_bytes(descriptor_bytes)",
                f"    r={{'ok':False,**descriptor,'failure_descriptor_path':{candidate_report_path!r},'failure_descriptor_size':len(descriptor_bytes),'failure_descriptor_sha256':sha256_bytes(descriptor_bytes),'typed_rule_ir_path':{candidate_ir_path!r}}}",
                "print(json.dumps(r,sort_keys=True))",
            ]
        )
        command = (
            f"test -f {shlex.quote(ir_path)} && "
            f"test ! -e {shlex.quote(candidate_root.as_posix())} && "
            f"install -d -m 0700 {shlex.quote(candidate_root.as_posix())} && "
            f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
            f"python3 -m corridor_kit graph init {shlex.quote(graph_path)} && "
            f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
            f"python3 -c {shlex.quote(build_program)}"
        )
        try:
            built = await self.exec_as_root(environment, command=command)
        except Exception as exc:
            failure_bytes = str(exc).encode("utf-8")
            return {
                "ok": False,
                "iteration": iteration,
                "graph_path": graph_path,
                "status": "compile_candidate_execution_failed",
                "failure_type": type(exc).__name__,
                "failure_size": len(failure_bytes),
                "failure_sha256": "sha256:"
                + hashlib.sha256(failure_bytes).hexdigest(),
            }
        lines = [line for line in (built.stdout or "").splitlines() if line.strip()]
        if built.return_code != 0 or not lines:
            failure_bytes = (
                built.stderr or built.stdout or "no output"
            ).encode("utf-8")
            return {
                "ok": False,
                "iteration": iteration,
                "graph_path": graph_path,
                "status": "compile_candidate_build_failed",
                "failure_type": "command_failed",
                "failure_size": len(failure_bytes),
                "failure_sha256": "sha256:"
                + hashlib.sha256(failure_bytes).hexdigest(),
            }
        try:
            candidate = json.loads(lines[-1])
        except json.JSONDecodeError:
            failure_bytes = (built.stdout or "").encode("utf-8")
            return {
                "ok": False,
                "iteration": iteration,
                "graph_path": graph_path,
                "status": "compile_candidate_result_unreadable",
                "failure_type": "result_unreadable",
                "failure_size": len(failure_bytes),
                "failure_sha256": "sha256:"
                + hashlib.sha256(failure_bytes).hexdigest(),
            }
        candidate = {"iteration": iteration, "graph_path": graph_path, **candidate}
        if candidate.get("status") == "compile_candidate_semantic_rejected":
            await self.exec_as_root(
                environment,
                command=(
                    f"find {shlex.quote(candidate_root.as_posix())} -type f -exec chmod 0444 {{}} + && "
                    f"chmod 0555 {shlex.quote(candidate_root.as_posix())}"
                ),
            )
            return candidate
        doctor = await self._graph_doctor_report(environment, graph_path=graph_path)
        if (
            candidate.get("ok") is not True
            or doctor.get("structurally_valid") is not True
            or doctor.get("graph_digest") != candidate.get("graph_digest")
        ):
            return {
                "ok": False,
                "iteration": iteration,
                "graph_path": graph_path,
                "status": "compile_candidate_identity_invalid",
                "candidate": candidate,
                "doctor": doctor,
            }
        await self.exec_as_root(
            environment,
            command=(
                f"find {shlex.quote(candidate_root.as_posix())} -type f -exec chmod 0444 {{}} + && "
                f"chmod 0555 {shlex.quote(candidate_root.as_posix())}"
            ),
        )
        return {
            "ok": True,
            **candidate,
            "doctor": doctor,
        }

    async def _read_rule_compile_audit(
        self,
        environment: BaseEnvironment,
        *,
        path: str,
        study_profile_digest: str,
        candidate: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        result = await environment.exec(
            command=f"python3 -c {shlex.quote(remote_json_read_program(path))}",
            user=environment.default_user,
        )
        if result.return_code != 0 or not result.stdout:
            return None, {
                "valid": False,
                "errors": ["RULE_COMPILE_AUDIT_UNREADABLE"],
                "outcome": "not_assessed",
                "rule_closure_ready": False,
            }
        try:
            value = load_qa_json_text(result.stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, {
                "valid": False,
                "errors": ["RULE_COMPILE_AUDIT_JSON"],
                "outcome": "not_assessed",
                "rule_closure_ready": False,
            }
        if candidate.get("status") == "compile_candidate_semantic_rejected":
            errors = validate_graph_compile_failure_audit(
                value,
                study_profile_digest=study_profile_digest,
                failed_candidate_id=str(candidate["failed_candidate_id"]),
                typed_rule_ir_digest=str(candidate["typed_rule_ir_sha256"]),
                failure_descriptor_digest=str(
                    candidate["failure_descriptor_sha256"]
                ),
            )
        else:
            errors = validate_graph_compile_audit(
                value,
                study_profile_digest=study_profile_digest,
                graph_digest=str(candidate["graph_digest"]),
                candidate_report_record_id=str(
                    candidate["candidate_report_record_id"]
                ),
                candidate_report_digest=str(candidate["candidate_report_digest"]),
            )
        outcome = value.get("outcome") if not errors else "not_assessed"
        return value, {
            "valid": not errors,
            "errors": errors,
            "outcome": outcome,
            "rule_closure_ready": not errors and outcome == "pass",
            "advisory_only": True,
            "blocking_gate": False,
            "authorizes_mutation": False,
        }

    async def _install_rule_closure(
        self,
        environment: BaseEnvironment,
        *,
        candidate: dict[str, Any],
        qa_path: str,
        iteration: int,
    ) -> dict[str, Any]:
        """Retain runner-owned QA evidence; install only a passing RuleClosure."""

        user = shlex.quote(str(environment.default_user or "root"))
        closure_staging = (
            PurePosixPath(RUNTIME_ROOT)
            / "compile-candidates"
            / f"rule-closure-{iteration:04d}.jsonl"
        ).as_posix()
        program = (
            "import json; from pathlib import Path; "
            "from corridor_kit.graph import ratify_rule_candidate; "
            f"a=json.loads(Path({qa_path!r}).read_text(encoding='utf-8')); "
            f"r=ratify_rule_candidate(Path({closure_staging!r}),"
            f"candidate_report_record_id={candidate['candidate_report_record_id']!r},"
            f"candidate_report_digest={candidate['candidate_report_digest']!r},"
            "outcome=a['outcome'],findings=a['findings'],"
            f"ratifier_ref={'runner:compile-audit-' + str(iteration).zfill(4)!r}); "
            "print(json.dumps(r,sort_keys=True))"
        )
        installed = await self.exec_as_root(
            environment,
            command=(
                f"test ! -e {shlex.quote(closure_staging)} && "
                f"install -m 0600 {shlex.quote(str(candidate['graph_path']))} "
                f"{shlex.quote(closure_staging)} && "
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -c {shlex.quote(program)} && "
                f"chmod 0444 {shlex.quote(closure_staging)}"
            ),
        )
        lines = [line for line in (installed.stdout or "").splitlines() if line.strip()]
        if installed.return_code != 0 or not lines:
            return {
                "ok": False,
                "status": "rule_closure_install_failed",
                "error": (installed.stderr or installed.stdout or "no output")[-4000:],
            }
        try:
            result = json.loads(lines[-1])
        except json.JSONDecodeError:
            return {
                "ok": False,
                "status": "rule_closure_result_unreadable",
                "error": (installed.stdout or "")[-4000:],
            }
        result["assessed_graph_path"] = closure_staging
        if result.get("rule_closure_established") is not True:
            return result
        live_install = await self.exec_as_root(
            environment,
            command=(
                f"install -m 0600 {shlex.quote(closure_staging)} "
                f"{shlex.quote(GRAPH_PATH)} && "
                f"chown {user} {shlex.quote(GRAPH_PATH)}"
            ),
        )
        if live_install.return_code != 0:
            return {
                "ok": False,
                "status": "rule_closure_live_install_failed",
                "assessed_graph_path": closure_staging,
                "error": (live_install.stderr or live_install.stdout or "no output")[-4000:],
            }
        return result

    async def _read_execution_test_audit(
        self,
        environment: BaseEnvironment,
        *,
        path: str,
        study_profile_digest: str,
        candidate: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        result = await environment.exec(
            command=f"python3 -c {shlex.quote(remote_json_read_program(path))}",
            user=environment.default_user,
        )
        if result.return_code != 0 or not result.stdout:
            return None, {
                "valid": False,
                "errors": ["EXECUTION_TEST_AUDIT_UNREADABLE"],
                "outcome": "not_assessed",
                "revision_requested": False,
            }
        try:
            value = load_qa_json_text(result.stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, {
                "valid": False,
                "errors": ["EXECUTION_TEST_AUDIT_JSON"],
                "outcome": "not_assessed",
                "revision_requested": False,
            }
        errors = validate_execution_test_audit(
            value,
            study_profile_digest=study_profile_digest,
            graph_digest=str(candidate["graph_digest"]),
            contract_record_id=str(candidate["execution_test_contract_record_id"]),
            contract_digest=str(candidate["execution_test_contract_digest"]),
        )
        outcome = value.get("outcome") if not errors else "not_assessed"
        return value, {
            "valid": not errors,
            "errors": errors,
            "outcome": outcome,
            "revision_requested": not errors and outcome == "fail" and bool(
                value.get("findings")
            ),
            "advisory_only": True,
            "blocking_gate": False,
            "authorizes_mutation": False,
        }

    async def _append_execution_test_qa_assessment(
        self,
        environment: BaseEnvironment,
        *,
        qa_path: str,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Runner appends exact QA bytes without granting mutation authority."""

        program = (
            "import json; from pathlib import Path; "
            "from corridor_kit.core import sha256_json; "
            "from corridor_kit.graph import append_graph_record, EXECUTION_TEST_QA_ASSESSMENT_SCHEMA; "
            f"a=json.loads(Path({qa_path!r}).read_text(encoding='utf-8')); "
            "n={'schema_version':EXECUTION_TEST_QA_ASSESSMENT_SCHEMA,"
            f"'contract_record_id':{candidate['execution_test_contract_record_id']!r},"
            f"'contract_digest':{candidate['execution_test_contract_digest']!r},"
            "'outcome':a['outcome'],'findings':a['findings']}; "
            "b={**n,'assessment_digest':sha256_json(n)}; "
            f"r=append_graph_record(Path({GRAPH_PATH!r}),record_type='execution_test_qa_assessment',actor='qa',body=b); "
            "print(json.dumps(r,sort_keys=True))"
        )
        appended = await environment.exec(
            command=(
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={shlex.quote(SDK_ROOT)} "
                f"python3 -c {shlex.quote(program)}"
            ),
            user=environment.default_user,
        )
        lines = [line for line in (appended.stdout or "").splitlines() if line.strip()]
        if appended.return_code != 0 or not lines:
            return {
                "ok": False,
                "status": "execution_test_qa_append_failed",
                "error": (appended.stderr or appended.stdout or "no output")[-4000:],
            }
        try:
            return {"ok": True, **json.loads(lines[-1])}
        except json.JSONDecodeError:
            return {
                "ok": False,
                "status": "execution_test_qa_append_unreadable",
                "error": (appended.stdout or "")[-4000:],
            }

    async def _read_graph_audit(
        self,
        environment: BaseEnvironment,
        *,
        path: str,
        study_profile_digest: str,
        graph_digest: str,
        snapshot_ref: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        result = await environment.exec(
            command=f"python3 -c {shlex.quote(remote_json_read_program(path))}",
            user=environment.default_user,
        )
        if result.return_code != 0 or not result.stdout:
            return None, {
                "valid": False,
                "errors": ["GRAPH_AUDIT_UNREADABLE"],
                "path_assessment": "not_assessed",
                "repair_required": False,
            }
        try:
            value = load_qa_json_text(result.stdout)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, {
                "valid": False,
                "errors": ["GRAPH_AUDIT_JSON"],
                "path_assessment": "not_assessed",
                "repair_required": False,
            }
        errors = validate_graph_audit(
            value,
            study_profile_digest=study_profile_digest,
            graph_digest=graph_digest,
            snapshot_ref=snapshot_ref,
        )
        repair_required = (
            not errors
            and isinstance(value, dict)
            and value.get("repair_recommended") is True
            and value.get("path_assessment") in {"drifted", "incomplete"}
            and bool(value.get("witnesses"))
        )
        return value, {
            "valid": not errors,
            "errors": errors,
            "path_assessment": (
                value.get("path_assessment")
                if not errors and isinstance(value, dict)
                else "not_assessed"
            ),
            "repair_required": repair_required,
            "advisory_only": True,
            "blocking_gate": False,
            "authorizes_mutation": False,
        }

    async def _run_task(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not self.model_name:
            raise ValueError("Model name is required")
        if self.ARM not in {"method", "neutral"}:
            raise ValueError("Graph Kernel agent arm is not configured")

        worker = self._child_agent("worker")
        qa = self._child_agent("qa")
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        task_timeout_seconds = _task_timeout_seconds(instruction)
        task_deadline = started_at + task_timeout_seconds
        execution_deadline = task_deadline - FINALIZATION_RESERVE_SECONDS
        method_text = (
            self._method_source.decode("utf-8") if self.ARM == "method" else None
        )
        profile = graph_study_profile(
            arm=self.ARM,
            task_instruction=instruction,
            model_name=self.model_name,
            task_timeout_seconds=task_timeout_seconds,
            agent_version=GRAPH_AGENT_VERSION,
            kit_version=str(self._sdk_identity["kit_version"]),
            kit_tree_digest=str(self._sdk_identity["tree_digest"]),
        )
        await self._write_root_json(
            environment, path=STUDY_PROFILE_PATH, value=profile
        )
        metadata: dict[str, Any] = {
            "schema_version": "charting-loop/graph-kernel-run/v2",
            "method": "method-guided-graph-kernel",
            "arm": self.ARM,
            "study_profile": profile,
            "study_profile_digest": profile["profile_digest"],
            "builder_present": False,
            "roles": ["worker", "qa"],
            "task_clock_roles": ["worker", "qa"],
            "qa_schedule": (
                "compile_candidate_then_execution_test_contract_then_each_worker_freeze"
            ),
            "qa_budget_is_separate": False,
            "phase_events": [
                "study_profile_frozen",
                "graph_kernel_ready",
                "worker_compile_started",
            ],
            "phase_runs": [],
            "deadline_policy": "single_task_deadline",
            "task_timeout_seconds": task_timeout_seconds,
            "finalization_reserve_seconds": FINALIZATION_RESERVE_SECONDS,
            "phase_time_allocations": None,
            "corridor_sdk": dict(self._sdk_identity),
            "submission_root": SUBMISSION_ROOT,
            "submission_snapshots": [],
            "graph_path": GRAPH_PATH,
            "graph_revision_freezes": [],
            "qa_audits": [],
            "qa_is_advisory": True,
            "qa_can_recommend_repair": True,
            "qa_can_repair": False,
            "repair_actor": "same_worker_session",
            "official_verifier_schedule": "after_agent_return",
            "last_worker_snapshot_owns_fallback": True,
            "grading_owned_by_harbor": True,
        }
        context.metadata = metadata

        qa_started = False
        worker_started = False
        compile_iteration = 0
        compile_candidate: dict[str, Any] | None = None
        compile_qa_path: str | None = None
        rule_closure: dict[str, Any] | None = None
        compile_decision: dict[str, Any] = {
            "valid": False,
            "errors": ["RULE_COMPILE_QA_NOT_RUN"],
            "outcome": "not_assessed",
            "rule_closure_ready": False,
        }
        prior_candidate: dict[str, Any] | None = None
        while _remaining_seconds(execution_deadline) > 0 and rule_closure is None:
            compile_iteration += 1
            ir_path, report_path = self._rule_compile_paths(compile_iteration)
            if worker_started:
                assert prior_candidate is not None and compile_qa_path is not None
                if (
                    prior_candidate.get("status")
                    == "compile_candidate_semantic_rejected"
                ):
                    repair_prompt = graph_compile_failure_repair_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        failed_candidate_id=str(
                            prior_candidate["failed_candidate_id"]
                        ),
                        prior_typed_rule_ir_digest=str(
                            prior_candidate["typed_rule_ir_sha256"]
                        ),
                        qa_path=compile_qa_path,
                        output_ir_path=ir_path,
                        output_report_path=report_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    )
                else:
                    repair_prompt = graph_compile_repair_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        prior_graph_digest=str(prior_candidate["graph_digest"]),
                        prior_candidate_report_record_id=str(
                            prior_candidate["candidate_report_record_id"]
                        ),
                        qa_path=compile_qa_path,
                        output_ir_path=ir_path,
                        output_report_path=report_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    )
                _, worker_run = await self._resume_role(
                    "worker",
                    worker,
                    repair_prompt,
                    environment,
                    phase=f"worker-recompile-{compile_iteration:04d}",
                    deadline=execution_deadline,
                )
            else:
                _, worker_run = await self._run_new_role(
                    "worker",
                    worker,
                    graph_worker_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    ),
                    environment,
                    deadline=execution_deadline,
                )
                worker_started = True
            self._record_phase_outcome(metadata, worker_run, context)
            compile_candidate = await self._freeze_rule_compile_candidate(
                environment,
                iteration=compile_iteration,
                ir_path=ir_path,
            )
            metadata.setdefault("compile_candidates", []).append(
                self._rule_compile_candidate_metadata(compile_candidate)
            )
            compiler_rejected = (
                compile_candidate.get("status")
                == "compile_candidate_semantic_rejected"
            )
            if compile_candidate.get("ok") is not True and not compiler_rejected:
                metadata["phase_events"].append("compile_candidate_build_failed")
                break
            if compiler_rejected:
                metadata["phase_events"].append(
                    "compile_candidate_semantic_rejected"
                )

            compile_qa_path = (
                PurePosixPath(RUNTIME_ROOT)
                / "qa"
                / f"compile-audit-{compile_iteration:04d}.json"
            ).as_posix()
            await self._open_qa_directory(environment)
            try:
                if compiler_rejected:
                    compile_prompt = graph_compile_failure_qa_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        failed_candidate_id=str(
                            compile_candidate["failed_candidate_id"]
                        ),
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                        typed_rule_ir_path=str(
                            compile_candidate["typed_rule_ir_path"]
                        ),
                        typed_rule_ir_digest=str(
                            compile_candidate["typed_rule_ir_sha256"]
                        ),
                        typed_rule_ir_size=int(
                            compile_candidate["typed_rule_ir_size"]
                        ),
                        failure_descriptor_path=str(
                            compile_candidate["failure_descriptor_path"]
                        ),
                        failure_descriptor_digest=str(
                            compile_candidate["failure_descriptor_sha256"]
                        ),
                        failure_descriptor_size=int(
                            compile_candidate["failure_descriptor_size"]
                        ),
                        qa_output_path=compile_qa_path,
                        audit_iteration=compile_iteration,
                    )
                else:
                    compile_prompt = graph_compile_qa_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        graph_digest=str(compile_candidate["graph_digest"]),
                        candidate_report_record_id=str(
                            compile_candidate["candidate_report_record_id"]
                        ),
                        candidate_report_digest=str(
                            compile_candidate["candidate_report_digest"]
                        ),
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                        graph_path=str(compile_candidate["graph_path"]),
                        typed_rule_ir_path=str(
                            compile_candidate["typed_rule_ir_path"]
                        ),
                        typed_rule_ir_digest=str(
                            compile_candidate["typed_rule_ir_sha256"]
                        ),
                        typed_rule_ir_size=int(
                            compile_candidate["typed_rule_ir_size"]
                        ),
                        typed_rule_report_path=str(
                            compile_candidate["typed_rule_report_path"]
                        ),
                        typed_rule_report_digest=str(
                            compile_candidate["compile_report_sha256"]
                        ),
                        typed_rule_report_size=int(
                            compile_candidate["compile_report_size"]
                        ),
                        qa_output_path=compile_qa_path,
                        audit_iteration=compile_iteration,
                    )
                if qa_started:
                    _, qa_run = await self._resume_role(
                        "qa",
                        qa,
                        compile_prompt,
                        environment,
                        phase=f"compile-qa-{compile_iteration:04d}",
                        deadline=execution_deadline,
                    )
                else:
                    _, qa_run = await self._run_new_role(
                        "qa", qa, compile_prompt, environment, deadline=execution_deadline
                    )
                    qa_started = True
                qa_snapshot = await self._freeze_submission_paths(
                    environment, role="qa", paths=[compile_qa_path]
                )
                metadata["submission_snapshots"].append(qa_snapshot)
            finally:
                await self._seal_qa_directory(environment)
            self._record_phase_outcome(metadata, qa_run, context)
            compile_assessment, compile_decision = await self._read_rule_compile_audit(
                environment,
                path=compile_qa_path,
                study_profile_digest=str(profile["profile_digest"]),
                candidate=compile_candidate,
            )
            compile_audit_record = {
                "kind": "rule_compile",
                "iteration": compile_iteration,
                "qa_path": compile_qa_path,
                "decision": compile_decision,
                "assessment": compile_assessment,
            }
            if compiler_rejected:
                compile_audit_record.update(
                    {
                        "candidate_status": compile_candidate["status"],
                        "failed_candidate_id": compile_candidate[
                            "failed_candidate_id"
                        ],
                        "typed_rule_ir_sha256": compile_candidate[
                            "typed_rule_ir_sha256"
                        ],
                        "failure_descriptor_sha256": compile_candidate[
                            "failure_descriptor_sha256"
                        ],
                    }
                )
            else:
                compile_audit_record.update(
                    {
                        "graph_digest": compile_candidate["graph_digest"],
                        "candidate_report_record_id": compile_candidate[
                            "candidate_report_record_id"
                        ],
                    }
                )
            metadata["qa_audits"].append(compile_audit_record)
            compile_assessment_record: dict[str, Any] | None = None
            if compiler_rejected and compile_decision.get("valid") is not True:
                metadata["phase_events"].append(
                    "compile_failure_audit_invalid"
                )
                break
            if compile_decision.get("valid") is True and not compiler_rejected:
                compile_assessment_record = await self._install_rule_closure(
                    environment,
                    candidate=compile_candidate,
                    qa_path=compile_qa_path,
                    iteration=compile_iteration,
                )
                metadata.setdefault("compile_assessment_graphs", []).append(
                    compile_assessment_record
                )
                if compile_assessment_record.get("ok") is not True:
                    metadata["phase_events"].append("compile_assessment_record_failed")
                    break
            if compile_decision.get("rule_closure_ready") is True:
                if (
                    compile_assessment_record is None
                    or compile_assessment_record.get("rule_closure_established") is not True
                ):
                    metadata["phase_events"].append("rule_closure_install_failed")
                    break
                rule_closure = compile_assessment_record
                metadata["phase_events"].append("rule_closure_established")
                break
            if (
                compile_assessment_record is not None
                and compile_assessment_record.get("rule_closure_established") is True
            ):
                metadata["phase_events"].append("nonpassing_compile_created_closure")
                break
            metadata["phase_events"].append("compile_qa_returned_for_recompile")
            prior_candidate = compile_candidate

        metadata["compile_qa_decision"] = compile_decision
        metadata["rule_closure"] = rule_closure
        execution_test_iteration = 0
        execution_test_candidate: dict[str, Any] | None = None
        execution_test_qa_path: str | None = None
        execution_test_qa_assessment_record_id: str | None = None
        execution_test_decision: dict[str, Any] = {
            "valid": False,
            "errors": ["EXECUTION_TEST_QA_NOT_RUN"],
            "outcome": "not_assessed",
            "revision_requested": False,
            "advisory_only": True,
            "blocking_gate": False,
            "authorizes_mutation": False,
        }
        if rule_closure is not None and _remaining_seconds(execution_deadline) > 0:
            while _remaining_seconds(execution_deadline) > 0:
                execution_test_iteration += 1
                execution_test_qa_assessment_record_id = None
                if execution_test_candidate is None:
                    plan_prompt = graph_execution_test_plan_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        graph_digest=str(rule_closure["graph_digest"]),
                        qa_assessment_ref=str(rule_closure["qa_assessment_ref"]),
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    )
                    phase = "worker-execution-test-plan"
                else:
                    assert execution_test_qa_path is not None
                    plan_prompt = graph_execution_test_repair_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        prior_contract_record_id=str(
                            execution_test_candidate[
                                "execution_test_contract_record_id"
                            ]
                        ),
                        prior_contract_digest=str(
                            execution_test_candidate[
                                "execution_test_contract_digest"
                            ]
                        ),
                        qa_path=execution_test_qa_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    )
                    phase = f"worker-execution-test-revision-{execution_test_iteration:04d}"
                _, plan_run = await self._resume_role(
                    "worker",
                    worker,
                    plan_prompt,
                    environment,
                    phase=phase,
                    deadline=execution_deadline,
                )
                self._record_phase_outcome(metadata, plan_run, context)
                execution_test_candidate = await self._freeze_graph_revision(
                    environment,
                    iteration=execution_test_iteration,
                    worker_snapshot_ref=(
                        f"execution-test-contract-{execution_test_iteration:04d}"
                    ),
                    namespace="execution-test",
                    include_execution_test_fixtures=True,
                )
                metadata.setdefault("execution_test_candidates", []).append(
                    execution_test_candidate
                )
                if execution_test_candidate.get("ok") is not True:
                    metadata["phase_events"].append(
                        "execution_test_candidate_freeze_failed"
                    )
                    break
                contract_record_id = execution_test_candidate.get(
                    "execution_test_contract_record_id"
                )
                contract_digest = execution_test_candidate.get(
                    "execution_test_contract_digest"
                )
                fixture_manifest_path = execution_test_candidate.get(
                    "execution_test_fixture_manifest_path"
                )
                if not all(
                    isinstance(item, str) and item
                    for item in (
                        contract_record_id,
                        contract_digest,
                        fixture_manifest_path,
                    )
                ):
                    metadata["phase_events"].append(
                        "execution_test_candidate_identity_missing"
                    )
                    break
                execution_test_qa_path = (
                    PurePosixPath(RUNTIME_ROOT)
                    / "qa"
                    / f"execution-test-audit-{execution_test_iteration:04d}.json"
                ).as_posix()
                await self._open_qa_directory(environment)
                try:
                    test_qa_prompt = graph_execution_test_qa_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        graph_digest=str(execution_test_candidate["graph_digest"]),
                        contract_record_id=str(contract_record_id),
                        contract_digest=str(contract_digest),
                        fixture_manifest_path=str(fixture_manifest_path),
                        graph_path=str(execution_test_candidate["graph_path"]),
                        qa_output_path=execution_test_qa_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                        audit_iteration=execution_test_iteration,
                    )
                    if qa_started:
                        _, test_qa_run = await self._resume_role(
                            "qa",
                            qa,
                            test_qa_prompt,
                            environment,
                            phase=f"execution-test-qa-{execution_test_iteration:04d}",
                            deadline=execution_deadline,
                        )
                    else:
                        _, test_qa_run = await self._run_new_role(
                            "qa",
                            qa,
                            test_qa_prompt,
                            environment,
                            deadline=execution_deadline,
                        )
                        qa_started = True
                    qa_snapshot = await self._freeze_submission_paths(
                        environment,
                        role="qa",
                        paths=[execution_test_qa_path],
                    )
                    metadata["submission_snapshots"].append(qa_snapshot)
                finally:
                    await self._seal_qa_directory(environment)
                self._record_phase_outcome(metadata, test_qa_run, context)
                test_assessment, execution_test_decision = (
                    await self._read_execution_test_audit(
                        environment,
                        path=execution_test_qa_path,
                        study_profile_digest=str(profile["profile_digest"]),
                        candidate=execution_test_candidate,
                    )
                )
                metadata["qa_audits"].append(
                    {
                        "kind": "execution_test_pre_action",
                        "iteration": execution_test_iteration,
                        "qa_path": execution_test_qa_path,
                        "graph_digest": execution_test_candidate["graph_digest"],
                        "contract_record_id": contract_record_id,
                        "contract_digest": contract_digest,
                        "decision": execution_test_decision,
                        "assessment": test_assessment,
                    }
                )
                if execution_test_decision.get("valid") is True:
                    appended = await self._append_execution_test_qa_assessment(
                        environment,
                        qa_path=execution_test_qa_path,
                        candidate=execution_test_candidate,
                    )
                    metadata.setdefault(
                        "execution_test_assessment_records", []
                    ).append(appended)
                    if appended.get("ok") is True and isinstance(
                        appended.get("record_id"), str
                    ):
                        execution_test_qa_assessment_record_id = str(
                            appended["record_id"]
                        )
                if execution_test_decision.get("outcome") == "pass":
                    metadata["phase_events"].append("execution_test_qa_passed")
                    break
                if (
                    execution_test_decision.get("revision_requested") is True
                    and execution_test_iteration < 2
                    and _remaining_seconds(execution_deadline) > 0
                ):
                    metadata["phase_events"].append(
                        "execution_test_qa_returned_for_revision"
                    )
                    continue
                metadata["phase_events"].append(
                    "execution_test_unresolved_but_nonblocking"
                )
                break

        metadata["execution_test_qa_decision"] = execution_test_decision
        if rule_closure is not None and _remaining_seconds(execution_deadline) > 0:
            live_doctor = await self._graph_doctor_report(
                environment, graph_path=GRAPH_PATH
            )
            _, implementation_run = await self._resume_role(
                "worker",
                worker,
                graph_implementation_prompt(
                    instruction,
                    arm=self.ARM,
                    study_profile_digest=str(profile["profile_digest"]),
                    graph_digest=str(
                        live_doctor.get("graph_digest", rule_closure["graph_digest"])
                    ),
                    qa_assessment_ref=str(rule_closure["qa_assessment_ref"]),
                    remaining_seconds=_remaining_seconds(execution_deadline),
                    method_text=method_text,
                    execution_test_contract_record_id=(
                        str(
                            execution_test_candidate.get(
                                "execution_test_contract_record_id"
                            )
                        )
                        if execution_test_candidate
                        and execution_test_candidate.get(
                            "execution_test_contract_record_id"
                        )
                        else None
                    ),
                    execution_test_contract_digest=(
                        str(
                            execution_test_candidate.get(
                                "execution_test_contract_digest"
                            )
                        )
                        if execution_test_candidate
                        and execution_test_candidate.get(
                            "execution_test_contract_digest"
                        )
                        else None
                    ),
                    execution_test_qa_outcome=str(
                        execution_test_decision.get("outcome", "not_assessed")
                        if execution_test_qa_assessment_record_id is not None
                        else "missing"
                    ),
                    execution_test_qa_assessment_record_id=(
                        execution_test_qa_assessment_record_id
                    ),
                ),
                environment,
                phase="worker-implementation",
                deadline=execution_deadline,
            )
            self._record_phase_outcome(metadata, implementation_run, context)
            metadata["worker_revision_progress"] = await self._worker_revision_progress(
                environment
            )
        elif rule_closure is None:
            metadata["phase_events"].append("implementation_not_started_without_rule_closure")
        else:
            metadata["phase_events"].append("implementation_skipped_task_deadline")

        audited_snapshot_refs: set[str] = set()
        audit_iteration = 0
        last_decision: dict[str, Any] = {
            "valid": False,
            "errors": ["QA_NOT_RUN"],
            "path_assessment": "not_assessed",
            "repair_required": False,
            "advisory_only": True,
            "blocking_gate": False,
            "authorizes_mutation": False,
        }
        while _remaining_seconds(execution_deadline) > 0:
            progress = await self._worker_revision_progress(environment)
            metadata["worker_revision_progress"] = progress
            snapshots = progress.get("snapshots", []) if isinstance(progress, dict) else []
            snapshot_ref = (
                str(snapshots[-1].get("snapshot_id"))
                if isinstance(snapshots, list)
                and snapshots
                and isinstance(snapshots[-1], dict)
                and isinstance(snapshots[-1].get("snapshot_id"), str)
                else None
            )
            if snapshot_ref is None:
                metadata["phase_events"].append("qa_skipped_no_valid_worker_freeze")
                break
            if snapshot_ref in audited_snapshot_refs:
                metadata["phase_events"].append("repair_did_not_advance_worker_freeze")
                break
            audit_iteration += 1
            graph_revision = await self._freeze_graph_revision(
                environment,
                iteration=audit_iteration,
                worker_snapshot_ref=snapshot_ref,
            )
            metadata["graph_revision_freezes"].append(graph_revision)
            position_ref = graph_revision.get("position_ref")
            direction_digest = graph_revision.get("direction_digest")
            graph_path_complete = (
                isinstance(position_ref, str)
                and bool(position_ref)
                and isinstance(direction_digest, str)
                and bool(direction_digest)
            )
            metadata.setdefault("graph_path_observations", []).append(
                {
                    "iteration": audit_iteration,
                    "worker_snapshot_ref": snapshot_ref,
                    "rule_closure_established": rule_closure is not None,
                    "position_ref": position_ref,
                    "direction_digest": direction_digest,
                    "complete": graph_path_complete,
                    "advisory_only": True,
                    "blocking_gate": False,
                }
            )
            metadata["phase_events"].append(
                "implementation_graph_path_complete"
                if graph_path_complete
                else "implementation_graph_path_incomplete"
            )
            if graph_revision.get("ok") is not True:
                metadata["phase_events"].append("qa_skipped_invalid_graph_revision")
                break
            audited_snapshot_refs.add(snapshot_ref)
            qa_path = (
                PurePosixPath(RUNTIME_ROOT)
                / "qa"
                / f"graph-audit-{audit_iteration:04d}.json"
            ).as_posix()
            await self._open_qa_directory(environment)
            try:
                prompt = graph_qa_prompt(
                    instruction,
                    arm=self.ARM,
                    study_profile_digest=str(profile["profile_digest"]),
                    graph_digest=str(graph_revision["graph_digest"]),
                    latest_worker_snapshot_ref=snapshot_ref,
                    remaining_seconds=_remaining_seconds(execution_deadline),
                    method_text=method_text,
                    graph_path=str(graph_revision["graph_path"]),
                    qa_output_path=qa_path,
                    audit_iteration=audit_iteration,
                )
                if qa_started:
                    _, qa_run = await self._resume_role(
                        "qa",
                        qa,
                        prompt,
                        environment,
                        phase=f"qa-audit-{audit_iteration:04d}",
                        deadline=execution_deadline,
                    )
                else:
                    _, qa_run = await self._run_new_role(
                        "qa",
                        qa,
                        prompt,
                        environment,
                        deadline=execution_deadline,
                    )
                    qa_started = True
                qa_snapshot = await self._freeze_submission_paths(
                    environment,
                    role="qa",
                    paths=[qa_path],
                )
                metadata["submission_snapshots"].append(qa_snapshot)
            finally:
                await self._seal_qa_directory(environment)
            self._record_phase_outcome(metadata, qa_run, context)
            assessment, last_decision = await self._read_graph_audit(
                environment,
                path=qa_path,
                study_profile_digest=str(profile["profile_digest"]),
                graph_digest=str(graph_revision["graph_digest"]),
                snapshot_ref=snapshot_ref,
            )
            metadata["qa_audits"].append(
                {
                    "kind": "frozen_result",
                    "iteration": audit_iteration,
                    "qa_path": qa_path,
                    "worker_snapshot_ref": snapshot_ref,
                    "graph_digest": graph_revision["graph_digest"],
                    "decision": last_decision,
                    "assessment": assessment,
                }
            )
            if not last_decision.get("repair_required"):
                metadata["phase_events"].append("qa_repair_not_requested")
                break
            if _remaining_seconds(execution_deadline) <= 0:
                metadata["phase_events"].append("repair_skipped_task_deadline")
                break

            repair_test_candidate: dict[str, Any] | None = None
            repair_test_decision: dict[str, Any] = {
                "valid": False,
                "errors": ["REPAIR_EXECUTION_TEST_QA_NOT_RUN"],
                "outcome": "not_assessed",
                "revision_requested": False,
                "advisory_only": True,
                "blocking_gate": False,
                "authorizes_mutation": False,
            }
            repair_test_qa_path: str | None = None
            repair_test_qa_assessment_record_id: str | None = None
            for repair_test_iteration in range(1, 3):
                if _remaining_seconds(execution_deadline) <= 0:
                    metadata["phase_events"].append(
                        "repair_execution_test_skipped_task_deadline"
                    )
                    break
                repair_test_qa_assessment_record_id = None
                if repair_test_candidate is None:
                    repair_plan_prompt = graph_result_repair_test_plan_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        graph_digest=str(graph_revision["graph_digest"]),
                        audited_snapshot_ref=snapshot_ref,
                        qa_path=qa_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    )
                    repair_plan_phase = (
                        f"repair-execution-test-plan-{audit_iteration:04d}"
                    )
                else:
                    assert repair_test_qa_path is not None
                    repair_plan_prompt = graph_execution_test_repair_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        prior_contract_record_id=str(
                            repair_test_candidate[
                                "execution_test_contract_record_id"
                            ]
                        ),
                        prior_contract_digest=str(
                            repair_test_candidate[
                                "execution_test_contract_digest"
                            ]
                        ),
                        qa_path=repair_test_qa_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                    )
                    repair_plan_phase = (
                        "repair-execution-test-revision-"
                        f"{audit_iteration:04d}-{repair_test_iteration:04d}"
                    )
                _, repair_plan_run = await self._resume_role(
                    "worker",
                    worker,
                    repair_plan_prompt,
                    environment,
                    phase=repair_plan_phase,
                    deadline=execution_deadline,
                )
                self._record_phase_outcome(metadata, repair_plan_run, context)
                repair_test_candidate = await self._freeze_graph_revision(
                    environment,
                    iteration=repair_test_iteration,
                    worker_snapshot_ref=(
                        "repair-execution-test-contract-"
                        f"{audit_iteration:04d}-{repair_test_iteration:04d}"
                    ),
                    namespace=f"repair-execution-test-{audit_iteration:04d}",
                    include_execution_test_fixtures=True,
                )
                metadata.setdefault("repair_execution_test_candidates", []).append(
                    repair_test_candidate
                )
                if repair_test_candidate.get("ok") is not True:
                    metadata["phase_events"].append(
                        "repair_execution_test_candidate_freeze_failed"
                    )
                    break
                repair_contract_record_id = repair_test_candidate.get(
                    "execution_test_contract_record_id"
                )
                repair_contract_digest = repair_test_candidate.get(
                    "execution_test_contract_digest"
                )
                repair_fixture_manifest_path = repair_test_candidate.get(
                    "execution_test_fixture_manifest_path"
                )
                if not all(
                    isinstance(item, str) and item
                    for item in (
                        repair_contract_record_id,
                        repair_contract_digest,
                        repair_fixture_manifest_path,
                    )
                ):
                    metadata["phase_events"].append(
                        "repair_execution_test_candidate_identity_missing"
                    )
                    break
                repair_test_qa_path = (
                    PurePosixPath(RUNTIME_ROOT)
                    / "qa"
                    / (
                        "repair-execution-test-audit-"
                        f"{audit_iteration:04d}-{repair_test_iteration:04d}.json"
                    )
                ).as_posix()
                await self._open_qa_directory(environment)
                try:
                    repair_test_qa_prompt = graph_execution_test_qa_prompt(
                        instruction,
                        arm=self.ARM,
                        study_profile_digest=str(profile["profile_digest"]),
                        graph_digest=str(repair_test_candidate["graph_digest"]),
                        contract_record_id=str(repair_contract_record_id),
                        contract_digest=str(repair_contract_digest),
                        fixture_manifest_path=str(repair_fixture_manifest_path),
                        graph_path=str(repair_test_candidate["graph_path"]),
                        qa_output_path=repair_test_qa_path,
                        remaining_seconds=_remaining_seconds(execution_deadline),
                        method_text=method_text,
                        audit_iteration=repair_test_iteration,
                    )
                    _, repair_test_qa_run = await self._resume_role(
                        "qa",
                        qa,
                        repair_test_qa_prompt,
                        environment,
                        phase=(
                            "repair-execution-test-qa-"
                            f"{audit_iteration:04d}-{repair_test_iteration:04d}"
                        ),
                        deadline=execution_deadline,
                    )
                    repair_qa_snapshot = await self._freeze_submission_paths(
                        environment,
                        role="qa",
                        paths=[repair_test_qa_path],
                    )
                    metadata["submission_snapshots"].append(repair_qa_snapshot)
                finally:
                    await self._seal_qa_directory(environment)
                self._record_phase_outcome(metadata, repair_test_qa_run, context)
                repair_test_assessment, repair_test_decision = (
                    await self._read_execution_test_audit(
                        environment,
                        path=repair_test_qa_path,
                        study_profile_digest=str(profile["profile_digest"]),
                        candidate=repair_test_candidate,
                    )
                )
                metadata["qa_audits"].append(
                    {
                        "kind": "repair_execution_test_pre_action",
                        "result_audit_iteration": audit_iteration,
                        "iteration": repair_test_iteration,
                        "qa_path": repair_test_qa_path,
                        "graph_digest": repair_test_candidate["graph_digest"],
                        "contract_record_id": repair_contract_record_id,
                        "contract_digest": repair_contract_digest,
                        "decision": repair_test_decision,
                        "assessment": repair_test_assessment,
                    }
                )
                if repair_test_decision.get("valid") is True:
                    appended = await self._append_execution_test_qa_assessment(
                        environment,
                        qa_path=repair_test_qa_path,
                        candidate=repair_test_candidate,
                    )
                    metadata.setdefault(
                        "execution_test_assessment_records", []
                    ).append(appended)
                    if appended.get("ok") is True and isinstance(
                        appended.get("record_id"), str
                    ):
                        repair_test_qa_assessment_record_id = str(
                            appended["record_id"]
                        )
                if repair_test_decision.get("outcome") == "pass":
                    metadata["phase_events"].append(
                        "repair_execution_test_qa_passed"
                    )
                    break
                if (
                    repair_test_decision.get("revision_requested") is True
                    and repair_test_iteration < 2
                    and _remaining_seconds(execution_deadline) > 0
                ):
                    metadata["phase_events"].append(
                        "repair_execution_test_qa_returned_for_revision"
                    )
                    continue
                metadata["phase_events"].append(
                    "repair_execution_test_unresolved_but_nonblocking"
                )
                break

            _, repair_run = await self._resume_role(
                "worker",
                worker,
                graph_repair_prompt(
                    instruction,
                    arm=self.ARM,
                    study_profile_digest=str(profile["profile_digest"]),
                    graph_digest=str(graph_revision["graph_digest"]),
                    audited_snapshot_ref=snapshot_ref,
                    qa_path=qa_path,
                    remaining_seconds=_remaining_seconds(execution_deadline),
                    method_text=method_text,
                    execution_test_contract_record_id=(
                        str(
                            repair_test_candidate.get(
                                "execution_test_contract_record_id"
                            )
                        )
                        if repair_test_candidate
                        and repair_test_candidate.get(
                            "execution_test_contract_record_id"
                        )
                        else None
                    ),
                    execution_test_contract_digest=(
                        str(
                            repair_test_candidate.get(
                                "execution_test_contract_digest"
                            )
                        )
                        if repair_test_candidate
                        and repair_test_candidate.get(
                            "execution_test_contract_digest"
                        )
                        else None
                    ),
                    execution_test_qa_outcome=str(
                        repair_test_decision.get("outcome", "not_assessed")
                        if repair_test_qa_assessment_record_id is not None
                        else "missing"
                    ),
                    execution_test_qa_assessment_record_id=(
                        repair_test_qa_assessment_record_id
                    ),
                ),
                environment,
                phase=f"repair-{audit_iteration:04d}",
                deadline=execution_deadline,
            )
            self._record_phase_outcome(metadata, repair_run, context)
            metadata["worker_revision_progress"] = await self._worker_revision_progress(
                environment
            )

        metadata["qa_decision"] = last_decision
        freeze = await self._seal_graph_corridor(environment)
        metadata["corridor_digest"] = freeze["corridor_digest"]
        metadata["graph_bytes_digest"] = freeze.get("graph_bytes_digest")
        metadata["graph_validation"] = freeze.get("graph_validation")
        metadata["graph_doctor"] = freeze.get("graph_doctor")
        metadata["graph_structurally_valid"] = freeze.get("graph_structurally_valid")
        metadata["phase_events"].append("final_graph_sealed")
        metadata["submission_fallback"] = await self._restore_latest_worker_submission(
            environment
        )
        metadata["worker_revision_progress"] = await self._worker_revision_progress(
            environment
        )
        metadata["task_deadline_reached"] = loop.time() >= execution_deadline
        metadata["elapsed_seconds"] = round(loop.time() - started_at, 3)
        metadata["remaining_finalization_seconds"] = max(
            0.0, round(task_deadline - loop.time(), 3)
        )
        metadata["phase_events"].append("agent_returned_for_grading")
        context.metadata = metadata


class ChartingLoopGraphKernelMethodAgent(_ChartingLoopGraphKernelAgent):
    """Treatment: frozen Method v8 plus the shared Graph Kernel."""

    ARM = "method"

    @staticmethod
    def name() -> str:
        return "charting-loop-graph-kernel-method"


class ChartingLoopGraphKernelNeutralAgent(_ChartingLoopGraphKernelAgent):
    """Control: frozen neutral instruction plus the same Graph Kernel bytes."""

    ARM = "neutral"

    @staticmethod
    def name() -> str:
        return "charting-loop-graph-kernel-neutral"
