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
            "charting-loop-method-v7",
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

    def test_agent_is_bound_to_the_exact_frozen_v7_method(self) -> None:
        index = json.loads(
            (REPOSITORY_ROOT / "method-paper" / "VERSIONS.json").read_text(
                encoding="utf-8"
            )
        )
        versions = [
            version
            for version in index["versions"]
            if version["version_id"] == "charting-loop-method-v7"
        ]
        self.assertEqual(1, len(versions))
        version = versions[0]
        self.assertEqual("frozen", version["status"])
        self.assertTrue(version["study_eligible"])
        self.assertFalse(version["adoption_eligible"])
        self.assertEqual(
            "c68813cea1aa1d1eeaafde69a3f35f71ffab6d0d",
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

        v8 = next(
            item
            for item in index["versions"]
            if item["version_id"] == "charting-loop-method-v8"
        )
        self.assertEqual(
            "d63cd34c2f1b039ebf3d346d4da6fa6ec35126b7",
            v8["source_commit"],
        )
        self.assertNotEqual(version["content_sha256"], v8["content_sha256"])

        module = load_harbor_agent_with_stubs()
        resolved = module._resolve_frozen_method(REPOSITORY_ROOT)
        self.assertIsInstance(resolved, bytes)
        self.assertEqual(
            version["content_sha256"],
            "sha256:" + hashlib.sha256(resolved).hexdigest(),
        )
        self.assertNotEqual(
            resolved,
            (REPOSITORY_ROOT / version["path"]).read_bytes(),
        )

        source = (REPOSITORY_ROOT / "benchmark_agents" / "harbor_agent.py").read_text(
            encoding="utf-8"
        )
        for value in (
            "charting-loop-method-v7",
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
        worker = contract.worker_prompt(task, digest)
        qa = contract.qa_prompt(
            task,
            digest,
            acceptance_ledger_status="complete",
            expected_acceptance_ids=["ACCEPT-1"],
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
        self.assertIn("independent QA", qa)
        self.assertIn("Do not mutate", qa)
        self.assertIn(contract.QA_PATH, qa)
        self.assertIn(contract.ACCEPTANCE_PATH, worker)
        self.assertIn("ACCEPT-1", qa)
        self.assertIn("independently re-read", qa.lower())
        self.assertIn('"source_mapping_complete"', qa)
        self.assertIn('"definition_closure_complete"', qa)
        self.assertIn('"assessment_closure"', qa)
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
        self.assertIn("python3 -m corridor_kit capabilities builtins", prompt)
        self.assertIn("Dependencies must be acyclic", prompt)
        self.assertIn("Reminders are advisory", prompt)

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
            self.assertIn("manifest_file_mismatch", probe["violations"])
            self.assertIn("corridor_digest_mismatch", probe["violations"])

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
        ):
            self.assertIn(marker, source)
        self.assertNotIn("PHASE_TIMEOUT_SECONDS", source)
        self.assertNotIn('"phase_timeout_seconds"', source)
        self.assertNotIn("official verifier", source.lower())
        self.assertNotIn("verifier.run", source)


if __name__ == "__main__":
    unittest.main()
