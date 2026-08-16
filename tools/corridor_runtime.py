#!/usr/bin/env python3
"""Build and validate non-normative Charting Loop runtime-evidence bundles.

This module intentionally does not validate or unlock Candidate v2 artifacts.  Runtime
receipts remain outside Candidate semantic identity and demonstrate only the bounded
engineering fixture that produced them.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit


DEMO_SCHEMA = "charting-loop/engineering-demo/v1"
BUNDLE_SCHEMA = "charting-loop/runtime-evidence-bundle/v1"
GUIDE_RECEIPT_SCHEMA = "charting-loop/guide-receipt/v1"
TRAVERSAL_RECEIPT_SCHEMA = "charting-loop/traversal-receipt/v1"
PATH_CERTIFICATE_SCHEMA = "charting-loop/path-certificate/v1"
EVIDENTIAL_WARRANTY_SCHEMA = "charting-loop/evidential-warranty/v1"
AUTHORITY_WARRANTY_SCHEMA = "charting-loop/authority-warranty/v1"
WORLD_PROJECTOR_SCHEMA = "charting-loop/world-projector/v1"
USAGE_RECEIPT_SCHEMA = "charting-loop/usage-receipt/v1"
ACCEPTANCE_RECORD_SCHEMA = "charting-loop/ai-acceptance-record/v1"
PACKAGE_COST_SCHEMA = "charting-loop/package-cost/v1"
MEASUREMENT_PLAN_SCHEMA = "charting-loop/measurement-plan/v1"
ACCEPTANCE_TRUSTED_CONTEXT_SCHEMA = "charting-loop/acceptance-trusted-context/v1"
SESSION_RECEIPT_SCHEMA = "charting-loop/ai-session-receipt/v1"
REPLAY_RECEIPT_SCHEMA = "charting-loop/acceptance-replay-receipt/v1"
SOURCE_VALIDATION_SCHEMA = "charting-loop/acceptance-source-validation/v1"

ALLOWED_EVIDENCE_KINDS = {
    "candidate-artifact",
    "runner-log",
    "task-output",
    "transcript",
    "verifier-output",
}

USAGE_STAGES = (
    "construction",
    "guided_execution",
    "reentry_revalidation",
    "retry",
)
CORE_USAGE_STAGES = USAGE_STAGES[:-1]
USAGE_METRICS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "wall_time_ms",
    "tool_calls",
)

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
GIT_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
MAX_JSON_BYTES = 5 * 1024 * 1024
# Keep canonical JSON serialization below CPython's integer-to-string safety limit
# while retaining exact arithmetic for deliberately large accounting probes.
MAX_JSON_INTEGER_BITS = 4096


def _reject_out_of_range_integers(value: Any) -> None:
    """Enforce the declared integer bound as a canonicalization invariant.

    ``MAX_JSON_INTEGER_BITS`` is validated per field, but ``json.dumps`` will
    happily serialize an arbitrarily large int. Without this check a receipt
    that already failed ``INTEGER_RANGE`` still receives a well-formed digest,
    so an invalid record would carry a valid-looking canonical hash.
    """

    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if value.bit_length() > MAX_JSON_INTEGER_BITS:
            raise ValueError(
                f"integer exceeds {MAX_JSON_INTEGER_BITS} bits for canonical JSON evidence"
            )
        return
    if isinstance(value, dict):
        for item in value.values():
            _reject_out_of_range_integers(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_out_of_range_integers(item)


def canonical_json_bytes(value: Any) -> bytes:
    _reject_out_of_range_integers(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _json_exact_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON values without Python's bool/int/float value coercions."""

    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return set(actual) == set(expected) and all(
            _json_exact_equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _json_exact_equal(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"digest input must be a regular non-symlink file: {path}")
    size = path.stat().st_size
    if size > MAX_JSON_BYTES:
        raise ValueError(f"digest input exceeds {MAX_JSON_BYTES} bytes: {path}")
    return sha256_bytes(path.read_bytes())


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    if path.is_symlink():
        raise ValueError(f"symlink JSON input is forbidden: {path}")
    size = path.stat().st_size
    if size > MAX_JSON_BYTES:
        raise ValueError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value: {item}")
            ),
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported limit") from exc
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in item):
            raise ValueError("JSON contains an unpaired Unicode surrogate")
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


@dataclass
class ValidationReport:
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


class DemoDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _exact_keys(
    value: Any,
    expected: set[str],
    report: ValidationReport,
    location: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        report.error("OBJECT", location, "must be an object")
        return None
    actual = set(value)
    if actual != expected:
        report.error(
            "FIELDS",
            location,
            f"must contain exactly {sorted(expected)}; got {sorted(actual)}",
        )
    return value


def _string(value: Any, report: ValidationReport, location: str) -> str | None:
    if not isinstance(value, str) or not value:
        report.error("STRING", location, "must be a non-empty string")
        return None
    return value


def _digest(value: Any, report: ValidationReport, location: str) -> str | None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        report.error("DIGEST", location, "must be a lowercase sha256 digest")
        return None
    return value


def _strict_https(value: Any, report: ValidationReport, location: str) -> str | None:
    text = _string(value, report, location)
    if text is None:
        return None
    try:
        parts = urlsplit(text)
        _ = parts.port
    except ValueError as exc:
        report.error("HTTPS_URL", location, f"invalid URL: {exc}")
        return None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or any(char.isspace() or ord(char) < 32 for char in text)
        or "\\" in text
    ):
        report.error("HTTPS_URL", location, "must be a strict credential-free HTTPS URL")
        return None
    return text


def _boolean(value: Any, report: ValidationReport, location: str) -> bool | None:
    if type(value) is not bool:
        report.error("BOOLEAN", location, "must be a JSON boolean")
        return None
    return value


def _integer(value: Any, report: ValidationReport, location: str) -> int | None:
    if type(value) is not int:
        report.error("INTEGER", location, "must be a JSON integer")
        return None
    return value


def _nonnegative_integer(
    value: Any, report: ValidationReport, location: str
) -> int | None:
    number = _integer(value, report, location)
    if number is not None and number < 0:
        report.error("NONNEGATIVE_INTEGER", location, "must be non-negative")
        return None
    if number is not None and number.bit_length() > MAX_JSON_INTEGER_BITS:
        report.error(
            "INTEGER_RANGE",
            location,
            f"must fit within {MAX_JSON_INTEGER_BITS} bits for canonical JSON evidence",
        )
        return None
    return number


def _list(value: Any, report: ValidationReport, location: str) -> list[Any] | None:
    if not isinstance(value, list):
        report.error("LIST", location, "must be a list")
        return None
    return value


def _unique_map(
    values: Any,
    key: str,
    report: ValidationReport,
    location: str,
) -> dict[str, dict[str, Any]]:
    records = _list(values, report, location) or []
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        item_location = f"{location}[{index}]"
        if not isinstance(record, dict):
            report.error("OBJECT", item_location, "must be an object")
            continue
        identity = _string(record.get(key), report, f"{item_location}.{key}")
        if identity is None:
            continue
        if identity in result:
            report.error("DUPLICATE_ID", f"{item_location}.{key}", "must be unique")
            continue
        result[identity] = record
    return result


def _validate_stage_usage(
    value: Any,
    report: ValidationReport,
    location: str,
) -> dict[str, Any] | None:
    stage = _exact_keys(
        value,
        {
            "stage",
            "stage_receipt_id",
            "attempt_id",
            "retry_of_attempt_id",
            "retry_of_stage",
            "assessment_status",
            *USAGE_METRICS,
        },
        report,
        location,
    )
    if stage is None:
        return None
    stage_id = stage.get("stage")
    if not isinstance(stage_id, str) or stage_id not in USAGE_STAGES:
        report.error(
            "USAGE_STAGE",
            f"{location}.stage",
            f"must be one of {list(USAGE_STAGES)}",
        )
    _string(stage.get("stage_receipt_id"), report, f"{location}.stage_receipt_id")
    _string(stage.get("attempt_id"), report, f"{location}.attempt_id")
    if stage_id == "retry":
        retry_of_attempt_id = _string(
            stage.get("retry_of_attempt_id"),
            report,
            f"{location}.retry_of_attempt_id",
        )
        retry_of_stage = stage.get("retry_of_stage")
        if not isinstance(retry_of_stage, str) or retry_of_stage not in CORE_USAGE_STAGES:
            report.error(
                "RETRY_ROOT_STAGE",
                f"{location}.retry_of_stage",
                f"must be one of {list(CORE_USAGE_STAGES)}",
            )
        if retry_of_attempt_id == stage.get("attempt_id"):
            report.error(
                "RETRY_SELF_REFERENCE",
                f"{location}.retry_of_attempt_id",
                "must refer to a distinct core attempt",
            )
    else:
        for field_name in ("retry_of_attempt_id", "retry_of_stage"):
            if stage.get(field_name) is not None:
                report.error(
                    "CORE_RETRY_ANCESTRY",
                    f"{location}.{field_name}",
                    "must be null for a core stage record",
                )
    status = stage.get("assessment_status")
    if not isinstance(status, str) or status not in {
        "measured",
        "not_assessed",
        "not_applicable",
    }:
        report.error(
            "USAGE_STATUS",
            f"{location}.assessment_status",
            "must be measured, not_assessed, or not_applicable",
        )
    if stage_id in CORE_USAGE_STAGES and status == "not_applicable":
        report.error(
            "CORE_STAGE_NOT_APPLICABLE",
            f"{location}.assessment_status",
            "core construction, execution, and re-entry stages are always applicable; use not_assessed with null metrics when measurement is unavailable",
        )
    measured: dict[str, int] = {}
    for metric in USAGE_METRICS:
        metric_location = f"{location}.{metric}"
        raw = stage.get(metric)
        if status == "measured":
            number = _nonnegative_integer(raw, report, metric_location)
            if number is not None:
                measured[metric] = number
        elif raw is not None:
            report.error(
                "USAGE_UNMEASURED_VALUE",
                metric_location,
                "must be null unless assessment_status is measured",
            )
    if status == "measured":
        if measured.get("cached_input_tokens", 0) > measured.get("input_tokens", 0):
            report.error(
                "CACHED_INPUT_SUBSET",
                f"{location}.cached_input_tokens",
                "cached input is a subset of input_tokens, not an additive quantity",
            )
        if measured.get("reasoning_output_tokens", 0) > measured.get("output_tokens", 0):
            report.error(
                "REASONING_OUTPUT_SUBSET",
                f"{location}.reasoning_output_tokens",
                "reasoning output is a subset of output_tokens, not an additive quantity",
            )
    return stage


def package_cost_from_usage(
    usage_receipt: dict[str, Any], *, amortized_reuses: int = 1
) -> dict[str, Any]:
    """Derive one primary package cost and non-additive secondary views.

    Validation is intentionally separate so callers can inspect a fail-closed record.
    Primary totals are null unless every required stage is measured.  Secondary views
    are projections of the same measurements and must never be added to primary.
    """

    if type(amortized_reuses) is not int or amortized_reuses < 1:
        raise ValueError("amortized_reuses must be a positive integer")
    records = [item for item in usage_receipt.get("stages", []) if isinstance(item, dict)]
    core = {
        item.get("stage"): item
        for item in records
        if item.get("stage") in CORE_USAGE_STAGES
    }
    retries = [item for item in records if item.get("stage") == "retry"]

    def applicable(item: dict[str, Any]) -> bool:
        return (
            item.get("stage") in CORE_USAGE_STAGES
            or item.get("assessment_status") != "not_applicable"
        )

    def missing_for(view_records: list[dict[str, Any]], required: tuple[str, ...]) -> list[str]:
        missing = [stage for stage in required if stage not in core]
        missing.extend(
            str(item.get("stage_receipt_id") or item.get("stage") or "unknown")
            for item in view_records
            if applicable(item) and item.get("assessment_status") != "measured"
        )
        return list(dict.fromkeys(missing))

    def totals(
        view_records: list[dict[str, Any]], missing: list[str]
    ) -> dict[str, int | None]:
        if missing:
            return {metric: None for metric in USAGE_METRICS}
        measured = [item for item in view_records if item.get("assessment_status") == "measured"]
        return {
            metric: sum(int(item[metric]) for item in measured)
            for metric in USAGE_METRICS
        }

    primary_records = records
    primary_missing = missing_for(primary_records, CORE_USAGE_STAGES)
    primary_totals = totals(primary_records, primary_missing)
    execution_records = [
        item
        for item in records
        if item.get("stage") in {"guided_execution", "reentry_revalidation"}
        or (
            item.get("stage") == "retry"
            and item.get("retry_of_stage")
            in {"guided_execution", "reentry_revalidation"}
        )
    ]
    execution_missing = missing_for(
        execution_records, ("guided_execution", "reentry_revalidation")
    )
    execution_totals = totals(execution_records, execution_missing)
    construction_records = [
        item
        for item in records
        if item.get("stage") == "construction"
        or (
            item.get("stage") == "retry"
            and item.get("retry_of_stage") == "construction"
        )
    ]
    construction_missing = missing_for(construction_records, ("construction",))
    amortized_missing = list(dict.fromkeys(construction_missing + execution_missing))
    construction_totals = totals(construction_records, construction_missing)
    amortized: dict[str, Any] = {
        "assumed_reuses": amortized_reuses,
        "missing_stages": amortized_missing,
    }
    for metric in USAGE_METRICS:
        if amortized_missing:
            amortized[metric] = None
            continue
        amortized[metric] = {
            "numerator": int(execution_totals[metric]) * amortized_reuses
            + int(construction_totals[metric]),
            "denominator": amortized_reuses,
        }
    return {
        "schema_version": PACKAGE_COST_SCHEMA,
        "usage_receipt_sha256": sha256_json(usage_receipt),
        "primary": {
            "view_id": "construction_plus_execution",
            **primary_totals,
            "missing_stages": primary_missing,
        },
        "secondary": {
            "non_additive": True,
            "execution_only": {
                **execution_totals,
                "missing_stages": execution_missing,
            },
            "amortized": amortized,
        },
    }


def validate_usage_receipt(value: Any) -> ValidationReport:
    report = ValidationReport()
    receipt = _exact_keys(
        value,
        {
            "schema_version",
            "receipt_id",
            "run_id",
            "run_sha256",
            "session_id",
            "attempt_id",
            "measurement_plan_sha256",
            "stages",
        },
        report,
        "usage-receipt",
    )
    if receipt is None:
        return report
    if receipt.get("schema_version") != USAGE_RECEIPT_SCHEMA:
        report.error(
            "USAGE_SCHEMA",
            "usage-receipt.schema_version",
            f"must be {USAGE_RECEIPT_SCHEMA}",
        )
    for key in ("receipt_id", "run_id", "session_id", "attempt_id"):
        _string(receipt.get(key), report, f"usage-receipt.{key}")
    _digest(receipt.get("run_sha256"), report, "usage-receipt.run_sha256")
    _digest(
        receipt.get("measurement_plan_sha256"),
        report,
        "usage-receipt.measurement_plan_sha256",
    )
    stages = _list(receipt.get("stages"), report, "usage-receipt.stages") or []
    if len(stages) < len(USAGE_STAGES):
        report.error(
            "USAGE_STAGE_SET",
            "usage-receipt.stages",
            "must contain three core records followed by one or more retry records",
        )
    parsed: list[dict[str, Any]] = []
    for index, stage in enumerate(stages):
        valid = _validate_stage_usage(
            stage,
            report,
            f"usage-receipt.stages[{index}]",
        )
        if valid is not None:
            parsed.append(valid)
    for index, expected in enumerate(CORE_USAGE_STAGES):
        actual = parsed[index].get("stage") if index < len(parsed) else None
        if actual != expected:
            report.error(
                "USAGE_CORE_ORDER",
                f"usage-receipt.stages[{index}].stage",
                f"must be {expected}",
            )
    if any(item.get("stage") != "retry" for item in parsed[len(CORE_USAGE_STAGES) :]):
        report.error(
            "USAGE_RETRY_ORDER",
            "usage-receipt.stages",
            "all records after the core stages must be retry records",
        )
    stage_receipt_ids = [
        item["stage_receipt_id"]
        for item in parsed
        if isinstance(item.get("stage_receipt_id"), str)
        and bool(item["stage_receipt_id"])
    ]
    attempt_ids = [
        item["attempt_id"]
        for item in parsed
        if isinstance(item.get("attempt_id"), str) and bool(item["attempt_id"])
    ]
    if len(stage_receipt_ids) != len(set(stage_receipt_ids)):
        report.error(
            "DUPLICATE_STAGE_RECEIPT_ID",
            "usage-receipt.stages",
            "stage_receipt_id values must be unique",
        )
    if len(attempt_ids) != len(set(attempt_ids)):
        report.error(
            "DUPLICATE_ATTEMPT_ID",
            "usage-receipt.stages",
            "attempt_id values must be unique",
        )
    core_by_attempt = {
        item["attempt_id"]: item
        for item in parsed
        if item.get("stage") in CORE_USAGE_STAGES
        and isinstance(item.get("attempt_id"), str)
        and bool(item["attempt_id"])
    }
    for index, item in enumerate(parsed):
        if item.get("stage") != "retry":
            continue
        retry_of_attempt_id = item.get("retry_of_attempt_id")
        root = (
            core_by_attempt.get(retry_of_attempt_id)
            if isinstance(retry_of_attempt_id, str)
            else None
        )
        if root is None:
            report.error(
                "RETRY_ROOT_ATTEMPT",
                f"usage-receipt.stages[{index}].retry_of_attempt_id",
                "must resolve to a core attempt in this receipt",
            )
        elif root.get("stage") != item.get("retry_of_stage"):
            report.error(
                "RETRY_ROOT_JOIN",
                f"usage-receipt.stages[{index}].retry_of_stage",
                "must equal the resolved core attempt stage",
            )
    retry_records = [item for item in parsed if item.get("stage") == "retry"]
    not_applicable_retries = [
        item
        for item in retry_records
        if item.get("assessment_status") == "not_applicable"
    ]
    if not_applicable_retries and (
        len(retry_records) != 1 or len(not_applicable_retries) != 1
    ):
        report.error(
            "RETRY_NOT_APPLICABLE_CARDINALITY",
            "usage-receipt.stages",
            "not_applicable is the sole no-retry sentinel; it cannot coexist with another retry record",
        )
    try:
        receipt_sha256 = sha256_json(value) if isinstance(value, dict) else None
    except (OverflowError, RecursionError, TypeError, UnicodeError, ValueError) as exc:
        report.error(
            "CANONICAL_JSON",
            "usage-receipt",
            f"cannot canonicalize receipt: {type(exc).__name__}",
        )
        receipt_sha256 = None
    report.facts.update(
        {
            "usage_status": "measured"
            if report.ok
            and len(parsed) >= len(USAGE_STAGES)
            and all(
                stage.get("assessment_status") in {"measured", "not_applicable"}
                for stage in parsed
            )
            else "incomplete",
            "receipt_sha256": receipt_sha256,
        }
    )
    return report


def _measurement_plan_report(value: Any) -> ValidationReport:
    report = ValidationReport()
    plan = _exact_keys(
        value,
        {
            "schema_version",
            "usage_receipt_schema",
            "package_cost_schema",
            "required_usage_stages",
            "raw_evidence_profile",
            "independent_replay_required",
        },
        report,
        "measurement-plan",
    )
    if plan is None:
        return report
    expected = {
        "schema_version": MEASUREMENT_PLAN_SCHEMA,
        "usage_receipt_schema": USAGE_RECEIPT_SCHEMA,
        "package_cost_schema": PACKAGE_COST_SCHEMA,
        "required_usage_stages": list(USAGE_STAGES),
        "raw_evidence_profile": "complete-digest-bound",
        "independent_replay_required": True,
    }
    if not _json_exact_equal(plan, expected):
        report.error(
            "MEASUREMENT_PLAN",
            "measurement-plan",
            "must exactly match the CL-014 formal evidence plan",
        )
    return report


def _acceptance_gate(
    *, clean_pair_ids: list[str], replay_verified: bool,
    trusted_inputs_verified: bool, validation_ok: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    if len(clean_pair_ids) < 2:
        blockers.append("fewer_than_two_clean_pairs")
    if not replay_verified:
        blockers.append("independent_replay_not_verified")
    if not trusted_inputs_verified:
        blockers.append("trusted_inputs_not_verified")
    if not validation_ok:
        blockers.append("validation_errors")
    return {
        "instrumented_acceptance_pilot_ready": not blockers,
        "formal_comparison_ready": False,
        "clean_pair_ids": clean_pair_ids,
        "required_clean_pair_count": 2,
        "blockers": blockers,
        "benchmark_result": False,
        "causal_claim_allowed": False,
        "adoption_claim_allowed": False,
        "authority_warranty_state": "not_assessed",
    }


def acceptance_gate_for_verified_inputs(
    *, clean_pair_ids: list[str], replay_verified: bool,
    trusted_inputs_verified: bool,
) -> dict[str, Any]:
    """Construct the only optimistic gate a trusted runner may submit.

    The full validator still re-derives this value after every structural and byte
    join.  Any error, including a caller-tampered gate, replaces readiness with the
    fail-closed ``validation_errors`` result in report facts.
    """

    return _acceptance_gate(
        clean_pair_ids=sorted(clean_pair_ids),
        replay_verified=replay_verified,
        trusted_inputs_verified=trusted_inputs_verified,
        validation_ok=True,
    )


def _safe_evidence_path(
    root: Path, value: Any, report: ValidationReport, location: str
) -> tuple[str, Path] | None:
    text = _evidence_relative_path(value, report, location)
    if text is None:
        return None
    pure = PurePosixPath(text)
    try:
        if root.is_symlink():
            raise OSError("evidence_root must not be a symlink")
        base = root.resolve(strict=True)
    except OSError:
        report.error("EVIDENCE_ROOT", str(root), "must be an existing directory")
        return None
    cursor = base
    for part in pure.parts:
        cursor /= part
        if cursor.is_symlink():
            report.error("EVIDENCE_PATH", location, "must not traverse a symlink")
            return None
    try:
        resolved = cursor.resolve(strict=True)
    except OSError:
        report.error("EVIDENCE_FILE", location, "referenced evidence file is missing")
        return None
    if base not in resolved.parents or not resolved.is_file():
        report.error("EVIDENCE_PATH", location, "must resolve to a regular file below evidence_root")
        return None
    return pure.as_posix(), resolved


def _evidence_relative_path(
    value: Any, report: ValidationReport, location: str
) -> str | None:
    text = _string(value, report, location)
    if text is None:
        return None
    pure = PurePosixPath(text)
    if (
        pure.is_absolute()
        or text != pure.as_posix()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or any(ord(char) < 32 or char == "\x7f" for char in text)
    ):
        report.error(
            "EVIDENCE_PATH",
            location,
            "must be a normalized safe-relative POSIX path",
        )
        return None
    return text


def _string_list(
    value: Any, report: ValidationReport, location: str, *, nonempty: bool = False
) -> list[str]:
    raw = _list(value, report, location)
    if raw is None:
        return []
    result: list[str] = []
    for index, item in enumerate(raw):
        text = _string(item, report, f"{location}[{index}]")
        if text is not None:
            result.append(text)
    if nonempty and not result:
        report.error("NONEMPTY_LIST", location, "must contain at least one value")
    if len(result) != len(set(result)):
        report.error("DUPLICATE_LIST_VALUE", location, "must not contain duplicates")
    return result


def _replay_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(record.get(key))
        for key in (
            "schema_version", "acceptance_id", "assembler", "source_validation_sha256",
            "run_bindings", "method_binding",
            "measurement_plan", "usage_receipts", "package_costs", "raw_evidence",
            "attempts", "pairs",
        )
    }


