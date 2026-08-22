from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

from benchmark_agents import contract
from corridor_kit import create_scaffold


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_harbor_agent_with_stubs():
    """Load the adapter orchestration without requiring Harbor in unit-test CI."""

    modules = {
        name: types.ModuleType(name)
        for name in (
            "harbor",
            "harbor.agents",
            "harbor.agents.installed",
            "harbor.agents.installed.codex",
            "harbor.environments",
            "harbor.environments.base",
            "harbor.models",
            "harbor.models.agent",
            "harbor.models.agent.context",
            "harbor.models.trajectories",
            "harbor.models.trial",
            "harbor.models.trial.paths",
            "harbor.utils",
            "harbor.utils.trajectory_utils",
        )
    }

    class StubCodex:
        pass

    class StubEnvironment:
        pass

    class StubAgentContext:
        def __init__(self) -> None:
            self.metadata = None

    class StubEnvironmentPaths:
        agent_dir = PurePosixPath("/logs/agent")

    modules["harbor.agents.installed.codex"].Codex = StubCodex
    modules["harbor.environments.base"].BaseEnvironment = StubEnvironment
    modules["harbor.models.agent.context"].AgentContext = StubAgentContext
    modules["harbor.models.trial.paths"].EnvironmentPaths = StubEnvironmentPaths
    for name in ("Agent", "FinalMetrics", "Step", "Trajectory"):
        setattr(modules["harbor.models.trajectories"], name, type(name, (), {}))
    modules["harbor.utils.trajectory_utils"].format_trajectory_json = lambda value: value

    module_name = "_charting_loop_harbor_agent_test_double"
    path = REPOSITORY_ROOT / "benchmark_agents" / "harbor_agent.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, modules):
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
    return module


def complete_assessment(
    digest: str,
    *,
    outcome: str = "pass",
    acceptance_ids: tuple[str, ...] = ("ACCEPT-1",),
) -> dict[str, object]:
    return {
        "schema_version": contract.ASSESSMENT_SCHEMA,
        "outcome": outcome,
        "summary": "The complete public acceptance map was assessed.",
        "corridor_digest": digest,
        "source_mapping_complete": True,
        "definition_closure_complete": True,
        "assessment_closure": "complete",
        "assessed_scope": "complete",
        "scope_limitations": [],
        "acceptance_results": [
            {
                "acceptance_id": acceptance_id,
                "applicability": "applicable",
                "status": "pass",
                "evidence": f"Observed passing evidence for {acceptance_id}.",
                "replay": f"Replay the check for {acceptance_id}.",
            }
            for acceptance_id in acceptance_ids
        ],
        "unmapped_requirements": [],
        "unresolved_relations": [],
        "checks": [
            {
                "name": "source coverage",
                "status": "pass",
                "evidence": "Every public normative clause is mapped.",
            }
        ],
        "witnesses": [],
    }


