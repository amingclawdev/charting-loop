#!/usr/bin/env python3
"""Fail-closed, non-paid preflight for the Terminal-Bench 3 Corridor probe.

The doctor resolves configuration and inspects local/account state.  It never starts
a Harbor trial, a Modal task environment, or a paid model call.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "charting-loop/terminal-bench-doctor/v1"
DATASET = "terminal-bench/terminal-bench@3.0.0"
DATASET_NAME = "terminal-bench/terminal-bench"
DATASET_REF = "3.0.0"
DATASET_CONTENT_SHA256 = (
    "sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3"
)
TASK_NAME = "ico-path-patch"
TASK_FILTER = "terminal-bench/ico-path-patch"
TASK_CACHE_DIGEST = "0115a4136189b48da79070f9b3004dc4e0dfc1a60725c5acebdd7f380d037d14"
SESSION_WINDOW_TASK_NAME = "session-window-debug"
SESSION_WINDOW_TASK_CACHE_DIGEST = (
    "638c00fd438a0289ba75f6bc536861831f4a8eab2b85064064038e1bcc91cfbb"
)
BUN_SOURCEMAP_TASK_NAME = "bun-sourcemap-leak"
BUN_SOURCEMAP_TASK_CACHE_DIGEST = (
    "ac0b0f77da4e8f6c3904133033ec6d8591eb0d3f18205ab28104ea3cf2a5a07f"
)
MUSIC_HARMONY_TASK_NAME = "music-harmony"
MUSIC_HARMONY_TASK_CACHE_DIGEST = (
    "f5ba5ef9140c164e1c3654425caea7dc0f74423c9632f5e0c9a6dc9001d38f00"
)
DATA_ANONYMIZATION_TASK_NAME = "data-anonymization"
DATA_ANONYMIZATION_TASK_CACHE_DIGEST = (
    "2d463025deb8bcc4c860f8a8e90c799435306e566e6c36af4b0df6d18e10a290"
)
HEAT_PUMP_WARRANTY_TASK_NAME = "heat-pump-warranty"
HEAT_PUMP_WARRANTY_TASK_CACHE_DIGEST = (
    "195e39da0c97ea45552d216f04b204d438ec397e1003300be3edc064aa9859b6"
)
AGENT_IMPORT = "benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent"
AGENT_VERSION = "0.9.0"
CORRIDOR_SDK_VERSION = "0.6.0"
MODEL = "openai/gpt-5.6-sol"
REASONING_EFFORT = "max"
METHOD_VERSION_ID = "charting-loop-method-v8"
METHOD_SOURCE_COMMIT = "3c3813444a7d43d0a56837e9cb960be86ce26d06"
METHOD_SOURCE_PATH = "method-paper/METHOD.md"
METHOD_SCOPE_PATH = "method-paper/SCOPE-DATUM.md"
METHOD_CONTENT_SHA256 = (
    "sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446"
)
METHOD_SCOPE_SHA256 = (
    "sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af"
)
PHASE_ISOLATION_COMMIT = "9281e739f5bfa6ed78784c505f38831d8ff0f9e7"
MIN_HARBOR_VERSION = (0, 21, 0)


@dataclass(frozen=True)
class TaskSpec:
    name: str
    cache_digest: str
    agent_timeout_sec: float
    dockerfile_from: str
    requires_x86_64_binary: bool = False

    @property
    def task_filter(self) -> str:
        return f"terminal-bench/{self.name}"


TASK_SPECS = {
    TASK_NAME: TaskSpec(
        name=TASK_NAME,
        cache_digest=TASK_CACHE_DIGEST,
        agent_timeout_sec=5400.0,
        dockerfile_from="FROM python:3.12-slim",
        requires_x86_64_binary=True,
    ),
    SESSION_WINDOW_TASK_NAME: TaskSpec(
        name=SESSION_WINDOW_TASK_NAME,
        cache_digest=SESSION_WINDOW_TASK_CACHE_DIGEST,
        agent_timeout_sec=7200.0,
        dockerfile_from="FROM python:3.12-slim",
    ),
    BUN_SOURCEMAP_TASK_NAME: TaskSpec(
        name=BUN_SOURCEMAP_TASK_NAME,
        cache_digest=BUN_SOURCEMAP_TASK_CACHE_DIGEST,
        agent_timeout_sec=1800.0,
        dockerfile_from="FROM oven/bun:1.2.15-debian",
    ),
    MUSIC_HARMONY_TASK_NAME: TaskSpec(
        name=MUSIC_HARMONY_TASK_NAME,
        cache_digest=MUSIC_HARMONY_TASK_CACHE_DIGEST,
        agent_timeout_sec=7200.0,
        dockerfile_from="FROM python:3.11-slim",
    ),
    DATA_ANONYMIZATION_TASK_NAME: TaskSpec(
        name=DATA_ANONYMIZATION_TASK_NAME,
        cache_digest=DATA_ANONYMIZATION_TASK_CACHE_DIGEST,
        agent_timeout_sec=3600.0,
        dockerfile_from="FROM ubuntu:24.04 AS input-builder",
    ),
    HEAT_PUMP_WARRANTY_TASK_NAME: TaskSpec(
        name=HEAT_PUMP_WARRANTY_TASK_NAME,
        cache_digest=HEAT_PUMP_WARRANTY_TASK_CACHE_DIGEST,
        agent_timeout_sec=7200.0,
        dockerfile_from="FROM python:3.13-slim",
    ),
}


def _active_dockerfile_from_instructions(docker_text: str) -> tuple[str, ...]:
    """Return active, single-line Dockerfile FROM instructions."""

    instructions: list[str] = []
    for raw_line in docker_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        keyword, separator, _ = line.partition(" ")
        if separator and keyword.casefold() == "from":
            instructions.append(line)
    return tuple(instructions)

_SECRET_PATTERNS = (
    re.compile(r"sk-harbor-[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*[^\s,;}]+"
    ),
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner:
    """Small injectable subprocess boundary; commands are never run through a shell."""

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: int = 60,
    ) -> CommandResult:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            env=merged_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    summary: str
    details: Mapping[str, Any]
    repair: str | None = None


@dataclass(frozen=True)
class DoctorConfig:
    repo_root: Path
    job_name: str
    jobs_dir: Path
    modal_spend_limit_usd: Decimal
    task_name: str = TASK_NAME
    min_modal_headroom_usd: Decimal = Decimal("1.00")
    trusted_cyber_access_confirmed: bool = False
    expected_head: str | None = None
    force_auth_json: str | None = None
    task_cache_root: Path | None = None
    auth_path: Path | None = None
    harbor_executable: str | None = None
    harbor_python: str | None = None
    modal_executable: str | None = None
    codex_executable: str | None = None
    docker_executable: str | None = None
    file_executable: str | None = None
    git_executable: str | None = None


def _task_spec(config: DoctorConfig) -> TaskSpec | None:
    return TASK_SPECS.get(config.task_name)


def _task_filter(config: DoctorConfig) -> str:
    return f"terminal-bench/{config.task_name}"


def _scrub_text(value: str) -> str:
    cleaned = value
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, Mapping):
        return {str(key): _scrub(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha256(
    runner: Runner, git: str, repository_root: Path, commit: str, path: str
) -> str:
    """Hash the exact committed text blob instead of the mutable worktree path."""

    commit_check = runner.run(
        [git, "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repository_root
    )
    shown = runner.run([git, "show", f"{commit}:{path}"], cwd=repository_root)
    if commit_check.returncode or shown.returncode:
        raise RuntimeError(f"frozen Git blob unavailable: {commit}:{path}")
    return "sha256:" + hashlib.sha256(shown.stdout.encode("utf-8")).hexdigest()


def _tool(explicit: str | None, name: str) -> str | None:
    if explicit:
        return explicit
    return shutil.which(name)


def _harbor_python(harbor: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        first_line = Path(harbor).resolve().read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeDecodeError, IndexError):
        first_line = ""
    if first_line.startswith("#!"):
        candidate = Path(first_line[2:].strip().split()[0])
        if candidate.is_file():
            return str(candidate)
    candidate = Path.home() / ".local/share/uv/tools/harbor/bin/python"
    return str(candidate) if candidate.is_file() else None


def _parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _json(text: str) -> Any:
    return json.loads(text)


def _passed(
    check_id: str, summary: str, details: Mapping[str, Any] | None = None
) -> CheckResult:
    return CheckResult(check_id, True, summary, details or {})


def _failed(
    check_id: str,
    summary: str,
    repair: str,
    details: Mapping[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(check_id, False, summary, details or {}, repair)


def _check_tools(config: DoctorConfig) -> tuple[CheckResult, dict[str, str]]:
    names = {
        "git": _tool(config.git_executable, "git"),
        "harbor": _tool(config.harbor_executable, "harbor"),
        "modal": _tool(config.modal_executable, "modal"),
        "codex": _tool(config.codex_executable, "codex"),
        "docker": _tool(config.docker_executable, "docker"),
        "file": _tool(config.file_executable, "file"),
    }
    missing = sorted(name for name, path in names.items() if not path)
    if missing:
        return (
            _failed(
                "toolchain",
                "Required local tools are missing.",
                "Install the missing tools, then rerun the doctor.",
                {"missing": missing},
            ),
            {},
        )
    resolved = {name: str(path) for name, path in names.items() if path}
    harbor_python = _harbor_python(resolved["harbor"], config.harbor_python)
    if not harbor_python:
        return (
            _failed(
                "toolchain",
                "Harbor's Python runtime could not be resolved.",
                "Reinstall Harbor with uv tool install --upgrade 'harbor[modal]'.",
            ),
            {},
        )
    resolved["harbor_python"] = harbor_python
    return _passed("toolchain", "Required local tools are available."), resolved


def _check_git_and_method(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    git = tools["git"]
    status = runner.run([git, "status", "--porcelain"], cwd=config.repo_root)
    head = runner.run([git, "rev-parse", "HEAD"], cwd=config.repo_root)
    ancestor = runner.run(
        [git, "merge-base", "--is-ancestor", PHASE_ISOLATION_COMMIT, "HEAD"],
        cwd=config.repo_root,
    )
    if status.returncode or head.returncode or ancestor.returncode:
        return _failed(
            "immutable_inputs",
            "Git identity or the required isolation ancestor could not be proved.",
            "Use a clean commit descended from the CL-057 isolation commit.",
        )
    actual_head = head.stdout.strip()
    if status.stdout.strip():
        return _failed(
            "immutable_inputs",
            "The repository has uncommitted changes.",
            "Commit or remove the intended changes before a scored run.",
            {"head": actual_head, "worktree_clean": False},
        )
    if config.expected_head and actual_head != config.expected_head:
        return _failed(
            "immutable_inputs",
            "HEAD does not match the operator-pinned commit.",
            "Check out the pinned commit or update the declared condition.",
            {"head": actual_head, "expected_head": config.expected_head},
        )

    try:
        index = _json((config.repo_root / "method-paper/VERSIONS.json").read_text())
        record = next(
            item for item in index["versions"] if item["version_id"] == METHOD_VERSION_ID
        )
        method_digest = _git_blob_sha256(
            runner, git, config.repo_root, METHOD_SOURCE_COMMIT, METHOD_SOURCE_PATH
        )
        scope_digest = _git_blob_sha256(
            runner, git, config.repo_root, METHOD_SOURCE_COMMIT, METHOD_SCOPE_PATH
        )
        agent_source = (config.repo_root / "benchmark_agents/harbor_agent.py").read_text()
    except (OSError, RuntimeError, ValueError, KeyError, StopIteration, TypeError):
        return _failed(
            "immutable_inputs",
            "Frozen method or agent identity could not be read.",
            "Restore the versioned method index and agent source.",
        )
    expected_record = (
        record.get("status") == "frozen"
        and record.get("study_eligible") is True
        and record.get("adoption_eligible") is False
        and record.get("builder_eligible") is False
        and record.get("source_commit") == METHOD_SOURCE_COMMIT
        and record.get("path") == METHOD_SOURCE_PATH
        and record.get("content_sha256") == METHOD_CONTENT_SHA256
        and record.get("scope_datum_path") == METHOD_SCOPE_PATH
        and record.get("scope_datum_sha256") == METHOD_SCOPE_SHA256
    )
    agent_match = re.search(r'^AGENT_VERSION\s*=\s*"([^"]+)"', agent_source, re.MULTILINE)
    sdk_program = (
        "import json; from pathlib import Path; "
        "from corridor_kit import KIT_VERSION, regular_tree_manifest; "
        "manifest=regular_tree_manifest(Path('corridor_kit')); "
        "print(json.dumps({'kit_version':KIT_VERSION,'tree_digest':manifest['tree_digest'],"
        "'paths':[item['path'] for item in manifest['files']]},sort_keys=True))"
    )
    sdk_result = runner.run(
        [tools["harbor_python"], "-c", sdk_program],
        cwd=config.repo_root,
        env={"PYTHONPATH": str(config.repo_root)},
    )
    try:
        sdk_identity = _json(sdk_result.stdout)
    except (ValueError, TypeError):
        sdk_identity = {}
    sdk_paths = set(sdk_identity.get("paths", []))
    required_sdk_paths = {
        "__main__.py",
        "acceptance.py",
        "authoring.py",
        "capabilities.py",
        "core.py",
        "domain/binary.py",
        "runtime.py",
        "scaffold.py",
        "submission.py",
    }
    sdk_exact = (
        sdk_result.returncode == 0
        and sdk_identity.get("kit_version") == CORRIDOR_SDK_VERSION
        and isinstance(sdk_identity.get("tree_digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", sdk_identity["tree_digest"])
        is not None
        and required_sdk_paths.issubset(sdk_paths)
    )
    if (
        not expected_record
        or method_digest != METHOD_CONTENT_SHA256
        or scope_digest != METHOD_SCOPE_SHA256
        or not agent_match
        or agent_match.group(1) != AGENT_VERSION
        or not sdk_exact
    ):
        return _failed(
            "immutable_inputs",
            "Frozen method or agent bytes do not match the declared condition.",
            "Restore the frozen v8 method, Agent v0.9.0, and Corridor SDK v0.5.0 before running.",
            {
                "head": actual_head,
                "method_version_id": METHOD_VERSION_ID,
                "corridor_sdk_version": sdk_identity.get("kit_version"),
            },
        )
    return _passed(
        "immutable_inputs",
        "Git, method, agent, and timeout-isolation identities are exact.",
        {
            "head": actual_head,
            "worktree_clean": True,
            "method_version_id": METHOD_VERSION_ID,
            "method_sha256": method_digest,
            "scope_datum_sha256": scope_digest,
            "agent_version": AGENT_VERSION,
            "corridor_sdk_version": CORRIDOR_SDK_VERSION,
            "corridor_sdk_tree_digest": sdk_identity["tree_digest"],
            "isolation_ancestor": PHASE_ISOLATION_COMMIT,
        },
    )


_HARBOR_USER_PROGRAM = """import asyncio,json
from harbor.auth.client import create_authenticated_client,require_user_id
async def main():
    user_id=await require_user_id()
    client=await create_authenticated_client()
    response=await client.table("user").select("id,github_username,display_name").eq("id",user_id).maybe_single().execute()
    row=response.data or {}
    print(json.dumps({"record_found":bool(row),"github_username_claimed":bool(row.get("github_username")),"display_name_present":bool(row.get("display_name"))},sort_keys=True))
