#!/usr/bin/env python3
"""Run the task-neutral Corridor Kit v5 four-stage engineering demo."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


DEMO_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = DEMO_ROOT.parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from corridor_kit import (  # noqa: E402
    KIT_VERSION,
    CorridorKitError,
    append_graph_record,
    freeze_submission,
    graph_doctor,
    initialize_graph,
    restore_submission,
    sha256_bytes,
    sha256_json,
    verify_submission,
)
from corridor_kit.compiler import (  # noqa: E402
    SOURCE_WITNESS_FIELDS,
    SOURCE_WITNESS_KINDS,
    assemble_parallel_rule_ir,
    validate_source_partition_product,
)
from corridor_kit.graph import (  # noqa: E402
    EXECUTION_TEST_CONTRACT_SCHEMA,
    EXECUTION_TEST_QA_ASSESSMENT_SCHEMA,
    EXECUTION_TEST_RECEIPT_SCHEMA,
    freeze_rule_candidate,
    ratify_rule_candidate,
)


def _parallel_products() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    instruction = "Every demo item must be written and verified."
    instruction_bytes = instruction.encode("utf-8")
    instruction_digest = sha256_bytes(instruction_bytes)
    source = {
        "source_id": "SRC-DEMO",
        "source_ref": "demo:instruction",
        "plane": "normative_rule",
        "role": "instruction",
        "byte_status": "available",
        "byte_digest": instruction_digest,
        "byte_size": len(instruction_bytes),
        "media_type": "text/plain",
        "content_encoding": "utf-8",
        "content_utf8": instruction,
        "semantic_extraction_status": "complete",
        "extractor": {
            "identity": "charting-loop.demo-source-extractor",
            "version": "1",
            "digest": "sha256:" + "5" * 64,
        },
        "extraction_artifact": {
            "ref": "memory:demo:clauses",
            "digest": instruction_digest,
            "source_byte_digest": instruction_digest,
            "content_encoding": "utf-8",
            "content_utf8": instruction,
            "byte_size": len(instruction_bytes),
        },
    }
    authority = {
        "schema_version": "charting-loop/authority-snapshot/v3",
        "snapshot_id": "AUTHORITY-DEMO",
        "snapshot_revision": 1,
        "parent_snapshot_digest": None,
        "manifest_digest": None,
        "freeze_receipt": {
            "actor_role": "runner",
            "ref": "runner:demo-freeze",
            "digest": "sha256:" + "7" * 64,
        },
        "closure_status": "complete",
        "sources": [source],
    }
    authority_manifest = {
        "snapshot_id": authority["snapshot_id"],
        "snapshot_revision": authority["snapshot_revision"],
        "parent_snapshot_digest": authority["parent_snapshot_digest"],
        "sources": [
            {
                "source_id": source["source_id"],
                "source_ref": source["source_ref"],
                "plane": source["plane"],
                "role": source["role"],
                "byte_status": source["byte_status"],
                "byte_digest": source["byte_digest"],
                "byte_size": source["byte_size"],
                "media_type": source["media_type"],
                "semantic_extraction_status": source["semantic_extraction_status"],
                "extractor_digest": source["extractor"]["digest"],
                "extraction_artifact_digest": source["extraction_artifact"]["digest"],
            }
        ],
    }
    authority["manifest_digest"] = sha256_json(authority_manifest)
    authority["freeze_receipt"]["digest"] = sha256_json(
        {
            "actor_role": "runner",
            "ref": "runner:demo-freeze",
            "manifest_digest": authority["manifest_digest"],
        }
    )
    source_slice = {
        "slice_id": "SL-DEMO",
        "source_id": "SRC-DEMO",
        "byte_start": 0,
        "byte_end": len(instruction_bytes),
        "slice_digest": instruction_digest,
        "representation": "source_bytes",
    }
    clause = {
        "clause_id": "CLAUSE-DEMO",
        "clause_order_key": "CLAUSE-ORDER-0001",
        "source_slices": [source_slice],
        "clause_text": instruction,
        "clause_digest": instruction_digest,
        "requirement_level": "required",
        "mapping_status": "mapped",
        "rule_ids": ["R-DEMO"],
        "required_semantic_roles": [
            "condition",
            "domain",
            "evidence_requirement",
            "obligation",
            "outcome",
            "quantifier",
            "witness_requirement",
        ],
        "issue": "",
    }
    partition_manifest = {
        "schema_version": "charting-loop/source-partition-manifest/v1",
        "partition_id": "PARTITION-DEMO",
        "authority_snapshot_digest": sha256_json(authority),
        "lanes": [
            {
                "lane_id": "LANE-DEMO",
                "owner_clause_ids": ["CLAUSE-DEMO"],
                "boundary_clause_ids": [],
                "lane_kind": "global",
            }
        ],
        "dependency_stubs": [],
        "global_lane_id": "LANE-DEMO",
        "unresolved_clause_ids": [],
    }
    partition_product = validate_source_partition_product(
        {
            "schema_version": "charting-loop/source-partition-product/v1",
            "source_bundle": authority,
            "source_clause_inventory": [clause],
            "revision": {
                "revision_id": "IR-REV-DEMO",
                "revision_kind": "first_attempt",
                "parent_ir_digest": None,
                "qa_witness_refs": [],
            },
            "method_digest": "sha256:" + "2" * 64,
            "compiler_config_digest": "sha256:" + "3" * 64,
            "partition_manifest": partition_manifest,
        }
    )
    semantics = {
        "schema_version": "charting-loop/typed-rule-semantics/v5",
        "requirement_level": "required",
        "applicability": {"mode": "always", "predicate": "the demo runs"},
        "rule_kind": "conditional",
        "compilation_status": "complete",
        "compile_issues": [],
        "quantifier": {
            "mode": "all",
            "subject_axis": "item",
            "subjects": ["demo-item"],
            "domain_kind": "closed_enumeration",
            "domain_source": "public_source",
            "domain_predicate": "the one public demo item",
        },
        "conditions": [
            {
                "condition_id": "written-and-verified",
                "predicate": "the item is written",
                "expected_outcome": "the item is verified",
                "required_witness_operators": ["equals"],
                "condition_kind": "static",
                "predicate_spec": {
                    "schema_version": "charting-loop/typed-predicate/v1",
                    "predicate_id": "PRED-DEMO",
                    "operator": "equals",
                    "inputs": [
                        {
                            "variable_id": "input-demo",
                            "value_type": "string",
                            "source_slice_ids": ["SL-DEMO"],
                        }
                    ],
                    "outputs": [
                        {
                            "variable_id": "output-demo",
                            "value_type": "boolean",
                            "source_slice_ids": ["SL-DEMO"],
                        }
                    ],
                    "producer_refs": ["SL-DEMO"],
                    "precondition_rule_ids": [],
                    "dependency_refs": [],
                    "semantic_fields": {"source_meaning": instruction},
                },
            }
        ],
        "checklist_projection": {
            "projection_mode": "per_subject",
            "behavioral_partitions": ["positive", "boundary"],
            "evidence_requirement": "Replay the public demo item.",
            "decision_rule": {
                "pass": "the item is verified",
                "fail": "the item is not verified",
                "unknown": "verification is absent",
            },
        },
        "dependencies": [],
        "guidance": [
            {
                "guidance_id": "GUIDANCE-DEMO",
                "trigger": "before assessing this Rule",
                "action": "re-read its bound source slice",
                "source_slice_ids": ["SL-DEMO"],
            }
        ],
    }
    rule_product = {
        "schema_version": "charting-loop/rule-lane-product/v2",
        "partition_product_digest": sha256_json(partition_product),
        "rule_lane_bindings": [
            {
                "schema_version": "charting-loop/rule-lane-binding/v1",
                "lane_id": "LANE-DEMO",
                "rule_ids": ["R-DEMO"],
            }
        ],
        "rules": [
            {
                "rule_id": "R-DEMO",
                "statement": instruction,
                "source_clause_ids": ["CLAUSE-DEMO"],
                "source_slices": [
                    {"slice_id": "SL-DEMO", "semantic_role": role}
                    for role in (
                        "obligation",
                        "domain",
                        "quantifier",
                        "condition",
                        "outcome",
                        "evidence_requirement",
                        "witness_requirement",
                    )
                ],
                "semantics": semantics,
            }
        ],
    }
    input_envelope = {
        "schema_version": "charting-loop/source-witness-input-envelope/v1",
        "partition_manifest_digest": sha256_json(partition_manifest),
        "authority_snapshot_digest": sha256_json(authority),
        "lane_id": "LANE-DEMO",
        "source_clause_ids": ["CLAUSE-DEMO"],
        "source_slice_ids": ["SL-DEMO"],
    }
    witnesses = [
        {
            "schema_version": "charting-loop/source-witness/v1",
            "witness_ref": f"WIT-{kind.upper()}",
            "kind": kind,
            "source_clause_ids": ["CLAUSE-DEMO"],
            "source_slice_ids": ["SL-DEMO"],
            "operator": "equals",
            "input_case": {"subject_id": "demo-item", "case_kind": kind},
            "expected_relation": f"source requires the {kind} relation",
            "boundary_relation": "source boundary remains explicit",
        }
        for kind in sorted(SOURCE_WITNESS_KINDS)
    ]
    witness_product = {
        "schema_version": "charting-loop/witness-lane-product/v1",
        "partition_product_digest": sha256_json(partition_product),
        "partition_manifest_digest": sha256_json(partition_manifest),
        "authority_snapshot_digest": sha256_json(authority),
        "witness_lane_packages": [
            {
                "schema_version": "charting-loop/witness-lane-package/v1",
                "lane_id": "LANE-DEMO",
                "role_session_ref": "source-witness:demo",
                "visibility": {
                    "source_only": True,
                    "candidate_rule_visible": False,
                    "candidate_checklist_visible": False,
                    "candidate_witness_visible": False,
                    "input_envelope_digest": sha256_json(input_envelope),
                },
                "source_clause_ids": ["CLAUSE-DEMO"],
                "source_slice_ids": ["SL-DEMO"],
                "witnesses": witnesses,
            }
        ],
    }
    return partition_product, rule_product, witness_product


def _append_qa_assessment(
    graph_path: Path, *, contract_record: dict[str, Any]
) -> dict[str, Any]:
    assessment = {
        "schema_version": EXECUTION_TEST_QA_ASSESSMENT_SCHEMA,
        "contract_record_id": contract_record["record_id"],
        "contract_digest": contract_record["body"]["contract_digest"],
        "outcome": "pass",
        "findings": [],
    }
    assessment["assessment_digest"] = sha256_json(assessment)
    return append_graph_record(
        graph_path,
        record_type="execution_test_qa_assessment",
        actor="qa",
        body=assessment,
    )["record"]


def _append_receipt(
    graph_path: Path,
    *,
    contract_record: dict[str, Any],
    assessment_record: dict[str, Any],
    probe: dict[str, Any],
) -> None:
    receipt = {
        "schema_version": EXECUTION_TEST_RECEIPT_SCHEMA,
        "contract_record_id": contract_record["record_id"],
        "contract_digest": contract_record["body"]["contract_digest"],
        "probe_id": probe["probe_id"],
        "outcome": "passed",
        "pre_action_qa_status": "pass",
        "pre_action_qa_assessment_record_id": assessment_record["record_id"],
        "command_digest": sha256_json({"command": probe["command"]}),
        "result_digest": sha256_bytes(b"probe passed\n"),
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    append_graph_record(
        graph_path,
        record_type="execution_test_receipt",
        actor="worker",
        body=receipt,
    )


def run_demo() -> dict[str, Any]:
    partition, rule_product, witness_product = _parallel_products()

    legacy_product = json.loads(json.dumps(witness_product))
    legacy = legacy_product["witness_lane_packages"][0]["witnesses"][0]
    legacy["witness_id"] = legacy.pop("witness_ref")
    legacy["witness_class"] = legacy.pop("kind")
    legacy["expected_outcome"] = legacy.pop("expected_relation")
    try:
        assemble_parallel_rule_ir(partition, rule_product, legacy_product)
    except CorridorKitError as error:
        if "source witness has unknown or missing fields" not in str(error):
            raise
        legacy_rejected = True
    else:
        raise RuntimeError("the CL-151 legacy witness shape was not rejected")

    assembly = assemble_parallel_rule_ir(partition, rule_product, witness_product)
    report = assembly["compile_report"]
    if not report["compilation_complete"]:
        raise RuntimeError(f"canonical v5 compilation failed: {report['compile_issues']}")

    with tempfile.TemporaryDirectory(prefix="charting-loop-four-stage-") as raw:
        root = Path(raw)
        graph_path = root / "GRAPH.jsonl"
        initialize_graph(graph_path)
        candidate = freeze_rule_candidate(
            graph_path, typed_rule_ir=assembly["typed_rule_ir"]
        )
        closure = ratify_rule_candidate(
            graph_path,
            candidate_report_record_id=candidate["candidate_report_record_id"],
            candidate_report_digest=candidate["candidate_report_digest"],
            outcome="pass",
            findings=[],
            ratifier_ref="qa:local-demo",
        )
        if not closure["rule_closure_established"]:
            raise RuntimeError("compile QA did not establish RuleClosure")

        records = [
            json.loads(line)
            for line in graph_path.read_text(encoding="utf-8").splitlines()
        ]
        rule_record = next(
            item for item in records if item["record_type"] == "rule_proposal"
        )
        checklist_record = next(
            item
            for item in records
            if item["record_type"] == "acceptance_checklist_item"
        )
        checklist_id = checklist_record["body"]["checklist_item_id"]
        closure_digests = sorted(closure["rule_closure_digests"].values())
        witness_ids = sorted(
            item["witness_obligation_id"]
            for item in report["witness_obligation_templates"]
            if item["checklist_item_id"] == checklist_id
        )
        common_position = {
            "task_identity": {"task_ref": "demo/four-stage"},
            "scope": {"working_set": ["demo-output.txt"]},
            "role_assignments": {"executor": "worker", "reviewer": "qa"},
            "rule_record_ids": [rule_record["record_id"]],
            "rule_closure_digests": closure_digests,
            "artifact_record_ids": [],
            "checklist_item_ids": [checklist_id],
        }
        initial_position = append_graph_record(
            graph_path,
            record_type="position_checkpoint",
            actor="worker",
            body={
                **common_position,
                "position_id": "P-DEMO-READY",
                "previous_position_ref": None,
                "fact_receipt_ids": [],
                "checkpoint_kind": "row_progress",
                "ready_item_ids": [checklist_id],
                "blocked_item_ids": [],
                "unresolved_checklist_item_ids": [checklist_id],
                "checklist_assessments": {
                    checklist_id: {
                        "status": "unknown",
                        "applicability_status": "applicable",
                        "witness_fact_receipt_ids": [],
                    }
                },
            },
        )["record"]
        semantic_binding = {
            "position_ref": initial_position["record_id"],
            "rule_id": "R-DEMO",
            "rule_record_id": rule_record["record_id"],
            "semantic_edge_ids": [],
            "checklist_item_id": checklist_id,
            "witness_obligation_ids": witness_ids,
        }
        direction = append_graph_record(
            graph_path,
            record_type="direction_proposal",
            actor="worker",
            body={
                "direction_id": "D-DEMO-IMPLEMENT",
                "position_ref": initial_position["record_id"],
                "statement": "Implement and verify the source-bound demo item.",
                "rule_record_ids": [rule_record["record_id"]],
                "rule_closure_digests": closure_digests,
                "fact_receipt_ids": [],
                "evidence_refs": [],
                "checklist_item_ids": [checklist_id],
                "ready_item_ids": [checklist_id],
                "blocked_item_ids": [],
                "unresolved_checklist_item_ids": [checklist_id],
                "semantic_bindings": [semantic_binding],
            },
        )["record"]
        append_graph_record(
            graph_path,
            record_type="direction_snapshot",
            actor="runner",
            body={
                "position_ref": initial_position["record_id"],
                "direction_record_ids": [direction["record_id"]],
                "selected_direction_record_id": direction["record_id"],
            },
        )

        before_fixture = root / "before.json"
        after_fixture = root / "after.json"
        before_fixture.write_text('{"verified":false}\n', encoding="utf-8")
        after_fixture.write_text('{"verified":true}\n', encoding="utf-8")
        probes = []
        for kind, fixture in (
            ("positive", after_fixture),
            ("boundary", before_fixture),
        ):
            probes.append(
                {
                    "probe_id": f"PROBE-{kind.upper()}",
                    "checklist_item_id": checklist_id,
                    "case_kind": kind,
                    "source_slice_ids": ["SL-DEMO"],
                    "operator": "code_test",
                    "fixture_artifacts": [
                        {"path": str(fixture), "digest": sha256_bytes(fixture.read_bytes())}
                    ],
                    "command": f"python3 -m json.tool {fixture}",
                    "oracle": f"The {kind} source-bound case remains explicit.",
                    "dependency_refs": [],
                    "predecessor_probe_ids": (
                        [] if kind == "positive" else ["PROBE-POSITIVE"]
                    ),
                    "pre_action_status": "not_run_yet",
                    "applicability_predicate": None,
                    "non_applicability_fact_receipt_ids": [],
                    "unsupported_reason": None,
                }
            )
        contract_body = {
            "schema_version": EXECUTION_TEST_CONTRACT_SCHEMA,
            "contract_id": "EXECUTION-CONTRACT-DEMO",
            "position_ref": initial_position["record_id"],
            "direction_record_id": direction["record_id"],
            "execution_kind": "task_mutation",
            "selected_checklist_item_ids": [checklist_id],
            "selected_rule_record_ids": [rule_record["record_id"]],
            "semantic_edge_ids": [],
            "witness_obligation_ids": witness_ids,
            "probe_cases": probes,
            "exemption_reason": None,
        }
        contract_body["contract_digest"] = sha256_json(contract_body)
        contract_record = append_graph_record(
            graph_path,
            record_type="execution_test_contract",
            actor="worker",
            body=contract_body,
        )["record"]
        assessment_record = _append_qa_assessment(
            graph_path, contract_record=contract_record
        )
        for probe in probes:
            _append_receipt(
                graph_path,
                contract_record=contract_record,
                assessment_record=assessment_record,
                probe=probe,
            )

        output = root / "demo-output.txt"
        output.write_text("verified demo output\n", encoding="utf-8")
        submission_root = root / "submissions"
        frozen = freeze_submission(submission_root, role="worker", paths=[output])
        output.write_text("unfinished output\n", encoding="utf-8")
        restore_submission(submission_root, role="worker")
        if output.read_text(encoding="utf-8") != "verified demo output\n":
            raise RuntimeError("Worker freeze did not restore byte-identically")
        verified = verify_submission(submission_root, role="worker")

        fact = append_graph_record(
            graph_path,
            record_type="fact_proposal",
            actor="worker",
            body={
                "fact_id": "F-DEMO-VERIFIED",
                "statement": "The frozen demo output passed both probes and restored.",
                "evidence_ref": f"submission:{verified['snapshot_id']}",
                "evidence_digest": verified["tree_digest"],
                "position_ref": initial_position["record_id"],
                "witness_bindings": [
                    {
                        "checklist_item_id": checklist_id,
                        "source_rule_semantics_digest": checklist_record["body"][
                            "source_rule_semantics_digest"
                        ],
                        "operators": checklist_record["body"][
                            "required_witness_operators"
                        ],
                    }
                ],
            },
        )["record"]
        receipt = append_graph_record(
            graph_path,
            record_type="fact_admission",
            actor="qa",
            body={
                "fact_id": "F-DEMO-VERIFIED",
                "fact_record_id": fact["record_id"],
                "admission_rule_id": "R-DEMO",
                "admission_rule_record_id": rule_record["record_id"],
                "admitter_ref": "qa:local-demo",
                "receipt_ref": f"submission:{verified['snapshot_id']}",
            },
        )["record"]
        final_position = append_graph_record(
            graph_path,
            record_type="position_checkpoint",
            actor="worker",
            body={
                **common_position,
                "position_id": "P-DEMO-COMPLETE",
                "previous_position_ref": initial_position["record_id"],
                "fact_receipt_ids": [receipt["record_id"]],
                "checkpoint_kind": "acceptance_assessment",
                "ready_item_ids": [],
                "blocked_item_ids": [],
                "unresolved_checklist_item_ids": [],
                "checklist_assessments": {
                    checklist_id: {
                        "status": "pass",
                        "applicability_status": "applicable",
                        "witness_fact_receipt_ids": [receipt["record_id"]],
                    }
                },
            },
        )["record"]
        final_binding = {**semantic_binding, "position_ref": final_position["record_id"]}
        final_direction = append_graph_record(
            graph_path,
            record_type="direction_proposal",
            actor="worker",
            body={
                "direction_id": "D-DEMO-RETURN",
                "position_ref": final_position["record_id"],
                "statement": "Return the latest verified Worker freeze.",
                "rule_record_ids": [rule_record["record_id"]],
                "rule_closure_digests": closure_digests,
                "fact_receipt_ids": [receipt["record_id"]],
                "evidence_refs": [f"submission:{verified['snapshot_id']}"],
                "checklist_item_ids": [checklist_id],
                "ready_item_ids": [],
                "blocked_item_ids": [],
                "unresolved_checklist_item_ids": [],
                "semantic_bindings": [final_binding],
            },
        )["record"]
        append_graph_record(
            graph_path,
            record_type="direction_snapshot",
            actor="runner",
            body={
                "position_ref": final_position["record_id"],
                "direction_record_ids": [final_direction["record_id"]],
                "selected_direction_record_id": final_direction["record_id"],
            },
        )
        navigation_body = {
            "schema_version": EXECUTION_TEST_CONTRACT_SCHEMA,
            "contract_id": "EXECUTION-CONTRACT-DEMO-RETURN",
            "position_ref": final_position["record_id"],
            "direction_record_id": final_direction["record_id"],
            "execution_kind": "read_only_navigation",
            "selected_checklist_item_ids": [],
            "selected_rule_record_ids": [],
            "semantic_edge_ids": [],
            "witness_obligation_ids": [],
            "probe_cases": [],
            "exemption_reason": "Returning the existing verified freeze performs no task mutation.",
        }
        navigation_body["contract_digest"] = sha256_json(navigation_body)
        navigation_record = append_graph_record(
            graph_path,
            record_type="execution_test_contract",
            actor="worker",
            body=navigation_body,
        )["record"]
        _append_qa_assessment(graph_path, contract_record=navigation_record)

        doctor = graph_doctor(graph_path)
        if not doctor["structurally_valid"]:
            raise RuntimeError(f"result QA rejected the Graph: {doctor['errors']}")
        if doctor["incomplete_reasons"]:
            raise RuntimeError(
                "result QA found an incomplete Graph: "
                + ", ".join(doctor["incomplete_reasons"])
            )
        if doctor["classification"] != "acceptance_assessed_complete":
            raise RuntimeError(f"unexpected Graph classification: {doctor['classification']}")

        return {
            "ok": True,
            "schema_version": "charting-loop/four-stage-local-demo/v1",
            "kit_version": KIT_VERSION,
            "benchmark_result": False,
            "paid_compute_used": False,
            "method_changed": False,
            "canonical_source_witness_fields": list(SOURCE_WITNESS_FIELDS),
            "legacy_cl151_shape_rejected": legacy_rejected,
            "stages": [
                {
                    "stage": "worker_compile",
                    "status": "passed",
                    "rule_count": report["rule_count"],
                    "witness_count": len(
                        witness_product["witness_lane_packages"][0]["witnesses"]
                    ),
                },
                {
                    "stage": "compile_qa",
                    "status": "passed",
                    "rule_closure_established": closure["rule_closure_established"],
                },
                {
                    "stage": "worker_implementation",
                    "status": "passed",
                    "snapshot_id": frozen["snapshot_id"],
                    "restored_tree_digest": verified["tree_digest"],
                },
                {
                    "stage": "result_qa",
                    "status": "passed",
                    "graph_classification": doctor["classification"],
                    "graph_record_count": doctor["record_count"],
                },
            ],
        }


def main() -> int:
    try:
        result = run_demo()
    except (CorridorKitError, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
