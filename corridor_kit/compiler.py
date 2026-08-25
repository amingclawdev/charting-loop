"""Task-neutral compilation of public task requirements into typed Rule cells.

The compiler validates an agent-authored semantic IR and projects it into Graph
Kernel record bodies.  It does not read a verifier, infer task truth, choose a
Direction, or authorize work.  Natural-language interpretation remains an agent
responsibility; this module makes that interpretation explicit and replayable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core import CorridorKitError, sha256_bytes, sha256_json


TYPED_RULE_IR_SCHEMA_V1 = "charting-loop/typed-rule-ir/v1"
TYPED_RULE_IR_SCHEMA = "charting-loop/typed-rule-ir/v2"
TYPED_RULE_IR_SCHEMA_V3 = "charting-loop/typed-rule-ir/v3"
TYPED_RULE_IR_SCHEMA_V4 = "charting-loop/typed-rule-ir/v4"
TYPED_RULE_IR_SCHEMA_V5 = "charting-loop/typed-rule-ir/v5"
TYPED_RULE_COMPILATION_SCHEMA_V1 = "charting-loop/typed-rule-compilation/v1"
TYPED_RULE_COMPILATION_SCHEMA = "charting-loop/typed-rule-compilation/v2"
TYPED_RULE_COMPILATION_SCHEMA_V3 = "charting-loop/typed-rule-compilation/v3"
TYPED_RULE_COMPILATION_SCHEMA_V4 = "charting-loop/typed-rule-compilation/v4"
TYPED_RULE_COMPILATION_SCHEMA_V5 = "charting-loop/typed-rule-compilation/v5"
COMPILE_PROBE_MANIFEST_SCHEMA_V1 = "charting-loop/compile-probe-manifest/v1"
COMPILE_PROBE_MANIFEST_SCHEMA = "charting-loop/compile-probe-manifest/v2"
COMPILE_PROBE_MANIFEST_SCHEMA_V3 = "charting-loop/compile-probe-manifest/v3"
COMPILE_PROBE_MANIFEST_SCHEMA_V4 = "charting-loop/compile-probe-manifest/v4"
COMPILE_PROBE_MANIFEST_SCHEMA_V5 = "charting-loop/compile-probe-manifest/v5"
TASK_SOURCE_BUNDLE_SCHEMA = "charting-loop/task-source-bundle/v1"
TASK_SOURCE_BUNDLE_SCHEMA_V2 = "charting-loop/task-source-bundle/v2"
TASK_SOURCE_BUNDLE_SCHEMA_V3 = "charting-loop/authority-snapshot/v3"
TYPED_RULE_SEMANTICS_SCHEMA = "charting-loop/typed-rule-semantics/v2"
TYPED_RULE_SEMANTICS_SCHEMA_V3 = "charting-loop/typed-rule-semantics/v3"
TYPED_RULE_SEMANTICS_SCHEMA_V4 = "charting-loop/typed-rule-semantics/v4"
TYPED_RULE_SEMANTICS_SCHEMA_V5 = "charting-loop/typed-rule-semantics/v5"
SOURCE_PARTITION_MANIFEST_SCHEMA = "charting-loop/source-partition-manifest/v1"
SOURCE_PARTITION_PRODUCT_SCHEMA = "charting-loop/source-partition-product/v1"
SOURCE_DEPENDENCY_STUB_SCHEMA = "charting-loop/source-dependency-stub/v1"
RULE_LANE_BINDING_SCHEMA = "charting-loop/rule-lane-binding/v1"
WITNESS_LANE_PACKAGE_SCHEMA = "charting-loop/witness-lane-package/v1"
SOURCE_WITNESS_SCHEMA = "charting-loop/source-witness/v1"
TYPED_PREDICATE_SCHEMA = "charting-loop/typed-predicate/v1"
INTEGRATOR_MANIFEST_SCHEMA = "charting-loop/rule-integrator-manifest/v1"
RULE_LANE_PRODUCT_SCHEMA = "charting-loop/rule-lane-product/v2"
WITNESS_LANE_PRODUCT_SCHEMA = "charting-loop/witness-lane-product/v1"
PARALLEL_RULE_ASSEMBLY_SCHEMA = "charting-loop/parallel-rule-assembly/v1"
SOURCE_WITNESS_REPAIR_ENVELOPE_SCHEMA = (
    "charting-loop/source-witness-repair-envelope/v1"
)

RULE_KINDS = frozenset(
    {
        "invariant",
        "conditional",
        "temporal_conditional",
        "state_transition",
        "cardinality",
        "aggregate",
        "precedence",
        "optimization",
        "coupled",
        "prohibition",
    }
)
QUANTIFIER_MODES = frozenset(
    {"all", "any", "none", "exactly", "at_least", "at_most"}
)
PROJECTION_MODES = frozenset({"aggregate", "per_subject"})
RULE_RELATIONSHIPS = frozenset(
    {
        "applicable_when",
        "precondition_for",
        "precedes",
        "requires",
        "invalidates",
        "conflicts",
        "overrides",
        "coupled_with",
        "derived_from",
        "overlaps",
    }
)
TEMPORAL_OPERATORS = frozenset(
    {"ordered_before", "ordered_after", "duration", "state_transition"}
)
WITNESS_OBLIGATION_SCHEMA = "charting-loop/witness-obligation/v1"
SEMANTIC_EDGE_TEMPLATE_SCHEMA = "charting-loop/semantic-edge-template/v1"
_WITNESS_FAMILY_OPERATORS = {
    "namespace_disjointness": frozenset(
        {
            "collision_free",
            "disjoint",
            "namespace_disjoint",
            "not_equal",
            "unique",
        }
    ),
    "relational_closure": frozenset(
        {"acyclic", "cycle_free", "permutation", "transitive", "two_hop"}
    ),
    "numeric_boundary": frozenset(
        {
            "above",
            "at_least",
            "at_most",
            "below",
            "equal",
            "greater_than",
            "less_than",
            "numeric_compare",
        }
    ),
}
RUN_CLASSIFICATIONS = frozenset(
    {"fresh_task_pre_experiment", "same_task_regression"}
)
COMPILATION_STATUSES = frozenset(
    {"complete", "incomplete", "ambiguous", "unsupported"}
)
REQUIREMENT_LEVELS = frozenset({"required", "optional"})
SOURCE_ROLES = frozenset(
    {
        "instruction",
        "authoritative_specification",
        "task_world",
        "reference_material",
    }
)
AUTHORITY_PLANES = frozenset(
    {"normative_rule", "public_task_fact", "supporting_input"}
)
BYTE_STATUSES = frozenset(
    {"available", "unavailable", "malformed", "not_digest_bound"}
)
SEMANTIC_EXTRACTION_STATUSES = frozenset(
    {"complete", "incomplete", "unsupported", "not_required"}
)
SOURCE_RETRIEVAL_STATUSES = frozenset(
    {"available", "unavailable", "malformed", "not_digest_bound"}
)
SOURCE_BUNDLE_CLOSURE_STATUSES = frozenset({"complete", "unresolved"})
SOURCE_CLAUSE_MAPPING_STATUSES = frozenset(
    {"mapped", "unmapped", "ambiguous", "unsupported"}
)
IR_REVISION_KINDS = frozenset({"first_attempt", "semantic_repair"})
DOMAIN_KINDS = frozenset({"closed_enumeration", "open_including", "source_defined"})
DOMAIN_SOURCES = frozenset({"public_source", "task_world", "produced_output"})
APPLICABILITY_MODES = frozenset({"always", "conditional"})
SOURCE_SLICE_SEMANTIC_ROLES = frozenset(
    {
        "obligation",
        "applicability",
        "domain",
        "condition",
        "outcome",
        "quantifier",
        "witness_requirement",
        "evidence_requirement",
        "relationship",
        "prohibition",
    }
)
DEPENDENCY_PROVENANCE_KINDS = frozenset({"direct", "derived"})
DEPENDENCY_DERIVATION_KINDS = frozenset(
    {
        "applicability",
        "conjunction",
        "invalidating_change",
        "ordering",
        "other_declared",
        "transitive",
    }
)
CONDITION_KINDS = frozenset({"static", "temporal", "state_transition"})
RELATIONSHIP_ALIGNMENT_MODES = frozenset(
    {"keyed", "aggregate_to_members", "explicit_pairs", "all_to_all"}
)
ALIGNMENT_CELL_KEYS = frozenset(
    {"subject_axis", "subject_id", "condition_id", "predicate", "expected_outcome"}
)

SOURCE_WITNESS_KINDS = frozenset({"positive", "negative", "boundary"})
PREDICATE_VALUE_TYPES = frozenset(
    {"boolean", "bytes", "duration", "integer", "number", "state", "string", "timestamp"}
)

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_OPERATOR = re.compile(r"^[a-z][a-z0-9_.:-]*$")


def _text(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise CorridorKitError(f"typed Rule field {field} must be non-empty text")
    return item


def _identifier(value: Mapping[str, Any], field: str) -> str:
    item = _text(value, field)
    if not _IDENTIFIER.fullmatch(item):
        raise CorridorKitError(
            f"typed Rule field {field} must be a stable identifier"
        )
    return item


def _digest(value: Mapping[str, Any], field: str) -> str:
    item = _text(value, field)
    if not item.startswith("sha256:") or len(item) != 71:
        raise CorridorKitError(f"typed Rule field {field} must be a sha256 digest")
    try:
        int(item[7:], 16)
    except ValueError as exc:
        raise CorridorKitError(
            f"typed Rule field {field} must be a sha256 digest"
        ) from exc
    return item


def _text_list(
    value: Mapping[str, Any], field: str, *, nonempty: bool = False
) -> list[str]:
    items = value.get(field)
    if not isinstance(items, list) or any(
        not isinstance(item, str) or not item.strip() for item in items
    ):
        raise CorridorKitError(f"typed Rule field {field} must be a text list")
    if nonempty and not items:
        raise CorridorKitError(f"typed Rule field {field} must not be empty")
    if len(items) != len(set(items)):
        raise CorridorKitError(f"typed Rule field {field} contains duplicates")
    return list(items)


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise CorridorKitError(
            f"{label} has unknown or missing fields; missing={missing}, extra={extra}"
        )


def _utf8_boundaries(content: str) -> set[int]:
    """Return byte offsets that begin or end a UTF-8 code point."""

    boundaries = {0}
    offset = 0
    for character in content:
        offset += len(character.encode("utf-8"))
        boundaries.add(offset)
    return boundaries


def _validate_source_artifact(raw: Any, *, successor: bool) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CorridorKitError("task source bundle source must be an object")
    expected = {
        "source_id",
        "source_ref",
        "source_digest",
        "role",
        "retrieval_status",
    }
    if successor:
        expected.update({"content_encoding", "content_utf8"})
    _exact_keys(raw, expected, label="task source bundle source")
    source_id = _identifier(raw, "source_id")
    source_ref = _text(raw, "source_ref")
    role = _text(raw, "role")
    if role not in SOURCE_ROLES:
        raise CorridorKitError(f"unknown task source role: {role}")
    retrieval_status = _text(raw, "retrieval_status")
    if retrieval_status not in SOURCE_RETRIEVAL_STATUSES:
        raise CorridorKitError(
            f"unknown task source retrieval_status: {retrieval_status}"
        )
    source_digest = raw.get("source_digest")
    content_encoding: str | None = None
    content_utf8: str | None = None
    if retrieval_status == "available":
        source_digest = _digest(raw, "source_digest")
        if successor:
            content_encoding = _text(raw, "content_encoding")
            if content_encoding != "utf-8":
                raise CorridorKitError("successor task source encoding must be utf-8")
            content_utf8 = raw.get("content_utf8")
            if not isinstance(content_utf8, str):
                raise CorridorKitError(
                    "available successor task source must freeze content_utf8"
                )
            if sha256_bytes(content_utf8.encode("utf-8")) != source_digest:
                raise CorridorKitError(
                    f"task source digest does not match frozen bytes: {source_id}"
                )
    else:
        if source_digest is not None:
            raise CorridorKitError(
                "unavailable, malformed, or undigested task source must use null source_digest"
            )
        if successor and (
            raw.get("content_encoding") is not None
            or raw.get("content_utf8") is not None
        ):
            raise CorridorKitError(
                "unavailable successor task source must not claim frozen bytes"
            )
    normalized = {
        "source_id": source_id,
        "source_ref": source_ref,
        "source_digest": source_digest,
        "role": role,
        "retrieval_status": retrieval_status,
    }
    if successor:
        normalized.update(
            {
                "content_encoding": content_encoding,
                "content_utf8": content_utf8,
            }
        )
    return normalized


def validate_source_artifact(value: Any) -> dict[str, Any]:
    """Validate one successor frozen-source Graph record body."""

    return _validate_source_artifact(value, successor=True)


def _nullable_digest(value: Mapping[str, Any], field: str) -> str | None:
    item = value.get(field)
    if item is None:
        return None
    return _digest(value, field)


def validate_authority_source_artifact(value: Any) -> dict[str, Any]:
    """Validate one plane-typed AuthoritySnapshot source.

    Byte custody and semantic extraction are deliberately separate.  A readable
    blob can therefore remain semantically incomplete without being relabelled
    as missing, and an extraction artifact cannot replace the frozen bytes.
    """

    if not isinstance(value, dict):
        raise CorridorKitError("AuthoritySnapshot source must be an object")
    _exact_keys(
        value,
        {
            "source_id",
            "source_ref",
            "plane",
            "role",
            "byte_status",
            "byte_digest",
            "byte_size",
            "media_type",
            "content_encoding",
            "content_utf8",
            "semantic_extraction_status",
            "extractor",
            "extraction_artifact",
        },
        label="AuthoritySnapshot source",
    )
    source_id = _identifier(value, "source_id")
    source_ref = _text(value, "source_ref")
    plane = _text(value, "plane")
    if plane not in AUTHORITY_PLANES:
        raise CorridorKitError(f"unknown AuthoritySnapshot plane: {plane}")
    role = _text(value, "role")
    if role not in SOURCE_ROLES:
        raise CorridorKitError(f"unknown AuthoritySnapshot source role: {role}")
    if plane == "normative_rule" and role not in {
        "instruction",
        "authoritative_specification",
    }:
        raise CorridorKitError("normative Rule plane requires an authority-bearing role")
    if plane == "public_task_fact" and role != "task_world":
        raise CorridorKitError("public task Fact plane requires task_world role")
    if plane == "supporting_input" and role != "reference_material":
        raise CorridorKitError("supporting input plane requires reference_material role")

    byte_status = _text(value, "byte_status")
    if byte_status not in BYTE_STATUSES:
        raise CorridorKitError(f"unknown AuthoritySnapshot byte_status: {byte_status}")
    byte_digest = _nullable_digest(value, "byte_digest")
    byte_size = value.get("byte_size")
    media_type = value.get("media_type")
    content_encoding = value.get("content_encoding")
    content_utf8 = value.get("content_utf8")
    if byte_status == "available":
        if byte_digest is None:
            raise CorridorKitError("available AuthoritySnapshot source requires byte_digest")
        if (
            not isinstance(byte_size, int)
            or isinstance(byte_size, bool)
            or byte_size < 0
        ):
            raise CorridorKitError("available AuthoritySnapshot source requires byte_size")
        if not isinstance(media_type, str) or not media_type.strip():
            raise CorridorKitError("available AuthoritySnapshot source requires media_type")
        if content_encoding == "utf-8":
            if not isinstance(content_utf8, str):
                raise CorridorKitError("UTF-8 AuthoritySnapshot source requires content_utf8")
            payload = content_utf8.encode("utf-8")
            if len(payload) != byte_size or sha256_bytes(payload) != byte_digest:
                raise CorridorKitError(
                    f"AuthoritySnapshot byte identity does not match content: {source_id}"
                )
        elif content_encoding is not None or content_utf8 is not None:
            raise CorridorKitError(
                "non-UTF-8 AuthoritySnapshot source must not claim decoded content"
            )
    else:
        if any(
            item is not None
            for item in (byte_digest, byte_size, media_type, content_encoding, content_utf8)
        ):
            raise CorridorKitError(
                "unavailable AuthoritySnapshot source cannot claim byte identity"
            )

    extraction_status = _text(value, "semantic_extraction_status")
    if extraction_status not in SEMANTIC_EXTRACTION_STATUSES:
        raise CorridorKitError(
            f"unknown semantic_extraction_status: {extraction_status}"
        )
    extractor = value.get("extractor")
    extraction_artifact = value.get("extraction_artifact")
    if extraction_status == "complete":
        if byte_status != "available":
            raise CorridorKitError("complete extraction requires available frozen bytes")
        if not isinstance(extractor, dict):
            raise CorridorKitError("complete extraction requires extractor identity")
        _exact_keys(
            extractor,
            {"identity", "version", "digest"},
            label="AuthoritySnapshot extractor",
        )
        normalized_extractor = {
            "identity": _text(extractor, "identity"),
            "version": _text(extractor, "version"),
            "digest": _digest(extractor, "digest"),
        }
        if not isinstance(extraction_artifact, dict):
            raise CorridorKitError("complete extraction requires extraction artifact")
        _exact_keys(
            extraction_artifact,
            {
                "ref",
                "digest",
                "source_byte_digest",
                "content_encoding",
                "content_utf8",
                "byte_size",
            },
            label="AuthoritySnapshot extraction artifact",
        )
        artifact_encoding = extraction_artifact.get("content_encoding")
        artifact_content = extraction_artifact.get("content_utf8")
        artifact_size = extraction_artifact.get("byte_size")
        if artifact_encoding != "utf-8" or not isinstance(artifact_content, str):
            raise CorridorKitError(
                "complete extraction artifact must freeze UTF-8 semantic bytes"
            )
        artifact_bytes = artifact_content.encode("utf-8")
        if (
            not isinstance(artifact_size, int)
            or isinstance(artifact_size, bool)
            or artifact_size != len(artifact_bytes)
        ):
            raise CorridorKitError(
                "extraction artifact byte_size does not match frozen semantic bytes"
            )
        artifact_digest = _digest(extraction_artifact, "digest")
        if artifact_digest != sha256_bytes(artifact_bytes):
            raise CorridorKitError(
                "extraction artifact digest does not match frozen semantic bytes"
            )
        if _digest(extraction_artifact, "source_byte_digest") != byte_digest:
            raise CorridorKitError(
                "extraction artifact does not bind its frozen source bytes"
            )
        normalized_artifact = {
            "ref": _text(extraction_artifact, "ref"),
            "digest": artifact_digest,
            "source_byte_digest": byte_digest,
            "content_encoding": "utf-8",
            "content_utf8": artifact_content,
            "byte_size": artifact_size,
        }
    else:
        if extractor is not None or extraction_artifact is not None:
            raise CorridorKitError(
                "non-complete extraction cannot claim extractor or extraction artifact"
            )
        normalized_extractor = None
        normalized_artifact = None
        if plane == "normative_rule" and extraction_status == "not_required":
            raise CorridorKitError(
                "normative Rule source cannot waive semantic extraction"
            )
    return {
        "source_id": source_id,
        "source_ref": source_ref,
        "plane": plane,
        "role": role,
        "byte_status": byte_status,
        "byte_digest": byte_digest,
        "byte_size": byte_size,
        "media_type": media_type,
        "content_encoding": content_encoding,
        "content_utf8": content_utf8,
        "semantic_extraction_status": extraction_status,
        "extractor": normalized_extractor,
        "extraction_artifact": normalized_artifact,
    }


def authority_snapshot_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact identity manifest covered by an AuthoritySnapshot digest."""

    return {
        "snapshot_id": value["snapshot_id"],
        "snapshot_revision": value["snapshot_revision"],
        "parent_snapshot_digest": value["parent_snapshot_digest"],
        "sources": [
            {
                key: source[key]
                for key in (
                    "source_id",
                    "source_ref",
                    "plane",
                    "role",
                    "byte_status",
                    "byte_digest",
                    "byte_size",
                    "media_type",
                    "semantic_extraction_status",
                )
            }
            | {
                "extractor_digest": (
                    source["extractor"]["digest"] if source["extractor"] else None
                ),
                "extraction_artifact_digest": (
                    source["extraction_artifact"]["digest"]
                    if source["extraction_artifact"]
                    else None
                ),
            }
            for source in value["sources"]
        ],
    }


