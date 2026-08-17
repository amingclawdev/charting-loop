"""Work-row, Position-timeline, Guide, and advisory-reminder projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from typing import Any

from .acceptance import validate_acceptance_ledger
from .capabilities import validate_capability_registry
from .core import CorridorKitError, canonical_json_bytes, load_json, sha256_json


WORK_BACKLOG_SCHEMA = "charting-loop/task-work-backlog/v1"
POSITION_EVENT_SCHEMA = "charting-loop/position-event/v1"
POSITION_PROJECTION_SCHEMA = "charting-loop/position-projection/v1"
RUNTIME_GUIDE_SCHEMA = "charting-loop/runtime-guide/v1"
ROW_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
BACKLOG_STATES = frozenset({"compiled", "uncompiled"})
REMINDER_WHEN = frozenset(
    {"on_ready", "on_enter", "before_mutation", "before_complete", "on_blocked"}
)
ROW_EVENT_STATES = {
    "row_started": "in_progress",
    "row_progress": "in_progress",
    "row_blocked": "blocked",
    "row_completed": "done",
    "row_reopened": "pending",
    "row_not_applicable": "not_applicable",
}
MAX_TIMELINE_BYTES = 16 * 1024 * 1024


@dataclass
class WorkBacklogReport:
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
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "facts": self.facts}


def _nonempty(value: Any, report: WorkBacklogReport, location: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        report.error("NONEMPTY_STRING_REQUIRED", location, "must be a non-empty string")
        return None
    return value.strip()


def _strings(
    value: Any,
    report: WorkBacklogReport,
    location: str,
    *,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        report.error("STRING_LIST_REQUIRED", location, "must be a list of strings")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _nonempty(item, report, f"{location}[{index}]")
        if text is not None:
            result.append(text)
    if len(result) != len(set(result)):
        report.error("DUPLICATE_LIST_VALUE", location, "values must be unique")
    if nonempty and not result:
        report.error("NONEMPTY_LIST_REQUIRED", location, "must contain at least one value")
    return result


def _cycle_nodes(dependencies: dict[str, list[str]]) -> set[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            start = stack.index(node)
            cycles.update(stack[start:])
            return
        visiting.add(node)
        stack.append(node)
        for dependency in dependencies.get(node, []):
            if dependency in dependencies:
                visit(dependency, stack)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for row_id in dependencies:
        visit(row_id, [])
    return cycles


def validate_work_backlog(
    value: Any,
    *,
    acceptance_ids: set[str] | None = None,
    capability_ids: set[str] | None = None,
    allow_draft: bool = False,
) -> WorkBacklogReport:
    """Validate immutable work definitions and all dependency/link closures."""

    report = WorkBacklogReport()
    expected_top = {"schema_version", "state", "acceptance_ledger_digest", "rows"}
    if not isinstance(value, dict):
        report.error("OBJECT_REQUIRED", "$", "must be an object")
        return report
    if set(value) != expected_top:
        report.error(
            "EXACT_FIELDS_REQUIRED",
            "$",
            f"must contain exactly {sorted(expected_top)}; got {sorted(value)}",
        )
    if value.get("schema_version") != WORK_BACKLOG_SCHEMA:
        report.error("SCHEMA_VERSION", "$.schema_version", f"must equal {WORK_BACKLOG_SCHEMA!r}")
    state = value.get("state")
    if state not in BACKLOG_STATES:
        report.error("BACKLOG_STATE", "$.state", f"must be one of {sorted(BACKLOG_STATES)}")
    ledger_digest = value.get("acceptance_ledger_digest")
    if ledger_digest is not None and (
        not isinstance(ledger_digest, str) or not SHA256_RE.fullmatch(ledger_digest)
    ):
        report.error("ACCEPTANCE_LEDGER_DIGEST", "$.acceptance_ledger_digest", "must be null or sha256:<64 lowercase hex>")

    rows_value = value.get("rows")
    if not isinstance(rows_value, list):
        report.error("ROW_LIST_REQUIRED", "$.rows", "must be a list")
        rows_value = []
    if state == "uncompiled":
        if rows_value:
            report.error("UNCOMPILED_BACKLOG_HAS_ROWS", "$.rows", "uncompiled starter must not imply task rows")
        if ledger_digest is not None:
            report.error("UNCOMPILED_BACKLOG_HAS_LEDGER", "$.acceptance_ledger_digest", "uncompiled starter must not bind a task ledger")
        if not allow_draft:
            report.error("UNCOMPILED_BACKLOG", "$.state", "final backlog must be compiled")
    elif state == "compiled":
        if not rows_value:
            report.error("COMPILED_ROWS_NONEMPTY", "$.rows", "compiled backlog needs at least one row")
        if ledger_digest is None:
            report.error("COMPILED_LEDGER_DIGEST_REQUIRED", "$.acceptance_ledger_digest", "compiled backlog must bind ACCEPTANCE.json")

    row_fields = {
        "row_id",
        "title",
        "acceptance_ids",
        "depends_on",
        "scope",
        "done_when",
        "capability_ids",
        "reminders",
    }
    reminder_fields = {"reminder_id", "when", "message", "acceptance_ids"}
    row_ids: list[str] = []
    dependencies: dict[str, list[str]] = {}
    all_bound_acceptance: set[str] = set()
    reminder_ids: list[str] = []
    referenced_capabilities: set[str] = set()
    for index, row_value in enumerate(rows_value):
        location = f"$.rows[{index}]"
        if not isinstance(row_value, dict):
            report.error("ROW_OBJECT_REQUIRED", location, "must be an object")
            continue
        if set(row_value) != row_fields:
            report.error("EXACT_ROW_FIELDS", location, f"must contain exactly {sorted(row_fields)}; got {sorted(row_value)}")
        row_id = _nonempty(row_value.get("row_id"), report, f"{location}.row_id")
        if row_id is not None:
            if not ROW_ID_RE.fullmatch(row_id):
                report.error("ROW_ID_FORMAT", f"{location}.row_id", "must be a stable token")
            row_ids.append(row_id)
        _nonempty(row_value.get("title"), report, f"{location}.title")
        bound_ids = _strings(row_value.get("acceptance_ids"), report, f"{location}.acceptance_ids", nonempty=True)
        all_bound_acceptance.update(bound_ids)
        depends_on = _strings(row_value.get("depends_on"), report, f"{location}.depends_on")
        if row_id is not None:
            dependencies[row_id] = depends_on
            if row_id in depends_on:
                report.error("SELF_DEPENDENCY", f"{location}.depends_on", "row cannot depend on itself")
        scope = row_value.get("scope")
        if not isinstance(scope, dict) or not scope:
            report.error("NONEMPTY_SCOPE", f"{location}.scope", "must be a non-empty object")
        _strings(row_value.get("done_when"), report, f"{location}.done_when", nonempty=True)
        capability_refs = _strings(row_value.get("capability_ids"), report, f"{location}.capability_ids")
        referenced_capabilities.update(capability_refs)
        reminders = row_value.get("reminders")
        if not isinstance(reminders, list):
            report.error("REMINDER_LIST_REQUIRED", f"{location}.reminders", "must be a list")
            reminders = []
        for reminder_index, reminder in enumerate(reminders):
            reminder_location = f"{location}.reminders[{reminder_index}]"
            if not isinstance(reminder, dict):
                report.error("REMINDER_OBJECT_REQUIRED", reminder_location, "must be an object")
                continue
            if set(reminder) != reminder_fields:
                report.error("EXACT_REMINDER_FIELDS", reminder_location, f"must contain exactly {sorted(reminder_fields)}; got {sorted(reminder)}")
            reminder_id = _nonempty(reminder.get("reminder_id"), report, f"{reminder_location}.reminder_id")
            if reminder_id is not None:
                if not ROW_ID_RE.fullmatch(reminder_id):
                    report.error("REMINDER_ID_FORMAT", f"{reminder_location}.reminder_id", "must be a stable token")
                reminder_ids.append(reminder_id)
            if reminder.get("when") not in REMINDER_WHEN:
                report.error("REMINDER_WHEN", f"{reminder_location}.when", f"must be one of {sorted(REMINDER_WHEN)}")
            _nonempty(reminder.get("message"), report, f"{reminder_location}.message")
            reminder_acceptance = _strings(reminder.get("acceptance_ids"), report, f"{reminder_location}.acceptance_ids", nonempty=True)
            for acceptance_id in reminder_acceptance:
                if acceptance_id not in bound_ids:
                    report.error("REMINDER_ACCEPTANCE_OUTSIDE_ROW", f"{reminder_location}.acceptance_ids", f"{acceptance_id!r} is not bound to the row")

    known_rows = set(row_ids)
    if len(row_ids) != len(known_rows):
        report.error("DUPLICATE_ROW_ID", "$.rows", "row IDs must be unique")
    if len(reminder_ids) != len(set(reminder_ids)):
        report.error("DUPLICATE_REMINDER_ID", "$.rows", "reminder IDs must be globally unique")
    for row_id, dependency_ids in dependencies.items():
        for dependency_id in dependency_ids:
            if dependency_id not in known_rows:
                report.error("UNKNOWN_ROW_DEPENDENCY", f"row:{row_id}", f"unknown dependency {dependency_id!r}")
    cycles = sorted(_cycle_nodes(dependencies))
    if cycles:
        report.error("ROW_DEPENDENCY_CYCLE", "$.rows", f"cyclic rows: {cycles}")
    if acceptance_ids is not None:
        for acceptance_id in sorted(all_bound_acceptance - acceptance_ids):
            report.error("UNKNOWN_ACCEPTANCE_ID", "$.rows", f"unknown acceptance ID {acceptance_id!r}")
        for acceptance_id in sorted(acceptance_ids - all_bound_acceptance):
            report.error("UNBOUND_ACCEPTANCE_ID", "$.rows", f"acceptance ID {acceptance_id!r} has no work row")
    if capability_ids is not None:
        for capability_id in sorted(referenced_capabilities - capability_ids):
            report.error("UNKNOWN_CAPABILITY_ID", "$.rows", f"unknown capability ID {capability_id!r}")
    if allow_draft and state == "uncompiled":
        report.warning("UNCOMPILED_WORK_SURFACE", "$.state", "Builder must compile rows before Corridor freeze")
    report.facts = {
        "schema_version": value.get("schema_version"),
        "state": state,
        "row_ids": row_ids,
        "acceptance_ids": sorted(all_bound_acceptance),
        "capability_ids": sorted(referenced_capabilities),
        "dependency_cycle_rows": cycles,
        "backlog_digest": sha256_json(value) if not report.errors else None,
        "advisory_only": True,
        "authorizes_mutation": False,
    }
    return report


def validate_work_files(
    work_path: Path,
    *,
    acceptance_path: Path,
    capability_path: Path,
    allow_draft: bool = False,
) -> WorkBacklogReport:
    try:
        work = load_json(work_path)
        acceptance = load_json(acceptance_path)
        capabilities = load_json(capability_path)
    except CorridorKitError as exc:
        report = WorkBacklogReport()
        report.error("JSON_INPUT", str(work_path), str(exc))
        return report
    acceptance_report = validate_acceptance_ledger(acceptance, allow_draft=allow_draft)
    capability_report = validate_capability_registry(capabilities, allow_draft=allow_draft)
    report = validate_work_backlog(
        work,
        acceptance_ids=set(acceptance_report.facts.get("acceptance_ids", [])),
        capability_ids=set(capability_report.facts.get("capability_ids", [])),
        allow_draft=allow_draft,
    )
    if acceptance_report.ok and work.get("acceptance_ledger_digest") not in (None, sha256_json(acceptance)):
        report.error("ACCEPTANCE_DIGEST_MISMATCH", "$.acceptance_ledger_digest", "does not bind the supplied acceptance ledger")
    for error in acceptance_report.errors:
        report.error("ACCEPTANCE_" + error["code"], error["location"], error["message"])
    for error in capability_report.errors:
        report.error("CAPABILITY_" + error["code"], error["location"], error["message"])
    report.facts["acceptance_ledger_digest"] = sha256_json(acceptance) if acceptance_report.ok else None
    report.facts["capability_registry_digest"] = capability_report.facts.get("registry_digest")
    report.facts["task_ready"] = bool(
        report.ok
        and acceptance_report.facts.get("task_ready")
        and work.get("state") == "compiled"
        and capabilities.get("state") == "compiled"
    )
    return report


def starter_work_backlog() -> dict[str, Any]:
    return {
        "schema_version": WORK_BACKLOG_SCHEMA,
        "state": "uncompiled",
        "acceptance_ledger_digest": None,
        "rows": [],
    }


def _load_timeline(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise CorridorKitError(f"timeline must be a regular non-symlink file: {path}")
    if path.stat().st_size > MAX_TIMELINE_BYTES:
        raise CorridorKitError(f"timeline exceeds {MAX_TIMELINE_BYTES} bytes: {path}")
    events: list[dict[str, Any]] = []
    previous_hash: str | None = None
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise CorridorKitError(f"timeline contains a blank line at {index}")
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise CorridorKitError(f"invalid timeline JSON at line {index}: {exc}") from exc
        if not isinstance(event, dict):
            raise CorridorKitError(f"timeline event at line {index} must be an object")
        expected_fields = {
            "schema_version", "event_id", "observed_at", "actor", "event_type",
            "row_id", "status", "details", "previous_event_hash", "event_hash",
        }
        if set(event) != expected_fields:
            raise CorridorKitError(f"timeline event at line {index} has wrong fields")
        if event.get("schema_version") != POSITION_EVENT_SCHEMA:
            raise CorridorKitError(f"timeline schema mismatch at line {index}")
        if event.get("event_id") != f"evt-{index:06d}":
            raise CorridorKitError(f"timeline sequence mismatch at line {index}")
        if event.get("previous_event_hash") != previous_hash:
            raise CorridorKitError(f"timeline previous hash mismatch at line {index}")
        claimed = event.get("event_hash")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        actual = sha256_json(unsigned)
        if claimed != actual:
            raise CorridorKitError(f"timeline event hash mismatch at line {index}")
        previous_hash = claimed
        events.append(event)
    return events


def load_position_timeline(path: Path) -> list[dict[str, Any]]:
    """Read and verify the entire append-only hash chain."""

    return _load_timeline(Path(path))


def append_position_event(
    path: Path,
    *,
    actor: str,
    event_type: str,
    status: str,
    row_id: str | None = None,
    details: dict[str, Any] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Append one structurally valid observation without making an authority claim."""

    for name, value in (("actor", actor), ("event_type", event_type), ("status", status)):
        if not isinstance(value, str) or not value.strip():
            raise CorridorKitError(f"{name} must be a non-empty string")
    if row_id is not None and (not isinstance(row_id, str) or not ROW_ID_RE.fullmatch(row_id)):
        raise CorridorKitError("row_id must be null or a stable token")
    if event_type.startswith("row_") and row_id is None:
        raise CorridorKitError("row events require row_id")
    if event_type in ROW_EVENT_STATES and status != ROW_EVENT_STATES[event_type]:
        raise CorridorKitError(f"{event_type} status must equal {ROW_EVENT_STATES[event_type]!r}")
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise CorridorKitError("details must be an object")
    canonical_json_bytes(details)
    timestamp = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise CorridorKitError("observed_at must be a non-empty string")

    path = Path(path)
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise CorridorKitError(f"timeline parent must be a real directory: {parent}")
    if path.is_symlink():
        raise CorridorKitError(f"timeline symlink is forbidden: {path}")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            events = _load_timeline(path)
            unsigned = {
                "schema_version": POSITION_EVENT_SCHEMA,
                "event_id": f"evt-{len(events) + 1:06d}",
                "observed_at": timestamp,
                "actor": actor.strip(),
                "event_type": event_type.strip(),
                "row_id": row_id,
                "status": status.strip(),
                "details": details,
                "previous_event_hash": events[-1]["event_hash"] if events else None,
            }
            event = {**unsigned, "event_hash": sha256_json(unsigned)}
            handle.seek(0, os.SEEK_END)
            handle.write(canonical_json_bytes(event).decode("utf-8") + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return event
    except Exception:
        raise


def project_position(work: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Project row state and a current row from frozen definitions plus RAW events."""

    report = validate_work_backlog(work, allow_draft=True)
    if not report.ok:
        raise CorridorKitError(f"invalid work backlog: {report.errors}")
    rows = work.get("rows", [])
    known = {row["row_id"]: row for row in rows}
    explicit: dict[str, tuple[str, int]] = {}
    unknown_event_rows: list[str] = []
    for index, event in enumerate(events):
        row_id = event.get("row_id")
        event_type = event.get("event_type")
        if row_id is None or event_type not in ROW_EVENT_STATES:
            continue
        if row_id not in known:
            unknown_event_rows.append(row_id)
            continue
        explicit[row_id] = (ROW_EVENT_STATES[event_type], index)

    terminal = {
        row_id
        for row_id, (state, _) in explicit.items()
        if state in {"done", "not_applicable"}
    }
    projected_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_id = row["row_id"]
        if row_id in explicit:
            state, event_index = explicit[row_id]
        else:
            state = "ready" if all(dep in terminal for dep in row["depends_on"]) else "pending"
            event_index = -1
        projected_rows.append({
            "row_id": row_id,
            "state": state,
            "definition_index": index,
            "last_event_index": event_index,
            "acceptance_ids": row["acceptance_ids"],
            "depends_on": row["depends_on"],
        })
    active = [row for row in projected_rows if row["state"] in {"in_progress", "blocked"}]
    active.sort(key=lambda row: row["last_event_index"], reverse=True)
    ready = [row for row in projected_rows if row["state"] == "ready"]
    current = active[0] if active else (ready[0] if ready else None)
    warnings: list[str] = []
    if len(active) > 1:
        warnings.append("multiple_active_rows_observed")
    if unknown_event_rows:
        warnings.append("timeline_references_unknown_rows")
    return {
        "schema_version": POSITION_PROJECTION_SCHEMA,
        "work_backlog_digest": sha256_json(work),
        "timeline_head": events[-1]["event_hash"] if events else None,
        "event_count": len(events),
        "rows": projected_rows,
        "current_row_id": current["row_id"] if current else None,
        "complete": bool(projected_rows) and all(
            row["state"] in {"done", "not_applicable"} for row in projected_rows
        ),
        "warnings": warnings,
        "raw_observation_only": True,
        "authorizes_mutation": False,
    }


def runtime_guide(
    work: dict[str, Any],
    capabilities: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the current row, bounded reusable operations, and reminders."""

    capability_report = validate_capability_registry(capabilities, allow_draft=True)
    work_report = validate_work_backlog(
        work,
        capability_ids=set(capability_report.facts.get("capability_ids", [])),
        allow_draft=True,
    )
    if not capability_report.ok or not work_report.ok:
        raise CorridorKitError(
            f"invalid runtime inputs: work={work_report.errors}; capabilities={capability_report.errors}"
        )
    projection = project_position(work, events)
    current_id = projection["current_row_id"]
    row = next((item for item in work.get("rows", []) if item["row_id"] == current_id), None)
    by_capability = {item["capability_id"]: item for item in capabilities.get("capabilities", [])}
    selected = [by_capability[item] for item in row["capability_ids"]] if row else []
    reminders = []
    if row:
        reminders.append({
            "reminder_id": "runtime.recheck-acceptance",
            "when": "on_enter",
            "message": "Re-read the bound acceptance items and live state before acting.",
            "acceptance_ids": row["acceptance_ids"],
            "source": "runtime",
        })
        reminders.extend({**item, "source": "work_row"} for item in row["reminders"])
    return {
        "schema_version": RUNTIME_GUIDE_SCHEMA,
        "work_state": work_report.facts.get("state"),
        "capability_state": capability_report.facts.get("state"),
        "current_row": row,
        "position": projection,
        "capabilities": selected,
        "reminders": reminders,
        "advisory_only": True,
        "authorizes_mutation": False,
        "blocking_gate": False,
    }


def load_runtime_guide(work_path: Path, capability_path: Path, timeline_path: Path) -> dict[str, Any]:
    return runtime_guide(load_json(work_path), load_json(capability_path), load_position_timeline(timeline_path))
