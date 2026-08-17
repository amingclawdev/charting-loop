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
import shlex
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Agent, FinalMetrics, Step, Trajectory
from harbor.models.trial.paths import EnvironmentPaths
from harbor.utils.trajectory_utils import format_trajectory_json

from benchmark_agents.contract import (
    CLOSURE_PATH,
    FREEZE_PATH,
    METHOD_PATH,
    QA_PATH,
    RUNTIME_ROOT,
    builder_prompt,
    closure_prompt,
    freeze_program,
    load_qa_json_text,
    qa_prompt,
    remote_json_read_program,
    repair_prompt,
    validate_qa_assessment,
    verify_freeze_program,
    worker_prompt,
)


AGENT_VERSION = "0.5.1"
METHOD_VERSION_ID = "charting-loop-method-v4"
METHOD_SOURCE_COMMIT = "0d3ed5c357c906edcc697a83b3ce681c68cd353a"
METHOD_CONTENT_SHA256 = (
    "sha256:d3a9da497c31f3bde46a31f37990236af51b9f677ae807d023582b27254c4ab0"
)
METHOD_SCOPE_SHA256 = (
    "sha256:65c6a91120c15bec30278288a26ecc98bdf96cfb07fd490dc915408a78844327"
)
ROLE_ORDER = ("builder", "worker", "qa")
PHASE_TIMEOUT_SECONDS = {
    "builder": 1800,
    "worker": 900,
    "qa": 450,
    "repair": 210,
    "closure": 60,
}
PHASE_TIMEOUT_TOTAL_SECONDS = sum(PHASE_TIMEOUT_SECONDS.values())
PHASE_TOKEN_ENV = "CHARTING_LOOP_PHASE_TOKEN"


def _codex_runtime_binding_command(
    *,
    nvm_node_root: str = "/root/.nvm/versions/node",
    stable_bin_dir: str = "/usr/local/bin",
) -> str:
    """Bind an NVM-installed Codex CLI into a fresh-shell stable PATH."""

    node_root = shlex.quote(nvm_node_root)
    bin_dir = shlex.quote(stable_bin_dir)
    fresh_path = shlex.quote(f"{stable_bin_dir}:/usr/bin:/bin")
    return (
        "set -eu; "
        f"NVM_NODE_ROOT={node_root}; STABLE_BIN_DIR={bin_dir}; "
        'CODEX_BIN="$(find "$NVM_NODE_ROOT" -path "*/bin/codex" '
        '\\( -type f -o -type l \\) -print 2>/dev/null | sort -V | tail -n 1)"; '
        'test -n "$CODEX_BIN" && test -e "$CODEX_BIN"; '
        'NODE_BIN="${CODEX_BIN%/codex}/node"; test -x "$NODE_BIN"; '
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
        return (
            "command -v setsid >/dev/null 2>&1 || "
            "{ echo 'setsid is required for phase isolation' >&2; exit 125; }; "
            f"rm -f {shlex.quote(identity_path)}; "
            f"export {PHASE_TOKEN_ENV}={shlex.quote(token)}; "
            f"setsid sh -c {shlex.quote(command)} & phase_pid=$!; "
            f"printf {shlex.quote(identity)} \"$phase_pid\" \"$phase_pid\" "
            f"> {shlex.quote(identity_path)}; "
            'wait "$phase_pid"; phase_status=$?; exit "$phase_status"'
        )

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
        owned_command = self._owned_command(command) if paid_command else command
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


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_frozen_method(repository_root: Path) -> Path:
    """Resolve the exact v4 bytes or fail before a paid model call."""

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
        "path": "method-paper/METHOD.md",
        "content_sha256": METHOD_CONTENT_SHA256,
        "scope_datum_path": "method-paper/SCOPE-DATUM.md",
        "scope_datum_sha256": METHOD_SCOPE_SHA256,
    }
    mismatches = [key for key, value in expected.items() if version.get(key) != value]
    if mismatches:
        raise RuntimeError(
            "Frozen method catalog binding changed: " + ", ".join(mismatches)
        )
    method_path = repository_root / expected["path"]
    scope_path = repository_root / expected["scope_datum_path"]
    if not method_path.is_file() or not scope_path.is_file():
        raise FileNotFoundError("Frozen method or scope datum is missing")
    if _sha256(method_path) != METHOD_CONTENT_SHA256:
        raise RuntimeError("Mutable METHOD.md bytes do not match the frozen v4 digest")
    if _sha256(scope_path) != METHOD_SCOPE_SHA256:
        raise RuntimeError("Mutable SCOPE-DATUM.md bytes do not match the frozen v4 digest")
    return method_path