def _operators(
    value: Mapping[str, Any], field: str, *, nonempty: bool = True
) -> list[str]:
    operators = _text_list(value, field, nonempty=nonempty)
    invalid = [item for item in operators if not _OPERATOR.fullmatch(item)]
    if invalid:
        raise CorridorKitError(
            f"typed Rule field {field} has invalid operator identifiers: {invalid}"
        )
    return operators


def validate_source_bundle(value: Any) -> dict[str, Any]:
    """Validate a closed, digest-bound inventory of public task sources."""

    if not isinstance(value, dict):
        raise CorridorKitError("task source bundle must be an object")
    bundle_schema = value.get("schema_version")
    is_authority_snapshot = bundle_schema == TASK_SOURCE_BUNDLE_SCHEMA_V3
    _exact_keys(
        value,
        (
            {
                "schema_version",
                "snapshot_id",
                "snapshot_revision",
                "parent_snapshot_digest",
                "manifest_digest",
                "freeze_receipt",
                "closure_status",
                "sources",
            }
            if is_authority_snapshot
            else {"schema_version", "closure_status", "sources"}
        ),
        label="task source bundle",
    )
    successor = bundle_schema == TASK_SOURCE_BUNDLE_SCHEMA_V2
    if (
        not successor
        and not is_authority_snapshot
        and bundle_schema != TASK_SOURCE_BUNDLE_SCHEMA
    ):
        raise CorridorKitError("task source bundle has the wrong schema")
    closure_status = _text(value, "closure_status")
    if closure_status not in SOURCE_BUNDLE_CLOSURE_STATUSES:
        raise CorridorKitError("task source bundle has an unknown closure_status")
    raw_sources = value.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise CorridorKitError("task source bundle sources must be a non-empty list")
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    source_refs: set[str] = set()
    for raw in raw_sources:
        source = (
            validate_authority_source_artifact(raw)
            if is_authority_snapshot
            else _validate_source_artifact(raw, successor=successor)
        )
        source_id = source["source_id"]
        source_ref = source["source_ref"]
        if source_id in source_ids or source_ref in source_refs:
            raise CorridorKitError("task source bundle contains a duplicate source identity")
        source_ids.add(source_id)
        source_refs.add(source_ref)
        sources.append(source)
    if not any(source["role"] == "instruction" for source in sources):
        raise CorridorKitError("task source bundle must include the public instruction")
    derived_closure = (
        "complete"
        if all(
            source.get("retrieval_status", source.get("byte_status")) == "available"
            and (
                source.get("plane") != "normative_rule"
                or source.get("semantic_extraction_status") == "complete"
            )
            for source in sources
        )
        else "unresolved"
    )
    if closure_status != derived_closure:
        raise CorridorKitError(
            "task source bundle closure_status does not match retrieval statuses"
        )
    normalized = {
        "schema_version": bundle_schema,
        "closure_status": closure_status,
        "sources": sources,
    }
    if is_authority_snapshot:
        snapshot_id = _identifier(value, "snapshot_id")
        revision = value.get("snapshot_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise CorridorKitError("AuthoritySnapshot revision must be a positive integer")
        parent_digest = value.get("parent_snapshot_digest")
        if revision == 1:
            if parent_digest is not None:
                raise CorridorKitError("first AuthoritySnapshot cannot claim a parent")
        else:
            parent_digest = _digest(value, "parent_snapshot_digest")
        receipt = value.get("freeze_receipt")
        if not isinstance(receipt, dict):
            raise CorridorKitError("AuthoritySnapshot requires a runner freeze receipt")
        _exact_keys(receipt, {"actor_role", "ref", "digest"}, label="freeze receipt")
        if receipt.get("actor_role") != "runner":
            raise CorridorKitError("AuthoritySnapshot must be frozen by the runner")
        normalized.update(
            {
                "snapshot_id": snapshot_id,
                "snapshot_revision": revision,
                "parent_snapshot_digest": parent_digest,
                "freeze_receipt": {
                    "actor_role": "runner",
                    "ref": _text(receipt, "ref"),
                    "digest": _digest(receipt, "digest"),
                },
            }
        )
        manifest_digest = _digest(value, "manifest_digest")
        expected_manifest_digest = sha256_json(authority_snapshot_manifest(normalized))
        if manifest_digest != expected_manifest_digest:
            raise CorridorKitError(
                "AuthoritySnapshot manifest_digest does not match exact source identities"
            )
        normalized["manifest_digest"] = manifest_digest
        expected_receipt_digest = sha256_json(
            {
                "actor_role": "runner",
                "ref": normalized["freeze_receipt"]["ref"],
                "manifest_digest": manifest_digest,
            }
        )
        if normalized["freeze_receipt"]["digest"] != expected_receipt_digest:
            raise CorridorKitError(
                "AuthoritySnapshot freeze receipt does not bind its manifest"
            )
    return normalized


def validate_ir_revision(value: Any) -> dict[str, Any]:
    """Validate immutable first-attempt or QA-repair lineage metadata."""

    if not isinstance(value, dict):
        raise CorridorKitError("typed Rule IR revision must be an object")
    _exact_keys(
        value,
        {"revision_id", "revision_kind", "parent_ir_digest", "qa_witness_refs"},
        label="typed Rule IR revision",
    )
    revision_id = _identifier(value, "revision_id")
    revision_kind = _text(value, "revision_kind")
    if revision_kind not in IR_REVISION_KINDS:
        raise CorridorKitError(f"unknown typed Rule IR revision_kind: {revision_kind}")
    parent_ir_digest = value.get("parent_ir_digest")
    qa_witness_refs = _text_list(value, "qa_witness_refs")
    if revision_kind == "first_attempt":
        if parent_ir_digest is not None or qa_witness_refs:
            raise CorridorKitError(
                "first-attempt typed Rule IR cannot claim a parent or QA repair witness"
            )
    else:
        parent_ir_digest = _digest(value, "parent_ir_digest")
        if not qa_witness_refs:
            raise CorridorKitError(
                "semantic-repair typed Rule IR must bind at least one QA witness"
            )
    return {
        "revision_id": revision_id,
        "revision_kind": revision_kind,
        "parent_ir_digest": parent_ir_digest,
        "qa_witness_refs": qa_witness_refs,
    }


def validate_source_clause_inventory(value: Any) -> list[dict[str, Any]]:
    """Validate the independently enumerable normative-clause inventory."""

    if not isinstance(value, list) or not value:
        raise CorridorKitError("source clause inventory must be a non-empty list")
    clauses: list[dict[str, Any]] = []
    clause_ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CorridorKitError("source clause inventory entry must be an object")
        _exact_keys(
            raw,
            {
                "clause_id",
                "source_id",
                "clause_text",
                "clause_digest",
                "requirement_level",
                "mapping_status",
                "rule_ids",
                "issue",
            },
            label="source clause inventory entry",
        )
        clause_id = _identifier(raw, "clause_id")
        if clause_id in clause_ids:
            raise CorridorKitError(f"source clause ID is duplicated: {clause_id}")
        clause_ids.add(clause_id)
        clause_text = _text(raw, "clause_text")
        clause_digest = _digest(raw, "clause_digest")
        if sha256_bytes(clause_text.encode("utf-8")) != clause_digest:
            raise CorridorKitError(
                f"source clause digest does not match clause_text: {clause_id}"
            )
        requirement_level = _text(raw, "requirement_level")
        if requirement_level not in REQUIREMENT_LEVELS:
            raise CorridorKitError(
                f"unknown source clause requirement_level: {requirement_level}"
            )
        mapping_status = _text(raw, "mapping_status")
        if mapping_status not in SOURCE_CLAUSE_MAPPING_STATUSES:
            raise CorridorKitError(
                f"unknown source clause mapping_status: {mapping_status}"
            )
        rule_ids = _text_list(raw, "rule_ids")
        issue = raw.get("issue")
        if not isinstance(issue, str):
            raise CorridorKitError("source clause issue must be text, including empty text")
        if mapping_status == "mapped":
            if not rule_ids or issue:
                raise CorridorKitError(
                    "mapped source clause requires Rule IDs and an empty issue"
                )
        elif rule_ids or not issue.strip():
            raise CorridorKitError(
                "non-mapped source clause requires no Rule IDs and a non-empty issue"
            )
        clauses.append(
            {
                "clause_id": clause_id,
                "source_id": _identifier(raw, "source_id"),
                "clause_text": clause_text,
                "clause_digest": clause_digest,
                "requirement_level": requirement_level,
                "mapping_status": mapping_status,
                "rule_ids": rule_ids,
                "issue": issue,
            }
        )
    return clauses


def validate_source_clause_inventory_v3(
    value: Any, *, source_bundle: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Validate byte-addressed clauses against exact frozen source bytes."""

    if not isinstance(value, list) or not value:
        raise CorridorKitError("source clause inventory must be a non-empty list")
    source_by_id = {
        source["source_id"]: source for source in source_bundle["sources"]
    }
    clauses: list[dict[str, Any]] = []
    clause_ids: set[str] = set()
    clause_order_keys: set[str] = set()
    slice_ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CorridorKitError("source clause inventory entry must be an object")
        _exact_keys(
            raw,
            {
                "clause_id",
                "clause_order_key",
                "source_slices",
                "clause_text",
                "clause_digest",
                "requirement_level",
                "mapping_status",
                "rule_ids",
                "required_semantic_roles",
                "issue",
            },
            label="successor source clause inventory entry",
        )
        clause_id = _identifier(raw, "clause_id")
        if clause_id in clause_ids:
            raise CorridorKitError(f"source clause ID is duplicated: {clause_id}")
        clause_ids.add(clause_id)
        clause_order_key = _identifier(raw, "clause_order_key")
        if clause_order_key in clause_order_keys:
            raise CorridorKitError(
                f"source clause order key is duplicated: {clause_order_key}"
            )
        clause_order_keys.add(clause_order_key)
        raw_slices = raw.get("source_slices")
        if not isinstance(raw_slices, list) or not raw_slices:
            raise CorridorKitError(
                "successor source clause must contain ordered source_slices"
            )
        slices: list[dict[str, Any]] = []
        reconstructed: list[str] = []
        for raw_slice in raw_slices:
            if not isinstance(raw_slice, dict):
                raise CorridorKitError("source slice must be an object")
            is_authority_snapshot = (
                source_bundle.get("schema_version") == TASK_SOURCE_BUNDLE_SCHEMA_V3
            )
            _exact_keys(
                raw_slice,
                {
                    "slice_id",
                    "source_id",
                    "byte_start",
                    "byte_end",
                    "slice_digest",
                    *( ["representation"] if is_authority_snapshot else [] ),
                },
                label="source slice",
            )
            slice_id = _identifier(raw_slice, "slice_id")
            if slice_id in slice_ids:
                raise CorridorKitError(f"source slice ID is duplicated: {slice_id}")
            slice_ids.add(slice_id)
            source_id = _identifier(raw_slice, "source_id")
            source = source_by_id.get(source_id)
            if source is None:
                raise CorridorKitError(
                    f"source slice references unknown source: {slice_id}"
                )
            if source.get("retrieval_status", source.get("byte_status")) != "available":
                raise CorridorKitError(
                    f"source slice references unresolved source: {slice_id}"
                )
            byte_start = raw_slice.get("byte_start")
            byte_end = raw_slice.get("byte_end")
            if (
                not isinstance(byte_start, int)
                or isinstance(byte_start, bool)
                or not isinstance(byte_end, int)
                or isinstance(byte_end, bool)
                or byte_start < 0
                or byte_end <= byte_start
            ):
                raise CorridorKitError(
                    f"source slice requires a non-empty half-open byte range: {slice_id}"
                )
            representation = raw_slice.get("representation", "source_bytes")
            if representation not in {"source_bytes", "extraction_artifact"}:
                raise CorridorKitError(
                    f"source slice has an unknown representation: {slice_id}"
                )
            if representation == "source_bytes":
                content = source.get("content_utf8")
                if not isinstance(content, str):
                    raise CorridorKitError(
                        f"source slice requires decoded source bytes: {slice_id}"
                    )
            else:
                extraction_artifact = source.get("extraction_artifact")
                if not isinstance(extraction_artifact, dict):
                    raise CorridorKitError(
                        f"source slice requires a frozen extraction artifact: {slice_id}"
                    )
                content = extraction_artifact.get("content_utf8")
                if not isinstance(content, str):
                    raise CorridorKitError(
                        f"source slice extraction artifact lacks semantic bytes: {slice_id}"
                    )
            content_bytes = content.encode("utf-8")
            if byte_end > len(content_bytes):
                raise CorridorKitError(f"source slice is out of bounds: {slice_id}")
            boundaries = _utf8_boundaries(content)
            if byte_start not in boundaries or byte_end not in boundaries:
                raise CorridorKitError(
                    f"source slice is not aligned to UTF-8 code points: {slice_id}"
                )
            sliced_bytes = content_bytes[byte_start:byte_end]
            slice_digest = _digest(raw_slice, "slice_digest")
            if sha256_bytes(sliced_bytes) != slice_digest:
                raise CorridorKitError(
                    f"source slice digest does not match frozen bytes: {slice_id}"
                )
            reconstructed.append(sliced_bytes.decode("utf-8"))
            slices.append(
                {
                    "slice_id": slice_id,
                    "source_id": source_id,
                    **(
                        {"representation": representation}
                        if is_authority_snapshot
                        else {}
                    ),
                    "byte_start": byte_start,
                    "byte_end": byte_end,
                    "slice_digest": slice_digest,
                }
            )
        clause_text = raw.get("clause_text")
        if not isinstance(clause_text, str) or not clause_text:
            raise CorridorKitError("successor source clause text must be non-empty")
        if clause_text != "".join(reconstructed):
            raise CorridorKitError(
                f"source clause text does not reconstruct from ordered slices: {clause_id}"
            )
        clause_digest = _digest(raw, "clause_digest")
        if sha256_bytes(clause_text.encode("utf-8")) != clause_digest:
            raise CorridorKitError(
                f"source clause digest does not match reconstructed bytes: {clause_id}"
            )
        requirement_level = _text(raw, "requirement_level")
        if requirement_level not in REQUIREMENT_LEVELS:
            raise CorridorKitError(
                f"unknown source clause requirement_level: {requirement_level}"
            )
        mapping_status = _text(raw, "mapping_status")
        if mapping_status not in SOURCE_CLAUSE_MAPPING_STATUSES:
            raise CorridorKitError(
                f"unknown source clause mapping_status: {mapping_status}"
            )
        rule_ids = _text_list(raw, "rule_ids")
        required_roles = _text_list(
            raw, "required_semantic_roles", nonempty=mapping_status == "mapped"
        )
        invalid_roles = sorted(set(required_roles) - SOURCE_SLICE_SEMANTIC_ROLES)
        if invalid_roles:
            raise CorridorKitError(
                f"unknown source slice semantic roles: {invalid_roles}"
            )
        issue = raw.get("issue")
        if not isinstance(issue, str):
            raise CorridorKitError("source clause issue must be text, including empty text")
        if mapping_status == "mapped":
            if not rule_ids or issue:
                raise CorridorKitError(
                    "mapped source clause requires Rule IDs and an empty issue"
                )
        elif rule_ids or required_roles or not issue.strip():
            raise CorridorKitError(
                "non-mapped source clause requires no Rule IDs or semantic roles and a non-empty issue"
            )
        clauses.append(
            {
                "clause_id": clause_id,
                "clause_order_key": clause_order_key,
                "source_slices": slices,
                "clause_text": clause_text,
                "clause_digest": clause_digest,
                "requirement_level": requirement_level,
                "mapping_status": mapping_status,
                "rule_ids": rule_ids,
                "required_semantic_roles": required_roles,
                "issue": issue,
            }
        )
    return sorted(clauses, key=lambda clause: clause["clause_order_key"])


def validate_rule_source_slices(value: Any) -> list[dict[str, str]]:
    """Validate ordered Rule-to-slice semantic bindings."""

    if not isinstance(value, list) or not value:
        raise CorridorKitError("successor typed Rule source_slices must be non-empty")
    bindings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CorridorKitError("typed Rule source slice binding must be an object")
        _exact_keys(
            raw,
            {"slice_id", "semantic_role"},
            label="typed Rule source slice binding",
        )
        slice_id = _identifier(raw, "slice_id")
        semantic_role = _text(raw, "semantic_role")
        if semantic_role not in SOURCE_SLICE_SEMANTIC_ROLES:
            raise CorridorKitError(
                f"unknown source slice semantic role: {semantic_role}"
            )
        identity = (slice_id, semantic_role)
        if identity in seen:
            raise CorridorKitError(
                f"typed Rule source slice binding is duplicated: {slice_id}:{semantic_role}"
            )
        seen.add(identity)
        bindings.append({"slice_id": slice_id, "semantic_role": semantic_role})
    if "obligation" not in {item["semantic_role"] for item in bindings}:
        raise CorridorKitError(
            "successor typed Rule must bind at least one obligation source slice"
        )
    return bindings


def rule_source_provenance_identity(
    *,
    rule_id: str,
    statement: str,
    source_clause_ids: list[str],
    source_slices: list[dict[str, str]],
    source_bundle: Mapping[str, Any],
    source_clauses: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve Rule bindings to the exact frozen source-byte identities they name."""

    source_by_id = {
        source["source_id"]: source for source in source_bundle["sources"]
    }
    slice_resolution: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for clause in source_clauses:
        for source_slice in clause["source_slices"]:
            slice_resolution[source_slice["slice_id"]] = (clause, source_slice)
    resolved_bindings: list[dict[str, Any]] = []
    for binding in source_slices:
        resolution = slice_resolution.get(binding["slice_id"])
        if resolution is None:
            raise CorridorKitError(
                f"typed Rule references unknown source slice: {binding['slice_id']}"
            )
        clause, source_slice = resolution
        source = source_by_id[source_slice["source_id"]]
        resolved_bindings.append(
            {
                "slice_id": source_slice["slice_id"],
                "semantic_role": binding["semantic_role"],
                "clause_id": clause["clause_id"],
                "clause_order_key": clause["clause_order_key"],
                "clause_digest": clause["clause_digest"],
                "source_id": source_slice["source_id"],
                "source_digest": source.get("source_digest", source.get("byte_digest")),
                **(
                    {"representation": source_slice["representation"]}
                    if "representation" in source_slice
                    else {}
                ),
                "byte_start": source_slice["byte_start"],
                "byte_end": source_slice["byte_end"],
                "slice_digest": source_slice["slice_digest"],
            }
        )
    return {
        "rule_id": rule_id,
        "statement": statement,
        "source_clause_ids": source_clause_ids,
        "source_slices": resolved_bindings,
    }


def _alignment_selector(value: Any, *, label: str) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise CorridorKitError(f"{label} must be an object")
    _exact_keys(value, {"subject_id", "condition_id"}, label=label)
    normalized: dict[str, str | None] = {}
    for field in ("subject_id", "condition_id"):
        item = value.get(field)
        if item is not None and (not isinstance(item, str) or not item.strip()):
            raise CorridorKitError(f"{label} {field} must be text or null")
        normalized[field] = item
    if all(item is None for item in normalized.values()):
        raise CorridorKitError(f"{label} must constrain at least one cell field")
    return normalized


def _cardinality_bound(value: Any, *, label: str) -> dict[str, int | None]:
    if not isinstance(value, dict):
        raise CorridorKitError(f"{label} must be an object")
    _exact_keys(value, {"minimum", "maximum"}, label=label)
    minimum = value.get("minimum")
    maximum = value.get("maximum")
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or minimum < 0
        or (
            maximum is not None
            and (
                not isinstance(maximum, int)
                or isinstance(maximum, bool)
                or maximum < minimum
            )
        )
    ):
        raise CorridorKitError(f"{label} has invalid minimum/maximum")
    return {"minimum": minimum, "maximum": maximum}


def validate_relationship_alignment(value: Any) -> dict[str, Any]:
    """Validate explicit checklist-cell alignment for one Rule relationship."""

    if not isinstance(value, dict):
        raise CorridorKitError("relationship alignment must be an object")
    _exact_keys(
        value,
        {
            "mode",
            "source_endpoint",
            "target_endpoint",
            "key_pairs",
            "source_scope",
            "target_scope",
            "source_cardinality",
            "target_cardinality",
            "membership_ref",
            "explicit_pairs",
            "rationale",
        },
        label="relationship alignment",
    )
    mode = _text(value, "mode")
    if mode not in RELATIONSHIP_ALIGNMENT_MODES:
        raise CorridorKitError(f"unknown relationship alignment mode: {mode}")
    source_endpoint = _text(value, "source_endpoint")
    target_endpoint = _text(value, "target_endpoint")
    raw_keys = value.get("key_pairs")
    if not isinstance(raw_keys, list):
        raise CorridorKitError("relationship alignment key_pairs must be a list")
    key_pairs: list[dict[str, str]] = []
    for raw in raw_keys:
        if not isinstance(raw, dict):
            raise CorridorKitError("relationship alignment key pair must be an object")
        _exact_keys(raw, {"source_key", "target_key"}, label="alignment key pair")
        source_key = _text(raw, "source_key")
        target_key = _text(raw, "target_key")
        if source_key not in ALIGNMENT_CELL_KEYS or target_key not in ALIGNMENT_CELL_KEYS:
            raise CorridorKitError("relationship alignment uses an unknown coverage-cell key")
        key_pairs.append({"source_key": source_key, "target_key": target_key})
    if len({(item["source_key"], item["target_key"]) for item in key_pairs}) != len(
        key_pairs
    ):
        raise CorridorKitError("relationship alignment key_pairs contain duplicates")

    def selector_list(field: str) -> list[dict[str, str | None]]:
        raw_items = value.get(field)
        if not isinstance(raw_items, list):
            raise CorridorKitError(f"relationship alignment {field} must be a list")
        return [
            _alignment_selector(item, label=f"relationship alignment {field} selector")
            for item in raw_items
        ]

    source_scope = selector_list("source_scope")
    target_scope = selector_list("target_scope")
    raw_pairs = value.get("explicit_pairs")
    if not isinstance(raw_pairs, list):
        raise CorridorKitError("relationship alignment explicit_pairs must be a list")
    explicit_pairs: list[dict[str, Any]] = []
    for raw in raw_pairs:
        if not isinstance(raw, dict):
            raise CorridorKitError("relationship alignment explicit pair must be an object")
        _exact_keys(raw, {"source", "target"}, label="alignment explicit pair")
        explicit_pairs.append(
            {
                "source": _alignment_selector(raw["source"], label="explicit source"),
                "target": _alignment_selector(raw["target"], label="explicit target"),
            }
        )
    membership_ref = value.get("membership_ref")
    rationale = value.get("rationale")
    if membership_ref is not None and (
        not isinstance(membership_ref, str) or not membership_ref.strip()
    ):
        raise CorridorKitError("relationship alignment membership_ref must be text or null")
    if rationale is not None and (not isinstance(rationale, str) or not rationale.strip()):
        raise CorridorKitError("relationship alignment rationale must be text or null")
    if mode == "keyed":
        if not key_pairs or explicit_pairs or membership_ref is not None:
            raise CorridorKitError("keyed alignment requires only one or more key_pairs")
    elif mode == "aggregate_to_members":
        if key_pairs or not explicit_pairs or membership_ref is None:
            raise CorridorKitError(
                "aggregate_to_members alignment requires membership_ref and explicit pairs"
            )
    elif mode == "explicit_pairs":
        if key_pairs or not explicit_pairs or membership_ref is not None:
            raise CorridorKitError("explicit_pairs alignment requires exact pairs only")
    elif key_pairs or explicit_pairs or membership_ref is not None or rationale is None:
        raise CorridorKitError(
            "all_to_all alignment requires an explicit rationale and no implicit mapping"
        )
    return {
        "mode": mode,
        "source_endpoint": source_endpoint,
        "target_endpoint": target_endpoint,
        "key_pairs": key_pairs,
        "source_scope": source_scope,
        "target_scope": target_scope,
        "source_cardinality": _cardinality_bound(
            value.get("source_cardinality"), label="source cardinality"
        ),
        "target_cardinality": _cardinality_bound(
            value.get("target_cardinality"), label="target cardinality"
        ),
        "membership_ref": membership_ref,
        "explicit_pairs": explicit_pairs,
        "rationale": rationale,
    }


def _typed_variable(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorridorKitError(f"{label} must be an object")
    _exact_keys(
        value,
        {"variable_id", "value_type", "source_slice_ids"},
        label=label,
    )
    variable_id = _identifier(value, "variable_id")
    value_type = _text(value, "value_type")
    if value_type not in PREDICATE_VALUE_TYPES:
        raise CorridorKitError(f"{label} has an unknown value_type: {value_type}")
    return {
        "variable_id": variable_id,
        "value_type": value_type,
        "source_slice_ids": _text_list(value, "source_slice_ids", nonempty=True),
    }


def validate_typed_predicate(value: Any, *, condition_kind: str) -> dict[str, Any]:
    """Validate one source-indexed executable predicate declaration.

    The compiler validates declared variables and temporal identity.  It does not
    infer truth from prose or an evaluator.
    """

    if not isinstance(value, dict):
        raise CorridorKitError("typed predicate must be an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "predicate_id",
            "operator",
            "inputs",
            "outputs",
            "producer_refs",
            "precondition_rule_ids",
            "dependency_refs",
            "semantic_fields",
        },
        label="typed predicate",
    )
    if value.get("schema_version") != TYPED_PREDICATE_SCHEMA:
        raise CorridorKitError("typed predicate has the wrong schema")
    operator = _text(value, "operator")
    if not _OPERATOR.fullmatch(operator):
        raise CorridorKitError("typed predicate operator must be a stable operator")
    raw_inputs = value.get("inputs")
    raw_outputs = value.get("outputs")
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise CorridorKitError("typed predicate inputs must be non-empty")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise CorridorKitError("typed predicate outputs must be non-empty")
    inputs = [_typed_variable(item, label="typed predicate input") for item in raw_inputs]
    outputs = [_typed_variable(item, label="typed predicate output") for item in raw_outputs]
    variable_ids = [item["variable_id"] for item in [*inputs, *outputs]]
    if len(variable_ids) != len(set(variable_ids)):
        raise CorridorKitError("typed predicate variable IDs must be unique")
    semantic_fields = value.get("semantic_fields")
    if not isinstance(semantic_fields, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(item, str)
        or not item.strip()
        for key, item in semantic_fields.items()
    ):
        raise CorridorKitError("typed predicate semantic_fields must be a text map")
    if condition_kind in {"temporal", "state_transition"}:
        required = {
            "event_time_variable",
            "transition_time_variable",
            "before_outcome",
            "after_outcome",
            "chain_outcome",
        }
        missing = sorted(required - set(semantic_fields))
        if missing:
            raise CorridorKitError(
                f"temporal typed predicate lacks semantic fields: {missing}"
            )
        input_ids = {item["variable_id"] for item in inputs}
        for field in ("event_time_variable", "transition_time_variable"):
            if semantic_fields[field] not in input_ids:
                raise CorridorKitError(
                    f"temporal typed predicate {field} must name an input variable"
                )
        if semantic_fields["before_outcome"] == semantic_fields["after_outcome"]:
            raise CorridorKitError(
                "temporal typed predicate cannot collapse before and after outcomes"
            )
    return {
        "schema_version": TYPED_PREDICATE_SCHEMA,
        "predicate_id": _identifier(value, "predicate_id"),
        "operator": operator,
        "inputs": inputs,
        "outputs": outputs,
        "producer_refs": _text_list(value, "producer_refs", nonempty=True),
        "precondition_rule_ids": _text_list(value, "precondition_rule_ids"),
        "dependency_refs": _text_list(value, "dependency_refs"),
        "semantic_fields": dict(sorted(semantic_fields.items())),
    }


def _validate_source_partition_manifest(
    value: Any, *, source_clause_ids: set[str]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorridorKitError("source partition manifest must be an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "partition_id",
            "authority_snapshot_digest",
            "lanes",
            "dependency_stubs",
            "global_lane_id",
            "unresolved_clause_ids",
        },
        label="source partition manifest",
    )
    if value.get("schema_version") != SOURCE_PARTITION_MANIFEST_SCHEMA:
        raise CorridorKitError("source partition manifest has the wrong schema")
    raw_lanes = value.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raise CorridorKitError("source partition manifest lanes must be non-empty")
    lanes: list[dict[str, Any]] = []
    lane_ids: set[str] = set()
    owners: dict[str, str] = {}
    for raw in raw_lanes:
        if not isinstance(raw, dict):
            raise CorridorKitError("source partition lane must be an object")
        _exact_keys(
            raw,
            {
                "lane_id",
                "owner_clause_ids",
                "boundary_clause_ids",
                "lane_kind",
            },
            label="source partition lane",
        )
        lane_id = _identifier(raw, "lane_id")
        if lane_id in lane_ids:
            raise CorridorKitError(f"source partition lane is duplicated: {lane_id}")
        lane_ids.add(lane_id)
        owner_clause_ids = _text_list(raw, "owner_clause_ids")
        boundary_clause_ids = _text_list(raw, "boundary_clause_ids")
        unknown = sorted(
            (set(owner_clause_ids) | set(boundary_clause_ids)) - source_clause_ids
        )
        if unknown:
            raise CorridorKitError(
                f"source partition lane references unknown clauses: {unknown}"
            )
        for clause_id in owner_clause_ids:
            if clause_id in owners:
                raise CorridorKitError(
                    f"source clause has duplicate lane ownership: {clause_id}"
                )
            owners[clause_id] = lane_id
        lanes.append(
            {
                "lane_id": lane_id,
                "owner_clause_ids": owner_clause_ids,
                "boundary_clause_ids": boundary_clause_ids,
                "lane_kind": _text(raw, "lane_kind"),
            }
        )
    unresolved = _text_list(value, "unresolved_clause_ids")
    if set(unresolved) - source_clause_ids:
        raise CorridorKitError("partition unresolved clauses reference unknown clauses")
    if set(owners).intersection(unresolved):
        raise CorridorKitError("owned source clause cannot also be unresolved")
    missing = sorted(source_clause_ids - set(owners) - set(unresolved))
    if missing:
        raise CorridorKitError(f"source partition has coverage holes: {missing}")
    global_lane_id = _identifier(value, "global_lane_id")
    if global_lane_id not in lane_ids:
        raise CorridorKitError("source partition global lane is missing")
    raw_stubs = value.get("dependency_stubs")
    if not isinstance(raw_stubs, list):
        raise CorridorKitError("source partition dependency_stubs must be a list")
    dependency_stubs: list[dict[str, Any]] = []
    seen_stub_ids: set[str] = set()
    seen_stub_identities: set[tuple[Any, ...]] = set()
    for raw in raw_stubs:
        if not isinstance(raw, dict):
            raise CorridorKitError("source dependency stub must be an object")
        _exact_keys(
            raw,
            {
                "schema_version",
                "dependency_ref",
                "from_lane_id",
                "to_lane_id",
                "from_clause_ids",
                "to_clause_ids",
                "relationship",
            },
            label="source dependency stub",
        )
        if raw.get("schema_version") != SOURCE_DEPENDENCY_STUB_SCHEMA:
            raise CorridorKitError("source dependency stub has the wrong schema")
        dependency_ref = _identifier(raw, "dependency_ref")
        if dependency_ref in seen_stub_ids:
            raise CorridorKitError(
                f"source dependency stub is duplicated: {dependency_ref}"
            )
        seen_stub_ids.add(dependency_ref)
        from_lane_id = _identifier(raw, "from_lane_id")
        to_lane_id = _identifier(raw, "to_lane_id")
        if (
            from_lane_id not in lane_ids
            or to_lane_id not in lane_ids
            or from_lane_id == to_lane_id
        ):
            raise CorridorKitError(
                "source dependency stub must join two known distinct lanes"
            )
        from_clause_ids = _text_list(raw, "from_clause_ids", nonempty=True)
        to_clause_ids = _text_list(raw, "to_clause_ids", nonempty=True)
        if set(from_clause_ids) - source_clause_ids or set(to_clause_ids) - source_clause_ids:
            raise CorridorKitError(
                "source dependency stub references unknown source clauses"
            )
        from_owned = {
            clause_id for clause_id, lane_id in owners.items() if lane_id == from_lane_id
        }
        to_owned = {
            clause_id for clause_id, lane_id in owners.items() if lane_id == to_lane_id
        }
        if not set(from_clause_ids).issubset(from_owned) or not set(
            to_clause_ids
        ).issubset(to_owned):
            raise CorridorKitError(
                "source dependency stub clauses must be owned by their endpoint lanes"
            )
        relationship = _text(raw, "relationship")
        if relationship not in RULE_RELATIONSHIPS:
            raise CorridorKitError(
                f"source dependency stub has an unknown relationship: {relationship}"
            )
        identity = (
            from_lane_id,
            to_lane_id,
            tuple(sorted(from_clause_ids)),
            tuple(sorted(to_clause_ids)),
            relationship,
        )
        if identity in seen_stub_identities:
            raise CorridorKitError("source dependency stub identity is duplicated")
        seen_stub_identities.add(identity)
        dependency_stubs.append(
            {
                "schema_version": SOURCE_DEPENDENCY_STUB_SCHEMA,
                "dependency_ref": dependency_ref,
                "from_lane_id": from_lane_id,
                "to_lane_id": to_lane_id,
                "from_clause_ids": sorted(from_clause_ids),
                "to_clause_ids": sorted(to_clause_ids),
                "relationship": relationship,
            }
        )
    return {
        "schema_version": SOURCE_PARTITION_MANIFEST_SCHEMA,
        "partition_id": _identifier(value, "partition_id"),
        "authority_snapshot_digest": _digest(value, "authority_snapshot_digest"),
        "lanes": sorted(lanes, key=lambda item: item["lane_id"]),
        "dependency_stubs": sorted(
            dependency_stubs, key=lambda item: item["dependency_ref"]
        ),
        "global_lane_id": global_lane_id,
        "unresolved_clause_ids": unresolved,
    }


def validate_source_partition_product(value: Any) -> dict[str, Any]:
    """Validate and canonicalize the frozen authority/partition product."""

    if not isinstance(value, dict):
        raise CorridorKitError("source partition product must be an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "source_bundle",
            "source_clause_inventory",
            "revision",
            "method_digest",
            "compiler_config_digest",
            "partition_manifest",
        },
        label="source partition product",
    )
    if value.get("schema_version") != SOURCE_PARTITION_PRODUCT_SCHEMA:
        raise CorridorKitError("source partition product has the wrong schema")
    source_bundle = validate_source_bundle(value.get("source_bundle"))
    if source_bundle.get("schema_version") != TASK_SOURCE_BUNDLE_SCHEMA_V3:
        raise CorridorKitError(
            "source partition product requires a frozen AuthoritySnapshot"
        )
    source_clauses = validate_source_clause_inventory_v3(
        value.get("source_clause_inventory"), source_bundle=source_bundle
    )
    partition_manifest = _validate_source_partition_manifest(
        value.get("partition_manifest"),
        source_clause_ids={item["clause_id"] for item in source_clauses},
    )
    if partition_manifest["authority_snapshot_digest"] != sha256_json(source_bundle):
        raise CorridorKitError(
            "source partition manifest does not bind the AuthoritySnapshot"
        )
    return {
        "schema_version": SOURCE_PARTITION_PRODUCT_SCHEMA,
        "source_bundle": source_bundle,
        "source_clause_inventory": source_clauses,
        "revision": validate_ir_revision(value.get("revision")),
        "method_digest": _digest(value, "method_digest"),
        "compiler_config_digest": _digest(value, "compiler_config_digest"),
        "partition_manifest": partition_manifest,
    }


