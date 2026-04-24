#!/usr/bin/env python3
"""Thin simulator orchestrator wrapper.

Maps profile/scenario input to fixture files and runs list verification in-process.
"""

from __future__ import annotations

import argparse
import json
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


def run_orchestrator(
    profile: str,
    scenario: str,
    *,
    strict: bool,
    output: str,
    output_file: Path | None,
    controllers_csv: Path,
    scenarios_dir: Path,
) -> int:
    """Run scenario-backed list verification (in-process; no subprocess)."""
    import importlib.util

    scenario_file = f"{scenario}.example.json"
    scenario_path = scenarios_dir / scenario_file
    if not scenario_path.exists():
        print(f"error: scenario file not found: {scenario_path}")
        return 2

    spec = importlib.util.spec_from_file_location(
        "simulator_list_verifier", LIST_VERIFIER
    )
    if spec is None or spec.loader is None:
        print(f"error: unable to load list_verifier from {LIST_VERIFIER}")
        return 2
    lv_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = lv_mod
    spec.loader.exec_module(lv_mod)
    run_verifier = lv_mod.run_verifier
    code = run_verifier(
        controllers_csv,
        scenario_path,
        strict=strict,
        output=output,
        output_file=output_file,
    )
    if output == "text":
        print(f"scenario_file={scenario_file} profile={profile}")
    elif output_file is not None:
        payload = json.loads(output_file.read_text(encoding="utf-8"))
        payload["scenario_file"] = scenario_file
        payload["profile"] = profile
        output_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return code


def main() -> int:
    args = parse_args()
    return run_orchestrator(
        args.profile,
        args.scenario,
        strict=args.strict,
        output=args.output,
        output_file=args.output_file,
        controllers_csv=args.controllers_csv,
        scenarios_dir=args.scenarios_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
