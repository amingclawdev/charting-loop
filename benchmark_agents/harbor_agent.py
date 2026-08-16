"""Harbor adapter for the task-conditioned full Charting Loop method.

Import with::

    benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent

The adapter deliberately leaves benchmark grading to Harbor.  Its responsibility is
only the construction/execution/review sequence and a complete multi-agent ATIF
record.  All model calls occur inside the scored trial.
"""

from __future__ import annotations

import hashlib
import json
import shlex
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


AGENT_VERSION = "0.3.0"
METHOD_VERSION_ID = "charting-loop-method-v4"
METHOD_SOURCE_COMMIT = "0d3ed5c357c906edcc697a83b3ce681c68cd353a"
METHOD_CONTENT_SHA256 = (
    "sha256:d3a9da497c31f3bde46a31f37990236af51b9f677ae807d023582b27254c4ab0"
)
METHOD_SCOPE_SHA256 = (
    "sha256:65c6a91120c15bec30278288a26ecc98bdf96cfb07fd490dc915408a78844327"
)
ROLE_ORDER = ("builder", "worker", "qa")


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
        child = Codex(
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
            f"test -d {shlex.quote(sessions.as_posix())} && "
            f"cp -R {shlex.quote(sessions.as_posix())} "
            f"{shlex.quote((role_dir / 'sessions').as_posix())} && "
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
    ) -> AgentContext:
        await self._reset_live_session(environment)
        phase_context = AgentContext()
        await agent.run(prompt, environment, phase_context)
        await self._archive_role(
            environment,
            role,
            agent._OUTPUT_FILENAME,
        )
        return phase_context

    async def _resume_role(
        self,
        role: str,
        agent: Codex,
        prompt: str,
        environment: BaseEnvironment,
    ) -> AgentContext:
        await self._restore_role(environment, role)
        phase_context = AgentContext()
        await agent.resume(prompt, environment, phase_context)
        await self._archive_role(
            environment,
            role,
            agent._OUTPUT_FILENAME,
        )
        return phase_context

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
            "qa_is_advisory": True,
            "grading_owned_by_harbor": True,
        }

        await self._run_new_role(
            "builder",
            builder,
            builder_prompt(instruction),
            environment,
        )
        metadata["phase_events"].append("builder_constructed")

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
        metadata["phase_events"].append("corridor_frozen")

        await self._verify_freeze(environment, expected_digest=digest)
        await self._run_new_role(
            "worker",
            worker,
            worker_prompt(instruction, digest),
            environment,
        )
        metadata["phase_events"].append("worker_executed")

        await self._verify_freeze(environment, expected_digest=digest)
        await self._open_qa_directory(environment)
        try:
            await self._run_new_role(
                "qa",
                qa,
                qa_prompt(
                    instruction,
                    digest,
                    acceptance_ledger_status=acceptance_ledger_status,
                    expected_acceptance_ids=expected_acceptance_ids,
                ),
                environment,
            )
        finally:
            await self._seal_qa_directory(environment)
        metadata["phase_events"].append("qa_audited")
        _, decision = await self._read_assessment(
            environment,
            path=QA_PATH,
            expected_digest=digest,
            acceptance_ledger_status=acceptance_ledger_status,
            expected_acceptance_ids=expected_acceptance_ids,
            required_acceptance_ids=required_acceptance_ids,
        )
        metadata["qa_decision"] = decision

        if decision["repair_required"]:
            await self._verify_freeze(environment, expected_digest=digest)
            await self._resume_role(
                "worker",
                worker,
                repair_prompt(instruction, digest),
                environment,
            )
            metadata["phase_events"].append("worker_repaired_once")

            await self._verify_freeze(environment, expected_digest=digest)
            await self._open_qa_directory(environment)
            try:
                await self._resume_role(
                    "qa",
                    qa,
                    closure_prompt(
                        instruction,
                        digest,
                        acceptance_ledger_status=acceptance_ledger_status,
                        expected_acceptance_ids=expected_acceptance_ids,
                    ),
                    environment,
                )
            finally:
                await self._seal_qa_directory(environment)
            metadata["phase_events"].append("qa_closed_once")
            _, closure = await self._read_assessment(
                environment,
                path=CLOSURE_PATH,
                expected_digest=digest,
                acceptance_ledger_status=acceptance_ledger_status,
                expected_acceptance_ids=expected_acceptance_ids,
                required_acceptance_ids=required_acceptance_ids,
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