def build_source_witness_repair_envelope(
    source_partition_product: Any,
    prior_witness_product: Any,
    *,
    affected_lane_ids: Iterable[str],
    source_refs: Iterable[str],
) -> dict[str, Any]:
    """Project repair scope onto identities visible in the frozen source partition."""

    partition = validate_source_partition_product(source_partition_product)
    if (
        not isinstance(prior_witness_product, dict)
        or prior_witness_product.get("schema_version") != WITNESS_LANE_PRODUCT_SCHEMA
    ):
        raise CorridorKitError("source witness repair requires a witness lane product")
    lanes = list(affected_lane_ids)
    if (
        not lanes
        or any(not isinstance(item, str) or not item.strip() for item in lanes)
        or len(lanes) != len(set(lanes))
    ):
        raise CorridorKitError(
            "source witness repair affected lanes must be a non-empty unique text list"
        )
    known_lanes = {
        item["lane_id"] for item in partition["partition_manifest"]["lanes"]
    }
    unknown_lanes = sorted(set(lanes) - known_lanes)
    if unknown_lanes:
        raise CorridorKitError(
            f"source witness repair lane escapes frozen partition: {unknown_lanes}"
        )
    refs = list(source_refs)
    if (
        any(not isinstance(item, str) or not item.strip() for item in refs)
        or len(refs) != len(set(refs))
    ):
        raise CorridorKitError(
            "source witness repair source refs must be a unique text list"
        )
    known_source_refs = {
        item["clause_id"] for item in partition["source_clause_inventory"]
    }
    known_source_refs.update(
        source_slice["slice_id"]
        for item in partition["source_clause_inventory"]
        for source_slice in item["source_slices"]
    )
    known_source_refs.update(
        item["source_id"] for item in partition["source_bundle"]["sources"]
    )
    known_source_refs.update(
        item["source_ref"] for item in partition["source_bundle"]["sources"]
    )
    unknown_refs = sorted(set(refs) - known_source_refs)
    if unknown_refs:
        raise CorridorKitError(
            f"source witness repair ref escapes frozen partition: {unknown_refs}"
        )
    return {
        "schema_version": SOURCE_WITNESS_REPAIR_ENVELOPE_SCHEMA,
        "affected_lane_ids": sorted(lanes),
        "source_refs": sorted(refs),
        "partition_product_digest": sha256_json(partition),
        "prior_witness_product_digest": sha256_json(prior_witness_product),
    }


