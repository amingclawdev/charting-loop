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


TYPED_RULE_IR_SCHEMA = "charting-loop/typed-rule-ir/v1"
TYPED_RULE_COMPILATION_SCHEMA = "charting-loop/typed-rule-compilation/v1"
COMPILE_PROBE_MANIFEST_SCHEMA = "charting-loop/compile-probe-manifest/v1"

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


def validate_rule_semantics(value: Any) -> dict[str, Any]:
    """Return one canonical Rule semantic object or raise without guessing."""

    if not isinstance(value, dict):
        raise CorridorKitError("typed Rule semantics must be an object")
    _exact_keys(
        value,
        {
            "rule_kind",
            "compilation_status",
            "compile_issues",
            "quantifier",
            "conditions",
            "checklist_projection",
            "dependencies",
        },
        label="typed Rule semantics",
    )
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
        {"mode", "subject_axis", "subjects"},
        label="typed Rule quantifier",
    )
    mode = _text(quantifier, "mode")
    if mode not in QUANTIFIER_MODES:
        raise CorridorKitError(f"unknown typed Rule quantifier mode: {mode}")
    subject_axis = _identifier(quantifier, "subject_axis")
    subjects = _text_list(quantifier, "subjects", nonempty=True)
    if len(subjects) != len(set(subjects)):
        raise CorridorKitError("typed Rule subjects contain duplicates")

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

    return {
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
    _exact_keys(
        value,
        {
            "schema_version",
            "task_source_ref",
            "task_source_digest",
            "method_digest",
            "compiler_config_digest",
            "rules",
        },
        label="typed Rule IR",
    )
    if value.get("schema_version") != TYPED_RULE_IR_SCHEMA:
        raise CorridorKitError("typed Rule IR has the wrong schema")
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
            {"rule_id", "statement", "source_ref", "source_digest", "semantics"},
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

    normalized_ir = {
        "schema_version": TYPED_RULE_IR_SCHEMA,
        "task_source_ref": task_source_ref,
        "task_source_digest": task_source_digest,
        "method_digest": method_digest,
        "compiler_config_digest": compiler_config_digest,
        "rules": normalized_rules,
    }
    ir_digest = sha256_json(normalized_ir)
    implementation_digest = _compiler_implementation_digest()
    manifest = {
        "schema_version": COMPILE_PROBE_MANIFEST_SCHEMA,
        "run_classification": run_classification,
        "task_source_ref": task_source_ref,
        "task_source_digest": task_source_digest,
        "method_digest": method_digest,
        "compiler_config_digest": compiler_config_digest,
        "compiler_implementation_digest": implementation_digest,
        "typed_rule_ir_digest": ir_digest,
        "input_policy": {
            "allowed": ["frozen_method", "public_task_source", "compiler_interface"],
            "forbidden": [
                "historical_task_graph",
                "official_verifier_output",
                "prior_task_result",
                "prior_task_transcript",
            ],
        },
        "fresh_efficacy_or_transfer_claim_allowed": (
            run_classification == "fresh_task_pre_experiment"
        ),
    }
    manifest["manifest_digest"] = sha256_json(manifest)
    compilation_complete = all(
        rule["semantics"]["compilation_status"] == "complete"
        for rule in normalized_rules
    )
    report = {
        "schema_version": TYPED_RULE_COMPILATION_SCHEMA,
        "ok": True,
        "compilation_complete": compilation_complete,
        "compile_issues": [
            {
                "rule_id": rule["rule_id"],
                "status": rule["semantics"]["compilation_status"],
                "issues": rule["semantics"]["compile_issues"],
            }
            for rule in normalized_rules
            if rule["semantics"]["compilation_status"] != "complete"
        ],
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
