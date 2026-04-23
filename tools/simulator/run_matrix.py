#!/usr/bin/env python3
"""Run a scenario matrix and write JSON artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTROLLERS_CSV = ROOT / "docs" / "examples" / "site-controllers.template.csv"
DEFAULT_SCENARIOS_DIR = ROOT / "docs" / "examples" / "simulator-scenarios"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "simulator"
ORCHESTRATOR = ROOT / "tools" / "simulator" / "orchestrator.py"


@dataclass(frozen=True)
class MatrixCase:
    profile: str
    scenario: str
    strict: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run simulator scenario matrix and collect JSON artifacts."
    )
    parser.add_argument("--controllers-csv", type=Path, default=DEFAULT_CONTROLLERS_CSV)
    parser.add_argument("--scenarios-dir", type=Path, default=DEFAULT_SCENARIOS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--matrix",
        help="JSON matrix file with entries: [{profile, scenario, strict}]",
    )
    return parser.parse_args()


def load_matrix(matrix_file: Path | None) -> list[MatrixCase]:
    if matrix_file is None:
        return [
            MatrixCase(profile="ci", scenario="happy-path", strict=True),
            MatrixCase(profile="ci", scenario="identity-mismatch", strict=True),
            MatrixCase(profile="ci", scenario="required-point-missing", strict=True),
            MatrixCase(profile="ci", scenario="timeout-burst", strict=True),
        ]

    data = json.loads(matrix_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Matrix JSON must be a list")
    matrix: list[MatrixCase] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Each matrix entry must be an object")
        profile = str(entry.get("profile", "")).strip()
        scenario = str(entry.get("scenario", "")).strip()
        if not profile or not scenario:
            raise ValueError(f"Invalid matrix entry: {entry}")
        strict_value = entry.get("strict", True)
        if not isinstance(strict_value, bool):
            raise ValueError(
                f"Matrix 'strict' must be boolean for entry: {entry}"
            )
        matrix.append(
            MatrixCase(profile=profile, scenario=scenario, strict=strict_value)
        )
    return matrix


def run_case(
    controllers_csv: Path,
    scenarios_dir: Path,
    output_dir: Path,
    profile: str,
    scenario: str,
    strict: bool,
) -> int:
    output_file = output_dir / f"{profile}-{scenario}.json"
    cmd = [
        sys.executable,
        str(ORCHESTRATOR),
        "--controllers-csv",
        str(controllers_csv),
        "--scenarios-dir",
        str(scenarios_dir),
        "--profile",
        profile,
        "--scenario",
        scenario,
        "--output",
        "json",
        "--output-file",
        str(output_file),
    ]
    if strict:
        cmd.append("--strict")

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] profile={profile} scenario={scenario} output={output_file}")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        matrix = load_matrix(Path(args.matrix) if args.matrix else None)
    except (OSError, ValueError, json.JSONDecodeError) as err:
        print(f"error: {err}")
        return 2

    highest_exit = 0
    for entry in matrix:
        case_exit = run_case(
            controllers_csv=args.controllers_csv,
            scenarios_dir=args.scenarios_dir,
            output_dir=args.output_dir,
            profile=entry.profile,
            scenario=entry.scenario,
            strict=entry.strict,
        )
        highest_exit = max(highest_exit, case_exit)

    print(f"matrix_complete output_dir={args.output_dir}")
    return highest_exit


if __name__ == "__main__":
    raise SystemExit(main())