asyncio.run(main())
"""


def _check_harbor(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    harbor = tools["harbor"]
    version = runner.run([harbor, "--version"], cwd=config.repo_root)
    parsed = _parse_version(version.stdout) if version.returncode == 0 else None
    dataset = runner.run(
        [harbor, "version", "show", DATASET, "--json"], cwd=config.repo_root
    )
    auth = runner.run([harbor, "auth", "status"], cwd=config.repo_root)
    identity = runner.run(
        [tools["harbor_python"], "-c", _HARBOR_USER_PROGRAM], cwd=config.repo_root
    )
    try:
        dataset_data = _json(dataset.stdout)
        identity_data = _json(identity.stdout)
    except (ValueError, TypeError):
        dataset_data = {}
        identity_data = {}
    version_ok = parsed is not None and parsed >= MIN_HARBOR_VERSION
    dataset_ok = (
        dataset.returncode == 0
        and dataset_data.get("package") == DATASET_NAME
        and DATASET_REF in dataset_data.get("tags", [])
        and dataset_data.get("content_hash") == DATASET_CONTENT_SHA256
    )
    auth_ok = auth.returncode == 0 and "logged in" in auth.stdout.lower()
    identity_ok = (
        identity.returncode == 0
        and identity_data.get("record_found") is True
        and identity_data.get("github_username_claimed") is True
    )
    if not (version_ok and dataset_ok and auth_ok and identity_ok):
        return _failed(
            "harbor_account",
            "Harbor version, dataset identity, login, or upload identity is incomplete.",
            "Use Harbor >=0.21.0, log in, claim a GitHub username on Harbor Hub, and retry.",
            {
                "version_ok": version_ok,
                "dataset_identity_ok": dataset_ok,
                "authenticated": auth_ok,
                "user_record_found": identity_data.get("record_found") is True,
                "github_username_claimed": identity_data.get("github_username_claimed")
                is True,
            },
        )
    return _passed(
        "harbor_account",
        "Harbor can resolve the frozen dataset and the account has an upload identity.",
        {
            "version": ".".join(str(part) for part in parsed),
            "dataset_content_sha256": DATASET_CONTENT_SHA256,
            "authenticated": True,
            "github_username_claimed": True,
        },
    )


def _sum_costs(value: Any) -> Decimal:
    if isinstance(value, list):
        return sum((_sum_costs(item) for item in value), Decimal("0"))
    if isinstance(value, Mapping):
        total = Decimal("0")
        for key, item in value.items():
            if key == "cost" and isinstance(item, (str, int, float)):
                total += Decimal(str(item))
            else:
                total += _sum_costs(item)
        return total
    return Decimal("0")


def _check_modal(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    modal = tools["modal"]
    profile = runner.run([modal, "profile", "current"], cwd=config.repo_root)
    billing = runner.run(
        [modal, "billing", "report", "--for", "this month", "--json"],
        cwd=config.repo_root,
    )
    try:
        spent = _sum_costs(_json(billing.stdout))
    except (ValueError, InvalidOperation, TypeError):
        spent = Decimal("-1")
    headroom = config.modal_spend_limit_usd - spent
    ok = (
        profile.returncode == 0
        and bool(profile.stdout.strip())
        and billing.returncode == 0
        and spent >= 0
        and headroom >= config.min_modal_headroom_usd
    )
    details = {
        "profile_present": profile.returncode == 0 and bool(profile.stdout.strip()),
        "billing_api_readable": billing.returncode == 0 and spent >= 0,
        "current_cycle_spend_usd": str(spent) if spent >= 0 else "unavailable",
        "operator_declared_spend_limit_usd": str(config.modal_spend_limit_usd),
        "computed_headroom_usd": str(headroom) if spent >= 0 else "unavailable",
        "required_headroom_usd": str(config.min_modal_headroom_usd),
        "limit_source": "operator_attestation",
    }
    if not ok:
        return _failed(
            "modal_billing",
            "Modal profile, billing access, or declared spend headroom is insufficient.",
            "Authenticate Modal and declare a dashboard spend cap with enough headroom.",
            details,
        )
    return _passed(
        "modal_billing",
        "Modal billing is readable and declared headroom meets the floor.",
        details,
    )


def _check_codex(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    login = runner.run([tools["codex"], "login", "status"], cwd=config.repo_root)
    auth_path = config.auth_path or (Path.home() / ".codex/auth.json")
    # Codex CLI versions have emitted status on either stdout or stderr.  Inspect
    # both locally, but project only the boolean into the copy-safe report.
    login_status = f"{login.stdout}\n{login.stderr}".lower()
    logged_in = login.returncode == 0 and "logged in" in login_status
    auth_present = auth_path.is_file()
    force_auth = config.force_auth_json == "1"
    trusted = config.trusted_cyber_access_confirmed
    details = {
        "logged_in": logged_in,
        "auth_file_present": auth_present,
        "force_auth_json_enabled": force_auth,
        "trusted_cyber_access_attested": trusted,
    }
    if not all(details.values()):
        return _failed(
            "codex_access",
            "Codex login, ephemeral auth handoff, or Trusted Cyber Access is unproved.",
            "Log in, export CODEX_FORCE_AUTH_JSON=1, complete Trusted Access verification, and pass --trusted-cyber-access-confirmed.",
            details,
        )
    return _passed(
        "codex_access",
        "Codex subscription auth and Trusted Cyber Access are explicitly present.",
        details,
    )


def _print_config_command(
    config: DoctorConfig, harbor: str
) -> list[str]:
    return [
        harbor,
        "run",
        "--print-config",
        "--job-name",
        config.job_name,
        "-o",
        str(config.jobs_dir),
        "-d",
        DATASET,
        "-i",
        _task_filter(config),
        "--n-tasks",
        "1",
        "-e",
        "modal",
        "-a",
        AGENT_IMPORT,
        "-m",
        MODEL,
        "--ak",
        f"reasoning_effort={REASONING_EFFORT}",
        "-n",
        "1",
        "--max-retries",
        "0",
        "--upload",
        "--private",
    ]


def _check_resolved_config(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    env = {
        "CHARTING_LOOP_ROOT": str(config.repo_root),
        "PYTHONPATH": str(config.repo_root),
        "CODEX_FORCE_AUTH_JSON": "1",
    }
    resolved = runner.run(
        _print_config_command(config, tools["harbor"]),
        cwd=config.repo_root,
        env=env,
        timeout=120,
    )
    try:
        data = _json(resolved.stdout)
        agent = data["agents"][0]
        dataset = data["datasets"][0]
        exact = (
            resolved.returncode == 0
            and data.get("job_name") == config.job_name
            and Path(data.get("jobs_dir", "")).resolve() == config.jobs_dir.resolve()
            and data.get("n_concurrent_trials") == 1
            and data.get("environment", {}).get("type") == "modal"
            and len(data.get("agents", [])) == 1
            and agent.get("name") == AGENT_IMPORT
            and agent.get("model_name") == MODEL
            and agent.get("kwargs") == {"reasoning_effort": REASONING_EFFORT}
            and len(data.get("datasets", [])) == 1
            and dataset.get("name") == DATASET_NAME
            and dataset.get("ref") == DATASET_REF
            and _task_spec(config) is not None
            and dataset.get("task_names") == [_task_filter(config)]
            and dataset.get("n_tasks") == 1
        )
    except (ValueError, KeyError, IndexError, TypeError, OSError):
        exact = False
    policy = {
        "task": config.task_name,
        "task_filter": _task_filter(config),
        "n_tasks": 1,
        "concurrency": 1,
        "max_retries": 0,
        "upload_visibility": "private",
        "environment": "modal",
        "agent": AGENT_IMPORT,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
    }
    if not exact:
        return _failed(
            "resolved_run_config",
            "Harbor did not resolve the exact single-task private-run condition.",
            "Do not run; restore the documented task, agent, model, Modal, and retry policy.",
            policy,
        )
    return _passed(
        "resolved_run_config",
        "Harbor resolved the exact one-task, private, zero-retry condition.",
        policy,
    )


def _default_task_cache(config: DoctorConfig) -> Path | None:
    spec = _task_spec(config)
    if spec is None:
        return None
    return (
        Path.home()
        / ".cache/harbor/tasks/packages/terminal-bench"
        / spec.name
        / spec.cache_digest
    )


def _check_task_architecture(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    spec = _task_spec(config)
    if spec is None:
        return _failed(
            "task_architecture",
            "The requested task has no pinned doctor identity.",
            "Choose one of the doctor-supported canonical task names.",
            {"task": config.task_name, "supported_tasks": sorted(TASK_SPECS)},
        )
    root = config.task_cache_root or _default_task_cache(config)
    assert root is not None
    task_toml = root / "task.toml"
    dockerfile = root / "environment/Dockerfile"
    binary = root / "environment/ico/ico"
    try:
        task_data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
        docker_text = dockerfile.read_text(encoding="utf-8")
    except (OSError, tomllib.TOMLDecodeError):
        return _failed(
            "task_architecture",
            "The exact cached task bytes are unavailable.",
            "Run the doctor again after Harbor resolves the pinned task cache.",
            {"task": spec.name, "task_cache_digest": spec.cache_digest},
        )
    digest_program = (
        "import sys;"
        "from pathlib import Path;"
        "from harbor.publisher.packager import Packager;"
        "print(Packager.compute_content_hash(Path(sys.argv[1]))[0])"
    )
    digest_result = runner.run(
        [tools["harbor_python"], "-c", digest_program, str(root)],
        cwd=config.repo_root,
    )
    file_result = (
        runner.run([tools["file"], str(binary)], cwd=config.repo_root)
        if spec.requires_x86_64_binary
        else None
    )
    cache_exact = (
        digest_result.returncode == 0
        and digest_result.stdout.strip() == spec.cache_digest
    )
    task_section = task_data.get("task", {})
    agent_section = task_data.get("agent", {})
    environment_section = task_data.get("environment", {})
    task_ok = (
        task_section.get("name") == spec.task_filter
        and agent_section.get("timeout_sec") == spec.agent_timeout_sec
        and environment_section.get("gpus", 0) == 0
    )
    image_ok = spec.dockerfile_from in _active_dockerfile_from_instructions(
        docker_text
    )
    amd64 = not spec.requires_x86_64_binary or (
        file_result is not None
        and file_result.returncode == 0
        and "ELF 64-bit" in file_result.stdout
        and "x86-64" in file_result.stdout
    )
    if not (cache_exact and task_ok and image_ok and amd64):
        return _failed(
            "task_architecture",
            "The pinned task cache or execution identity is not exact.",
            "Restore the selected canonical task cache; use Modal amd64 when the task contains an x86-64 binary.",
            {
                "task": spec.name,
                "task_filter": spec.task_filter,
                "task_cache_digest": spec.cache_digest,
                "task_tree_digest_exact": cache_exact,
                "task_manifest_exact": task_ok,
                "base_image_exact": image_ok,
                "expected_base_image": spec.dockerfile_from,
                "x86_64_binary_required": spec.requires_x86_64_binary,
                "binary_is_x86_64": amd64 if spec.requires_x86_64_binary else None,
            },
        )
    return _passed(
        "task_architecture",
        "The exact selected task cache and execution identity are pinned.",
        {
            "task": spec.name,
            "task_filter": spec.task_filter,
            "task_cache_digest": spec.cache_digest,
            "task_tree_digest_exact": True,
            "base_image": spec.dockerfile_from,
            "binary_architecture": (
                "x86-64" if spec.requires_x86_64_binary else "not_task_constrained"
            ),
            "execution_environment": "modal-amd64",
        },
    )


def _check_output_identity(config: DoctorConfig) -> CheckResult:
    target = config.jobs_dir / config.job_name
    if target.exists():
        return _failed(
            "output_identity",
            "The planned job output already exists.",
            "Choose a new job name; never overwrite or append to an earlier result.",
            {"job_name": config.job_name, "target_exists": True},
        )
    probe_parent = config.jobs_dir.resolve()
    while not probe_parent.exists() and probe_parent != probe_parent.parent:
        probe_parent = probe_parent.parent
    try:
        with tempfile.NamedTemporaryFile(prefix=".charting-loop-doctor-", dir=probe_parent):
            pass
    except OSError:
        return _failed(
            "output_identity",
            "The planned output parent is not writable.",
            "Choose a new writable jobs directory.",
            {"job_name": config.job_name, "target_exists": False},
        )
    return _passed(
        "output_identity",
        "The job identity is unused and its output parent is writable.",
        {"job_name": config.job_name, "target_exists": False},
    )


def _phase_harness(
    probe_b64: str,
    discovery_b64: str,
    binding_b64: str,
    phase_env_b64: str,
    token: str,
) -> str:
    child = (
        "import signal,time;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "time.sleep(120)"
    )
    return f"""import base64,hashlib,json,os,subprocess,sys,time