class FullMethodContractTests(unittest.TestCase):
    def test_codex_runtime_binding_is_visible_to_a_fresh_shell(self) -> None:
        module = load_harbor_agent_with_stubs()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nvm_root = root / "nvm/versions/node"
            version_bin = nvm_root / "v22.17.0/bin"
            stable_bin = root / "stable-bin"
            version_bin.mkdir(parents=True)
            node = version_bin / "node"
            codex = version_bin / "codex"
            node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            codex.write_text("#!/bin/sh\necho codex-cli-test\n", encoding="utf-8")
            node.chmod(0o755)
            codex.chmod(0o755)

            command = module._codex_runtime_binding_command(
                node_bin=str(node),
                codex_bin=str(codex),
                stable_bin_dir=str(stable_bin),
            )
            completed = subprocess.run(
                ["sh", "-c", command],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("codex-cli-test", completed.stdout)
            self.assertEqual(node.resolve(), (stable_bin / "node").resolve())
            self.assertEqual(codex.resolve(), (stable_bin / "codex").resolve())

    def test_codex_runtime_discovery_uses_the_agent_runtime_home(self) -> None:
        module = load_harbor_agent_with_stubs()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version_bin = root / ".nvm/versions/node/v22.17.0/bin"
            version_bin.mkdir(parents=True)
            node = version_bin / "node"
            codex = version_bin / "codex"
            node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            codex.write_text("#!/bin/sh\necho codex-cli-test\n", encoding="utf-8")
            node.chmod(0o755)
            codex.chmod(0o755)
            (root / ".nvm/nvm.sh").write_text(
                f'PATH="{version_bin}:$PATH"; export PATH\n',
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["/bin/sh", "-c", module._codex_runtime_discovery_command()],
                text=True,
                capture_output=True,
                check=False,
                env={"HOME": str(root), "PATH": "/usr/bin:/bin"},
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(
                (str(node), str(codex)),
                module._parse_codex_runtime_paths(completed.stdout),
            )

    def test_codex_runtime_discovery_fails_closed_without_an_install(self) -> None:
        module = load_harbor_agent_with_stubs()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            empty_bin = root / "empty-bin"
            empty_bin.mkdir()
            completed = subprocess.run(
                ["/bin/sh", "-c", module._codex_runtime_discovery_command()],
                text=True,
                capture_output=True,
                check=False,
                env={"HOME": str(root), "PATH": str(empty_bin)},
            )

            self.assertNotEqual(0, completed.returncode)

    def test_one_total_task_deadline_prefers_explicit_public_limit(self) -> None:
        module = load_harbor_agent_with_stubs()
        self.assertEqual(5400, module._task_timeout_seconds("No limit is stated."))
        self.assertEqual(
            3600,
            module._task_timeout_seconds("You have 3600 seconds to complete the task."),
        )
        self.assertEqual(
            7200,
            module._task_timeout_seconds("The task time limit is 7200 seconds."),
        )

    def test_protocol_and_runbook_fix_the_claim_and_visibility_boundaries(self) -> None:
        protocol = (
            REPOSITORY_ROOT
            / "protocol"
            / "TASK-CONDITIONED-CORRIDOR-BENCHMARK-V4.md"
        ).read_text(encoding="utf-8")
        runbook = (
            REPOSITORY_ROOT / "docs" / "TERMINAL-BENCH-3-RUNBOOK.md"
        ).read_text(encoding="utf-8")
        normalized_protocol = " ".join(protocol.split())

        for marker in (
            "terminal-bench/terminal-bench@3.0.0",
            "74 scored tasks",
            "4 tasks require GPU-capable execution",
            "QA follows its cooperative write boundary, never suppresses or replaces the Worker",
            "never short-circuits the benchmark grader",
            "Do not ask Builder to construct a mandatory approval",
            "linear-unlock",
            "Rule remains the normative authority layer",
            "whole-chain",
            "leaderboard score is end-to-end performance",
            "ACCEPTANCE.json",
            "WORK_ITEMS.json",
            "CAPABILITIES.json",
            "hash-linked append-only Position timeline",
            "Reminder delivery and use are observable process facts, not Gates",
            "restores the latest verified complete Worker snapshot by per-file atomic replacement",
            "charting-loop-method-v8",
            "namespace/provenance label, not a credential",
            "one end-to-end deadline",
            "not a Gate",
            "same-task rerun",
        ):
            self.assertIn(marker, normalized_protocol)
        for marker in (
            'export PYTHONPATH="$CHARTING_LOOP_ROOT',
            "--print-config",
            "--upload --private",
            "CODEX_FORCE_AUTH_JSON=1",
            "Do not add a control arm to this job",
            "Do not call this a causal estimate",
        ):
            self.assertIn(marker, runbook)
        self.assertNotIn("--ae CODEX_FORCE_AUTH_JSON=1", runbook)

    def test_agent_is_bound_to_the_exact_frozen_v8_method(self) -> None:
        index = json.loads(
            (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        versions = [
            version
            for version in index["versions"]
            if version["version_id"] == "charting-loop-method-v8"
        ]
        self.assertEqual(1, len(versions))
        version = versions[0]
        self.assertEqual("frozen", version["status"])
        self.assertTrue(version["study_eligible"])
        self.assertFalse(version["adoption_eligible"])
        self.assertEqual(
            "3c3813444a7d43d0a56837e9cb960be86ce26d06",
            version["source_commit"],
        )
        for path_key, digest_key in (
            ("path", "content_sha256"),
            ("scope_datum_path", "scope_datum_sha256"),
        ):
            shown = subprocess.run(
                [
                    "git",
                    "show",
                    f"{version['source_commit']}:{version[path_key]}",
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
            )
            actual = "sha256:" + hashlib.sha256(shown.stdout).hexdigest()
            self.assertEqual(version[digest_key], actual)

        v7 = next(
            item
            for item in index["versions"]
            if item["version_id"] == "charting-loop-method-v7"
        )
        self.assertNotEqual(version["content_sha256"], v7["content_sha256"])

        module = load_harbor_agent_with_stubs()
        resolved = module._resolve_frozen_method(REPOSITORY_ROOT)
        self.assertIsInstance(resolved, bytes)
        self.assertEqual(
            version["content_sha256"],
            "sha256:" + hashlib.sha256(resolved).hexdigest(),
        )
        self.assertEqual(resolved, (REPOSITORY_ROOT / version["path"]).read_bytes())

        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                REPOSITORY_ROOT / "benchmark_agents" / "harbor_agent.py",
                REPOSITORY_ROOT / "benchmark_agents" / "contract.py",
            )
        )
        for value in (
            "charting-loop-method-v8",
            version["source_commit"],
            version["content_sha256"],
            version["scope_datum_sha256"],
            "_resolve_frozen_method",
            "before a paid model call",
        ):
            self.assertIn(value, source)

    def test_worker_and_qa_receive_same_corridor_identity(self) -> None:
        digest = "sha256:" + "a" * 64
        task = "Repair the live system and leave it verifiable."
        method_text = (REPOSITORY_ROOT / "method-paper" / "METHOD.md").read_text(
            encoding="utf-8"
        )
        worker = contract.worker_prompt(
            task,
            digest,
            position_ref="sha256:" + "1" * 64,
            direction_digest="sha256:" + "2" * 64,
            method_text=method_text,
            fact_candidate_ref="worker-candidate:test",
        )
        qa = contract.qa_prompt(
            task,
            digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            position_ref="sha256:" + "3" * 64,
            direction_digest="sha256:" + "4" * 64,
            method_text=method_text,
            fact_candidate_ref="worker-000001-deadbeef",
        )

        for prompt in (worker, qa):
            self.assertIn(task, prompt)
            self.assertIn(contract.CORRIDOR_PATH, prompt)
            self.assertIn(contract.FREEZE_PATH, prompt)
            self.assertIn(digest, prompt)
            self.assertIn(contract.WORK_PATH, prompt)
            self.assertIn(contract.CAPABILITIES_PATH, prompt)
            self.assertIn(contract.POSITION_PATH, prompt)
            self.assertIn("python3 -m corridor_kit runtime guide", prompt)
            self.assertIn(f"--acceptance {contract.ACCEPTANCE_PATH}", prompt)
            self.assertIn("PositionRef", prompt)
            self.assertIn("Direction digest", prompt)
            self.assertIn(method_text, prompt)
            self.assertIn(contract.METHOD_VERSION_ID, prompt)
            self.assertIn(contract.METHOD_CONTENT_SHA256, prompt)
            self.assertIn("not chain-of-thought", prompt)
            self.assertIn("runner alone may admit", " ".join(prompt.lower().split()))
        self.assertIn("independent QA", qa)
        self.assertIn("Do not mutate", qa)
        self.assertIn(contract.QA_PATH, qa)
        self.assertIn(contract.ACCEPTANCE_PATH, worker)
        self.assertIn("ACCEPT-1", qa)
        self.assertIn("independently re-read", qa.lower())
        self.assertIn('"source_mapping_complete"', qa)
        self.assertIn('"definition_closure_complete"', qa)
        self.assertIn('"assessment_closure"', qa)
        self.assertIn('"assessed_scope"', qa)
        self.assertIn('"scope_limitations"', qa)
        self.assertIn("corridor_kit qa validate", qa)
        self.assertNotIn('"coverage_complete"', qa)
        self.assertIn("one task-level deadline", worker)
        self.assertIn("corridor_kit submission freeze", worker)
        self.assertIn(contract.SUBMISSION_ROOT, worker)
        normalized_qa = " ".join(qa.split())
        self.assertIn("cooperative protocol roles", normalized_qa)
        self.assertIn("provenance namespace", normalized_qa)
        self.assertIn("not an authorization credential or Gate", normalized_qa)
        self.assertIn("write only the assessment path", normalized_qa)
        self.assertNotIn("QA remains advisory and cannot delete", qa)
        with self.assertRaisesRegex(ValueError, "frozen Method digest"):
            contract.worker_prompt(
                task,
                digest,
                method_text=method_text + "silent revision",
                fact_candidate_ref="worker-candidate:test",
            )

    def test_builder_is_task_conditioned_but_must_not_build_a_gate(self) -> None:
        prompt = contract.builder_prompt("Find and repair the fault.")
        self.assertIn("Find and repair the fault.", prompt)
        self.assertIn(contract.METHOD_PATH, prompt)
        self.assertIn(contract.CORRIDOR_PATH, prompt)
        self.assertIn("do not carry out the official task", prompt)
        self.assertIn("do not install a mandatory workflow gate", prompt)
        self.assertIn("not a new governance dependency", prompt)
        self.assertIn(contract.ACCEPTANCE_PATH, prompt)
        self.assertIn(contract.ACCEPTANCE_SCHEMA, prompt)
        self.assertIn("Decompose every normative", prompt)
        self.assertIn(contract.SDK_PACKAGE_PATH, prompt)
        self.assertIn(contract.WORK_PATH, prompt)
        self.assertIn(contract.CAPABILITIES_PATH, prompt)
        self.assertIn("METHOD-CAPSULE.json", prompt)
        self.assertIn(contract.METHOD_CONTENT_SHA256, prompt)
        self.assertIn("SOURCE-MAP.json", prompt)
        self.assertIn("EVIDENCE.json", prompt)
        self.assertIn("REPLAY.json", prompt)
        self.assertIn("python3 -m corridor_kit capabilities builtins", prompt)
        self.assertIn("Dependencies must be acyclic", prompt)
        self.assertIn("Reminders are advisory", prompt)
        self.assertIn("verification_obligations", prompt)
        for partition in ("positive", "negative", "boundary", "state", "temporal", "coupled"):
            self.assertIn(f'"{partition}"', prompt)

    def test_fail_requires_a_replayable_witness(self) -> None:
        digest = "sha256:" + "b" * 64
        assessment = complete_assessment(digest, outcome="fail")
        assessment["acceptance_results"][0]["status"] = "fail"
        self.assertIn(
            "FAIL_WITNESS_REQUIRED",
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="complete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
            ),
        )

        assessment["witnesses"] = [
            {
                "acceptance_id": "ACCEPT-1",
                "constraint": "The service must preserve identity.",
                "evidence": "Observed id changed from A to B.",
                "replay": "Read the before/after identity fields.",
            }
        ]
        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="complete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
            ),
        )

    def test_pass_requires_complete_exact_acceptance_coverage(self) -> None:
        digest = "sha256:" + "c" * 64
        assessment = complete_assessment(
            digest, acceptance_ids=("ACCEPT-1", "ACCEPT-2")
        )
        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="complete",
                expected_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
                required_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
            ),
        )

        missing = complete_assessment(digest)
        errors = contract.validate_qa_assessment(
            missing,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
            required_acceptance_ids=["ACCEPT-1", "ACCEPT-2"],
        )
        self.assertIn("ASSESSMENT_ACCEPTANCE_ID_MISSING_ACCEPT-2", errors)

        unknown = complete_assessment(
            digest, acceptance_ids=("ACCEPT-1", "UNKNOWN")
        )
        errors = contract.validate_qa_assessment(
            unknown,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn("ASSESSMENT_ACCEPTANCE_ID_UNKNOWN_UNKNOWN", errors)

        duplicate = complete_assessment(digest)
        duplicate["acceptance_results"].append(
            dict(duplicate["acceptance_results"][0])
        )
        errors = contract.validate_qa_assessment(
            duplicate,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn(
            "ASSESSMENT_ACCEPTANCE_ID_DUPLICATE_ACCEPT-1", errors
        )

    def test_incomplete_ledger_cannot_pass_but_can_be_not_assessed(self) -> None:
        digest = "sha256:" + "d" * 64
        assessment = complete_assessment(digest)
        errors = contract.validate_qa_assessment(
            assessment,
            expected_corridor_digest=digest,
            acceptance_ledger_status="incomplete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn("PASS_ACCEPTANCE_LEDGER_COMPLETE_REQUIRED", errors)

        assessment["outcome"] = "not_assessed"
        assessment["source_mapping_complete"] = False
        assessment["assessment_closure"] = "incomplete"
        assessment["unmapped_requirements"] = ["public-spec.md#metrics"]
        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="incomplete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
                source_mapping_status="incomplete",
            ),
        )

    def test_witness_fail_survives_incomplete_definition_closure(self) -> None:
        digest = "sha256:" + "e" * 64
        assessment = complete_assessment(digest, outcome="fail")
        assessment["definition_closure_complete"] = False
        assessment["assessment_closure"] = "incomplete"
        assessment["unresolved_relations"] = [
            "ACCEPT-1 has an unresolved relation to the public threshold."
        ]
        assessment["acceptance_results"][0]["status"] = "fail"
        assessment["witnesses"] = [
            {
                "acceptance_id": "ACCEPT-1",
                "constraint": "The patched path must preserve the public ABI.",
                "evidence": "The exported symbol is absent after the patch.",
                "replay": "Inspect the exported symbol table.",
            }
        ]

        self.assertEqual(
            [],
            contract.validate_qa_assessment(
                assessment,
                expected_corridor_digest=digest,
                acceptance_ledger_status="incomplete",
                expected_acceptance_ids=["ACCEPT-1"],
                required_acceptance_ids=["ACCEPT-1"],
                source_mapping_status="complete",
                definition_closure_status="incomplete",
                construction_readiness_status="unresolved",
            ),
        )

    def test_qa_closure_dimensions_have_independent_contradictions(self) -> None:
        digest = "sha256:" + "f" * 64
        assessment = complete_assessment(digest, outcome="not_assessed")
        assessment["unmapped_requirements"] = ["public-spec.md#missing"]
        assessment["unresolved_relations"] = ["ACCEPT-1 overlaps ACCEPT-2"]
        assessment["acceptance_results"][0]["status"] = "unknown"

        errors = contract.validate_qa_assessment(
            assessment,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )

        self.assertIn("ASSESSMENT_SOURCE_MAPPING_CONTRADICTION", errors)
        self.assertIn("ASSESSMENT_DEFINITION_CLOSURE_CONTRADICTION", errors)
        self.assertIn("ASSESSMENT_CLOSURE_CONTRADICTION", errors)

        contradictory = complete_assessment(digest, outcome="not_assessed")
        contradictory["definition_closure_complete"] = False
        errors = contract.validate_qa_assessment(
            contradictory,
            expected_corridor_digest=digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
            required_acceptance_ids=["ACCEPT-1"],
        )
        self.assertIn(
            "ASSESSMENT_DEFINITION_AND_CLOSURE_CONTRADICTION", errors
        )

    def test_qa_json_rejects_duplicate_keys_and_non_finite_numbers(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate QA JSON key"):
            contract.load_qa_json_text('{"outcome":"pass","outcome":"fail"}')
        with self.assertRaisesRegex(ValueError, "non-finite QA JSON value"):
            contract.load_qa_json_text('{"value":NaN}')

    def test_corridor_digest_binds_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plain = root / "plain"
            executable = root / "executable"
            plain.mkdir()
            executable.mkdir()
            (plain / "tool").write_text("same bytes\n", encoding="utf-8")
            (executable / "tool").write_text("same bytes\n", encoding="utf-8")
            os.chmod(executable / "tool", 0o755)
            plain_manifest = contract.corridor_manifest(plain)
            executable_manifest = contract.corridor_manifest(executable)
            self.assertFalse(plain_manifest[0]["executable"])
            self.assertTrue(executable_manifest[0]["executable"])
            self.assertNotEqual(
                contract.corridor_digest(plain_manifest),
                contract.corridor_digest(executable_manifest),
            )

    def test_private_custody_captures_frozen_bytes_before_teardown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent_dir = root / "agent"
            runtime_root = root / "runtime"
            corridor = runtime_root / "corridor"
            position = root / "position" / "POSITION.jsonl"
            submissions = agent_dir / "submissions"
            corridor.mkdir(parents=True)
            (corridor / "tool.py").write_text("print('public probe')\n", encoding="utf-8")
            os.chmod(corridor / "tool.py", 0o755)
            digest = contract.corridor_digest(contract.corridor_manifest(corridor))
            (runtime_root / "FREEZE.json").write_text(
                json.dumps({"corridor_digest": digest}), encoding="utf-8"
            )
            position.parent.mkdir(parents=True)
            position.write_text('{"event":"start"}\n', encoding="utf-8")
            phase = agent_dir / "phases" / "builder" / "sessions"
            phase.mkdir(parents=True)
            (phase / "events.jsonl").write_text(
                '{"payload":{"type":"task_complete"}}\n', encoding="utf-8"
            )
            latest = submissions / "latest"
            manifest_dir = submissions / "snapshots" / "worker" / "snapshot-1"
            blob_dir = submissions / "blobs"
            latest.mkdir(parents=True)
            manifest_dir.mkdir(parents=True)
            blob_dir.mkdir(parents=True)
            (latest / "worker.json").write_text(
                '{"snapshot_id":"snapshot-1"}\n', encoding="utf-8"
            )
            (manifest_dir / "manifest.json").write_text(
                '{"snapshot_id":"snapshot-1"}\n', encoding="utf-8"
            )
            (blob_dir / "private-solution-byte").write_bytes(b"do not duplicate")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    contract.private_custody_program(
                        agent_dir=str(agent_dir),
                        expected_corridor_digest=digest,
                        runtime_root=str(runtime_root),
                        position_path=str(position),
                        submission_root=str(submissions),
                    ),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertTrue(report["ok"])
            self.assertEqual("direct", report["custody_status"])
            self.assertTrue(report["direct_byte_match"])
            custody = agent_dir / "corridor-custody"
            self.assertEqual(
                (corridor / "tool.py").read_bytes(),
                (custody / "frozen-corridor" / "tool.py").read_bytes(),
            )
            self.assertTrue(
                (custody / "submission-manifests" / "latest" / "worker.json").is_file()
            )
            self.assertFalse(
                (custody / "submission-manifests" / "blobs").exists()
            )
            preserved_manifest = (custody / "custody-manifest.json").read_bytes()
            repeated = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    contract.private_custody_program(
                        agent_dir=str(agent_dir),
                        expected_corridor_digest=digest,
                        runtime_root=str(runtime_root),
                        position_path=str(position),
                        submission_root=str(submissions),
                    ),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, repeated.returncode, repeated.stderr)
            repeated_report = json.loads(repeated.stdout)
            self.assertTrue(repeated_report["ok"])
            self.assertTrue(repeated_report["already_captured"])
            self.assertTrue(repeated_report["preserved_existing"])
            self.assertTrue(repeated_report["existing_bytes_revalidated"])
            self.assertEqual(
                preserved_manifest,
                (custody / "custody-manifest.json").read_bytes(),
            )
            root_manifest = json.loads(preserved_manifest)
            root_manifest["forged_extra"] = True
            (custody / "custody-manifest.json").write_text(
                json.dumps(root_manifest), encoding="utf-8"
            )
            root_manifest_retry = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    contract.private_custody_program(
                        agent_dir=str(agent_dir),
                        expected_corridor_digest=digest,
                        runtime_root=str(runtime_root),
                        position_path=str(position),
                        submission_root=str(submissions),
                    ),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, root_manifest_retry.returncode, root_manifest_retry.stderr)
            root_manifest_report = json.loads(root_manifest_retry.stdout)
            self.assertFalse(root_manifest_report["ok"])
            self.assertFalse(root_manifest_report["existing_bytes_revalidated"])
            self.assertTrue(root_manifest_report["preserved_existing"])
            (custody / "custody-manifest.json").write_bytes(preserved_manifest)
            injected = custody / "roles" / "builder" / "custody-manifest.json"
            injected.write_text("unbound nested bytes\n", encoding="utf-8")
            nested_injection_retry = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    contract.private_custody_program(
                        agent_dir=str(agent_dir),
                        expected_corridor_digest=digest,
                        runtime_root=str(runtime_root),
                        position_path=str(position),
                        submission_root=str(submissions),
                    ),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                0, nested_injection_retry.returncode, nested_injection_retry.stderr
            )
            nested_injection_report = json.loads(nested_injection_retry.stdout)
            self.assertFalse(nested_injection_report["ok"])
            self.assertFalse(
                nested_injection_report["existing_bytes_revalidated"]
            )
            self.assertEqual(
                preserved_manifest,
                (custody / "custody-manifest.json").read_bytes(),
            )
            injected.unlink()
            (custody / "frozen-corridor" / "tool.py").write_text(
                "tampered\n", encoding="utf-8"
            )
            tampered_retry = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    contract.private_custody_program(
                        agent_dir=str(agent_dir),
                        expected_corridor_digest=digest,
                        runtime_root=str(runtime_root),
                        position_path=str(position),
                        submission_root=str(submissions),
                    ),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, tampered_retry.returncode, tampered_retry.stderr)
            tampered_report = json.loads(tampered_retry.stdout)
            self.assertFalse(tampered_report["ok"])
            self.assertFalse(tampered_report["existing_bytes_revalidated"])
            self.assertTrue(tampered_report["preserved_existing"])
            self.assertEqual(
                preserved_manifest,
                (custody / "custody-manifest.json").read_bytes(),
            )

        recovered = contract.custody_provenance(
            "recovered_from_builder_events", direct_byte_match=False
        )
        self.assertEqual("recovered", recovered["custody_status"])
        self.assertTrue(recovered["recovered"])
        self.assertFalse(recovered["direct_download"])

    def test_private_custody_reports_digest_mismatch_and_capture_failure(self) -> None:
        for case in ("mismatch", "missing_position"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                agent_dir = root / "agent"
                runtime_root = root / "runtime"
                corridor = runtime_root / "corridor"
                position = root / "position" / "POSITION.jsonl"
                submissions = agent_dir / "submissions"
                (agent_dir / "phases" / "builder").mkdir(parents=True)
                submissions.mkdir(parents=True)
                corridor.mkdir(parents=True)
                (corridor / "README.md").write_text("corridor\n", encoding="utf-8")
                actual_digest = contract.corridor_digest(
                    contract.corridor_manifest(corridor)
                )
                (runtime_root / "FREEZE.json").write_text(
                    json.dumps({"corridor_digest": actual_digest}), encoding="utf-8"
                )
                if case != "missing_position":
                    position.parent.mkdir(parents=True)
                    position.write_text('{"event":"start"}\n', encoding="utf-8")
                expected = (
                    "sha256:" + "0" * 64 if case == "mismatch" else actual_digest
                )
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        contract.private_custody_program(
                            agent_dir=str(agent_dir),
                            expected_corridor_digest=expected,
                            runtime_root=str(runtime_root),
                            position_path=str(position),
                            submission_root=str(submissions),
                        ),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                report = json.loads(completed.stdout)
                if case == "mismatch":
                    self.assertFalse(report["ok"])
                    self.assertEqual("digest_mismatch", report["custody_status"])
                    self.assertFalse(report["direct_byte_match"])
                    self.assertFalse(report["direct_download"])
                else:
                    self.assertFalse(report["ok"])
                    self.assertEqual("capture_failed", report["custody_status"])
                    self.assertEqual("FileNotFoundError", report["error_type"])
                    self.assertEqual(
                        "../phases/builder", report["builder_recovery_evidence"]
                    )
                manifest = json.loads(
                    (agent_dir / "corridor-custody" / "custody-manifest.json")
                    .read_text(encoding="utf-8")
                )
                self.assertEqual(report["custody_status"], manifest["custody_status"])

    def test_private_custody_rejects_forged_preexisting_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent_dir = root / "agent"
            target = agent_dir / "corridor-custody"
            target.mkdir(parents=True)
            (target / "custody-manifest.json").write_text(
                json.dumps({
                    "custody_status": "direct",
                    "direct_byte_match": True,
                    "direct_download": True,
                }),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    contract.private_custody_program(
                        agent_dir=str(agent_dir),
                        expected_corridor_digest="sha256:" + "f" * 64,
                        runtime_root=str(root / "runtime"),
                        position_path=str(root / "POSITION.jsonl"),
                        submission_root=str(root / "submissions"),
                    ),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertFalse(report["ok"])
            self.assertEqual("capture_failed", report["custody_status"])
            self.assertFalse(report["existing_bytes_revalidated"])
            self.assertTrue(report["preserved_existing"])

    def test_role_metrics_separate_tool_and_inference_wall_time(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            role_dir = root / "builder"
            session_dir = role_dir / "sessions"
            corridor = root / "corridor"
            session_dir.mkdir(parents=True)
            corridor.mkdir()
            events = [
                {
                    "timestamp": "2026-08-18T12:00:00Z",
                    "payload": {
                        "type": "task_started",
                        "started_at": "2026-08-18T12:00:00Z",
                    },
                },
                {
                    "timestamp": "2026-08-18T12:00:01Z",
                    "payload": {"type": "custom_tool_call", "call_id": "call-1"},
                },
                {
                    "timestamp": "2026-08-18T12:00:03Z",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "call-1",
                    },
                },
                {
                    "timestamp": "2026-08-18T12:00:05Z",
                    "payload": {"type": "agent_message"},
                },
                {
                    "timestamp": "2026-08-18T12:00:10Z",
                    "payload": {
                        "type": "task_complete",
                        "completed_at": "2026-08-18T12:00:10Z",
                    },
                },
            ]
            (session_dir / "events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            capsule = {
                "schema_version": "charting-loop/method-capsule/v1",
                "binding_state": "bound",
                "method_version": "method-v-test",
                "method_digest": "sha256:" + "a" * 64,
                "method_scope_digest": "sha256:" + "b" * 64,
            }
            (corridor / "METHOD-CAPSULE.json").write_text(
                json.dumps(capsule), encoding="utf-8"
            )
            (corridor / "KIT.json").write_text(
                json.dumps({
                    "method_capsule_digest": contract.sha256_bytes(
                        contract.canonical_json_bytes(capsule)
                    ),
                    "starter_digest": "sha256:" + "d" * 64,
                }),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    adapter._role_metrics_program(str(role_dir), str(corridor)),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            metrics = json.loads(completed.stdout)
            self.assertEqual(1, metrics["turn_count"])
            self.assertEqual(1, metrics["tool_call_count"])
            self.assertEqual(2.0, metrics["tool_wall_seconds"])
            self.assertEqual(8.0, metrics["inference_wall_seconds"])
            self.assertEqual(10.0, metrics["total_wall_seconds"])
            self.assertEqual(2, metrics["generated_file_count"])
            self.assertGreater(metrics["generated_bytes"], 0)
            self.assertEqual("bound", metrics["method_capsule"]["binding_state"])
            self.assertEqual(
                contract.sha256_bytes(contract.canonical_json_bytes(capsule)),
                metrics["method_capsule"]["capsule_digest"],
            )
            self.assertEqual(
                metrics["method_capsule"]["capsule_digest"],
                metrics["method_capsule"]["stored_capsule_digest"],
            )
            self.assertTrue(
                metrics["method_capsule"]["capsule_digest_matches_stored"]
            )
            self.assertEqual({}, metrics["method_capsule"]["parse_errors"])
            self.assertEqual(
                "sha256:" + "d" * 64,
                metrics["method_capsule"]["scaffold_digest"],
            )

        valid_freeze = {
            "builder_corridor_status": "frozen",
            "method_capsule_status": "complete",
            "method_capsule_errors": [],
            "method_capsule_digest": "sha256:" + "e" * 64,
            "method_capsule_expected_digest": "sha256:" + "e" * 64,
            "method_capsule_stored_digest": "sha256:" + "e" * 64,
            "method_capsule_digest_matches_stored": True,
            "acceptance_ledger_status": "complete",
            "source_mapping_status": "complete",
            "definition_closure_status": "complete",
            "construction_readiness_status": "ready",
            "acceptance_ledger_errors": [],
        }
        valid_runtime_guide = {
            "available": True,
            "status": "compiled",
            "work_validation_ok": True,
            "work_state": "compiled",
            "capability_state": "compiled",
            "current_row_id": "ROW-1",
            "direction_digest": "sha256:" + "d" * 64,
            "advisory_only": True,
            "authorizes_mutation": False,
        }
        valid_metrics = adapter._builder_freeze_metrics(
            valid_freeze,
            elapsed_seconds=12.3456,
            runtime_guide=valid_runtime_guide,
        )
        self.assertTrue(valid_metrics["first_valid_freeze_recorded"])
        self.assertEqual(12.346, valid_metrics["first_valid_freeze_elapsed_seconds"])
        self.assertEqual("complete", valid_metrics["method_capsule_status"])
        self.assertEqual([], valid_metrics["method_capsule_errors"])
        self.assertTrue(valid_metrics["method_capsule_digest_matches_stored"])

        invalid_freeze = dict(valid_freeze)
        invalid_freeze["acceptance_ledger_status"] = "invalid"
        invalid_metrics = adapter._builder_freeze_metrics(
            invalid_freeze,
            elapsed_seconds=9.0,
            runtime_guide=valid_runtime_guide,
        )
        self.assertFalse(invalid_metrics["first_valid_freeze_recorded"])
        self.assertIsNone(invalid_metrics["first_valid_freeze_elapsed_seconds"])
        self.assertEqual(9.0, invalid_metrics["freeze_elapsed_seconds"])

        invalid_runtime_guide = dict(valid_runtime_guide)
        invalid_runtime_guide["status"] = "invalid_or_uncompiled"
        invalid_runtime_guide["work_validation_ok"] = False
        invalid_runtime_guide["capability_state"] = "missing"
        runtime_invalid_metrics = adapter._builder_freeze_metrics(
            valid_freeze,
            elapsed_seconds=7.0,
            runtime_guide=invalid_runtime_guide,
        )
        self.assertFalse(runtime_invalid_metrics["first_valid_freeze_recorded"])
        self.assertIsNone(
            runtime_invalid_metrics["first_valid_freeze_elapsed_seconds"]
        )
        self.assertEqual(
            "invalid_or_uncompiled",
            runtime_invalid_metrics["work_backlog_status"],
        )
        self.assertEqual(
            "missing",
            runtime_invalid_metrics["capability_registry_status"],
        )

    def test_freezer_marks_a_tampered_method_capsule_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            (root / "method" / "METHOD.md").write_text(
                "method\n", encoding="utf-8"
            )
            corridor = create_scaffold(
                root / "corridor",
                method_version=contract.METHOD_VERSION_ID,
                method_digest=contract.METHOD_CONTENT_SHA256,
                method_scope_digest=contract.METHOD_SCOPE_SHA256,
            )
            capsule_path = corridor / "METHOD-CAPSULE.json"
            capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
            capsule["builder_invariants"] = ["replace the frozen method"]
            capsule_path.write_text(json.dumps(capsule), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            identity = json.loads(completed.stdout)
            self.assertEqual("invalid", identity["method_capsule_status"])
            self.assertIn(
                "METHOD_CAPSULE_CONTENT_MISMATCH",
                identity["method_capsule_errors"],
            )
            self.assertFalse(identity["method_capsule_digest_matches_stored"])
            manifest = json.loads(
                (root / "FREEZE.json").read_text(encoding="utf-8")
            )
            self.assertEqual("invalid", manifest["method_capsule"]["status"])

    def test_freezer_closes_bytes_and_falls_back_when_builder_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            (root / "method" / "METHOD.md").write_text("method\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            probe = json.loads(completed.stdout)
            self.assertTrue(probe["ok"])
            self.assertEqual("fallback", probe["builder_corridor_status"])

            manifest = json.loads((root / "FREEZE.json").read_text(encoding="utf-8"))
            self.assertEqual(contract.FREEZE_SCHEMA, manifest["schema_version"])
            self.assertEqual(probe["corridor_digest"], manifest["corridor_tree_sha256"])
            self.assertEqual("missing", probe["acceptance_ledger_status"])
            self.assertIn(
                "ACCEPTANCE_LEDGER_MISSING",
                probe["acceptance_ledger_errors"],
            )
            for path in [root / "FREEZE.json", *(root / "corridor").rglob("*")]:
                self.assertEqual(0, stat.S_IMODE(path.stat().st_mode) & 0o222)
                self.assertEqual(0o044, stat.S_IMODE(path.stat().st_mode) & 0o044)
            self.assertEqual(
                0o055,
                stat.S_IMODE((root / "corridor").stat().st_mode) & 0o055,
            )

            verified = subprocess.run(
                [sys.executable, "-c", contract.verify_freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, verified.returncode, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["ok"])

    def test_freeze_verification_rejects_python_cache_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            corridor = root / "corridor"
            corridor.mkdir()
            (root / "method" / "METHOD.md").write_text(
                "method\n", encoding="utf-8"
            )
            (corridor / "task_adapter.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            frozen = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, frozen.returncode, frozen.stderr)

            os.chmod(corridor, 0o755)
            cache = corridor / "__pycache__"
            cache.mkdir()
            (cache / "task_adapter.cpython-312.pyc").write_bytes(b"changed")
            verified = subprocess.run(
                [sys.executable, "-c", contract.verify_freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, verified.returncode, verified.stderr)
            probe = json.loads(verified.stdout)
            self.assertFalse(probe["ok"])
            self.assertTrue(
                any(
                    item.startswith("excluded_cache_present:")
                    for item in probe["violations"]
                ),
                probe,
            )

    def test_freezer_records_complete_acceptance_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            corridor = root / "corridor"
            corridor.mkdir()
            (root / "method" / "METHOD.md").write_text(
                "method\n", encoding="utf-8"
            )
            ledger = {
                "schema_version": contract.ACCEPTANCE_SCHEMA,
                "coverage": {
                    "status": "complete",
                    "unmapped_clauses": [],
                    "ambiguous_clauses": [],
                },
                "construction_readiness": {
                    "status": "ready",
                    "coupled_acceptance_ids": ["ACCEPT-1"],
                    "replay_entrypoint": "python3 validate.py",
                    "unresolved_constraints": [],
                },
                "items": [
                    {
                        "acceptance_id": "ACCEPT-1",
                        "source_ref": "instruction.md#output",
                        "statement": "Write the required output.",
                        "required": True,
                        "definition_state": "defined",
                        "scope": {"path": "/app/output.json"},
                        "rule": {"kind": "file_exists"},
                        "relations": [],
                        "verification_obligations": {
                            "positive": ["file exists"],
                            "negative": ["missing file is rejected"],
                            "boundary": ["empty file boundary is checked"],
                            "state": ["before/after file state is checked"],
                            "temporal": ["write precedes verification"],
                            "coupled": ["single requirement; explicit not applicable"],
                        },
                    }
                ],
            }
            (corridor / "ACCEPTANCE.json").write_text(
                json.dumps(ledger), encoding="utf-8"
            )
            completed = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            identity = json.loads(completed.stdout)
            self.assertEqual("complete", identity["acceptance_ledger_status"])
            self.assertEqual(["ACCEPT-1"], identity["acceptance_ids"])
            self.assertEqual(["ACCEPT-1"], identity["required_acceptance_ids"])
            self.assertEqual([], identity["acceptance_ledger_errors"])
            self.assertEqual("complete", identity["source_mapping_status"])
            self.assertEqual("complete", identity["definition_closure_status"])
            self.assertEqual("ready", identity["construction_readiness_status"])

    def test_freezer_separates_mapping_from_definition_closure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "method").mkdir(parents=True)
            corridor = root / "corridor"
            corridor.mkdir()
            (root / "method" / "METHOD.md").write_text(
                "method\n", encoding="utf-8"
            )
            ledger = {
                "schema_version": contract.ACCEPTANCE_SCHEMA,
                "coverage": {
                    "status": "complete",
                    "unmapped_clauses": [],
                    "ambiguous_clauses": [
                        {
                            "source_ref": "instruction.md#output",
                            "statement": "Write the output using the public ABI.",
                            "reason": "The ABI version is not stated.",
                        }
                    ],
                },
                "construction_readiness": {
                    "status": "unresolved",
                    "coupled_acceptance_ids": ["ACCEPT-1"],
                    "replay_entrypoint": "",
                    "unresolved_constraints": ["The ABI version is unknown."],
                },
                "items": [
                    {
                        "acceptance_id": "ACCEPT-1",
                        "source_ref": "instruction.md#output",
                        "statement": "Write the required output.",
                        "required": True,
                        "definition_state": "ambiguous",
                        "scope": {"path": "/app/output.json"},
                        "rule": {"kind": "file_exists"},
                        "relations": [],
                        "verification_obligations": {
                            "positive": ["file exists"],
                            "negative": ["missing file is rejected"],
                            "boundary": ["empty file boundary is checked"],
                            "state": ["before/after file state is checked"],
                            "temporal": ["write precedes verification"],
                            "coupled": ["single requirement; explicit not applicable"],
                        },
                    }
                ],
            }
            (corridor / "ACCEPTANCE.json").write_text(
                json.dumps(ledger), encoding="utf-8"
            )

            completed = subprocess.run(
                [sys.executable, "-c", contract.freeze_program(str(root))],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            identity = json.loads(completed.stdout)
            self.assertEqual("incomplete", identity["acceptance_ledger_status"])
            self.assertEqual("complete", identity["source_mapping_status"])
            self.assertEqual("incomplete", identity["definition_closure_status"])
            self.assertEqual([], identity["acceptance_ledger_errors"])

    def test_task_deadline_terminates_resistant_child_before_archive(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        events: list[str] = []

        class ResistantAgent:
            _OUTPUT_FILENAME = "codex-worker.txt"

            def begin_phase(self, phase: str) -> None:
                events.append(f"begin:{phase}")
                self.remote_alive = False

            async def run(self, prompt, environment, context) -> None:
                self.remote_alive = True
                events.append("remote_started")
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    events.append("host_cancelled_remote_still_alive")
                    raise

            async def ensure_phase_quiescent(
                self, environment, *, terminate: bool
            ) -> dict[str, object]:
                events.append("terminate_exact_remote_tree")
                initial = [4242] if self.remote_alive else []
                self.remote_alive = False
                return {
                    "initial_pids": initial,
                    "remaining_pids": [],
                    "quiescent": True,
                }

        async def scenario() -> dict[str, object]:
            owner = object.__new__(adapter.ChartingLoopFullMethodAgent)
            loop = asyncio.get_running_loop()

            async def reset(environment) -> None:
                events.append("reset")

            async def archive(environment, role, output_filename) -> None:
                events.append("archive")

            owner._reset_live_session = reset
            owner._archive_role = archive
            _, outcome = await owner._run_new_role(
                "worker",
                ResistantAgent(),
                "do the task",
                object(),
                deadline=loop.time() + 0.01,
            )
            return outcome

        outcome = asyncio.run(scenario())
        self.assertEqual("task_deadline_reached", outcome["status"])
        self.assertEqual("task", outcome["deadline_scope"])
        self.assertTrue(outcome["quiescent"])
        self.assertTrue(outcome["archived"])
        self.assertLess(
            events.index("terminate_exact_remote_tree"), events.index("archive")
        )
        self.assertIn("host_cancelled_remote_still_alive", events)

    def test_owned_phase_disables_descendant_python_bytecode_writes(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        agent = object.__new__(adapter._PhaseCodex)
        agent._phase_label = "worker"
        agent._phase_token = "phase-token"
        agent._phase_token_hash = "sha256:" + "a" * 64
        agent._phase_identity_path = "/tmp/phase-identity.json"

        command = agent._owned_command(
            "codex exec --dangerously-bypass-approvals-and-sandbox --json -- task"
        )

        bytecode_export = "export PYTHONDONTWRITEBYTECODE=1;"
        self.assertIn(bytecode_export, command)
        self.assertLess(command.index(bytecode_export), command.index("setsid sh -c"))

    def test_phase_cancellation_cleans_up_and_unproven_quiescence_fails_closed(
        self,
    ) -> None:
        adapter = load_harbor_agent_with_stubs()

        class CancelledAgent:
            _OUTPUT_FILENAME = "codex-builder.txt"

            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.cleaned = False

            def begin_phase(self, phase: str) -> None:
                pass

            async def run(self, prompt, environment, context) -> None:
                self.started.set()
                await asyncio.Event().wait()

            async def ensure_phase_quiescent(
                self, environment, *, terminate: bool
            ) -> dict[str, object]:
                self.cleaned = True
                return {"remaining_pids": [], "quiescent": True}

        async def cancellation_scenario() -> bool:
            owner = object.__new__(adapter.ChartingLoopFullMethodAgent)
            agent = CancelledAgent()
            loop = asyncio.get_running_loop()

            async def reset(environment) -> None:
                pass

            async def archive(environment, role, output_filename) -> None:
                pass

            owner._reset_live_session = reset
            owner._archive_role = archive
            task = asyncio.create_task(
                owner._run_new_role(
                    "builder",
                    agent,
                    "build",
                    object(),
                    deadline=loop.time() + 30,
                )
            )
            await agent.started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            return agent.cleaned

        self.assertTrue(asyncio.run(cancellation_scenario()))

        context = adapter.AgentContext()
        metadata = {"phase_runs": [], "phase_events": []}
        with self.assertRaisesRegex(RuntimeError, "quiescence could not be proven"):
            adapter.ChartingLoopFullMethodAgent._record_phase_outcome(
                metadata,
                {
                    "phase": "worker",
                    "status": "isolation_failed",
                    "quiescent": False,
                },
                context,
            )

    def test_qa_fact_admission_requires_valid_failure_and_verified_worker_snapshot(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        owner = object.__new__(adapter.ChartingLoopFullMethodAgent)
        assessment = {"witnesses": [{"acceptance_id": "ACCEPT-1"}]}

        async def exercise(decision: dict[str, object], candidate_ref: str | None):
            return await owner._admit_qa_witnesses(
                object(),
                assessment=assessment,
                decision=decision,
                candidate_ref=candidate_ref,
                corridor_digest="sha256:" + "a" * 64,
                guide={},
            )

        invalid = asyncio.run(
            exercise({"valid": False, "outcome": "not_assessed"}, "worker-000001")
        )
        self.assertEqual("invalid_assessment", invalid["status"])
        self.assertEqual(0, invalid["admitted"])

        passed = asyncio.run(
            exercise({"valid": True, "outcome": "pass"}, "worker-000001")
        )
        self.assertEqual("non_failure_assessment", passed["status"])
        self.assertEqual(0, passed["admitted"])

        no_snapshot = asyncio.run(
            exercise({"valid": True, "outcome": "fail"}, None)
        )
        self.assertEqual("no_verified_worker_snapshot", no_snapshot["status"])
        self.assertEqual(0, no_snapshot["admitted"])

    def test_harbor_adapter_preserves_role_and_verifier_boundaries(self) -> None:
        source = (REPOSITORY_ROOT / "benchmark_agents" / "harbor_agent.py").read_text(
            encoding="utf-8"
        )
        for marker in (
            "builder_prompt(",
            "worker_prompt(",
            "qa_prompt(",
            "repair_prompt(",
            "closure_prompt(",
            "await agent.resume(",
            'self._resume_role(\n                "worker",\n                worker,',
            'self._resume_role(',
            'decision["repair_required"]',
            "subagent_trajectories",
            "CHARTING_LOOP_PHASE_TOKEN",
            "setsid sh -c",
            "Phase process quiescence could not be proven",
            "regular_tree_manifest(self._sdk_source)",
            "Corridor SDK upload digest mismatch",
            "python3 -m corridor_kit validate-work",
            "work_validation_ok",
            "run_initialized",
            "runtime_guide_projections",
            "position_timeline_errors",
            '"deadline_policy": "single_task_deadline"',
            "FINALIZATION_RESERVE_SECONDS",
            "_restore_latest_worker_submission",
            "submission restore",
            "_validate_qa_presubmit",
            "_worker_revision_progress",
            "_archive_private_custody",
            "private_custody_",
            "_builder_freeze_metrics",
            '"first_valid_freeze_elapsed_seconds"',
            "_prepare_worker_fact_path",
            "_admit_fact_file",
            "_admit_qa_witnesses",
            "QA_FAILURE_WITNESS_NOT_ADMITTED_AS_FACT",
            '"mode": "exact_frozen_bytes"',
        ):
            self.assertIn(marker, source)
        self.assertNotIn("PHASE_TIMEOUT_SECONDS", source)
        self.assertNotIn('"phase_timeout_seconds"', source)
        self.assertNotIn("verifier.run", source)


    def test_graph_study_profiles_are_matched_except_condition(self) -> None:
        common = {
            "task_instruction": "Repair the task in 1800 seconds.",
            "model_name": "openai/gpt-5.6-sol",
            "task_timeout_seconds": 1800,
            "agent_version": "1.1.0",
            "kit_version": "0.7.0",
            "kit_tree_digest": "sha256:" + "7" * 64,
        }
        treatment = contract.graph_study_profile(arm="method", **common)
        control = contract.graph_study_profile(arm="neutral", **common)
        for profile in (treatment, control):
            self.assertFalse(profile["builder_present"])
            self.assertTrue(profile["qa_can_recommend_repair"])
            self.assertFalse(profile["qa_can_repair"])
            self.assertEqual(profile["repair_actor"], "same_worker_session")
            self.assertEqual(profile["roles"], ["worker", "qa"])
            self.assertEqual(profile["task_clock_roles"], ["worker", "qa"])
            self.assertEqual(
                profile["qa_schedule"], "in_clock_after_each_worker_freeze"
            )
            self.assertFalse(profile["qa_budget_is_separate"])
            self.assertIsNone(profile["phase_time_allocations"])
            self.assertEqual(
                profile["submission_rule"],
                "latest_valid_worker_freeze_before_official_verifier",
            )
            self.assertEqual(
                profile["official_verifier_schedule"], "after_agent_return"
            )
            self.assertTrue(profile["graph_is_advisory"])
            self.assertFalse(profile["graph_authorizes_mutation"])
        treatment_shared = {
            key: value
            for key, value in treatment.items()
            if key not in {"condition", "profile_digest"}
        }
        control_shared = {
            key: value
            for key, value in control.items()
            if key not in {"condition", "profile_digest"}
        }
        self.assertEqual(treatment_shared, control_shared)
        self.assertEqual(treatment["condition"]["kind"], "frozen_method")
        self.assertEqual(
            control["condition"]["digest"],
            contract.NEUTRAL_GRAPH_INSTRUCTION_SHA256,
        )

    def test_graph_prompts_have_no_builder_and_use_in_clock_witnessed_repair(self) -> None:
        method_text = (REPOSITORY_ROOT / "method-paper" / "METHOD.md").read_text(
            encoding="utf-8"
        )
        digest = "sha256:" + "8" * 64
        treatment = contract.graph_worker_prompt(
            "Repair the public task.",
            arm="method",
            study_profile_digest=digest,
            remaining_seconds=1700,
            method_text=method_text,
        )
        control = contract.graph_worker_prompt(
            "Repair the public task.",
            arm="neutral",
            study_profile_digest=digest,
            remaining_seconds=1700,
            method_text=None,
        )
        for prompt in (treatment, control):
            self.assertIn("There is no Builder phase", prompt)
            self.assertIn("corridor_kit graph append", prompt)
            self.assertIn(contract.GRAPH_PATH, prompt)
            self.assertIn("You choose Direction", prompt)
            self.assertIn("invalid graph mutation", prompt)
            self.assertIn("submission freeze", prompt)
            self.assertIn("first complete, locally verified, scorable freeze", prompt)
            self.assertIn("same total task clock", prompt)
            self.assertIn("acceptance_checklist_item", prompt)
            self.assertIn("typed_dependency", prompt)
            self.assertIn("checkpoint_kind", prompt)
            self.assertIn("graph doctor", prompt)
            self.assertIn("structurally_valid_but_incomplete", prompt)
        self.assertIn(method_text, treatment)
        self.assertNotIn(method_text, control)
        qa = contract.graph_qa_prompt(
            "Repair the public task.",
            arm="method",
            study_profile_digest=digest,
            graph_digest="sha256:" + "9" * 64,
            latest_worker_snapshot_ref="worker-000001-example",
            remaining_seconds=200,
            method_text=method_text,
            study_profile_path="/audit/STUDY.json",
            graph_path="/audit/GRAPH.jsonl",
            qa_output_path=None,
            audit_iteration=2,
        )
        self.assertIn("advisory QA", qa)
        self.assertIn("you must not\nmutate", qa)
        self.assertIn("official verifier has not run yet", qa)
        self.assertIn("same total task clock", qa)
        self.assertIn("audit iteration 2", qa)
        self.assertIn("replayable witness", qa)
        self.assertIn("candidate_ref", qa)
        self.assertIn("submission verify", qa)
        self.assertIn(contract.SUBMISSION_ROOT, qa)
        self.assertIn("snapshots/worker/worker-000001-example", qa)
        self.assertIn("Return exactly one JSON object", qa)
        self.assertIn(contract.GRAPH_AUDIT_SCHEMA, qa)
        self.assertIn("recompute", qa.lower())
        self.assertIn("invalidation closure", qa)
        self.assertIn("not a QA verdict", qa)
        repair = contract.graph_repair_prompt(
            "Repair the public task.",
            arm="method",
            study_profile_digest=digest,
            graph_digest="sha256:" + "9" * 64,
            audited_snapshot_ref="worker-000001-example",
            qa_path="/audit/qa.json",
            remaining_seconds=120,
            method_text=method_text,
        )
        self.assertIn("SAME Worker", repair)
        self.assertIn("Reproduce every witness", repair)
        self.assertIn("Never overwrite or invalidate the prior freeze", repair)
        self.assertIn("same total task clock", repair)
        self.assertIn("re-project invalidated checklist assessments", repair)
        self.assertIn("graph doctor", repair)

    def test_graph_revision_binds_matching_prefreeze_and_qa_intake_doctor_reports(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        agent = object.__new__(adapter.ChartingLoopGraphKernelNeutralAgent)
        doctor_calls: list[str] = []
        writes: list[dict] = []
        digest = "sha256:" + "d" * 64

        async def doctor(self, environment, *, graph_path):
            doctor_calls.append(graph_path)
            return {
                "schema_version": "charting-loop/graph-doctor-report/v1",
                "classification": "structurally_valid_but_incomplete",
                "structurally_valid": True,
                "graph_digest": "sha256:" + "a" * 64,
                "graph_bytes_digest": digest,
                "doctor_code_digest": "sha256:" + "b" * 64,
                "report_digest": "sha256:" + "c" * 64,
                "head_record_id": "sha256:" + "e" * 64,
                "record_count": 4,
                "latest_position_ref": "sha256:" + "f" * 64,
                "direction_digest": "sha256:" + "1" * 64,
                "acceptance_root": "sha256:" + "2" * 64,
            }

        async def exec_root(self, environment, *, command):
            return types.SimpleNamespace(return_code=0, stdout="", stderr="")

        async def write(self, environment, *, path, value):
            writes.append(value)

        agent._graph_doctor_report = types.MethodType(doctor, agent)
        agent.exec_as_root = types.MethodType(exec_root, agent)
        agent._write_root_json = types.MethodType(write, agent)
        report = asyncio.run(
            agent._freeze_graph_revision(
                object(), iteration=1, worker_snapshot_ref="worker-000001-example"
            )
        )

        self.assertTrue(report["ok"])
        self.assertEqual(2, len(doctor_calls))
        self.assertEqual(adapter.GRAPH_PATH, doctor_calls[0])
        self.assertTrue(doctor_calls[1].endswith("/GRAPH.jsonl"))
        self.assertTrue(report["exact_graph_bytes_match"])
        self.assertEqual("structurally_valid_but_incomplete", report["doctor_classification"])
        self.assertEqual("sha256:" + "f" * 64, report["position_ref"])
        self.assertEqual("sha256:" + "1" * 64, report["direction_digest"])
        self.assertEqual("sha256:" + "2" * 64, report["acceptance_root"])
        self.assertEqual(report["doctor_report_digest"], writes[0]["doctor_report_digest"])

    def test_invalid_graph_revision_is_retained_read_only_without_blocking_fallback(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        agent = object.__new__(adapter.ChartingLoopGraphKernelNeutralAgent)
        writes: list[tuple[str, dict]] = []
        commands: list[str] = []

        async def doctor(self, environment, *, graph_path):
            return {
                "schema_version": "charting-loop/graph-doctor-report/v1",
                "classification": "structurally_invalid",
                "structurally_valid": False,
                "graph_digest": None,
                "graph_bytes_digest": "sha256:" + "d" * 64,
                "doctor_code_digest": "sha256:" + "b" * 64,
                "report_digest": "sha256:" + "c" * 64,
                "errors": ["generic structural defect"],
                "authorizes_mutation": False,
                "blocking_gate": False,
                "pass_assessed": False,
            }

        async def exec_root(self, environment, *, command):
            commands.append(command)
            return types.SimpleNamespace(return_code=0, stdout="", stderr="")

        async def write(self, environment, *, path, value):
            writes.append((path, value))

        agent._graph_doctor_report = types.MethodType(doctor, agent)
        agent.exec_as_root = types.MethodType(exec_root, agent)
        agent._write_root_json = types.MethodType(write, agent)
        report = asyncio.run(
            agent._freeze_graph_revision(
                object(), iteration=2, worker_snapshot_ref="worker-000002-example"
            )
        )

        self.assertFalse(report["ok"])
        self.assertEqual("graph_revision_invalid", report["status"])
        self.assertTrue(report["manifest_path"].endswith("/GRAPH-FREEZE.json"))
        self.assertEqual(report["manifest_path"], writes[0][0])
        self.assertEqual("graph_revision_invalid", writes[0][1]["status"])
        self.assertIn("chmod 0444", commands[-1])
        self.assertIn("chmod 0555", commands[-1])

    def test_graph_audit_is_identity_bound_and_requires_replayable_repair_witness(self) -> None:
        snapshot_ref = "worker-000001-example"
        value = {
            "schema_version": contract.GRAPH_AUDIT_SCHEMA,
            "study_profile_digest": "sha256:" + "a" * 64,
            "graph_digest": "sha256:" + "b" * 64,
            "snapshot_ref": snapshot_ref,
            "path_assessment": "drifted",
            "repair_recommended": True,
            "witnesses": [
                {
                    "witness_id": "W-1",
                    "category": "direction",
                    "observation": "D-1 used a stale Position.",
                    "expected": "Direction must bind the latest Position.",
                    "evidence_ref": "graph:record-7",
                    "replay": "Replay graph and compare D-1.position_ref.",
                    "position_ref": "sha256:" + "c" * 64,
                    "candidate_ref": snapshot_ref,
                }
            ],
            "scope_limitations": ["official grader not inspected"],
        }
        self.assertEqual(
            contract.validate_graph_audit(
                value,
                study_profile_digest="sha256:" + "a" * 64,
                graph_digest="sha256:" + "b" * 64,
                snapshot_ref=snapshot_ref,
            ),
            [],
        )
        value["graph_digest"] = "sha256:" + "c" * 64
        self.assertIn(
            "GRAPH_AUDIT_GRAPH_IDENTITY",
            contract.validate_graph_audit(
                value,
                study_profile_digest="sha256:" + "a" * 64,
                graph_digest="sha256:" + "b" * 64,
                snapshot_ref=snapshot_ref,
            ),
        )
        value["graph_digest"] = "sha256:" + "b" * 64
        value["witnesses"] = []
        self.assertIn(
            "GRAPH_AUDIT_REPAIR_WITNESS_REQUIRED",
            contract.validate_graph_audit(
                value,
                study_profile_digest="sha256:" + "a" * 64,
                graph_digest="sha256:" + "b" * 64,
                snapshot_ref=snapshot_ref,
            ),
        )
        value["path_assessment"] = "coherent"
        self.assertIn(
            "GRAPH_AUDIT_REPAIR_OUTCOME_CONTRADICTION",
            contract.validate_graph_audit(
                value,
                study_profile_digest="sha256:" + "a" * 64,
                graph_digest="sha256:" + "b" * 64,
                snapshot_ref=snapshot_ref,
            ),
        )

    def test_graph_agent_profiles_use_one_in_clock_worker_qa_repair_loop(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        method = object.__new__(adapter.ChartingLoopGraphKernelMethodAgent)
        neutral = object.__new__(adapter.ChartingLoopGraphKernelNeutralAgent)
        self.assertEqual(method.version(), "1.1.0")
        self.assertEqual(neutral.version(), "1.1.0")
        self.assertEqual(method.ROLE_SEQUENCE, ("worker", "qa"))
        self.assertEqual(neutral.ROLE_SEQUENCE, ("worker", "qa"))
        self.assertIn("Worker freeze", method.ORCHESTRATION_MESSAGE)
        self.assertIn("same-Worker", method.ORCHESTRATION_MESSAGE)
        self.assertIn("official scoring", method.ORCHESTRATION_MESSAGE)
        self.assertNotEqual(method.name(), neutral.name())
        source = (REPOSITORY_ROOT / "benchmark_agents" / "harbor_agent.py").read_text(
            encoding="utf-8"
        )
        for marker in (
            '"deadline_policy": "single_task_deadline"',
            '"phase_time_allocations": None',
            "while _remaining_seconds(execution_deadline) > 0",
            "_freeze_graph_revision(",
            'self._resume_role(\n                        "qa"',
            'self._resume_role(\n                "worker"',
            "graph_repair_prompt(",
            '"target.write_bytes(source.read_bytes()); target.chmod(0o444)"',
            'f"chmod 0555 {shlex.quote(revision_root.as_posix())}"',
            "_restore_latest_worker_submission(",
            '"agent_returned_for_grading"',
        ):
            self.assertIn(marker, source)

    def test_graph_agent_audits_each_freeze_before_returning_for_verification(self) -> None:
        adapter = load_harbor_agent_with_stubs()
        agent = object.__new__(adapter.ChartingLoopGraphKernelNeutralAgent)
        agent.model_name = "openai/gpt-5.6-sol"
        agent._sdk_identity = {
            "kit_version": "0.7.0",
            "tree_digest": "sha256:" + "7" * 64,
        }
        roles = {"worker": object(), "qa": object()}
        agent._child_agent = lambda role: roles[role]
        events: list[str] = []
        state = {"worker_snapshot": "worker-000001-a"}

        async def write_root_json(self, environment, *, path, value):
            events.append("study-frozen")

        async def run_new(self, role, child, prompt, environment, *, deadline):
            events.append(f"{role}-new")
            return adapter.AgentContext(), {
                "phase": role,
                "role": role,
                "status": "completed",
                "quiescent": True,
            }

        async def resume(self, role, child, prompt, environment, *, phase, deadline):
            events.append(f"{role}-resume")
            if role == "worker":
                state["worker_snapshot"] = "worker-000002-b"
            return adapter.AgentContext(), {
                "phase": phase,
                "role": role,
                "status": "completed",
                "quiescent": True,
            }

        async def progress(self, environment):
            return {
                "available": True,
                "snapshot_count": 1,
                "snapshots": [{"snapshot_id": state["worker_snapshot"]}],
            }

        async def freeze_graph(self, environment, *, iteration, worker_snapshot_ref):
            events.append(f"graph-freeze-{iteration}:{worker_snapshot_ref}")
            return {
                "ok": True,
                "graph_path": f"/audit/graph-{iteration}.jsonl",
                "graph_digest": "sha256:" + str(iteration) * 64,
            }

        async def open_qa(self, environment):
            events.append("qa-open")

        async def seal_qa(self, environment):
            events.append("qa-seal")

        async def freeze_submission(self, environment, *, role, paths):
            events.append(f"{role}-report-frozen")
            return {"ok": True, "role": role}

        async def read_audit(
            self,
            environment,
            *,
            path,
            study_profile_digest,
            graph_digest,
            snapshot_ref,
        ):
            repair = snapshot_ref == "worker-000001-a"
            events.append(f"qa-decision:{snapshot_ref}:{repair}")
            return {"snapshot_ref": snapshot_ref}, {
                "valid": True,
                "errors": [],
                "path_assessment": "drifted" if repair else "coherent",
                "repair_required": repair,
                "advisory_only": True,
                "blocking_gate": False,
                "authorizes_mutation": False,
            }

        async def seal_graph(self, environment):
            events.append("final-graph-sealed")
            return {
                "corridor_digest": "sha256:" + "c" * 64,
                "graph_bytes_digest": "sha256:" + "d" * 64,
                "graph_validation": {"ok": True},
                "graph_structurally_valid": True,
            }

        async def restore(self, environment):
            events.append("latest-worker-restored")
            return {"ok": True, "snapshot_id": state["worker_snapshot"]}

        for name, function in (
            ("_write_root_json", write_root_json),
            ("_run_new_role", run_new),
            ("_resume_role", resume),
            ("_worker_revision_progress", progress),
            ("_freeze_graph_revision", freeze_graph),
            ("_open_qa_directory", open_qa),
            ("_seal_qa_directory", seal_qa),
            ("_freeze_submission_paths", freeze_submission),
            ("_read_graph_audit", read_audit),
            ("_seal_graph_corridor", seal_graph),
            ("_restore_latest_worker_submission", restore),
        ):
            setattr(agent, name, types.MethodType(function, agent))

        context = adapter.AgentContext()
        asyncio.run(
            agent._run_task(
                "You have 100 seconds to complete the official task.",
                object(),
                context,
            )
        )

        self.assertEqual(
            events,
            [
                "study-frozen",
                "worker-new",
                "graph-freeze-1:worker-000001-a",
                "qa-open",
                "qa-new",
                "qa-report-frozen",
                "qa-seal",
                "qa-decision:worker-000001-a:True",
                "worker-resume",
                "graph-freeze-2:worker-000002-b",
                "qa-open",
                "qa-resume",
                "qa-report-frozen",
                "qa-seal",
                "qa-decision:worker-000002-b:False",
                "final-graph-sealed",
                "latest-worker-restored",
            ],
        )
        self.assertEqual(context.metadata["qa_schedule"], "in_clock_after_each_worker_freeze")
        self.assertFalse(context.metadata["qa_budget_is_separate"])
        self.assertFalse(context.metadata["qa_can_repair"])
        self.assertEqual(context.metadata["repair_actor"], "same_worker_session")
        self.assertEqual(context.metadata["submission_fallback"]["snapshot_id"], "worker-000002-b")
        self.assertEqual(context.metadata["official_verifier_schedule"], "after_agent_return")
        self.assertEqual(context.metadata["phase_events"][-1], "agent_returned_for_grading")


if __name__ == "__main__":
    unittest.main()
