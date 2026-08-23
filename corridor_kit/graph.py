"""Task-neutral append-only graph mechanics for integrated Method execution.

The graph stores identity-bound records.  It validates structure and provenance,
but deliberately does not decide task truth, correctness, completion, or PASS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core import (
    MAX_JSON_BYTES,
    CorridorKitError,
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_bytes,
    sha256_json,
)
from .compiler import (
    TASK_SOURCE_BUNDLE_SCHEMA_V3,
    TASK_SOURCE_BUNDLE_SCHEMA_V2,
    RULE_RELATIONSHIPS,
    TYPED_RULE_SEMANTICS_SCHEMA_V3,
    TYPED_RULE_SEMANTICS_SCHEMA_V4,
    compile_typed_rule_ir,
    project_relationship_alignment,
    project_rule_checklist_templates,
    rule_source_provenance_identity,
    validate_rule_source_slices,
    validate_rule_semantics,
    validate_source_artifact,
    validate_authority_source_artifact,
    validate_source_bundle,
    validate_source_clause_inventory_v3,
)

RULE_RATIFICATION_SCHEMA_V2 = "charting-loop/rule-ratification/v2"
RULE_CANDIDATE_REPORT_SCHEMA = "charting-loop/rule-candidate-report/v1"
RULE_QA_ASSESSMENT_SCHEMA = "charting-loop/rule-qa-assessment/v1"


GRAPH_RECORD_SCHEMA = "charting-loop/graph-kernel-record/v1"
GRAPH_REPLAY_SCHEMA = "charting-loop/graph-kernel-replay/v1"
GRAPH_DOCTOR_SCHEMA = "charting-loop/graph-doctor-report/v1"
GRAPH_RECORD_TYPES = frozenset(
    {
        "task_source_artifact",
        "authority_snapshot",
        "source_clause",
        "rule_proposal",
        "rule_revision",
        "rule_candidate_report",
        "rule_qa_assessment",
        "rule_ratification",
        "rule_dependency",
        "acceptance_checklist_item",
        "typed_dependency",
        "dependency_resolution",
        "fact_proposal",
        "fact_admission",
        "position_checkpoint",
        "direction_proposal",
        "direction_snapshot",
        "artifact_revision",
    }
)
GRAPH_ACTORS = frozenset({"worker", "qa", "runner", "operator"})
CHECKPOINT_KINDS = frozenset({"row_progress", "acceptance_assessment"})
CHECKLIST_STATUSES = frozenset({"pass", "fail", "unknown"})
CHECKLIST_APPLICABILITY_STATUSES = frozenset(
    {"applicable", "not_applicable", "unresolved"}
)
CHECKLIST_COMPILATION_STATUSES = frozenset(
    {"complete", "incomplete", "ambiguous", "unsupported"}
)
DEPENDENCY_KINDS = frozenset({"normative", "work", "evidence"})
HARD_DEPENDENCY_RELATIONSHIPS = frozenset(
    {"requires", "produces_fact_for", "precondition_for"}
)
NON_ORDERING_DEPENDENCY_RELATIONSHIPS = frozenset(
    {"derived_from", "subsumes", "overlaps", "can_parallelize_with"}
)
DEPENDENCY_RELATIONSHIPS = frozenset(
    {*HARD_DEPENDENCY_RELATIONSHIPS, *NON_ORDERING_DEPENDENCY_RELATIONSHIPS, "conflicts", "invalidates"}
)
RULE_HARD_RELATIONSHIPS = frozenset({"requires", "precondition_for", "precedes"})


def _strict_object(raw: str, *, line_number: int) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in pairs:
            if key in value:
                raise CorridorKitError(
                    f"duplicate graph JSON key on line {line_number}: {key}"
                )
            value[key] = child
        return value

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                CorridorKitError(f"non-finite graph JSON value: {item}")
            ),
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise CorridorKitError(
            f"invalid graph JSON on line {line_number}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CorridorKitError(f"graph line {line_number} must be a JSON object")
    return value


def _text(body: Mapping[str, Any], field: str) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CorridorKitError(f"graph body field {field} must be non-empty text")
    return value


def _text_list(body: Mapping[str, Any], field: str, *, nonempty: bool = False) -> list[str]:
    value = body.get(field)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CorridorKitError(f"graph body field {field} must be a text list")
    if nonempty and not value:
        raise CorridorKitError(f"graph body field {field} must not be empty")
    if len(value) != len(set(value)):
        raise CorridorKitError(f"graph body field {field} contains duplicates")
    return value


def _digest(body: Mapping[str, Any], field: str) -> str:
    value = _text(body, field)
    if not value.startswith("sha256:") or len(value) != 71:
        raise CorridorKitError(f"graph body field {field} must be a sha256 digest")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise CorridorKitError(
            f"graph body field {field} must be a sha256 digest"
        ) from exc
    return value


def _validate_rule_qa_assessment_body(body: Mapping[str, Any]) -> dict[str, Any]:
    if set(body) != {
        "schema_version",
        "candidate_report_record_id",
        "candidate_report_digest",
        "outcome",
        "findings",
        "assessment_digest",
    }:
        raise CorridorKitError("Rule QA assessment has unknown or missing fields")
    if body.get("schema_version") != RULE_QA_ASSESSMENT_SCHEMA:
        raise CorridorKitError("Rule QA assessment has the wrong schema")
    normalized = {
        "schema_version": RULE_QA_ASSESSMENT_SCHEMA,
        "candidate_report_record_id": _text(body, "candidate_report_record_id"),
        "candidate_report_digest": _digest(body, "candidate_report_digest"),
        "outcome": _text(body, "outcome"),
        "findings": _text_list(body, "findings"),
    }
    if normalized["outcome"] not in {"pass", "fail", "not_assessed"}:
        raise CorridorKitError("Rule QA assessment has an unknown outcome")
    if normalized["outcome"] == "pass" and normalized["findings"]:
        raise CorridorKitError("passing Rule QA assessment cannot retain findings")
    if normalized["outcome"] != "pass" and not normalized["findings"]:
        raise CorridorKitError("non-passing Rule QA assessment requires findings")
    assessment_digest = _digest(body, "assessment_digest")
    if assessment_digest != sha256_json(normalized):
        raise CorridorKitError("Rule QA assessment digest does not match its content")
    return {**normalized, "assessment_digest": assessment_digest}


def _identity_payload(
    *, sequence: int, record_type: str, actor: str, body: Mapping[str, Any], previous: str | None
) -> dict[str, Any]:
    return {
        "schema_version": GRAPH_RECORD_SCHEMA,
        "sequence": sequence,
        "record_type": record_type,
        "actor": actor,
        "body": dict(body),
        "previous_record_id": previous,
    }


def _content_id(record_type: str, actor: str, body: Mapping[str, Any]) -> str:
    return sha256_json(
        {"schema_version": GRAPH_RECORD_SCHEMA, "record_type": record_type, "actor": actor, "body": dict(body)}
    )


def _record_id(payload: Mapping[str, Any]) -> str:
    return sha256_json(payload)


def load_graph(path: Path) -> list[dict[str, Any]]:
    """Load and verify every byte in a graph chain without following symlinks."""

    if path.is_symlink() or not path.is_file():
        raise CorridorKitError(f"graph must be a regular non-symlink file: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise CorridorKitError(f"graph exceeds {MAX_JSON_BYTES} bytes: {path}")
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CorridorKitError(f"graph is unreadable: {path}") from exc
    for index, raw in enumerate(lines, start=1):
        if not raw.strip():
            raise CorridorKitError(f"graph contains a blank line at {index}")
        records.append(_strict_object(raw, line_number=index))
    validate_graph_records(records)
    return records


def _assert_acyclic(edges: Mapping[str, set[str]], *, label: str = "rule dependency") -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CorridorKitError(f"{label} graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for target in edges.get(node, set()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        visit(node)


def _object(body: Mapping[str, Any], field: str, *, nonempty: bool = False) -> dict[str, Any]:
    value = body.get(field)
    if not isinstance(value, dict) or (nonempty and not value):
        suffix = " non-empty" if nonempty else ""
        raise CorridorKitError(f"graph body field {field} must be a{suffix} object")
    return value


def _topological_order(nodes: Iterable[str], edges: Mapping[str, set[str]]) -> list[str]:
    """Return dependencies before dependants for source-depends-on-target edges."""

    remaining = {node: set(edges.get(node, set())) for node in set(nodes)}
    order: list[str] = []
    while remaining:
        ready = sorted(node for node, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise CorridorKitError("hard dependency graph contains a cycle")
        for node in ready:
            order.append(node)
            remaining.pop(node)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return order


def _hard_dependency_pair(dependency: Mapping[str, Any]) -> tuple[str, str]:
    """Return (dependant, prerequisite) for one hard relationship."""

    source = str(dependency["from_ref"])
    target = str(dependency["to_ref"])
    if dependency["relationship"] == "requires":
        return source, target
    return target, source


def _position_bindings_present(body: Mapping[str, Any]) -> bool:
    fields = {
        "checkpoint_kind",
        "checklist_item_ids",
        "ready_item_ids",
        "blocked_item_ids",
        "unresolved_checklist_item_ids",
        "checklist_assessments",
    }
    present = fields.intersection(body)
    if present and present != fields:
        missing = sorted(fields - present)
        raise CorridorKitError(
            "Position checkpoint has partial checklist bindings; missing " + ", ".join(missing)
        )
    return bool(present)


def _direction_bindings_present(body: Mapping[str, Any]) -> bool:
    fields = {
        "checklist_item_ids",
        "ready_item_ids",
        "blocked_item_ids",
        "unresolved_checklist_item_ids",
    }
    present = fields.intersection(body)
    if present and present != fields:
        missing = sorted(fields - present)
        raise CorridorKitError(
            "Direction proposal has partial checklist bindings; missing " + ", ".join(missing)
        )
    return bool(present)


def _successor_source_bundle(
    source_artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    sources = [
        (
            {
                "source_id": source["source_id"],
                "source_ref": source["source_ref"],
                "source_digest": source["byte_digest"],
                "role": source["role"],
                "retrieval_status": source["byte_status"],
                "content_encoding": source["content_encoding"],
                "content_utf8": source["content_utf8"],
            }
            if "plane" in source
            else dict(source)
        )
        for source in source_artifacts.values()
    ]
    return {
        "schema_version": TASK_SOURCE_BUNDLE_SCHEMA_V2,
        "closure_status": (
            "complete"
            if sources
            and all(source["retrieval_status"] == "available" for source in sources)
            else "unresolved"
        ),
        "sources": sources,
    }


def _validate_successor_rule_source(
    body: Mapping[str, Any],
    *,
    source_artifacts: Mapping[str, Mapping[str, Any]],
    source_clauses: Mapping[str, Mapping[str, Any]],
    source_slice_to_clause: Mapping[str, str],
    authority_snapshot: Mapping[str, Any] | None = None,
) -> str:
    rule_id = _text(body, "rule_id")
    statement = _text(body, "statement")
    source_clause_ids = _text_list(body, "source_clause_ids", nonempty=True)
    source_slices = validate_rule_source_slices(body.get("source_slices"))
    unknown_clauses = sorted(set(source_clause_ids) - set(source_clauses))
    if unknown_clauses:
        raise CorridorKitError(
            f"successor Rule references unknown source clauses: {unknown_clauses}"
        )
    canonical_clause_ids = sorted(
        source_clause_ids,
        key=lambda clause_id: source_clauses[clause_id]["clause_order_key"],
    )
    if source_clause_ids != canonical_clause_ids:
        raise CorridorKitError(
            "successor Rule source clauses are not in stable clause-order-key order"
        )
    mapped_clauses = sorted(
        clause_id
        for clause_id, clause in source_clauses.items()
        if rule_id in clause["rule_ids"]
    )
    if sorted(source_clause_ids) != mapped_clauses:
        raise CorridorKitError(
            f"successor Rule source clauses do not match graph inventory: {rule_id}"
        )
    unknown_slices = sorted(
        {
            binding["slice_id"]
            for binding in source_slices
            if binding["slice_id"] not in source_slice_to_clause
        }
    )
    if unknown_slices:
        raise CorridorKitError(
            f"successor Rule references unknown source slices: {unknown_slices}"
        )
    outside_slices = sorted(
        binding["slice_id"]
        for binding in source_slices
        if source_slice_to_clause[binding["slice_id"]] not in set(source_clause_ids)
    )
    if outside_slices:
        raise CorridorKitError(
            f"successor Rule source slices fall outside mapped clauses: {outside_slices}"
        )
    source_bundle = (
        dict(authority_snapshot)
        if authority_snapshot is not None
        else _successor_source_bundle(source_artifacts)
    )
    source_identity = rule_source_provenance_identity(
        rule_id=rule_id,
        statement=statement,
        source_clause_ids=source_clause_ids,
        source_slices=source_slices,
        source_bundle=source_bundle,
        source_clauses=list(source_clauses.values()),
    )
    provenance_digest = _digest(body, "rule_source_provenance_digest")
    if sha256_json(source_identity) != provenance_digest:
        raise CorridorKitError("successor Rule source provenance digest does not match")
    is_v4 = body.get("semantics", {}).get("schema_version") == TYPED_RULE_SEMANTICS_SCHEMA_V4
    if is_v4:
        snapshot_digest = _digest(body, "source_digest")
        if authority_snapshot is None:
            raise CorridorKitError("v4 Rule requires a runner AuthoritySnapshot")
        if snapshot_digest != sha256_json(source_bundle):
            raise CorridorKitError("v4 Rule does not bind the current AuthoritySnapshot")
        if _digest(body, "authority_snapshot_manifest_digest") != source_bundle[
            "manifest_digest"
        ]:
            raise CorridorKitError("v4 Rule manifest digest differs from AuthoritySnapshot")
        if body.get("source_ref") != f"authority-snapshot:{snapshot_digest}":
            raise CorridorKitError("v4 Rule source_ref does not bind AuthoritySnapshot")
        return provenance_digest
    bundle_digest = sha256_json(source_bundle)
    if body.get("source_ref") != f"source-bundle:{bundle_digest}":
        raise CorridorKitError("successor Rule source_ref does not bind current source bundle")
    if _digest(body, "source_digest") != bundle_digest:
        raise CorridorKitError("successor Rule source_digest does not bind current source bundle")
    return provenance_digest


def _checklist_frontier(
    *,
    checklist_items: Mapping[str, Mapping[str, Any]],
    assessments: Mapping[str, Mapping[str, Any]],
    typed_dependencies: Mapping[str, Mapping[str, Any]],
    resolved_dependency_ids: set[str],
    admitted_fact_ids: set[str],
) -> tuple[list[str], list[str], list[str]]:
    checklist_ids = set(checklist_items)
    hard: dict[str, set[str]] = {item: set() for item in checklist_ids}
    conflicts: dict[str, set[str]] = {item: set() for item in checklist_ids}
    for dependency_id, dependency in typed_dependencies.items():
        relationship = dependency["relationship"]
        if relationship in HARD_DEPENDENCY_RELATIONSHIPS:
            dependant, prerequisite = _hard_dependency_pair(dependency)
            if dependant in checklist_ids:
                hard[dependant].add(prerequisite)
        elif relationship == "conflicts" and dependency_id not in resolved_dependency_ids:
            source = dependency["from_ref"]
            target = dependency["to_ref"]
            if source not in checklist_ids:
                continue
            conflicts[source].add(target)
            if target in checklist_ids:
                conflicts[target].add(source)

    def dependency_satisfied(target: str) -> bool:
        if target in checklist_ids:
            assessment = assessments.get(target, {})
            return assessment.get("status") == "pass" or (
                assessment.get("applicability_status") == "not_applicable"
                and bool(assessment.get("witness_fact_receipt_ids"))
            )
        return target in admitted_fact_ids

    ready: list[str] = []
    blocked: list[str] = []
    unresolved: list[str] = []
    for item_id in sorted(checklist_ids):
        assessment = assessments.get(item_id, {})
        status = assessment.get("status", "unknown")
        if (
            assessment.get("applicability_status") == "not_applicable"
            and assessment.get("witness_fact_receipt_ids")
        ):
            continue
        if status != "pass":
            unresolved.append(item_id)
        if status == "pass":
            continue
        if conflicts[item_id] or any(
            not dependency_satisfied(target) for target in hard[item_id]
        ):
            blocked.append(item_id)
        else:
            ready.append(item_id)
    return ready, blocked, unresolved


def validate_graph_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate chain identity, authority receipts, and reference closure."""

    source_artifacts: dict[str, dict[str, Any]] = {}
    authority_snapshot: dict[str, Any] | None = None
    authority_snapshot_record_id: str | None = None
    source_clauses: dict[str, dict[str, Any]] = {}
    source_clause_order_keys: set[str] = set()
    source_slice_to_clause: dict[str, str] = {}
    rule_records: dict[str, str] = {}
    current_rule_bodies: dict[str, dict[str, Any]] = {}
    rule_source_digests: dict[str, str] = {}
    rule_source_provenance_digests: dict[str, str] = {}
    rule_source_bindings: dict[str, list[dict[str, str]]] = {}
    rule_semantics: dict[str, dict[str, Any]] = {}
    rule_semantics_digests: dict[str, str] = {}
    ratified_rules: dict[str, str] = {}
    ratified_rule_closures: dict[str, str] = {}
    candidate_reports: dict[str, dict[str, Any]] = {}
    qa_assessments: dict[str, dict[str, Any]] = {}
    dependencies: dict[str, set[str]] = {}
    checklist_items: dict[str, dict[str, Any]] = {}
    typed_dependencies: dict[str, dict[str, Any]] = {}
    dependency_resolutions: dict[str, dict[str, Any]] = {}
    hard_dependencies: dict[str, set[str]] = {}
    fact_records: dict[str, str] = {}
    fact_bodies: dict[str, dict[str, Any]] = {}
    fact_receipts: dict[str, str] = {}
    positions: dict[str, dict[str, Any]] = {}
    position_ids: set[str] = set()
    directions: dict[str, dict[str, Any]] = {}
    direction_ids: set[str] = set()
    artifacts: dict[str, int] = {}
    latest_artifact_record_ids: dict[str, str] = {}
    content_ids: set[str] = set()
    previous: str | None = None

    exact_keys = {
        "schema_version",
        "sequence",
        "record_type",
        "actor",
        "body",
        "content_id",
        "record_id",
        "previous_record_id",
    }
    for index, record in enumerate(records):
        if set(record) != exact_keys:
            raise CorridorKitError(f"graph record {index + 1} has unknown or missing fields")
        if record.get("schema_version") != GRAPH_RECORD_SCHEMA:
            raise CorridorKitError(f"graph record {index + 1} has the wrong schema")
        if record.get("sequence") != index + 1:
            raise CorridorKitError(f"graph record {index + 1} has a non-contiguous sequence")
        record_type = record.get("record_type")
        actor = record.get("actor")
        body = record.get("body")
        if record_type not in GRAPH_RECORD_TYPES:
            raise CorridorKitError(f"unknown graph record type: {record_type}")
        if actor not in GRAPH_ACTORS:
            raise CorridorKitError(f"unknown graph actor: {actor}")
        if not isinstance(body, dict):
            raise CorridorKitError("graph body must be an object")
        if record.get("previous_record_id") != previous:
            raise CorridorKitError(f"graph record {index + 1} breaks the hash chain")
        expected_content = _content_id(record_type, actor, body)
        if record.get("content_id") != expected_content:
            raise CorridorKitError(f"graph record {index + 1} has the wrong content identity")
        if expected_content in content_ids:
            raise CorridorKitError("graph contains a duplicate content identity")
        content_ids.add(expected_content)
        payload = _identity_payload(
            sequence=index + 1,
            record_type=record_type,
            actor=actor,
            body=body,
            previous=previous,
        )
        expected_record = _record_id(payload)
        if record.get("record_id") != expected_record:
            raise CorridorKitError(f"graph record {index + 1} has the wrong record identity")
        previous = expected_record

        if record_type == "authority_snapshot":
            if actor != "runner":
                raise CorridorKitError("AuthoritySnapshot must be frozen by the runner")
            if authority_snapshot is not None:
                raise CorridorKitError("graph already contains an AuthoritySnapshot")
            snapshot = validate_source_bundle(body)
            if snapshot["schema_version"] != TASK_SOURCE_BUNDLE_SCHEMA_V3:
                raise CorridorKitError("authority_snapshot record requires schema v3")
            authority_snapshot = snapshot
            authority_snapshot_record_id = expected_record
        elif record_type == "task_source_artifact":
            artifact = (
                validate_authority_source_artifact(body)
                if "plane" in body
                else validate_source_artifact(body)
            )
            if "plane" in artifact:
                if actor != "runner" or authority_snapshot is None:
                    raise CorridorKitError(
                        "v4 task source artifacts require a prior runner AuthoritySnapshot"
                    )
                frozen_source = next(
                    (
                        item
                        for item in authority_snapshot["sources"]
                        if item["source_id"] == artifact["source_id"]
                    ),
                    None,
                )
                if frozen_source != artifact:
                    raise CorridorKitError(
                        "task source artifact differs from runner AuthoritySnapshot"
                    )
            source_id = artifact["source_id"]
            if source_id in source_artifacts or any(
                item["source_ref"] == artifact["source_ref"]
                for item in source_artifacts.values()
            ):
                raise CorridorKitError(
                    "task source artifact identity is duplicated; changed bytes require a new source ID"
                )
            source_artifacts[source_id] = artifact
        elif record_type == "source_clause":
            if not source_artifacts:
                raise CorridorKitError(
                    "source clause requires prior frozen task source artifacts"
                )
            source_bundle = (
                authority_snapshot
                if authority_snapshot is not None
                else _successor_source_bundle(source_artifacts)
            )
            clause = validate_source_clause_inventory_v3(
                [body], source_bundle=source_bundle
            )[0]
            clause_id = clause["clause_id"]
            if clause_id in source_clauses:
                raise CorridorKitError(f"source clause already exists: {clause_id}")
            clause_order_key = clause["clause_order_key"]
            if clause_order_key in source_clause_order_keys:
                raise CorridorKitError(
                    f"source clause order key is duplicated: {clause_order_key}"
                )
            source_clause_order_keys.add(clause_order_key)
            for source_slice in clause["source_slices"]:
                slice_id = source_slice["slice_id"]
                if slice_id in source_slice_to_clause:
                    raise CorridorKitError(f"source slice already exists: {slice_id}")
                source_slice_to_clause[slice_id] = clause_id
            source_clauses[clause_id] = clause
        elif record_type == "rule_proposal":
            rule_id = _text(body, "rule_id")
            _text(body, "statement")
            _text(body, "source_ref")
            source_digest = _digest(body, "source_digest")
            semantic_fields = {"semantics", "rule_semantics_digest"}.intersection(body)
            if semantic_fields and semantic_fields != {
                "semantics",
                "rule_semantics_digest",
            }:
                raise CorridorKitError(
                    "typed Rule proposal must bind semantics and rule_semantics_digest together"
                )
            if semantic_fields:
                semantics = validate_rule_semantics(body["semantics"])
                semantics_digest = _digest(body, "rule_semantics_digest")
                if sha256_json(semantics) != semantics_digest:
                    raise CorridorKitError("typed Rule semantics digest does not match")
                semantics_schema = semantics.get("schema_version")
                if semantics_schema in {
                    TYPED_RULE_SEMANTICS_SCHEMA_V3,
                    TYPED_RULE_SEMANTICS_SCHEMA_V4,
                }:
                    provenance_digest = _validate_successor_rule_source(
                        body,
                        source_artifacts=source_artifacts,
                        source_clauses=source_clauses,
                        source_slice_to_clause=source_slice_to_clause,
                        authority_snapshot=authority_snapshot,
                    )
                elif semantics_schema == "charting-loop/typed-rule-semantics/v2":
                    _text_list(body, "source_clause_ids", nonempty=True)
                elif {"source_clause_ids", "source_slices", "rule_source_provenance_digest"}.intersection(body):
                    raise CorridorKitError(
                        "legacy typed Rule cannot claim successor source bindings"
                    )
            if rule_id in rule_records:
                raise CorridorKitError(f"rule proposal already exists: {rule_id}")
            rule_records[rule_id] = expected_record
            current_rule_bodies[rule_id] = dict(body)
            rule_source_digests[rule_id] = source_digest
            if semantic_fields:
                rule_semantics[rule_id] = semantics
                rule_semantics_digests[rule_id] = semantics_digest
                if semantics.get("schema_version") in {
                    TYPED_RULE_SEMANTICS_SCHEMA_V3,
                    TYPED_RULE_SEMANTICS_SCHEMA_V4,
                }:
                    rule_source_provenance_digests[rule_id] = provenance_digest
                    rule_source_bindings[rule_id] = list(body["source_slices"])
        elif record_type == "rule_revision":
            rule_id = _text(body, "rule_id")
            supersedes = _text(body, "supersedes_record_id")
            _text(body, "statement")
            _text(body, "source_ref")
            source_digest = _digest(body, "source_digest")
            semantic_fields = {"semantics", "rule_semantics_digest"}.intersection(body)
            if semantic_fields and semantic_fields != {
                "semantics",
                "rule_semantics_digest",
            }:
                raise CorridorKitError(
                    "typed Rule revision must bind semantics and rule_semantics_digest together"
                )
            if semantic_fields:
                semantics = validate_rule_semantics(body["semantics"])
                semantics_digest = _digest(body, "rule_semantics_digest")
                if sha256_json(semantics) != semantics_digest:
                    raise CorridorKitError("typed Rule semantics digest does not match")
                semantics_schema = semantics.get("schema_version")
                if semantics_schema in {
                    TYPED_RULE_SEMANTICS_SCHEMA_V3,
                    TYPED_RULE_SEMANTICS_SCHEMA_V4,
                }:
                    provenance_digest = _validate_successor_rule_source(
                        body,
                        source_artifacts=source_artifacts,
                        source_clauses=source_clauses,
                        source_slice_to_clause=source_slice_to_clause,
                        authority_snapshot=authority_snapshot,
                    )
                elif semantics_schema == "charting-loop/typed-rule-semantics/v2":
                    _text_list(body, "source_clause_ids", nonempty=True)
                elif {"source_clause_ids", "source_slices", "rule_source_provenance_digest"}.intersection(body):
                    raise CorridorKitError(
                        "legacy typed Rule cannot claim successor source bindings"
                    )
            if rule_records.get(rule_id) != supersedes:
                raise CorridorKitError(f"rule revision does not supersede the current rule: {rule_id}")
            rule_records[rule_id] = expected_record
            current_rule_bodies[rule_id] = dict(body)
            rule_source_digests[rule_id] = source_digest
            if semantic_fields:
                rule_semantics[rule_id] = semantics
                rule_semantics_digests[rule_id] = semantics_digest
                if semantics.get("schema_version") in {
                    TYPED_RULE_SEMANTICS_SCHEMA_V3,
                    TYPED_RULE_SEMANTICS_SCHEMA_V4,
                }:
                    rule_source_provenance_digests[rule_id] = provenance_digest
                    rule_source_bindings[rule_id] = list(body["source_slices"])
                else:
                    rule_source_provenance_digests.pop(rule_id, None)
                    rule_source_bindings.pop(rule_id, None)
            else:
                rule_semantics.pop(rule_id, None)
                rule_semantics_digests.pop(rule_id, None)
                rule_source_provenance_digests.pop(rule_id, None)
                rule_source_bindings.pop(rule_id, None)
            ratified_rules.pop(rule_id, None)
            ratified_rule_closures.pop(rule_id, None)
        elif record_type == "rule_candidate_report":
            if actor != "runner":
                raise CorridorKitError("Rule candidate report must be frozen by the runner")
            if set(body) != {
                "schema_version",
                "authority_snapshot_record_id",
                "typed_rule_ir",
                "compile_report",
                "rule_record_ids",
                "candidate_report_digest",
            }:
                raise CorridorKitError("Rule candidate report has unknown or missing fields")
            if body.get("schema_version") != RULE_CANDIDATE_REPORT_SCHEMA:
                raise CorridorKitError("Rule candidate report has the wrong schema")
            if authority_snapshot_record_id is None or body.get(
                "authority_snapshot_record_id"
            ) != authority_snapshot_record_id:
                raise CorridorKitError(
                    "Rule candidate report does not bind the runner AuthoritySnapshot"
                )
            expected_report = compile_typed_rule_ir(body.get("typed_rule_ir"))
            if body.get("compile_report") != expected_report:
                raise CorridorKitError(
                    "Rule candidate report does not reproduce from its typed Rule IR"
                )
            expected_rule_ids = {
                rule_body["rule_id"]: rule_records.get(rule_body["rule_id"])
                for rule_body in expected_report["rule_bodies"]
            }
            if body.get("rule_record_ids") != expected_rule_ids or any(
                current_rule_bodies.get(rule_body["rule_id"]) != rule_body
                for rule_body in expected_report["rule_bodies"]
            ):
                raise CorridorKitError(
                    "Rule candidate report does not bind the current Rule candidates"
                )
            if authority_snapshot != expected_report["authority_snapshot_template"]:
                raise CorridorKitError(
                    "Rule candidate report AuthoritySnapshot differs from Graph custody"
                )
            if list(source_artifacts.values()) != expected_report["source_artifact_templates"]:
                raise CorridorKitError(
                    "Rule candidate report source artifacts differ from Graph custody"
                )
            if list(source_clauses.values()) != expected_report["source_clause_templates"]:
                raise CorridorKitError(
                    "Rule candidate report source clauses differ from Graph custody"
                )
            normalized_candidate = {
                key: body[key] for key in body if key != "candidate_report_digest"
            }
            candidate_digest = _digest(body, "candidate_report_digest")
            if candidate_digest != sha256_json(normalized_candidate):
                raise CorridorKitError("Rule candidate report digest does not match")
            candidate_reports[expected_record] = {
                **normalized_candidate,
                "candidate_report_digest": candidate_digest,
            }
        elif record_type == "rule_qa_assessment":
            if actor != "qa":
                raise CorridorKitError("Rule QA assessment must be authored by QA")
            assessment = _validate_rule_qa_assessment_body(body)
            candidate = candidate_reports.get(
                assessment["candidate_report_record_id"]
            )
            if candidate is None or assessment["candidate_report_digest"] != candidate[
                "candidate_report_digest"
            ]:
                raise CorridorKitError(
                    "Rule QA assessment does not bind an existing candidate report"
                )
            qa_assessments[expected_record] = assessment
        elif record_type == "rule_ratification":
            rule_id = _text(body, "rule_id")
            rule_record_id = _text(body, "rule_record_id")
            _text(body, "authority_ref")
            authority_digest = _digest(body, "authority_digest")
            _text(body, "receipt_ref")
            if rule_records.get(rule_id) != rule_record_id:
                raise CorridorKitError(f"ratification does not bind the current rule: {rule_id}")
            if rule_source_digests.get(rule_id) != authority_digest:
                raise CorridorKitError(
                    f"ratification authority does not bind the current rule source: {rule_id}"
                )
            if rule_id in ratified_rules:
                raise CorridorKitError(f"current rule is already ratified: {rule_id}")
            successor_fields = {
                "ratification_schema",
                "candidate_report_record_id",
                "candidate_report_digest",
                "candidate_revision_digest",
                "authority_snapshot_digest",
                "reverse_projection_digest",
                "semantic_delta_digest",
                "qa_assessment_ref",
                "qa_assessment_digest",
                "ratifier_ref",
                "rule_closure_digest",
            }
            present = successor_fields.intersection(body)
            if present:
                if present != successor_fields:
                    raise CorridorKitError(
                        "v2 Rule ratification has partial closure bindings"
                    )
                if body.get("ratification_schema") != RULE_RATIFICATION_SCHEMA_V2:
                    raise CorridorKitError("Rule ratification has the wrong schema")
                if actor not in {"runner", "operator"}:
                    raise CorridorKitError("QA and Worker cannot ratify Rule authority")
                candidate_revision_digest = _digest(body, "candidate_revision_digest")
                candidate_report_record_id = _text(
                    body, "candidate_report_record_id"
                )
                candidate_report_digest = _digest(body, "candidate_report_digest")
                snapshot_digest = _digest(body, "authority_snapshot_digest")
                reverse_digest = _digest(body, "reverse_projection_digest")
                semantic_delta_digest = _digest(body, "semantic_delta_digest")
                qa_ref = _text(body, "qa_assessment_ref")
                qa_digest = _digest(body, "qa_assessment_digest")
                ratifier_ref = _text(body, "ratifier_ref")
                if authority_digest != snapshot_digest:
                    raise CorridorKitError(
                        "Rule ratification authority_digest differs from AuthoritySnapshot"
                    )
                if rule_semantics.get(rule_id, {}).get("schema_version") != TYPED_RULE_SEMANTICS_SCHEMA_V4:
                    raise CorridorKitError("v2 ratification requires a current v4 Rule candidate")
                candidate = candidate_reports.get(candidate_report_record_id)
                if candidate is None or candidate[
                    "candidate_report_digest"
                ] != candidate_report_digest:
                    raise CorridorKitError(
                        "Rule ratification does not bind an existing frozen candidate report"
                    )
                report = candidate["compile_report"]
                if (
                    not report["compilation_complete"]
                    or report["compile_issues"]
                    or report["semantic_delta"]
                    or report["unaccounted_normative_ranges"]
                    or report["relationship_alignment_issues"]
                ):
                    raise CorridorKitError(
                        "RuleClosure requires a complete zero-delta compile report"
                    )
                if (
                    candidate["rule_record_ids"].get(rule_id) != rule_record_id
                    or report["candidate_revision_digest"]
                    != candidate_revision_digest
                    or report["authority_snapshot_digest"] != snapshot_digest
                    or report["reverse_semantic_projection_digest"] != reverse_digest
                    or report["semantic_delta_digest"] != semantic_delta_digest
                ):
                    raise CorridorKitError(
                        "Rule ratification inputs differ from frozen candidate report"
                    )
                qa_assessment = qa_assessments.get(qa_ref)
                if (
                    qa_assessment is None
                    or qa_assessment["assessment_digest"] != qa_digest
                    or qa_assessment["candidate_report_record_id"]
                    != candidate_report_record_id
                    or qa_assessment["candidate_report_digest"]
                    != candidate_report_digest
                    or qa_assessment["outcome"] != "pass"
                ):
                    raise CorridorKitError(
                        "RuleClosure requires a passing QA assessment of the same candidate"
                    )
                expected_closure = sha256_json(
                    {
                        "rule_id": rule_id,
                        "rule_record_id": rule_record_id,
                        "candidate_report_record_id": candidate_report_record_id,
                        "candidate_report_digest": candidate_report_digest,
                        "candidate_revision_digest": candidate_revision_digest,
                        "authority_snapshot_digest": snapshot_digest,
                        "reverse_projection_digest": reverse_digest,
                        "semantic_delta_digest": semantic_delta_digest,
                        "qa_assessment_ref": qa_ref,
                        "qa_assessment_digest": qa_digest,
                        "ratifier_ref": ratifier_ref,
                    }
                )
                closure_digest = _digest(body, "rule_closure_digest")
                if closure_digest != expected_closure:
                    raise CorridorKitError("RuleClosure digest does not match ratification inputs")
                ratified_rule_closures[rule_id] = closure_digest
            ratified_rules[rule_id] = expected_record
        elif record_type == "rule_dependency":
            source = _text(body, "from_rule_id")
            target = _text(body, "to_rule_id")
            relationship = _text(body, "relationship")
            if relationship not in RULE_RELATIONSHIPS:
                raise CorridorKitError(f"unknown rule dependency relationship: {relationship}")
            if source not in rule_records or target not in rule_records or source == target:
                raise CorridorKitError("rule dependency references an unknown or identical rule")
            successor_fields = {
                "edge_provenance",
                "source_rule_provenance_digest",
                "target_rule_provenance_digest",
                "relationship_alignment",
            }.intersection(body)
            if source in rule_source_provenance_digests:
                expected_successor_fields = {
                    "edge_provenance",
                    "source_rule_provenance_digest",
                    "target_rule_provenance_digest",
                }
                if (
                    rule_semantics[source].get("schema_version")
                    == TYPED_RULE_SEMANTICS_SCHEMA_V4
                ):
                    expected_successor_fields.add("relationship_alignment")
                if successor_fields != expected_successor_fields:
                    raise CorridorKitError(
                        "successor rule dependency must bind edge and both endpoint provenances"
                    )
                expected_dependency = next(
                    (
                        item
                        for item in rule_semantics[source]["dependencies"]
                        if item["relationship"] == relationship
                        and item["target_rule_id"] == target
                    ),
                    None,
                )
                if expected_dependency is None or body["edge_provenance"] != expected_dependency["provenance"]:
                    raise CorridorKitError(
                        "successor rule dependency contradicts its source Rule semantics"
                    )
                if (
                    "alignment" in expected_dependency
                    and body.get("relationship_alignment")
                    != expected_dependency["alignment"]
                ):
                    raise CorridorKitError(
                        "v4 Rule dependency contradicts relationship alignment"
                    )
                if (
                    _digest(body, "source_rule_provenance_digest")
                    != rule_source_provenance_digests[source]
                    or _digest(body, "target_rule_provenance_digest")
                    != rule_source_provenance_digests.get(target)
                ):
                    raise CorridorKitError(
                        "successor rule dependency binds stale endpoint provenance"
                    )
            elif successor_fields:
                raise CorridorKitError(
                    "legacy rule dependency cannot claim successor provenance"
                )
            if relationship in RULE_HARD_RELATIONSHIPS:
                dependant, prerequisite = (
                    (source, target)
                    if relationship == "requires"
                    else (target, source)
                )
                dependencies.setdefault(dependant, set()).add(prerequisite)
                _assert_acyclic(dependencies)
        elif record_type == "acceptance_checklist_item":
            checklist_item_id = _text(body, "checklist_item_id")
            source_rule_id = _text(body, "source_rule_id")
            source_rule_record_id = _text(body, "source_rule_record_id")
            _text(body, "obligation")
            _object(body, "scope", nonempty=True)
            _text(body, "quantifier")
            _text_list(body, "behavioral_partitions", nonempty=True)
            _text(body, "evidence_requirement")
            decision_rule = _object(body, "decision_rule", nonempty=True)
            if set(decision_rule) != {"pass", "fail", "unknown"} or any(
                not isinstance(value, str) or not value.strip()
                for value in decision_rule.values()
            ):
                raise CorridorKitError(
                    "acceptance checklist decision_rule must define non-empty pass/fail/unknown"
                )
            compilation_status = _text(body, "compilation_status")
            if compilation_status not in CHECKLIST_COMPILATION_STATUSES:
                raise CorridorKitError("unknown checklist compilation_status")
            if (
                rule_records.get(source_rule_id) != source_rule_record_id
                or source_rule_id not in ratified_rules
            ):
                raise CorridorKitError(
                    "acceptance checklist item must bind the current ratified source Rule"
                )
            typed_fields = {
                "source_rule_semantics_digest",
                "coverage_cell",
                "required_witness_operators",
            }.intersection(body)
            if source_rule_id in rule_semantics:
                if typed_fields != {
                    "source_rule_semantics_digest",
                    "coverage_cell",
                    "required_witness_operators",
                }:
                    raise CorridorKitError(
                        "typed Rule checklist must bind semantics, coverage cell, and witness operators"
                    )
                if (
                    _digest(body, "source_rule_semantics_digest")
                    != rule_semantics_digests[source_rule_id]
                ):
                    raise CorridorKitError(
                        "typed Rule checklist semantics digest does not match its source Rule"
                    )
                _text_list(
                    body,
                    "required_witness_operators",
                    nonempty=compilation_status == "complete",
                )
                if not isinstance(body.get("coverage_cell"), dict):
                    raise CorridorKitError("typed Rule coverage_cell must be an object")
                templates = {
                    item["checklist_item_id"]: item
                    for item in project_rule_checklist_templates(
                        rule_id=source_rule_id,
                        statement=next(
                            record["body"]["statement"]
                            for record in reversed(records[:index + 1])
                            if record["record_id"] == source_rule_record_id
                        ),
                        semantics=rule_semantics[source_rule_id],
                    )
                }
                expected = templates.get(checklist_item_id)
                if expected is None or any(
                    body.get(field) != expected[field]
                    for field in expected
                    if field not in {"source_rule_id"}
                ):
                    raise CorridorKitError(
                        "typed Rule checklist does not match its deterministic coverage projection"
                    )
            elif typed_fields:
                raise CorridorKitError(
                    "legacy Rule checklist cannot claim an unbound typed projection"
                )
            if checklist_item_id in checklist_items:
                raise CorridorKitError(
                    f"acceptance checklist item already exists: {checklist_item_id}"
                )
            checklist_items[checklist_item_id] = {
                **body,
                "record_id": expected_record,
            }
        elif record_type == "typed_dependency":
            dependency_id = _text(body, "dependency_id")
            dependency_kind = _text(body, "dependency_kind")
            relationship = _text(body, "relationship")
            source = _text(body, "from_ref")
            target = _text(body, "to_ref")
            source_rule_id = _text(body, "source_rule_id")
            source_rule_record_id = _text(body, "source_rule_record_id")
            if dependency_kind not in DEPENDENCY_KINDS:
                raise CorridorKitError(f"unknown dependency kind: {dependency_kind}")
            if relationship not in DEPENDENCY_RELATIONSHIPS:
                raise CorridorKitError(f"unknown dependency relationship: {relationship}")
            if source == target:
                raise CorridorKitError("typed dependency cannot be self-referential")
            if (
                rule_records.get(source_rule_id) != source_rule_record_id
                or source_rule_id not in ratified_rules
            ):
                raise CorridorKitError(
                    "typed dependency must bind a current ratified source Rule"
                )
            successor_fields = {
                "target_rule_id",
                "target_rule_record_id",
                "source_rule_provenance_digest",
                "target_rule_provenance_digest",
                "edge_provenance",
                "relationship_alignment",
            }.intersection(body)
            if source_rule_id in rule_source_provenance_digests:
                expected_fields = {
                    "target_rule_id",
                    "target_rule_record_id",
                    "source_rule_provenance_digest",
                    "target_rule_provenance_digest",
                    "edge_provenance",
                }
                if (
                    rule_semantics[source_rule_id].get("schema_version")
                    == TYPED_RULE_SEMANTICS_SCHEMA_V4
                ):
                    expected_fields.add("relationship_alignment")
                if successor_fields != expected_fields:
                    raise CorridorKitError(
                        "successor typed dependency must bind edge and both current endpoint Rules"
                    )
                target_rule_id = _text(body, "target_rule_id")
                target_rule_record_id = _text(body, "target_rule_record_id")
                if (
                    rule_records.get(target_rule_id) != target_rule_record_id
                    or target_rule_id not in ratified_rules
                ):
                    raise CorridorKitError(
                        "successor typed dependency target Rule is stale or unratified"
                    )
                if (
                    _digest(body, "source_rule_provenance_digest")
                    != rule_source_provenance_digests[source_rule_id]
                    or _digest(body, "target_rule_provenance_digest")
                    != rule_source_provenance_digests.get(target_rule_id)
                ):
                    raise CorridorKitError(
                        "successor typed dependency binds stale endpoint provenance"
                    )
                expected_dependency = next(
                    (
                        item
                        for item in rule_semantics[source_rule_id]["dependencies"]
                        if item["target_rule_id"] == target_rule_id
                        and (
                            item["relationship"] == relationship
                            or (
                                item["relationship"] == "precedes"
                                and relationship == "precondition_for"
                            )
                        )
                    ),
                    None,
                )
                if expected_dependency is None or body["edge_provenance"] != expected_dependency["provenance"]:
                    raise CorridorKitError(
                        "successor typed dependency contradicts its source Rule semantics"
                    )
                if (
                    "alignment" in expected_dependency
                    and body.get("relationship_alignment")
                    != expected_dependency["alignment"]
                ):
                    raise CorridorKitError(
                        "v4 typed dependency contradicts relationship alignment"
                    )
            elif successor_fields:
                raise CorridorKitError(
                    "legacy typed dependency cannot claim successor provenance"
                )
            known_rule_ids = set(rule_records)
            known_checklist_ids = set(checklist_items)
            known_fact_ids = set(fact_records)
            if dependency_kind == "normative":
                endpoints_valid = source in known_rule_ids and target in known_rule_ids
            elif dependency_kind == "work":
                endpoints_valid = source in known_checklist_ids and target in known_checklist_ids
            else:
                evidence_nodes = known_checklist_ids.union(known_fact_ids)
                endpoints_valid = (
                    source in evidence_nodes
                    and target in evidence_nodes
                    and bool({source, target}.intersection(known_checklist_ids))
                )
                if relationship == "invalidates":
                    endpoints_valid = endpoints_valid and target in known_checklist_ids
            if not endpoints_valid:
                raise CorridorKitError("typed dependency contains a dangling or wrong-kind reference")
            if source_rule_id in rule_source_provenance_digests and dependency_kind == "work":
                if (
                    checklist_items[source]["source_rule_id"] != source_rule_id
                    or checklist_items[target]["source_rule_id"] != body["target_rule_id"]
                ):
                    raise CorridorKitError(
                        "successor work dependency endpoints contradict bound Rule direction"
                    )
                if (
                    rule_semantics[source_rule_id].get("schema_version")
                    == TYPED_RULE_SEMANTICS_SCHEMA_V4
                ):
                    source_cells = [
                        item
                        for item in checklist_items.values()
                        if item["source_rule_id"] == source_rule_id
                    ]
                    target_cells = [
                        item
                        for item in checklist_items.values()
                        if item["source_rule_id"] == body["target_rule_id"]
                    ]
                    alignment_projection = project_relationship_alignment(
                        alignment=body["relationship_alignment"],
                        source_cells=source_cells,
                        target_cells=target_cells,
                    )
                    allowed_pairs = {
                        (item["from_ref"], item["to_ref"])
                        for item in alignment_projection["edge_pairs"]
                    }
                    if alignment_projection["issues"] or (source, target) not in allowed_pairs:
                        raise CorridorKitError(
                            "v4 work dependency endpoint pair is outside relationship alignment"
                        )
            if dependency_id in typed_dependencies:
                raise CorridorKitError(f"typed dependency already exists: {dependency_id}")
            typed_dependencies[dependency_id] = dict(body)
            if relationship in HARD_DEPENDENCY_RELATIONSHIPS:
                dependant, prerequisite = _hard_dependency_pair(body)
                hard_dependencies.setdefault(dependant, set()).add(prerequisite)
                _assert_acyclic(hard_dependencies, label="hard dependency")
        elif record_type == "dependency_resolution":
            dependency_id = _text(body, "dependency_id")
            resolution = _text(body, "resolution")
            authority_rule_id = _text(body, "authority_rule_id")
            authority_rule_record_id = _text(body, "authority_rule_record_id")
            _text(body, "receipt_ref")
            dependency = typed_dependencies.get(dependency_id)
            if dependency is None or dependency["relationship"] != "conflicts":
                raise CorridorKitError("dependency resolution must reference an unresolved conflict")
            if dependency_id in dependency_resolutions:
                raise CorridorKitError(f"dependency conflict is already resolved: {dependency_id}")
            if resolution not in {"precedence", "reconciled", "waived"}:
                raise CorridorKitError("unknown dependency conflict resolution")
            if (
                rule_records.get(authority_rule_id) != authority_rule_record_id
                or authority_rule_id not in ratified_rules
                or authority_rule_id != dependency["source_rule_id"]
                or authority_rule_record_id != dependency["source_rule_record_id"]
            ):
                raise CorridorKitError(
                    "dependency resolution requires its current ratified source authority Rule"
                )
            winner_ref = body.get("winner_ref")
            if resolution == "precedence":
                if winner_ref not in {dependency["from_ref"], dependency["to_ref"]}:
                    raise CorridorKitError(
                        "precedence resolution winner_ref must be one conflict endpoint"
                    )
            elif winner_ref is not None:
                raise CorridorKitError("winner_ref is only valid for precedence resolution")
            dependency_resolutions[dependency_id] = dict(body)
        elif record_type == "fact_proposal":
            fact_id = _text(body, "fact_id")
            _text(body, "statement")
            _text(body, "evidence_ref")
            _digest(body, "evidence_digest")
            position_ref = _text(body, "position_ref")
            if position_ref not in positions:
                raise CorridorKitError("fact proposal references an unknown Position")
            if "witness_bindings" in body:
                bindings = body["witness_bindings"]
                if not isinstance(bindings, list) or not bindings:
                    raise CorridorKitError(
                        "fact witness_bindings must be a non-empty list"
                    )
                seen_bindings: set[str] = set()
                for binding in bindings:
                    if not isinstance(binding, dict) or set(binding) != {
                        "checklist_item_id",
                        "source_rule_semantics_digest",
                        "operators",
                    }:
                        raise CorridorKitError(
                            "fact witness binding must name checklist, semantics digest, and operators"
                        )
                    item_id = _text(binding, "checklist_item_id")
                    if item_id not in checklist_items or item_id in seen_bindings:
                        raise CorridorKitError(
                            "fact witness binding references an unknown or duplicated checklist item"
                        )
                    seen_bindings.add(item_id)
                    _digest(binding, "source_rule_semantics_digest")
                    _text_list(binding, "operators", nonempty=True)
            if fact_id in fact_records:
                raise CorridorKitError(f"fact proposal already exists: {fact_id}")
            fact_records[fact_id] = expected_record
            fact_bodies[fact_id] = dict(body)
        elif record_type == "fact_admission":
            fact_id = _text(body, "fact_id")
            fact_record_id = _text(body, "fact_record_id")
            rule_id = _text(body, "admission_rule_id")
            rule_record_id = _text(body, "admission_rule_record_id")
            _text(body, "admitter_ref")
            _text(body, "receipt_ref")
            if fact_records.get(fact_id) != fact_record_id:
                raise CorridorKitError(f"fact admission does not bind the proposal: {fact_id}")
            if rule_records.get(rule_id) != rule_record_id or rule_id not in ratified_rules:
                raise CorridorKitError("fact admission requires the current ratified admission Rule")
            if fact_id in fact_receipts:
                raise CorridorKitError(f"fact already admitted: {fact_id}")
            fact_receipts[fact_id] = expected_record
        elif record_type == "position_checkpoint":
            position_id = _text(body, "position_id")
            previous_position_ref = body.get("previous_position_ref")
            expected_previous = next(reversed(positions), None)
            if previous_position_ref != expected_previous:
                raise CorridorKitError("Position checkpoint does not bind the latest Position")
            if not isinstance(body.get("task_identity"), dict) or not body["task_identity"]:
                raise CorridorKitError("Position checkpoint requires task_identity")
            if not isinstance(body.get("scope"), dict) or not body["scope"]:
                raise CorridorKitError("Position checkpoint requires scope")
            if not isinstance(body.get("role_assignments"), dict) or not body["role_assignments"]:
                raise CorridorKitError("Position checkpoint requires role_assignments")
            rule_refs = _text_list(body, "rule_record_ids", nonempty=True)
            receipt_refs = _text_list(body, "fact_receipt_ids")
            artifact_refs = _text_list(body, "artifact_record_ids")
            current_ratified_rule_records = {
                rule_records[rule_id] for rule_id in ratified_rules
            }
            if set(rule_refs) != current_ratified_rule_records:
                raise CorridorKitError(
                    "Position checkpoint must bind the whole current ratified Rule closure"
                )
            closure_refs = body.get("rule_closure_digests")
            if ratified_rule_closures:
                if not isinstance(closure_refs, list) or any(
                    not isinstance(item, str) for item in closure_refs
                ):
                    raise CorridorKitError(
                        "v4 Position must bind current RuleClosure digests"
                    )
                if set(closure_refs) != set(ratified_rule_closures.values()):
                    raise CorridorKitError(
                        "Position does not bind the whole current RuleClosure"
                    )
            elif closure_refs is not None:
                raise CorridorKitError(
                    "legacy Position cannot claim successor RuleClosure digests"
                )
            if set(receipt_refs) != set(fact_receipts.values()):
                raise CorridorKitError(
                    "Position checkpoint must bind the whole current admitted Fact receipt set"
                )
            if set(artifact_refs) != set(latest_artifact_record_ids.values()):
                raise CorridorKitError(
                    "Position checkpoint must bind the whole current latest artifact revision set"
                )
            if position_id in position_ids:
                raise CorridorKitError(f"Position checkpoint already exists: {position_id}")
            if _position_bindings_present(body):
                checkpoint_kind = _text(body, "checkpoint_kind")
                if checkpoint_kind not in CHECKPOINT_KINDS:
                    raise CorridorKitError(f"unknown Position checkpoint_kind: {checkpoint_kind}")
                checklist_refs = _text_list(body, "checklist_item_ids")
                current_checklist_ids = {
                    item_id
                    for item_id, item in checklist_items.items()
                    if rule_records.get(item["source_rule_id"])
                    == item["source_rule_record_id"]
                    and item["source_rule_id"] in ratified_rules
                }
                if set(checklist_refs) != current_checklist_ids:
                    raise CorridorKitError(
                        "Position checkpoint must bind the whole current acceptance checklist"
                    )
                assessments = _object(body, "checklist_assessments")
                if set(assessments) != current_checklist_ids:
                    raise CorridorKitError(
                        "Position checklist assessments must cover every current checklist item"
                    )
                for item_id, assessment in assessments.items():
                    checklist_item = checklist_items[item_id]
                    typed_v2 = checklist_item.get("typed_rule_semantics_schema") in {
                        "charting-loop/typed-rule-semantics/v2",
                        TYPED_RULE_SEMANTICS_SCHEMA_V3,
                        TYPED_RULE_SEMANTICS_SCHEMA_V4,
                    }
                    expected_assessment_fields = {
                        "status",
                        "witness_fact_receipt_ids",
                    }
                    if typed_v2:
                        expected_assessment_fields.add("applicability_status")
                    if (
                        not isinstance(assessment, dict)
                        or set(assessment) != expected_assessment_fields
                    ):
                        raise CorridorKitError(
                            f"checklist assessment {item_id} has unknown or missing fields"
                        )
                    if assessment.get("status") not in CHECKLIST_STATUSES:
                        raise CorridorKitError(f"checklist assessment {item_id} has unknown status")
                    witness_refs = _text_list(assessment, "witness_fact_receipt_ids")
                    if not set(witness_refs).issubset(set(receipt_refs)):
                        raise CorridorKitError(
                            f"checklist assessment {item_id} uses Facts outside its Position"
                        )
                    if typed_v2:
                        applicability_status = assessment.get("applicability_status")
                        if applicability_status not in CHECKLIST_APPLICABILITY_STATUSES:
                            raise CorridorKitError(
                                f"checklist assessment {item_id} has unknown applicability status"
                            )
                        applicability = checklist_item.get("applicability")
                        if not isinstance(applicability, dict):
                            raise CorridorKitError(
                                f"typed checklist item {item_id} lacks applicability semantics"
                            )
                        if applicability_status == "not_applicable":
                            if applicability.get("mode") != "conditional":
                                raise CorridorKitError(
                                    f"always-applicable checklist item {item_id} cannot be not_applicable"
                                )
                            if assessment.get("status") != "unknown" or not witness_refs:
                                raise CorridorKitError(
                                    f"not-applicable checklist item {item_id} requires unknown status and a Fact witness"
                                )
                        elif applicability_status == "unresolved" and assessment.get(
                            "status"
                        ) != "unknown":
                            raise CorridorKitError(
                                f"unresolved applicability for {item_id} requires unknown status"
                            )
                active_typed_dependencies = {
                    dependency_id: dependency
                    for dependency_id, dependency in typed_dependencies.items()
                    if dependency["source_rule_id"] in ratified_rules
                    and rule_records.get(dependency["source_rule_id"])
                    == dependency["source_rule_record_id"]
                }
                active_dependency_resolutions = {
                    dependency_id
                    for dependency_id, resolution in dependency_resolutions.items()
                    if resolution["authority_rule_id"] in ratified_rules
                    and rule_records.get(resolution["authority_rule_id"])
                    == resolution["authority_rule_record_id"]
                }
                ready, blocked, unresolved = _checklist_frontier(
                    checklist_items={
                        item_id: checklist_items[item_id]
                        for item_id in current_checklist_ids
                    },
                    assessments=assessments,
                    typed_dependencies=active_typed_dependencies,
                    resolved_dependency_ids=active_dependency_resolutions,
                    admitted_fact_ids={
                        fact_id
                        for fact_id, receipt_id in fact_receipts.items()
                        if receipt_id in receipt_refs
                    },
                )
                if _text_list(body, "ready_item_ids") != ready:
                    raise CorridorKitError("Position ready frontier does not match the graph")
                if _text_list(body, "blocked_item_ids") != blocked:
                    raise CorridorKitError("Position blocked frontier does not match the graph")
                if _text_list(body, "unresolved_checklist_item_ids") != unresolved:
                    raise CorridorKitError("Position unresolved checklist does not match the graph")
                if expected_previous is not None:
                    previous_position = positions[expected_previous]
                    if _position_bindings_present(previous_position):
                        prior_assessments = previous_position["checklist_assessments"]
                        for dependency in active_typed_dependencies.values():
                            if dependency["relationship"] != "invalidates":
                                continue
                            source = dependency["from_ref"]
                            target = dependency["to_ref"]
                            if target not in assessments:
                                continue
                            source_changed = (
                                prior_assessments.get(source) != assessments.get(source)
                                if source in assessments
                                else (
                                    (fact_receipts.get(source) in receipt_refs)
                                    != (
                                        fact_receipts.get(source)
                                        in previous_position["fact_receipt_ids"]
                                    )
                                )
                            )
                            if source_changed:
                                target_assessment = assessments[target]
                                if target_assessment["status"] != "unknown" or target_assessment[
                                    "witness_fact_receipt_ids"
                                ]:
                                    raise CorridorKitError(
                                        "changed upstream assessment must invalidate downstream assessment"
                                    )
            position_ids.add(position_id)
            positions[expected_record] = {"position_id": position_id, **body}
        elif record_type == "direction_proposal":
            direction_id = _text(body, "direction_id")
            position_ref = _text(body, "position_ref")
            _text(body, "statement")
            rule_refs = _text_list(body, "rule_record_ids", nonempty=True)
            receipt_refs = _text_list(body, "fact_receipt_ids")
            _text_list(body, "evidence_refs")
            if position_ref not in positions:
                raise CorridorKitError("Direction proposal references an unknown Position")
            position = positions[position_ref]
            if not set(rule_refs).issubset(set(position["rule_record_ids"])):
                raise CorridorKitError("Direction proposal uses Rules outside its Position")
            if not set(receipt_refs).issubset(set(position["fact_receipt_ids"])):
                raise CorridorKitError("Direction proposal uses Facts outside its Position")
            position_closures = position.get("rule_closure_digests")
            direction_closures = body.get("rule_closure_digests")
            if position_closures is not None:
                if direction_closures != position_closures:
                    raise CorridorKitError(
                        "effective Direction must bind its Position RuleClosure digests"
                    )
            elif direction_closures is not None:
                raise CorridorKitError(
                    "Direction cannot introduce RuleClosure absent from its Position"
                )
            if _direction_bindings_present(body):
                if not _position_bindings_present(position):
                    raise CorridorKitError(
                        "Direction checklist bindings require a checklist-bound Position"
                    )
                for field in (
                    "checklist_item_ids",
                    "ready_item_ids",
                    "blocked_item_ids",
                    "unresolved_checklist_item_ids",
                ):
                    if _text_list(body, field) != position[field]:
                        raise CorridorKitError(
                            f"Direction {field} does not match its exact Position"
                        )
            if direction_id in direction_ids:
                raise CorridorKitError(f"Direction proposal already exists: {direction_id}")
            direction_ids.add(direction_id)
            directions[expected_record] = {"direction_id": direction_id, **body}
        elif record_type == "direction_snapshot":
            position_ref = _text(body, "position_ref")
            direction_refs = _text_list(body, "direction_record_ids", nonempty=True)
            selected = body.get("selected_direction_record_id")
            if position_ref not in positions:
                raise CorridorKitError("Direction snapshot references an unknown Position")
            if any(
                ref not in directions or directions[ref]["position_ref"] != position_ref
                for ref in direction_refs
            ):
                raise CorridorKitError("Direction snapshot references an unknown proposal")
            if selected is not None and selected not in direction_refs:
                raise CorridorKitError("selected Direction is not in the snapshot")
        elif record_type == "artifact_revision":
            artifact_id = _text(body, "artifact_id")
            _text(body, "path")
            _digest(body, "digest")
            position_ref = _text(body, "position_ref")
            revision = body.get("revision")
            if position_ref not in positions:
                raise CorridorKitError("artifact revision references an unknown Position")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
                raise CorridorKitError("artifact revision must be a positive integer")
            if revision != artifacts.get(artifact_id, 0) + 1:
                raise CorridorKitError("artifact revision is not monotonic")
            artifacts[artifact_id] = revision
            latest_artifact_record_ids[artifact_id] = expected_record

    return {
        "ok": True,
        "schema_version": GRAPH_REPLAY_SCHEMA,
        "record_count": len(records),
        "head_record_id": previous,
        "task_source_artifact_count": len(source_artifacts),
        "source_clause_count": len(source_clauses),
        "rule_count": len(rule_records),
        "ratified_rule_count": len(ratified_rules),
        "rule_closure_count": len(ratified_rule_closures),
        "acceptance_checklist_item_count": len(checklist_items),
        "typed_dependency_count": len(typed_dependencies),
        "dependency_resolution_count": len(dependency_resolutions),
        "fact_proposal_count": len(fact_records),
        "admitted_fact_count": len(fact_receipts),
        "position_count": len(positions),
        "direction_proposal_count": len(directions),
        "artifact_count": len(artifacts),
        "structurally_valid": True,
        "task_truth_assessed": False,
        "pass_assessed": False,
        "authorizes_mutation": False,
        "blocking_gate": False,
    }


