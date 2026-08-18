"""Strict validation for the task acceptance ledger shared by Worker and QA."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from .core import CorridorKitError, load_json


ACCEPTANCE_SCHEMA = "charting-loop/task-acceptance-ledger/v2"
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
            if item.get("required") is True and not entries:
                report.error(
                    "REQUIRED_VERIFICATION_OBLIGATION",
                    f"{location}.verification_obligations.{kind}",
                    "required acceptance must explicitly declare at least one obligation; use an explicit not-applicable reason when the partition does not apply",
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
