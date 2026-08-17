from __future__ import annotations

import base64
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tools.terminal_bench_doctor import (
    DATASET_CONTENT_SHA256,
    DoctorConfig,
    CommandResult,
    PHASE_ISOLATION_COMMIT,
    TASK_CACHE_DIGEST,
    TASK_FILTER,
    run_doctor,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeRunner:
    def __init__(
        self,
        *,
        job_name: str,
        jobs_dir: Path,
        username_claimed: bool = True,
        resolved_task: str = TASK_FILTER,
        docker_quiescent: bool = True,
        codex_runtime_bound: bool = True,
    ) -> None:
        self.job_name = job_name
        self.jobs_dir = jobs_dir
        self.username_claimed = username_claimed
        self.resolved_task = resolved_task
        self.docker_quiescent = docker_quiescent
        self.codex_runtime_bound = codex_runtime_bound
        self.calls: list[list[str]] = []

    def run(self, args, *, cwd=None, env=None, timeout=60):
        command = list(args)
        self.calls.append(command)
        executable = command[0]
        if executable == "fake-git":
            if command[1:3] == ["status", "--porcelain"]:
                return CommandResult(0, "")
            if command[1:3] == ["rev-parse", "HEAD"]:
                return CommandResult(0, "f" * 40 + "\n")
            if command[1:3] == ["merge-base", "--is-ancestor"]:
                self.assert_isolation_commit(command)
                return CommandResult(0, "")
        if executable == "fake-harbor":
            if command[1:] == ["--version"]:
                return CommandResult(0, "0.21.0\n")
            if command[1:4] == ["version", "show", "terminal-bench/terminal-bench@3.0.0"]:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "package": "terminal-bench/terminal-bench",
                            "tags": ["3.0.0", "latest"],
                            "content_hash": DATASET_CONTENT_SHA256,
                        }
                    ),
                )
            if command[1:3] == ["auth", "status"]:
                return CommandResult(
                    0, "Logged in as test (API key sk-harbor-DO-NOT-REPORT)\n"
                )
            if command[1:3] == ["run", "--print-config"]:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "job_name": self.job_name,
                            "jobs_dir": str(self.jobs_dir),
                            "n_concurrent_trials": 1,
                            "environment": {"type": "modal"},
                            "agents": [
                                {
                                    "name": "benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent",
                                    "model_name": "openai/gpt-5.6-sol",
                                    "kwargs": {"reasoning_effort": "max"},
                                }
                            ],
                            "datasets": [
                                {
                                    "name": "terminal-bench/terminal-bench",
                                    "ref": "3.0.0",
                                    "task_names": [self.resolved_task],
                                    "n_tasks": 1,
                                }
                            ],
                        }
                    ),
                )
        if executable == "fake-harbor-python":
            program = command[-1]
            if "Packager.compute_content_hash" in command[-2]:
                return CommandResult(0, TASK_CACHE_DIGEST + "\n")
            if "github_username_claimed" in program:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "record_found": True,
                            "github_username_claimed": self.username_claimed,
                            "display_name_present": True,
                        }
                    ),
                )
            if "_phase_quiescence_program" in program:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "probe_b64": base64.b64encode(b"print('{}')").decode(),
                            "discovery_b64": base64.b64encode(b"true").decode(),
                            "binding_b64": base64.b64encode(b"true").decode(),
                        }
                    )
                    + "\n",
                )
        if executable == "fake-modal":
            if command[1:3] == ["profile", "current"]:
                return CommandResult(0, "test-workspace\n")
            if command[1:3] == ["billing", "report"]:
                return CommandResult(
                    0,
                    json.dumps(
                        [
                            {"cost": "0.30", "token": "eyJhidden.payload.sig"},
                            {"cost": "0.70"},
                        ]
                    ),
                )
        if executable == "fake-codex" and command[1:] == ["login", "status"]:
            return CommandResult(0, "", "Logged in using ChatGPT\n")
        if executable == "fake-file":
            return CommandResult(
                0,
                f"{command[-1]}: ELF 64-bit LSB executable, x86-64, stripped\n",
            )
        if executable == "fake-docker":
            if command[1:3] == ["image", "inspect"]:
                return CommandResult(0, "[]")
            if command[1:3] == ["run", "--rm"]:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "probe_returncode": 0,
                            "child_observed": self.docker_quiescent,
                            "quiescent": self.docker_quiescent,
                            "remaining_count": 0 if self.docker_quiescent else 1,
                            "codex_runtime_bound": self.codex_runtime_bound,
                        }
                    ),
                )
        return CommandResult(127, "", "unexpected fake command")

    def assert_isolation_commit(self, command: list[str]) -> None:
        if PHASE_ISOLATION_COMMIT not in command:
            raise AssertionError("doctor did not bind the CL-057 isolation commit")


class TerminalBenchDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.jobs_dir = self.root / "jobs"
        self.jobs_dir.mkdir()
        self.task_cache = self.root / TASK_CACHE_DIGEST
        (self.task_cache / "environment/ico").mkdir(parents=True)
        (self.task_cache / "task.toml").write_text(
            '\n'.join(
                [
                    '[task]',
                    'name = "terminal-bench/ico-path-patch"',
                    '[agent]',
                    'timeout_sec = 5400.0',
                    '[environment]',
                    'gpus = 0',
                ]
            ),
            encoding="utf-8",
        )
        (self.task_cache / "environment/Dockerfile").write_text(
            "FROM python:3.12-slim\n", encoding="utf-8"
        )
        (self.task_cache / "environment/ico/ico").write_bytes(b"ELF fixture")
        self.auth_path = self.root / "auth.json"
        self.auth_path.write_text("{}", encoding="utf-8")

    def config(
        self,
        *,
        job_name: str = "doctor-test-001",
        spend_limit: str = "10.00",
        trusted: bool = True,
    ) -> DoctorConfig:
        return DoctorConfig(
            repo_root=REPO_ROOT,
            job_name=job_name,
            jobs_dir=self.jobs_dir,
            modal_spend_limit_usd=Decimal(spend_limit),
            min_modal_headroom_usd=Decimal("1.00"),
            trusted_cyber_access_confirmed=trusted,
            force_auth_json="1",
            task_cache_root=self.task_cache,
            auth_path=self.auth_path,
            harbor_executable="fake-harbor",
            harbor_python="fake-harbor-python",
            modal_executable="fake-modal",
            codex_executable="fake-codex",
            docker_executable="fake-docker",
            file_executable="fake-file",
            git_executable="fake-git",
        )

    def run_fake(self, config: DoctorConfig, **runner_options):
        runner = FakeRunner(
            job_name=config.job_name,
            jobs_dir=config.jobs_dir,
            **runner_options,
        )
        return run_doctor(config, runner), runner

    def test_ready_report_binds_exact_non_paid_condition(self) -> None:
        report, runner = self.run_fake(self.config())

        self.assertTrue(report["ready"])
        self.assertFalse(report["paid_actions_started"])
        self.assertEqual(report["condition"]["task"], "ico-path-patch")
        self.assertEqual(report["condition"]["task_filter"], TASK_FILTER)
        self.assertEqual(report["condition"]["max_retries"], 0)
        self.assertEqual(report["condition"]["upload_visibility"], "private")
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        print_calls = [
            call
            for call in runner.calls
            if call[:3] == ["fake-harbor", "run", "--print-config"]
        ]
        self.assertEqual(len(print_calls), 1)
        command = print_calls[0]
        self.assertIn("--max-retries", command)
        self.assertEqual(command[command.index("--max-retries") + 1], "0")
        self.assertIn("--private", command)
        self.assertIn("-i", command)
        self.assertEqual(command[command.index("-i") + 1], TASK_FILTER)

    def test_unclaimed_harbor_username_fails_closed(self) -> None:
        report, _ = self.run_fake(self.config(), username_claimed=False)

        self.assertFalse(report["ready"])
        harbor = next(
            check for check in report["checks"] if check["check_id"] == "harbor_account"
        )
        self.assertFalse(harbor["passed"])
        self.assertFalse(harbor["details"]["github_username_claimed"])
        self.assertIn("claim a GitHub username", harbor["repair"])

    def test_headroom_trusted_access_and_output_collision_each_fail(self) -> None:
        config = self.config(spend_limit="1.25", trusted=False)
        (config.jobs_dir / config.job_name).mkdir()

        report, _ = self.run_fake(config)

        self.assertFalse(report["ready"])
        failed = {
            check["check_id"]
            for check in report["checks"]
            if not check["passed"]
        }
        self.assertTrue(
            {"modal_billing", "codex_access", "output_identity"}.issubset(failed)
        )

    def test_resolved_task_drift_fails_without_starting_a_trial(self) -> None:
        report, runner = self.run_fake(
            self.config(), resolved_task="some-other-task"
        )

        self.assertFalse(report["ready"])
        resolved = next(
            check
            for check in report["checks"]
            if check["check_id"] == "resolved_run_config"
        )
        self.assertFalse(resolved["passed"])
        harbor_run_calls = [
            call for call in runner.calls if call[:2] == ["fake-harbor", "run"]
        ]
        self.assertTrue(harbor_run_calls)
        self.assertTrue(all("--print-config" in call for call in harbor_run_calls))

    def test_isolation_self_test_failure_blocks_readiness(self) -> None:
        report, _ = self.run_fake(self.config(), docker_quiescent=False)

        isolation = next(
            check
            for check in report["checks"]
            if check["check_id"] == "phase_isolation"
        )
        self.assertFalse(report["ready"])
        self.assertFalse(isolation["passed"])

    def test_codex_runtime_binding_failure_blocks_readiness(self) -> None:
        report, _ = self.run_fake(self.config(), codex_runtime_bound=False)

        isolation = next(
            check
            for check in report["checks"]
            if check["check_id"] == "phase_isolation"
        )
        self.assertFalse(report["ready"])
        self.assertFalse(isolation["passed"])
        self.assertFalse(isolation["details"]["codex_runtime_bound"])

    def test_report_scrubs_secrets_even_when_input_contains_one(self) -> None:
        secret = "sk-harbor-THIS-MUST-NOT-APPEAR"
        report, _ = self.run_fake(self.config(job_name=f"doctor-{secret}"))

        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(secret, serialized)
        self.assertIn("[REDACTED]", serialized)


if __name__ == "__main__":
    unittest.main()