def _graph_projection(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Project current identities after structural validation, without task judgment."""

    source_artifacts: dict[str, dict[str, Any]] = {}
    source_clauses: dict[str, dict[str, Any]] = {}
    rule_records: dict[str, str] = {}
    rule_statements: dict[str, str] = {}
    rule_semantics: dict[str, dict[str, Any]] = {}
    rule_semantics_digests: dict[str, str] = {}
    rule_source_provenance_digests: dict[str, str] = {}
    rule_source_clause_ids: dict[str, list[str]] = {}
    rule_source_bindings: dict[str, list[dict[str, str]]] = {}
    ratified_rules: set[str] = set()
    rule_closures: dict[str, str] = {}
    checklist_items: dict[str, dict[str, Any]] = {}
    rule_dependencies: list[dict[str, Any]] = []
    dependencies: dict[str, dict[str, Any]] = {}
    resolutions: dict[str, dict[str, Any]] = {}
    fact_ids: set[str] = set()
    fact_bodies: dict[str, dict[str, Any]] = {}
    fact_receipts: dict[str, str] = {}
    fact_receipt_ids: dict[str, str] = {}
    positions: dict[str, dict[str, Any]] = {}
    directions: dict[str, dict[str, Any]] = {}
    direction_snapshots: list[dict[str, Any]] = []
    for record in records:
        record_type = record["record_type"]
        body = record["body"]
        if record_type == "task_source_artifact":
            source_artifacts[body["source_id"]] = dict(body)
        elif record_type == "source_clause":
            source_clauses[body["clause_id"]] = dict(body)
        elif record_type == "rule_proposal":
            rule_records[body["rule_id"]] = record["record_id"]
            rule_statements[body["rule_id"]] = body["statement"]
            if "semantics" in body:
                rule_semantics[body["rule_id"]] = dict(body["semantics"])
                rule_semantics_digests[body["rule_id"]] = body[
                    "rule_semantics_digest"
                ]
                if "rule_source_provenance_digest" in body:
                    rule_source_provenance_digests[body["rule_id"]] = body[
                        "rule_source_provenance_digest"
                    ]
                    rule_source_clause_ids[body["rule_id"]] = list(
                        body["source_clause_ids"]
                    )
                    rule_source_bindings[body["rule_id"]] = list(body["source_slices"])
                else:
                    rule_source_provenance_digests.pop(body["rule_id"], None)
                    rule_source_clause_ids.pop(body["rule_id"], None)
                    rule_source_bindings.pop(body["rule_id"], None)
        elif record_type == "rule_revision":
            rule_records[body["rule_id"]] = record["record_id"]
            rule_statements[body["rule_id"]] = body["statement"]
            if "semantics" in body:
                rule_semantics[body["rule_id"]] = dict(body["semantics"])
                rule_semantics_digests[body["rule_id"]] = body[
                    "rule_semantics_digest"
                ]
                if "rule_source_provenance_digest" in body:
                    rule_source_provenance_digests[body["rule_id"]] = body[
                        "rule_source_provenance_digest"
                    ]
                    rule_source_clause_ids[body["rule_id"]] = list(
                        body["source_clause_ids"]
                    )
                    rule_source_bindings[body["rule_id"]] = list(body["source_slices"])
                else:
                    rule_source_provenance_digests.pop(body["rule_id"], None)
                    rule_source_clause_ids.pop(body["rule_id"], None)
                    rule_source_bindings.pop(body["rule_id"], None)
            else:
                rule_semantics.pop(body["rule_id"], None)
                rule_semantics_digests.pop(body["rule_id"], None)
                rule_source_provenance_digests.pop(body["rule_id"], None)
                rule_source_clause_ids.pop(body["rule_id"], None)
                rule_source_bindings.pop(body["rule_id"], None)
            ratified_rules.discard(body["rule_id"])
            rule_closures.pop(body["rule_id"], None)
        elif record_type == "rule_ratification":
            ratified_rules.add(body["rule_id"])
            if "rule_closure_digest" in body:
                rule_closures[body["rule_id"]] = body["rule_closure_digest"]
        elif record_type == "rule_dependency":
            rule_dependencies.append(dict(body))
        elif record_type == "acceptance_checklist_item":
            checklist_items[body["checklist_item_id"]] = {
                **body,
                "record_id": record["record_id"],
            }
        elif record_type == "typed_dependency":
            dependencies[body["dependency_id"]] = dict(body)
        elif record_type == "dependency_resolution":
            resolutions[body["dependency_id"]] = dict(body)
        elif record_type == "fact_proposal":
            fact_ids.add(body["fact_id"])
            fact_bodies[body["fact_id"]] = dict(body)
        elif record_type == "fact_admission":
            fact_receipts[body["fact_id"]] = record["record_id"]
            fact_receipt_ids[record["record_id"]] = body["fact_id"]
        elif record_type == "position_checkpoint":
            positions[record["record_id"]] = dict(body)
        elif record_type == "direction_proposal":
            directions[record["record_id"]] = dict(body)
        elif record_type == "direction_snapshot":
            direction_snapshots.append({**body, "record_id": record["record_id"]})
    current_checklists = {
        item_id: item
        for item_id, item in checklist_items.items()
        if item["source_rule_id"] in ratified_rules
        and rule_records.get(item["source_rule_id"]) == item["source_rule_record_id"]
    }
    return {
        "source_artifacts": source_artifacts,
        "source_clauses": source_clauses,
        "rule_records": rule_records,
        "rule_statements": rule_statements,
        "rule_semantics": rule_semantics,
        "rule_semantics_digests": rule_semantics_digests,
        "rule_source_provenance_digests": rule_source_provenance_digests,
        "rule_source_clause_ids": rule_source_clause_ids,
        "rule_source_bindings": rule_source_bindings,
        "ratified_rules": ratified_rules,
        "rule_closures": rule_closures,
        "checklist_items": current_checklists,
        "rule_dependencies": rule_dependencies,
        "dependencies": dependencies,
        "resolutions": resolutions,
        "fact_ids": fact_ids,
        "fact_bodies": fact_bodies,
        "fact_receipts": fact_receipts,
        "fact_receipt_ids": fact_receipt_ids,
        "positions": positions,
        "directions": directions,
        "direction_snapshots": direction_snapshots,
    }


def _doctor_code_digest() -> str:
    try:
        return sha256_bytes(Path(__file__).read_bytes())
    except OSError:
        return sha256_json(
            {
                "schema_version": GRAPH_DOCTOR_SCHEMA,
                "relationships": sorted(DEPENDENCY_RELATIONSHIPS),
                "checkpoint_kinds": sorted(CHECKPOINT_KINDS),
            }
        )


def graph_doctor(path: Path) -> dict[str, Any]:
    """Inspect exact graph bytes without mutation or authority side effects.

    The classification describes graph evidence only.  It is never task truth,
    official verification, delivery authority, or a runtime Gate.
    """

    graph_bytes_digest: str | None = None
    try:
        if path.is_symlink() or not path.is_file():
            raise CorridorKitError(f"graph must be a regular non-symlink file: {path}")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise CorridorKitError(f"graph exceeds {MAX_JSON_BYTES} bytes: {path}")
        graph_bytes_digest = sha256_bytes(path.read_bytes())
        records = load_graph(path)
        validation = validate_graph_records(records)
    except (CorridorKitError, OSError, UnicodeError) as exc:
        error_text = str(exc)
        source_issue_id = error_text.rsplit(":", 1)[-1].strip()
        out_of_bounds = (
            [source_issue_id] if "source slice is out of bounds:" in error_text else []
        )
        non_codepoint_aligned = (
            [source_issue_id]
            if "source slice is not aligned to UTF-8 code points:" in error_text
            else []
        )
        digest_mismatch = (
            [source_issue_id]
            if "source slice digest does not match frozen bytes:" in error_text
            else []
        )
        report: dict[str, Any] = {
            "schema_version": GRAPH_DOCTOR_SCHEMA,
            "classification": "structurally_invalid",
            "structurally_valid": False,
            "graph_digest": None,
            "graph_bytes_digest": graph_bytes_digest,
            "doctor_code_digest": _doctor_code_digest(),
            "errors": [error_text],
            "incomplete_reasons": [],
            "typed_rule_coverage": {},
            "source_provenance": {
                "status": "unresolved",
                "source_ids": [],
                "clause_ids": [],
                "unresolved_source_ids": [],
                "unmapped_clause_ids": [],
                "uninventoried_source_ids": [],
                "source_less_rule_ids": [],
                "provenance_less_dependency_ids": [],
                "missing_rule_dependency_projections": [],
                "stale_rule_dependency_projections": [],
                "relationship_alignment_edge_issues": [],
                "stale_dependency_provenance_ids": [],
                "semantic_role_issues": [],
                "out_of_bounds_slice_ids": out_of_bounds,
                "non_codepoint_aligned_slice_ids": non_codepoint_aligned,
                "digest_mismatch_slice_ids": digest_mismatch,
                "dangling_dependency_provenance_ids": [],
                "internally_inconsistent_dependency_provenance_ids": [],
            },
            "hard_dependency_topological_order": [],
            "latest_position_ref": None,
            "direction_digest": None,
            "acceptance_root": None,
            "task_truth_assessed": False,
            "pass_assessed": False,
            "authorizes_mutation": False,
            "blocking_gate": False,
        }
        report["report_digest"] = sha256_json(report)
        return report

    projection = _graph_projection(records)
    checklist_items: dict[str, dict[str, Any]] = projection["checklist_items"]
    dependencies: dict[str, dict[str, Any]] = projection["dependencies"]
    source_artifacts: dict[str, dict[str, Any]] = projection["source_artifacts"]
    source_clauses: dict[str, dict[str, Any]] = projection["source_clauses"]
    unresolved_source_ids = sorted(
        source_id
        for source_id, source in source_artifacts.items()
        if source.get("retrieval_status", source.get("byte_status")) != "available"
        or (
            source.get("plane") == "normative_rule"
            and source.get("semantic_extraction_status") != "complete"
        )
    )
    unmapped_clause_ids = sorted(
        clause_id
        for clause_id, clause in source_clauses.items()
        if clause["mapping_status"] != "mapped"
    )
    inventoried_source_ids = {
        source_slice["source_id"]
        for clause in source_clauses.values()
        for source_slice in clause["source_slices"]
    }
    uninventoried_source_ids = sorted(
        source_id
        for source_id, source in source_artifacts.items()
        if source.get("retrieval_status", source.get("byte_status")) == "available"
        and source.get("plane", "normative_rule") == "normative_rule"
        and source_id not in inventoried_source_ids
    )
    source_less_rule_ids = sorted(
        rule_id
        for rule_id, semantics in projection["rule_semantics"].items()
        if semantics.get("schema_version") in {
            TYPED_RULE_SEMANTICS_SCHEMA_V3,
            TYPED_RULE_SEMANTICS_SCHEMA_V4,
        }
        and rule_id not in projection["rule_source_provenance_digests"]
    )
    role_issues: list[str] = []
    slice_to_clause = {
        source_slice["slice_id"]: clause_id
        for clause_id, clause in source_clauses.items()
        for source_slice in clause["source_slices"]
    }
    for clause_id, clause in source_clauses.items():
        if clause["mapping_status"] != "mapped":
            continue
        declared_roles = {
            binding["semantic_role"]
            for rule_id in clause["rule_ids"]
            for binding in projection["rule_source_bindings"].get(rule_id, [])
            if slice_to_clause.get(binding["slice_id"]) == clause_id
        }
        missing_roles = sorted(
            set(clause["required_semantic_roles"]) - declared_roles
        )
        if missing_roles:
            role_issues.append(f"{clause_id}:missing:" + ",".join(missing_roles))
    provenance_less_dependency_ids = sorted(
        dependency_id
        for dependency_id, dependency in dependencies.items()
        if dependency["source_rule_id"]
        in projection["rule_source_provenance_digests"]
        and "edge_provenance" not in dependency
    )
    missing_rule_dependency_projections: list[str] = []
    stale_rule_dependency_projections: list[str] = []
    relationship_alignment_edge_issues: list[dict[str, Any]] = []
    for source_rule_id, semantics in projection["rule_semantics"].items():
        if semantics.get("schema_version") not in {
            TYPED_RULE_SEMANTICS_SCHEMA_V3,
            TYPED_RULE_SEMANTICS_SCHEMA_V4,
        }:
            continue
        for semantic_dependency in semantics["dependencies"]:
            identity = (
                f"{source_rule_id}:{semantic_dependency['relationship']}:"
                f"{semantic_dependency['target_rule_id']}"
            )
            projected = next(
                (
                    item
                    for item in projection["rule_dependencies"]
                    if item["from_rule_id"] == source_rule_id
                    and item["to_rule_id"] == semantic_dependency["target_rule_id"]
                    and item["relationship"] == semantic_dependency["relationship"]
                ),
                None,
            )
            if projected is None:
                missing_rule_dependency_projections.append(identity)
            elif (
                projected.get("source_rule_provenance_digest")
                != projection["rule_source_provenance_digests"].get(source_rule_id)
                or projected.get("target_rule_provenance_digest")
                != projection["rule_source_provenance_digests"].get(
                    semantic_dependency["target_rule_id"]
                )
                or (
                    "alignment" in semantic_dependency
                    and projected.get("relationship_alignment")
                    != semantic_dependency["alignment"]
                )
            ):
                stale_rule_dependency_projections.append(identity)
            if (
                semantics.get("schema_version") == TYPED_RULE_SEMANTICS_SCHEMA_V4
                and "alignment" in semantic_dependency
                and semantic_dependency["target_rule_id"]
                in projection["rule_semantics"]
            ):
                target_rule_id = semantic_dependency["target_rule_id"]
                alignment_projection = project_relationship_alignment(
                    alignment=semantic_dependency["alignment"],
                    source_cells=[
                        item
                        for item in checklist_items.values()
                        if item["source_rule_id"] == source_rule_id
                    ],
                    target_cells=[
                        item
                        for item in checklist_items.values()
                        if item["source_rule_id"] == target_rule_id
                    ],
                )
                graph_relationship = (
                    "precondition_for"
                    if semantic_dependency["relationship"] == "precedes"
                    else semantic_dependency["relationship"]
                )
                expected_pairs = {
                    (item["from_ref"], item["to_ref"])
                    for item in alignment_projection["edge_pairs"]
                }
                actual_pairs = {
                    (item["from_ref"], item["to_ref"])
                    for item in dependencies.values()
                    if item.get("source_rule_id") == source_rule_id
                    and item.get("target_rule_id") == target_rule_id
                    and item.get("relationship") == graph_relationship
                    and item.get("dependency_kind") == "work"
                }
                if (
                    alignment_projection["issues"]
                    or expected_pairs != actual_pairs
                ):
                    relationship_alignment_edge_issues.append(
                        {
                            "identity": identity,
                            "projection_issues": alignment_projection["issues"],
                            "missing_pairs": sorted(expected_pairs - actual_pairs),
                            "extra_pairs": sorted(actual_pairs - expected_pairs),
                        }
                    )
    current_nodes = set(checklist_items).union(projection["ratified_rules"])
    # Proposed Facts belong to the dependency topology, but only a receipt in
    # ``fact_receipts`` satisfies an evidence dependency.  Keeping those two
    # identities separate lets Doctor expose a blocked edge without pretending
    # that observing a proposal admitted it.
    current_nodes.update(projection["fact_ids"])
    hard_edges: dict[str, set[str]] = {}
    unresolved_conflicts: list[str] = []
    stale_dependency_ids: list[str] = []
    active_resolutions = {
        dependency_id
        for dependency_id, resolution in projection["resolutions"].items()
        if resolution["authority_rule_id"] in projection["ratified_rules"]
        and projection["rule_records"].get(resolution["authority_rule_id"])
        == resolution["authority_rule_record_id"]
    }
    for dependency_id, dependency in dependencies.items():
        if (
            dependency["source_rule_id"] not in projection["ratified_rules"]
            or projection["rule_records"].get(dependency["source_rule_id"])
            != dependency["source_rule_record_id"]
            or (
                "target_rule_id" in dependency
                and (
                    dependency["target_rule_id"] not in projection["ratified_rules"]
                    or projection["rule_records"].get(dependency["target_rule_id"])
                    != dependency.get("target_rule_record_id")
                    or projection["rule_source_provenance_digests"].get(
                        dependency["source_rule_id"]
                    )
                    != dependency.get("source_rule_provenance_digest")
                    or projection["rule_source_provenance_digests"].get(
                        dependency["target_rule_id"]
                    )
                    != dependency.get("target_rule_provenance_digest")
                )
            )
        ):
            stale_dependency_ids.append(dependency_id)
            continue
        source = dependency["from_ref"]
        target = dependency["to_ref"]
        if source not in current_nodes or target not in current_nodes:
            continue
        if dependency["relationship"] in HARD_DEPENDENCY_RELATIONSHIPS:
            dependant, prerequisite = _hard_dependency_pair(dependency)
            hard_edges.setdefault(dependant, set()).add(prerequisite)
        elif (
            dependency["relationship"] == "conflicts"
            and dependency_id not in active_resolutions
        ):
            unresolved_conflicts.append(dependency_id)
    topological_order = _topological_order(current_nodes, hard_edges)

    positions: dict[str, dict[str, Any]] = projection["positions"]
    latest_position_ref = next(reversed(positions), None)
    latest_position = positions.get(latest_position_ref) if latest_position_ref else None
    incomplete_reasons: list[str] = []
    stale_or_missing_rule_closures = sorted(
        rule_id
        for rule_id, semantics in projection["rule_semantics"].items()
        if semantics.get("schema_version") == TYPED_RULE_SEMANTICS_SCHEMA_V4
        and rule_id in projection["ratified_rules"]
        and rule_id not in projection["rule_closures"]
    )
    incomplete_reasons.extend(
        f"v4_rule_missing_authorized_closure:{rule_id}"
        for rule_id in stale_or_missing_rule_closures
    )
    if source_artifacts:
        incomplete_reasons.extend(
            f"unresolved_task_source:{source_id}"
            for source_id in unresolved_source_ids
        )
        incomplete_reasons.extend(
            f"unmapped_source_clause:{clause_id}"
            for clause_id in unmapped_clause_ids
        )
        incomplete_reasons.extend(
            f"uninventoried_task_source:{source_id}"
            for source_id in uninventoried_source_ids
        )
        incomplete_reasons.extend(
            f"source_less_successor_rule:{rule_id}"
            for rule_id in source_less_rule_ids
        )
        incomplete_reasons.extend(
            f"source_semantic_role_inconsistent:{issue}" for issue in role_issues
        )
        incomplete_reasons.extend(
            f"dependency_provenance_missing:{dependency_id}"
            for dependency_id in provenance_less_dependency_ids
        )
        incomplete_reasons.extend(
            f"rule_dependency_projection_missing:{identity}"
            for identity in missing_rule_dependency_projections
        )
        incomplete_reasons.extend(
            f"rule_dependency_projection_stale:{identity}"
            for identity in stale_rule_dependency_projections
        )
        incomplete_reasons.extend(
            f"relationship_alignment_edge_set_mismatch:{item['identity']}"
            for item in relationship_alignment_edge_issues
        )
    if not checklist_items:
        incomplete_reasons.append("no_current_acceptance_checklist")
    checklist_rule_ids = {item["source_rule_id"] for item in checklist_items.values()}
    for rule_id in sorted(projection["ratified_rules"] - checklist_rule_ids):
        incomplete_reasons.append(f"rule_missing_checklist:{rule_id}")
    typed_rule_coverage: dict[str, dict[str, Any]] = {}
    for rule_id in sorted(projection["ratified_rules"]):
        semantics = projection["rule_semantics"].get(rule_id)
        if semantics is None:
            continue
        expected_templates = project_rule_checklist_templates(
            rule_id=rule_id,
            statement=projection["rule_statements"][rule_id],
            semantics=semantics,
        )
        expected_ids = {
            item["checklist_item_id"] for item in expected_templates
        }
        actual_ids = {
            item_id
            for item_id, item in checklist_items.items()
            if item["source_rule_id"] == rule_id
        }
        missing_ids = sorted(expected_ids - actual_ids)
        typed_rule_coverage[rule_id] = {
            "rule_semantics_digest": projection["rule_semantics_digests"][rule_id],
            "requirement_level": semantics.get("requirement_level", "legacy_unstated"),
            "applicability": semantics.get("applicability"),
            "expected_checklist_item_ids": sorted(expected_ids),
            "actual_checklist_item_ids": sorted(actual_ids),
            "missing_checklist_item_ids": missing_ids,
        }
        incomplete_reasons.extend(
            f"typed_rule_coverage_cell_missing:{rule_id}:{item_id}"
            for item_id in missing_ids
        )
    for item_id, item in sorted(checklist_items.items()):
        if item["compilation_status"] != "complete":
            incomplete_reasons.append(
                f"checklist_compilation_{item['compilation_status']}:{item_id}"
            )
        required_partitions = item["scope"].get("required_partitions")
        if isinstance(required_partitions, list) and all(
            isinstance(value, str) and value.strip() for value in required_partitions
        ):
            omitted = sorted(set(required_partitions) - set(item["behavioral_partitions"]))
            if omitted:
                incomplete_reasons.append(
                    f"checklist_partition_coverage_missing:{item_id}:" + ",".join(omitted)
                )
    if unresolved_conflicts:
        incomplete_reasons.extend(
            f"unresolved_dependency_conflict:{value}"
            for value in sorted(unresolved_conflicts)
        )
    incomplete_reasons.extend(
        f"stale_dependency_authority:{value}" for value in sorted(stale_dependency_ids)
    )

    assessments: dict[str, Any] = {}
    acceptance_root: str | None = None
    if latest_position is None:
        incomplete_reasons.append("no_position_checkpoint")
    elif not _position_bindings_present(latest_position):
        incomplete_reasons.append("legacy_position_missing_checklist_bindings")
    else:
        assessments = latest_position["checklist_assessments"]
        if latest_position["checkpoint_kind"] != "acceptance_assessment":
            incomplete_reasons.append("latest_position_not_acceptance_assessment")
        acceptance_root = sha256_json(
            {
                "checklist_items": {
                    item_id: checklist_items[item_id]
                    for item_id in sorted(checklist_items)
                },
                "assessments": {
                    item_id: assessments[item_id] for item_id in sorted(assessments)
                },
            }
        )
        for item_id in sorted(checklist_items):
            assessment = assessments.get(item_id, {})
            not_applicable = (
                assessment.get("applicability_status") == "not_applicable"
                and bool(assessment.get("witness_fact_receipt_ids"))
            )
            if not_applicable:
                continue
            if assessment.get("status") != "pass":
                incomplete_reasons.append(f"checklist_not_passed:{item_id}")
            elif not assessment.get("witness_fact_receipt_ids"):
                incomplete_reasons.append(f"checklist_pass_missing_witness:{item_id}")
            elif "source_rule_semantics_digest" in checklist_items[item_id]:
                item = checklist_items[item_id]
                bindings: list[dict[str, Any]] = []
                for receipt_id in assessment["witness_fact_receipt_ids"]:
                    fact_id = projection["fact_receipt_ids"].get(receipt_id)
                    fact = projection["fact_bodies"].get(fact_id, {})
                    for binding in fact.get("witness_bindings", []):
                        if binding.get("checklist_item_id") == item_id:
                            bindings.append(binding)
                if not bindings:
                    incomplete_reasons.append(
                        f"checklist_witness_contract_missing:{item_id}"
                    )
                else:
                    matching = [
                        binding
                        for binding in bindings
                        if binding.get("source_rule_semantics_digest")
                        == item["source_rule_semantics_digest"]
                    ]
                    if not matching:
                        incomplete_reasons.append(
                            f"checklist_witness_semantics_mismatch:{item_id}"
                        )
                    else:
                        observed_operators = {
                            operator
                            for binding in matching
                            for operator in binding.get("operators", [])
                        }
                        missing_operators = sorted(
                            set(item["required_witness_operators"])
                            - observed_operators
                        )
                        if missing_operators:
                            incomplete_reasons.append(
                                f"checklist_witness_operators_missing:{item_id}:"
                                + ",".join(missing_operators)
                            )
        if latest_position.get("unresolved_checklist_item_ids"):
            incomplete_reasons.append("latest_position_has_unresolved_checklist_items")
        if latest_position.get("blocked_item_ids"):
            incomplete_reasons.append("latest_position_has_blocked_checklist_items")

    selected_direction_ref: str | None = None
    for snapshot in reversed(projection["direction_snapshots"]):
        if snapshot["position_ref"] == latest_position_ref:
            selected_direction_ref = snapshot.get("selected_direction_record_id")
            break
    if selected_direction_ref is None:
        selected_direction_ref = next(
            (
                record_id
                for record_id, body in reversed(list(projection["directions"].items()))
                if body["position_ref"] == latest_position_ref
            ),
            None,
        )
    selected_direction = projection["directions"].get(selected_direction_ref)
    if selected_direction is None:
        incomplete_reasons.append("no_direction_for_latest_position")
    elif not _direction_bindings_present(selected_direction):
        incomplete_reasons.append("legacy_direction_missing_checklist_bindings")
    elif latest_position is not None:
        for field in (
            "checklist_item_ids",
            "ready_item_ids",
            "blocked_item_ids",
            "unresolved_checklist_item_ids",
        ):
            if selected_direction[field] != latest_position[field]:
                incomplete_reasons.append(f"stale_direction_{field}")

    classification = (
        "acceptance_assessed_complete"
        if not incomplete_reasons
        else "structurally_valid_but_incomplete"
    )
    report = {
        "schema_version": GRAPH_DOCTOR_SCHEMA,
        "classification": classification,
        "structurally_valid": True,
        "graph_digest": sha256_json(records),
        "graph_bytes_digest": graph_bytes_digest,
        "doctor_code_digest": _doctor_code_digest(),
        "record_count": validation["record_count"],
        "head_record_id": validation["head_record_id"],
        "errors": [],
        "incomplete_reasons": sorted(set(incomplete_reasons)),
        "typed_rule_coverage": typed_rule_coverage,
        "source_provenance": {
            "status": (
                "authority_snapshot_with_exact_byte_slices"
                if any("plane" in source for source in source_artifacts.values())
                and not (
                    unresolved_source_ids
                    or unmapped_clause_ids
                    or uninventoried_source_ids
                    or source_less_rule_ids
                    or role_issues
                    or provenance_less_dependency_ids
                    or missing_rule_dependency_projections
                    or stale_rule_dependency_projections
                    or relationship_alignment_edge_issues
                    or stale_dependency_ids
                )
                else "exact_byte_slices"
                if source_artifacts and not (
                    unresolved_source_ids
                    or unmapped_clause_ids
                    or uninventoried_source_ids
                    or source_less_rule_ids
                    or role_issues
                    or provenance_less_dependency_ids
                    or missing_rule_dependency_projections
                    or stale_rule_dependency_projections
                    or relationship_alignment_edge_issues
                    or stale_dependency_ids
                )
                else "unresolved"
                if source_artifacts
                else "legacy_unassessed"
            ),
            "source_ids": sorted(source_artifacts),
            "clause_ids": sorted(source_clauses),
            "unresolved_source_ids": unresolved_source_ids,
            "unmapped_clause_ids": unmapped_clause_ids,
            "uninventoried_source_ids": uninventoried_source_ids,
            "source_less_rule_ids": source_less_rule_ids,
            "provenance_less_dependency_ids": provenance_less_dependency_ids,
            "missing_rule_dependency_projections": sorted(
                missing_rule_dependency_projections
            ),
            "stale_rule_dependency_projections": sorted(
                stale_rule_dependency_projections
            ),
            "relationship_alignment_edge_issues": relationship_alignment_edge_issues,
            "stale_dependency_provenance_ids": sorted(stale_dependency_ids),
            "semantic_role_issues": role_issues,
            "out_of_bounds_slice_ids": [],
            "non_codepoint_aligned_slice_ids": [],
            "digest_mismatch_slice_ids": [],
            "dangling_dependency_provenance_ids": [],
            "internally_inconsistent_dependency_provenance_ids": [],
        },
        "rule_ratification": {
            "rule_closure_digests": dict(sorted(projection["rule_closures"].items())),
            "missing_or_stale_rule_ids": stale_or_missing_rule_closures,
        },
        "hard_dependency_topological_order": topological_order,
        "ready_item_ids": (
            list(latest_position.get("ready_item_ids", [])) if latest_position else []
        ),
        "blocked_item_ids": (
            list(latest_position.get("blocked_item_ids", [])) if latest_position else []
        ),
        "latest_position_ref": latest_position_ref,
        "direction_digest": selected_direction_ref,
        "acceptance_root": acceptance_root,
        "task_truth_assessed": False,
        "pass_assessed": False,
        "authorizes_mutation": False,
        "blocking_gate": False,
    }
    report["report_digest"] = sha256_json(report)
    return report


def replay_graph(path: Path) -> dict[str, Any]:
    records = load_graph(path)
    report = validate_graph_records(records)
    report["graph_digest"] = sha256_json(records)
    report["latest_position_ref"] = next(
        (record["record_id"] for record in reversed(records) if record["record_type"] == "position_checkpoint"),
        None,
    )
    report["latest_direction_snapshot_ref"] = next(
        (record["record_id"] for record in reversed(records) if record["record_type"] == "direction_snapshot"),
        None,
    )
    report["records"] = records
    return report


def initialize_graph(path: Path) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        raise CorridorKitError(f"graph output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, b"", mode=0o600)
    return replay_graph(path)


def append_graph_record(
    path: Path, *, record_type: str, actor: str, body: Mapping[str, Any]
) -> dict[str, Any]:
    """Append one valid record atomically; invalid input leaves bytes unchanged."""

    if record_type not in GRAPH_RECORD_TYPES:
        raise CorridorKitError(f"unknown graph record type: {record_type}")
    if actor not in GRAPH_ACTORS:
        raise CorridorKitError(f"unknown graph actor: {actor}")
    if not isinstance(body, Mapping):
        raise CorridorKitError("graph body must be an object")
    canonical_body = json.loads(canonical_json_bytes(dict(body)).decode("utf-8"))
    records = load_graph(path)
    content_id = _content_id(record_type, actor, canonical_body)
    for existing in records:
        if existing["content_id"] == content_id:
            return {"ok": True, "idempotent": True, "appended": False, "record": existing}
    previous = records[-1]["record_id"] if records else None
    payload = _identity_payload(
        sequence=len(records) + 1,
        record_type=record_type,
        actor=actor,
        body=canonical_body,
        previous=previous,
    )
    record = {
        **payload,
        "content_id": content_id,
        "record_id": _record_id(payload),
    }
    candidate = [*records, record]
    validate_graph_records(candidate)
    encoded = b"".join(canonical_json_bytes(item) + b"\n" for item in candidate)
    atomic_write_bytes(path, encoded, mode=0o600)
    return {"ok": True, "idempotent": False, "appended": True, "record": record}
