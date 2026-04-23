#!/usr/bin/env python3
"""Thin simulator orchestrator wrapper.

Maps profile/scenario input to fixture files and invokes list_verifier.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTROLLERS_CSV = ROOT / "docs" / "examples" / "site-controllers.template.csv"
DEFAULT_SCENARIOS_DIR = ROOT / "docs" / "examples" / "simulator-scenarios"
LIST_VERIFIER = ROOT / "tools" / "simulator" / "list_verifier.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run list-first verifier for a simulator profile/scenario."
    )
    parser.add_argument("--profile", required=True, choices=["ci", "lab", "multisubnet"])
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional path where verifier output should be written.",
    )
    parser.add_argument("--controllers-csv", type=Path, default=DEFAULT_CONTROLLERS_CSV)
    parser.add_argument("--scenarios-dir", type=Path, default=DEFAULT_SCENARIOS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scenario_file = f"{args.scenario}.example.json"
    scenario_path = args.scenarios_dir / scenario_file
    if not scenario_path.exists():
        print(f"error: scenario file not found: {scenario_path}")
        return 2

    cmd = [
        sys.executable,
        str(LIST_VERIFIER),
        "--controllers-csv",
        str(args.controllers_csv),
        "--scenario-json",
        str(scenario_path),
        "--output",
        args.output,
    ]
    if args.output_file:
        cmd.extend(["--output-file", str(args.output_file)])
    if args.strict:
        cmd.append("--strict")
    verifier = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if verifier.stdout:
        print(verifier.stdout, end="")
    if verifier.stderr:
        print(verifier.stderr, end="", file=sys.stderr)
    if args.output == "text":
        print(f"scenario_file={scenario_file} profile={args.profile}")
    elif args.output_file is not None:
        # Enrich JSON artifact with orchestrator context.
        payload = json.loads(args.output_file.read_text(encoding="utf-8"))
        payload["scenario_file"] = scenario_file
        payload["profile"] = args.profile
        args.output_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return verifier.returncode


if __name__ == "__main__":
    raise SystemExit(main())
