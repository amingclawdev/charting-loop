from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
DEMO_ROOT = REPOSITORY_ROOT / "demos" / "service-plan-corridor-e2e"
sys.path.insert(0, str(TOOLS_ROOT))

import corridor_runtime as runtime


class CorridorRuntimeDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        manifest_report, manifest = runtime.validate_demo_manifest(DEMO_ROOT)
        self.assertTrue(manifest_report.ok, manifest_report.errors)
        assert manifest is not None
        self.manifest = manifest
        self.expected = runtime.load_json(DEMO_ROOT / "expected" / "RUNTIME-EVIDENCE.json")
        self.generated = runtime.build_service_plan_bundle(DEMO_ROOT)

    def validate(self, value: object | None = None) -> runtime.ValidationReport:
        return runtime.validate_runtime_evidence(
            self.expected if value is None else value,
            manifest=self.manifest,
            demo_root=DEMO_ROOT,
        )

    @staticmethod
    def codes(report: runtime.ValidationReport) -> set[str]:
        return {error["code"] for error in report.errors}

    def test_checked_in_demo_and_golden_are_valid(self) -> None:
        report = self.validate()
        self.assertTrue(report.ok, report.errors)
        self.assertTrue(report.facts["task_pass"])
        self.assertTrue(report.facts["corridor_e2e_pass"])
        self.assertFalse(report.facts["benchmark_result"])
        self.assertFalse(report.facts["causal_claim_allowed"])
        self.assertEqual(report.facts["authority_log_status"], "not_assessed")
        self.assertEqual(report.facts["authority_warranty_count"], 3)

    def test_two_builds_and_golden_are_byte_identical(self) -> None:
        second = runtime.build_service_plan_bundle(DEMO_ROOT)
        self.assertEqual(
            runtime.canonical_json_bytes(self.generated),
            runtime.canonical_json_bytes(second),
        )
        self.assertEqual(
            runtime.canonical_json_bytes(self.generated),
            runtime.canonical_json_bytes(self.expected),
        )

    def test_runner_check_is_subscription_free_and_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(DEMO_ROOT / "run_demo.py"), "--check"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertTrue(result["task_pass"])
        self.assertTrue(result["corridor_e2e_pass"])
        self.assertFalse(result["benchmark_result"])

    def test_oversized_manifest_integer_fails_closed_in_api_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            demo_root = Path(temp_name) / "demo"
            shutil.copytree(DEMO_ROOT, demo_root)
            manifest_path = demo_root / "DEMO.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["environment"]["oversized_integer"] = 1 << runtime.MAX_JSON_INTEGER_BITS
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report, loaded = runtime.validate_demo_manifest(demo_root)
            self.assertFalse(report.ok)
            self.assertIsNone(loaded)
            self.assertIn("MALFORMED_DEMO_MANIFEST", self.codes(report))

            completed = subprocess.run(
                [sys.executable, str(TOOLS_ROOT / "corridor_runtime.py"), "build", str(demo_root)],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("Traceback", completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn(
                "MALFORMED_DEMO_MANIFEST",
                {error["code"] for error in payload["errors"]},
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "corridor_runtime.py"),
                    "validate",
                    str(demo_root / "expected" / "RUNTIME-EVIDENCE.json"),
                    "--demo-root",
                    str(demo_root),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("Traceback", completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn(
                "MALFORMED_DEMO_MANIFEST",
                {error["code"] for error in payload["errors"]},
            )

    def test_worldspan_cannot_cross_base_commit(self) -> None:
        value = copy.deepcopy(self.expected)
        value["world_refs"][1]["base_commit"] = "1" * 40
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertTrue({"WORLD_LINEAGE", "WORLDSPAN_LINEAGE"} & self.codes(report))

    def test_world_prefix_must_be_contiguous_and_hashed(self) -> None:
        value = copy.deepcopy(self.expected)
        value["world_refs"][1]["evidence_prefix"]["through_sequence"] = 2
        value["world_refs"][1]["evidence_prefix"]["prefix_sha256"] = "sha256:" + "0" * 64
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("WORLD_PREFIX_SEQUENCE", self.codes(report))
        self.assertIn("WORLD_PREFIX_HASH", self.codes(report))

    def test_boolean_prefix_is_not_an_integer(self) -> None:
        value = copy.deepcopy(self.expected)
        value["world_refs"][1]["evidence_prefix"]["through_sequence"] = True
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("INTEGER", self.codes(report))

    def test_complete_worldref_identity_components_fail_closed(self) -> None:
        mutations = (
            (("project_id",), "different-project", "WORLD_LINEAGE"),
            (("run_id",), "different-run", "WORLD_LINEAGE"),
            (("generation_id",), "generation-2", "WORLD_LINEAGE"),
            (("environment_sha256",), "sha256:" + "1" * 64, "WORLD_LINEAGE"),
            (("derived_state_sha256",), "sha256:" + "1" * 64, "WORLD_FACT_JOIN"),
            (("evidence_prefix", "admission", "rule_revision"), "2", "WORLD_LINEAGE"),
            (("evidence_prefix", "projector", "algorithm_version"), "2", "WORLD_LINEAGE"),
        )
        for path, replacement, expected_code in mutations:
            with self.subTest(path=path):
                value = copy.deepcopy(self.expected)
                target = value["world_refs"][1]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                report = self.validate(value)
                self.assertFalse(report.ok)
                self.assertIn(expected_code, self.codes(report))

    def test_timeline_presence_does_not_bypass_admission(self) -> None:
        value = copy.deepcopy(self.expected)
        admission = value["world_refs"][1]["evidence_prefix"]["admission"]
        admission["admitted_root_sha256"] = "sha256:" + "0" * 64
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("WORLD_ADMISSION_ROOT", self.codes(report))

    def test_actor_role_consumption_requires_dual_live_warranties(self) -> None:
        value = copy.deepcopy(self.expected)
        warranty = next(
            item
            for item in value["authority_warranties"]
            if item["warranty_id"] == "aw-r1-live-w1"
        )
        warranty["state"] = "lapsed"
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("GUIDE_DUAL_LIVE_WARRANTY", self.codes(report))

    def test_unknown_and_not_assessed_have_typed_refusals(self) -> None:
        for state, code in (("unknown", "unknown"), ("not_assessed", "not_assessed")):
            with self.subTest(state=state):
                value = copy.deepcopy(self.expected)
                warranty = next(
                    item for item in value["authority_warranties"]
                    if item["warranty_id"] == "aw-r1-live-w1"
                )
                warranty["state"] = state
                warranty["assessment_sha256"] = runtime.sha256_json(
                    {key: item for key, item in warranty.items() if key != "assessment_sha256"}
                )
                receipt = next(
                    item for item in value["guide_receipts"]
                    if item["receipt_id"] == "gr-r1-runtime-w1"
                )
                receipt["result"] = {
                    "kind": "typed-refusal",
                    "cardinality": 1,
                    "code": code,
                    "candidate_ref": receipt["candidate_ref"],
                    "expected_world_ref_id": receipt["world_ref_id"],
                    "actual_world_ref_id": receipt["world_ref_id"],
                }
                receipt["result_sha256"] = runtime.sha256_json(receipt["result"])
                report = self.validate(value)
                self.assertNotIn("GUIDE_TYPED_WARRANTY_REFUSAL", self.codes(report))

    def test_same_guide_context_cannot_change_result(self) -> None:
        value = copy.deepcopy(self.expected)
        receipt = next(
            record
            for record in value["guide_receipts"]
            if record["receipt_id"] == "gr-r0-runtime-w0"
        )
        receipt["result"]["entrance_id"] = "entrance:changed"
        receipt["result_sha256"] = runtime.sha256_json(receipt["result"])
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("GUIDE_NONDETERMINISTIC", self.codes(report))

    def test_cardinality_requires_exact_integer_one(self) -> None:
        for invalid in (True, 2, "1"):
            with self.subTest(invalid=invalid):
                value = copy.deepcopy(self.expected)
                value["guide_receipts"][0]["result"]["cardinality"] = invalid
                value["guide_receipts"][0]["result_sha256"] = runtime.sha256_json(
                    value["guide_receipts"][0]["result"]
                )
                report = self.validate(value)
                self.assertFalse(report.ok)
                self.assertIn("GUIDE_CARDINALITY", self.codes(report))

    def test_facade_interface_and_scope_are_pinned(self) -> None:
        value = copy.deepcopy(self.expected)
        for receipt in value["guide_receipts"]:
            result = receipt["result"]
            if result.get("kind") != "entrance":
                continue
            interface = result["instruction"]["facade"]["interface"]
            interface["operation"] = "search"
            interface["sha256"] = runtime.sha256_json(
                {key: item for key, item in interface.items() if key != "sha256"}
            )
            facade = result["instruction"]["facade"]
            facade["sha256"] = runtime.sha256_json(
                {key: item for key, item in facade.items() if key != "sha256"}
            )
            receipt["result_sha256"] = runtime.sha256_json(result)
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("GUIDE_INTERFACE_IDENTITY", self.codes(report))

    def test_stale_world_requires_typed_refusal_before_reentry(self) -> None:
        value = copy.deepcopy(self.expected)
        receipt = next(
            record
            for record in value["guide_receipts"]
            if record["receipt_id"] == "gr-r0-runtime-w1-refusal"
        )
        receipt["result"]["code"] = "continue_anyway"
        receipt["result_sha256"] = runtime.sha256_json(receipt["result"])
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertTrue({"GUIDE_REFUSAL", "DEMO_STALE_REFUSAL"} <= self.codes(report))

    def test_reentry_must_use_stale_source_warranty_and_new_revision(self) -> None:
        value = copy.deepcopy(self.expected)
        value["reentries"][0]["trigger_warranty_ref"] = "ew-r0-live-w0"
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("REENTRY_TRIGGER", self.codes(report))

    def test_certificate_rejects_bypass_even_when_record_is_rehashed(self) -> None:
        value = copy.deepcopy(self.expected)
        traversal = next(
            record
            for record in value["traversal_receipts"]
            if record["receipt_id"] == "tr-r0-canary"
        )
        traversal["bypass"] = True
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("CERTIFICATE_TRAVERSAL_STATE", self.codes(report))

    def test_warranty_scope_and_liveness_state_are_independent(self) -> None:
        value = copy.deepcopy(self.expected)
        warranty = next(
            record
            for record in value["evidential_warranties"]
            if record["warranty_id"] == "ew-r0-lapsed-w1"
        )
        warranty["state"] = "live"
        warranty["scope"] = "all-future-worlds"
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertTrue(
            {"WARRANTY_SCOPE", "WARRANTY_LIVE_WORLD", "GUIDE_DUAL_LIVE_WARRANTY"}
            & self.codes(report)
        )

    def test_receipts_do_not_change_candidate_semantic_identity(self) -> None:
        before = self.expected["candidate_projections"][0]
        value = copy.deepcopy(self.expected)
        value["guide_receipts"][0]["result"]["entrance_id"] = "changed"
        after = value["candidate_projections"][0]
        self.assertEqual(
            runtime.candidate_semantic_sha256(before),
            runtime.candidate_semantic_sha256(after),
        )
        self.assertEqual(before["semantic_sha256"], after["semantic_sha256"])

    def test_control_and_treatment_share_task_score_and_output(self) -> None:
        pair = self.expected["execution_pair"]
        self.assertEqual(pair["control"]["stage_instruction_sha256"], pair["treatment"]["stage_instruction_sha256"])
        self.assertEqual(pair["control"]["task_output"], pair["treatment"]["task_output"])
        self.assertEqual(pair["control"]["task_score"], pair["treatment"]["task_score"])
        self.assertTrue(pair["treatment"]["corridor_score"]["corridor_e2e_pass"])

    def test_optional_authority_log_absence_is_explicit_and_nonblocking(self) -> None:
        report = self.validate()
        self.assertTrue(report.ok)
        self.assertEqual(self.expected["authority_log_status"], "not_assessed")
        self.assertNotIn("authority_log", self.expected)

    def test_world_refs_must_join_the_frozen_demo_subject(self) -> None:
        value = copy.deepcopy(self.expected)
        for world in value["world_refs"]:
            world["repository_url"] = "https://example.invalid/alien"
            world["base_commit"] = "1" * 40
            world["environment_sha256"] = "sha256:" + "1" * 64
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("WORLD_MANIFEST_JOIN", self.codes(report))

    def test_candidate_projection_identity_is_frozen(self) -> None:
        value = copy.deepcopy(self.expected)
        candidate = value["candidate_projections"][0]
        candidate["builder_id"] = "replacement-builder"
        candidate["semantic_sha256"] = runtime.candidate_semantic_sha256(candidate)
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("CANDIDATE_FIXTURE_JOIN", self.codes(report))

    def test_candidate_ref_derives_from_candidate_and_revision(self) -> None:
        value = copy.deepcopy(self.expected)
        candidate = value["candidate_projections"][0]
        candidate["candidate_id"] = "alien-corridor"
        candidate["semantic_sha256"] = runtime.candidate_semantic_sha256(candidate)
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("CANDIDATE_REF", self.codes(report))

    def test_canary_must_consume_the_exact_guide_result(self) -> None:
        value = copy.deepcopy(self.expected)
        traversal = next(
            item
            for item in value["traversal_receipts"]
            if item["receipt_id"] == "tr-r0-canary"
        )
        traversal["events"] = [{"sequence": 1, "kind": "unrelated-noop"}]
        traversal["trace_sha256"] = runtime.sha256_json(traversal["events"])
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("TRAVERSAL_EVENT_JOIN", self.codes(report))

    def test_evidential_warranty_rule_must_resolve_to_candidate_direction_rule(self) -> None:
        value = copy.deepcopy(self.expected)
        warranty = next(
            item
            for item in value["evidential_warranties"]
            if item["warranty_id"] == "ew-r1-live-w1"
        )
        warranty["rule_ref"] = "undeclared-rule@999"
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("WARRANTY_RULE_JOIN", self.codes(report))

    def test_position_role_definition_must_resolve_to_its_rule(self) -> None:
        for mutation in ("missing", "mismatched"):
            with self.subTest(mutation=mutation):
                value = copy.deepcopy(self.expected)
                candidate = value["candidate_projections"][1]
                role_id = candidate["position"]["role_definition"]["role_definition_id"]
                role_rule = next(rule for rule in candidate["rules"] if rule["rule_id"] == role_id)
                if mutation == "missing":
                    candidate["rules"].remove(role_rule)
                else:
                    role_rule["role_id"] = "unrelated-role"
                candidate["semantic_sha256"] = runtime.candidate_semantic_sha256(candidate)
                report = self.validate(value)
                self.assertFalse(report.ok)
                self.assertIn("CANDIDATE_ROLE_DEFINITION_RULE", self.codes(report))

    def test_position_assignment_must_resolve_to_matching_admitted_fact(self) -> None:
        for mutation in ("missing", "mismatched"):
            with self.subTest(mutation=mutation):
                value = copy.deepcopy(self.expected)
                candidate = value["candidate_projections"][1]
                fact_id = candidate["position"]["role_assignment"]["assignment_fact_id"]
                assignment_fact = next(fact for fact in candidate["facts"] if fact["fact_id"] == fact_id)
                if mutation == "missing":
                    candidate["facts"].remove(assignment_fact)
                else:
                    assignment_fact["actor_id"] = "different-actor"
                    assignment_fact["fact_sha256"] = runtime.sha256_json(
                        {key: item for key, item in assignment_fact.items() if key != "fact_sha256"}
                    )
                candidate["semantic_sha256"] = runtime.candidate_semantic_sha256(candidate)
                report = self.validate(value)
                self.assertFalse(report.ok)
                self.assertIn("CANDIDATE_ASSIGNMENT_FACT", self.codes(report))

    def test_authority_warranty_cannot_bind_the_unrelated_direction_rule(self) -> None:
        value = copy.deepcopy(self.expected)
        candidate = value["candidate_projections"][1]
        direction_rule = next(
            rule for rule in candidate["rules"] if "acceptance_sha256" in rule
        )
        warranty = next(
            item
            for item in value["authority_warranties"]
            if item["warranty_id"] == "aw-r1-live-w1"
        )
        warranty["rule_ref"] = f"{direction_rule['rule_id']}@{direction_rule['version']}"
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("AUTHORITY_WARRANTY_RULE_JOIN", self.codes(report))

    def test_authority_warranty_must_bind_assignment_fact_authority_source(self) -> None:
        value = copy.deepcopy(self.expected)
        warranty = next(
            item
            for item in value["authority_warranties"]
            if item["warranty_id"] == "aw-r1-live-w1"
        )
        warranty["issuer_id"] = "unrelated-authority-source"
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("AUTHORITY_WARRANTY_FACT_AUTHORITY", self.codes(report))

    def test_evidential_warranty_binds_the_admitted_assignment_fact(self) -> None:
        value = copy.deepcopy(self.expected)
        warranty = next(
            item
            for item in value["evidential_warranties"]
            if item["warranty_id"] == "ew-r1-live-w1"
        )
        warranty["assignment_id"] = "assignment-from-another-candidate"
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("WARRANTY_ASSIGNMENT", self.codes(report))

    def test_warranty_prior_must_be_strictly_earlier(self) -> None:
        value = copy.deepcopy(self.expected)
        warranty = next(
            item
            for item in value["evidential_warranties"]
            if item["warranty_id"] == "ew-r0-lapsed-w1"
        )
        warranty["prior_assessment_ref"] = warranty["warranty_id"]
        warranty["assessment_sha256"] = runtime.sha256_json(
            {key: item for key, item in warranty.items() if key != "assessment_sha256"}
        )
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("WARRANTY_PRIOR_ORDER", self.codes(report))

    def test_u_states_bind_the_frozen_lifecycle_sequence(self) -> None:
        value = copy.deepcopy(self.expected)
        value["u_states"][0]["trigger"] = "already_charted"
        value["u_states"][0]["opens_candidate_ref"] = "candidate:service-plan-corridor@r1"
        value["u_states"][1]["trigger"] = "not_stale"
        value["u_states"][1]["opens_candidate_ref"] = "candidate:service-plan-corridor@r0"
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("U_STATE_SEQUENCE_JOIN", self.codes(report))

    def test_pair_instructions_join_the_frozen_task(self) -> None:
        value = copy.deepcopy(self.expected)
        replacement = ["sha256:" + "1" * 64, "sha256:" + "2" * 64]
        value["execution_pair"]["control"]["stage_instruction_sha256"] = replacement
        value["execution_pair"]["treatment"]["stage_instruction_sha256"] = replacement
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("PAIR_INSTRUCTION_JOIN", self.codes(report))

    def test_corridor_score_uses_the_closed_check_set(self) -> None:
        value = copy.deepcopy(self.expected)
        value["execution_pair"]["treatment"]["corridor_score"]["checks"] = {
            "anything": True
        }
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("CORRIDOR_E2E_PASS", self.codes(report))

    def test_malformed_nested_values_fail_closed(self) -> None:
        value = copy.deepcopy(self.expected)
        value["timeline_events"] = ["not-an-object"]
        report = self.validate(value)
        self.assertFalse(report.ok)
        self.assertIn("MALFORMED_RUNTIME_EVIDENCE", self.codes(report))

    def test_observed_pair_is_digest_bound_by_manifest(self) -> None:
        observed = self.manifest["observed_docker_pair"]
        pair = runtime.load_json(DEMO_ROOT / observed["path"])
        self.assertEqual(observed["content_sha256"], runtime.sha256_json(pair))
        self.assertEqual(observed["schema_version"], pair["schema_version"])

    def test_observed_pair_is_sanitized_and_keeps_excluded_attempt(self) -> None:
        pair = runtime.load_json(DEMO_ROOT / "examples" / "PAIR-RESULT.json")
        self.assertFalse(pair["benchmark_result"])
        self.assertFalse(pair["causal_claim_allowed"])
        self.assertEqual(pair["authority_warranty_state"], "not_assessed")
        self.assertEqual(pair["evidence_basis"], "runner-reported-no-raw-proof")
        self.assertFalse(pair["method_level_c_established"])
        self.assertFalse(pair["independent_verification_established"])
        self.assertFalse(pair["raw_evidence_published"])
        self.assertEqual(pair["valid_pair"], ["control-r1", "treatment-r2"])
        self.assertEqual(pair["excluded_attempts"][0]["id"], "treatment-r1")
        self.assertFalse(pair["excluded_attempts"][0]["included_in_pair"])
        serialized = runtime.canonical_json_bytes(pair).decode()
        for forbidden in (
            "/Users/",
            "/private/tmp/",
            "workspace_volume",
            '"container"',
            "Bearer ",
            "route_token",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_demo_tree_contains_no_runtime_secrets_or_logs(self) -> None:
        for path in DEMO_ROOT.rglob("*"):
            self.assertFalse(path.is_symlink(), path)
            if not path.is_file():
                continue
            self.assertNotEqual(path.name, "auth.json")
            self.assertNotEqual(path.suffix, ".jsonl")
            if path.suffix in {".json", ".py"}:
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/private/tmp/", text)
                self.assertNotIn("Bearer ", text)

    def test_output_is_written_only_to_caller_selected_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "bundle.json"
            completed = subprocess.run(
                [sys.executable, str(DEMO_ROOT / "run_demo.py"), "--output", str(output)],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                runtime.canonical_json_bytes(runtime.load_json(output)),
                runtime.canonical_json_bytes(self.expected),
            )


class UsageReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.measurement_plan = {
            "schema_version": runtime.MEASUREMENT_PLAN_SCHEMA,
            "usage_receipt_schema": runtime.USAGE_RECEIPT_SCHEMA,
            "package_cost_schema": runtime.PACKAGE_COST_SCHEMA,
            "required_usage_stages": list(runtime.USAGE_STAGES),
            "raw_evidence_profile": "complete-digest-bound",
            "independent_replay_required": True,
        }
        self.receipt = {
            "schema_version": runtime.USAGE_RECEIPT_SCHEMA,
            "receipt_id": "usage-attempt-1",
            "run_id": "run-1",
            "run_sha256": "sha256:" + "a" * 64,
            "session_id": "session-1",
            "attempt_id": "attempt-1",
            "measurement_plan_sha256": runtime.sha256_json(self.measurement_plan),
            "stages": [
                {
                    "stage": stage,
                    "stage_receipt_id": f"stage-{index}",
                    "attempt_id": f"attempt-{index}",
                    "retry_of_attempt_id": "attempt-1" if stage == "retry" else None,
                    "retry_of_stage": "guided_execution" if stage == "retry" else None,
                    "assessment_status": "measured",
                    "input_tokens": 100 + index,
                    "cached_input_tokens": 20,
                    "output_tokens": 50 + index,
                    "reasoning_output_tokens": 10,
                    "wall_time_ms": 1000 + index,
                    "tool_calls": index,
                }
                for index, stage in enumerate(runtime.USAGE_STAGES)
            ],
        }

    def test_measured_receipt_and_primary_package_cost(self) -> None:
        report = runtime.validate_usage_receipt(self.receipt)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["usage_status"], "measured")
        package = runtime.package_cost_from_usage(self.receipt, amortized_reuses=2)
        self.assertEqual(package["primary"]["missing_stages"], [])
        self.assertEqual(package["primary"]["input_tokens"], 406)
        self.assertEqual(package["primary"]["cached_input_tokens"], 80)
        self.assertEqual(package["secondary"]["execution_only"]["input_tokens"], 306)
        self.assertEqual(package["secondary"]["execution_only"]["missing_stages"], [])
        self.assertEqual(
            package["secondary"]["amortized"]["input_tokens"],
            {"numerator": 712, "denominator": 2},
        )
        self.assertTrue(package["secondary"]["non_additive"])

    def test_cached_and_reasoning_tokens_are_subsets(self) -> None:
        for field, parent, code in (
            ("cached_input_tokens", "input_tokens", "CACHED_INPUT_SUBSET"),
            ("reasoning_output_tokens", "output_tokens", "REASONING_OUTPUT_SUBSET"),
        ):
            with self.subTest(field=field):
                receipt = copy.deepcopy(self.receipt)
                receipt["stages"][0][field] = receipt["stages"][0][parent] + 1
                report = runtime.validate_usage_receipt(receipt)
                self.assertFalse(report.ok)
                self.assertIn(code, {error["code"] for error in report.errors})

    def test_unmeasured_stage_has_null_values_and_fail_closed_primary(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][3]["assessment_status"] = "not_assessed"
        for metric in runtime.USAGE_METRICS:
            receipt["stages"][3][metric] = None
        report = runtime.validate_usage_receipt(receipt)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["usage_status"], "incomplete")
        package = runtime.package_cost_from_usage(receipt)
        self.assertEqual(package["primary"]["missing_stages"], ["stage-3"])
        for metric in runtime.USAGE_METRICS:
            self.assertIsNone(package["primary"][metric])
            self.assertIsNone(package["secondary"]["execution_only"][metric])

    def test_unmeasured_stage_cannot_hide_non_null_usage(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][2]["assessment_status"] = "not_applicable"
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        self.assertIn(
            "USAGE_UNMEASURED_VALUE",
            {error["code"] for error in report.errors},
        )

    def test_stage_order_and_boolean_counts_fail_closed(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][0], receipt["stages"][1] = (
            receipt["stages"][1],
            receipt["stages"][0],
        )
        receipt["stages"][2]["tool_calls"] = True
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        codes = {error["code"] for error in report.errors}
        self.assertIn("USAGE_CORE_ORDER", codes)
        self.assertIn("INTEGER", codes)

    def test_execution_view_survives_missing_construction(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][0]["assessment_status"] = "not_assessed"
        for metric in runtime.USAGE_METRICS:
            receipt["stages"][0][metric] = None
        report = runtime.validate_usage_receipt(receipt)
        self.assertTrue(report.ok, report.errors)
        package = runtime.package_cost_from_usage(receipt, amortized_reuses=3)
        self.assertEqual(package["primary"]["missing_stages"], ["stage-0"])
        self.assertIsNone(package["primary"]["input_tokens"])
        self.assertEqual(package["secondary"]["execution_only"]["missing_stages"], [])
        self.assertEqual(package["secondary"]["execution_only"]["input_tokens"], 306)
        self.assertEqual(package["secondary"]["amortized"]["missing_stages"], ["stage-0"])
        self.assertIsNone(package["secondary"]["amortized"]["input_tokens"])

    def test_multiple_retries_are_retained_and_rooted_by_domain(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        construction_retry = copy.deepcopy(receipt["stages"][3])
        construction_retry.update(
            {
                "stage_receipt_id": "stage-4",
                "attempt_id": "attempt-4",
                "retry_of_attempt_id": "attempt-0",
                "retry_of_stage": "construction",
                "input_tokens": 7,
                "cached_input_tokens": 0,
                "output_tokens": 5,
                "reasoning_output_tokens": 0,
                "wall_time_ms": 11,
                "tool_calls": 1,
            }
        )
        receipt["stages"].append(construction_retry)
        report = runtime.validate_usage_receipt(receipt)
        self.assertTrue(report.ok, report.errors)
        package = runtime.package_cost_from_usage(receipt, amortized_reuses=2)
        self.assertEqual(package["primary"]["input_tokens"], 413)
        self.assertEqual(package["secondary"]["execution_only"]["input_tokens"], 306)
        self.assertEqual(
            package["secondary"]["amortized"]["input_tokens"],
            {"numerator": 719, "denominator": 2},
        )

    def test_retry_root_must_join_exact_core_attempt_and_stage(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][3]["retry_of_attempt_id"] = "attempt-0"
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        self.assertIn("RETRY_ROOT_JOIN", {error["code"] for error in report.errors})

    def test_no_retry_uses_explicit_not_applicable_record(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        retry = receipt["stages"][3]
        retry["assessment_status"] = "not_applicable"
        for metric in runtime.USAGE_METRICS:
            retry[metric] = None
        report = runtime.validate_usage_receipt(receipt)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.facts["usage_status"], "measured")
        package = runtime.package_cost_from_usage(receipt)
        self.assertEqual(package["primary"]["missing_stages"], [])
        self.assertEqual(package["primary"]["input_tokens"], 303)

    def test_core_stage_cannot_be_declared_not_applicable(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        core = receipt["stages"][0]
        core["assessment_status"] = "not_applicable"
        for metric in runtime.USAGE_METRICS:
            core[metric] = None
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        self.assertEqual(report.facts["usage_status"], "incomplete")
        self.assertIn(
            "CORE_STAGE_NOT_APPLICABLE",
            {error["code"] for error in report.errors},
        )
        package = runtime.package_cost_from_usage(receipt)
        self.assertEqual(package["primary"]["missing_stages"], ["stage-0"])
        self.assertIsNone(package["primary"]["input_tokens"])

    def test_no_retry_sentinel_cannot_coexist_with_other_retry_records(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        sentinel = receipt["stages"][3]
        sentinel["assessment_status"] = "not_applicable"
        for metric in runtime.USAGE_METRICS:
            sentinel[metric] = None
        second = copy.deepcopy(sentinel)
        second["stage_receipt_id"] = "stage-4"
        second["attempt_id"] = "attempt-4"
        receipt["stages"].append(second)
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        self.assertIn(
            "RETRY_NOT_APPLICABLE_CARDINALITY",
            {error["code"] for error in report.errors},
        )

    def test_extreme_integer_returns_range_error_without_raising(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][0]["input_tokens"] = 10**5000
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        self.assertIsNone(report.facts["receipt_sha256"])
        self.assertTrue(
            {"INTEGER_RANGE", "CANONICAL_JSON"}
            <= {error["code"] for error in report.errors}
        )

    def test_duplicate_attempt_and_stage_receipt_ids_fail(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["stages"][3]["attempt_id"] = "attempt-2"
        receipt["stages"][3]["stage_receipt_id"] = "stage-2"
        report = runtime.validate_usage_receipt(receipt)
        self.assertFalse(report.ok)
        codes = {error["code"] for error in report.errors}
        self.assertIn("DUPLICATE_ATTEMPT_ID", codes)
        self.assertIn("DUPLICATE_STAGE_RECEIPT_ID", codes)

    def test_malformed_scalar_ids_return_errors_without_raising(self) -> None:
        mutations = (
            (0, "stage", []),
            (0, "stage_receipt_id", []),
            (0, "attempt_id", {}),
            (0, "assessment_status", []),
            (1, "assessment_status", {}),
            (3, "retry_of_attempt_id", []),
            (3, "retry_of_stage", {}),
        )
        for index, key, replacement in mutations:
            with self.subTest(key=key):
                receipt = copy.deepcopy(self.receipt)
                receipt["stages"][index][key] = replacement
                report = runtime.validate_usage_receipt(receipt)
                self.assertFalse(report.ok)
                self.assertTrue(report.errors)

    def test_amortized_values_are_exact_for_huge_integers(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        huge = 10**400
        receipt["stages"][0]["input_tokens"] = huge
        package = runtime.package_cost_from_usage(receipt, amortized_reuses=7)
        value = package["secondary"]["amortized"]["input_tokens"]
        self.assertEqual(value["denominator"], 7)
        self.assertEqual(value["numerator"], 306 * 7 + huge)

    def test_amortized_reuse_one_preserves_exact_integer(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        exact = 9_007_199_254_740_993
        receipt["stages"][0]["input_tokens"] = exact
        package = runtime.package_cost_from_usage(receipt, amortized_reuses=1)
        value = package["secondary"]["amortized"]["input_tokens"]
        self.assertEqual(value, {"numerator": exact + 306, "denominator": 1})


if __name__ == "__main__":
    unittest.main()
