from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tools.terminal_bench_doctor import (
    BUN_SOURCEMAP_TASK_CACHE_DIGEST,
    BUN_SOURCEMAP_TASK_NAME,
    CORRIDOR_SDK_VERSION,
    DATASET_CONTENT_SHA256,
    DATA_ANONYMIZATION_TASK_CACHE_DIGEST,
    DATA_ANONYMIZATION_TASK_NAME,
    DoctorConfig,
    CommandResult,
    HEAT_PUMP_WARRANTY_TASK_CACHE_DIGEST,
    HEAT_PUMP_WARRANTY_TASK_NAME,
    MUSIC_HARMONY_TASK_CACHE_DIGEST,
    MUSIC_HARMONY_TASK_NAME,
    PHASE_ISOLATION_COMMIT,
    SESSION_WINDOW_TASK_CACHE_DIGEST,
    SESSION_WINDOW_TASK_NAME,
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
        frozen_corridor_unchanged: bool = True,
        task_digest_override: str | None = None,
    ) -> None:
        self.job_name = job_name
        self.jobs_dir = jobs_dir
        self.username_claimed = username_claimed
        self.resolved_task = resolved_task
        self.docker_quiescent = docker_quiescent
        self.codex_runtime_bound = codex_runtime_bound
        self.frozen_corridor_unchanged = frozen_corridor_unchanged
        self.task_digest_override = task_digest_override
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
            if command[1:3] == ["cat-file", "-e"]:
                return CommandResult(0, "")
            if command[1] == "show":
                shown = subprocess.run(
                    ["git", "show", command[2]],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                return CommandResult(shown.returncode, shown.stdout, shown.stderr)
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
                digest = self.task_digest_override or Path(command[-1]).name
                return CommandResult(0, digest + "\n")
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
            if "regular_tree_manifest" in program:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "kit_version": CORRIDOR_SDK_VERSION,
                            "tree_digest": "sha256:" + "a" * 64,
                            "paths": [
                                "__main__.py",
                                "acceptance.py",
                                "authoring.py",
                                "capabilities.py",
                                "core.py",
                                "domain/binary.py",
                                "runtime.py",
                                "scaffold.py",
                                "submission.py",
                            ],
                        }
                    )
                    + "\n",
                )
            if "_phase_quiescence_program" in program:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "probe_b64": base64.b64encode(b"print('{}')").decode(),
                            "discovery_b64": base64.b64encode(b"true").decode(),
                            "binding_b64": base64.b64encode(b"true").decode(),
                            "phase_env_b64": base64.b64encode(
                                b"export PYTHONDONTWRITEBYTECODE=1"
                            ).decode(),
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
                            "frozen_corridor_unchanged": self.frozen_corridor_unchanged,
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
        self.session_task_cache = self.root / SESSION_WINDOW_TASK_CACHE_DIGEST
        (self.session_task_cache / "environment/app").mkdir(parents=True)
        (self.session_task_cache / "task.toml").write_text(
            "\n".join(
                [
                    "[task]",
                    'name = "terminal-bench/session-window-debug"',
                    "[agent]",
                    "timeout_sec = 7200.0",
                    "[environment]",
                    "cpus = 2",
                ]
            ),
            encoding="utf-8",
        )
        (self.session_task_cache / "environment/Dockerfile").write_text(
            "FROM python:3.12-slim\n", encoding="utf-8"
        )
        self.bun_task_cache = self.root / BUN_SOURCEMAP_TASK_CACHE_DIGEST
        (self.bun_task_cache / "environment").mkdir(parents=True)
        (self.bun_task_cache / "task.toml").write_text(
            "\n".join(
                [
                    "[task]",
                    'name = "terminal-bench/bun-sourcemap-leak"',
                    "[agent]",
                    "timeout_sec = 1800.0",
                    "[environment]",
                ]
            ),
            encoding="utf-8",
        )
        (self.bun_task_cache / "environment/Dockerfile").write_text(
            "FROM oven/bun:1.2.15-debian\n", encoding="utf-8"
        )
        self.music_task_cache = self.root / MUSIC_HARMONY_TASK_CACHE_DIGEST
        (self.music_task_cache / "environment").mkdir(parents=True)
        (self.music_task_cache / "task.toml").write_text(
            "\n".join(
                [
                    "[task]",
                    'name = "terminal-bench/music-harmony"',
                    "[agent]",
                    "timeout_sec = 7200.0",
                    "[environment]",
                    "gpus = 0",
                ]
            ),
            encoding="utf-8",
        )
        (self.music_task_cache / "environment/Dockerfile").write_text(
            "FROM python:3.11-slim\n", encoding="utf-8"
        )
        self.data_task_cache = self.root / DATA_ANONYMIZATION_TASK_CACHE_DIGEST
        (self.data_task_cache / "environment").mkdir(parents=True)
        (self.data_task_cache / "task.toml").write_text(
            "\n".join(
                [
                    "[task]",
                    'name = "terminal-bench/data-anonymization"',
                    "[agent]",
                    "timeout_sec = 3600.0",
                    "[environment]",
                    "gpus = 0",
                ]
            ),
            encoding="utf-8",
        )
        (self.data_task_cache / "environment/Dockerfile").write_text(
            "FROM ubuntu:24.04 AS input-builder\n", encoding="utf-8"
        )
        self.heat_task_cache = self.root / HEAT_PUMP_WARRANTY_TASK_CACHE_DIGEST
        (self.heat_task_cache / "environment").mkdir(parents=True)
        (self.heat_task_cache / "task.toml").write_text(
            "\n".join(
                [
                    "[task]",
                    'name = "terminal-bench/heat-pump-warranty"',
                    "[agent]",
                    "timeout_sec = 7200.0",
                    "[environment]",
                    "gpus = 0",
                ]
            ),
            encoding="utf-8",
        )
        (self.heat_task_cache / "environment/Dockerfile").write_text(
            "FROM python:3.13-slim\n", encoding="utf-8"
        )
        self.task_caches = {
            "ico-path-patch": self.task_cache,
            SESSION_WINDOW_TASK_NAME: self.session_task_cache,
            BUN_SOURCEMAP_TASK_NAME: self.bun_task_cache,
            MUSIC_HARMONY_TASK_NAME: self.music_task_cache,
            DATA_ANONYMIZATION_TASK_NAME: self.data_task_cache,
            HEAT_PUMP_WARRANTY_TASK_NAME: self.heat_task_cache,
        }
        self.auth_path = self.root / "auth.json"
        self.auth_path.write_text("{}", encoding="utf-8")

    def config(
        self,
        *,
        job_name: str = "doctor-test-001",
        spend_limit: str = "10.00",
        trusted: bool = True,
        task_name: str = "ico-path-patch",
    ) -> DoctorConfig:
        task_cache = self.task_caches[task_name]
        return DoctorConfig(
            repo_root=REPO_ROOT,
            job_name=job_name,
            jobs_dir=self.jobs_dir,
            modal_spend_limit_usd=Decimal(spend_limit),
            task_name=task_name,
            min_modal_headroom_usd=Decimal("1.00"),
            trusted_cyber_access_confirmed=trusted,
            force_auth_json="1",
            task_cache_root=task_cache,
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
        runner_options.setdefault(
            "resolved_task", f"terminal-bench/{config.task_name}"
        )
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
        self.assertEqual(
            report["condition"]["corridor_sdk_version"], CORRIDOR_SDK_VERSION
        )
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
        git_show_calls = [
            call for call in runner.calls if call[:2] == ["fake-git", "show"]
        ]
        self.assertEqual(2, len(git_show_calls))
        self.assertTrue(
            all(
                call[2].startswith(
                    "3c3813444a7d43d0a56837e9cb960be86ce26d06:method-paper/"
                )
                for call in git_show_calls
            )
        )

    def test_session_window_task_binds_exact_canonical_identity(self) -> None:
        config = self.config(
            job_name="session-window-doctor-001",
            task_name=SESSION_WINDOW_TASK_NAME,
        )

        report, runner = self.run_fake(config)

        self.assertTrue(report["ready"])
        self.assertEqual(report["condition"]["task"], SESSION_WINDOW_TASK_NAME)
        self.assertEqual(
            report["condition"]["task_filter"],
            "terminal-bench/session-window-debug",
        )
        self.assertEqual(
            report["condition"]["task_cache_digest"],
            SESSION_WINDOW_TASK_CACHE_DIGEST,
        )
        architecture = next(
            check
            for check in report["checks"]
            if check["check_id"] == "task_architecture"
        )
        self.assertTrue(architecture["passed"])
        self.assertEqual(
            architecture["details"]["binary_architecture"], "not_task_constrained"
        )
        print_call = next(
            call
            for call in runner.calls
            if call[:3] == ["fake-harbor", "run", "--print-config"]
        )
        self.assertEqual(
            print_call[print_call.index("-i") + 1],
            "terminal-bench/session-window-debug",
        )

    def test_session_window_short_filter_fails_closed(self) -> None:
        config = self.config(task_name=SESSION_WINDOW_TASK_NAME)

        report, _ = self.run_fake(config, resolved_task="session-window-debug")

        self.assertFalse(report["ready"])
        resolved = next(
            check
            for check in report["checks"]
            if check["check_id"] == "resolved_run_config"
        )
        self.assertFalse(resolved["passed"])
        self.assertEqual(
            resolved["details"]["task_filter"],
            "terminal-bench/session-window-debug",
        )

    def test_adaptive_regression_tasks_bind_exact_canonical_identities(self) -> None:
        cases = (
            (
                BUN_SOURCEMAP_TASK_NAME,
                BUN_SOURCEMAP_TASK_CACHE_DIGEST,
                "FROM oven/bun:1.2.15-debian",
            ),
            (
                MUSIC_HARMONY_TASK_NAME,
                MUSIC_HARMONY_TASK_CACHE_DIGEST,
                "FROM python:3.11-slim",
            ),
            (
                DATA_ANONYMIZATION_TASK_NAME,
                DATA_ANONYMIZATION_TASK_CACHE_DIGEST,
                "FROM ubuntu:24.04 AS input-builder",
            ),
            (
                HEAT_PUMP_WARRANTY_TASK_NAME,
                HEAT_PUMP_WARRANTY_TASK_CACHE_DIGEST,
                "FROM python:3.13-slim",
            ),
        )
        for task_name, cache_digest, base_image in cases:
            with self.subTest(task=task_name):
                config = self.config(
                    job_name=f"{task_name}-kit05-doctor-001",
                    task_name=task_name,
                )

                report, runner = self.run_fake(config)

                self.assertTrue(report["ready"])
                self.assertEqual(report["condition"]["task"], task_name)
                self.assertEqual(
                    report["condition"]["task_filter"],
                    f"terminal-bench/{task_name}",
                )
                self.assertEqual(
                    report["condition"]["task_cache_digest"], cache_digest
                )
                architecture = next(
                    check
                    for check in report["checks"]
                    if check["check_id"] == "task_architecture"
                )
                self.assertTrue(architecture["passed"])
                self.assertEqual(architecture["details"]["base_image"], base_image)
                print_call = next(
                    call
                    for call in runner.calls
                    if call[:3] == ["fake-harbor", "run", "--print-config"]
                )
                self.assertEqual(
                    print_call[print_call.index("-i") + 1],
                    f"terminal-bench/{task_name}",
                )

    def test_kit06_task_identity_drift_fails_closed(self) -> None:
        task_toml = self.data_task_cache / "task.toml"
        dockerfile = self.data_task_cache / "environment/Dockerfile"
        canonical_task = task_toml.read_text(encoding="utf-8")
        canonical_docker = dockerfile.read_text(encoding="utf-8")
        cases = (
            ("digest", canonical_task, canonical_docker, "0" * 64),
            (
                "task_name",
                canonical_task.replace(
                    "terminal-bench/data-anonymization",
                    "terminal-bench/not-data-anonymization",
                ),
                canonical_docker,
                None,
            ),
            (
                "timeout",
                canonical_task.replace("timeout_sec = 3600.0", "timeout_sec = 3599.0"),
                canonical_docker,
                None,
            ),
            (
                "gpu",
                canonical_task.replace("gpus = 0", "gpus = 1"),
                canonical_docker,
                None,
            ),
            (
                "base_image",
                canonical_task,
                "FROM python:3.12-slim\n",
                None,
            ),
        )
        for name, task_text, docker_text, digest_override in cases:
            with self.subTest(drift=name):
                task_toml.write_text(task_text, encoding="utf-8")
                dockerfile.write_text(docker_text, encoding="utf-8")
                report, _ = self.run_fake(
                    self.config(task_name=DATA_ANONYMIZATION_TASK_NAME),
                    task_digest_override=digest_override,
                )
                architecture = next(
                    check
                    for check in report["checks"]
                    if check["check_id"] == "task_architecture"
                )
                self.assertFalse(report["ready"])
                self.assertFalse(architecture["passed"])
                task_toml.write_text(canonical_task, encoding="utf-8")
                dockerfile.write_text(canonical_docker, encoding="utf-8")

    def test_kit06_expected_base_image_in_comment_fails_closed(self) -> None:
        cases = (
            (
                DATA_ANONYMIZATION_TASK_NAME,
                self.data_task_cache,
                "FROM ubuntu:24.04 AS input-builder",
            ),
            (
                HEAT_PUMP_WARRANTY_TASK_NAME,
                self.heat_task_cache,
                "FROM python:3.13-slim",
            ),
        )
        for task_name, task_cache, expected_from in cases:
            with self.subTest(task=task_name):
                dockerfile = task_cache / "environment/Dockerfile"
                canonical_docker = dockerfile.read_text(encoding="utf-8")
                dockerfile.write_text(
                    f"FROM alpine:3.22\n# {expected_from}\n",
                    encoding="utf-8",
                )
                report, _ = self.run_fake(self.config(task_name=task_name))
                architecture = next(
                    check
                    for check in report["checks"]
                    if check["check_id"] == "task_architecture"
                )
                self.assertFalse(report["ready"])
                self.assertFalse(architecture["passed"])
                self.assertFalse(architecture["details"]["base_image_exact"])
                dockerfile.write_text(canonical_docker, encoding="utf-8")

    def test_adaptive_regression_task_base_image_drift_fails_closed(self) -> None:
        (self.bun_task_cache / "environment/Dockerfile").write_text(
            "FROM python:3.12-slim\n", encoding="utf-8"
        )

        report, _ = self.run_fake(
            self.config(task_name=BUN_SOURCEMAP_TASK_NAME)
        )

        self.assertFalse(report["ready"])
        architecture = next(
            check
            for check in report["checks"]
            if check["check_id"] == "task_architecture"
        )
        self.assertFalse(architecture["passed"])
        self.assertFalse(architecture["details"]["base_image_exact"])

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

    def test_frozen_corridor_bytecode_mutation_blocks_readiness(self) -> None:
        report, _ = self.run_fake(
            self.config(), frozen_corridor_unchanged=False
        )

        isolation = next(
            check
            for check in report["checks"]
            if check["check_id"] == "phase_isolation"
        )
        self.assertFalse(report["ready"])
        self.assertFalse(isolation["passed"])
        self.assertFalse(isolation["details"]["frozen_corridor_unchanged"])

    def test_report_scrubs_secrets_even_when_input_contains_one(self) -> None:
        secret = "sk-harbor-THIS-MUST-NOT-APPEAR"
        report, _ = self.run_fake(self.config(job_name=f"doctor-{secret}"))

        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn(secret, serialized)
        self.assertIn("[REDACTED]", serialized)


if __name__ == "__main__":
    unittest.main()