from pathlib import Path
token={token!r}
probe=base64.b64decode({probe_b64!r}).decode()
discovery=base64.b64decode({discovery_b64!r}).decode()
binding=base64.b64decode({binding_b64!r}).decode()
phase_env=base64.b64decode({phase_env_b64!r}).decode()
runtime_home=Path("/tmp/charting-loop-doctor-home")
nvm_bin=runtime_home/".nvm/versions/node/v22.17.0/bin"
nvm_bin.mkdir(parents=True,exist_ok=True)
(nvm_bin/"node").write_text("#!/bin/sh\\nexit 0\\n")
(nvm_bin/"codex").write_text("#!/bin/sh\\necho codex-cli-doctor\\n")
(nvm_bin/"node").chmod(0o755)
(nvm_bin/"codex").chmod(0o755)
(runtime_home/".nvm/nvm.sh").write_text(f'PATH="{{nvm_bin}}:$PATH"; export PATH\\n')
discovered=subprocess.run(["sh","-c",discovery],text=True,capture_output=True,timeout=15,env={{**os.environ,"HOME":str(runtime_home),"PATH":"/usr/bin:/bin"}})
discovered_paths=[line.strip() for line in discovered.stdout.splitlines() if line.strip()]
runtime_discovered=discovered.returncode==0 and discovered_paths==[str(nvm_bin/"node"),str(nvm_bin/"codex")]
bound=subprocess.run(["sh","-c",binding],text=True,capture_output=True,timeout=15)
fresh=subprocess.run(["sh","-c","PATH=/tmp/charting-loop-doctor-bin:/usr/bin:/bin; command -v node >/dev/null && command -v codex >/dev/null && codex --version"],text=True,capture_output=True,timeout=15)
codex_runtime_bound=runtime_discovered and bound.returncode==0 and fresh.returncode==0 and "codex-cli-doctor" in fresh.stdout
frozen=Path("/tmp/charting-loop-doctor-corridor")
frozen.mkdir(parents=True,exist_ok=True)
(frozen/"task_adapter.py").write_text("VALUE = 1\\n")
(frozen/"task_adapter.py").chmod(0o444)
frozen.chmod(0o555)
def frozen_tree():
    return [(p.relative_to(frozen).as_posix(),hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(frozen.rglob("*")) if p.is_file()]
frozen_before=frozen_tree()
adapter_import=subprocess.run(["sh","-c",phase_env+"; PYTHONPATH=/tmp/charting-loop-doctor-corridor python3 -c 'import task_adapter; assert task_adapter.VALUE == 1'"],text=True,capture_output=True,timeout=15)
frozen_after=frozen_tree()
frozen_corridor_unchanged=adapter_import.returncode==0 and frozen_before==frozen_after and not any(p.name=="__pycache__" or p.suffix==".pyc" for p in frozen.rglob("*"))
pid=os.fork()
if pid==0:
    os.setsid()
    env=os.environ.copy()
    env["CHARTING_LOOP_PHASE_TOKEN"]=token
    os.execve(sys.executable,[sys.executable,"-c",{child!r}],env)
time.sleep(0.25)
completed=subprocess.run([sys.executable,"-c",probe],text=True,capture_output=True,timeout=15)
try:
    os.waitpid(pid,0)
except ChildProcessError:
    pass
data=json.loads(completed.stdout)
observed=pid in data.get("initial_pids",[]) and pid in (data.get("term_signal_pids",[])+data.get("kill_signal_pids",[]))
print(json.dumps({{"probe_returncode":completed.returncode,"child_observed":observed,"quiescent":data.get("quiescent") is True,"remaining_count":len(data.get("remaining_pids",[])),"codex_runtime_bound":codex_runtime_bound,"frozen_corridor_unchanged":frozen_corridor_unchanged}},sort_keys=True))
"""


def _check_phase_isolation(
    config: DoctorConfig, runner: Runner, tools: Mapping[str, str]
) -> CheckResult:
    image = runner.run(
        [tools["docker"], "image", "inspect", "python:3.12-slim"],
        cwd=config.repo_root,
    )
    if image.returncode != 0:
        return _failed(
            "phase_isolation",
            "The local Linux self-test image is unavailable; no pull was attempted.",
            "Pull python:3.12-slim explicitly, inspect it, then rerun the doctor.",
            {"paid_actions_started": False},
        )
    token = "doctor-" + uuid.uuid4().hex
    export_program = (
        "import base64,json;"
        "from benchmark_agents.harbor_agent import "
        "PHASE_NO_BYTECODE_EXPORT,_codex_runtime_binding_command,_codex_runtime_discovery_command,_phase_quiescence_program;"
        "payload={"
        f"'probe_b64':base64.b64encode(_phase_quiescence_program({token!r},terminate=True).encode()).decode(),"
        "'discovery_b64':base64.b64encode(_codex_runtime_discovery_command().encode()).decode(),"
        "'binding_b64':base64.b64encode(_codex_runtime_binding_command("
        "node_bin='/tmp/charting-loop-doctor-home/.nvm/versions/node/v22.17.0/bin/node',"
        "codex_bin='/tmp/charting-loop-doctor-home/.nvm/versions/node/v22.17.0/bin/codex',"
        "stable_bin_dir='/tmp/charting-loop-doctor-bin').encode()).decode(),"
        "'phase_env_b64':base64.b64encode(PHASE_NO_BYTECODE_EXPORT.encode()).decode()};"
        "print(json.dumps(payload,sort_keys=True))"
    )
    exported = runner.run(
        [tools["harbor_python"], "-c", export_program],
        cwd=config.repo_root,
        env={"PYTHONPATH": str(config.repo_root)},
    )
    if exported.returncode != 0:
        return _failed(
            "phase_isolation",
            "The committed CL-057 quiescence program could not be imported.",
            "Restore the committed Harbor adapter and rerun its unit tests.",
        )
    try:
        exported_programs = _json(exported.stdout)
        probe_b64 = exported_programs["probe_b64"]
        discovery_b64 = exported_programs["discovery_b64"]
        binding_b64 = exported_programs["binding_b64"]
        phase_env_b64 = exported_programs["phase_env_b64"]
        base64.b64decode(probe_b64, validate=True)
        base64.b64decode(discovery_b64, validate=True)
        base64.b64decode(binding_b64, validate=True)
        base64.b64decode(phase_env_b64, validate=True)
    except (ValueError, KeyError, TypeError):
        return _failed(
            "phase_isolation",
            "The CL-057/CL-061 runtime program export was invalid.",
            "Restore the committed Harbor adapter and rerun its unit tests.",
        )
    harness = _phase_harness(
        probe_b64, discovery_b64, binding_b64, phase_env_b64, token
    )
    exercised = runner.run(
        [tools["docker"], "run", "--rm", "python:3.12-slim", "python3", "-c", harness],
        cwd=config.repo_root,
        timeout=30,
    )
    try:
        result = _json(exercised.stdout)
    except (ValueError, TypeError):
        result = {}
    passed = (
        exercised.returncode == 0
        and result.get("probe_returncode") == 0
        and result.get("child_observed") is True
        and result.get("quiescent") is True
        and result.get("remaining_count") == 0
        and result.get("codex_runtime_bound") is True
        and result.get("frozen_corridor_unchanged") is True
    )
    if not passed:
        return _failed(
            "phase_isolation",
            "The phase cleanup, fresh-shell Codex runtime, or frozen-Corridor bytecode self-test did not pass.",
            "Do not start a paid run; repair phase isolation, runtime binding, or root-phase bytecode suppression and rerun the full tests.",
            {
                "child_observed": result.get("child_observed") is True,
                "quiescent": result.get("quiescent") is True,
                "codex_runtime_bound": result.get("codex_runtime_bound") is True,
                "frozen_corridor_unchanged": result.get("frozen_corridor_unchanged")
                is True,
            },
        )
    return _passed(
        "phase_isolation",
        "The Linux self-test proved phase quiescence, fresh-shell Codex availability, and frozen-Corridor byte identity.",
        {
            "child_observed": True,
            "quiescent": True,
            "remaining_count": 0,
            "codex_runtime_bound": True,
            "frozen_corridor_unchanged": True,
        },
    )


def run_doctor(config: DoctorConfig, runner: Runner | None = None) -> dict[str, Any]:
    """Run every non-paid check and return a secret-scrubbed report."""

    runner = runner or Runner()
    checks: list[CheckResult] = []
    tool_check, tools = _check_tools(config)
    checks.append(tool_check)
    if tools:
        check_functions = (
            _check_git_and_method,
            _check_harbor,
            _check_modal,
            _check_codex,
            _check_resolved_config,
            _check_task_architecture,
        )
        for function in check_functions:
            try:
                checks.append(function(config, runner, tools))
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                checks.append(
                    _failed(
                        function.__name__.removeprefix("_check_"),
                        "The check ended with a local internal error.",
                        "Inspect the local tool installation; no benchmark action was started.",
                    )
                )
        checks.append(_check_output_identity(config))
        try:
            checks.append(_check_phase_isolation(config, runner, tools))
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            checks.append(
                _failed(
                    "phase_isolation",
                    "The isolation self-test ended with a local internal error.",
                    "Do not start a paid run; inspect Docker and the Harbor adapter.",
                )
            )
    report = {
        "schema_version": SCHEMA_VERSION,
        "ready": bool(checks) and all(check.passed for check in checks),
        "paid_actions_started": False,
        "condition": {
            "dataset": DATASET,
            "dataset_content_sha256": DATASET_CONTENT_SHA256,
            "task": config.task_name,
            "task_filter": _task_filter(config),
            "task_cache_digest": (
                _task_spec(config).cache_digest if _task_spec(config) else "unregistered"
            ),
            "agent": AGENT_IMPORT,
            "agent_version": AGENT_VERSION,
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "method_version_id": METHOD_VERSION_ID,
            "corridor_sdk_version": CORRIDOR_SDK_VERSION,
            "job_name": config.job_name,
            "max_retries": 0,
            "upload_visibility": "private",
        },
        "checks": [asdict(check) for check in checks],
    }
    return _scrub(report)


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("expected a decimal amount") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("amount must be non-negative")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--job-name", required=True)
    parser.add_argument(
        "--task",
        choices=sorted(TASK_SPECS),
        default=TASK_NAME,
        help="Pinned bare task name; the doctor constructs terminal-bench/<task>.",
    )
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument("--expected-head")
    parser.add_argument(
        "--modal-spend-limit-usd",
        type=_decimal,
        default=os.environ.get("CHARTING_LOOP_MODAL_SPEND_LIMIT_USD"),
        help="Operator-declared Modal dashboard spend cap (or CHARTING_LOOP_MODAL_SPEND_LIMIT_USD).",
    )
    parser.add_argument(
        "--min-modal-headroom-usd", type=_decimal, default=Decimal("1.00")
    )
    parser.add_argument("--trusted-cyber-access-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.modal_spend_limit_usd is None:
        parser.error(
            "--modal-spend-limit-usd or CHARTING_LOOP_MODAL_SPEND_LIMIT_USD is required"
        )
    repo_root = args.repo_root.resolve()
    jobs_dir = args.jobs_dir
    if not jobs_dir.is_absolute():
        jobs_dir = repo_root / jobs_dir
    config = DoctorConfig(
        repo_root=repo_root,
        job_name=args.job_name,
        jobs_dir=jobs_dir,
        modal_spend_limit_usd=args.modal_spend_limit_usd,
        task_name=args.task,
        min_modal_headroom_usd=args.min_modal_headroom_usd,
        trusted_cyber_access_confirmed=args.trusted_cyber_access_confirmed,
        expected_head=args.expected_head,
        force_auth_json=os.environ.get("CODEX_FORCE_AUTH_JSON"),
    )
    try:
        report = run_doctor(config)
    except Exception as exc:  # Last-resort CLI boundary; never serialize command output.
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "ready": False,
                    "paid_actions_started": False,
                    "error": f"internal error ({type(exc).__name__})",
                },
                sort_keys=True,
            )
        )
        return 3
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        status = "READY" if report["ready"] else "NOT READY"
        print(f"Terminal-Bench doctor: {status} (no paid actions started)")
        for check in report["checks"]:
            marker = "PASS" if check["passed"] else "FAIL"
            print(f"[{marker}] {check['check_id']}: {check['summary']}")
            if check.get("repair"):
                print(f"       Repair: {check['repair']}")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