def trusted_context_from_verified_sources(
    record: dict[str, Any], source_validation: dict[str, Any]
) -> dict[str, Any]:
    """Project the out-of-band validator result consumed by acceptance validation.

    ``source_validation`` is deliberately not derived from the AcceptanceRecord.  The
    manual runner constructs it from successful method-index, STUDY, and RUN validator
    reports.  Receipt bytes and raw evidence are checked separately under evidence_root.
    """

    return {
        "schema_version": ACCEPTANCE_TRUSTED_CONTEXT_SCHEMA,
        "acceptance_id": record.get("acceptance_id"),
        "assembler": copy.deepcopy(record.get("assembler")),
        "source_validation": copy.deepcopy(source_validation),
        "source_validation_sha256": sha256_json(source_validation),
        "verified": True,
    }


def _validate_acceptance_record_impl(
    value: Any, *, trusted_context: dict[str, Any] | None = None,
    evidence_root: Path | None = None,
) -> ValidationReport:
    """Validate an instrumented acceptance package without synthesizing authority.

    A serialized record is never trusted by itself.  The optional ``trusted_context``
    is an out-of-band projection produced only after the runner has executed the full
    RUN/STUDY/catalog validators and hashed independently issued session/replay receipts.
    Even a fully verified package opens only the engineering pilot gate.
    """

    report = ValidationReport()
    record = _exact_keys(
        value,
        {
            "schema_version", "acceptance_id", "assembler",
            "source_validation_sha256", "run_bindings",
            "method_binding", "measurement_plan", "usage_receipts", "package_costs",
            "raw_evidence", "attempts", "pairs", "independent_replay", "gate",
        },
        report,
        "acceptance",
    )
    if record is None:
        return report
    if record.get("schema_version") != ACCEPTANCE_RECORD_SCHEMA:
        report.error("ACCEPTANCE_SCHEMA", "acceptance.schema_version", f"must be {ACCEPTANCE_RECORD_SCHEMA}")
    _string(record.get("acceptance_id"), report, "acceptance.acceptance_id")
    _digest(
        record.get("source_validation_sha256"),
        report,
        "acceptance.source_validation_sha256",
    )

    assembler = _exact_keys(
        record.get("assembler"), {"runner_id", "session_id", "invocation_id"},
        report, "acceptance.assembler",
    )
    if assembler is not None:
        for key in ("runner_id", "session_id", "invocation_id"):
            _string(assembler.get(key), report, f"acceptance.assembler.{key}")

    plan = record.get("measurement_plan")
    plan_report = _measurement_plan_report(plan)
    report.errors.extend(plan_report.errors)
    plan_sha = sha256_json(plan) if isinstance(plan, dict) else None

    common_keys = {
        "task_sha256", "world_comparison_sha256", "provider", "model", "runtime",
        "profile_sha256", "tools_sha256", "network_access", "budget_sha256",
        "stopping_rule_sha256", "evaluator_sha256", "trial", "seed",
    }
    run_keys = {
        "schema_version", "run_id", "run_sha256", "study_id", "study_sha256",
        "condition_id", "taskset_id", "task_id", "trial", "seed",
        "status", "system_condition", "knowledge_condition", "runner_id",
        "measurement_plan_sha256", "common_conditions", "common_condition_sha256",
    }
    runs_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(record.get("run_bindings"), report, "acceptance.run_bindings") or []):
        location = f"acceptance.run_bindings[{index}]"
        run = _exact_keys(raw, run_keys, report, location)
        if run is None:
            continue
        for key in (
            "schema_version", "run_id", "study_id", "condition_id", "taskset_id",
            "task_id", "seed", "status", "system_condition", "knowledge_condition", "runner_id",
        ):
            _string(run.get(key), report, f"{location}.{key}")
        _nonnegative_integer(run.get("trial"), report, f"{location}.trial")
        if run.get("schema_version") != "charting-loop/exogenous-run/v2":
            report.error(
                "RUN_SCHEMA",
                f"{location}.schema_version",
                "acceptance requires a validated exogenous RUN v2",
            )
        if run.get("status") != "completed":
            report.error(
                "RUN_STATUS",
                f"{location}.status",
                "acceptance evidence requires a completed RUN",
            )
        for key in ("run_sha256", "study_sha256", "measurement_plan_sha256", "common_condition_sha256"):
            _digest(run.get(key), report, f"{location}.{key}")
        if plan_sha is not None and run.get("measurement_plan_sha256") != plan_sha:
            report.error("RUN_PLAN_JOIN", f"{location}.measurement_plan_sha256", "must bind the exact measurement plan")
        common = _exact_keys(run.get("common_conditions"), common_keys, report, f"{location}.common_conditions")
        if common is not None:
            for key in ("task_sha256", "world_comparison_sha256", "profile_sha256", "tools_sha256", "budget_sha256", "stopping_rule_sha256", "evaluator_sha256"):
                _digest(common.get(key), report, f"{location}.common_conditions.{key}")
            for key in ("provider", "model", "runtime", "network_access", "seed"):
                _string(common.get(key), report, f"{location}.common_conditions.{key}")
            _nonnegative_integer(
                common.get("trial"), report, f"{location}.common_conditions.trial"
            )
            if common.get("trial") != run.get("trial") or common.get("seed") != run.get("seed"):
                report.error(
                    "COMMON_RUN_JOIN",
                    f"{location}.common_conditions",
                    "trial and seed must equal the bound RUN",
                )
            if run.get("common_condition_sha256") != sha256_json(common):
                report.error("COMMON_CONDITION_DIGEST", f"{location}.common_condition_sha256", "must derive from the closed nuisance-variable object")
        run_id = run.get("run_id")
        if isinstance(run_id, str) and run_id:
            if run_id in runs_by_id:
                report.error("DUPLICATE_RUN_BINDING", f"{location}.run_id", "must be unique")
            else:
                runs_by_id[run_id] = run

    method_keys = {
        "condition_id", "study_id", "study_schema_version", "study_sha256",
        "catalog_sha256", "version_id", "status", "source_commit", "representation_path",
        "content_sha256", "study_eligible", "adoption_eligible", "builder_eligible",
    }
    method = _exact_keys(record.get("method_binding"), method_keys, report, "acceptance.method_binding")
    if method is not None:
        for key in (
            "condition_id", "study_id", "study_schema_version", "version_id",
            "status", "representation_path",
        ):
            _string(method.get(key), report, f"acceptance.method_binding.{key}")
        for key in ("study_sha256", "catalog_sha256", "content_sha256"):
            _digest(method.get(key), report, f"acceptance.method_binding.{key}")
        commit = method.get("source_commit")
        if not isinstance(commit, str) or not GIT_SHA1_RE.fullmatch(commit):
            report.error("METHOD_COMMIT", "acceptance.method_binding.source_commit", "must be a full lowercase commit")
        if method.get("study_schema_version") != "charting-loop/exogenous-study/v2":
            report.error("METHOD_STUDY_SCHEMA", "acceptance.method_binding.study_schema_version", "must be the study-eligibility v2 schema")
        if method.get("status") != "frozen":
            report.error(
                "METHOD_STATUS",
                "acceptance.method_binding.status",
                "study admission requires a frozen method version",
            )
        if method.get("study_eligible") is not True:
            report.error("METHOD_STUDY_ELIGIBILITY", "acceptance.method_binding.study_eligible", "must be true")
        if type(method.get("adoption_eligible")) is not bool or type(method.get("builder_eligible")) is not bool:
            report.error("METHOD_ELIGIBILITY_TYPE", "acceptance.method_binding", "adoption and builder eligibility must be booleans")
        elif method.get("adoption_eligible") != method.get("builder_eligible"):
            report.error("METHOD_ADOPTION_ALIAS", "acceptance.method_binding", "builder_eligible must equal adoption_eligible")

    receipt_by_attempt: dict[str, dict[str, Any]] = {}
    valid_receipt_digests: dict[str, str] = {}
    usage_receipt_ids: set[str] = set()
    for index, receipt in enumerate(_list(record.get("usage_receipts"), report, "acceptance.usage_receipts") or []):
        usage = validate_usage_receipt(receipt)
        for error in usage.errors:
            report.error(error["code"], f"acceptance.usage_receipts[{index}].{error['location']}", error["message"])
        if not usage.ok or not isinstance(receipt, dict):
            continue
        receipt_id = receipt.get("receipt_id")
        if isinstance(receipt_id, str):
            if receipt_id in usage_receipt_ids:
                report.error(
                    "DUPLICATE_USAGE_RECEIPT_ID",
                    f"acceptance.usage_receipts[{index}].receipt_id",
                    "must be unique",
                )
            usage_receipt_ids.add(receipt_id)
        if usage.facts.get("usage_status") != "measured":
            report.error(
                "USAGE_INCOMPLETE",
                f"acceptance.usage_receipts[{index}]",
                "all required usage stages must be measured or explicitly not_applicable",
            )
        attempt_id = receipt.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id:
            if attempt_id in receipt_by_attempt:
                report.error("DUPLICATE_USAGE_ATTEMPT", f"acceptance.usage_receipts[{index}].attempt_id", "must be unique")
            else:
                receipt_by_attempt[attempt_id] = receipt
                valid_receipt_digests[attempt_id] = sha256_json(receipt)
        if plan_sha is not None and receipt.get("measurement_plan_sha256") != plan_sha:
            report.error("USAGE_PLAN_JOIN", f"acceptance.usage_receipts[{index}].measurement_plan_sha256", "must bind the exact plan")

    cost_by_digest: dict[str, dict[str, Any]] = {}
    costs = _list(record.get("package_costs"), report, "acceptance.package_costs") or []
    for index, cost in enumerate(costs):
        location = f"acceptance.package_costs[{index}]"
        if not isinstance(cost, dict):
            report.error("OBJECT", location, "must be an object")
            continue
        digest = _digest(cost.get("usage_receipt_sha256"), report, f"{location}.usage_receipt_sha256")
        if digest is not None:
            if digest in cost_by_digest:
                report.error("DUPLICATE_PACKAGE_COST", location, "must be exact-once per UsageReceipt")
            else:
                cost_by_digest[digest] = cost
    expected_cost_digests = set(valid_receipt_digests.values())
    if set(cost_by_digest) != expected_cost_digests:
        report.error("PACKAGE_COST_COVERAGE", "acceptance.package_costs", "must cover every valid UsageReceipt exactly and contain no extras")
    for attempt_id, receipt in receipt_by_attempt.items():
        digest = valid_receipt_digests[attempt_id]
        if not _json_exact_equal(
            cost_by_digest.get(digest), package_cost_from_usage(receipt)
        ):
            report.error("PACKAGE_COST_DERIVATION", "acceptance.package_costs", f"must be exactly derived for {attempt_id}")

    artifacts_by_id: dict[str, dict[str, Any]] = {}
    evidence_paths: set[str] = set()
    evidence_bytes_verified = evidence_root is not None
    for index, raw in enumerate(_list(record.get("raw_evidence"), report, "acceptance.raw_evidence") or []):
        location = f"acceptance.raw_evidence[{index}]"
        item = _exact_keys(raw, {"artifact_id", "kind", "path", "content_sha256", "attempt_id"}, report, location)
        if item is None:
            continue
        artifact_id = _string(item.get("artifact_id"), report, f"{location}.artifact_id")
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in ALLOWED_EVIDENCE_KINDS:
            report.error(
                "EVIDENCE_KIND",
                f"{location}.kind",
                f"must be one of {sorted(ALLOWED_EVIDENCE_KINDS)}",
            )
        _string(item.get("attempt_id"), report, f"{location}.attempt_id")
        expected_digest = _digest(item.get("content_sha256"), report, f"{location}.content_sha256")
        relative = _evidence_relative_path(item.get("path"), report, f"{location}.path")
        if relative is not None:
            if relative in evidence_paths:
                report.error(
                    "DUPLICATE_EVIDENCE_PATH",
                    f"{location}.path",
                    "each raw artifact must bind distinct evidence bytes",
                )
            evidence_paths.add(relative)
        if evidence_root is not None:
            safe = _safe_evidence_path(evidence_root, item.get("path"), report, f"{location}.path")
            if safe is None:
                evidence_bytes_verified = False
            elif expected_digest is not None:
                _relative, path = safe
                try:
                    actual = file_sha256(path)
                except (OSError, ValueError) as exc:
                    report.error("EVIDENCE_FILE", f"{location}.path", str(exc))
                    evidence_bytes_verified = False
                else:
                    if actual != expected_digest:
                        report.error("EVIDENCE_DIGEST", f"{location}.content_sha256", "does not match actual evidence bytes")
                        evidence_bytes_verified = False
        if artifact_id is not None:
            if artifact_id in artifacts_by_id:
                report.error("DUPLICATE_ARTIFACT", f"{location}.artifact_id", "must be unique")
            else:
                artifacts_by_id[artifact_id] = item

    attempt_keys = {
        "attempt_id", "arm", "run_id", "session_id", "invocation_id",
        "session_receipt_path", "session_receipt_sha256", "agent_kind", "scripted", "candidate_sha256",
        "common_condition_sha256", "artifact_ids", "outcome",
        "supersedes_attempt_id", "repair_reason",
    }
    attempts_by_id: dict[str, dict[str, Any]] = {}
    attempt_artifact_refs: dict[str, list[str]] = {}
    sessions: set[str] = set()
    invocations: set[str] = set()
    session_receipt_digests: set[str] = set()
    session_receipt_paths: set[str] = set()
    for index, raw in enumerate(_list(record.get("attempts"), report, "acceptance.attempts") or []):
        location = f"acceptance.attempts[{index}]"
        item = _exact_keys(raw, attempt_keys, report, location)
        if item is None:
            continue
        attempt_id = _string(item.get("attempt_id"), report, f"{location}.attempt_id")
        arm = item.get("arm")
        if not isinstance(arm, str) or arm not in {"builder", "treatment", "control"}:
            report.error("ATTEMPT_ARM", f"{location}.arm", "must be builder, treatment, or control")
        for key in ("run_id", "session_id", "invocation_id", "agent_kind", "outcome"):
            _string(item.get(key), report, f"{location}.{key}")
        if item.get("outcome") not in {"passed", "failed", "infra_failed", "excluded"}:
            report.error(
                "ATTEMPT_OUTCOME",
                f"{location}.outcome",
                "must be passed, failed, infra_failed, or excluded",
            )
        _digest(item.get("session_receipt_sha256"), report, f"{location}.session_receipt_sha256")
        receipt_path = _evidence_relative_path(
            item.get("session_receipt_path"),
            report,
            f"{location}.session_receipt_path",
        )
        receipt_digest = item.get("session_receipt_sha256")
        if isinstance(receipt_digest, str):
            if receipt_digest in session_receipt_digests:
                report.error(
                    "SESSION_RECEIPT_REUSE",
                    f"{location}.session_receipt_sha256",
                    "each attempt requires distinct independently issued receipt bytes",
                )
            session_receipt_digests.add(receipt_digest)
        if receipt_path is not None:
            if receipt_path in session_receipt_paths:
                report.error(
                    "SESSION_RECEIPT_REUSE",
                    f"{location}.session_receipt_path",
                    "each attempt requires a distinct receipt file",
                )
            if receipt_path in evidence_paths:
                report.error(
                    "SESSION_RECEIPT_REUSE",
                    f"{location}.session_receipt_path",
                    "session receipt must be distinct from raw task evidence",
                )
            session_receipt_paths.add(receipt_path)
        _digest(item.get("common_condition_sha256"), report, f"{location}.common_condition_sha256")
        candidate = item.get("candidate_sha256")
        if arm == "control":
            if candidate is not None:
                report.error("CONTROL_CANDIDATE", f"{location}.candidate_sha256", "must be null")
        else:
            _digest(candidate, report, f"{location}.candidate_sha256")
        if item.get("agent_kind") != "ai-agent" or item.get("scripted") is not False:
            report.error("REAL_AI_REQUIRED", location, "must bind a non-scripted AI session receipt")
        refs = _string_list(item.get("artifact_ids"), report, f"{location}.artifact_ids", nonempty=True)
        for ref in refs:
            artifact = artifacts_by_id.get(ref)
            if artifact is None or artifact.get("attempt_id") != attempt_id:
                report.error("ATTEMPT_ARTIFACT_JOIN", f"{location}.artifact_ids", "must bijectively own every referenced artifact")
        candidate_artifacts = [
            artifacts_by_id[ref]
            for ref in refs
            if ref in artifacts_by_id
            and artifacts_by_id[ref].get("attempt_id") == attempt_id
            and artifacts_by_id[ref].get("kind") == "candidate-artifact"
        ]
        if arm == "control":
            if candidate_artifacts:
                report.error(
                    "CONTROL_CANDIDATE_ARTIFACT",
                    f"{location}.artifact_ids",
                    "task-only control must not carry a Corridor candidate artifact",
                )
        elif not any(
            artifact.get("content_sha256") == candidate
            for artifact in candidate_artifacts
        ):
            report.error(
                "CANDIDATE_ARTIFACT_JOIN",
                f"{location}.candidate_sha256",
                "must equal an owned candidate-artifact byte digest",
            )
        run = runs_by_id.get(item.get("run_id")) if isinstance(item.get("run_id"), str) else None
        if run is None:
            report.error("ATTEMPT_RUN_JOIN", f"{location}.run_id", "must resolve an exact validated RUN binding")
        else:
            if item.get("common_condition_sha256") != run.get("common_condition_sha256"):
                report.error("ATTEMPT_COMMON_JOIN", f"{location}.common_condition_sha256", "must bind the RUN nuisance-variable digest")
            receipt = receipt_by_attempt.get(attempt_id or "")
            if receipt is not None and (
                receipt.get("run_id") != run.get("run_id")
                or receipt.get("run_sha256") != run.get("run_sha256")
                or receipt.get("session_id") != item.get("session_id")
            ):
                report.error("USAGE_ATTEMPT_JOIN", location, "UsageReceipt must bind exact RUN and session")
        supersedes = item.get("supersedes_attempt_id")
        repair_reason = item.get("repair_reason")
        if supersedes is None:
            if repair_reason is not None:
                report.error("REPAIR_ANCESTRY", f"{location}.repair_reason", "must be null without a superseded attempt")
        else:
            _string(supersedes, report, f"{location}.supersedes_attempt_id")
            _string(repair_reason, report, f"{location}.repair_reason")
        session_id = item.get("session_id")
        invocation_id = item.get("invocation_id")
        if isinstance(session_id, str):
            if session_id in sessions:
                report.error("SESSION_REUSE", f"{location}.session_id", "must be fresh across attempts")
            sessions.add(session_id)
        if isinstance(invocation_id, str):
            if invocation_id in invocations:
                report.error("INVOCATION_REUSE", f"{location}.invocation_id", "must be unique")
            invocations.add(invocation_id)
        if attempt_id is not None:
            if attempt_id in attempts_by_id:
                report.error("DUPLICATE_ATTEMPT", f"{location}.attempt_id", "must be unique")
            else:
                attempts_by_id[attempt_id] = item
                attempt_artifact_refs[attempt_id] = refs
                if attempt_id not in receipt_by_attempt:
                    report.error("ATTEMPT_USAGE_JOIN", f"{location}.attempt_id", "must have exactly one UsageReceipt")

    attempt_order = {attempt_id: index for index, attempt_id in enumerate(attempts_by_id)}
    for attempt_id, item in attempts_by_id.items():
        parent = item.get("supersedes_attempt_id")
        if parent is not None:
            previous = attempts_by_id.get(parent) if isinstance(parent, str) else None
            if (
                previous is None
                or previous.get("arm") != item.get("arm")
                or parent == attempt_id
                or attempt_order.get(str(parent), len(attempt_order)) >= attempt_order[attempt_id]
            ):
                report.error("REPAIR_ANCESTRY", f"acceptance.attempts.{attempt_id}", "must resolve a distinct earlier same-arm attempt")
    if set(receipt_by_attempt) != set(attempts_by_id):
        report.error("USAGE_ATTEMPT_COVERAGE", "acceptance.usage_receipts", "must cover every attempt exactly and contain no extras")
    used_run_ids = {
        item.get("run_id")
        for item in attempts_by_id.values()
        if isinstance(item.get("run_id"), str)
    }
    if used_run_ids != set(runs_by_id):
        report.error(
            "RUN_ATTEMPT_COVERAGE",
            "acceptance.run_bindings",
            "must contain exactly the RUNs used by retained attempts",
        )
    for artifact_id, artifact in artifacts_by_id.items():
        owner = artifact.get("attempt_id")
        if not isinstance(owner, str) or owner not in attempts_by_id or artifact_id not in attempt_artifact_refs.get(owner, []):
            report.error("ARTIFACT_OWNER", f"acceptance.raw_evidence.{artifact_id}", "must be referenced exactly by its owning attempt")

    session_receipts_verified = evidence_root is not None
    receipt_ids: set[str] = set()
    forbidden_receipt_issuers = sessions | invocations | {
        str(run.get("runner_id")) for run in runs_by_id.values()
    }
    if assembler is not None:
        forbidden_receipt_issuers |= {
            str(assembler.get("runner_id")),
            str(assembler.get("session_id")),
            str(assembler.get("invocation_id")),
        }
    receipt_keys = {
        "schema_version", "receipt_id", "issuer_id", "issuer_session_id",
        "issuer_invocation_id", "attempt_id", "session_id", "invocation_id",
        "agent_kind", "scripted",
    }
    for attempt_id, item in attempts_by_id.items():
        location = f"acceptance.attempts.{attempt_id}.session_receipt_path"
        if evidence_root is None:
            session_receipts_verified = False
            continue
        safe = _safe_evidence_path(evidence_root, item.get("session_receipt_path"), report, location)
        if safe is None:
            session_receipts_verified = False
            continue
        _relative, path = safe
        try:
            raw_digest = file_sha256(path)
            receipt_value = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report.error("SESSION_RECEIPT_FILE", location, str(exc))
            session_receipts_verified = False
            continue
        if raw_digest != item.get("session_receipt_sha256"):
            report.error(
                "SESSION_RECEIPT_DIGEST",
                location,
                "declared digest does not match the independently issued receipt bytes",
            )
            session_receipts_verified = False
        receipt = _exact_keys(receipt_value, receipt_keys, report, location)
        if receipt is None:
            session_receipts_verified = False
            continue
        if receipt.get("schema_version") != SESSION_RECEIPT_SCHEMA:
            report.error("SESSION_RECEIPT_SCHEMA", location, f"must be {SESSION_RECEIPT_SCHEMA}")
        for key in (
            "receipt_id", "issuer_id", "issuer_session_id", "issuer_invocation_id",
            "attempt_id", "session_id", "invocation_id", "agent_kind",
        ):
            _string(receipt.get(key), report, f"{location}.{key}")
        if type(receipt.get("scripted")) is not bool:
            report.error("BOOLEAN", f"{location}.scripted", "must be a JSON boolean")
        receipt_id = receipt.get("receipt_id")
        if isinstance(receipt_id, str):
            if receipt_id in receipt_ids:
                report.error("SESSION_RECEIPT_REUSE", f"{location}.receipt_id", "must be unique")
            receipt_ids.add(receipt_id)
        expected_join = {
            "attempt_id": attempt_id,
            "session_id": item.get("session_id"),
            "invocation_id": item.get("invocation_id"),
            "agent_kind": item.get("agent_kind"),
            "scripted": item.get("scripted"),
        }
        if any(receipt.get(key) != expected for key, expected in expected_join.items()):
            report.error("SESSION_RECEIPT_JOIN", location, "must bind the exact attempt session")
            session_receipts_verified = False
        if any(
            isinstance(receipt.get(key), str)
            and receipt.get(key) in forbidden_receipt_issuers
            for key in ("issuer_id", "issuer_session_id", "issuer_invocation_id")
        ):
            report.error(
                "SESSION_RECEIPT_INDEPENDENCE",
                location,
                "issuer identity/session/invocation must differ from runners and agent sessions",
            )
            session_receipts_verified = False

    pair_keys = {
        "pair_id", "builder_attempt_id", "treatment_attempt_id", "control_attempt_id",
        "candidate_sha256", "common_condition_sha256",
    }
    clean_pair_ids: list[str] = []
    pair_cost_accounting: list[dict[str, Any]] = []
    seen_pair_ids: set[str] = set()
    used_pair_sessions: set[str] = set()
    used_pair_runs: set[str] = set()
    used_pair_attempts: set[str] = set()
    used_pair_assignments: set[tuple[str, str, int, str]] = set()
    pairs = _list(record.get("pairs"), report, "acceptance.pairs") or []

    def attempt_lineage(attempt_id: str) -> list[str]:
        lineage: list[str] = []
        current: str | None = attempt_id
        seen: set[str] = set()
        while current is not None and current in attempts_by_id and current not in seen:
            seen.add(current)
            lineage.append(current)
            parent = attempts_by_id[current].get("supersedes_attempt_id")
            current = parent if isinstance(parent, str) else None
        lineage.reverse()
        return lineage

    def usage_cost(attempt_ids: list[str]) -> dict[str, Any]:
        total = {metric: 0 for metric in USAGE_METRICS}
        by_stage = {
            stage: {metric: 0 for metric in USAGE_METRICS}
            for stage in USAGE_STAGES
        }
        missing_stages: list[str] = []
        for attempt_id in attempt_ids:
            receipt = receipt_by_attempt.get(attempt_id)
            if receipt is None:
                missing_stages.append(f"{attempt_id}:missing-usage-receipt")
                continue
            usage_report = validate_usage_receipt(receipt)
            if (
                not usage_report.ok
                or usage_report.facts.get("usage_status") != "measured"
            ):
                missing_stages.append(f"{attempt_id}:usage-incomplete")
                continue
            package = package_cost_from_usage(receipt)
            missing_stages.extend(
                f"{attempt_id}:{stage}"
                for stage in package["primary"]["missing_stages"]
            )
            for stage in receipt.get("stages", []):
                if not isinstance(stage, dict) or stage.get("assessment_status") != "measured":
                    continue
                stage_name = stage.get("stage")
                if stage_name not in by_stage:
                    continue
                for metric in USAGE_METRICS:
                    value = stage.get(metric)
                    if type(value) is int:
                        total[metric] += value
                        by_stage[stage_name][metric] += value
        if missing_stages:
            total = {metric: None for metric in USAGE_METRICS}
            by_stage = {
                stage: {metric: None for metric in USAGE_METRICS}
                for stage in USAGE_STAGES
            }
        return {
            "attempt_ids": attempt_ids,
            "total": total,
            "by_stage": by_stage,
            "missing_stages": missing_stages,
            "complete": not missing_stages,
            "cached_input_and_reasoning_are_subsets": True,
        }

    for index, raw in enumerate(pairs):
        location = f"acceptance.pairs[{index}]"
        pair = _exact_keys(raw, pair_keys, report, location)
        if pair is None:
            continue
        pair_id = _string(pair.get("pair_id"), report, f"{location}.pair_id")
        if pair_id is not None:
            if pair_id in seen_pair_ids:
                report.error("DUPLICATE_PAIR", f"{location}.pair_id", "must be unique")
            seen_pair_ids.add(pair_id)
        refs: list[str] = []
        for key in ("builder_attempt_id", "treatment_attempt_id", "control_attempt_id"):
            ref = _string(pair.get(key), report, f"{location}.{key}")
            if ref is not None:
                refs.append(ref)
        if len(refs) != 3 or len(set(refs)) != 3:
            report.error(
                "PAIR_ATTEMPT_REFS",
                location,
                "must resolve three distinct attempt references",
            )
        _digest(pair.get("candidate_sha256"), report, f"{location}.candidate_sha256")
        _digest(pair.get("common_condition_sha256"), report, f"{location}.common_condition_sha256")
        selected = [attempts_by_id.get(ref) for ref in refs]
        clean = len(selected) == 3 and all(item is not None for item in selected)
        pair_lineages = [attempt_lineage(ref) for ref in refs]
        lineage_ids = [item for lineage in pair_lineages for item in lineage]
        clean = clean and len(lineage_ids) == len(set(lineage_ids))
        if clean:
            builder, treatment, control = selected  # type: ignore[misc]
            lineage_attempts = [attempts_by_id[item] for item in lineage_ids]
            pair_sessions = {
                str(item.get("session_id")) for item in lineage_attempts
            }
            lineage_run_ids = {
                str(item.get("run_id")) for item in lineage_attempts
            }
            lineage_assignment_keys = {
                (
                    str(runs_by_id[run_id].get("taskset_id")),
                    str(runs_by_id[run_id].get("task_id")),
                    runs_by_id[run_id].get("trial")
                    if type(runs_by_id[run_id].get("trial")) is int
                    else -1,
                    str(runs_by_id[run_id].get("seed")),
                )
                for run_id in lineage_run_ids
                if run_id in runs_by_id
            }
            treatment_run = str(treatment.get("run_id"))
            control_run = str(control.get("run_id"))
            clean = [builder.get("arm"), treatment.get("arm"), control.get("arm")] == ["builder", "treatment", "control"]
            clean = clean and builder.get("run_id") == treatment.get("run_id")
            clean = clean and len(pair_sessions) == len(lineage_ids)
            clean = clean and not (pair_sessions & used_pair_sessions)
            clean = clean and not (set(lineage_ids) & used_pair_attempts)
            clean = clean and treatment_run != control_run
            clean = clean and not (lineage_run_ids & used_pair_runs)
            clean = clean and not (
                lineage_assignment_keys & used_pair_assignments
            )
            clean = clean and builder.get("candidate_sha256") == treatment.get("candidate_sha256") == pair.get("candidate_sha256")
            clean = clean and all(item.get("common_condition_sha256") == pair.get("common_condition_sha256") for item in selected)
            clean = clean and all(item.get("outcome") == "passed" for item in selected)
            treatment_binding = runs_by_id.get(treatment_run)
            control_binding = runs_by_id.get(control_run)
            clean = clean and treatment_binding is not None and control_binding is not None
            if treatment_binding is not None and control_binding is not None:
                clean = clean and treatment_binding.get("system_condition") == "corridor"
                clean = clean and treatment_binding.get("knowledge_condition") == "method-paper"
                clean = clean and control_binding.get("system_condition") == "task-only"
                clean = clean and control_binding.get("knowledge_condition") == "task-only"
                clean = clean and treatment_binding.get("common_conditions") == control_binding.get("common_conditions")
                clean = clean and treatment_binding.get("taskset_id") == control_binding.get("taskset_id")
                clean = clean and treatment_binding.get("task_id") == control_binding.get("task_id")
                clean = clean and (
                    method is not None
                    and treatment_binding.get("condition_id") == method.get("condition_id")
                    and treatment_binding.get("study_id") == method.get("study_id")
                    and treatment_binding.get("study_sha256") == method.get("study_sha256")
                    and control_binding.get("study_id") == method.get("study_id")
                    and control_binding.get("study_sha256") == method.get("study_sha256")
                )
            if clean and pair_id is not None:
                clean_pair_ids.append(pair_id)
                used_pair_sessions.update(pair_sessions)
                used_pair_runs.update(lineage_run_ids)
                used_pair_attempts.update(lineage_ids)
                used_pair_assignments.update(lineage_assignment_keys)
                pair_cost_accounting.append(
                    {
                        "pair_id": pair_id,
                        "corridor_e2e": usage_cost(pair_lineages[0] + pair_lineages[1]),
                        "control_task": usage_cost(pair_lineages[2]),
                    }
                )
        if not clean:
            report.error(
                "PAIR_NOT_CLEAN",
                location,
                "selected pairs must satisfy exact role, RUN, study, candidate, nuisance, outcome, and freshness joins",
            )

    clean_pair_ids.sort()
    pair_cost_accounting.sort(key=lambda item: str(item.get("pair_id")))
    if used_pair_attempts != set(attempts_by_id):
        report.error(
            "PAIR_ATTEMPT_COVERAGE",
            "acceptance.pairs",
            "every retained attempt must be selected or an explicit superseded ancestor",
        )

    replay = _exact_keys(
        record.get("independent_replay"),
        {
            "schema_version", "replay_id", "verifier_id", "verifier_session_id",
            "verifier_invocation_id", "runner_id", "runner_session_id",
            "runner_invocation_id", "receipt_path", "receipt_sha256", "payload_sha256",
            "outcome_sha256", "verified",
        },
        report,
        "acceptance.independent_replay",
    )
    replay_verified = False
    replay_bytes_verified = evidence_root is not None
    if replay is not None:
        for key in (
            "replay_id", "verifier_id", "verifier_session_id", "verifier_invocation_id",
            "runner_id", "runner_session_id", "runner_invocation_id", "receipt_path",
        ):
            _string(replay.get(key), report, f"acceptance.independent_replay.{key}")
        _evidence_relative_path(
            replay.get("receipt_path"),
            report,
            "acceptance.independent_replay.receipt_path",
        )
        for key in ("receipt_sha256", "payload_sha256", "outcome_sha256"):
            _digest(replay.get(key), report, f"acceptance.independent_replay.{key}")
        if replay.get("schema_version") != REPLAY_RECEIPT_SCHEMA:
            report.error("REPLAY_SCHEMA", "acceptance.independent_replay.schema_version", f"must be {REPLAY_RECEIPT_SCHEMA}")
        if assembler is not None and (
            replay.get("runner_id") != assembler.get("runner_id")
            or replay.get("runner_session_id") != assembler.get("session_id")
            or replay.get("runner_invocation_id") != assembler.get("invocation_id")
        ):
            report.error("REPLAY_RUNNER_JOIN", "acceptance.independent_replay", "must bind the exact assembler invocation")
        forbidden_identities = sessions | invocations | {
            str(run.get("runner_id")) for run in runs_by_id.values()
        }
        if assembler is not None:
            forbidden_identities |= {str(assembler.get("runner_id")), str(assembler.get("session_id")), str(assembler.get("invocation_id"))}
        if any(
            isinstance(replay.get(key), str)
            and replay.get(key) in forbidden_identities
            for key in ("verifier_id", "verifier_session_id", "verifier_invocation_id")
        ):
            report.error("REPLAY_INDEPENDENCE", "acceptance.independent_replay", "verifier identity/session/invocation must differ from assembler and every agent session")
        expected_payload = sha256_json(_replay_payload(record))
        expected_outcome = sha256_json(
            {
                "attempt_outcomes": [
                    {"attempt_id": key, "outcome": attempts_by_id[key].get("outcome")}
                    for key in sorted(attempts_by_id)
                ],
                "clean_pair_ids": clean_pair_ids,
            }
        )
        if replay.get("payload_sha256") != expected_payload:
            report.error("REPLAY_PAYLOAD_JOIN", "acceptance.independent_replay.payload_sha256", "must bind the complete canonical package payload")
        if replay.get("outcome_sha256") != expected_outcome:
            report.error("REPLAY_OUTCOME_JOIN", "acceptance.independent_replay.outcome_sha256", "must bind attempt outcomes and derived clean pairs")
        replay_verified = replay.get("verified") is True
        if not replay_verified:
            report.error("REPLAY_VERDICT", "acceptance.independent_replay.verified", "must be true")

        if evidence_root is not None:
            receipt_path = _safe_evidence_path(
                evidence_root,
                replay.get("receipt_path"),
                report,
                "acceptance.independent_replay.receipt_path",
            )
            if receipt_path is None:
                replay_bytes_verified = False
            else:
                _relative, path = receipt_path
                try:
                    actual_digest = file_sha256(path)
                    persisted = load_json(path)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    report.error("REPLAY_RECEIPT_FILE", "acceptance.independent_replay.receipt_path", str(exc))
                    replay_bytes_verified = False
                else:
                    expected_persisted = {
                        key: replay.get(key)
                        for key in replay
                        if key not in {"receipt_path", "receipt_sha256"}
                    }
                    if actual_digest != replay.get("receipt_sha256"):
                        report.error("REPLAY_RECEIPT_DIGEST", "acceptance.independent_replay.receipt_sha256", "does not match replay receipt bytes")
                        replay_bytes_verified = False
                    if not _json_exact_equal(persisted, expected_persisted):
                        report.error("REPLAY_RECEIPT_JOIN", "acceptance.independent_replay.receipt_path", "persisted replay receipt must equal the closed replay projection")
                        replay_bytes_verified = False
                    if replay.get("receipt_path") in evidence_paths or replay.get("receipt_path") in session_receipt_paths:
                        report.error(
                            "REPLAY_RECEIPT_REUSE",
                            "acceptance.independent_replay.receipt_path",
                            "replay receipt must be a distinct evidence file",
                        )
                        replay_bytes_verified = False
        else:
            replay_bytes_verified = False

    replay_verified = replay_verified and replay_bytes_verified

    trusted_verified = False
    if trusted_context is not None:
        trusted = _exact_keys(
            trusted_context,
            {
                "schema_version", "acceptance_id", "assembler",
                "source_validation", "source_validation_sha256", "verified",
            },
            report,
            "trusted_context",
        )
        source = None
        if trusted is not None:
            if trusted.get("schema_version") != ACCEPTANCE_TRUSTED_CONTEXT_SCHEMA:
                report.error("TRUSTED_CONTEXT_SCHEMA", "trusted_context.schema_version", f"must be {ACCEPTANCE_TRUSTED_CONTEXT_SCHEMA}")
            source = _exact_keys(
                trusted.get("source_validation"),
                {
                    "schema_version", "catalog_schema_version", "catalog_sha256",
                    "catalog_selected_version", "study_schema_version", "study_id",
                    "study_sha256", "formal_method_study_eligible",
                    "study_eligible_condition_ids", "study_eligible_method_refs",
                    "run_facts",
                },
                report,
                "trusted_context.source_validation",
            )
            source_sha = sha256_json(source) if source is not None else None
            if (
                trusted.get("acceptance_id") != record.get("acceptance_id")
                or not _json_exact_equal(
                    trusted.get("assembler"), record.get("assembler")
                )
            ):
                report.error("TRUSTED_CONTEXT_JOIN", "trusted_context", "must bind acceptance and assembler exactly")
            if source_sha != trusted.get("source_validation_sha256") or source_sha != record.get("source_validation_sha256"):
                report.error("SOURCE_VALIDATION_DIGEST", "trusted_context.source_validation_sha256", "must bind the exact out-of-band source validation facts")
            if trusted.get("verified") is not True:
                report.error("TRUSTED_CONTEXT_VERDICT", "trusted_context.verified", "must be true")
        if source is not None:
            if source.get("schema_version") != SOURCE_VALIDATION_SCHEMA:
                report.error("SOURCE_VALIDATION_SCHEMA", "trusted_context.source_validation.schema_version", f"must be {SOURCE_VALIDATION_SCHEMA}")
            if source.get("catalog_schema_version") != "charting-loop/method-index/v2":
                report.error("SOURCE_CATALOG_SCHEMA", "trusted_context.source_validation.catalog_schema_version", "must be method-index/v2")
            if source.get("study_schema_version") != "charting-loop/exogenous-study/v2":
                report.error("SOURCE_STUDY_SCHEMA", "trusted_context.source_validation.study_schema_version", "must be exogenous-study/v2")
            for key in ("catalog_sha256", "study_sha256"):
                _digest(source.get(key), report, f"trusted_context.source_validation.{key}")
            if method is not None:
                expected_catalog = {
                    "version_id": method.get("version_id"),
                    "status": method.get("status"),
                    "source_commit": method.get("source_commit"),
                    "path": method.get("representation_path"),
                    "content_sha256": method.get("content_sha256"),
                    "study_eligible": method.get("study_eligible"),
                    "adoption_eligible": method.get("adoption_eligible"),
                    "builder_eligible": method.get("builder_eligible"),
                }
                expected_ref = {
                    "condition_id": method.get("condition_id"),
                    "version_id": method.get("version_id"),
                    "source_commit": method.get("source_commit"),
                    "representation_path": method.get("representation_path"),
                    "content_sha256": method.get("content_sha256"),
                    "study_eligible": method.get("study_eligible"),
                    "adoption_eligible": method.get("adoption_eligible"),
                    "builder_eligible": method.get("builder_eligible"),
                }
                if (
                    source.get("catalog_sha256") != method.get("catalog_sha256")
                    or not _json_exact_equal(
                        source.get("catalog_selected_version"), expected_catalog
                    )
                ):
                    report.error("SOURCE_CATALOG_JOIN", "trusted_context.source_validation", "must equal the selected validated method catalog version")
                if source.get("study_id") != method.get("study_id") or source.get("study_sha256") != method.get("study_sha256"):
                    report.error("SOURCE_STUDY_JOIN", "trusted_context.source_validation", "must bind the exact validated STUDY")
                if (
                    source.get("formal_method_study_eligible") is not True
                    or not _json_exact_equal(
                        source.get("study_eligible_condition_ids"),
                        [method.get("condition_id")],
                    )
                    or not _json_exact_equal(
                        source.get("study_eligible_method_refs"), [expected_ref]
                    )
                ):
                    report.error("SOURCE_STUDY_ELIGIBILITY", "trusted_context.source_validation", "must contain the exact formal study-eligible condition and MethodRef")
            expected_run_facts = [
                {
                    "run_id": run.get("run_id"),
                    "schema_version": run.get("schema_version"),
                    "status": run.get("status"),
                    "run_sha256": run.get("run_sha256"),
                    "study_id": run.get("study_id"),
                    "study_sha256": run.get("study_sha256"),
                    "condition_id": run.get("condition_id"),
                    "measurement_plan_sha256": run.get("measurement_plan_sha256"),
                    "measurement_plan_complete": True,
                    "common_condition_sha256": run.get("common_condition_sha256"),
                    "run_binding_sha256": sha256_json(run),
                }
                for run in sorted(runs_by_id.values(), key=lambda item: str(item.get("run_id")))
            ]
            if not _json_exact_equal(source.get("run_facts"), expected_run_facts):
                report.error("SOURCE_RUN_JOIN", "trusted_context.source_validation.run_facts", "must equal every validated RUN fact projection")
            trusted_verified = trusted is not None and trusted.get("verified") is True
    trusted_verified = (
        trusted_verified
        and evidence_bytes_verified
        and session_receipts_verified
        and replay_bytes_verified
    )

    validation_ok = report.ok
    derived = _acceptance_gate(
        clean_pair_ids=clean_pair_ids,
        replay_verified=replay_verified,
        trusted_inputs_verified=trusted_verified,
        validation_ok=validation_ok,
    )
    if not _json_exact_equal(record.get("gate"), derived):
        report.error("GATE_DERIVATION", "acceptance.gate", "must equal the derived gate; callers cannot declare readiness")
        derived = _acceptance_gate(
            clean_pair_ids=clean_pair_ids,
            replay_verified=replay_verified,
            trusted_inputs_verified=trusted_verified,
            validation_ok=False,
        )
    report.facts.update(derived)
    report.facts["pair_cost_accounting"] = pair_cost_accounting
    report.facts["acceptance_sha256"] = sha256_json(record)
    return report