def _validate_rule_lane_bindings(
    value: Any, *, lane_ids: set[str], rule_ids: set[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CorridorKitError("rule lane bindings must be non-empty")
    result: list[dict[str, Any]] = []
    owned_rules: set[str] = set()
    seen_lanes: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CorridorKitError("rule lane binding must be an object")
        _exact_keys(
            raw,
            {"schema_version", "lane_id", "rule_ids"},
            label="rule lane binding",
        )
        if raw.get("schema_version") != RULE_LANE_BINDING_SCHEMA:
            raise CorridorKitError("rule lane binding has the wrong schema")
        lane_id = _identifier(raw, "lane_id")
        if lane_id not in lane_ids or lane_id in seen_lanes:
            raise CorridorKitError("rule lane binding has an unknown or duplicate lane")
        seen_lanes.add(lane_id)
        bound_rules = _text_list(raw, "rule_ids")
        if set(bound_rules) - rule_ids:
            raise CorridorKitError("rule lane binding references unknown Rules")
        if owned_rules.intersection(bound_rules):
            raise CorridorKitError("Rule has duplicate lane ownership")
        owned_rules.update(bound_rules)
        result.append(
            {
                "schema_version": RULE_LANE_BINDING_SCHEMA,
                "lane_id": lane_id,
                "rule_ids": bound_rules,
            }
        )
    if owned_rules != rule_ids:
        raise CorridorKitError("rule lane bindings do not own every Rule exactly once")
    return sorted(result, key=lambda item: item["lane_id"])


def _validate_witness_lane_packages(
    value: Any,
    *,
    lane_ids: set[str],
    source_clause_ids: set[str],
    source_slice_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CorridorKitError("witness lane packages must be non-empty")
    packages: list[dict[str, Any]] = []
    seen_lanes: set[str] = set()
    seen_witnesses: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CorridorKitError("witness lane package must be an object")
        _exact_keys(
            raw,
            {
                "schema_version",
                "lane_id",
                "role_session_ref",
                "visibility",
                "source_clause_ids",
                "source_slice_ids",
                "witnesses",
            },
            label="witness lane package",
        )
        if raw.get("schema_version") != WITNESS_LANE_PACKAGE_SCHEMA:
            raise CorridorKitError("witness lane package has the wrong schema")
        lane_id = _identifier(raw, "lane_id")
        if lane_id not in lane_ids or lane_id in seen_lanes:
            raise CorridorKitError("witness lane package has an unknown or duplicate lane")
        seen_lanes.add(lane_id)
        visibility = raw.get("visibility")
        if not isinstance(visibility, dict):
            raise CorridorKitError("witness lane visibility must be an object")
        _exact_keys(
            visibility,
            {
                "source_only",
                "candidate_rule_visible",
                "candidate_checklist_visible",
                "candidate_witness_visible",
                "input_envelope_digest",
            },
            label="witness lane visibility",
        )
        if (
            visibility.get("source_only") is not True
            or visibility.get("candidate_rule_visible") is not False
            or visibility.get("candidate_checklist_visible") is not False
            or visibility.get("candidate_witness_visible") is not False
        ):
            raise CorridorKitError("witness lane must use a source-only input envelope")
        envelope_digest = _digest(visibility, "input_envelope_digest")
        package_clause_ids = _text_list(raw, "source_clause_ids", nonempty=True)
        package_slice_ids = _text_list(raw, "source_slice_ids", nonempty=True)
        if set(package_clause_ids) - source_clause_ids or set(package_slice_ids) - source_slice_ids:
            raise CorridorKitError("witness lane package references unknown source identity")
        raw_witnesses = raw.get("witnesses")
        if not isinstance(raw_witnesses, list) or not raw_witnesses:
            raise CorridorKitError("witness lane package must contain witnesses")
        witnesses: list[dict[str, Any]] = []
        kinds: set[str] = set()
        for witness in raw_witnesses:
            if not isinstance(witness, dict):
                raise CorridorKitError("source witness must be an object")
            _exact_keys(
                witness,
                {
                    "schema_version",
                    "witness_ref",
                    "kind",
                    "source_clause_ids",
                    "source_slice_ids",
                    "operator",
                    "input_case",
                    "expected_relation",
                    "boundary_relation",
                },
                label="source witness",
            )
            if witness.get("schema_version") != SOURCE_WITNESS_SCHEMA:
                raise CorridorKitError("source witness has the wrong schema")
            witness_ref = _identifier(witness, "witness_ref")
            if witness_ref in seen_witnesses:
                raise CorridorKitError(f"source witness is duplicated: {witness_ref}")
            seen_witnesses.add(witness_ref)
            kind = _text(witness, "kind")
            if kind not in SOURCE_WITNESS_KINDS:
                raise CorridorKitError(f"source witness has an unknown kind: {kind}")
            kinds.add(kind)
            witness_clause_ids = _text_list(witness, "source_clause_ids", nonempty=True)
            witness_slice_ids = _text_list(witness, "source_slice_ids", nonempty=True)
            if not set(witness_clause_ids).issubset(package_clause_ids) or not set(
                witness_slice_ids
            ).issubset(package_slice_ids):
                raise CorridorKitError("source witness escapes its lane source envelope")
            input_case = witness.get("input_case")
            if not isinstance(input_case, dict):
                raise CorridorKitError("source witness input_case must be an object")
            operator = _text(witness, "operator")
            if not _OPERATOR.fullmatch(operator):
                raise CorridorKitError("source witness operator must be stable")
            witnesses.append(
                {
                    "schema_version": SOURCE_WITNESS_SCHEMA,
                    "witness_ref": witness_ref,
                    "kind": kind,
                    "source_clause_ids": witness_clause_ids,
                    "source_slice_ids": witness_slice_ids,
                    "operator": operator,
                    "input_case": input_case,
                    "expected_relation": _text(witness, "expected_relation"),
                    "boundary_relation": _text(witness, "boundary_relation"),
                }
            )
        if kinds != SOURCE_WITNESS_KINDS:
            raise CorridorKitError(
                "each witness lane must retain positive, negative, and boundary cases"
            )
        packages.append(
            {
                "schema_version": WITNESS_LANE_PACKAGE_SCHEMA,
                "lane_id": lane_id,
                "role_session_ref": _text(raw, "role_session_ref"),
                "visibility": {
                    **visibility,
                    "input_envelope_digest": envelope_digest,
                },
                "source_clause_ids": package_clause_ids,
                "source_slice_ids": package_slice_ids,
                "witnesses": witnesses,
            }
        )
    if seen_lanes != lane_ids:
        raise CorridorKitError("witness lane packages do not cover every source lane")
    return sorted(packages, key=lambda item: item["lane_id"])


def validate_rule_semantics(value: Any) -> dict[str, Any]:
    """Return one canonical Rule semantic object or raise without guessing."""

    if not isinstance(value, dict):
        raise CorridorKitError("typed Rule semantics must be an object")
    semantics_schema = value.get("schema_version")
    is_v5 = semantics_schema == TYPED_RULE_SEMANTICS_SCHEMA_V5
    is_v4 = semantics_schema == TYPED_RULE_SEMANTICS_SCHEMA_V4
    is_v3 = semantics_schema == TYPED_RULE_SEMANTICS_SCHEMA_V3
    is_v2 = semantics_schema == TYPED_RULE_SEMANTICS_SCHEMA
    is_current = is_v2 or is_v3 or is_v4 or is_v5
    expected_fields = {
        "rule_kind",
        "compilation_status",
        "compile_issues",
        "quantifier",
        "conditions",
        "checklist_projection",
        "dependencies",
    }
    if is_current:
        expected_fields.update(
            {"schema_version", "requirement_level", "applicability"}
        )
        if is_v4 or is_v5:
            expected_fields.add("guidance")
    elif semantics_schema is not None:
        raise CorridorKitError("typed Rule semantics has an unknown schema")
    _exact_keys(
        value,
        expected_fields,
        label="typed Rule semantics",
    )
    requirement_level = "required"
    applicability: dict[str, str] | None = None
    if is_current:
        requirement_level = _text(value, "requirement_level")
        if requirement_level not in REQUIREMENT_LEVELS:
            raise CorridorKitError(
                f"unknown typed Rule requirement_level: {requirement_level}"
            )
        raw_applicability = value.get("applicability")
        if not isinstance(raw_applicability, dict):
            raise CorridorKitError("typed Rule applicability must be an object")
        _exact_keys(
            raw_applicability,
            {"mode", "predicate"},
            label="typed Rule applicability",
        )
        applicability_mode = _text(raw_applicability, "mode")
        if applicability_mode not in APPLICABILITY_MODES:
            raise CorridorKitError(
                f"unknown typed Rule applicability mode: {applicability_mode}"
            )
        applicability = {
            "mode": applicability_mode,
            "predicate": _text(raw_applicability, "predicate"),
        }
    rule_kind = _text(value, "rule_kind")
    if rule_kind not in RULE_KINDS:
        raise CorridorKitError(f"unknown typed Rule kind: {rule_kind}")
    compilation_status = _text(value, "compilation_status")
    if compilation_status not in COMPILATION_STATUSES:
        raise CorridorKitError(
            f"unknown typed Rule compilation status: {compilation_status}"
        )
    compile_issues = _text_list(value, "compile_issues")
    if compilation_status == "complete" and compile_issues:
        raise CorridorKitError("complete typed Rule cannot retain compile issues")
    if compilation_status != "complete" and not compile_issues:
        raise CorridorKitError(
            "non-complete typed Rule must retain at least one compile issue"
        )

    quantifier = value.get("quantifier")
    if not isinstance(quantifier, dict):
        raise CorridorKitError("typed Rule quantifier must be an object")
    _exact_keys(
        quantifier,
        (
            {
                "mode",
                "subject_axis",
                "subjects",
                "domain_kind",
                "domain_source",
                "domain_predicate",
            }
            if is_current
            else {"mode", "subject_axis", "subjects"}
        ),
        label="typed Rule quantifier",
    )
    mode = _text(quantifier, "mode")
    if mode not in QUANTIFIER_MODES:
        raise CorridorKitError(f"unknown typed Rule quantifier mode: {mode}")
    subject_axis = _identifier(quantifier, "subject_axis")
    subjects = _text_list(quantifier, "subjects", nonempty=True)
    if len(subjects) != len(set(subjects)):
        raise CorridorKitError("typed Rule subjects contain duplicates")
    domain_kind: str | None = None
    domain_source: str | None = None
    domain_predicate: str | None = None
    if is_current:
        domain_kind = _text(quantifier, "domain_kind")
        if domain_kind not in DOMAIN_KINDS:
            raise CorridorKitError(f"unknown typed Rule domain_kind: {domain_kind}")
        domain_source = _text(quantifier, "domain_source")
        if domain_source not in DOMAIN_SOURCES:
            raise CorridorKitError(
                f"unknown typed Rule domain_source: {domain_source}"
            )
        domain_predicate = _text(quantifier, "domain_predicate")
        if (
            compilation_status == "complete"
            and mode in {"all", "none"}
            and domain_source == "produced_output"
        ):
            raise CorridorKitError(
                "complete universal typed Rule cannot define its domain from produced output"
            )
        if domain_kind == "open_including" and not domain_predicate.strip():
            raise CorridorKitError(
                "open including-domain must retain a residual domain predicate"
            )

    raw_conditions = value.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise CorridorKitError("typed Rule conditions must be a non-empty list")
    conditions: list[dict[str, Any]] = []
    condition_ids: set[str] = set()
    for raw in raw_conditions:
        if not isinstance(raw, dict):
            raise CorridorKitError("typed Rule condition must be an object")
        _exact_keys(
            raw,
            (
                ({
                    "condition_id",
                    "condition_kind",
                    "predicate",
                    "expected_outcome",
                    "required_witness_operators",
                } | ({"predicate_spec"} if is_v5 else set()))
                if is_v4 or is_v5
                else {
                    "condition_id",
                    "predicate",
                    "expected_outcome",
                    "required_witness_operators",
                }
            ),
            label="typed Rule condition",
        )
        condition_id = _identifier(raw, "condition_id")
        if condition_id in condition_ids:
            raise CorridorKitError(
                f"typed Rule condition is duplicated: {condition_id}"
            )
        condition_ids.add(condition_id)
        normalized_condition = {
                "condition_id": condition_id,
                "predicate": _text(raw, "predicate"),
                "expected_outcome": _text(raw, "expected_outcome"),
                "required_witness_operators": _operators(
                    raw,
                    "required_witness_operators",
                    nonempty=compilation_status == "complete",
                ),
            }
        if is_v4 or is_v5:
            condition_kind = _text(raw, "condition_kind")
            if condition_kind not in CONDITION_KINDS:
                raise CorridorKitError(
                    f"unknown typed Rule condition_kind: {condition_kind}"
                )
            normalized_condition["condition_kind"] = condition_kind
        if is_v5:
            normalized_condition["predicate_spec"] = validate_typed_predicate(
                raw.get("predicate_spec"), condition_kind=condition_kind
            )
        conditions.append(normalized_condition)

    if (
        compilation_status == "complete"
        and rule_kind in {"temporal_conditional", "state_transition", "precedence"}
    ):
        temporal_conditions = (
            [
                condition
                for condition in conditions
                if condition.get("condition_kind") in {"temporal", "state_transition"}
            ]
            if is_v4 or is_v5
            else conditions
        )
        if (is_v4 or is_v5) and not temporal_conditions:
            raise CorridorKitError("temporal Rule requires at least one temporal condition")
        for condition in temporal_conditions:
            if not set(condition["required_witness_operators"]).intersection(
                TEMPORAL_OPERATORS
            ):
                raise CorridorKitError(
                    f"temporal Rule condition {condition['condition_id']} "
                    "requires a temporal witness operator"
                )

    projection = value.get("checklist_projection")
    if not isinstance(projection, dict):
        raise CorridorKitError("typed Rule checklist_projection must be an object")
    _exact_keys(
        projection,
        {
            "projection_mode",
            "behavioral_partitions",
            "evidence_requirement",
            "decision_rule",
        },
        label="typed Rule checklist_projection",
    )
    projection_mode = _text(projection, "projection_mode")
    if projection_mode not in PROJECTION_MODES:
        raise CorridorKitError(
            f"unknown typed Rule projection mode: {projection_mode}"
        )
    if projection_mode == "aggregate" and len(subjects) != 1:
        raise CorridorKitError(
            "aggregate projection must declare exactly one aggregate subject"
        )
    partitions = _text_list(
        projection, "behavioral_partitions", nonempty=True
    )
    decision_rule = projection.get("decision_rule")
    if not isinstance(decision_rule, dict):
        raise CorridorKitError("typed Rule decision_rule must be an object")
    _exact_keys(
        decision_rule,
        {"pass", "fail", "unknown"},
        label="typed Rule decision_rule",
    )
    normalized_decision = {
        name: _text(decision_rule, name) for name in ("pass", "fail", "unknown")
    }

    raw_dependencies = value.get("dependencies")
    if not isinstance(raw_dependencies, list):
        raise CorridorKitError("typed Rule dependencies must be a list")
    dependencies: list[dict[str, Any]] = []
    seen_dependencies: set[tuple[str, str]] = set()
    for raw in raw_dependencies:
        if not isinstance(raw, dict):
            raise CorridorKitError("typed Rule dependency must be an object")
        _exact_keys(
            raw,
            (
                {"relationship", "target_rule_id", "provenance", "alignment"}
                if is_v4 or is_v5
                else {"relationship", "target_rule_id", "provenance"}
                if is_v3
                else {"relationship", "target_rule_id"}
            ),
            label="typed Rule dependency",
        )
        relationship = _text(raw, "relationship")
        if relationship not in RULE_RELATIONSHIPS:
            raise CorridorKitError(
                f"unknown typed Rule relationship: {relationship}"
            )
        target_rule_id = _identifier(raw, "target_rule_id")
        identity = (relationship, target_rule_id)
        if identity in seen_dependencies:
            raise CorridorKitError(
                f"typed Rule dependency is duplicated: {relationship}:{target_rule_id}"
            )
        seen_dependencies.add(identity)
        normalized_dependency: dict[str, Any] = {
            "relationship": relationship,
            "target_rule_id": target_rule_id,
        }
        if is_v3 or is_v4 or is_v5:
            raw_provenance = raw.get("provenance")
            if not isinstance(raw_provenance, dict):
                raise CorridorKitError("successor dependency provenance must be an object")
            _exact_keys(
                raw_provenance,
                {
                    "kind",
                    "source_slice_ids",
                    "derivation_kind",
                    "input_rule_provenance_digests",
                },
                label="successor dependency provenance",
            )
            provenance_kind = _text(raw_provenance, "kind")
            if provenance_kind not in DEPENDENCY_PROVENANCE_KINDS:
                raise CorridorKitError(
                    f"unknown dependency provenance kind: {provenance_kind}"
                )
            source_slice_ids = _text_list(raw_provenance, "source_slice_ids")
            derivation_kind = raw_provenance.get("derivation_kind")
            raw_inputs = raw_provenance.get("input_rule_provenance_digests")
            if not isinstance(raw_inputs, dict):
                raise CorridorKitError(
                    "dependency input_rule_provenance_digests must be an object"
                )
            input_digests: dict[str, str] = {}
            for input_rule_id, digest in raw_inputs.items():
                if not isinstance(input_rule_id, str) or not _IDENTIFIER.fullmatch(
                    input_rule_id
                ):
                    raise CorridorKitError(
                        "dependency provenance input key must be a stable Rule ID"
                    )
                input_digests[input_rule_id] = _digest(
                    {"digest": digest}, "digest"
                )
            if provenance_kind == "direct":
                if not source_slice_ids or derivation_kind is not None or input_digests:
                    raise CorridorKitError(
                        "direct dependency provenance requires source slices only"
                    )
            else:
                if source_slice_ids:
                    raise CorridorKitError(
                        "derived dependency provenance cannot claim direct source slices"
                    )
                if not isinstance(derivation_kind, str) or (
                    derivation_kind not in DEPENDENCY_DERIVATION_KINDS
                ):
                    raise CorridorKitError(
                        "derived dependency provenance requires a declared derivation kind"
                    )
                if not input_digests:
                    raise CorridorKitError(
                        "derived dependency provenance requires current Rule provenance digests"
                    )
            normalized_dependency["provenance"] = {
                "kind": provenance_kind,
                "source_slice_ids": source_slice_ids,
                "derivation_kind": derivation_kind,
                "input_rule_provenance_digests": input_digests,
            }
            if is_v4 or is_v5:
                normalized_dependency["alignment"] = validate_relationship_alignment(
                    raw.get("alignment")
                )
        dependencies.append(normalized_dependency)

    guidance: list[dict[str, Any]] = []
    if is_v4 or is_v5:
        raw_guidance = value.get("guidance")
        if not isinstance(raw_guidance, list):
            raise CorridorKitError("typed Guidance must be a list")
        guidance_ids: set[str] = set()
        for raw in raw_guidance:
            if not isinstance(raw, dict):
                raise CorridorKitError("typed Guidance item must be an object")
            _exact_keys(
                raw,
                {"guidance_id", "trigger", "action", "source_slice_ids"},
                label="typed Guidance item",
            )
            guidance_id = _identifier(raw, "guidance_id")
            if guidance_id in guidance_ids:
                raise CorridorKitError(f"typed Guidance ID is duplicated: {guidance_id}")
            guidance_ids.add(guidance_id)
            guidance.append(
                {
                    "guidance_id": guidance_id,
                    "trigger": _text(raw, "trigger"),
                    "action": _text(raw, "action"),
                    "source_slice_ids": _text_list(raw, "source_slice_ids", nonempty=True),
                }
            )

    normalized = {
        "rule_kind": rule_kind,
        "compilation_status": compilation_status,
        "compile_issues": compile_issues,
        "quantifier": {
            "mode": mode,
            "subject_axis": subject_axis,
            "subjects": subjects,
        },
        "conditions": conditions,
        "checklist_projection": {
            "projection_mode": projection_mode,
            "behavioral_partitions": partitions,
            "evidence_requirement": _text(projection, "evidence_requirement"),
            "decision_rule": normalized_decision,
        },
        "dependencies": dependencies,
    }
    if is_v4 or is_v5:
        normalized["guidance"] = guidance
    if is_current:
        normalized = {
            "schema_version": (
                TYPED_RULE_SEMANTICS_SCHEMA_V5
                if is_v5
                else TYPED_RULE_SEMANTICS_SCHEMA_V4
                if is_v4
                else TYPED_RULE_SEMANTICS_SCHEMA_V3
                if is_v3
                else TYPED_RULE_SEMANTICS_SCHEMA
            ),
            "requirement_level": requirement_level,
            "applicability": applicability,
            **normalized,
        }
        normalized["quantifier"] = {
            **normalized["quantifier"],
            "domain_kind": domain_kind,
            "domain_source": domain_source,
            "domain_predicate": domain_predicate,
        }
    return normalized


def project_rule_checklist_templates(
    *, rule_id: str, statement: str, semantics: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Project the complete declared subject-by-condition coverage product."""

    normalized = validate_rule_semantics(dict(semantics))
    semantics_digest = sha256_json(normalized)
    quantifier = normalized["quantifier"]
    projection = normalized["checklist_projection"]
    templates: list[dict[str, Any]] = []
    for subject_id in quantifier["subjects"]:
        for condition in normalized["conditions"]:
            coverage_cell = {
                "rule_id": rule_id,
                "subject_axis": quantifier["subject_axis"],
                "subject_id": subject_id,
                "condition_id": condition["condition_id"],
                "predicate": condition["predicate"],
                "expected_outcome": condition["expected_outcome"],
                **(
                    {
                        "predicate_spec": condition["predicate_spec"],
                        "predicate_digest": sha256_json(condition["predicate_spec"]),
                    }
                    if "predicate_spec" in condition
                    else {}
                ),
                **(
                    {"condition_kind": condition["condition_kind"]}
                    if "condition_kind" in condition
                    else {}
                ),
            }
            cell_digest = sha256_json(coverage_cell)
            templates.append(
                {
                    "checklist_item_id": f"CL-{cell_digest[7:23]}",
                    "source_rule_id": rule_id,
                    "source_rule_semantics_digest": semantics_digest,
                    "coverage_cell": coverage_cell,
                    "obligation": (
                        f"For {quantifier['subject_axis']} {subject_id}, when "
                        f"{condition['predicate']}, require "
                        f"{condition['expected_outcome']}. Source Rule: {statement}"
                    ),
                    "scope": {
                        "projection_mode": projection["projection_mode"],
                        "subject_axis": quantifier["subject_axis"],
                        "subject_id": subject_id,
                        "condition_id": condition["condition_id"],
                        "required_partitions": projection[
                            "behavioral_partitions"
                        ],
                    },
                    "quantifier": quantifier["mode"],
                    "behavioral_partitions": projection[
                        "behavioral_partitions"
                    ],
                    "evidence_requirement": projection["evidence_requirement"],
                    "decision_rule": projection["decision_rule"],
                    "compilation_status": normalized["compilation_status"],
                    "required_witness_operators": condition[
                        "required_witness_operators"
                    ],
                    **(
                        {
                            "typed_rule_semantics_schema": normalized[
                                "schema_version"
                            ],
                            "requirement_level": normalized[
                                "requirement_level"
                            ],
                            "applicability": normalized["applicability"],
                            "domain_kind": quantifier["domain_kind"],
                            "domain_source": quantifier["domain_source"],
                            "domain_predicate": quantifier[
                                "domain_predicate"
                            ],
                        }
                        if normalized.get("schema_version")
                        in {
                            TYPED_RULE_SEMANTICS_SCHEMA,
                            TYPED_RULE_SEMANTICS_SCHEMA_V3,
                            TYPED_RULE_SEMANTICS_SCHEMA_V4,
                            TYPED_RULE_SEMANTICS_SCHEMA_V5,
                        }
                        else {}
                    ),
                }
            )
    return templates


def project_witness_obligation_templates(
    *, rule_id: str, statement: str, semantics: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Project explicit Rule semantics into stable, task-neutral witness duties.

    The projection classifies only condition kinds and operator names that the
    compiled Rule already declares.  It never infers a business relationship or
    expected outcome from a Rule kind.
    """

    normalized = validate_rule_semantics(dict(semantics))
    semantics_digest = sha256_json(normalized)
    checklist = project_rule_checklist_templates(
        rule_id=rule_id,
        statement=statement,
        semantics=normalized,
    )
    condition_by_id = {
        condition["condition_id"]: condition
        for condition in normalized["conditions"]
    }
    obligations: list[dict[str, Any]] = []
    for item in checklist:
        condition = condition_by_id[item["coverage_cell"]["condition_id"]]
        operators = set(condition["required_witness_operators"])
        families = {"declared_condition"}
        condition_kind = condition.get("condition_kind", "legacy_untyped")
        if condition_kind == "temporal" or operators.intersection(TEMPORAL_OPERATORS):
            families.add("temporal_boundary")
        if condition_kind == "state_transition" or "state_transition" in operators:
            families.add("state_transition")
        if normalized.get("applicability", {}).get("mode") == "conditional":
            families.add("conditional_branch")
        for family, family_operators in _WITNESS_FAMILY_OPERATORS.items():
            if operators.intersection(family_operators):
                families.add(family)
        identity = {
            "rule_id": rule_id,
            "checklist_item_id": item["checklist_item_id"],
            "condition_id": condition["condition_id"],
            "condition_kind": condition_kind,
            "required_witness_operators": sorted(operators),
            "behavioral_partitions": sorted(item["behavioral_partitions"]),
            "rule_semantics_digest": semantics_digest,
        }
        obligations.append(
            {
                "schema_version": WITNESS_OBLIGATION_SCHEMA,
                "witness_obligation_id": f"WOB-{sha256_json(identity)[7:23]}",
                **identity,
                "witness_families": sorted(families),
                "evidence_requirement": item["evidence_requirement"],
                "decision_rule": item["decision_rule"],
            }
        )
    return obligations


def semantic_edge_id(
    *, from_rule_id: str, to_rule_id: str, declared_relationship: str
) -> str:
    """Return the stable family identity for one declared semantic Rule edge."""

    return "SEDGE-" + sha256_json(
        {
            "from_rule_id": from_rule_id,
            "to_rule_id": to_rule_id,
            "declared_relationship": declared_relationship,
        }
    )[7:23]


def _compiler_implementation_digest() -> str:
    try:
        return sha256_bytes(Path(__file__).read_bytes())
    except OSError:
        return sha256_json(
            {
                "schema_version": TYPED_RULE_COMPILATION_SCHEMA,
                "rule_kinds": sorted(RULE_KINDS),
                "relationships": sorted(RULE_RELATIONSHIPS),
            }
        )


def _required_semantic_roles(semantics: Mapping[str, Any]) -> set[str]:
    roles = {
        "obligation",
        "domain",
        "quantifier",
        "condition",
        "outcome",
        "evidence_requirement",
        "witness_requirement",
    }
    if semantics.get("applicability", {}).get("mode") == "conditional":
        roles.add("applicability")
    if semantics.get("dependencies"):
        roles.add("relationship")
    if semantics.get("rule_kind") == "prohibition":
        roles.add("prohibition")
    return roles


def _unaccounted_normative_ranges(
    *, source_bundle: Mapping[str, Any], source_clauses: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Return non-whitespace normative byte ranges absent from clause inventory."""

    covered: dict[tuple[str, str], set[int]] = {}
    for clause in source_clauses:
        for source_slice in clause.get("source_slices", []):
            representation = source_slice.get("representation", "source_bytes")
            covered.setdefault(
                (source_slice["source_id"], representation), set()
            ).update(
                range(source_slice["byte_start"], source_slice["byte_end"])
            )
    gaps: list[dict[str, Any]] = []
    for source in source_bundle["sources"]:
        if source.get("plane") != "normative_rule":
            continue
        if isinstance(source.get("content_utf8"), str):
            representation = "source_bytes"
            payload = source["content_utf8"].encode("utf-8")
        elif isinstance(source.get("extraction_artifact"), dict):
            representation = "extraction_artifact"
            payload = source["extraction_artifact"]["content_utf8"].encode("utf-8")
        else:
            continue
        missing = {
            index
            for index, byte in enumerate(payload)
            if index
            not in covered.get((source["source_id"], representation), set())
            and not chr(byte).isspace()
        }
        while missing:
            start = min(missing)
            end = start + 1
            missing.remove(start)
            while end in missing:
                missing.remove(end)
                end += 1
            gaps.append(
                {
                    "source_id": source["source_id"],
                    "representation": representation,
                    "byte_start": start,
                    "byte_end": end,
                }
            )
    return gaps


def _cell_matches_selector(cell: Mapping[str, Any], selector: Mapping[str, Any]) -> bool:
    coverage = cell["coverage_cell"]
    return all(value is None or coverage.get(field) == value for field, value in selector.items())


def _scoped_cells(
    cells: list[dict[str, Any]], selectors: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if not selectors:
        return cells
    return [cell for cell in cells if any(_cell_matches_selector(cell, item) for item in selectors)]


def _alignment_cardinality_issues(
    *,
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    source_cells: list[dict[str, Any]],
    target_cells: list[dict[str, Any]],
    alignment: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    for endpoint, cells, index, bound in (
        ("source", source_cells, 0, alignment["source_cardinality"]),
        ("target", target_cells, 1, alignment["target_cardinality"]),
    ):
        for cell in cells:
            count = sum(pair[index]["checklist_item_id"] == cell["checklist_item_id"] for pair in pairs)
            maximum = bound["maximum"]
            if count < bound["minimum"] or (maximum is not None and count > maximum):
                issues.append(
                    f"{endpoint}:{cell['checklist_item_id']}:projected={count}:"
                    f"expected={bound['minimum']}..{maximum if maximum is not None else '*'}"
                )
    return issues


def _project_aligned_dependency(
    *,
    dependency: Mapping[str, Any],
    source_cells: list[dict[str, Any]],
    target_cells: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[str]]:
    alignment = dependency["relationship_alignment"]
    source_scope = _scoped_cells(source_cells, alignment["source_scope"])
    target_scope = _scoped_cells(target_cells, alignment["target_scope"])
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if alignment["mode"] == "keyed":
        for source in source_scope:
            for target in target_scope:
                if all(
                    source["coverage_cell"].get(key_pair["source_key"])
                    == target["coverage_cell"].get(key_pair["target_key"])
                    for key_pair in alignment["key_pairs"]
                ):
                    pairs.append((source, target))
    elif alignment["mode"] in {"explicit_pairs", "aggregate_to_members"}:
        for declared in alignment["explicit_pairs"]:
            sources = [
                cell
                for cell in source_scope
                if _cell_matches_selector(cell, declared["source"])
            ]
            targets = [
                cell
                for cell in target_scope
                if _cell_matches_selector(cell, declared["target"])
            ]
            pairs.extend((source, target) for source in sources for target in targets)
    else:
        pairs = [(source, target) for source in source_scope for target in target_scope]
    unique = {
        (source["checklist_item_id"], target["checklist_item_id"]): (source, target)
        for source, target in pairs
    }
    pairs = [unique[key] for key in sorted(unique)]
    issues: list[str] = []
    if not source_scope or not target_scope:
        issues.append("alignment_scope_matches_no_coverage_cells")
    if not pairs:
        issues.append("alignment_projects_no_edges")
    issues.extend(
        _alignment_cardinality_issues(
            pairs=pairs,
            source_cells=source_scope,
            target_cells=target_scope,
            alignment=alignment,
        )
    )
    return pairs, issues


def project_relationship_alignment(
    *,
    alignment: Mapping[str, Any],
    source_cells: list[dict[str, Any]],
    target_cells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project and audit the exact checklist-edge set for one relationship.

    Compiler, Graph validation, and Doctor share this function so a relation
    cannot regain an implicit Cartesian product after compilation.
    """

    normalized_alignment = validate_relationship_alignment(dict(alignment))
    pairs, issues = _project_aligned_dependency(
        dependency={"relationship_alignment": normalized_alignment},
        source_cells=source_cells,
        target_cells=target_cells,
    )
    return {
        "alignment": normalized_alignment,
        "edge_pairs": [
            {
                "from_ref": source["checklist_item_id"],
                "to_ref": target["checklist_item_id"],
            }
            for source, target in pairs
        ],
        "issues": issues,
    }


def compile_typed_rule_ir(
    value: Any,
    *,
    run_classification: str = "fresh_task_pre_experiment",
) -> dict[str, Any]:
    """Validate a complete IR and return deterministic Graph record templates."""

    if run_classification not in RUN_CLASSIFICATIONS:
        raise CorridorKitError(
            f"unknown compile-probe run classification: {run_classification}"
        )
    if not isinstance(value, dict):
        raise CorridorKitError("typed Rule IR must be an object")
    ir_schema = value.get("schema_version")
    is_v5 = ir_schema == TYPED_RULE_IR_SCHEMA_V5
    is_v4 = ir_schema == TYPED_RULE_IR_SCHEMA_V4
    is_v3 = ir_schema == TYPED_RULE_IR_SCHEMA_V3
    is_v2 = ir_schema == TYPED_RULE_IR_SCHEMA
    is_byte_bound = is_v3 or is_v4 or is_v5
    is_source_bound = is_v2 or is_byte_bound
    if not is_source_bound and ir_schema != TYPED_RULE_IR_SCHEMA_V1:
        raise CorridorKitError("typed Rule IR has the wrong schema")
    _exact_keys(
        value,
        (
            (
                {
                "schema_version",
                "source_bundle",
                "source_clause_inventory",
                "revision",
                "method_digest",
                "compiler_config_digest",
                "rules",
                }
                | (
                    {
                        "partition_manifest",
                        "rule_lane_bindings",
                        "witness_lane_packages",
                    }
                    if is_v5
                    else set()
                )
            )
            if is_source_bound
            else {
                "schema_version",
                "task_source_ref",
                "task_source_digest",
                "method_digest",
                "compiler_config_digest",
                "rules",
            }
        ),
        label="typed Rule IR",
    )
    source_bundle: dict[str, Any] | None = None
    source_clauses: list[dict[str, Any]] = []
    revision: dict[str, Any] | None = None
    if is_source_bound:
        source_bundle = validate_source_bundle(value.get("source_bundle"))
        if is_byte_bound:
            required_bundle_schema = (
                TASK_SOURCE_BUNDLE_SCHEMA_V3
                if is_v4 or is_v5
                else TASK_SOURCE_BUNDLE_SCHEMA_V2
            )
            if source_bundle["schema_version"] != required_bundle_schema:
                raise CorridorKitError(
                    "successor typed Rule IR requires its matching frozen AuthoritySnapshot"
                )
            source_clauses = validate_source_clause_inventory_v3(
                value.get("source_clause_inventory"), source_bundle=source_bundle
            )
        else:
            if source_bundle["schema_version"] != TASK_SOURCE_BUNDLE_SCHEMA:
                raise CorridorKitError("typed Rule IR v2 requires task source bundle v1")
            source_clauses = validate_source_clause_inventory(
                value.get("source_clause_inventory")
            )
        revision = validate_ir_revision(value.get("revision"))
        instruction_source = next(
            source
            for source in source_bundle["sources"]
            if source["role"] == "instruction"
        )
        task_source_ref = instruction_source["source_ref"]
        task_source_digest = instruction_source.get(
            "source_digest", instruction_source.get("byte_digest")
        )
        if task_source_digest is None:
            raise CorridorKitError("public instruction lacks a frozen byte digest")
    else:
        task_source_ref = _text(value, "task_source_ref")
        task_source_digest = _digest(value, "task_source_digest")
    method_digest = _digest(value, "method_digest")
    compiler_config_digest = _digest(value, "compiler_config_digest")
    raw_rules = value.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise CorridorKitError("typed Rule IR rules must be a non-empty list")

    normalized_rules: list[dict[str, Any]] = []
    rule_ids: set[str] = set()
    rule_bodies: list[dict[str, Any]] = []
    checklist_templates: list[dict[str, Any]] = []
    witness_obligation_templates: list[dict[str, Any]] = []
    rule_dependency_templates: list[dict[str, Any]] = []
    checklist_templates_by_rule: dict[str, list[dict[str, Any]]] = {}
    rule_provenance_digest_by_id: dict[str, str] = {}
    partition_manifest: dict[str, Any] | None = None
    rule_lane_bindings: list[dict[str, Any]] = []
    witness_lane_packages: list[dict[str, Any]] = []
    source_witness_bindings: list[dict[str, Any]] = []
    v5_integration_issues: list[dict[str, Any]] = []
    clause_order_by_id = (
        {
            clause["clause_id"]: clause["clause_order_key"]
            for clause in source_clauses
        }
        if is_byte_bound
        else {}
    )
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise CorridorKitError("typed Rule IR rule must be an object")
        _exact_keys(
            raw,
            (
                {
                    "rule_id",
                    "statement",
                    "source_ref",
                    "source_digest",
                    "source_clause_ids",
                    "semantics",
                }
                if is_v2
                else (
                    {
                        "rule_id",
                        "statement",
                        "source_clause_ids",
                        "source_slices",
                        "semantics",
                    }
                    if is_byte_bound
                    else {
                        "rule_id",
                        "statement",
                        "source_ref",
                        "source_digest",
                        "semantics",
                    }
                )
            ),
            label="typed Rule IR rule",
        )
        rule_id = _identifier(raw, "rule_id")
        if rule_id in rule_ids:
            raise CorridorKitError(f"typed Rule ID is duplicated: {rule_id}")
        rule_ids.add(rule_id)
        statement = _text(raw, "statement")
        semantics = validate_rule_semantics(raw.get("semantics"))
        if is_v4 and semantics.get("schema_version") != TYPED_RULE_SEMANTICS_SCHEMA_V4:
            raise CorridorKitError("typed Rule IR v4 requires typed Rule semantics v4")
        if is_v5 and semantics.get("schema_version") != TYPED_RULE_SEMANTICS_SCHEMA_V5:
            raise CorridorKitError("typed Rule IR v5 requires typed Rule semantics v5")
        semantics_digest = sha256_json(semantics)
        if is_byte_bound:
            assert source_bundle is not None
            source_clause_ids = _text_list(raw, "source_clause_ids", nonempty=True)
            unknown_clause_ids = sorted(
                set(source_clause_ids) - set(clause_order_by_id)
            )
            if unknown_clause_ids:
                raise CorridorKitError(
                    f"typed Rule references unknown source clauses: {unknown_clause_ids}"
                )
            source_clause_ids = sorted(
                source_clause_ids, key=lambda clause_id: clause_order_by_id[clause_id]
            )
            source_slices = validate_rule_source_slices(raw.get("source_slices"))
            source_identity = rule_source_provenance_identity(
                rule_id=rule_id,
                statement=statement,
                source_clause_ids=source_clause_ids,
                source_slices=source_slices,
                source_bundle=source_bundle,
                source_clauses=source_clauses,
            )
            rule_source_provenance_digest = sha256_json(source_identity)
            rule_provenance_digest_by_id[rule_id] = rule_source_provenance_digest
            bundle_digest = sha256_json(source_bundle)
            normalized = {
                "rule_id": rule_id,
                "statement": statement,
                "source_ref": (
                    f"authority-snapshot:{bundle_digest}"
                    if is_v4 or is_v5
                    else f"source-bundle:{bundle_digest}"
                ),
                "source_digest": bundle_digest,
                **(
                    {
                        "authority_snapshot_manifest_digest": source_bundle[
                            "manifest_digest"
                        ]
                    }
                    if is_v4 or is_v5
                    else {}
                ),
                "source_clause_ids": source_clause_ids,
                "source_slices": source_slices,
                "rule_source_provenance_digest": rule_source_provenance_digest,
                "semantics": semantics,
            }
        else:
            normalized = {
                "rule_id": rule_id,
                "statement": statement,
                "source_ref": _text(raw, "source_ref"),
                "source_digest": _digest(raw, "source_digest"),
                **(
                    {
                        "source_clause_ids": _text_list(
                            raw, "source_clause_ids", nonempty=True
                        )
                    }
                    if is_v2
                    else {}
                ),
                "semantics": semantics,
            }
        normalized_rules.append(normalized)
        rule_bodies.append(
            {
                **normalized,
                "rule_semantics_digest": semantics_digest,
            }
        )
        projected_checklists = project_rule_checklist_templates(
            rule_id=rule_id, statement=statement, semantics=semantics
        )
        checklist_templates_by_rule[rule_id] = projected_checklists
        checklist_templates.extend(projected_checklists)
        witness_obligation_templates.extend(
            project_witness_obligation_templates(
                rule_id=rule_id,
                statement=statement,
                semantics=semantics,
            )
        )
        for dependency in semantics["dependencies"]:
            rule_dependency_templates.append(
                {
                    "from_rule_id": rule_id,
                    "to_rule_id": dependency["target_rule_id"],
                    "relationship": dependency["relationship"],
                    **(
                        {
                            "edge_provenance": dependency["provenance"],
                            **(
                                {"relationship_alignment": dependency["alignment"]}
                                if is_v4 or is_v5
                                else {}
                            ),
                        }
                        if is_byte_bound
                        else {}
                    ),
                }
            )

    if is_v5:
        assert source_bundle is not None
        all_clause_ids = {clause["clause_id"] for clause in source_clauses}
        all_slice_ids = {
            source_slice["slice_id"]
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        partition_manifest = _validate_source_partition_manifest(
            value.get("partition_manifest"), source_clause_ids=all_clause_ids
        )
        if partition_manifest["authority_snapshot_digest"] != sha256_json(source_bundle):
            raise CorridorKitError(
                "source partition manifest does not bind the AuthoritySnapshot"
            )
        lane_ids = {lane["lane_id"] for lane in partition_manifest["lanes"]}
        rule_lane_bindings = _validate_rule_lane_bindings(
            value.get("rule_lane_bindings"), lane_ids=lane_ids, rule_ids=rule_ids
        )
        witness_lane_packages = _validate_witness_lane_packages(
            value.get("witness_lane_packages"),
            lane_ids=lane_ids,
            source_clause_ids=all_clause_ids,
            source_slice_ids=all_slice_ids,
        )
        partition_lane_by_id = {
            lane["lane_id"]: lane for lane in partition_manifest["lanes"]
        }
        rule_by_id = {rule["rule_id"]: rule for rule in normalized_rules}
        witness_lane_by_id = {
            package["lane_id"]: package for package in witness_lane_packages
        }
        clause_id_by_slice = {
            source_slice["slice_id"]: clause["clause_id"]
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        for lane_id, package in witness_lane_by_id.items():
            lane = partition_lane_by_id[lane_id]
            accessible_clauses = set(lane["owner_clause_ids"]) | set(
                lane["boundary_clause_ids"]
            )
            if not set(package["source_clause_ids"]).issubset(accessible_clauses):
                raise CorridorKitError(
                    f"witness lane {lane_id} escapes its source clause envelope"
                )
            package_slice_clauses = {
                clause_id_by_slice[slice_id]
                for slice_id in package["source_slice_ids"]
            }
            if not package_slice_clauses.issubset(
                set(package["source_clause_ids"])
            ):
                raise CorridorKitError(
                    f"witness lane {lane_id} source slices escape its clause envelope"
                )
            source_envelope = {
                "schema_version": "charting-loop/source-witness-input-envelope/v1",
                "partition_manifest_digest": sha256_json(partition_manifest),
                "authority_snapshot_digest": sha256_json(source_bundle),
                "lane_id": lane_id,
                "source_clause_ids": sorted(package["source_clause_ids"]),
                "source_slice_ids": sorted(package["source_slice_ids"]),
            }
            if package["visibility"]["input_envelope_digest"] != sha256_json(
                source_envelope
            ):
                raise CorridorKitError(
                    f"witness lane {lane_id} input envelope digest is not reproducible"
                )
        for binding in rule_lane_bindings:
            lane = partition_lane_by_id[binding["lane_id"]]
            accessible_clauses = set(lane["owner_clause_ids"]) | set(
                lane["boundary_clause_ids"]
            )
            for rule_id in binding["rule_ids"]:
                rule = rule_by_id[rule_id]
                if not set(rule["source_clause_ids"]).issubset(accessible_clauses):
                    raise CorridorKitError(
                        f"Rule {rule_id} escapes its source lane envelope"
                    )
                if not set(rule["source_clause_ids"]).intersection(
                    lane["owner_clause_ids"]
                ):
                    raise CorridorKitError(
                        f"Rule {rule_id} has no owned source clause in its lane"
                    )
                package = witness_lane_by_id[binding["lane_id"]]
                matching_witnesses = [
                    witness
                    for witness in package["witnesses"]
                    if set(witness["source_clause_ids"]).intersection(
                        rule["source_clause_ids"]
                    )
                ]
                for condition in rule["semantics"]["conditions"]:
                    predicate = condition["predicate_spec"]
                    unknown_predicate_rule_refs = sorted(
                        (
                            set(predicate["precondition_rule_ids"])
                            | set(predicate["dependency_refs"])
                        )
                        - rule_ids
                    )
                    if unknown_predicate_rule_refs:
                        v5_integration_issues.append(
                            {
                                "lane_id": binding["lane_id"],
                                "rule_id": rule_id,
                                "condition_id": condition["condition_id"],
                                "error_type": "typed_predicate_dangling_rule_ref",
                                "unknown_rule_refs": unknown_predicate_rule_refs,
                            }
                        )
                    witnesses = [
                        witness
                        for witness in matching_witnesses
                        if witness["operator"] == predicate["operator"]
                    ]
                    kinds = {witness["kind"] for witness in witnesses}
                    if kinds != SOURCE_WITNESS_KINDS:
                        v5_integration_issues.append(
                            {
                                "lane_id": binding["lane_id"],
                                "rule_id": rule_id,
                                "condition_id": condition["condition_id"],
                                "error_type": "source_witness_partition_gap",
                                "missing_witness_kinds": sorted(
                                    SOURCE_WITNESS_KINDS - kinds
                                ),
                            }
                        )
                    source_witness_bindings.append(
                        {
                            "lane_id": binding["lane_id"],
                            "rule_id": rule_id,
                            "condition_id": condition["condition_id"],
                            "predicate_id": predicate["predicate_id"],
                            "predicate_digest": sha256_json(predicate),
                            "source_witness_refs": sorted(
                                witness["witness_ref"] for witness in witnesses
                            ),
                            "source_witness_digest": sha256_json(witnesses),
                        }
                    )
                quantifier = rule["semantics"]["quantifier"]
                applicability = rule["semantics"]["applicability"]
                witness_domain_kinds = {
                    witness["input_case"].get("domain_kind")
                    for witness in matching_witnesses
                    if isinstance(witness["input_case"].get("domain_kind"), str)
                }
                if witness_domain_kinds and witness_domain_kinds != {
                    quantifier["domain_kind"]
                }:
                    v5_integration_issues.append(
                        {
                            "lane_id": binding["lane_id"],
                            "rule_id": rule_id,
                            "error_type": "source_witness_domain_mismatch",
                            "rule_domain_kind": quantifier["domain_kind"],
                            "source_witness_domain_kinds": sorted(
                                witness_domain_kinds
                            ),
                        }
                    )
                if (
                    quantifier["domain_kind"] == "closed_enumeration"
                    and applicability["mode"] == "conditional"
                ):
                    for subject_id in quantifier["subjects"]:
                        subject_kinds = {
                            witness["kind"]
                            for witness in matching_witnesses
                            if witness["input_case"].get("subject_id") == subject_id
                        }
                        missing_classifications = {
                            "positive",
                            "negative",
                        } - subject_kinds
                        if missing_classifications:
                            v5_integration_issues.append(
                                {
                                    "lane_id": binding["lane_id"],
                                    "rule_id": rule_id,
                                    "subject_id": subject_id,
                                    "error_type": "closed_domain_classification_gap",
                                    "missing_witness_kinds": sorted(
                                        missing_classifications
                                    ),
                                }
                            )

    if is_byte_bound:
        assert source_bundle is not None
        source_by_id = {
            source["source_id"]: source for source in source_bundle["sources"]
        }
        clause_by_id = {clause["clause_id"]: clause for clause in source_clauses}
        slice_by_id = {
            source_slice["slice_id"]: source_slice
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        clause_ids_by_slice = {
            source_slice["slice_id"]: clause["clause_id"]
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        for clause in source_clauses:
            unknown_rule_ids = sorted(set(clause["rule_ids"]) - rule_ids)
            if unknown_rule_ids:
                raise CorridorKitError(
                    f"source clause references unknown Rules: {unknown_rule_ids}"
                )
        inventoried_source_ids = {
            source_slice["source_id"]
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        missing_source_inventories = sorted(
            source["source_id"]
            for source in source_bundle["sources"]
            if source.get("retrieval_status", source.get("byte_status")) == "available"
            and (not (is_v4 or is_v5) or source.get("plane") == "normative_rule")
            and source["source_id"] not in inventoried_source_ids
        )
        if missing_source_inventories:
            raise CorridorKitError(
                "available task sources lack byte-addressed clause inventory entries: "
                + ", ".join(missing_source_inventories)
            )
        bindings_by_rule = {
            rule["rule_id"]: rule["source_slices"] for rule in normalized_rules
        }
        for rule in normalized_rules:
            clause_ids = rule["source_clause_ids"]
            unknown_clause_ids = sorted(set(clause_ids) - set(clause_by_id))
            if unknown_clause_ids:
                raise CorridorKitError(
                    f"typed Rule references unknown source clauses: {unknown_clause_ids}"
                )
            mapped_clause_ids = sorted(
                clause["clause_id"]
                for clause in source_clauses
                if rule["rule_id"] in clause["rule_ids"]
            )
            if sorted(clause_ids) != mapped_clause_ids:
                raise CorridorKitError(
                    f"typed Rule source_clause_ids do not match clause inventory: {rule['rule_id']}"
                )
            bound_slice_ids = {item["slice_id"] for item in rule["source_slices"]}
            unknown_slice_ids = sorted(bound_slice_ids - set(slice_by_id))
            if unknown_slice_ids:
                raise CorridorKitError(
                    f"typed Rule references unknown source slices: {unknown_slice_ids}"
                )
            outside_clause_slices = sorted(
                slice_id
                for slice_id in bound_slice_ids
                if clause_ids_by_slice[slice_id] not in set(clause_ids)
            )
            if outside_clause_slices:
                raise CorridorKitError(
                    f"typed Rule source slices fall outside its mapped clauses: {outside_clause_slices}"
                )
            clause_levels = {
                clause_by_id[clause_id]["requirement_level"]
                for clause_id in clause_ids
            }
            if clause_levels != {rule["semantics"]["requirement_level"]}:
                raise CorridorKitError(
                    f"typed Rule requirement level does not match its source clauses: {rule['rule_id']}"
                )
        for clause in source_clauses:
            if clause["mapping_status"] != "mapped":
                continue
            declared_roles = {
                binding["semantic_role"]
                for rule_id in clause["rule_ids"]
                for binding in bindings_by_rule[rule_id]
                if clause_ids_by_slice.get(binding["slice_id"]) == clause["clause_id"]
            }
            missing_roles = sorted(
                set(clause["required_semantic_roles"]) - declared_roles
            )
            if missing_roles and not (is_v4 or is_v5):
                raise CorridorKitError(
                    f"source clause semantic roles are not mapped: {clause['clause_id']}:{missing_roles}"
                )
        for dependency in rule_dependency_templates:
            provenance = dependency["edge_provenance"]
            source_rule_id = dependency["from_rule_id"]
            target_rule_id = dependency["to_rule_id"]
            if provenance["kind"] == "direct":
                endpoint_bindings = {
                    binding["slice_id"]
                    for endpoint in (source_rule_id, target_rule_id)
                    for binding in bindings_by_rule.get(endpoint, [])
                    if binding["semantic_role"] == "relationship"
                }
                invalid_slices = sorted(
                    set(provenance["source_slice_ids"]) - endpoint_bindings
                )
                if invalid_slices:
                    raise CorridorKitError(
                        "direct dependency provenance must bind relationship slices "
                        f"from an endpoint Rule: {invalid_slices}"
                    )
            else:
                expected_endpoint_digests = {
                    endpoint: rule_provenance_digest_by_id[endpoint]
                    for endpoint in (source_rule_id, target_rule_id)
                    if endpoint in rule_provenance_digest_by_id
                }
                if provenance["input_rule_provenance_digests"] != expected_endpoint_digests:
                    raise CorridorKitError(
                        "derived dependency provenance must bind both current endpoint Rule revisions"
                    )

    if is_v2:
        assert source_bundle is not None
        source_by_id = {
            source["source_id"]: source for source in source_bundle["sources"]
        }
        clause_by_id = {clause["clause_id"]: clause for clause in source_clauses}
        for clause in source_clauses:
            if clause["source_id"] not in source_by_id:
                raise CorridorKitError(
                    f"source clause references unknown source: {clause['clause_id']}"
                )
            unknown_rule_ids = sorted(set(clause["rule_ids"]) - rule_ids)
            if unknown_rule_ids:
                raise CorridorKitError(
                    f"source clause references unknown Rules: {unknown_rule_ids}"
                )
        inventoried_source_ids = {clause["source_id"] for clause in source_clauses}
        missing_source_inventories = sorted(
            source["source_id"]
            for source in source_bundle["sources"]
            if source["retrieval_status"] == "available"
            and source["source_id"] not in inventoried_source_ids
        )
        if missing_source_inventories:
            raise CorridorKitError(
                "available task sources lack clause inventory entries: "
                + ", ".join(missing_source_inventories)
            )
        for rule in normalized_rules:
            clause_ids = rule["source_clause_ids"]
            unknown_clause_ids = sorted(set(clause_ids) - set(clause_by_id))
            if unknown_clause_ids:
                raise CorridorKitError(
                    f"typed Rule references unknown source clauses: {unknown_clause_ids}"
                )
            mapped_clause_ids = sorted(
                clause["clause_id"]
                for clause in source_clauses
                if rule["rule_id"] in clause["rule_ids"]
            )
            if sorted(clause_ids) != mapped_clause_ids:
                raise CorridorKitError(
                    f"typed Rule source_clause_ids do not match clause inventory: {rule['rule_id']}"
                )
            clause_sources = {
                source_by_id[clause_by_id[clause_id]["source_id"]]["source_ref"]
                for clause_id in clause_ids
            }
            clause_digests = {
                source_by_id[clause_by_id[clause_id]["source_id"]]["source_digest"]
                for clause_id in clause_ids
            }
            if clause_sources != {rule["source_ref"]} or clause_digests != {
                rule["source_digest"]
            }:
                raise CorridorKitError(
                    f"typed Rule source identity does not match its source clauses: {rule['rule_id']}"
                )
            clause_levels = {
                clause_by_id[clause_id]["requirement_level"]
                for clause_id in clause_ids
            }
            if clause_levels != {rule["semantics"]["requirement_level"]}:
                raise CorridorKitError(
                    f"typed Rule requirement level does not match its source clauses: {rule['rule_id']}"
                )

    reverse_semantic_projection: list[dict[str, Any]] = []
    semantic_delta: list[dict[str, Any]] = []
    unaccounted_normative_ranges: list[dict[str, Any]] = []
    mapping_matrix: list[dict[str, Any]] = []
    if is_v4 or is_v5:
        assert source_bundle is not None
        slice_index = {
            source_slice["slice_id"]: (clause, source_slice)
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        for rule in normalized_rules:
            bound_roles = {item["semantic_role"] for item in rule["source_slices"]}
            required_roles = _required_semantic_roles(rule["semantics"])
            missing_roles = sorted(required_roles - bound_roles)
            extra_roles = sorted(bound_roles - required_roles)
            guidance_slice_ids = {
                slice_id
                for guidance in rule["semantics"]["guidance"]
                for slice_id in guidance["source_slice_ids"]
            }
            unknown_guidance_slices = sorted(
                guidance_slice_ids - {item["slice_id"] for item in rule["source_slices"]}
            )
            if missing_roles or unknown_guidance_slices:
                semantic_delta.append(
                    {
                        "rule_id": rule["rule_id"],
                        "missing_semantic_roles": missing_roles,
                        "extra_semantic_roles": extra_roles,
                        "unknown_guidance_slice_ids": unknown_guidance_slices,
                    }
                )
            reverse_semantic_projection.append(
                {
                    "rule_id": rule["rule_id"],
                    "candidate_revision_id": revision["revision_id"],
                    "source_bindings": [
                        {
                            **binding,
                            "clause_id": slice_index[binding["slice_id"]][0]["clause_id"],
                            "source_id": slice_index[binding["slice_id"]][1]["source_id"],
                            "byte_start": slice_index[binding["slice_id"]][1]["byte_start"],
                            "byte_end": slice_index[binding["slice_id"]][1]["byte_end"],
                            "slice_digest": slice_index[binding["slice_id"]][1]["slice_digest"],
                        }
                        for binding in rule["source_slices"]
                    ],
                    "required_semantic_roles": sorted(required_roles),
                    "bound_semantic_roles": sorted(bound_roles),
                    "projection_digest": sha256_json(
                        {
                            "rule_id": rule["rule_id"],
                            "source_slices": rule["source_slices"],
                            "semantics": rule["semantics"],
                        }
                    ),
                }
            )
        mapping_matrix = [
            {
                "clause_id": clause["clause_id"],
                "rule_ids": list(clause["rule_ids"]),
                "mapping_status": clause["mapping_status"],
            }
            for clause in source_clauses
        ]
        unaccounted_normative_ranges = _unaccounted_normative_ranges(
            source_bundle=source_bundle, source_clauses=source_clauses
        )

    dangling = sorted(
        {
            item["to_rule_id"]
            for item in rule_dependency_templates
            if item["to_rule_id"] not in rule_ids
        }
    )
    if dangling:
        raise CorridorKitError(
            f"typed Rule dependencies reference unknown Rules: {dangling}"
        )
    for item in rule_dependency_templates:
        if item["from_rule_id"] == item["to_rule_id"]:
            raise CorridorKitError("typed Rule dependency cannot be self-referential")
        if is_byte_bound:
            item.update(
                {
                    "source_rule_provenance_digest": rule_provenance_digest_by_id[
                        item["from_rule_id"]
                    ],
                    "target_rule_provenance_digest": rule_provenance_digest_by_id[
                        item["to_rule_id"]
                    ],
                }
            )
    hard_edges: dict[str, set[str]] = {rule_id: set() for rule_id in rule_ids}
    for item in rule_dependency_templates:
        relationship = item["relationship"]
        if relationship == "requires":
            hard_edges[item["from_rule_id"]].add(item["to_rule_id"])
        elif relationship in {"precondition_for", "precedes"}:
            hard_edges[item["to_rule_id"]].add(item["from_rule_id"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(rule_id: str) -> None:
        if rule_id in visiting:
            raise CorridorKitError("typed Rule hard dependency graph contains a cycle")
        if rule_id in visited:
            return
        visiting.add(rule_id)
        for prerequisite in hard_edges[rule_id]:
            visit(prerequisite)
        visiting.remove(rule_id)
        visited.add(rule_id)

    for rule_id in sorted(rule_ids):
        visit(rule_id)

    work_relationships = {
        "requires": "requires",
        "precondition_for": "precondition_for",
        "precedes": "precondition_for",
        "invalidates": "invalidates",
        "conflicts": "conflicts",
    }
    typed_dependency_templates: list[dict[str, Any]] = []
    relationship_alignment_issues: list[dict[str, Any]] = []
    for dependency in rule_dependency_templates:
        graph_relationship = work_relationships.get(dependency["relationship"])
        if graph_relationship is None:
            continue
        source_cells = checklist_templates_by_rule[dependency["from_rule_id"]]
        target_cells = checklist_templates_by_rule[dependency["to_rule_id"]]
        if is_v4 or is_v5:
            aligned_pairs, issues = _project_aligned_dependency(
                dependency=dependency,
                source_cells=source_cells,
                target_cells=target_cells,
            )
            if issues:
                relationship_alignment_issues.append(
                    {
                        "from_rule_id": dependency["from_rule_id"],
                        "to_rule_id": dependency["to_rule_id"],
                        "relationship": dependency["relationship"],
                        "issues": issues,
                    }
                )
        else:
            # Preserved only for legacy schemas.  New v4 candidates can never
            # obtain checklist edges from an undeclared Cartesian product.
            aligned_pairs = [
                (source_cell, target_cell)
                for source_cell in source_cells
                for target_cell in target_cells
            ]
        for source_cell, target_cell in aligned_pairs:
                identity = {
                    "from_ref": source_cell["checklist_item_id"],
                    "to_ref": target_cell["checklist_item_id"],
                    "relationship": graph_relationship,
                    "source_rule_id": dependency["from_rule_id"],
                    **(
                        {
                            "target_rule_id": dependency["to_rule_id"],
                            "source_rule_provenance_digest": dependency[
                                "source_rule_provenance_digest"
                            ],
                            "target_rule_provenance_digest": dependency[
                                "target_rule_provenance_digest"
                            ],
                            "edge_provenance": dependency["edge_provenance"],
                            **(
                                {
                                    "relationship_alignment": dependency[
                                        "relationship_alignment"
                                    ]
                                }
                                if is_v4 or is_v5
                                else {}
                            ),
                        }
                        if is_byte_bound
                        else {}
                    ),
                }
                typed_dependency_templates.append(
                    {
                        "dependency_id": f"DEP-{sha256_json(identity)[7:23]}",
                        "dependency_kind": "work",
                        **identity,
                    }
                )

    semantic_edge_templates: list[dict[str, Any]] = []
    if is_v4 or is_v5:
        checklist_ids_by_rule = {
            rule_id: sorted(
                item["checklist_item_id"]
                for item in checklist_templates_by_rule[rule_id]
            )
            for rule_id in sorted(checklist_templates_by_rule)
        }
        obligation_ids_by_rule = {
            rule_id: sorted(
                item["witness_obligation_id"]
                for item in witness_obligation_templates
                if item["rule_id"] == rule_id
            )
            for rule_id in sorted(checklist_templates_by_rule)
        }
        rule_semantics_by_id = {
            rule["rule_id"]: rule["semantics"] for rule in normalized_rules
        }
        slice_details = {
            source_slice["slice_id"]: {
                "slice_id": source_slice["slice_id"],
                "clause_id": clause["clause_id"],
                "source_id": source_slice["source_id"],
                "representation": source_slice["representation"],
                "byte_start": source_slice["byte_start"],
                "byte_end": source_slice["byte_end"],
                "slice_digest": source_slice["slice_digest"],
            }
            for clause in source_clauses
            for source_slice in clause["source_slices"]
        }
        for dependency in rule_dependency_templates:
            from_rule_id = dependency["from_rule_id"]
            to_rule_id = dependency["to_rule_id"]
            provenance = dependency["edge_provenance"]
            source_slice_ids = list(provenance["source_slice_ids"])
            declared_relationship = dependency["relationship"]
            projected_relationship = work_relationships.get(declared_relationship)
            typed_expansion_ids = sorted(
                item["dependency_id"]
                for item in typed_dependency_templates
                if item["source_rule_id"] == from_rule_id
                and item.get("target_rule_id") == to_rule_id
                and item["relationship"] == projected_relationship
            )
            semantic_edge_templates.append(
                {
                    "schema_version": SEMANTIC_EDGE_TEMPLATE_SCHEMA,
                    "semantic_edge_id": semantic_edge_id(
                        from_rule_id=from_rule_id,
                        to_rule_id=to_rule_id,
                        declared_relationship=declared_relationship,
                    ),
                    "from_rule_id": from_rule_id,
                    "to_rule_id": to_rule_id,
                    "declared_relationship": declared_relationship,
                    "relationship_alignment": dependency["relationship_alignment"],
                    "edge_provenance": provenance,
                    "relationship_expectation_status": (
                        "source_bound"
                        if provenance["kind"] == "direct" and source_slice_ids
                        else "unresolved"
                    ),
                    "relationship_source_bindings": [
                        slice_details[slice_id]
                        for slice_id in source_slice_ids
                    ],
                    "relationship_derivation_inputs": dict(
                        provenance["input_rule_provenance_digests"]
                    ),
                    "endpoint_condition_kinds": {
                        from_rule_id: sorted(
                            {
                                condition["condition_kind"]
                                for condition in rule_semantics_by_id[from_rule_id][
                                    "conditions"
                                ]
                            }
                        ),
                        to_rule_id: sorted(
                            {
                                condition["condition_kind"]
                                for condition in rule_semantics_by_id[to_rule_id][
                                    "conditions"
                                ]
                            }
                        ),
                    },
                    "endpoint_checklist_item_ids": {
                        from_rule_id: checklist_ids_by_rule[from_rule_id],
                        to_rule_id: checklist_ids_by_rule[to_rule_id],
                    },
                    "endpoint_witness_obligation_ids": {
                        from_rule_id: obligation_ids_by_rule[from_rule_id],
                        to_rule_id: obligation_ids_by_rule[to_rule_id],
                    },
                    "typed_expansion_ids": typed_expansion_ids,
                }
            )

    normalized_predicates = sorted(
        (
            {
                "rule_id": rule["rule_id"],
                "condition_id": condition["condition_id"],
                "predicate_spec": condition["predicate_spec"],
            }
            for rule in normalized_rules
            for condition in rule["semantics"]["conditions"]
            if "predicate_spec" in condition
        ),
        key=lambda item: (item["rule_id"], item["condition_id"]),
    )
    operator_signatures: dict[str, set[tuple[tuple[str, ...], tuple[str, ...]]]] = {}
    for item in normalized_predicates:
        predicate = item["predicate_spec"]
        operator_signatures.setdefault(predicate["operator"], set()).add(
            (
                tuple(variable["value_type"] for variable in predicate["inputs"]),
                tuple(variable["value_type"] for variable in predicate["outputs"]),
            )
        )
    operator_schema = [
        {
            "operator": operator,
            "signatures": [
                {"input_types": list(inputs), "output_types": list(outputs)}
                for inputs, outputs in sorted(signatures)
            ],
        }
        for operator, signatures in sorted(operator_signatures.items())
    ]
    if is_v5:
        for operator, signatures in sorted(operator_signatures.items()):
            if len(signatures) > 1:
                v5_integration_issues.append(
                    {
                        "operator": operator,
                        "error_type": "typed_operator_signature_conflict",
                        "signature_count": len(signatures),
                    }
                )
    hard_dependency_closure: dict[str, list[str]] = {}
    for rule_id in sorted(rule_ids):
        reachable: set[str] = set()
        pending = list(hard_edges[rule_id])
        while pending:
            prerequisite = pending.pop()
            if prerequisite in reachable:
                continue
            reachable.add(prerequisite)
            pending.extend(hard_edges[prerequisite])
        hard_dependency_closure[rule_id] = sorted(reachable)

    lane_packages: list[dict[str, Any]] = []
    integrator_manifest: dict[str, Any] | None = None
    if is_v5:
        assert partition_manifest is not None
        binding_by_lane = {
            item["lane_id"]: item for item in rule_lane_bindings
        }
        witness_by_lane = {
            item["lane_id"]: item for item in witness_lane_packages
        }
        lane_by_rule = {
            rule_id: binding["lane_id"]
            for binding in rule_lane_bindings
            for rule_id in binding["rule_ids"]
        }
        raw_cross_lane_edges = sorted(
            (
                {
                    "semantic_edge_id": item["semantic_edge_id"],
                    "from_rule_id": item["from_rule_id"],
                    "to_rule_id": item["to_rule_id"],
                    "from_lane_id": lane_by_rule[item["from_rule_id"]],
                    "to_lane_id": lane_by_rule[item["to_rule_id"]],
                    "relationship": item["declared_relationship"],
                }
                for item in semantic_edge_templates
                if lane_by_rule[item["from_rule_id"]]
                != lane_by_rule[item["to_rule_id"]]
            ),
            key=lambda item: item["semantic_edge_id"],
        )
        dependency_stubs = partition_manifest["dependency_stubs"]
        matched_stub_refs: set[str] = set()
        cross_lane_edges: list[dict[str, Any]] = []
        for edge in raw_cross_lane_edges:
            from_rule_clauses = set(
                rule_by_id[edge["from_rule_id"]]["source_clause_ids"]
            )
            to_rule_clauses = set(
                rule_by_id[edge["to_rule_id"]]["source_clause_ids"]
            )
            structural_matches = [
                stub
                for stub in dependency_stubs
                if stub["from_lane_id"] == edge["from_lane_id"]
                and stub["to_lane_id"] == edge["to_lane_id"]
                and bool(set(stub["from_clause_ids"]) & from_rule_clauses)
                and bool(set(stub["to_clause_ids"]) & to_rule_clauses)
            ]
            matches = [
                stub
                for stub in structural_matches
                if stub["relationship"] == edge["relationship"]
            ]
            if len(matches) != 1:
                v5_integration_issues.append(
                    {
                        "semantic_edge_id": edge["semantic_edge_id"],
                        "error_type": (
                            "cross_lane_dependency_stub_ambiguous"
                            if len(matches) > 1
                            else "cross_lane_dependency_relationship_mismatch"
                            if structural_matches
                            else "cross_lane_dependency_stub_missing"
                        ),
                        "source_dependency_refs": sorted(
                            stub["dependency_ref"] for stub in structural_matches
                        ),
                    }
                )
                cross_lane_edges.append({**edge, "source_dependency_ref": None})
                continue
            dependency_ref = matches[0]["dependency_ref"]
            matched_stub_refs.add(dependency_ref)
            cross_lane_edges.append(
                {**edge, "source_dependency_ref": dependency_ref}
            )
        for dependency_ref in sorted(
            {stub["dependency_ref"] for stub in dependency_stubs}
            - matched_stub_refs
        ):
            v5_integration_issues.append(
                {
                    "source_dependency_ref": dependency_ref,
                    "error_type": "source_dependency_stub_without_rule_edge",
                }
            )
        for lane in partition_manifest["lanes"]:
            lane_id = lane["lane_id"]
            binding = binding_by_lane[lane_id]
            lane_rules = [
                rule_by_id[rule_id] for rule_id in binding["rule_ids"]
            ]
            lane_witness = witness_by_lane[lane_id]
            incident_edges = [
                item
                for item in cross_lane_edges
                if lane_id in {item["from_lane_id"], item["to_lane_id"]}
            ]
            lane_package = {
                "lane_id": lane_id,
                "rule_ids": sorted(binding["rule_ids"]),
                "source_partition_digest": sha256_json(lane),
                "rule_package_digest": sha256_json(lane_rules),
                "witness_package_digest": sha256_json(lane_witness),
                "source_witness_binding_digest": sha256_json(
                    [
                        item
                        for item in source_witness_bindings
                        if item["lane_id"] == lane_id
                    ]
                ),
                "incident_cross_lane_edges": incident_edges,
            }
            lane_packages.append(
                {**lane_package, "lane_package_digest": sha256_json(lane_package)}
            )
        lane_packages.sort(key=lambda item: item["lane_id"])
        integrator_body = {
            "schema_version": INTEGRATOR_MANIFEST_SCHEMA,
            "partition_manifest_digest": sha256_json(partition_manifest),
            "lane_packages_digest": sha256_json(lane_packages),
            "normalized_predicate_digest": sha256_json(normalized_predicates),
            "operator_schema_digest": sha256_json(operator_schema),
            "source_witness_set_digest": sha256_json(witness_lane_packages),
            "source_witness_bindings_digest": sha256_json(source_witness_bindings),
            "dependency_closure_digest": sha256_json(hard_dependency_closure),
            "cross_lane_edges_digest": sha256_json(cross_lane_edges),
            "source_dependency_stubs_digest": sha256_json(dependency_stubs),
            "boundary_clause_ids": sorted(
                {
                    clause_id
                    for lane in partition_manifest["lanes"]
                    for clause_id in lane["boundary_clause_ids"]
                }
            ),
            "unresolved_clause_ids": list(
                partition_manifest["unresolved_clause_ids"]
            ),
            "integration_issues": v5_integration_issues,
            "whole_ledger_status": (
                "complete"
                if not v5_integration_issues
                and not partition_manifest["unresolved_clause_ids"]
                else "incomplete"
            ),
        }
        integrator_manifest = {
            **integrator_body,
            "integrator_digest": sha256_json(integrator_body),
        }

    normalized_ir = (
        {
            "schema_version": (
                TYPED_RULE_IR_SCHEMA_V5
                if is_v5
                else TYPED_RULE_IR_SCHEMA_V4
                if is_v4
                else TYPED_RULE_IR_SCHEMA_V3
                if is_v3
                else TYPED_RULE_IR_SCHEMA
            ),
            "source_bundle": source_bundle,
            "source_clause_inventory": source_clauses,
            "revision": revision,
            "method_digest": method_digest,
            "compiler_config_digest": compiler_config_digest,
            **(
                {
                    "partition_manifest": partition_manifest,
                    "rule_lane_bindings": rule_lane_bindings,
                    "witness_lane_packages": witness_lane_packages,
                }
                if is_v5
                else {}
            ),
            "rules": normalized_rules,
        }
        if is_source_bound
        else {
            "schema_version": TYPED_RULE_IR_SCHEMA_V1,
            "task_source_ref": task_source_ref,
            "task_source_digest": task_source_digest,
            "method_digest": method_digest,
            "compiler_config_digest": compiler_config_digest,
            "rules": normalized_rules,
        }
    )
    ir_digest = sha256_json(normalized_ir)
    if revision is not None and revision["parent_ir_digest"] == ir_digest:
        raise CorridorKitError("typed Rule IR revision cannot name itself as parent")
    implementation_digest = _compiler_implementation_digest()
    manifest = {
        "schema_version": (
            COMPILE_PROBE_MANIFEST_SCHEMA_V5
            if is_v5
            else COMPILE_PROBE_MANIFEST_SCHEMA_V4
            if is_v4
            else COMPILE_PROBE_MANIFEST_SCHEMA_V3
            if is_v3
            else COMPILE_PROBE_MANIFEST_SCHEMA
            if is_v2
            else COMPILE_PROBE_MANIFEST_SCHEMA_V1
        ),
        "run_classification": run_classification,
        "task_source_ref": task_source_ref,
        "task_source_digest": task_source_digest,
        **(
            {
                "task_source_bundle_digest": sha256_json(source_bundle),
                "source_clause_inventory_digest": sha256_json(source_clauses),
                "source_bundle_closure_status": source_bundle["closure_status"],
                "revision": revision,
                **(
                    {
                        "authority_snapshot_manifest_digest": source_bundle[
                            "manifest_digest"
                        ]
                    }
                    if is_v4 or is_v5
                    else {}
                ),
            }
            if is_source_bound
            else {"source_closure_assessed": False}
        ),
        "method_digest": method_digest,
        "compiler_config_digest": compiler_config_digest,
        "compiler_implementation_digest": implementation_digest,
        "typed_rule_ir_digest": ir_digest,
        "input_policy": {
            "allowed": [
                "frozen_method",
                (
                    "closed_public_task_source_bundle"
                    if is_source_bound
                    else "public_task_source"
                ),
                "compiler_interface",
                *(
                    ["independent_source_qa"]
                    if revision is not None
                    and revision["revision_kind"] == "semantic_repair"
                    else []
                ),
            ],
            "forbidden": [
                "task_solution",
                "task_tests",
                "historical_task_graph",
                "official_verifier_output",
                "prior_task_result",
                "prior_task_transcript",
                "hidden_evaluator_material",
                "task_specific_hint",
                *(
                    ["independent_source_qa"]
                    if revision is not None
                    and revision["revision_kind"] == "first_attempt"
                    else []
                ),
            ],
        },
        "fresh_efficacy_or_transfer_claim_allowed": (
            run_classification == "fresh_task_pre_experiment"
        ),
    }
    manifest["manifest_digest"] = sha256_json(manifest)
    rules_complete = all(
        rule["semantics"]["compilation_status"] == "complete"
        for rule in normalized_rules
    )
    source_clauses_complete = (
        all(clause["mapping_status"] == "mapped" for clause in source_clauses)
        if is_source_bound
        else None
    )
    compilation_complete = (
        rules_complete
        and source_bundle is not None
        and source_bundle["closure_status"] == "complete"
        and source_clauses_complete is True
        if is_source_bound
        else rules_complete
    )
    if is_v4 or is_v5:
        compilation_complete = bool(
            compilation_complete
            and not semantic_delta
            and not unaccounted_normative_ranges
            and not relationship_alignment_issues
            and (not is_v5 or not v5_integration_issues)
            and (
                not is_v5
                or partition_manifest is not None
                and not partition_manifest["unresolved_clause_ids"]
            )
        )
    rule_compile_issues = [
        {
            "rule_id": rule["rule_id"],
            "status": rule["semantics"]["compilation_status"],
            "issues": rule["semantics"]["compile_issues"],
        }
        for rule in normalized_rules
        if rule["semantics"]["compilation_status"] != "complete"
    ]
    source_clause_issues = (
        [
            {
                "clause_id": clause["clause_id"],
                "status": clause["mapping_status"],
                "issues": [clause["issue"]],
            }
            for clause in source_clauses
            if clause["mapping_status"] != "mapped"
        ]
        if is_source_bound
        else []
    )
    successor_issues = (
        [
            {
                "status": "incomplete",
                "issues": ["reverse_semantic_projection_mismatch"],
                "semantic_delta": semantic_delta,
            }
        ]
        if semantic_delta
        else []
    )
    if unaccounted_normative_ranges:
        successor_issues.append(
            {
                "status": "incomplete",
                "issues": ["unaccounted_normative_bytes"],
                "ranges": unaccounted_normative_ranges,
            }
        )
    if relationship_alignment_issues:
        successor_issues.append(
            {
                "status": "incomplete",
                "issues": ["relationship_alignment_mismatch"],
                "relationships": relationship_alignment_issues,
            }
        )
    if v5_integration_issues:
        successor_issues.append(
            {
                "status": "incomplete",
                "issues": ["parallel_lane_integration_mismatch"],
                "lane_findings": v5_integration_issues,
            }
        )
    report = {
        "schema_version": (
            TYPED_RULE_COMPILATION_SCHEMA_V5
            if is_v5
            else TYPED_RULE_COMPILATION_SCHEMA_V4
            if is_v4
            else TYPED_RULE_COMPILATION_SCHEMA_V3
            if is_v3
            else TYPED_RULE_COMPILATION_SCHEMA
            if is_v2
            else TYPED_RULE_COMPILATION_SCHEMA_V1
        ),
        "ok": True,
        "compilation_complete": compilation_complete,
        "compile_issues": [
            *rule_compile_issues,
            *source_clause_issues,
            *successor_issues,
        ],
        "source_closure_assessed": is_source_bound,
        "source_closure": (
            {
                "bundle_status": source_bundle["closure_status"],
                "clause_inventory_complete": source_clauses_complete,
                "source_count": len(source_bundle["sources"]),
                "clause_count": len(source_clauses),
                "mapped_clause_count": sum(
                    clause["mapping_status"] == "mapped"
                    for clause in source_clauses
                ),
                "source_slice_count": (
                    sum(len(clause["source_slices"]) for clause in source_clauses)
                    if is_byte_bound
                    else None
                ),
                "source_provenance_status": (
                    "authority_snapshot_with_exact_byte_slices"
                    if is_v4 or is_v5
                    else "exact_byte_slices"
                    if is_v3
                    else "legacy_clause_text"
                ),
            }
            if is_source_bound
            else {
                "bundle_status": "legacy_unassessed",
                "clause_inventory_complete": None,
                "source_count": None,
                "clause_count": None,
                "mapped_clause_count": None,
                "source_slice_count": None,
                "source_provenance_status": "legacy_unassessed",
            }
        ),
        "revision": revision,
        "typed_rule_ir_digest": ir_digest,
        "candidate_revision_digest": (
            sha256_json({"revision": revision, "typed_rule_ir_digest": ir_digest})
            if is_v4 or is_v5
            else None
        ),
        "authority_snapshot_digest": (
            sha256_json(source_bundle)
            if (is_v4 or is_v5) and source_bundle is not None
            else None
        ),
        "reverse_semantic_projection": reverse_semantic_projection,
        "reverse_semantic_projection_digest": (
            sha256_json(reverse_semantic_projection) if is_v4 or is_v5 else None
        ),
        "semantic_delta": semantic_delta,
        "semantic_delta_digest": (
            sha256_json(semantic_delta) if is_v4 or is_v5 else None
        ),
        "semantic_edge_templates": semantic_edge_templates,
        "semantic_edge_templates_digest": (
            sha256_json(semantic_edge_templates) if is_v4 or is_v5 else None
        ),
        "witness_obligation_templates": witness_obligation_templates,
        "witness_obligation_templates_digest": sha256_json(
            witness_obligation_templates
        ),
        "normalized_predicates": normalized_predicates,
        "normalized_predicate_digest": (
            sha256_json(normalized_predicates) if is_v5 else None
        ),
        "operator_schema": operator_schema,
        "operator_schema_digest": sha256_json(operator_schema) if is_v5 else None,
        "source_witness_bindings": source_witness_bindings,
        "source_witness_set_digest": (
            sha256_json(witness_lane_packages) if is_v5 else None
        ),
        "source_witness_bindings_digest": (
            sha256_json(source_witness_bindings) if is_v5 else None
        ),
        "hard_dependency_closure": hard_dependency_closure,
        "dependency_closure_digest": (
            sha256_json(hard_dependency_closure) if is_v5 else None
        ),
        "partition_manifest": partition_manifest,
        "partition_manifest_digest": (
            sha256_json(partition_manifest) if is_v5 else None
        ),
        "lane_packages": lane_packages,
        "lane_packages_digest": sha256_json(lane_packages) if is_v5 else None,
        "integrator_manifest": integrator_manifest,
        "integrator_digest": (
            integrator_manifest["integrator_digest"]
            if integrator_manifest is not None
            else None
        ),
        "parallel_lane_integration_issues": v5_integration_issues,
        "source_clause_rule_matrix": mapping_matrix,
        "unaccounted_normative_ranges": unaccounted_normative_ranges,
        "relationship_alignment_issues": relationship_alignment_issues,
        "compiler_implementation_digest": implementation_digest,
        "rule_count": len(rule_bodies),
        "coverage_cell_count": len(checklist_templates),
        "rule_dependency_count": len(rule_dependency_templates),
        "typed_dependency_count": len(typed_dependency_templates),
        "rule_bodies": rule_bodies,
        "authority_snapshot_template": (
            source_bundle if (is_v4 or is_v5) and source_bundle is not None else None
        ),
        "normalized_typed_rule_ir": normalized_ir if is_v4 or is_v5 else None,
        "source_artifact_templates": (
            source_bundle["sources"] if is_byte_bound and source_bundle is not None else []
        ),
        "source_clause_templates": source_clauses if is_byte_bound else [],
        "checklist_templates": checklist_templates,
        "rule_dependency_templates": rule_dependency_templates,
        "typed_dependency_templates": typed_dependency_templates,
        "compile_probe_manifest": manifest,
        "task_truth_assessed": False,
        "pass_assessed": False,
        "authorizes_mutation": False,
        "blocking_gate": False,
    }
    report["report_digest"] = sha256_json(report)
    return report


def assemble_parallel_rule_ir(
    source_partition_product: Any,
    rule_product: Any,
    witness_product: Any,
    *,
    run_classification: str = "fresh_task_pre_experiment",
) -> dict[str, Any]:
    """Join independently visible Rule and witness lane products deterministically."""

    source_partition = validate_source_partition_product(source_partition_product)
    if not isinstance(rule_product, dict) or not isinstance(witness_product, dict):
        raise CorridorKitError("parallel Rule assembly inputs must be objects")
    _exact_keys(
        rule_product,
        {
            "schema_version",
            "partition_product_digest",
            "rule_lane_bindings",
            "rules",
        },
        label="rule lane product",
    )
    if rule_product.get("schema_version") != RULE_LANE_PRODUCT_SCHEMA:
        raise CorridorKitError("rule lane product has the wrong schema")
    _exact_keys(
        witness_product,
        {
            "schema_version",
            "partition_product_digest",
            "partition_manifest_digest",
            "authority_snapshot_digest",
            "witness_lane_packages",
        },
        label="witness lane product",
    )
    if witness_product.get("schema_version") != WITNESS_LANE_PRODUCT_SCHEMA:
        raise CorridorKitError("witness lane product has the wrong schema")
    source_partition_digest = sha256_json(source_partition)
    if (
        rule_product.get("partition_product_digest") != source_partition_digest
        or witness_product.get("partition_product_digest") != source_partition_digest
    ):
        raise CorridorKitError(
            "parallel products do not bind the frozen source partition"
        )
    partition_manifest = source_partition["partition_manifest"]
    source_bundle = source_partition["source_bundle"]
    if witness_product.get("partition_manifest_digest") != sha256_json(
        partition_manifest
    ):
        raise CorridorKitError("witness product does not bind the Rule partition")
    if witness_product.get("authority_snapshot_digest") != sha256_json(source_bundle):
        raise CorridorKitError("witness product does not bind the AuthoritySnapshot")
    typed_rule_ir = {
        "schema_version": TYPED_RULE_IR_SCHEMA_V5,
        "source_bundle": source_bundle,
        "source_clause_inventory": source_partition["source_clause_inventory"],
        "revision": source_partition["revision"],
        "method_digest": source_partition["method_digest"],
        "compiler_config_digest": source_partition["compiler_config_digest"],
        "partition_manifest": partition_manifest,
        "rule_lane_bindings": rule_product["rule_lane_bindings"],
        "witness_lane_packages": witness_product["witness_lane_packages"],
        "rules": rule_product["rules"],
    }
    compile_report = compile_typed_rule_ir(
        typed_rule_ir, run_classification=run_classification
    )
    input_identity = {
        "partition_product_digest": source_partition_digest,
        "rule_product_digest": sha256_json(rule_product),
        "witness_product_digest": sha256_json(witness_product),
        "partition_manifest_digest": sha256_json(partition_manifest),
        "authority_snapshot_digest": sha256_json(source_bundle),
    }
    assembly = {
        "schema_version": PARALLEL_RULE_ASSEMBLY_SCHEMA,
        **input_identity,
        "typed_rule_ir_digest": compile_report["typed_rule_ir_digest"],
        "compile_report_digest": compile_report["report_digest"],
        "compilation_complete": compile_report["compilation_complete"],
    }
    return {
        "typed_rule_ir": typed_rule_ir,
        "compile_report": compile_report,
        "assembly_manifest": {
            **assembly,
            "assembly_digest": sha256_json(assembly),
        },
    }
