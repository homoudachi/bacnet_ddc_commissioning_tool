#!/usr/bin/env python3
"""List-first BACnet simulator verification CLI.

This tool validates every controller row in the imported CSV against a
scenario JSON and emits a strict pass/fail summary for CI gating.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {
    "reachable_verified",
    "unreachable_timeout",
    "identity_mismatch",
    "required_point_missing",
    "write_rejected",
    "known_unavailable",
}

REQUIRED_CSV_COLUMNS = {
    "controller_label",
    "profile_id",
    "bacnet_device_instance",
    "bacnet_ip",
    "bacnet_port",
}


@dataclass(frozen=True)
class ControllerRow:
    controller_label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify imported controllers using list-first scenario outcomes."
    )
    parser.add_argument("--controllers-csv", required=True, type=Path)
    parser.add_argument("--scenario-json", required=True, type=Path)
    parser.add_argument(
        "--output",
        "--output-format",
        dest="output",
        choices=["text", "json"],
        default="text",
        help="Summary output format.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail for any non-reachable required row.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional output artifact file path (typically with --output json).",
    )
    return parser.parse_args()


def load_controller_rows(csv_path: Path) -> list[ControllerRow]:
    rows: list[ControllerRow] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_CSV_COLUMNS - header)
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"Missing required CSV columns: {missing}")
        for index, item in enumerate(reader, start=2):
            label = (item.get("controller_label") or "").strip()
            if not label:
                raise ValueError(f"Missing controller_label at CSV line {index}")
            rows.append(ControllerRow(controller_label=label))
    return rows


def load_scenario_statuses(scenario_path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Scenario JSON top-level value must be an object")
    scenario_rows = data.get("rows")
    if not isinstance(scenario_rows, list):
        raise ValueError("Scenario JSON must contain a top-level 'rows' list")

    by_label: dict[str, dict[str, Any]] = {}
    for item in scenario_rows:
        if not isinstance(item, dict):
            raise ValueError("Scenario row must be an object")
        label = str(item.get("controller_label", "")).strip()
        status = str(item.get("status", "")).strip()
        if not label:
            raise ValueError("Scenario row missing controller_label")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported status '{status}' for {label}")
        by_label[label] = item
    return by_label


def evaluate(
    controllers: list[ControllerRow],
    scenario_by_label: dict[str, dict[str, Any]],
    strict: bool,
) -> tuple[Counter[str], bool, int]:
    status_counts: Counter[str] = Counter()
    unresolved = 0
    strict_pass = True

    for controller in controllers:
        scenario_row = scenario_by_label.get(controller.controller_label)
        if scenario_row is None:
            status = "unreachable_timeout"
        else:
            status = str(scenario_row["status"])

        status_counts[status] += 1

        if status != "reachable_verified":
            unresolved += 1

        if strict:
            if status != "reachable_verified":
                strict_pass = False
        else:
            if status == "known_unavailable":
                allowed = bool(
                    scenario_row
                    and scenario_row.get("allow_known_unavailable") is True
                )
                if not allowed:
                    strict_pass = False
            elif status != "reachable_verified":
                strict_pass = False

    return status_counts, strict_pass, unresolved


def build_summary_payload(
    total: int,
    unresolved: int,
    strict: bool,
    strict_pass: bool,
    status_counts: Counter[str],
) -> dict[str, Any]:
    found = total - unresolved
    return {
        "found": found,
        "total": total,
        "unresolved": unresolved,
        "strict_mode": strict,
        "strict_pass": strict_pass,
        "status_counts": dict(status_counts),
    }


def emit_summary(
    total: int,
    unresolved: int,
    strict: bool,
    strict_pass: bool,
    status_counts: Counter[str],
    output: str,
    output_file: Path | None,
) -> None:
    payload = build_summary_payload(
        total=total,
        unresolved=unresolved,
        strict=strict,
        strict_pass=strict_pass,
        status_counts=status_counts,
    )
    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    if output == "json":
        print(json.dumps(payload, sort_keys=True))
        return

    found = payload["found"]

    print(
        f"found={found} total={total} unresolved={unresolved} "
        f"strict_pass={'true' if strict_pass else 'false'} "
        f"strict_mode={'true' if strict else 'false'}"
    )
    for status in sorted(status_counts):
        print(f"{status}={status_counts[status]}")


def run_verifier(
    controllers_csv: Path,
    scenario_json: Path,
    *,
    strict: bool = False,
    output: str = "text",
    output_file: Path | None = None,
) -> int:
    """Run list-first verification; used by orchestrator and PyInstaller builds."""
    try:
        controllers = load_controller_rows(controllers_csv)
        scenario_by_label = load_scenario_statuses(scenario_json)
        status_counts, strict_pass, unresolved = evaluate(
            controllers=controllers,
            scenario_by_label=scenario_by_label,
            strict=strict,
        )
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print(f"error: {err}")
        return 2

    try:
        emit_summary(
            total=len(controllers),
            unresolved=unresolved,
            strict=strict,
            strict_pass=strict_pass,
            status_counts=status_counts,
            output=output,
            output_file=output_file,
        )
    except OSError as err:
        print(f"error: {err}")
        return 2
    return 0 if strict_pass else 2


def main() -> int:
    args = parse_args()
    return run_verifier(
        args.controllers_csv,
        args.scenario_json,
        strict=args.strict,
        output=args.output,
        output_file=args.output_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
