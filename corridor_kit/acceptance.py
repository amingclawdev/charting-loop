"""Strict validation for the task acceptance ledger shared by Worker and QA."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from .core import CorridorKitError, load_json


ACCEPTANCE_SCHEMA = "charting-loop/task-acceptance-ledger/v2"
QA_ASSESSMENT_SCHEMA = "charting-loop/corridor-qa-assessment/v3"
QA_OUTCOMES = frozenset({"pass", "fail", "blocked", "not_assessed"})
QA_APPLICABILITY = frozenset({"applicable", "not_applicable", "unknown"})
QA_ACCEPTANCE_STATES = frozenset({"pass", "fail", "unknown", "not_reached"})
QA_CLOSURE_STATES = frozenset({"complete", "incomplete"})
QA_SCOPE_STATES = frozenset({"complete", "partial"})
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
RELATION_TYPES = frozenset(
    {"requires", "subsumes", "overlaps", "conflicts", "derived_from"}
)
DEFINITION_STATES = frozenset({"defined", "ambiguous"})
COVERAGE_STATES = frozenset({"complete", "incomplete"})
READINESS_STATES = frozenset({"ready", "unresolved"})
ACCEPTANCE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
VERIFICATION_OBLIGATION_KINDS = (
    "positive",
    "negative",
    "boundary",
    "state",
    "temporal",
    "coupled",
)


@dataclass
class AcceptanceReport:
    """Structural findings and readiness facts; never an authorization decision."""

    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str, location: str, message: str) -> None:
        self.errors.append({"code": code, "location": location, "message": message})

    def warning(self, code: str, location: str, message: str) -> None:
        self.warnings.append({"code": code, "location": location, "message": message})

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


def _object(
    value: Any,
    *,
    exact_keys: set[str],
    report: AcceptanceReport,
    location: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        report.error("OBJECT_REQUIRED", location, "must be an object")
        return None
    if set(value) != exact_keys:
        report.error(
            "EXACT_FIELDS_REQUIRED",
            location,
            f"must contain exactly {sorted(exact_keys)}; got {sorted(value)}",
        )
    return value


def _nonempty_string(
    value: Any,
    *,
    report: AcceptanceReport,
    location: str,
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        report.error("NONEMPTY_STRING_REQUIRED", location, "must be a non-empty string")
        return None
    return value.strip()


def _string_list(
    value: Any,
    *,
    report: AcceptanceReport,
    location: str,
    unique: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        report.error("STRING_LIST_REQUIRED", location, "must be a list of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _nonempty_string(item, report=report, location=f"{location}[{index}]")
        if text is not None:
            result.append(text)
    if unique and len(result) != len(set(result)):
        report.error("DUPLICATE_LIST_VALUE", location, "values must be unique")
    return result


def _clause_list(
    value: Any,
    *,
    report: AcceptanceReport,
    location: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        report.error("CLAUSE_LIST_REQUIRED", location, "must be a list")
        return []
    clauses: list[dict[str, Any]] = []
    expected = {"source_ref", "statement", "reason"}
    for index, item in enumerate(value):
        item_location = f"{location}[{index}]"
        clause = _object(
            item,
            exact_keys=expected,
            report=report,
            location=item_location,
        )
        if clause is None:
            continue
        for field_name in expected:
            _nonempty_string(
                clause.get(field_name),
                report=report,
                location=f"{item_location}.{field_name}",
            )
        clauses.append(clause)
    return clauses


def validate_acceptance_ledger(
    value: Any,
    *,
    allow_draft: bool = False,
) -> AcceptanceReport:
    """Validate exact ledger structure and report non-authoritative readiness facts."""

    report = AcceptanceReport()
    ledger = _object(
        value,
        exact_keys={
            "schema_version",
            "coverage",
            "construction_readiness",
            "items",
        },
        report=report,
        location="$",
    )
    if ledger is None:
        return report
    if ledger.get("schema_version") != ACCEPTANCE_SCHEMA:
        report.error(
            "SCHEMA_VERSION",
            "$.schema_version",
            f"must equal {ACCEPTANCE_SCHEMA!r}",
        )

    coverage = _object(
        ledger.get("coverage"),
        exact_keys={"status", "unmapped_clauses", "ambiguous_clauses"},
        report=report,
        location="$.coverage",
    ) or {}
    coverage_status = coverage.get("status")
    if coverage_status not in COVERAGE_STATES:
        report.error(
            "COVERAGE_STATUS",
            "$.coverage.status",
            f"must be one of {sorted(COVERAGE_STATES)}",
        )
    unmapped = _clause_list(
        coverage.get("unmapped_clauses"),
        report=report,
        location="$.coverage.unmapped_clauses",
    )
    ambiguous_clauses = _clause_list(
        coverage.get("ambiguous_clauses"),
        report=report,
        location="$.coverage.ambiguous_clauses",
    )
    if coverage_status == "complete" and unmapped:
        report.error(
            "COMPLETE_COVERAGE_HAS_UNMAPPED_CLAUSES",
            "$.coverage",
            "complete source mapping cannot list unmapped clauses",
        )
    if coverage_status == "incomplete" and not unmapped:
        report.error(
            "INCOMPLETE_COVERAGE_NEEDS_UNMAPPED_CLAUSE",
            "$.coverage",
            "incomplete source mapping must describe at least one unmapped clause",
        )

    items_value = ledger.get("items")
    if not isinstance(items_value, list):
        report.error("ITEM_LIST_REQUIRED", "$.items", "must be a list")
        items_value = []
    if not items_value and not allow_draft:
        report.error("ITEMS_NONEMPTY", "$.items", "final ledger must contain an item")

    item_fields = {
        "acceptance_id",
        "source_ref",
        "statement",
        "required",
        "definition_state",
        "scope",
        "rule",
        "relations",
        "verification_obligations",
    }
    relation_fields = {"type", "target_id"}
    item_ids: list[str] = []
    required_ids: list[str] = []
    relation_targets: list[tuple[str, str, str]] = []
    ambiguous_item_ids: list[str] = []
    for index, item_value in enumerate(items_value):
        location = f"$.items[{index}]"
        item = _object(
            item_value,
            exact_keys=item_fields,
            report=report,
            location=location,
        )
        if item is None:
            continue
        acceptance_id = _nonempty_string(
            item.get("acceptance_id"),
            report=report,
            location=f"{location}.acceptance_id",
        )
        if acceptance_id is not None and not ACCEPTANCE_ID_RE.fullmatch(acceptance_id):
            report.error(
                "ACCEPTANCE_ID_FORMAT",
                f"{location}.acceptance_id",
                "must be a stable token containing only letters, digits, '.', '_', ':', or '-'",
            )
        _nonempty_string(
            item.get("source_ref"), report=report, location=f"{location}.source_ref"
        )
        _nonempty_string(
            item.get("statement"), report=report, location=f"{location}.statement"
        )
        if not isinstance(item.get("required"), bool):
            report.error(
                "BOOLEAN_REQUIRED", f"{location}.required", "must be a boolean"
            )
        definition_state = item.get("definition_state")
        if definition_state not in DEFINITION_STATES:
            report.error(
                "DEFINITION_STATE",
                f"{location}.definition_state",
                f"must be one of {sorted(DEFINITION_STATES)}",
            )
        scope = item.get("scope")
        if not isinstance(scope, dict) or not scope:
            report.error("NONEMPTY_SCOPE", f"{location}.scope", "must be a non-empty object")
        rule = item.get("rule")
        if not isinstance(rule, dict) or not rule:
            report.error("NONEMPTY_RULE", f"{location}.rule", "must be a non-empty object")
        if acceptance_id is not None:
            item_ids.append(acceptance_id)
            if item.get("required") is True:
                required_ids.append(acceptance_id)
            if definition_state == "ambiguous":
                ambiguous_item_ids.append(acceptance_id)

        relations = item.get("relations")
        if not isinstance(relations, list):
            report.error(
                "RELATION_LIST_REQUIRED", f"{location}.relations", "must be a list"
            )
            relations = []
        for relation_index, relation_value in enumerate(relations):
            relation_location = f"{location}.relations[{relation_index}]"
            relation = _object(
                relation_value,
                exact_keys=relation_fields,
                report=report,
                location=relation_location,
            )
            if relation is None:
                continue
            relation_type = relation.get("type")
            if relation_type not in RELATION_TYPES:
                report.error(
                    "RELATION_TYPE",
                    f"{relation_location}.type",
                    f"must be one of {sorted(RELATION_TYPES)}",
                )
            target_id = _nonempty_string(
                relation.get("target_id"),
                report=report,
                location=f"{relation_location}.target_id",
            )
            if acceptance_id and target_id:
                if acceptance_id == target_id:
                    report.error(
                        "SELF_RELATION",
                        relation_location,
                        "an acceptance item cannot relate to itself",
                    )
                relation_targets.append((acceptance_id, target_id, relation_location))

        obligations = _object(
            item.get("verification_obligations"),
            exact_keys=set(VERIFICATION_OBLIGATION_KINDS),
            report=report,
            location=f"{location}.verification_obligations",
        ) or {}
        for kind in VERIFICATION_OBLIGATION_KINDS:
            entries = _string_list(
                obligations.get(kind),
                report=report,
                location=f"{location}.verification_obligations.{kind}",
            )
            if not entries:
                report.error(
                    "VERIFICATION_OBLIGATION_REQUIRED",
                    f"{location}.verification_obligations.{kind}",
                    "every acceptance item must explicitly declare at least one obligation; use an explicit not-applicable reason when the partition does not apply",
                )

    if len(item_ids) != len(set(item_ids)):
        report.error("DUPLICATE_ACCEPTANCE_ID", "$.items", "acceptance IDs must be unique")
    known_ids = set(item_ids)
    for source_id, target_id, location in relation_targets:
        if target_id not in known_ids:
            report.error(
                "UNKNOWN_RELATION_TARGET",
                f"{location}.target_id",
                f"{source_id!r} refers to unknown acceptance ID {target_id!r}",
            )
    source_mapping_complete = bool(
        coverage_status == "complete" and not unmapped
    )
    definition_closure_complete = bool(
        not ambiguous_clauses and not ambiguous_item_ids
    )

    readiness = _object(
        ledger.get("construction_readiness"),
        exact_keys={
            "status",
            "coupled_acceptance_ids",
            "replay_entrypoint",
            "unresolved_constraints",
        },
        report=report,
        location="$.construction_readiness",
    ) or {}
    readiness_status = readiness.get("status")
    if readiness_status not in READINESS_STATES:
        report.error(
            "READINESS_STATUS",
            "$.construction_readiness.status",
            f"must be one of {sorted(READINESS_STATES)}",
        )
    coupled_ids = _string_list(
        readiness.get("coupled_acceptance_ids"),
        report=report,
        location="$.construction_readiness.coupled_acceptance_ids",
    )
    replay_entrypoint = readiness.get("replay_entrypoint")
    if not isinstance(replay_entrypoint, str):
        report.error(
            "REPLAY_ENTRYPOINT_STRING",
            "$.construction_readiness.replay_entrypoint",
            "must be a string; use an empty string only while unresolved",
        )
        replay_entrypoint = ""
    unresolved_constraints = _string_list(
        readiness.get("unresolved_constraints"),
        report=report,
        location="$.construction_readiness.unresolved_constraints",
    )
    for acceptance_id in coupled_ids:
        if acceptance_id not in known_ids:
            report.error(
                "UNKNOWN_COUPLED_ACCEPTANCE_ID",
                "$.construction_readiness.coupled_acceptance_ids",
                f"unknown acceptance ID {acceptance_id!r}",
            )
    if readiness_status == "ready":
        if not item_ids:
            report.error(
                "READY_ITEMS_NONEMPTY_REQUIRED",
                "$.construction_readiness.status",
                "construction cannot be ready before acceptance items are compiled",
            )
        if unresolved_constraints:
            report.error(
                "READY_WITH_UNRESOLVED_CONSTRAINTS",
                "$.construction_readiness",
                "ready construction cannot retain unresolved constraints",
            )
        if not replay_entrypoint.strip():
            report.error(
                "READY_REPLAY_ENTRYPOINT_REQUIRED",
                "$.construction_readiness.replay_entrypoint",
                "ready construction requires one replayable entrypoint",
            )
        if coverage_status != "complete":
            report.error(
                "READY_REQUIRES_COMPLETE_COVERAGE",
                "$.construction_readiness.status",
                "construction cannot be ready while source mapping is incomplete",
            )
        if not definition_closure_complete:
            report.error(
                "READY_REQUIRES_DEFINITION_CLOSURE",
                "$.construction_readiness.status",
                "construction cannot be ready while task definitions remain ambiguous",
            )
    elif readiness_status == "unresolved" and not unresolved_constraints:
        report.error(
            "UNRESOLVED_REASON_REQUIRED",
            "$.construction_readiness.unresolved_constraints",
            "unresolved construction must name a missing proof",
        )

    report.facts = {
        "schema_version": ledger.get("schema_version"),
        "coverage_status": coverage_status,
        "source_mapping_status": (
            "complete" if source_mapping_complete else "incomplete"
        ),
        "source_mapping_complete": source_mapping_complete,
        "definition_closure_status": (
            "complete" if definition_closure_complete else "incomplete"
        ),
        "definition_closure_complete": definition_closure_complete,
        "construction_readiness_status": readiness_status,
        "acceptance_ids": item_ids,
        "required_acceptance_ids": required_ids,
        "ambiguous_acceptance_ids": ambiguous_item_ids,
        "coupled_acceptance_ids": coupled_ids,
        "verification_obligation_kinds": list(VERIFICATION_OBLIGATION_KINDS),
        "unmapped_count": len(unmapped),
        "ambiguous_clause_count": len(ambiguous_clauses),
        "unresolved_constraints": unresolved_constraints,
        "replay_entrypoint": replay_entrypoint,
        "draft_allowed": allow_draft,
        "task_ready": bool(
            not report.errors
            and source_mapping_complete
            and definition_closure_complete
            and readiness_status == "ready"
            and item_ids
        ),
    }
    if allow_draft and not items_value:
        report.warning(
            "DRAFT_HAS_NO_ITEMS",
            "$.items",
            "starter is structurally honest but must be compiled before freeze",
        )
    return report


def validate_acceptance_file(
    path: Path,
    *,
    allow_draft: bool = False,
) -> AcceptanceReport:
    try:
        value = load_json(path)
    except CorridorKitError as exc:
        report = AcceptanceReport()
        report.error("JSON_INPUT", str(path), str(exc))
        return report
    return validate_acceptance_ledger(value, allow_draft=allow_draft)


def validate_qa_assessment(
    value: Any,
    *,
    expected_corridor_digest: str,
    acceptance_ledger_status: str,
    expected_acceptance_ids: list[str],
    required_acceptance_ids: list[str],
    source_mapping_status: str = "complete",
    definition_closure_status: str = "complete",
    construction_readiness_status: str = "ready",
) -> list[str]:
    """Validate one advisory QA envelope against its frozen Corridor identity.

    This is shared by the QA-side pre-submit command and harness intake.  It
    classifies evidence but never authorizes mutation or blocks task grading.
    ``assessed_scope=partial`` may close a declared subset, but it can never
    establish a task-level pass.
    """

    errors: list[str] = []
    if not isinstance(value, dict):
        return ["ASSESSMENT_OBJECT_REQUIRED"]
    if value.get("schema_version") != QA_ASSESSMENT_SCHEMA:
        errors.append("ASSESSMENT_SCHEMA")
    outcome = value.get("outcome")
    if outcome not in QA_OUTCOMES:
        errors.append("ASSESSMENT_OUTCOME")
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("ASSESSMENT_SUMMARY")
    digest = value.get("corridor_digest")
    if digest != expected_corridor_digest or not isinstance(digest, str):
        errors.append("ASSESSMENT_CORRIDOR_DIGEST")
    elif not SHA256_RE.fullmatch(digest):
        errors.append("ASSESSMENT_CORRIDOR_DIGEST_FORMAT")

    source_mapping_complete = value.get("source_mapping_complete")
    if not isinstance(source_mapping_complete, bool):
        errors.append("ASSESSMENT_SOURCE_MAPPING_COMPLETE")
    definition_closure_complete = value.get("definition_closure_complete")
    if not isinstance(definition_closure_complete, bool):
        errors.append("ASSESSMENT_DEFINITION_CLOSURE_COMPLETE")
    assessment_closure = value.get("assessment_closure")
    if assessment_closure not in QA_CLOSURE_STATES:
        errors.append("ASSESSMENT_CLOSURE")
    assessed_scope = value.get("assessed_scope", "complete")
    if assessed_scope not in QA_SCOPE_STATES:
        errors.append("ASSESSMENT_SCOPE")
    scope_limitations = value.get("scope_limitations", [])
    if not isinstance(scope_limitations, list) or any(
        not isinstance(item, str) or not item.strip() for item in scope_limitations
    ):
        errors.append("ASSESSMENT_SCOPE_LIMITATIONS")
        scope_limitations = []
    if assessed_scope == "partial" and not scope_limitations:
        errors.append("ASSESSMENT_PARTIAL_SCOPE_LIMITATION_REQUIRED")
    if assessed_scope == "complete" and scope_limitations:
        errors.append("ASSESSMENT_COMPLETE_SCOPE_LIMITATION_CONTRADICTION")
    if (
        definition_closure_complete is False
        and assessment_closure == "complete"
        and assessed_scope != "partial"
    ):
        errors.append("ASSESSMENT_DEFINITION_AND_CLOSURE_CONTRADICTION")

    expected_ids = set(expected_acceptance_ids)
    if len(expected_ids) != len(expected_acceptance_ids):
        errors.append("EXPECTED_ACCEPTANCE_IDS_DUPLICATE")
    required_ids = set(required_acceptance_ids)
    if not required_ids.issubset(expected_ids):
        errors.append("REQUIRED_ACCEPTANCE_IDS_UNKNOWN")

    acceptance_results = value.get("acceptance_results")
    results_by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(acceptance_results, list):
        errors.append("ASSESSMENT_ACCEPTANCE_RESULTS")
        acceptance_results = []
    for index, result in enumerate(acceptance_results):
        if not isinstance(result, dict):
            errors.append(f"ASSESSMENT_ACCEPTANCE_RESULT_{index}")
            continue
        acceptance_id = result.get("acceptance_id")
        if not isinstance(acceptance_id, str) or not acceptance_id.strip():
            errors.append(f"ASSESSMENT_ACCEPTANCE_ID_{index}")
            continue
        if acceptance_id in results_by_id:
            errors.append(f"ASSESSMENT_ACCEPTANCE_ID_DUPLICATE_{acceptance_id}")
            continue
        results_by_id[acceptance_id] = result
        if result.get("applicability") not in QA_APPLICABILITY:
            errors.append(f"ASSESSMENT_APPLICABILITY_{acceptance_id}")
        if result.get("status") not in QA_ACCEPTANCE_STATES:
            errors.append(f"ASSESSMENT_ACCEPTANCE_STATUS_{acceptance_id}")
        for field_name in ("evidence", "replay"):
            item = result.get(field_name)
            if not isinstance(item, str) or not item.strip():
                errors.append(
                    f"ASSESSMENT_ACCEPTANCE_{field_name.upper()}_{acceptance_id}"
                )

    actual_ids = set(results_by_id)
    for acceptance_id in sorted(expected_ids - actual_ids):
        errors.append(f"ASSESSMENT_ACCEPTANCE_ID_MISSING_{acceptance_id}")
    for acceptance_id in sorted(actual_ids - expected_ids):
        errors.append(f"ASSESSMENT_ACCEPTANCE_ID_UNKNOWN_{acceptance_id}")

    collections: dict[str, list[Any]] = {}
    for field_name, code in (
        ("unmapped_requirements", "ASSESSMENT_UNMAPPED_REQUIREMENTS"),
        ("unresolved_relations", "ASSESSMENT_UNRESOLVED_RELATIONS"),
    ):
        items = value.get(field_name)
        if not isinstance(items, list):
            errors.append(code)
            continue
        collections[field_name] = items
        for index, item in enumerate(items):
            if not isinstance(item, str) or not item.strip():
                errors.append(f"{code}_{index}")
    if source_mapping_complete is True and collections.get("unmapped_requirements"):
        errors.append("ASSESSMENT_SOURCE_MAPPING_CONTRADICTION")
    if definition_closure_complete is True and collections.get("unresolved_relations"):
        errors.append("ASSESSMENT_DEFINITION_CLOSURE_CONTRADICTION")
    if source_mapping_complete is True and source_mapping_status != "complete":
        errors.append("ASSESSMENT_SOURCE_MAPPING_EXCEEDS_FROZEN_LEDGER")
    if definition_closure_complete is True and definition_closure_status != "complete":
        errors.append("ASSESSMENT_DEFINITION_CLOSURE_EXCEEDS_FROZEN_LEDGER")

    checks = value.get("checks")
    if not isinstance(checks, list):
        errors.append("ASSESSMENT_CHECKS")
        checks = []
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"ASSESSMENT_CHECK_{index}")
                continue
            if not isinstance(check.get("name"), str) or not check["name"].strip():
                errors.append(f"ASSESSMENT_CHECK_NAME_{index}")
            if check.get("status") not in {"pass", "fail", "unknown"}:
                errors.append(f"ASSESSMENT_CHECK_STATUS_{index}")
            if not isinstance(check.get("evidence"), str):
                errors.append(f"ASSESSMENT_CHECK_EVIDENCE_{index}")

    if assessment_closure == "complete":
        unresolved = any(
            result.get("applicability") == "unknown"
            or (
                result.get("applicability") == "applicable"
                and result.get("status") in {"unknown", "not_reached"}
            )
            for result in results_by_id.values()
        ) or any(
            isinstance(check, dict) and check.get("status") == "unknown"
            for check in checks
        )
        if unresolved or (assessed_scope == "complete" and actual_ids != expected_ids):
            errors.append("ASSESSMENT_CLOSURE_CONTRADICTION")

    witnesses = value.get("witnesses")
    if not isinstance(witnesses, list):
        errors.append("ASSESSMENT_WITNESSES")
        witnesses = []
    witness_acceptance_ids: set[str] = set()
    for index, witness in enumerate(witnesses):
        if not isinstance(witness, dict):
            errors.append(f"ASSESSMENT_WITNESS_{index}")
            continue
        for field_name in ("constraint", "evidence", "replay"):
            item = witness.get(field_name)
            if not isinstance(item, str) or not item.strip():
                errors.append(f"ASSESSMENT_WITNESS_{field_name.upper()}_{index}")
        acceptance_id = witness.get("acceptance_id")
        if not isinstance(acceptance_id, str) or not acceptance_id.strip():
            errors.append(f"ASSESSMENT_WITNESS_ACCEPTANCE_ID_{index}")
        elif acceptance_id not in expected_ids:
            errors.append(f"ASSESSMENT_WITNESS_ACCEPTANCE_ID_UNKNOWN_{index}")
        else:
            witness_acceptance_ids.add(acceptance_id)

    if outcome == "fail":
        if not witnesses:
            errors.append("FAIL_WITNESS_REQUIRED")
        failed_ids = {
            acceptance_id
            for acceptance_id, result in results_by_id.items()
            if result.get("status") == "fail"
        }
        if not failed_ids:
            errors.append("FAIL_ACCEPTANCE_RESULT_REQUIRED")
        elif not (failed_ids & witness_acceptance_ids):
            errors.append("FAIL_WITNESS_ACCEPTANCE_MISMATCH")

    if outcome == "pass":
        if assessed_scope != "complete":
            errors.append("PASS_COMPLETE_SCOPE_REQUIRED")
        if construction_readiness_status != "ready":
            errors.append("PASS_CONSTRUCTION_READINESS_REQUIRED")
        if acceptance_ledger_status != "complete":
            errors.append("PASS_ACCEPTANCE_LEDGER_COMPLETE_REQUIRED")
        if source_mapping_status != "complete":
            errors.append("PASS_FROZEN_SOURCE_MAPPING_REQUIRED")
        if definition_closure_status != "complete":
            errors.append("PASS_FROZEN_DEFINITION_CLOSURE_REQUIRED")
        if not expected_ids:
            errors.append("PASS_ACCEPTANCE_IDS_REQUIRED")
        if source_mapping_complete is not True:
            errors.append("PASS_SOURCE_MAPPING_COMPLETE_REQUIRED")
        if definition_closure_complete is not True:
            errors.append("PASS_DEFINITION_CLOSURE_COMPLETE_REQUIRED")
        if assessment_closure != "complete":
            errors.append("PASS_ASSESSMENT_CLOSURE_REQUIRED")
        if value.get("unmapped_requirements") != []:
            errors.append("PASS_UNMAPPED_REQUIREMENTS_EMPTY_REQUIRED")
        if value.get("unresolved_relations") != []:
            errors.append("PASS_UNRESOLVED_RELATIONS_EMPTY_REQUIRED")
        for acceptance_id in sorted(expected_ids & actual_ids):
            result = results_by_id[acceptance_id]
            applicability = result.get("applicability")
            state = result.get("status")
            if applicability == "applicable" and state != "pass":
                errors.append(f"PASS_ACCEPTANCE_NOT_PASS_{acceptance_id}")
            elif applicability == "not_applicable" and state != "not_reached":
                errors.append(f"PASS_INAPPLICABLE_NOT_NOT_REACHED_{acceptance_id}")
            elif applicability == "unknown":
                errors.append(f"PASS_APPLICABILITY_UNKNOWN_{acceptance_id}")
    return errors


def qa_assessment_decision(value: Any, **expected: Any) -> dict[str, Any]:
    """Normalize validation into a non-authoritative intake decision."""

    errors = validate_qa_assessment(value, **expected)
    reported = value.get("outcome") if isinstance(value, dict) else None
    return {
        "schema_version": "charting-loop/qa-assessment-decision/v1",
        "valid": not errors,
        "errors": errors,
        "reported_outcome": reported,
        "outcome": reported if not errors else "not_assessed",
        "repair_required": not errors and reported == "fail",
        "raw_preserved": True,
        "advisory_only": True,
        "blocking_gate": False,
        "authorizes_mutation": False,
    }