def validate_acceptance_record(
    value: Any, *, trusted_context: dict[str, Any] | None = None,
    evidence_root: Path | None = None,
) -> ValidationReport:
    """Fail-closed public boundary for arbitrary JSON-shaped acceptance input."""

    try:
        return _validate_acceptance_record_impl(
            value,
            trusted_context=trusted_context,
            evidence_root=evidence_root,
        )
    except (
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        report = ValidationReport()
        report.error(
            "MALFORMED_ACCEPTANCE",
            "acceptance",
            f"invalid nested value: {type(exc).__name__}",
        )
        report.facts.update(
            _acceptance_gate(
                clean_pair_ids=[],
                replay_verified=False,
                trusted_inputs_verified=False,
                validation_ok=False,
            )
        )
        report.facts["acceptance_sha256"] = None
        return report


def compile_service_plan(world: Any) -> dict[str, Any]:
    if not isinstance(world, dict) or set(world) != {"services"}:
        raise DemoDataError("invalid_world", "world must contain only services")
    services = world.get("services")
    if not isinstance(services, list):
        raise DemoDataError("invalid_services", "services must be a list")
    compiled: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in services:
        if not isinstance(item, dict) or set(item) != {"service", "status", "capacity"}:
            raise DemoDataError("invalid_service", "each service has an exact shape")
        name = item.get("service")
        status = item.get("status")
        capacity = item.get("capacity")
        if not isinstance(name, str) or not name or name in seen:
            raise DemoDataError("invalid_service_name", "service names must be unique strings")
        seen.add(name)
        if status not in {"ready", "blocked"}:
            raise DemoDataError("invalid_status", "status must be ready or blocked")
        if type(capacity) is not int or capacity < 0:
            raise DemoDataError("invalid_capacity", "capacity must be a non-negative integer")
        if status == "ready":
            compiled.append({"service": name, "replicas": capacity})
    compiled.sort(key=lambda item: item["service"])
    return {"inventory_version": "sealed-inventory-L1", "services": compiled}


def _fixture(demo_root: Path, manifest: dict[str, Any], fixture_id: str) -> Any:
    spec = manifest["fixtures"][fixture_id]
    path = (demo_root / spec["path"]).resolve()
    if demo_root.resolve() not in path.parents or path.is_symlink():
        raise ValueError(f"unsafe fixture path: {spec['path']}")
    return load_json(path)


def _world_ref(
    manifest: dict[str, Any],
    *,
    world_ref_id: str,
    fixture_ref: str,
    fact_sha256: str,
    through_sequence: int,
    prefix_sha256: str,
) -> dict[str, Any]:
    projector = manifest["projector"]
    admission = manifest["admission"]
    return {
        "world_ref_id": world_ref_id,
        "project_id": manifest["project_id"],
        "run_id": manifest["run_id"],
        "generation_id": manifest["generation_id"],
        "repository_url": manifest["subject"]["repository_url"],
        "base_commit": manifest["subject"]["base_commit"],
        "environment_sha256": manifest["subject"]["environment_sha256"],
        "fixture_ref": fixture_ref,
        "evidence_prefix": {
            "stream_id": projector["stream_id"],
            "through_sequence": through_sequence,
            "prefix_sha256": prefix_sha256,
            "admission": {
                "receipt_id": f"admission-{world_ref_id}",
                "admitted_root_sha256": sha256_json(
                    {"fixture_ref": fixture_ref, "fact_sha256": fact_sha256}
                ),
                "rule_revision": admission["rule_revision"],
                "rule_sha256": manifest["admission_rule_sha256"],
            },
            "projector": {
                "schema_version": WORLD_PROJECTOR_SCHEMA,
                "algorithm_id": projector["id"],
                "algorithm_version": projector["version"],
                "algorithm_sha256": manifest["projector_sha256"],
            },
        },
        "derived_state_sha256": fact_sha256,
    }


def _candidate(
    *,
    candidate_id: str,
    revision_id: str,
    world_ref: dict[str, Any],
    stage: dict[str, Any],
) -> dict[str, Any]:
    actions = (
        ["compile-core", "emit-checkpoint"]
        if stage["id"] == "stage-1"
        else ["compile-final-plan", "validate-typed-failure"]
    )
    role_definition_id = f"service-plan-{stage['id']}-builder-role"
    assignment_id = f"assignment-{revision_id}"
    assignment_fact_id = f"assignment-fact-{revision_id}"
    rules = [
        {
            "rule_id": f"service-plan-{stage['id']}-direction",
            "version": "1",
            "scope": stage["id"],
            "acceptance_sha256": sha256_json(stage["instruction"]),
        },
        {
            "rule_id": f"service-plan-{stage['id']}-transition",
            "version": "1",
            "scope": stage["id"],
            "allowed_actions_sha256": sha256_json(actions),
        },
        {
            "rule_id": role_definition_id,
            "rule_kind": "RoleDefinition",
            "version": "1",
            "scope": stage["id"],
            "role_id": "service-plan-builder",
        },
    ]
    assignment_fact = {
        "fact_id": assignment_fact_id,
        "fact_kind": "ActorRoleAssignment",
        "assignment_id": assignment_id,
        "actor_id": "scripted-executor",
        "role_id": "service-plan-builder",
        "role_definition_id": role_definition_id,
        "scope": stage["id"],
        "world_ref_id": world_ref["world_ref_id"],
        "authority_source_id": "fixture-authority-issuer",
        "liveness_state": "live",
    }
    facts = [
        {
            "fact_id": f"inventory-{world_ref['world_ref_id']}",
            "world_ref_id": world_ref["world_ref_id"],
            "fact_sha256": world_ref["derived_state_sha256"],
        },
        {**assignment_fact, "fact_sha256": sha256_json(assignment_fact)},
    ]
    position = {
        "role_definition": {
            "role_definition_id": role_definition_id,
            "role_id": "service-plan-builder",
            "version": "1",
            "scope": stage["id"],
        },
        "role_assignment": {
            "assignment_id": assignment_id,
            "holder": "scripted-executor",
            "role_id": "service-plan-builder",
            "scope": stage["id"],
            "assignment_fact_id": assignment_fact_id,
            "world_ref_id": world_ref["world_ref_id"],
            "required_warranty_kinds": [
                "EvidentialWarranty",
                "AuthorityWarranty",
            ],
        },
        "coordinate": f"{stage['id']}:execute",
    }
    projection = {
        "candidate_id": candidate_id,
        "candidate_ref": f"candidate:{candidate_id}@{revision_id}",
        "revision_id": revision_id,
        "state": "frozen",
        "world_ref_id": world_ref["world_ref_id"],
        "stage_id": stage["id"],
        "scope": f"{stage['id']}-capsule-delivery",
        "builder_id": "scripted-corridor-builder",
        "rules": rules,
        "facts": facts,
        "position": position,
    }
    return {**projection, "semantic_sha256": sha256_json(projection)}


def candidate_semantic_sha256(candidate: dict[str, Any]) -> str:
    return sha256_json({key: value for key, value in candidate.items() if key != "semantic_sha256"})


def _entrance_result(
    manifest: dict[str, Any], candidate: dict[str, Any], stage: dict[str, Any]
) -> dict[str, Any]:
    interface = {
        "interface_id": "service-plan-guide-resolve",
        "interface_version": "1",
        "operation": "resolve",
    }
    facade = {
        "facade_id": "service-plan-context",
        "facade_version": "1",
        "interface": {**interface, "sha256": sha256_json(interface)},
    }
    actions = (
        ["compile-core", "emit-checkpoint"]
        if stage["id"] == "stage-1"
        else ["compile-final-plan", "validate-typed-failure"]
    )
    instruction = {
        "facade": {**facade, "sha256": sha256_json(facade)},
        "argument_mode": "bounded-opaque-key",
        "opaque_key": f"{stage['id']}@{candidate['world_ref_id']}",
        "lookup_scope_id": "service-plan-stage-capsules",
        "lookup_scope_version": "1",
        "lookup_scope_sha256": sha256_json(
            {
                "demo_id": manifest["demo_id"],
                "stage_id": stage["id"],
                "world_ref_id": candidate["world_ref_id"],
            }
        ),
        "max_matches": 1,
        "text": stage["instruction"],
        "text_sha256": sha256_json(stage["instruction"]),
    }
    return {
        "kind": "entrance",
        "cardinality": 1,
        "entrance_id": f"entrance:{candidate['revision_id']}:{stage['id']}",
        "instruction": instruction,
        "allowed_actions": actions,
        "allowed_actions_sha256": sha256_json(actions),
    }


def _refusal_result(candidate: dict[str, Any], actual_world_ref_id: str) -> dict[str, Any]:
    return {
        "kind": "typed-refusal",
        "cardinality": 1,
        "code": "stale_world_ref",
        "candidate_ref": candidate["candidate_ref"],
        "expected_world_ref_id": candidate["world_ref_id"],
        "actual_world_ref_id": actual_world_ref_id,
    }


def _guide_receipt(
    *,
    receipt_id: str,
    mode: str,
    candidate: dict[str, Any],
    world_ref_id: str,
    key: str,
    evidential_warranty_ref: str | None,
    authority_warranty_ref: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    evaluator_identity = {
        "id": "service-plan-deterministic-guide",
        "version": "1",
        "implementation_sha256": sha256_json(
            {"algorithm": "rule-fact-position-two-warranty-projection", "version": "3"}
        ),
    }
    inputs = {
        "rules_sha256": sha256_json(candidate["rules"]),
        "admitted_facts_sha256": sha256_json(candidate["facts"]),
        "position_sha256": sha256_json(candidate["position"]),
        "evidential_warranty_ref": evidential_warranty_ref,
        "authority_warranty_ref": authority_warranty_ref,
    }
    request = {"key": key, "world_ref_id": world_ref_id}
    return {
        "schema_version": GUIDE_RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "mode": mode,
        "candidate_ref": candidate["candidate_ref"],
        "world_ref_id": world_ref_id,
        "inputs": inputs,
        "inputs_sha256": sha256_json(inputs),
        "evaluator": evaluator_identity,
        "request": request,
        "request_sha256": sha256_json(request),
        "result": result,
        "result_sha256": sha256_json(result),
    }


def _traversal_receipt(
    *,
    receipt_id: str,
    candidate: dict[str, Any],
    guide_receipt_id: str,
    start_world_ref_id: str,
    end_world_ref_id: str,
    events: list[dict[str, Any]],
    outcome: str = "accepted",
    fresh: bool = True,
    bypass: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": TRAVERSAL_RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "candidate_ref": candidate["candidate_ref"],
        "guide_receipt_id": guide_receipt_id,
        "executor_id": "scripted-executor",
        "world_span": {
            "start_world_ref_id": start_world_ref_id,
            "end_world_ref_id": end_world_ref_id,
            "closed": True,
            "continuous": True,
        },
        "events": events,
        "trace_sha256": sha256_json(events),
        "fresh": fresh,
        "bypass": bypass,
        "outcome": outcome,
    }


def _path_certificate(
    *,
    certificate_id: str,
    candidate: dict[str, Any],
    traversal: dict[str, Any],
    guide_receipt_id: str,
) -> dict[str, Any]:
    projection = {
        "schema_version": PATH_CERTIFICATE_SCHEMA,
        "certificate_id": certificate_id,
        "candidate_ref": candidate["candidate_ref"],
        "traversal_receipt_id": traversal["receipt_id"],
        "guide_receipt_id": guide_receipt_id,
        "scope": candidate["scope"],
        "issuer_id": "fixture-path-verifier",
        "decision": "accepted",
        "fresh": True,
        "no_bypass": True,
    }
    return {**projection, "certificate_sha256": sha256_json(projection)}


def _evidential_warranty(
    *,
    warranty_id: str,
    candidate: dict[str, Any],
    certificate_id: str,
    world_ref_id: str,
    state: str,
    assessed_at_sequence: int,
    prior_assessment_ref: str | None,
) -> dict[str, Any]:
    projection = {
        "schema_version": EVIDENTIAL_WARRANTY_SCHEMA,
        "warranty_id": warranty_id,
        "candidate_ref": candidate["candidate_ref"],
        "assignment_id": candidate["position"]["role_assignment"]["assignment_id"],
        "path_certificate_id": certificate_id,
        "claim": "the admitted actor-role assignment remains factually and lifecycle-valid for the certified capsule-delivery path at the assessed WorldRef",
        "scope": candidate["scope"],
        "world_ref_id": world_ref_id,
        "rule_ref": f"{candidate['rules'][0]['rule_id']}@{candidate['rules'][0]['version']}",
        "assessor_id": "fixture-warranty-assessor",
        "state": state,
        "assessed_at_sequence": assessed_at_sequence,
        "prior_assessment_ref": prior_assessment_ref,
        "invalidation_predicates": [
            "world_ref_changed",
            "candidate_semantics_changed",
            "rule_version_changed",
        ],
    }
    return {**projection, "assessment_sha256": sha256_json(projection)}


def _authority_warranty(
    *,
    warranty_id: str,
    candidate: dict[str, Any],
    world_ref_id: str,
    state: str,
    assessed_at_sequence: int,
    prior_assessment_ref: str | None,
) -> dict[str, Any]:
    assignment = candidate["position"]["role_assignment"]
    role_definition = candidate["position"]["role_definition"]
    projection = {
        "schema_version": AUTHORITY_WARRANTY_SCHEMA,
        "warranty_id": warranty_id,
        "candidate_ref": candidate["candidate_ref"],
        "assignment_id": assignment["assignment_id"],
        "claim": "the declared issuer may bind the actor to the role and scope",
        "scope": assignment["scope"],
        "world_ref_id": world_ref_id,
        "rule_ref": f"{role_definition['role_definition_id']}@{role_definition['version']}",
        "issuer_id": "fixture-authority-issuer",
        "state": state,
        "assessed_at_sequence": assessed_at_sequence,
        "prior_assessment_ref": prior_assessment_ref,
        "invalidation_predicates": [
            "assignment_revoked",
            "issuer_scope_changed",
            "role_rule_superseded",
            "generation_changed",
        ],
    }
    return {**projection, "assessment_sha256": sha256_json(projection)}


def build_service_plan_bundle(demo_root: Path) -> dict[str, Any]:
    manifest = load_json(demo_root / "DEMO.json")
    world_l0 = _fixture(demo_root, manifest, "world_l0")
    world_l1 = _fixture(demo_root, manifest, "world_l1")
    expected_plan = _fixture(demo_root, manifest, "expected_plan")
    timeline_events = [{**manifest["context_event"], "event_sha256": manifest["context_event_sha256"]}]
    empty_prefix_sha256 = sha256_json([])
    l1_prefix_sha256 = sha256_json(timeline_events)
    world_ref_l0 = _world_ref(
        manifest,
        world_ref_id="world-L0",
        fixture_ref=manifest["fixtures"]["world_l0"]["path"],
        fact_sha256=manifest["fixtures"]["world_l0"]["content_sha256"],
        through_sequence=0,
        prefix_sha256=empty_prefix_sha256,
    )
    world_ref_l1 = _world_ref(
        manifest,
        world_ref_id="world-L1",
        fixture_ref=manifest["fixtures"]["world_l1"]["path"],
        fact_sha256=manifest["fixtures"]["world_l1"]["content_sha256"],
        through_sequence=1,
        prefix_sha256=l1_prefix_sha256,
    )
    stages = {stage["id"]: stage for stage in manifest["task"]["stages"]}
    r0 = _candidate(
        candidate_id="service-plan-corridor",
        revision_id="r0",
        world_ref=world_ref_l0,
        stage=stages["stage-1"],
    )
    r1 = _candidate(
        candidate_id="service-plan-corridor",
        revision_id="r1",
        world_ref=world_ref_l1,
        stage=stages["stage-2"],
    )

    result_r0 = _entrance_result(manifest, r0, stages["stage-1"])
    result_r1 = _entrance_result(manifest, r1, stages["stage-2"])
    result_r0_stale = _refusal_result(r0, "world-L1")
    guide_receipts = [
        _guide_receipt(
            receipt_id="gr-r0-canary-w0",
            mode="certification-canary",
            candidate=r0,
            world_ref_id="world-L0",
            key="stage-1",
            evidential_warranty_ref=None,
            authority_warranty_ref=None,
            result=result_r0,
        ),
        _guide_receipt(
            receipt_id="gr-r0-runtime-w0",
            mode="runtime",
            candidate=r0,
            world_ref_id="world-L0",
            key="stage-1",
            evidential_warranty_ref="ew-r0-live-w0",
            authority_warranty_ref="aw-r0-live-w0",
            result=result_r0,
        ),
        _guide_receipt(
            receipt_id="gr-r0-runtime-w1-refusal",
            mode="runtime",
            candidate=r0,
            world_ref_id="world-L1",
            key="stage-1",
            evidential_warranty_ref="ew-r0-lapsed-w1",
            authority_warranty_ref="aw-r0-live-w1",
            result=result_r0_stale,
        ),
        _guide_receipt(
            receipt_id="gr-r1-canary-w1",
            mode="certification-canary",
            candidate=r1,
            world_ref_id="world-L1",
            key="stage-2",
            evidential_warranty_ref=None,
            authority_warranty_ref=None,
            result=result_r1,
        ),
        _guide_receipt(
            receipt_id="gr-r1-runtime-w1",
            mode="runtime",
            candidate=r1,
            world_ref_id="world-L1",
            key="stage-2",
            evidential_warranty_ref="ew-r1-live-w1",
            authority_warranty_ref="aw-r1-live-w1",
            result=result_r1,
        ),
    ]
    guide_by_id = {receipt["receipt_id"]: receipt for receipt in guide_receipts}

    traversals = [
        _traversal_receipt(
            receipt_id="tr-r0-canary",
            candidate=r0,
            guide_receipt_id="gr-r0-canary-w0",
            start_world_ref_id="world-L0",
            end_world_ref_id="world-L0",
            events=[
                {
                    "sequence": 1,
                    "kind": "guide-result-consumed",
                    "guide_receipt_id": "gr-r0-canary-w0",
                    "result_sha256": guide_by_id["gr-r0-canary-w0"]["result_sha256"],
                }
            ],
        ),
        _traversal_receipt(
            receipt_id="tr-r0-execution",
            candidate=r0,
            guide_receipt_id="gr-r0-runtime-w0",
            start_world_ref_id="world-L0",
            end_world_ref_id="world-L1",
            events=[
                {
                    "sequence": 1,
                    "kind": "guide-consumed",
                    "guide_receipt_id": "gr-r0-runtime-w0",
                    "instruction_sha256": result_r0["instruction"]["text_sha256"],
                },
                {
                    "sequence": 2,
                    "kind": "checkpoint",
                    "event_sha256": manifest["context_event_sha256"],
                    "from_world_ref_id": "world-L0",
                    "to_world_ref_id": "world-L1",
                },
            ],
        ),
        _traversal_receipt(
            receipt_id="tr-r1-canary",
            candidate=r1,
            guide_receipt_id="gr-r1-canary-w1",
            start_world_ref_id="world-L1",
            end_world_ref_id="world-L1",
            events=[
                {
                    "sequence": 1,
                    "kind": "guide-result-consumed",
                    "guide_receipt_id": "gr-r1-canary-w1",
                    "result_sha256": guide_by_id["gr-r1-canary-w1"]["result_sha256"],
                }
            ],
        ),
        _traversal_receipt(
            receipt_id="tr-r1-execution",
            candidate=r1,
            guide_receipt_id="gr-r1-runtime-w1",
            start_world_ref_id="world-L1",
            end_world_ref_id="world-L1",
            events=[
                {
                    "sequence": 1,
                    "kind": "guide-consumed",
                    "guide_receipt_id": "gr-r1-runtime-w1",
                    "instruction_sha256": result_r1["instruction"]["text_sha256"],
                },
                {
                    "sequence": 2,
                    "kind": "task-output-evaluated",
                    "output_sha256": sha256_json(expected_plan),
                },
            ],
        ),
    ]
    traversal_by_id = {receipt["receipt_id"]: receipt for receipt in traversals}
    certificates = [
        _path_certificate(
            certificate_id="pc-r0",
            candidate=r0,
            traversal=traversal_by_id["tr-r0-canary"],
            guide_receipt_id="gr-r0-canary-w0",
        ),
        _path_certificate(
            certificate_id="pc-r1",
            candidate=r1,
            traversal=traversal_by_id["tr-r1-canary"],
            guide_receipt_id="gr-r1-canary-w1",
        ),
    ]
    evidential_warranties = [
        _evidential_warranty(
            warranty_id="ew-r0-live-w0",
            candidate=r0,
            certificate_id="pc-r0",
            world_ref_id="world-L0",
            state="live",
            assessed_at_sequence=0,
            prior_assessment_ref=None,
        ),
        _evidential_warranty(
            warranty_id="ew-r0-lapsed-w1",
            candidate=r0,
            certificate_id="pc-r0",
            world_ref_id="world-L1",
            state="lapsed",
            assessed_at_sequence=1,
            prior_assessment_ref="ew-r0-live-w0",
        ),
        _evidential_warranty(
            warranty_id="ew-r1-live-w1",
            candidate=r1,
            certificate_id="pc-r1",
            world_ref_id="world-L1",
            state="live",
            assessed_at_sequence=1,
            prior_assessment_ref=None,
        ),
    ]
    authority_warranties = [
        _authority_warranty(
            warranty_id="aw-r0-live-w0",
            candidate=r0,
            world_ref_id="world-L0",
            state="live",
            assessed_at_sequence=0,
            prior_assessment_ref=None,
        ),
        _authority_warranty(
            warranty_id="aw-r0-live-w1",
            candidate=r0,
            world_ref_id="world-L1",
            state="live",
            assessed_at_sequence=1,
            prior_assessment_ref="aw-r0-live-w0",
        ),
        _authority_warranty(
            warranty_id="aw-r1-live-w1",
            candidate=r1,
            world_ref_id="world-L1",
            state="live",
            assessed_at_sequence=1,
            prior_assessment_ref=None,
        ),
    ]

    actual_plan = compile_service_plan(world_l1)
    typed_failure = False
    try:
        compile_service_plan(
            {"services": [{"service": "api", "status": "ready", "capacity": True}]}
        )
    except DemoDataError as exc:
        typed_failure = exc.code == "invalid_capacity"
    task_checks = {
        "task_output_exact": actual_plan == expected_plan,
        "checkpoint_exactly_once": len(timeline_events) == 1
        and timeline_events[0]["event"] == manifest["task"]["checkpoint"],
        "typed_failure_preserves_output": typed_failure,
    }
    task_score = {"task_pass": all(task_checks.values()), "checks": task_checks}
    stage1_digest = sha256_json(stages["stage-1"]["instruction"])
    stage2_digest = sha256_json(stages["stage-2"]["instruction"])
    corridor_checks = {
        "u_to_c0": True,
        "deterministic_entrance": guide_by_id["gr-r0-canary-w0"]["result_sha256"]
        == guide_by_id["gr-r0-runtime-w0"]["result_sha256"],
        "same_generation_raw_prefix_extension": all(
            world_ref_l0[key] == world_ref_l1[key]
            for key in (
                "project_id",
                "run_id",
                "generation_id",
                "repository_url",
                "base_commit",
                "environment_sha256",
            )
        )
        and world_ref_l0["evidence_prefix"]["stream_id"]
        == world_ref_l1["evidence_prefix"]["stream_id"]
        and world_ref_l0["evidence_prefix"]["admission"]["rule_revision"]
        == world_ref_l1["evidence_prefix"]["admission"]["rule_revision"]
        and world_ref_l0["evidence_prefix"]["admission"]["rule_sha256"]
        == world_ref_l1["evidence_prefix"]["admission"]["rule_sha256"]
        and world_ref_l0["evidence_prefix"]["projector"]
        == world_ref_l1["evidence_prefix"]["projector"]
        and world_ref_l0["evidence_prefix"]["through_sequence"] == 0
        and world_ref_l1["evidence_prefix"]["through_sequence"] == 1,
        "stale_refusal_before_reentry": result_r0_stale["code"] == "stale_world_ref",
        "immutable_warranty_history": len([w for w in evidential_warranties if w["candidate_ref"] == r0["candidate_ref"]]) == 2,
        "u_to_c1": True,
        "dual_live_assignment": all(
            receipt["inputs"].get("evidential_warranty_ref")
            and receipt["inputs"].get("authority_warranty_ref")
            for receipt in guide_receipts
            if receipt["mode"] == "runtime" and receipt["result"]["kind"] == "entrance"
        ),
        "no_bypass": all(not receipt["bypass"] for receipt in traversals),
        "authority_log_optional": manifest["authority_log_status"] == "not_assessed",
    }
    execution_pair = {
        "kind": "deterministic-parity-fixture",
        "common": {
            "task_sha256": manifest["task_sha256"],
            "base_commit": manifest["subject"]["base_commit"],
            "environment_sha256": manifest["subject"]["environment_sha256"],
            "context_event_sha256": manifest["context_event_sha256"],
            "evaluator_sha256": manifest["evaluator_sha256"],
            "output_sha256": sha256_json(actual_plan),
        },
        "control": {
            "condition": {"system": "task-only", "knowledge": "task-only"},
            "stage_instruction_sha256": [stage1_digest, stage2_digest],
            "checkpoint_count": 1,
            "final_world_ref_id": "world-L1",
            "task_output": actual_plan,
            "task_score": copy.deepcopy(task_score),
        },
        "treatment": {
            "condition": {"system": "corridor", "knowledge": "task-only"},
            "stage_instruction_sha256": [
                result_r0["instruction"]["text_sha256"],
                result_r1["instruction"]["text_sha256"],
            ],
            "checkpoint_count": 1,
            "final_world_ref_id": "world-L1",
            "task_output": actual_plan,
            "task_score": copy.deepcopy(task_score),
            "corridor_score": {
                "corridor_e2e_pass": all(corridor_checks.values()),
                "checks": corridor_checks,
            },
        },
    }

    return {
        "schema_version": BUNDLE_SCHEMA,
        "demo_id": manifest["demo_id"],
        "classification": manifest["classification"],
        "evidence_strength": manifest["evidence_strength"],
        "normative": False,
        "benchmark_result": False,
        "causal_claim_allowed": False,
        "authority_log_status": "not_assessed",
        "manifest_sha256": sha256_json(manifest),
        "timeline_events": timeline_events,
        "world_refs": [world_ref_l0, world_ref_l1],
        "u_states": [
            {
                "u_state_id": "u0",
                "trigger": "no_live_warranty",
                "diagnostic_basis": "method-paper-draft-v2",
                "advisory": True,
                "opens_candidate_ref": r0["candidate_ref"],
            },
            {
                "u_state_id": "u1",
                "trigger": "stale_evidential_warranty",
                "diagnostic_basis": "ew-r0-lapsed-w1",
                "advisory": False,
                "opens_candidate_ref": r1["candidate_ref"],
            },
        ],
        "candidate_projections": [r0, r1],
        "guide_receipts": guide_receipts,
        "traversal_receipts": traversals,
        "path_certificates": certificates,
        "evidential_warranties": evidential_warranties,
        "authority_warranties": authority_warranties,
        "reentries": [
            {
                "reentry_id": "reentry-r0-r1",
                "from_candidate_ref": r0["candidate_ref"],
                "to_candidate_ref": r1["candidate_ref"],
                "trigger_warranty_ref": "ew-r0-lapsed-w1",
                "reason": "world_prefix_advanced",
                "history_rewritten": False,
            }
        ],
        "fixture_current_scopes": [
            {
                "candidate_ref": r1["candidate_ref"],
                "scope": r1["scope"],
                "world_ref_id": "world-L1",
                "evidential_warranty_ref": "ew-r1-live-w1",
                "authority_warranty_ref": "aw-r1-live-w1",
            }
        ],
        "execution_pair": execution_pair,
        "known_limits": manifest["known_limits"],
    }


def _validate_demo_manifest(demo_root: Path) -> tuple[ValidationReport, dict[str, Any] | None]:
    report = ValidationReport()
    manifest_path = demo_root / "DEMO.json"
    try:
        manifest = load_json(manifest_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        report.error("DEMO_JSON", str(manifest_path), str(exc))
        return report, None
    top = _exact_keys(
        manifest,
        {
            "schema_version",
            "demo_id",
            "classification",
            "evidence_strength",
            "normative",
            "benchmark_result",
            "causal_claim_allowed",
            "authority_log_status",
            "project_id",
            "run_id",
            "generation_id",
            "subject",
            "environment",
            "task",
            "task_sha256",
            "fixtures",
            "projector",
            "projector_sha256",
            "admission",
            "admission_rule_sha256",
            "context_event",
            "context_event_sha256",
            "evaluator",
            "evaluator_sha256",
            "expected_runtime_evidence",
            "observed_docker_pair",
            "known_limits",
        },
        report,
        "DEMO.json",
    )
    if top is None:
        return report, None
    if manifest.get("schema_version") != DEMO_SCHEMA:
        report.error("DEMO_SCHEMA", "DEMO.json.schema_version", f"must be {DEMO_SCHEMA}")
    _string(manifest.get("demo_id"), report, "DEMO.json.demo_id")
    if manifest.get("classification") != "engineering-e2e-smoke":
        report.error("DEMO_CLASSIFICATION", "DEMO.json.classification", "must be engineering-e2e-smoke")
    if manifest.get("evidence_strength") != "synthetic-fixture":
        report.error("DEMO_EVIDENCE_STRENGTH", "DEMO.json.evidence_strength", "must be synthetic-fixture")
    for key in ("normative", "benchmark_result", "causal_claim_allowed"):
        value = _boolean(manifest.get(key), report, f"DEMO.json.{key}")
        if value is not False:
            report.error("DEMO_CLAIM_BOUNDARY", f"DEMO.json.{key}", "must be false")
    if manifest.get("authority_log_status") != "not_assessed":
        report.error("DEMO_AUTHORITY_LOG", "DEMO.json.authority_log_status", "must be not_assessed")
    for key in ("project_id", "run_id", "generation_id"):
        _string(manifest.get(key), report, f"DEMO.json.{key}")

    subject = _exact_keys(
        manifest.get("subject"),
        {"repository_url", "base_commit", "base_tree", "environment_sha256"},
        report,
        "DEMO.json.subject",
    )
    if subject is not None:
        _strict_https(subject.get("repository_url"), report, "DEMO.json.subject.repository_url")
        for key in ("base_commit", "base_tree"):
            value = subject.get(key)
            if not isinstance(value, str) or not GIT_SHA1_RE.fullmatch(value):
                report.error("GIT_ID", f"DEMO.json.subject.{key}", "must be a full lowercase Git object id")
        _digest(subject.get("environment_sha256"), report, "DEMO.json.subject.environment_sha256")
    environment = manifest.get("environment")
    if not isinstance(environment, dict):
        report.error("ENVIRONMENT", "DEMO.json.environment", "must be an object")
    else:
        expected_environment_digest = sha256_json(environment)
        if subject is not None and subject.get("environment_sha256") != expected_environment_digest:
            report.error("ENVIRONMENT_HASH", "DEMO.json.subject.environment_sha256", "does not match environment")

    task = manifest.get("task")
    if not isinstance(task, dict):
        report.error("TASK", "DEMO.json.task", "must be an object")
    elif manifest.get("task_sha256") != sha256_json(task):
        report.error("TASK_HASH", "DEMO.json.task_sha256", "does not match task")
    else:
        stages = task.get("stages")
        if not isinstance(stages, list) or [stage.get("id") for stage in stages if isinstance(stage, dict)] != ["stage-1", "stage-2"]:
            report.error("TASK_STAGES", "DEMO.json.task.stages", "must declare stage-1 then stage-2")
        if task.get("checkpoint") != "core-ready":
            report.error("TASK_CHECKPOINT", "DEMO.json.task.checkpoint", "must be core-ready")
    _digest(manifest.get("task_sha256"), report, "DEMO.json.task_sha256")

    fixtures = _exact_keys(
        manifest.get("fixtures"),
        {"world_l0", "world_l1", "expected_plan"},
        report,
        "DEMO.json.fixtures",
    )
    if fixtures is not None:
        for fixture_id, spec in fixtures.items():
            location = f"DEMO.json.fixtures.{fixture_id}"
            spec_object = _exact_keys(spec, {"path", "content_sha256"}, report, location)
            if spec_object is None:
                continue
            path_text = _string(spec_object.get("path"), report, f"{location}.path")
            expected_digest = _digest(spec_object.get("content_sha256"), report, f"{location}.content_sha256")
            if path_text is None:
                continue
            path = (demo_root / path_text).resolve()
            if demo_root.resolve() not in path.parents or path.is_symlink() or not path.is_file():
                report.error("FIXTURE_PATH", f"{location}.path", "must resolve to a regular in-demo file")
                continue
            try:
                value = load_json(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                report.error("FIXTURE_JSON", str(path), str(exc))
                continue
            if expected_digest is not None and expected_digest != sha256_json(value):
                report.error("FIXTURE_HASH", f"{location}.content_sha256", "does not match canonical fixture bytes")

    for value_key, digest_key in (
        ("projector", "projector_sha256"),
        ("admission", "admission_rule_sha256"),
        ("context_event", "context_event_sha256"),
        ("evaluator", "evaluator_sha256"),
    ):
        value = manifest.get(value_key)
        if not isinstance(value, dict):
            report.error("OBJECT", f"DEMO.json.{value_key}", "must be an object")
        expected_digest = _digest(manifest.get(digest_key), report, f"DEMO.json.{digest_key}")
        if isinstance(value, dict) and expected_digest is not None and expected_digest != sha256_json(value):
            report.error("HASH_JOIN", f"DEMO.json.{digest_key}", f"does not match {value_key}")
    text = _string(manifest.get("expected_runtime_evidence"), report, "DEMO.json.expected_runtime_evidence")
    if text is not None:
        path = (demo_root / text).resolve()
        if demo_root.resolve() not in path.parents or path.is_symlink():
            report.error("DEMO_PATH", "DEMO.json.expected_runtime_evidence", "must stay inside the demo tree")
    observed = _exact_keys(
        manifest.get("observed_docker_pair"),
        {"path", "schema_version", "content_sha256"},
        report,
        "DEMO.json.observed_docker_pair",
    )
    if observed is not None:
        observed_path_text = _string(observed.get("path"), report, "DEMO.json.observed_docker_pair.path")
        observed_digest = _digest(observed.get("content_sha256"), report, "DEMO.json.observed_docker_pair.content_sha256")
        if observed.get("schema_version") != "charting-loop/docker-engineering-pair/v1":
            report.error("OBSERVED_PAIR_SCHEMA", "DEMO.json.observed_docker_pair.schema_version", "unexpected schema")
        if observed_path_text is not None:
            observed_path = (demo_root / observed_path_text).resolve()
            if demo_root.resolve() not in observed_path.parents or observed_path.is_symlink() or not observed_path.is_file():
                report.error("OBSERVED_PAIR_PATH", "DEMO.json.observed_docker_pair.path", "must resolve to a regular in-demo file")
            else:
                try:
                    observed_value = load_json(observed_path)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                    report.error("OBSERVED_PAIR_JSON", str(observed_path), str(exc))
                else:
                    if observed_digest is not None and observed_digest != sha256_json(observed_value):
                        report.error("OBSERVED_PAIR_HASH", "DEMO.json.observed_docker_pair.content_sha256", "does not match the observed pair")
                    if not isinstance(observed_value, dict) or observed_value.get("schema_version") != observed.get("schema_version"):
                        report.error("OBSERVED_PAIR_JOIN", str(observed_path), "schema does not match DEMO.json")
                    elif (
                        observed_value.get("benchmark_result") is not False
                        or observed_value.get("causal_claim_allowed") is not False
                        or observed_value.get("authority_warranty_state") != "not_assessed"
                        or observed_value.get("evidence_basis") != "runner-reported-no-raw-proof"
                        or observed_value.get("method_level_c_established") is not False
                        or observed_value.get("independent_verification_established") is not False
                        or observed_value.get("raw_evidence_published") is not False
                    ):
                        report.error("OBSERVED_PAIR_CLAIMS", str(observed_path), "must retain the engineering-only claim boundary")
    limits = _list(manifest.get("known_limits"), report, "DEMO.json.known_limits") or []
    if not limits or any(not isinstance(item, str) or not item for item in limits):
        report.error("KNOWN_LIMITS", "DEMO.json.known_limits", "must contain non-empty strings")
    report.facts.update(
        {
            "schema_version": manifest.get("schema_version"),
            "demo_id": manifest.get("demo_id"),
            "benchmark_result": manifest.get("benchmark_result"),
            "causal_claim_allowed": manifest.get("causal_claim_allowed"),
            "authority_log_status": manifest.get("authority_log_status"),
        }
    )
    return report, manifest


def validate_demo_manifest(demo_root: Path) -> tuple[ValidationReport, dict[str, Any] | None]:
    """Fail closed for malformed manifest or referenced JSON evidence.

    Manifest validation hashes nested JSON objects and referenced fixture files.  Keep
    canonicalization failures (including the declared integer-size bound) inside the
    public validator boundary so the CLI emits a structured INVALID result rather
    than a traceback.
    """

    try:
        return _validate_demo_manifest(demo_root)
    except (
        AttributeError,
        IndexError,
        KeyError,
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        report = ValidationReport()
        report.error(
            "MALFORMED_DEMO_MANIFEST",
            "DEMO.json",
            f"malformed nested value: {type(exc).__name__}",
        )
        return report, None


def _validate_runtime_evidence(
    bundle: Any,
    *,
    manifest: dict[str, Any] | None = None,
    demo_root: Path | None = None,
) -> ValidationReport:
    report = ValidationReport()
    top = _exact_keys(
        bundle,
        {
            "schema_version",
            "demo_id",
            "classification",
            "evidence_strength",
            "normative",
            "benchmark_result",
            "causal_claim_allowed",
            "authority_log_status",
            "manifest_sha256",
            "timeline_events",
            "world_refs",
            "u_states",
            "candidate_projections",
            "guide_receipts",
            "traversal_receipts",
            "path_certificates",
            "evidential_warranties",
            "authority_warranties",
            "reentries",
            "fixture_current_scopes",
            "execution_pair",
            "known_limits",
        },
        report,
        "runtime-evidence",
    )
    if top is None:
        return report
    if bundle.get("schema_version") != BUNDLE_SCHEMA:
        report.error("BUNDLE_SCHEMA", "runtime-evidence.schema_version", f"must be {BUNDLE_SCHEMA}")
    if bundle.get("classification") != "engineering-e2e-smoke":
        report.error("BUNDLE_CLASSIFICATION", "runtime-evidence.classification", "must be engineering-e2e-smoke")
    if bundle.get("evidence_strength") != "synthetic-fixture":
        report.error("BUNDLE_EVIDENCE_STRENGTH", "runtime-evidence.evidence_strength", "must be synthetic-fixture")
    for key in ("normative", "benchmark_result", "causal_claim_allowed"):
        value = _boolean(bundle.get(key), report, f"runtime-evidence.{key}")
        if value is not False:
            report.error("BUNDLE_CLAIM_BOUNDARY", f"runtime-evidence.{key}", "must be false")
    if bundle.get("authority_log_status") != "not_assessed":
        report.error("BUNDLE_AUTHORITY_LOG", "runtime-evidence.authority_log_status", "must be not_assessed")
    _digest(bundle.get("manifest_sha256"), report, "runtime-evidence.manifest_sha256")
    if manifest is not None:
        if bundle.get("demo_id") != manifest.get("demo_id"):
            report.error("DEMO_JOIN", "runtime-evidence.demo_id", "does not match DEMO.json")
        if bundle.get("manifest_sha256") != sha256_json(manifest):
            report.error("DEMO_JOIN", "runtime-evidence.manifest_sha256", "does not match DEMO.json")
        if bundle.get("known_limits") != manifest.get("known_limits"):
            report.error("LIMITS_JOIN", "runtime-evidence.known_limits", "must match DEMO.json")

    timeline_events = _list(bundle.get("timeline_events"), report, "runtime-evidence.timeline_events") or []
    event_sequences: list[int] = []
    for index, event in enumerate(timeline_events):
        location = f"runtime-evidence.timeline_events[{index}]"
        record = _exact_keys(
            event,
            {"sequence", "event", "from_world", "to_world", "fixture", "event_sha256"},
            report,
            location,
        )
        if record is None:
            continue
        sequence = _integer(record.get("sequence"), report, f"{location}.sequence")
        if sequence is not None:
            event_sequences.append(sequence)
        for key in ("event", "from_world", "to_world", "fixture"):
            _string(record.get(key), report, f"{location}.{key}")
        digest = _digest(record.get("event_sha256"), report, f"{location}.event_sha256")
        if digest is not None and digest != sha256_json({key: value for key, value in record.items() if key != "event_sha256"}):
            report.error("EVENT_HASH", f"{location}.event_sha256", "does not match the event")
    if event_sequences != list(range(1, len(event_sequences) + 1)):
        report.error("EVENT_SEQUENCE", "runtime-evidence.timeline_events", "must be contiguous from 1")
    if manifest is not None and timeline_events:
        expected_event = {**manifest["context_event"], "event_sha256": manifest["context_event_sha256"]}
        if timeline_events != [expected_event]:
            report.error("EVENT_JOIN", "runtime-evidence.timeline_events", "must match the one frozen context event")

    worlds = _unique_map(bundle.get("world_refs"), "world_ref_id", report, "runtime-evidence.world_refs")
    world_identity: tuple[Any, ...] | None = None
    ordered_prefixes: list[int] = []
    fixture_specs: dict[str, dict[str, Any]] = {}
    expected_worlds: dict[str, dict[str, Any]] = {}
    if manifest is not None:
        fixture_specs = {spec["path"]: spec for spec in manifest["fixtures"].values()}
        expected_worlds = {
            "world-L0": _world_ref(
                manifest,
                world_ref_id="world-L0",
                fixture_ref=manifest["fixtures"]["world_l0"]["path"],
                fact_sha256=manifest["fixtures"]["world_l0"]["content_sha256"],
                through_sequence=0,
                prefix_sha256=sha256_json([]),
            ),
            "world-L1": _world_ref(
                manifest,
                world_ref_id="world-L1",
                fixture_ref=manifest["fixtures"]["world_l1"]["path"],
                fact_sha256=manifest["fixtures"]["world_l1"]["content_sha256"],
                through_sequence=1,
                prefix_sha256=sha256_json(timeline_events),
            ),
        }
    for world_id, world in worlds.items():
        location = f"runtime-evidence.world_refs[{world_id}]"
        _exact_keys(
            world,
            {
                "world_ref_id", "project_id", "run_id", "generation_id",
                "repository_url", "base_commit", "environment_sha256",
                "fixture_ref", "evidence_prefix", "derived_state_sha256",
            },
            report,
            location,
        )
        for key in ("project_id", "run_id", "generation_id"):
            _string(world.get(key), report, f"{location}.{key}")
        repository_url = _strict_https(world.get("repository_url"), report, f"{location}.repository_url")
        base_commit = world.get("base_commit")
        if not isinstance(base_commit, str) or not GIT_SHA1_RE.fullmatch(base_commit):
            report.error("WORLD_BASE", f"{location}.base_commit", "must be a full lowercase commit")
        environment_sha256 = _digest(world.get("environment_sha256"), report, f"{location}.environment_sha256")
        fixture_ref = _string(world.get("fixture_ref"), report, f"{location}.fixture_ref")
        derived_state_sha256 = _digest(
            world.get("derived_state_sha256"),
            report,
            f"{location}.derived_state_sha256",
        )
        prefix = _exact_keys(
            world.get("evidence_prefix"),
            {"stream_id", "through_sequence", "prefix_sha256", "admission", "projector"},
            report,
            f"{location}.evidence_prefix",
        )
        if prefix is None:
            continue
        stream_id = _string(prefix.get("stream_id"), report, f"{location}.evidence_prefix.stream_id")
        through_sequence = _integer(prefix.get("through_sequence"), report, f"{location}.evidence_prefix.through_sequence")
        prefix_sha256 = _digest(prefix.get("prefix_sha256"), report, f"{location}.evidence_prefix.prefix_sha256")
        projector = _exact_keys(
            prefix.get("projector"),
            {"schema_version", "algorithm_id", "algorithm_version", "algorithm_sha256"},
            report,
            f"{location}.evidence_prefix.projector",
        )
        projector_identity: tuple[Any, ...] = (None, None, None, None)
        if projector is not None:
            projector_identity = (
                _string(projector.get("schema_version"), report, f"{location}.evidence_prefix.projector.schema_version"),
                _string(projector.get("algorithm_id"), report, f"{location}.evidence_prefix.projector.algorithm_id"),
                _string(projector.get("algorithm_version"), report, f"{location}.evidence_prefix.projector.algorithm_version"),
                _digest(projector.get("algorithm_sha256"), report, f"{location}.evidence_prefix.projector.algorithm_sha256"),
            )
        admission = _exact_keys(
            prefix.get("admission"),
            {"receipt_id", "admitted_root_sha256", "rule_revision", "rule_sha256"},
            report,
            f"{location}.evidence_prefix.admission",
        )
        admission_rule_identity: tuple[Any, ...] = (None, None)
        if admission is not None:
            _string(admission.get("receipt_id"), report, f"{location}.evidence_prefix.admission.receipt_id")
            _digest(admission.get("admitted_root_sha256"), report, f"{location}.evidence_prefix.admission.admitted_root_sha256")
            admission_rule_identity = (
                _string(admission.get("rule_revision"), report, f"{location}.evidence_prefix.admission.rule_revision"),
                _digest(admission.get("rule_sha256"), report, f"{location}.evidence_prefix.admission.rule_sha256"),
            )
        identity = (
            world.get("project_id"), world.get("run_id"), world.get("generation_id"),
            repository_url, base_commit, environment_sha256, stream_id,
            *admission_rule_identity, *projector_identity,
        )
        if world_identity is None:
            world_identity = identity
        elif identity != world_identity:
            report.error("WORLD_LINEAGE", location, "all WorldRefs in one span must share project, run, generation, repository, base, environment, stream, admission rules, and projector")
        if through_sequence is not None and through_sequence >= 0:
            ordered_prefixes.append(through_sequence)
            prefix_events = [event for event in timeline_events if type(event.get("sequence")) is int and event["sequence"] <= through_sequence]
            if prefix_sha256 is not None and prefix_sha256 != sha256_json(prefix_events):
                report.error("WORLD_PREFIX_HASH", f"{location}.evidence_prefix.prefix_sha256", "does not match the contiguous raw event prefix")
        else:
            report.error("WORLD_PREFIX", f"{location}.evidence_prefix.through_sequence", "must be non-negative")
        if fixture_ref in fixture_specs and derived_state_sha256 != fixture_specs[fixture_ref].get("content_sha256"):
            report.error("WORLD_FACT_JOIN", f"{location}.derived_state_sha256", "does not match the frozen derived fixture")
        elif manifest is not None and fixture_ref not in fixture_specs:
            report.error("WORLD_FIXTURE_JOIN", f"{location}.fixture_ref", "must resolve to a frozen fixture")
        if admission is not None and fixture_ref is not None and derived_state_sha256 is not None:
            expected_admitted_root = sha256_json(
                {"fixture_ref": fixture_ref, "fact_sha256": derived_state_sha256}
            )
            if admission.get("admitted_root_sha256") != expected_admitted_root:
                report.error(
                    "WORLD_ADMISSION_ROOT",
                    f"{location}.evidence_prefix.admission.admitted_root_sha256",
                    "must bind the admitted derived Fact set, not raw timeline presence",
                )
        if manifest is not None and world != expected_worlds.get(world_id):
            report.error(
                "WORLD_MANIFEST_JOIN",
                location,
                "must exactly match the frozen DEMO subject, fixture, prefix, and projector",
            )
    if ordered_prefixes != list(range(len(ordered_prefixes))):
        report.error(
            "WORLD_PREFIX_SEQUENCE",
            "runtime-evidence.world_refs",
            "prefixes must be ordered and contiguous from zero",
        )

    candidates = _unique_map(bundle.get("candidate_projections"), "candidate_ref", report, "runtime-evidence.candidate_projections")
    candidate_role_rules: dict[str, dict[str, Any]] = {}
    candidate_assignment_facts: dict[str, dict[str, Any]] = {}
    for candidate_ref, candidate in candidates.items():
        location = f"runtime-evidence.candidate_projections[{candidate_ref}]"
        _exact_keys(
            candidate,
            {"candidate_id", "candidate_ref", "revision_id", "state", "world_ref_id", "stage_id", "scope", "builder_id", "rules", "facts", "position", "semantic_sha256"},
            report,
            location,
        )
        for key in ("candidate_id", "revision_id", "world_ref_id", "stage_id", "scope", "builder_id"):
            _string(candidate.get(key), report, f"{location}.{key}")
        if (
            isinstance(candidate.get("candidate_id"), str)
            and isinstance(candidate.get("revision_id"), str)
            and candidate_ref
            != f"candidate:{candidate['candidate_id']}@{candidate['revision_id']}"
        ):
            report.error(
                "CANDIDATE_REF",
                f"{location}.candidate_ref",
                "must derive from candidate_id and revision_id",
            )
        if candidate.get("state") != "frozen":
            report.error("CANDIDATE_STATE", f"{location}.state", "must be frozen")
        if candidate.get("world_ref_id") not in worlds:
            report.error("CANDIDATE_WORLD", f"{location}.world_ref_id", "must resolve to one WorldRef")
        if not isinstance(candidate.get("rules"), list) or not candidate.get("rules"):
            report.error("CANDIDATE_RULES", f"{location}.rules", "must contain rules")
        if not isinstance(candidate.get("facts"), list) or not candidate.get("facts"):
            report.error("CANDIDATE_FACTS", f"{location}.facts", "must contain admitted facts")
        if not isinstance(candidate.get("position"), dict):
            report.error("CANDIDATE_POSITION", f"{location}.position", "must be an object")
        else:
            position = _exact_keys(
                candidate["position"],
                {"role_definition", "role_assignment", "coordinate"},
                report,
                f"{location}.position",
            )
            if position is not None:
                role_definition = _exact_keys(
                    position.get("role_definition"),
                    {"role_definition_id", "role_id", "version", "scope"},
                    report,
                    f"{location}.position.role_definition",
                )
                assignment = _exact_keys(
                    position.get("role_assignment"),
                    {
                        "assignment_id", "holder", "role_id", "scope",
                        "assignment_fact_id", "world_ref_id",
                        "required_warranty_kinds",
                    },
                    report,
                    f"{location}.position.role_assignment",
                )
                declared_rules = [
                    rule for rule in candidate.get("rules", []) if isinstance(rule, dict)
                ]
                declared_facts = [
                    fact for fact in candidate.get("facts", []) if isinstance(fact, dict)
                ]
                if role_definition is not None:
                    role_matches = [
                        rule
                        for rule in declared_rules
                        if rule.get("rule_id") == role_definition.get("role_definition_id")
                        and rule.get("rule_kind") == "RoleDefinition"
                        and rule.get("role_id") == role_definition.get("role_id")
                        and rule.get("version") == role_definition.get("version")
                        and rule.get("scope") == role_definition.get("scope")
                    ]
                    if len(role_matches) != 1:
                        report.error(
                            "CANDIDATE_ROLE_DEFINITION_RULE",
                            f"{location}.position.role_definition",
                            "must resolve exactly once to the declared role-definition Rule",
                        )
                    else:
                        candidate_role_rules[candidate_ref] = role_matches[0]
                if assignment is not None:
                    assignment_matches = [
                        fact
                        for fact in declared_facts
                        if fact.get("fact_id") == assignment.get("assignment_fact_id")
                        and fact.get("fact_kind") == "ActorRoleAssignment"
                        and fact.get("assignment_id") == assignment.get("assignment_id")
                        and fact.get("actor_id") == assignment.get("holder")
                        and fact.get("role_id") == assignment.get("role_id")
                        and fact.get("scope") == assignment.get("scope")
                        and fact.get("world_ref_id") == assignment.get("world_ref_id")
                        and fact.get("liveness_state") in {"live", "lapsed", "unknown", "not_assessed"}
                        and isinstance(fact.get("authority_source_id"), str)
                        and bool(fact.get("authority_source_id"))
                    ]
                    if role_definition is not None:
                        assignment_matches = [
                            fact
                            for fact in assignment_matches
                            if fact.get("role_definition_id")
                            == role_definition.get("role_definition_id")
                        ]
                    if len(assignment_matches) != 1:
                        report.error(
                            "CANDIDATE_ASSIGNMENT_FACT",
                            f"{location}.position.role_assignment.assignment_fact_id",
                            "must resolve exactly once to an admitted actor-role Assignment Fact with matching actor, role, scope, world, authority source, and liveness",
                        )
                    else:
                        candidate_assignment_facts[candidate_ref] = assignment_matches[0]
                if role_definition is not None and assignment is not None and (
                    assignment.get("role_id") != role_definition.get("role_id")
                    or assignment.get("scope") != role_definition.get("scope")
                ):
                    report.error(
                        "CANDIDATE_POSITION_BINDING",
                        f"{location}.position.role_assignment",
                        "must bind the declared role definition and scope",
                    )
        digest = _digest(candidate.get("semantic_sha256"), report, f"{location}.semantic_sha256")
        if digest is not None and digest != candidate_semantic_sha256(candidate):
            report.error("CANDIDATE_SEMANTIC_HASH", f"{location}.semantic_sha256", "does not match Candidate semantics")
        for fact in candidate.get("facts") if isinstance(candidate.get("facts"), list) else []:
            if isinstance(fact, dict) and fact.get("world_ref_id") != candidate.get("world_ref_id"):
                report.error("CANDIDATE_FACT_WORLD", f"{location}.facts", "facts must bind the Candidate WorldRef")
            if isinstance(fact, dict) and fact.get("fact_kind") == "ActorRoleAssignment":
                projection = {key: value for key, value in fact.items() if key != "fact_sha256"}
                digest = _digest(fact.get("fact_sha256"), report, f"{location}.facts[{fact.get('fact_id')}].fact_sha256")
                if digest is not None and digest != sha256_json(projection):
                    report.error(
                        "CANDIDATE_ASSIGNMENT_FACT_HASH",
                        f"{location}.facts[{fact.get('fact_id')}].fact_sha256",
                        "does not match the admitted Assignment Fact",
                    )
        if manifest is not None and candidate.get("revision_id") in {"r0", "r1"}:
            revision_id = candidate["revision_id"]
            stage_id = "stage-1" if revision_id == "r0" else "stage-2"
            expected_candidate = _candidate(
                candidate_id="service-plan-corridor",
                revision_id=revision_id,
                world_ref=expected_worlds["world-L0" if revision_id == "r0" else "world-L1"],
                stage=next(stage for stage in manifest["task"]["stages"] if stage["id"] == stage_id),
            )
            if candidate != expected_candidate:
                report.error(
                    "CANDIDATE_FIXTURE_JOIN",
                    location,
                    "must exactly match the frozen demo Candidate projection",
                )

    guide_receipts = _unique_map(bundle.get("guide_receipts"), "receipt_id", report, "runtime-evidence.guide_receipts")
    deterministic_results: dict[tuple[Any, ...], str] = {}
    for receipt_id, receipt in guide_receipts.items():
        location = f"runtime-evidence.guide_receipts[{receipt_id}]"
        _exact_keys(
            receipt,
            {"schema_version", "receipt_id", "mode", "candidate_ref", "world_ref_id", "inputs", "inputs_sha256", "evaluator", "request", "request_sha256", "result", "result_sha256"},
            report,
            location,
        )
        if receipt.get("schema_version") != GUIDE_RECEIPT_SCHEMA:
            report.error("GUIDE_SCHEMA", f"{location}.schema_version", f"must be {GUIDE_RECEIPT_SCHEMA}")
        if receipt.get("mode") not in {"certification-canary", "runtime"}:
            report.error("GUIDE_MODE", f"{location}.mode", "must be certification-canary or runtime")
        candidate = candidates.get(receipt.get("candidate_ref"))
        if candidate is None:
            report.error("GUIDE_CANDIDATE", f"{location}.candidate_ref", "must resolve to one Candidate")
        if receipt.get("world_ref_id") not in worlds:
            report.error("GUIDE_WORLD", f"{location}.world_ref_id", "must resolve to one WorldRef")
        inputs = _exact_keys(
            receipt.get("inputs"),
            {
                "rules_sha256", "admitted_facts_sha256", "position_sha256",
                "evidential_warranty_ref", "authority_warranty_ref",
            },
            report,
            f"{location}.inputs",
        )
        if inputs is not None:
            for key in ("rules_sha256", "admitted_facts_sha256", "position_sha256"):
                _digest(inputs.get(key), report, f"{location}.inputs.{key}")
            if candidate is not None:
                expected_inputs = {
                    "rules_sha256": sha256_json(candidate.get("rules")),
                    "admitted_facts_sha256": sha256_json(candidate.get("facts")),
                    "position_sha256": sha256_json(candidate.get("position")),
                }
                for key, expected in expected_inputs.items():
                    if inputs.get(key) != expected:
                        report.error("GUIDE_INPUT_JOIN", f"{location}.inputs.{key}", "does not match Candidate input")
            if receipt.get("mode") == "certification-canary" and any(
                inputs.get(key) is not None
                for key in ("evidential_warranty_ref", "authority_warranty_ref")
            ):
                report.error("GUIDE_CANARY_WARRANTY", f"{location}.inputs", "both warranties must be null before issuance")
            if receipt.get("mode") == "runtime":
                _string(inputs.get("evidential_warranty_ref"), report, f"{location}.inputs.evidential_warranty_ref")
                _string(inputs.get("authority_warranty_ref"), report, f"{location}.inputs.authority_warranty_ref")
            if receipt.get("inputs_sha256") != sha256_json(inputs):
                report.error("GUIDE_INPUT_HASH", f"{location}.inputs_sha256", "does not match inputs")
        _digest(receipt.get("inputs_sha256"), report, f"{location}.inputs_sha256")
        request = _exact_keys(receipt.get("request"), {"key", "world_ref_id"}, report, f"{location}.request")
        if request is not None:
            _string(request.get("key"), report, f"{location}.request.key")
            if request.get("world_ref_id") != receipt.get("world_ref_id"):
                report.error("GUIDE_REQUEST_WORLD", f"{location}.request.world_ref_id", "must match receipt WorldRef")
            if receipt.get("request_sha256") != sha256_json(request):
                report.error("GUIDE_REQUEST_HASH", f"{location}.request_sha256", "does not match request")
        evaluator = _exact_keys(receipt.get("evaluator"), {"id", "version", "implementation_sha256"}, report, f"{location}.evaluator")
        if evaluator is not None:
            _string(evaluator.get("id"), report, f"{location}.evaluator.id")
            _string(evaluator.get("version"), report, f"{location}.evaluator.version")
            _digest(evaluator.get("implementation_sha256"), report, f"{location}.evaluator.implementation_sha256")
        result = receipt.get("result")
        if not isinstance(result, dict):
            report.error("GUIDE_RESULT", f"{location}.result", "must be an object")
            continue
        if type(result.get("cardinality")) is not int or result.get("cardinality") != 1:
            report.error("GUIDE_CARDINALITY", f"{location}.result.cardinality", "must be integer 1")
        kind = result.get("kind")
        if kind == "entrance":
            _exact_keys(
                result,
                {"kind", "cardinality", "entrance_id", "instruction", "allowed_actions", "allowed_actions_sha256"},
                report,
                f"{location}.result",
            )
            _string(result.get("entrance_id"), report, f"{location}.result.entrance_id")
            actions = _list(result.get("allowed_actions"), report, f"{location}.result.allowed_actions") or []
            if not actions or any(not isinstance(action, str) or not action for action in actions) or len(set(actions)) != len(actions):
                report.error("GUIDE_ACTIONS", f"{location}.result.allowed_actions", "must contain unique strings")
            if result.get("allowed_actions_sha256") != sha256_json(actions):
                report.error("GUIDE_ACTION_HASH", f"{location}.result.allowed_actions_sha256", "does not match actions")
            instruction = _exact_keys(
                result.get("instruction"),
                {"facade", "argument_mode", "opaque_key", "lookup_scope_id", "lookup_scope_version", "lookup_scope_sha256", "max_matches", "text", "text_sha256"},
                report,
                f"{location}.result.instruction",
            )
            if instruction is not None:
                if instruction.get("argument_mode") != "bounded-opaque-key":
                    report.error("GUIDE_ARGUMENT_MODE", f"{location}.result.instruction.argument_mode", "must be bounded-opaque-key")
                for key in ("opaque_key", "lookup_scope_id", "lookup_scope_version", "text"):
                    _string(instruction.get(key), report, f"{location}.result.instruction.{key}")
                if type(instruction.get("max_matches")) is not int or instruction.get("max_matches") != 1:
                    report.error("GUIDE_LOOKUP_BOUND", f"{location}.result.instruction.max_matches", "must be integer 1")
                _digest(instruction.get("lookup_scope_sha256"), report, f"{location}.result.instruction.lookup_scope_sha256")
                if instruction.get("text_sha256") != sha256_json(instruction.get("text")):
                    report.error("GUIDE_INSTRUCTION_HASH", f"{location}.result.instruction.text_sha256", "does not match text")
                facade = _exact_keys(instruction.get("facade"), {"facade_id", "facade_version", "interface", "sha256"}, report, f"{location}.result.instruction.facade")
                if facade is not None:
                    if facade.get("facade_id") != "service-plan-context" or facade.get("facade_version") != "1":
                        report.error("GUIDE_FACADE_IDENTITY", f"{location}.result.instruction.facade", "must use the frozen service-plan-context facade v1")
                    facade_projection = {key: value for key, value in facade.items() if key != "sha256"}
                    if facade.get("sha256") != sha256_json(facade_projection):
                        report.error("GUIDE_FACADE_HASH", f"{location}.result.instruction.facade.sha256", "does not match facade")
                    interface = _exact_keys(facade.get("interface"), {"interface_id", "interface_version", "operation", "sha256"}, report, f"{location}.result.instruction.facade.interface")
                    if interface is not None:
                        if (
                            interface.get("interface_id") != "service-plan-guide-resolve"
                            or interface.get("interface_version") != "1"
                            or interface.get("operation") != "resolve"
                        ):
                            report.error("GUIDE_INTERFACE_IDENTITY", f"{location}.result.instruction.facade.interface", "must use the frozen resolve interface v1")
                        interface_projection = {key: value for key, value in interface.items() if key != "sha256"}
                        if interface.get("sha256") != sha256_json(interface_projection):
                            report.error("GUIDE_INTERFACE_HASH", f"{location}.result.instruction.facade.interface.sha256", "does not match interface")
                if candidate is not None:
                    expected_key = f"{candidate.get('stage_id')}@{candidate.get('world_ref_id')}"
                    if instruction.get("opaque_key") != expected_key:
                        report.error("GUIDE_OPAQUE_KEY", f"{location}.result.instruction.opaque_key", "must bind the Candidate stage and WorldRef")
                    if instruction.get("lookup_scope_id") != "service-plan-stage-capsules" or instruction.get("lookup_scope_version") != "1":
                        report.error("GUIDE_LOOKUP_SCOPE", f"{location}.result.instruction", "must use the frozen stage-capsule scope v1")
                    expected_scope_digest = sha256_json(
                        {
                            "demo_id": bundle.get("demo_id"),
                            "stage_id": candidate.get("stage_id"),
                            "world_ref_id": candidate.get("world_ref_id"),
                        }
                    )
                    if instruction.get("lookup_scope_sha256") != expected_scope_digest:
                        report.error("GUIDE_LOOKUP_SCOPE_HASH", f"{location}.result.instruction.lookup_scope_sha256", "does not match the frozen lookup scope")
                    transition_digests = {
                        rule.get("allowed_actions_sha256")
                        for rule in candidate.get("rules", [])
                        if isinstance(rule, dict) and "allowed_actions_sha256" in rule
                    }
                    if result.get("allowed_actions_sha256") not in transition_digests:
                        report.error("GUIDE_ACTION_RULE", f"{location}.result.allowed_actions_sha256", "must match one Candidate transition Rule")
                    if manifest is not None:
                        stage_matches = [
                            stage
                            for stage in manifest.get("task", {}).get("stages", [])
                            if isinstance(stage, dict) and stage.get("id") == candidate.get("stage_id")
                        ]
                        if len(stage_matches) != 1 or instruction.get("text") != stage_matches[0].get("instruction"):
                            report.error("GUIDE_INSTRUCTION_JOIN", f"{location}.result.instruction.text", "must match the frozen task stage instruction")
        elif kind == "typed-refusal":
            _exact_keys(
                result,
                {"kind", "cardinality", "code", "candidate_ref", "expected_world_ref_id", "actual_world_ref_id"},
                report,
                f"{location}.result",
            )
            if result.get("code") not in {
                "stale",
                "unauthorized",
                "unknown",
                "not_assessed",
                "stale_world_ref",
            }:
                report.error("GUIDE_REFUSAL", f"{location}.result.code", "must be a typed warranty/world refusal")
            if result.get("candidate_ref") != receipt.get("candidate_ref"):
                report.error("GUIDE_REFUSAL_CANDIDATE", f"{location}.result.candidate_ref", "must match receipt Candidate")
            if candidate is not None and result.get("expected_world_ref_id") != candidate.get("world_ref_id"):
                report.error("GUIDE_REFUSAL_EXPECTED_WORLD", f"{location}.result.expected_world_ref_id", "must match Candidate WorldRef")
            if result.get("actual_world_ref_id") != receipt.get("world_ref_id"):
                report.error("GUIDE_REFUSAL_ACTUAL_WORLD", f"{location}.result.actual_world_ref_id", "must match receipt WorldRef")
        else:
            report.error("GUIDE_RESULT_KIND", f"{location}.result.kind", "must be entrance or typed-refusal")
        result_digest = _digest(receipt.get("result_sha256"), report, f"{location}.result_sha256")
        if result_digest is not None and result_digest != sha256_json(result):
            report.error("GUIDE_RESULT_HASH", f"{location}.result_sha256", "does not match result")
        if request is not None and result_digest is not None:
            key = (receipt.get("candidate_ref"), receipt.get("world_ref_id"), request.get("key"))
            prior = deterministic_results.get(key)
            if prior is not None and prior != result_digest:
                report.error("GUIDE_NONDETERMINISTIC", location, "same Candidate, WorldRef, and key produced different results")
            deterministic_results[key] = result_digest

    traversals = _unique_map(bundle.get("traversal_receipts"), "receipt_id", report, "runtime-evidence.traversal_receipts")
    for receipt_id, receipt in traversals.items():
        location = f"runtime-evidence.traversal_receipts[{receipt_id}]"
        _exact_keys(
            receipt,
            {"schema_version", "receipt_id", "candidate_ref", "guide_receipt_id", "executor_id", "world_span", "events", "trace_sha256", "fresh", "bypass", "outcome"},
            report,
            location,
        )
        if receipt.get("schema_version") != TRAVERSAL_RECEIPT_SCHEMA:
            report.error("TRAVERSAL_SCHEMA", f"{location}.schema_version", f"must be {TRAVERSAL_RECEIPT_SCHEMA}")
        candidate = candidates.get(receipt.get("candidate_ref"))
        guide_receipt = guide_receipts.get(receipt.get("guide_receipt_id"))
        if candidate is None:
            report.error("TRAVERSAL_CANDIDATE", f"{location}.candidate_ref", "must resolve to one Candidate")
        if guide_receipt is None:
            report.error("TRAVERSAL_GUIDE", f"{location}.guide_receipt_id", "must resolve to one GuideReceipt")
        elif guide_receipt.get("candidate_ref") != receipt.get("candidate_ref"):
            report.error("TRAVERSAL_GUIDE_CANDIDATE", f"{location}.guide_receipt_id", "GuideReceipt Candidate mismatch")
        _string(receipt.get("executor_id"), report, f"{location}.executor_id")
        span = _exact_keys(
            receipt.get("world_span"),
            {"start_world_ref_id", "end_world_ref_id", "closed", "continuous"},
            report,
            f"{location}.world_span",
        )
        if span is not None:
            start = worlds.get(span.get("start_world_ref_id"))
            end = worlds.get(span.get("end_world_ref_id"))
            if start is None or end is None:
                report.error("WORLDSPAN_REF", f"{location}.world_span", "both endpoints must resolve")
            elif any(
                start.get(key) != end.get(key)
                for key in (
                    "project_id", "run_id", "generation_id", "repository_url",
                    "base_commit", "environment_sha256",
                )
            ):
                report.error("WORLDSPAN_LINEAGE", f"{location}.world_span", "must not cross project, run, generation, repository, base, or environment")
            else:
                start_prefix = start.get("evidence_prefix", {})
                end_prefix = end.get("evidence_prefix", {})
                start_admission = start_prefix.get("admission", {})
                end_admission = end_prefix.get("admission", {})
                if (
                    start_prefix.get("stream_id") != end_prefix.get("stream_id")
                    or start_admission.get("rule_revision") != end_admission.get("rule_revision")
                    or start_admission.get("rule_sha256") != end_admission.get("rule_sha256")
                    or start_prefix.get("projector") != end_prefix.get("projector")
                ):
                    report.error(
                        "WORLDSPAN_RULES",
                        f"{location}.world_span",
                        "must preserve raw stream, admission rules, and projector identity",
                    )
                start_sequence = start.get("evidence_prefix", {}).get("through_sequence")
                end_sequence = end.get("evidence_prefix", {}).get("through_sequence")
                if type(start_sequence) is int and type(end_sequence) is int and end_sequence < start_sequence:
                    report.error("WORLDSPAN_ORDER", f"{location}.world_span", "end prefix must extend start prefix")
            if span.get("closed") is not True or span.get("continuous") is not True:
                report.error("WORLDSPAN_CLOSED", f"{location}.world_span", "must be closed and continuous")
            if guide_receipt is not None and span.get("start_world_ref_id") != guide_receipt.get("world_ref_id"):
                report.error("WORLDSPAN_GUIDE", f"{location}.world_span.start_world_ref_id", "must match GuideReceipt WorldRef")
        events = _list(receipt.get("events"), report, f"{location}.events") or []
        if not events or any(not isinstance(event, dict) for event in events):
            report.error("TRAVERSAL_EVENTS", f"{location}.events", "must contain object events")
        else:
            sequences = [event.get("sequence") for event in events]
            if any(type(sequence) is not int for sequence in sequences) or sequences != list(range(1, len(events) + 1)):
                report.error("TRAVERSAL_EVENT_SEQUENCE", f"{location}.events", "must be contiguous from 1")
        digest = _digest(receipt.get("trace_sha256"), report, f"{location}.trace_sha256")
        if digest is not None and digest != sha256_json(events):
            report.error("TRAVERSAL_TRACE_HASH", f"{location}.trace_sha256", "does not match events")
        _boolean(receipt.get("fresh"), report, f"{location}.fresh")
        _boolean(receipt.get("bypass"), report, f"{location}.bypass")
        if receipt.get("outcome") not in {"accepted", "rejected", "failed"}:
            report.error("TRAVERSAL_OUTCOME", f"{location}.outcome", "must be accepted, rejected, or failed")

        if manifest is not None:
            expected_plan = _fixture(demo_root, manifest, "expected_plan") if demo_root is not None else None
            expected_events: dict[str, list[dict[str, Any]]] = {
                "tr-r0-canary": [
                    {
                        "sequence": 1,
                        "kind": "guide-result-consumed",
                        "guide_receipt_id": "gr-r0-canary-w0",
                        "result_sha256": guide_receipts.get("gr-r0-canary-w0", {}).get("result_sha256"),
                    }
                ],
                "tr-r0-execution": [
                    {
                        "sequence": 1,
                        "kind": "guide-consumed",
                        "guide_receipt_id": "gr-r0-runtime-w0",
                        "instruction_sha256": guide_receipts.get("gr-r0-runtime-w0", {}).get("result", {}).get("instruction", {}).get("text_sha256"),
                    },
                    {
                        "sequence": 2,
                        "kind": "checkpoint",
                        "event_sha256": manifest["context_event_sha256"],
                        "from_world_ref_id": "world-L0",
                        "to_world_ref_id": "world-L1",
                    },
                ],
                "tr-r1-canary": [
                    {
                        "sequence": 1,
                        "kind": "guide-result-consumed",
                        "guide_receipt_id": "gr-r1-canary-w1",
                        "result_sha256": guide_receipts.get("gr-r1-canary-w1", {}).get("result_sha256"),
                    }
                ],
                "tr-r1-execution": [
                    {
                        "sequence": 1,
                        "kind": "guide-consumed",
                        "guide_receipt_id": "gr-r1-runtime-w1",
                        "instruction_sha256": guide_receipts.get("gr-r1-runtime-w1", {}).get("result", {}).get("instruction", {}).get("text_sha256"),
                    },
                    {
                        "sequence": 2,
                        "kind": "task-output-evaluated",
                        "output_sha256": sha256_json(expected_plan) if expected_plan is not None else None,
                    },
                ],
            }
            if receipt_id in expected_events and events != expected_events[receipt_id]:
                report.error(
                    "TRAVERSAL_EVENT_JOIN",
                    f"{location}.events",
                    "must exactly witness the frozen Guide result and declared path event",
                )

    certificates = _unique_map(bundle.get("path_certificates"), "certificate_id", report, "runtime-evidence.path_certificates")
    for certificate_id, certificate in certificates.items():
        location = f"runtime-evidence.path_certificates[{certificate_id}]"
        _exact_keys(
            certificate,
            {"schema_version", "certificate_id", "candidate_ref", "traversal_receipt_id", "guide_receipt_id", "scope", "issuer_id", "decision", "fresh", "no_bypass", "certificate_sha256"},
            report,
            location,
        )
        if certificate.get("schema_version") != PATH_CERTIFICATE_SCHEMA:
            report.error("CERTIFICATE_SCHEMA", f"{location}.schema_version", f"must be {PATH_CERTIFICATE_SCHEMA}")
        candidate = candidates.get(certificate.get("candidate_ref"))
        traversal = traversals.get(certificate.get("traversal_receipt_id"))
        guide_receipt = guide_receipts.get(certificate.get("guide_receipt_id"))
        if candidate is None:
            report.error("CERTIFICATE_CANDIDATE", f"{location}.candidate_ref", "must resolve to one Candidate")
        if traversal is None:
            report.error("CERTIFICATE_TRAVERSAL", f"{location}.traversal_receipt_id", "must resolve to one traversal")
        else:
            if traversal.get("candidate_ref") != certificate.get("candidate_ref"):
                report.error("CERTIFICATE_TRAVERSAL_CANDIDATE", f"{location}.traversal_receipt_id", "Candidate mismatch")
            if traversal.get("guide_receipt_id") != certificate.get("guide_receipt_id"):
                report.error("CERTIFICATE_GUIDE_JOIN", f"{location}.guide_receipt_id", "must match traversal")
            if traversal.get("outcome") != "accepted" or traversal.get("fresh") is not True or traversal.get("bypass") is not False:
                report.error("CERTIFICATE_TRAVERSAL_STATE", location, "requires accepted, fresh, zero-bypass traversal")
        if guide_receipt is None:
            report.error("CERTIFICATE_GUIDE", f"{location}.guide_receipt_id", "must resolve to one GuideReceipt")
        elif guide_receipt.get("mode") != "certification-canary":
            report.error("CERTIFICATE_GUIDE_MODE", f"{location}.guide_receipt_id", "must bind a certification canary")
        if candidate is not None and certificate.get("scope") != candidate.get("scope"):
            report.error("CERTIFICATE_SCOPE", f"{location}.scope", "must match Candidate scope")
        issuer = _string(certificate.get("issuer_id"), report, f"{location}.issuer_id")
        if traversal is not None and issuer == traversal.get("executor_id"):
            report.error("CERTIFICATE_INDEPENDENCE", f"{location}.issuer_id", "must differ from traversal executor")
        if certificate.get("decision") != "accepted" or certificate.get("fresh") is not True or certificate.get("no_bypass") is not True:
            report.error("CERTIFICATE_DECISION", location, "must record accepted, fresh, no-bypass")
        projection = {key: value for key, value in certificate.items() if key != "certificate_sha256"}
        digest = _digest(certificate.get("certificate_sha256"), report, f"{location}.certificate_sha256")
        if digest is not None and digest != sha256_json(projection):
            report.error("CERTIFICATE_HASH", f"{location}.certificate_sha256", "does not match certificate")

    warranties = _unique_map(bundle.get("evidential_warranties"), "warranty_id", report, "runtime-evidence.evidential_warranties")
    for warranty_id, warranty in warranties.items():
        location = f"runtime-evidence.evidential_warranties[{warranty_id}]"
        _exact_keys(
            warranty,
            {"schema_version", "warranty_id", "candidate_ref", "assignment_id", "path_certificate_id", "claim", "scope", "world_ref_id", "rule_ref", "assessor_id", "state", "assessed_at_sequence", "prior_assessment_ref", "invalidation_predicates", "assessment_sha256"},
            report,
            location,
        )
        if warranty.get("schema_version") != EVIDENTIAL_WARRANTY_SCHEMA:
            report.error("WARRANTY_SCHEMA", f"{location}.schema_version", f"must be {EVIDENTIAL_WARRANTY_SCHEMA}")
        candidate = candidates.get(warranty.get("candidate_ref"))
        certificate = certificates.get(warranty.get("path_certificate_id"))
        world = worlds.get(warranty.get("world_ref_id"))
        if candidate is None:
            report.error("WARRANTY_CANDIDATE", f"{location}.candidate_ref", "must resolve to one Candidate")
        if certificate is None:
            report.error("WARRANTY_CERTIFICATE", f"{location}.path_certificate_id", "must resolve to one PathCertificate")
        elif certificate.get("candidate_ref") != warranty.get("candidate_ref"):
            report.error("WARRANTY_CERTIFICATE_CANDIDATE", f"{location}.path_certificate_id", "Candidate mismatch")
        if world is None:
            report.error("WARRANTY_WORLD", f"{location}.world_ref_id", "must resolve to one WorldRef")
        for key in ("claim", "scope", "rule_ref", "assessor_id"):
            _string(warranty.get(key), report, f"{location}.{key}")
        if candidate is not None:
            assignment = candidate.get("position", {}).get("role_assignment", {})
            assignment_fact = candidate_assignment_facts.get(warranty.get("candidate_ref"))
            if warranty.get("assignment_id") != assignment.get("assignment_id"):
                report.error(
                    "WARRANTY_ASSIGNMENT",
                    f"{location}.assignment_id",
                    "must bind the admitted Actor-Role Assignment Fact",
                )
            if assignment_fact is None or warranty.get("assignment_id") != assignment_fact.get("assignment_id"):
                report.error(
                    "WARRANTY_ASSIGNMENT_FACT_JOIN",
                    f"{location}.assignment_id",
                    "must resolve through Position to the admitted Actor-Role Assignment Fact",
                )
            if warranty.get("scope") != candidate.get("scope"):
                report.error("WARRANTY_SCOPE", f"{location}.scope", "must match Candidate scope")
            if warranty.get("assessor_id") == candidate.get("builder_id"):
                report.error("WARRANTY_INDEPENDENCE", f"{location}.assessor_id", "must differ from Candidate builder")
            expected_rule_ref = f"{candidate['rules'][0]['rule_id']}@{candidate['rules'][0]['version']}"
            if warranty.get("rule_ref") != expected_rule_ref:
                report.error(
                    "WARRANTY_RULE_JOIN",
                    f"{location}.rule_ref",
                    "must bind the Candidate direction Rule",
                )
        if warranty.get("state") not in {"live", "lapsed", "unknown", "not_assessed"}:
            report.error("WARRANTY_STATE", f"{location}.state", "invalid assessment state")
        if warranty.get("state") == "live" and candidate is not None and warranty.get("world_ref_id") != candidate.get("world_ref_id"):
            report.error("WARRANTY_LIVE_WORLD", f"{location}.world_ref_id", "live assessment must use Candidate WorldRef")
        assessed = _integer(warranty.get("assessed_at_sequence"), report, f"{location}.assessed_at_sequence")
        if assessed is not None and world is not None and assessed != world.get("evidence_prefix", {}).get("through_sequence"):
            report.error("WARRANTY_SEQUENCE", f"{location}.assessed_at_sequence", "must match WorldRef prefix")
        prior = warranty.get("prior_assessment_ref")
        if prior is not None and (not isinstance(prior, str) or not prior):
            report.error("WARRANTY_PRIOR", f"{location}.prior_assessment_ref", "must be null or a non-empty id")
        predicates = _list(warranty.get("invalidation_predicates"), report, f"{location}.invalidation_predicates") or []
        if not predicates or any(not isinstance(item, str) or not item for item in predicates):
            report.error("WARRANTY_INVALIDATION", f"{location}.invalidation_predicates", "must contain strings")
        projection = {key: value for key, value in warranty.items() if key != "assessment_sha256"}
        digest = _digest(warranty.get("assessment_sha256"), report, f"{location}.assessment_sha256")
        if digest is not None and digest != sha256_json(projection):
            report.error("WARRANTY_HASH", f"{location}.assessment_sha256", "does not match assessment")
    for warranty_id, warranty in warranties.items():
        prior = warranty.get("prior_assessment_ref")
        if prior is not None:
            previous = warranties.get(prior)
            if previous is None:
                report.error("WARRANTY_PRIOR", f"runtime-evidence.evidential_warranties[{warranty_id}].prior_assessment_ref", "must resolve")
            elif previous.get("candidate_ref") != warranty.get("candidate_ref"):
                report.error("WARRANTY_PRIOR_CANDIDATE", f"runtime-evidence.evidential_warranties[{warranty_id}].prior_assessment_ref", "Candidate mismatch")
            elif (
                previous.get("path_certificate_id") != warranty.get("path_certificate_id")
                or previous.get("scope") != warranty.get("scope")
                or previous.get("rule_ref") != warranty.get("rule_ref")
            ):
                report.error(
                    "WARRANTY_PRIOR_CONTINUITY",
                    f"runtime-evidence.evidential_warranties[{warranty_id}].prior_assessment_ref",
                    "must preserve certificate, scope, and Rule",
                )
            elif (
                prior == warranty_id
                or type(previous.get("assessed_at_sequence")) is not int
                or type(warranty.get("assessed_at_sequence")) is not int
                or previous["assessed_at_sequence"] >= warranty["assessed_at_sequence"]
            ):
                report.error(
                    "WARRANTY_PRIOR_ORDER",
                    f"runtime-evidence.evidential_warranties[{warranty_id}].prior_assessment_ref",
                    "must resolve to a strictly earlier assessment",
                )

    authority_warranties = _unique_map(
        bundle.get("authority_warranties"),
        "warranty_id",
        report,
        "runtime-evidence.authority_warranties",
    )
    for warranty_id, warranty in authority_warranties.items():
        location = f"runtime-evidence.authority_warranties[{warranty_id}]"
        _exact_keys(
            warranty,
            {
                "schema_version", "warranty_id", "candidate_ref", "assignment_id",
                "claim", "scope", "world_ref_id", "rule_ref", "issuer_id", "state",
                "assessed_at_sequence", "prior_assessment_ref",
                "invalidation_predicates", "assessment_sha256",
            },
            report,
            location,
        )
        if warranty.get("schema_version") != AUTHORITY_WARRANTY_SCHEMA:
            report.error("AUTHORITY_WARRANTY_SCHEMA", f"{location}.schema_version", f"must be {AUTHORITY_WARRANTY_SCHEMA}")
        candidate = candidates.get(warranty.get("candidate_ref"))
        world = worlds.get(warranty.get("world_ref_id"))
        assignment = candidate.get("position", {}).get("role_assignment", {}) if candidate else {}
        assignment_fact = candidate_assignment_facts.get(warranty.get("candidate_ref"))
        role_rule = candidate_role_rules.get(warranty.get("candidate_ref"))
        if candidate is None:
            report.error("AUTHORITY_WARRANTY_CANDIDATE", f"{location}.candidate_ref", "must resolve to one Candidate")
        if world is None:
            report.error("AUTHORITY_WARRANTY_WORLD", f"{location}.world_ref_id", "must resolve to one WorldRef")
        if candidate is not None and warranty.get("assignment_id") != assignment.get("assignment_id"):
            report.error("AUTHORITY_WARRANTY_ASSIGNMENT", f"{location}.assignment_id", "must bind the Candidate Actor-Role Assignment")
        if candidate is not None and (
            assignment_fact is None
            or warranty.get("assignment_id") != assignment_fact.get("assignment_id")
        ):
            report.error(
                "AUTHORITY_WARRANTY_ASSIGNMENT_FACT_JOIN",
                f"{location}.assignment_id",
                "must resolve through Position to the admitted Actor-Role Assignment Fact",
            )
        for key in ("assignment_id", "claim", "scope", "rule_ref", "issuer_id"):
            _string(warranty.get(key), report, f"{location}.{key}")
        if candidate is not None:
            if warranty.get("scope") != assignment.get("scope"):
                report.error("AUTHORITY_WARRANTY_SCOPE", f"{location}.scope", "must match assignment scope")
            if warranty.get("issuer_id") in {candidate.get("builder_id"), assignment.get("holder")}:
                report.error("AUTHORITY_WARRANTY_INDEPENDENCE", f"{location}.issuer_id", "must differ from builder and assignment holder")
            expected_rule_ref = (
                f"{role_rule['rule_id']}@{role_rule['version']}"
                if role_rule is not None
                else None
            )
            if warranty.get("rule_ref") != expected_rule_ref:
                report.error("AUTHORITY_WARRANTY_RULE_JOIN", f"{location}.rule_ref", "must bind the assignment-governing Rule")
            if assignment_fact is not None and warranty.get("issuer_id") != assignment_fact.get("authority_source_id"):
                report.error(
                    "AUTHORITY_WARRANTY_FACT_AUTHORITY",
                    f"{location}.issuer_id",
                    "must bind the authority source admitted by the Assignment Fact",
                )
        if warranty.get("state") not in {"live", "lapsed", "unknown", "not_assessed"}:
            report.error("AUTHORITY_WARRANTY_STATE", f"{location}.state", "invalid assessment state")
        assessed = _integer(warranty.get("assessed_at_sequence"), report, f"{location}.assessed_at_sequence")
        if assessed is not None and world is not None and assessed != world.get("evidence_prefix", {}).get("through_sequence"):
            report.error("AUTHORITY_WARRANTY_SEQUENCE", f"{location}.assessed_at_sequence", "must match WorldRef prefix")
        prior = warranty.get("prior_assessment_ref")
        if prior is not None and (not isinstance(prior, str) or not prior):
            report.error("AUTHORITY_WARRANTY_PRIOR", f"{location}.prior_assessment_ref", "must be null or a non-empty id")
        predicates = _list(warranty.get("invalidation_predicates"), report, f"{location}.invalidation_predicates") or []
        if not predicates or any(not isinstance(item, str) or not item for item in predicates):
            report.error("AUTHORITY_WARRANTY_INVALIDATION", f"{location}.invalidation_predicates", "must contain strings")
        projection = {key: value for key, value in warranty.items() if key != "assessment_sha256"}
        digest = _digest(warranty.get("assessment_sha256"), report, f"{location}.assessment_sha256")
        if digest is not None and digest != sha256_json(projection):
            report.error("AUTHORITY_WARRANTY_HASH", f"{location}.assessment_sha256", "does not match assessment")
    for warranty_id, warranty in authority_warranties.items():
        prior = warranty.get("prior_assessment_ref")
        if prior is None:
            continue
        previous = authority_warranties.get(prior)
        location = f"runtime-evidence.authority_warranties[{warranty_id}].prior_assessment_ref"
        if previous is None:
            report.error("AUTHORITY_WARRANTY_PRIOR", location, "must resolve")
        elif previous.get("candidate_ref") != warranty.get("candidate_ref") or previous.get("assignment_id") != warranty.get("assignment_id"):
            report.error("AUTHORITY_WARRANTY_PRIOR_ASSIGNMENT", location, "must preserve Candidate and assignment")
        elif (
            prior == warranty_id
            or type(previous.get("assessed_at_sequence")) is not int
            or type(warranty.get("assessed_at_sequence")) is not int
            or previous["assessed_at_sequence"] >= warranty["assessed_at_sequence"]
        ):
            report.error("AUTHORITY_WARRANTY_PRIOR_ORDER", location, "must resolve to a strictly earlier assessment")

    for receipt_id, receipt in guide_receipts.items():
        if receipt.get("mode") != "runtime" or not isinstance(receipt.get("inputs"), dict):
            continue
        location = f"runtime-evidence.guide_receipts[{receipt_id}]"
        evidential = warranties.get(receipt["inputs"].get("evidential_warranty_ref"))
        authority = authority_warranties.get(receipt["inputs"].get("authority_warranty_ref"))
        if evidential is None:
            report.error("GUIDE_EVIDENTIAL_WARRANTY", f"{location}.inputs.evidential_warranty_ref", "must resolve to an assessment")
        if authority is None:
            report.error("GUIDE_AUTHORITY_WARRANTY", f"{location}.inputs.authority_warranty_ref", "must resolve to an assessment")
        if evidential is None or authority is None:
            continue
        for kind, warranty, ref_key in (
            ("evidential", evidential, "evidential_warranty_ref"),
            ("authority", authority, "authority_warranty_ref"),
        ):
            if warranty.get("candidate_ref") != receipt.get("candidate_ref") or warranty.get("world_ref_id") != receipt.get("world_ref_id"):
                report.error("GUIDE_WARRANTY_JOIN", f"{location}.inputs.{ref_key}", f"{kind} warranty must match Candidate and WorldRef")
        result_kind = receipt.get("result", {}).get("kind") if isinstance(receipt.get("result"), dict) else None
        if result_kind == "entrance" and (evidential.get("state") != "live" or authority.get("state") != "live"):
            report.error("GUIDE_DUAL_LIVE_WARRANTY", f"{location}.inputs", "Entrance requires both warranties live")
        if result_kind == "typed-refusal":
            code = receipt.get("result", {}).get("code")
            expected_codes: set[str] = set()
            if evidential.get("state") == "lapsed":
                expected_codes.update({"stale", "stale_world_ref"})
            if authority.get("state") == "lapsed":
                expected_codes.add("unauthorized")
            if "unknown" in {evidential.get("state"), authority.get("state")}:
                expected_codes.add("unknown")
            if "not_assessed" in {evidential.get("state"), authority.get("state")}:
                expected_codes.add("not_assessed")
            if code not in expected_codes:
                report.error("GUIDE_TYPED_WARRANTY_REFUSAL", f"{location}.result.code", "must match the non-live warranty state")

    u_states = _unique_map(bundle.get("u_states"), "u_state_id", report, "runtime-evidence.u_states")
    for u_state_id, u_state in u_states.items():
        location = f"runtime-evidence.u_states[{u_state_id}]"
        _exact_keys(
            u_state,
            {"u_state_id", "trigger", "diagnostic_basis", "advisory", "opens_candidate_ref"},
            report,
            location,
        )
        for key in ("trigger", "diagnostic_basis"):
            _string(u_state.get(key), report, f"{location}.{key}")
        _boolean(u_state.get("advisory"), report, f"{location}.advisory")
        if u_state.get("opens_candidate_ref") not in candidates:
            report.error("U_STATE_CANDIDATE", f"{location}.opens_candidate_ref", "must resolve to one Candidate")
    expected_u_states = {
        "u0": {
            "u_state_id": "u0",
            "trigger": "no_live_warranty",
            "diagnostic_basis": "method-paper-draft-v2",
            "advisory": True,
            "opens_candidate_ref": "candidate:service-plan-corridor@r0",
        },
        "u1": {
            "u_state_id": "u1",
            "trigger": "stale_evidential_warranty",
            "diagnostic_basis": "ew-r0-lapsed-w1",
            "advisory": False,
            "opens_candidate_ref": "candidate:service-plan-corridor@r1",
        },
    }
    for u_state_id, expected_u_state in expected_u_states.items():
        if u_states.get(u_state_id) != expected_u_state:
            report.error(
                "U_STATE_SEQUENCE_JOIN",
                f"runtime-evidence.u_states[{u_state_id}]",
                "must match the frozen no-warranty then stale-warranty sequence",
            )

    reentries = _unique_map(bundle.get("reentries"), "reentry_id", report, "runtime-evidence.reentries")
    for reentry_id, reentry in reentries.items():
        location = f"runtime-evidence.reentries[{reentry_id}]"
        _exact_keys(
            reentry,
            {"reentry_id", "from_candidate_ref", "to_candidate_ref", "trigger_warranty_ref", "reason", "history_rewritten"},
            report,
            location,
        )
        source = candidates.get(reentry.get("from_candidate_ref"))
        target = candidates.get(reentry.get("to_candidate_ref"))
        warranty = warranties.get(reentry.get("trigger_warranty_ref"))
        if source is None or target is None or source is target:
            report.error("REENTRY_CANDIDATES", location, "must join two distinct Candidates")
        elif source.get("candidate_id") != target.get("candidate_id") or source.get("revision_id") == target.get("revision_id"):
            report.error("REENTRY_REVISION", location, "must create a new revision of the same Candidate")
        if warranty is None or warranty.get("candidate_ref") != reentry.get("from_candidate_ref") or warranty.get("state") != "lapsed":
            report.error("REENTRY_TRIGGER", f"{location}.trigger_warranty_ref", "must resolve to the source Candidate lapsed assessment")
        _string(reentry.get("reason"), report, f"{location}.reason")
        if reentry.get("history_rewritten") is not False:
            report.error("REENTRY_HISTORY", f"{location}.history_rewritten", "must be false")

    current_scopes = _list(bundle.get("fixture_current_scopes"), report, "runtime-evidence.fixture_current_scopes") or []
    for index, scope in enumerate(current_scopes):
        location = f"runtime-evidence.fixture_current_scopes[{index}]"
        record = _exact_keys(
            scope,
            {"candidate_ref", "scope", "world_ref_id", "evidential_warranty_ref", "authority_warranty_ref"},
            report,
            location,
        )
        if record is None:
            continue
        candidate = candidates.get(record.get("candidate_ref"))
        evidential = warranties.get(record.get("evidential_warranty_ref"))
        authority = authority_warranties.get(record.get("authority_warranty_ref"))
        if candidate is None or evidential is None or authority is None:
            report.error("CURRENT_SCOPE_JOIN", location, "must resolve Candidate and both Warranties")
        elif (
            evidential.get("state") != "live"
            or authority.get("state") != "live"
            or evidential.get("candidate_ref") != record.get("candidate_ref")
            or authority.get("candidate_ref") != record.get("candidate_ref")
            or evidential.get("world_ref_id") != record.get("world_ref_id")
            or authority.get("world_ref_id") != record.get("world_ref_id")
            or evidential.get("scope") != record.get("scope")
            or candidate.get("scope") != record.get("scope")
        ):
            report.error("CURRENT_SCOPE_WARRANTY", location, "must be covered by matching dual-live assessments")

    expected_ids = {
        "worlds": {"world-L0", "world-L1"},
        "guides": {"gr-r0-canary-w0", "gr-r0-runtime-w0", "gr-r0-runtime-w1-refusal", "gr-r1-canary-w1", "gr-r1-runtime-w1"},
        "traversals": {"tr-r0-canary", "tr-r0-execution", "tr-r1-canary", "tr-r1-execution"},
        "certificates": {"pc-r0", "pc-r1"},
        "warranties": {"ew-r0-live-w0", "ew-r0-lapsed-w1", "ew-r1-live-w1"},
        "authority_warranties": {"aw-r0-live-w0", "aw-r0-live-w1", "aw-r1-live-w1"},
        "u_states": {"u0", "u1"},
        "reentries": {"reentry-r0-r1"},
    }
    actual_ids = {
        "worlds": set(worlds),
        "guides": set(guide_receipts),
        "traversals": set(traversals),
        "certificates": set(certificates),
        "warranties": set(warranties),
        "authority_warranties": set(authority_warranties),
        "u_states": set(u_states),
        "reentries": set(reentries),
    }
    for kind, expected in expected_ids.items():
        if actual_ids[kind] != expected:
            report.error("DEMO_SEQUENCE", f"runtime-evidence.{kind}", f"must contain exactly {sorted(expected)}")
    stale_receipt = guide_receipts.get("gr-r0-runtime-w1-refusal", {})
    if stale_receipt.get("result", {}).get("code") != "stale_world_ref":
        report.error("DEMO_STALE_REFUSAL", "runtime-evidence.guide_receipts", "r0 must refuse at W1")
    r0_warranties = [warranty for warranty in warranties.values() if warranty.get("candidate_ref", "").endswith("@r0")]
    if {warranty.get("state") for warranty in r0_warranties} != {"live", "lapsed"}:
        report.error("DEMO_WARRANTY_HISTORY", "runtime-evidence.evidential_warranties", "r0 must retain live and lapsed assessments")
    if len(current_scopes) != 1 or not str(current_scopes[0].get("candidate_ref", "")).endswith("@r1"):
        report.error("DEMO_CURRENT_SCOPE", "runtime-evidence.fixture_current_scopes", "only r1 may be current in the fixture at W1")

    pair = _exact_keys(bundle.get("execution_pair"), {"kind", "common", "control", "treatment"}, report, "runtime-evidence.execution_pair")
    if pair is not None:
        if pair.get("kind") != "deterministic-parity-fixture":
            report.error("PAIR_KIND", "runtime-evidence.execution_pair.kind", "must be deterministic-parity-fixture")
        common = _exact_keys(
            pair.get("common"),
            {"task_sha256", "base_commit", "environment_sha256", "context_event_sha256", "evaluator_sha256", "output_sha256"},
            report,
            "runtime-evidence.execution_pair.common",
        )
        if common is not None:
            for key in ("task_sha256", "environment_sha256", "context_event_sha256", "evaluator_sha256", "output_sha256"):
                _digest(common.get(key), report, f"runtime-evidence.execution_pair.common.{key}")
            if not isinstance(common.get("base_commit"), str) or not GIT_SHA1_RE.fullmatch(common["base_commit"]):
                report.error("PAIR_BASE", "runtime-evidence.execution_pair.common.base_commit", "must be a full commit")
            if manifest is not None:
                expected_common = {
                    "task_sha256": manifest["task_sha256"],
                    "base_commit": manifest["subject"]["base_commit"],
                    "environment_sha256": manifest["subject"]["environment_sha256"],
                    "context_event_sha256": manifest["context_event_sha256"],
                    "evaluator_sha256": manifest["evaluator_sha256"],
                }
                for key, expected in expected_common.items():
                    if common.get(key) != expected:
                        report.error("PAIR_COMMON_JOIN", f"runtime-evidence.execution_pair.common.{key}", "does not match DEMO.json")
        arm_specs = {
            "control": {"condition", "stage_instruction_sha256", "checkpoint_count", "final_world_ref_id", "task_output", "task_score"},
            "treatment": {"condition", "stage_instruction_sha256", "checkpoint_count", "final_world_ref_id", "task_output", "task_score", "corridor_score"},
        }
        arms: dict[str, dict[str, Any]] = {}
        for arm_id, fields in arm_specs.items():
            arm = _exact_keys(pair.get(arm_id), fields, report, f"runtime-evidence.execution_pair.{arm_id}")
            if arm is None:
                continue
            arms[arm_id] = arm
            condition = _exact_keys(arm.get("condition"), {"system", "knowledge"}, report, f"runtime-evidence.execution_pair.{arm_id}.condition")
            if condition is not None:
                expected_system = "task-only" if arm_id == "control" else "corridor"
                if condition != {"system": expected_system, "knowledge": "task-only"}:
                    report.error("PAIR_CONDITION", f"runtime-evidence.execution_pair.{arm_id}.condition", "unexpected condition")
            instruction_digests = _list(arm.get("stage_instruction_sha256"), report, f"runtime-evidence.execution_pair.{arm_id}.stage_instruction_sha256") or []
            if len(instruction_digests) != 2:
                report.error("PAIR_INSTRUCTIONS", f"runtime-evidence.execution_pair.{arm_id}.stage_instruction_sha256", "must contain two stages")
            for index, value in enumerate(instruction_digests):
                _digest(value, report, f"runtime-evidence.execution_pair.{arm_id}.stage_instruction_sha256[{index}]")
            if type(arm.get("checkpoint_count")) is not int or arm.get("checkpoint_count") != 1:
                report.error("PAIR_CHECKPOINT", f"runtime-evidence.execution_pair.{arm_id}.checkpoint_count", "must be integer 1")
            if arm.get("final_world_ref_id") != "world-L1":
                report.error("PAIR_FINAL_WORLD", f"runtime-evidence.execution_pair.{arm_id}.final_world_ref_id", "must be world-L1")
            score = _exact_keys(arm.get("task_score"), {"task_pass", "checks"}, report, f"runtime-evidence.execution_pair.{arm_id}.task_score")
            if score is not None:
                if score.get("task_pass") is not True:
                    report.error("TASK_PASS", f"runtime-evidence.execution_pair.{arm_id}.task_score.task_pass", "must be true")
                checks = score.get("checks")
                if not isinstance(checks, dict) or set(checks) != {"task_output_exact", "checkpoint_exactly_once", "typed_failure_preserves_output"} or any(value is not True for value in checks.values()):
                    report.error("TASK_CHECKS", f"runtime-evidence.execution_pair.{arm_id}.task_score.checks", "all three public checks must pass")
        if set(arms) == {"control", "treatment"}:
            control = arms["control"]
            treatment = arms["treatment"]
            if control.get("stage_instruction_sha256") != treatment.get("stage_instruction_sha256"):
                report.error("PAIR_INSTRUCTION_PARITY", "runtime-evidence.execution_pair", "both arms must receive identical stage instruction bytes")
            if manifest is not None:
                expected_stage_digests = [
                    sha256_json(stage["instruction"])
                    for stage in manifest["task"]["stages"]
                ]
                if control.get("stage_instruction_sha256") != expected_stage_digests:
                    report.error(
                        "PAIR_INSTRUCTION_JOIN",
                        "runtime-evidence.execution_pair",
                        "both arms must bind the frozen task stage instructions",
                    )
            if control.get("task_output") != treatment.get("task_output"):
                report.error("PAIR_OUTPUT_PARITY", "runtime-evidence.execution_pair", "both arms must produce identical task output")
            if control.get("task_score") != treatment.get("task_score"):
                report.error("PAIR_SCORE_PARITY", "runtime-evidence.execution_pair", "both arms must receive identical task score")
            if common is not None and common.get("output_sha256") != sha256_json(control.get("task_output")):
                report.error("PAIR_OUTPUT_HASH", "runtime-evidence.execution_pair.common.output_sha256", "does not match task output")
            if demo_root is not None and manifest is not None:
                try:
                    expected_plan = _fixture(demo_root, manifest, "expected_plan")
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                    report.error("EXPECTED_PLAN", str(demo_root), str(exc))
                else:
                    if control.get("task_output") != expected_plan:
                        report.error("EXPECTED_PLAN", "runtime-evidence.execution_pair", "task output does not match frozen expected plan")
            corridor_score = _exact_keys(
                treatment.get("corridor_score"),
                {"corridor_e2e_pass", "checks"},
                report,
                "runtime-evidence.execution_pair.treatment.corridor_score",
            )
            if corridor_score is not None:
                checks = corridor_score.get("checks")
                required_corridor_checks = {
                    "u_to_c0",
                    "deterministic_entrance",
                    "same_generation_raw_prefix_extension",
                    "stale_refusal_before_reentry",
                    "immutable_warranty_history",
                    "u_to_c1",
                    "dual_live_assignment",
                    "no_bypass",
                    "authority_log_optional",
                }
                r0_live = warranties.get("ew-r0-live-w0", {})
                r0_lapsed = warranties.get("ew-r0-lapsed-w1", {})
                r1_live = warranties.get("ew-r1-live-w1", {})
                derived_corridor_checks = {
                    "u_to_c0": u_states.get("u0") == expected_u_states["u0"]
                    and r0_live.get("state") == "live",
                    "deterministic_entrance": guide_receipts.get("gr-r0-canary-w0", {}).get("result_sha256")
                    == guide_receipts.get("gr-r0-runtime-w0", {}).get("result_sha256"),
                    "same_generation_raw_prefix_extension": bool(
                        worlds.get("world-L0")
                        and worlds.get("world-L1")
                        and all(
                            worlds["world-L0"].get(key)
                            == worlds["world-L1"].get(key)
                            for key in (
                                "project_id",
                                "run_id",
                                "generation_id",
                                "repository_url",
                                "base_commit",
                                "environment_sha256",
                            )
                        )
                        and worlds["world-L0"].get("evidence_prefix", {}).get("stream_id")
                        == worlds["world-L1"].get("evidence_prefix", {}).get("stream_id")
                        and worlds["world-L0"].get("evidence_prefix", {}).get("admission", {}).get("rule_revision")
                        == worlds["world-L1"].get("evidence_prefix", {}).get("admission", {}).get("rule_revision")
                        and worlds["world-L0"].get("evidence_prefix", {}).get("admission", {}).get("rule_sha256")
                        == worlds["world-L1"].get("evidence_prefix", {}).get("admission", {}).get("rule_sha256")
                        and worlds["world-L0"].get("evidence_prefix", {}).get("projector")
                        == worlds["world-L1"].get("evidence_prefix", {}).get("projector")
                        and worlds["world-L0"].get("evidence_prefix", {}).get("through_sequence") == 0
                        and worlds["world-L1"].get("evidence_prefix", {}).get("through_sequence") == 1
                    ),
                    "stale_refusal_before_reentry": stale_receipt.get("result", {}).get("code")
                    == "stale_world_ref",
                    "immutable_warranty_history": r0_lapsed.get("prior_assessment_ref")
                    == "ew-r0-live-w0"
                    and r0_lapsed.get("state") == "lapsed",
                    "u_to_c1": u_states.get("u1") == expected_u_states["u1"]
                    and reentries.get("reentry-r0-r1", {}).get("trigger_warranty_ref")
                    == "ew-r0-lapsed-w1"
                    and r1_live.get("state") == "live",
                    "dual_live_assignment": all(
                        receipt.get("inputs", {}).get("evidential_warranty_ref") in warranties
                        and receipt.get("inputs", {}).get("authority_warranty_ref") in authority_warranties
                        and warranties[receipt["inputs"]["evidential_warranty_ref"]].get("state") == "live"
                        and authority_warranties[receipt["inputs"]["authority_warranty_ref"]].get("state") == "live"
                        for receipt in guide_receipts.values()
                        if receipt.get("mode") == "runtime" and receipt.get("result", {}).get("kind") == "entrance"
                    ),
                    "no_bypass": all(receipt.get("bypass") is False for receipt in traversals.values()),
                    "authority_log_optional": bundle.get("authority_log_status") == "not_assessed",
                }
                if (
                    corridor_score.get("corridor_e2e_pass") is not True
                    or not isinstance(checks, dict)
                    or set(checks) != required_corridor_checks
                    or any(value is not True for value in checks.values())
                    or checks != derived_corridor_checks
                ):
                    report.error("CORRIDOR_E2E_PASS", "runtime-evidence.execution_pair.treatment.corridor_score", "all Corridor plumbing checks must pass")

    limits = _list(bundle.get("known_limits"), report, "runtime-evidence.known_limits") or []
    if not limits or any(not isinstance(item, str) or not item for item in limits):
        report.error("KNOWN_LIMITS", "runtime-evidence.known_limits", "must contain non-empty strings")
    report.facts.update(
        {
            "schema_version": bundle.get("schema_version"),
            "demo_id": bundle.get("demo_id"),
            "world_ref_count": len(worlds),
            "candidate_projection_count": len(candidates),
            "guide_receipt_count": len(guide_receipts),
            "traversal_receipt_count": len(traversals),
            "path_certificate_count": len(certificates),
            "evidential_warranty_count": len(warranties),
            "authority_warranty_count": len(authority_warranties),
            "task_pass": bool(pair and isinstance(pair.get("control"), dict) and pair["control"].get("task_score", {}).get("task_pass") is True),
            "corridor_e2e_pass": bool(pair and isinstance(pair.get("treatment"), dict) and pair["treatment"].get("corridor_score", {}).get("corridor_e2e_pass") is True),
            "benchmark_result": bundle.get("benchmark_result"),
            "causal_claim_allowed": bundle.get("causal_claim_allowed"),
            "authority_log_status": bundle.get("authority_log_status"),
        }
    )
    return report


def validate_runtime_evidence(
    bundle: Any,
    *,
    manifest: dict[str, Any] | None = None,
    demo_root: Path | None = None,
) -> ValidationReport:
    """Fail closed for malformed untrusted bundle shapes.

    Field-level validators intentionally continue after errors to report several
    problems at once. Container substitutions can therefore reach later joins; this
    boundary converts those expected shape failures into a structural INVALID result
    instead of exposing an internal exception through the CLI.
    """

    try:
        return _validate_runtime_evidence(
            bundle,
            manifest=manifest,
            demo_root=demo_root,
        )
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, RecursionError) as exc:
        report = ValidationReport()
        report.error(
            "MALFORMED_RUNTIME_EVIDENCE",
            "runtime-evidence",
            f"malformed nested value: {type(exc).__name__}",
        )
        return report


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="build the deterministic service-plan evidence bundle")
    build_parser.add_argument("demo_root", type=Path)
    build_parser.add_argument("--output", type=Path)
    validate_parser = subparsers.add_parser("validate", help="validate one runtime-evidence bundle")
    validate_parser.add_argument("evidence", type=Path)
    validate_parser.add_argument("--demo-root", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        manifest_report, manifest = validate_demo_manifest(args.demo_root)
        if not manifest_report.ok or manifest is None:
            print(json.dumps(manifest_report.as_dict(), sort_keys=True))
            return 1
        bundle = build_service_plan_bundle(args.demo_root)
        report = validate_runtime_evidence(bundle, manifest=manifest, demo_root=args.demo_root)
        if not report.ok:
            print(json.dumps(report.as_dict(), sort_keys=True))
            return 1
        payload = canonical_json_bytes(bundle) + b"\n"
        if args.output is not None:
            args.output.write_bytes(payload)
        else:
            print(payload.decode("utf-8"), end="")
        return 0
    try:
        evidence = load_json(args.evidence)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [{"code": "EVIDENCE_JSON", "location": str(args.evidence), "message": str(exc)}]}))
        return 1
    manifest = None
    if args.demo_root is not None:
        manifest_report, manifest = validate_demo_manifest(args.demo_root)
        if not manifest_report.ok:
            print(json.dumps(manifest_report.as_dict(), sort_keys=True))
            return 1
    report = validate_runtime_evidence(evidence, manifest=manifest, demo_root=args.demo_root)
    print(json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":")))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