class ChartingLoopFullMethodAgent(Codex):
    """Build, freeze, use, and independently audit one Corridor per trial."""

    SUPPORTS_HANDOFF = False

    @staticmethod
    def name() -> str:
        return "charting-loop-full-method"

    def version(self) -> str:
        return AGENT_VERSION

    @property
    def _method_source(self) -> Path:
        return _resolve_frozen_method(Path(__file__).resolve().parents[1])

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

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await self.exec_as_root(
            environment,
            command=_codex_runtime_binding_command(),
        )
        if not self._method_source.is_file():
            raise FileNotFoundError(f"Frozen method source missing: {self._method_source}")

        corridor_dir = str(PurePosixPath(RUNTIME_ROOT) / "corridor")
        scratch_dir = str(PurePosixPath(RUNTIME_ROOT) / "builder-scratch")
        method_dir = str(PurePosixPath(METHOD_PATH).parent)
        user = shlex.quote(str(environment.default_user or "root"))
        await self.exec_as_root(
            environment,
            command=(
                f"install -d -m 0755 {shlex.quote(RUNTIME_ROOT)} "
                f"{shlex.quote(method_dir)} {shlex.quote(corridor_dir)} "
                f"{shlex.quote(scratch_dir)}"
            ),
        )
        await self._upload_agent_owned_file(
            environment,
            self._method_source,
            METHOD_PATH,
        )
        await self.exec_as_root(
            environment,
            command=(
                f"chown -R 0:0 {shlex.quote(RUNTIME_ROOT)} && "
                f"chmod 0555 {shlex.quote(RUNTIME_ROOT)} "
                f"{shlex.quote(method_dir)} && "
                f"chmod 0444 {shlex.quote(METHOD_PATH)} && "
                f"chown {user} {shlex.quote(corridor_dir)} "
                f"{shlex.quote(scratch_dir)} && "
                f"chmod 0700 {shlex.quote(corridor_dir)} "
                f"{shlex.quote(scratch_dir)}"
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
        timeout_seconds: int,
    ) -> tuple[AgentContext, dict[str, Any]]:
        phase_context = AgentContext()
        outcome: dict[str, Any] = {
            "phase": role,
            "role": role,
            "mode": "new",
            "timeout_seconds": timeout_seconds,
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
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._reset_live_session(environment)
                await agent.run(prompt, environment, phase_context)
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

    async def _resume_role(
        self,
        role: str,
        agent: Codex,
        prompt: str,
        environment: BaseEnvironment,
        *,
        phase: str,
        timeout_seconds: int,
    ) -> tuple[AgentContext, dict[str, Any]]:
        phase_context = AgentContext()
        outcome: dict[str, Any] = {
            "phase": phase,
            "role": role,
            "mode": "resume",
            "timeout_seconds": timeout_seconds,
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
            async with asyncio.timeout(timeout_seconds):
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
            command=f"python3 -c {shlex.quote(freeze_program())}",
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

    async def _verify_freeze(
        self,
        environment: BaseEnvironment,
        *,
        expected_digest: str,
    ) -> None:
        result = await environment.exec(
            command=f"python3 -c {shlex.quote(verify_freeze_program())}",
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

    async def run(
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
        metadata: dict[str, Any] = {
            "schema_version": "charting-loop/full-method-run/v2",
            "method": "task-conditioned-corridor",
            "method_version_id": METHOD_VERSION_ID,
            "method_source_commit": METHOD_SOURCE_COMMIT,
            "method_content_sha256": METHOD_CONTENT_SHA256,
            "method_scope_sha256": METHOD_SCOPE_SHA256,
            "roles": ["builder", "worker", "qa"],
            "phase_events": [],
            "phase_runs": [],
            "phase_timeout_seconds": dict(PHASE_TIMEOUT_SECONDS),
            "phase_timeout_total_seconds": PHASE_TIMEOUT_TOTAL_SECONDS,
            "qa_is_advisory": True,
            "grading_owned_by_harbor": True,
        }
        context.metadata = metadata

        _, builder_run = await self._run_new_role(
            "builder",
            builder,
            builder_prompt(instruction),
            environment,
            timeout_seconds=PHASE_TIMEOUT_SECONDS["builder"],
        )
        self._record_phase_outcome(metadata, builder_run, context)

        freeze = await self._freeze_corridor(environment)
        digest = str(freeze["corridor_digest"])
        metadata["corridor_digest"] = digest
        metadata["builder_corridor_status"] = freeze.get("builder_corridor_status")
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

        await self._verify_freeze(environment, expected_digest=digest)
        _, worker_run = await self._run_new_role(
            "worker",
            worker,
            worker_prompt(
                instruction,
                digest,
                construction_readiness_status=construction_readiness_status,
            ),
            environment,
            timeout_seconds=PHASE_TIMEOUT_SECONDS["worker"],
        )
        self._record_phase_outcome(metadata, worker_run, context)

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
                ),
                environment,
                timeout_seconds=PHASE_TIMEOUT_SECONDS["qa"],
            )
        finally:
            await self._seal_qa_directory(environment)
        self._record_phase_outcome(metadata, qa_run, context)
        _, decision = await self._read_assessment(
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
        metadata["qa_decision"] = decision

        if decision["repair_required"]:
            await self._verify_freeze(environment, expected_digest=digest)
            _, repair_run = await self._resume_role(
                "worker",
                worker,
                repair_prompt(instruction, digest),
                environment,
                phase="repair",
                timeout_seconds=PHASE_TIMEOUT_SECONDS["repair"],
            )
            self._record_phase_outcome(metadata, repair_run, context)

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
                    ),
                    environment,
                    phase="closure",
                    timeout_seconds=PHASE_TIMEOUT_SECONDS["closure"],
                )
            finally:
                await self._seal_qa_directory(environment)
            self._record_phase_outcome(metadata, closure_run, context)
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

        await self._verify_freeze(environment, expected_digest=digest)
        metadata["phase_events"].append("agent_returned_for_grading")
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
            for role in ROLE_ORDER
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
                    "method": "task-conditioned-corridor",
                    "role_count": len(trajectories),
                },
            ),
            steps=[
                Step(
                    step_id=1,
                    source="agent",
                    message=(
                        "Deterministic orchestration: Builder -> frozen Corridor -> "
                        "Worker -> independent Corridor-visible QA -> optional "
                        "same-Worker repair and same-QA closure."
                    ),
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
