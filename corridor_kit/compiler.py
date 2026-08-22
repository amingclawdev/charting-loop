"""Task-neutral compilation of public task requirements into typed Rule cells.

The compiler validates an agent-authored semantic IR and projects it into Graph
Kernel record bodies.  It does not read a verifier, infer task truth, choose a
Direction, or authorize work.  Natural-language interpretation remains an agent
responsibility; this module makes that interpretation explicit and replayable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .core import CorridorKitError, sha256_bytes, sha256_json


TYPED_RULE_IR_SCHEMA_V1 = "charting-loop/typed-rule-ir/v1"
TYPED_RULE_IR_SCHEMA = "charting-loop/typed-rule-ir/v2"
TYPED_RULE_COMPILATION_SCHEMA_V1 = "charting-loop/typed-rule-compilation/v1"
TYPED_RULE_COMPILATION_SCHEMA = "charting-loop/typed-rule-compilation/v2"
COMPILE_PROBE_MANIFEST_SCHEMA_V1 = "charting-loop/compile-probe-manifest/v1"
COMPILE_PROBE_MANIFEST_SCHEMA = "charting-loop/compile-probe-manifest/v2"
TASK_SOURCE_BUNDLE_SCHEMA = "charting-loop/task-source-bundle/v1"
TYPED_RULE_SEMANTICS_SCHEMA = "charting-loop/typed-rule-semantics/v2"

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
RUN_CLASSIFICATIONS = frozenset(
    {"fresh_task_pre_experiment", "same_task_regression"}
)
COMPILATION_STATUSES = frozenset(
    {"complete", "incomplete", "ambiguous", "unsupported"}
)
REQUIREMENT_LEVELS = frozenset({"required", "optional"})
SOURCE_ROLES = frozenset({"instruction", "authoritative_specification"})
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
    _exact_keys(
        value,
        {"schema_version", "closure_status", "sources"},
        label="task source bundle",
    )
    if value.get("schema_version") != TASK_SOURCE_BUNDLE_SCHEMA:
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
        if not isinstance(raw, dict):
            raise CorridorKitError("task source bundle source must be an object")
        _exact_keys(
            raw,
            {
                "source_id",
                "source_ref",
                "source_digest",
                "role",
                "retrieval_status",
            },
            label="task source bundle source",
        )
        source_id = _identifier(raw, "source_id")
        source_ref = _text(raw, "source_ref")
        if source_id in source_ids or source_ref in source_refs:
            raise CorridorKitError("task source bundle contains a duplicate source identity")
        source_ids.add(source_id)
        source_refs.add(source_ref)
        role = _text(raw, "role")
        if role not in SOURCE_ROLES:
            raise CorridorKitError(f"unknown task source role: {role}")
        retrieval_status = _text(raw, "retrieval_status")
        if retrieval_status not in SOURCE_RETRIEVAL_STATUSES:
            raise CorridorKitError(
                f"unknown task source retrieval_status: {retrieval_status}"
            )
        source_digest = raw.get("source_digest")
        if retrieval_status == "available":
            source_digest = _digest(raw, "source_digest")
        elif source_digest is not None:
            raise CorridorKitError(
                "unavailable, malformed, or undigested task source must use null source_digest"
            )
        sources.append(
            {
                "source_id": source_id,
                "source_ref": source_ref,
                "source_digest": source_digest,
                "role": role,
                "retrieval_status": retrieval_status,
            }
        )
    if not any(source["role"] == "instruction" for source in sources):
        raise CorridorKitError("task source bundle must include the public instruction")
    derived_closure = (
        "complete"
        if all(source["retrieval_status"] == "available" for source in sources)
        else "unresolved"
    )
    if closure_status != derived_closure:
        raise CorridorKitError(
            "task source bundle closure_status does not match retrieval statuses"
        )
    return {
        "schema_version": TASK_SOURCE_BUNDLE_SCHEMA,
        "closure_status": closure_status,
        "sources": sources,
    }


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


def validate_rule_semantics(value: Any) -> dict[str, Any]:
    """Return one canonical Rule semantic object or raise without guessing."""

    if not isinstance(value, dict):
        raise CorridorKitError("typed Rule semantics must be an object")
    semantics_schema = value.get("schema_version")
    is_v2 = semantics_schema == TYPED_RULE_SEMANTICS_SCHEMA
    expected_fields = {
        "rule_kind",
        "compilation_status",
        "compile_issues",
        "quantifier",
        "conditions",
        "checklist_projection",
        "dependencies",
    }
    if is_v2:
        expected_fields.update(
            {"schema_version", "requirement_level", "applicability"}
        )
    elif semantics_schema is not None:
        raise CorridorKitError("typed Rule semantics has an unknown schema")
    _exact_keys(
        value,
        expected_fields,
        label="typed Rule semantics",
    )
    requirement_level = "required"
    applicability: dict[str, str] | None = None
    if is_v2:
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
            if is_v2
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
    if is_v2:
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
            {
                "condition_id",
                "predicate",
                "expected_outcome",
                "required_witness_operators",
            },
            label="typed Rule condition",
        )
        condition_id = _identifier(raw, "condition_id")
        if condition_id in condition_ids:
            raise CorridorKitError(
                f"typed Rule condition is duplicated: {condition_id}"
            )
        condition_ids.add(condition_id)
        conditions.append(
            {
                "condition_id": condition_id,
                "predicate": _text(raw, "predicate"),
                "expected_outcome": _text(raw, "expected_outcome"),
                "required_witness_operators": _operators(
                    raw,
                    "required_witness_operators",
                    nonempty=compilation_status == "complete",
                ),
            }
        )

    if (
        compilation_status == "complete"
        and rule_kind in {"temporal_conditional", "state_transition", "precedence"}
    ):
        for condition in conditions:
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
    dependencies: list[dict[str, str]] = []
    seen_dependencies: set[tuple[str, str]] = set()
    for raw in raw_dependencies:
        if not isinstance(raw, dict):
            raise CorridorKitError("typed Rule dependency must be an object")
        _exact_keys(
            raw,
            {"relationship", "target_rule_id"},
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
        dependencies.append(
            {"relationship": relationship, "target_rule_id": target_rule_id}
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
    if is_v2:
        normalized = {
            "schema_version": TYPED_RULE_SEMANTICS_SCHEMA,
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
                        == TYPED_RULE_SEMANTICS_SCHEMA
                        else {}
                    ),
                }
            )
    return templates


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
    is_v2 = ir_schema == TYPED_RULE_IR_SCHEMA
    if not is_v2 and ir_schema != TYPED_RULE_IR_SCHEMA_V1:
        raise CorridorKitError("typed Rule IR has the wrong schema")
    _exact_keys(
        value,
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
            if is_v2
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
    if is_v2:
        source_bundle = validate_source_bundle(value.get("source_bundle"))
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
        task_source_digest = instruction_source["source_digest"]
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
    rule_dependency_templates: list[dict[str, Any]] = []
    checklist_templates_by_rule: dict[str, list[dict[str, Any]]] = {}
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
                else {
                    "rule_id",
                    "statement",
                    "source_ref",
                    "source_digest",
                    "semantics",
                }
            ),
            label="typed Rule IR rule",
        )
        rule_id = _identifier(raw, "rule_id")
        if rule_id in rule_ids:
            raise CorridorKitError(f"typed Rule ID is duplicated: {rule_id}")
        rule_ids.add(rule_id)
        statement = _text(raw, "statement")
        semantics = validate_rule_semantics(raw.get("semantics"))
        semantics_digest = sha256_json(semantics)
        normalized = {
            "rule_id": rule_id,
            "statement": statement,
            "source_ref": _text(raw, "source_ref"),
            "source_digest": _digest(raw, "source_digest"),
            **(
                {"source_clause_ids": _text_list(raw, "source_clause_ids", nonempty=True)}
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
        for dependency in semantics["dependencies"]:
            rule_dependency_templates.append(
                {
                    "from_rule_id": rule_id,
                    "to_rule_id": dependency["target_rule_id"],
                    "relationship": dependency["relationship"],
                }
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
    for dependency in rule_dependency_templates:
        graph_relationship = work_relationships.get(dependency["relationship"])
        if graph_relationship is None:
            continue
        source_cells = checklist_templates_by_rule[dependency["from_rule_id"]]
        target_cells = checklist_templates_by_rule[dependency["to_rule_id"]]
        for source_cell in source_cells:
            for target_cell in target_cells:
                identity = {
                    "from_ref": source_cell["checklist_item_id"],
                    "to_ref": target_cell["checklist_item_id"],
                    "relationship": graph_relationship,
                    "source_rule_id": dependency["from_rule_id"],
                }
                typed_dependency_templates.append(
                    {
                        "dependency_id": f"DEP-{sha256_json(identity)[7:23]}",
                        "dependency_kind": "work",
                        **identity,
                    }
                )

    normalized_ir = (
        {
            "schema_version": TYPED_RULE_IR_SCHEMA,
            "source_bundle": source_bundle,
            "source_clause_inventory": source_clauses,
            "revision": revision,
            "method_digest": method_digest,
            "compiler_config_digest": compiler_config_digest,
            "rules": normalized_rules,
        }
        if is_v2
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
            COMPILE_PROBE_MANIFEST_SCHEMA
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
            }
            if is_v2
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
                    if is_v2
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
        if is_v2
        else None
    )
    compilation_complete = (
        rules_complete
        and source_bundle is not None
        and source_bundle["closure_status"] == "complete"
        and source_clauses_complete is True
        if is_v2
        else rules_complete
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
        if is_v2
        else []
    )
    report = {
        "schema_version": (
            TYPED_RULE_COMPILATION_SCHEMA
            if is_v2
            else TYPED_RULE_COMPILATION_SCHEMA_V1
        ),
        "ok": True,
        "compilation_complete": compilation_complete,
        "compile_issues": [*rule_compile_issues, *source_clause_issues],
        "source_closure_assessed": is_v2,
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
            }
            if is_v2
            else {
                "bundle_status": "legacy_unassessed",
                "clause_inventory_complete": None,
                "source_count": None,
                "clause_count": None,
                "mapped_clause_count": None,
            }
        ),
        "revision": revision,
        "typed_rule_ir_digest": ir_digest,
        "compiler_implementation_digest": implementation_digest,
        "rule_count": len(rule_bodies),
        "coverage_cell_count": len(checklist_templates),
        "rule_dependency_count": len(rule_dependency_templates),
        "typed_dependency_count": len(typed_dependency_templates),
        "rule_bodies": rule_bodies,
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
