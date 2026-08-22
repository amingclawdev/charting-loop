"""Task-neutral append-only graph mechanics for integrated Method execution.

The graph stores identity-bound records.  It validates structure and provenance,
but deliberately does not decide task truth, correctness, completion, or PASS.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .core import (
    MAX_JSON_BYTES,
    CorridorKitError,
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_json,
)


GRAPH_RECORD_SCHEMA = "charting-loop/graph-kernel-record/v1"
GRAPH_REPLAY_SCHEMA = "charting-loop/graph-kernel-replay/v1"
GRAPH_RECORD_TYPES = frozenset(
    {
        "rule_proposal",
        "rule_revision",
        "rule_ratification",
        "rule_dependency",
        "fact_proposal",
        "fact_admission",
        "position_checkpoint",
        "direction_proposal",
        "direction_snapshot",
        "artifact_revision",
    }
)
GRAPH_ACTORS = frozenset({"worker", "qa", "runner", "operator"})


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


def _assert_acyclic(edges: Mapping[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CorridorKitError("rule dependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for target in edges.get(node, set()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        visit(node)


def validate_graph_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate chain identity, authority receipts, and reference closure."""

    rule_records: dict[str, str] = {}
    ratified_rules: dict[str, str] = {}
    dependencies: dict[str, set[str]] = {}
    fact_records: dict[str, str] = {}
    fact_receipts: dict[str, str] = {}
    positions: dict[str, dict[str, Any]] = {}
    directions: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, int] = {}
    artifact_record_ids: set[str] = set()
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

        if record_type == "rule_proposal":
            rule_id = _text(body, "rule_id")
            _text(body, "statement")
            _text(body, "source_ref")
            _digest(body, "source_digest")
            if rule_id in rule_records:
                raise CorridorKitError(f"rule proposal already exists: {rule_id}")
            rule_records[rule_id] = expected_record
        elif record_type == "rule_revision":
            rule_id = _text(body, "rule_id")
            supersedes = _text(body, "supersedes_record_id")
            _text(body, "statement")
            _text(body, "source_ref")
            _digest(body, "source_digest")
            if rule_records.get(rule_id) != supersedes:
                raise CorridorKitError(f"rule revision does not supersede the current rule: {rule_id}")
            rule_records[rule_id] = expected_record
            ratified_rules.pop(rule_id, None)
        elif record_type == "rule_ratification":
            rule_id = _text(body, "rule_id")
            rule_record_id = _text(body, "rule_record_id")
            _text(body, "authority_ref")
            _digest(body, "authority_digest")
            _text(body, "receipt_ref")
            if rule_records.get(rule_id) != rule_record_id:
                raise CorridorKitError(f"ratification does not bind the current rule: {rule_id}")
            ratified_rules[rule_id] = expected_record
        elif record_type == "rule_dependency":
            source = _text(body, "from_rule_id")
            target = _text(body, "to_rule_id")
            relationship = _text(body, "relationship")
            if relationship not in {"requires", "overlaps", "conflicts", "derived_from"}:
                raise CorridorKitError(f"unknown rule dependency relationship: {relationship}")
            if source not in rule_records or target not in rule_records or source == target:
                raise CorridorKitError("rule dependency references an unknown or identical rule")
            if relationship == "requires":
                dependencies.setdefault(source, set()).add(target)
                _assert_acyclic(dependencies)
        elif record_type == "fact_proposal":
            fact_id = _text(body, "fact_id")
            _text(body, "statement")
            _text(body, "evidence_ref")
            _digest(body, "evidence_digest")
            _text(body, "position_ref")
            if fact_id in fact_records:
                raise CorridorKitError(f"fact proposal already exists: {fact_id}")
            fact_records[fact_id] = expected_record
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
            if set(rule_refs) != set(rule_records.values()):
                raise CorridorKitError("Position checkpoint must bind the whole current Rule closure")
            if not set(receipt_refs).issubset(set(fact_receipts.values())):
                raise CorridorKitError("Position checkpoint references an unknown Fact receipt")
            if not set(artifact_refs).issubset(artifact_record_ids):
                raise CorridorKitError("Position checkpoint references an unknown artifact revision")
            if position_id in positions:
                raise CorridorKitError(f"Position checkpoint already exists: {position_id}")
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
            if direction_id in directions:
                raise CorridorKitError(f"Direction proposal already exists: {direction_id}")
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
            artifact_record_ids.add(expected_record)

    return {
        "ok": True,
        "schema_version": GRAPH_REPLAY_SCHEMA,
        "record_count": len(records),
        "head_record_id": previous,
        "rule_count": len(rule_records),
        "ratified_rule_count": len(ratified_rules),
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
