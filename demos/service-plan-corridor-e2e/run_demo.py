#!/usr/bin/env python3
"""Run or check the deterministic service-plan Corridor engineering demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = DEMO_ROOT.parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "tools"))

from corridor_runtime import (  # noqa: E402
    build_service_plan_bundle,
    canonical_json_bytes,
    load_json,
    validate_demo_manifest,
    validate_runtime_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate the manifest/golden and require deterministic byte equality",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write the generated bundle to this caller-selected path",
    )
    args = parser.parse_args()

    manifest_report, manifest = validate_demo_manifest(DEMO_ROOT)
    if not manifest_report.ok or manifest is None:
        print(json.dumps(manifest_report.as_dict(), sort_keys=True), file=sys.stderr)
        return 1
    generated = build_service_plan_bundle(DEMO_ROOT)
    generated_report = validate_runtime_evidence(
        generated, manifest=manifest, demo_root=DEMO_ROOT
    )
    if not generated_report.ok:
        print(json.dumps(generated_report.as_dict(), sort_keys=True), file=sys.stderr)
        return 1

    if args.check:
        expected_path = DEMO_ROOT / manifest["expected_runtime_evidence"]
        try:
            expected = load_json(expected_path)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            print(f"invalid expected runtime evidence: {exc}", file=sys.stderr)
            return 1
        expected_report = validate_runtime_evidence(
            expected, manifest=manifest, demo_root=DEMO_ROOT
        )
        if not expected_report.ok:
            print(json.dumps(expected_report.as_dict(), sort_keys=True), file=sys.stderr)
            return 1
        if canonical_json_bytes(generated) != canonical_json_bytes(expected):
            print(
                "generated runtime evidence differs from expected/RUNTIME-EVIDENCE.json",
                file=sys.stderr,
            )
            return 1
        print(
            json.dumps(
                {
                    "ok": True,
                    "classification": generated["classification"],
                    "task_pass": generated_report.facts["task_pass"],
                    "corridor_e2e_pass": generated_report.facts[
                        "corridor_e2e_pass"
                    ],
                    "benchmark_result": False,
                    "causal_claim_allowed": False,
                    "authority_warranty_state": "not_assessed",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    payload = canonical_json_bytes(generated) + b"\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    elif not args.check:
        sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
