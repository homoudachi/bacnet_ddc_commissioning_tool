#!/usr/bin/env python3
"""Runtime CLI skeleton for commissioning workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMPORT_COMPILER = ROOT / "tools" / "import" / "compile_job.py"
SIMULATOR_ORCH = ROOT / "tools" / "simulator" / "orchestrator.py"


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _append_event(log_path: Path, event: str, payload: dict | None = None) -> None:
    payload = payload or {}
    entry = {"ts": _utc_timestamp(), "event": event, **payload}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _parse_run_config(run_dir: Path) -> dict:
    config_path = run_dir / "config" / "runtime-config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def _flows_dir(run_dir: Path) -> Path:
    return run_dir / "state" / "flows"


def _flow_state_path(run_dir: Path, controller_label: str) -> Path:
    return _flows_dir(run_dir) / f"{controller_label}.json"


def cmd_init_run(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    artifacts_dir = run_dir / "artifacts"
    state_dir = run_dir / "state"
    logs_dir = run_dir / "logs"
    config_dir = run_dir / "config"
    log_path = logs_dir / "events.jsonl"
    config_path = config_dir / "runtime-config.json"

    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "job_id": args.job_id,
        "controllers_csv": str(args.controllers_csv.resolve()),
        "profiles_dir": str(args.profiles_dir.resolve()),
        "scenarios_dir": str(args.scenarios_dir.resolve()),
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    _append_event(log_path, "run_initialized", {"run_dir": str(run_dir.resolve())})
    print(f"run_initialized=true run_dir={run_dir}")
    return 0


def cmd_compile_import(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    config = _parse_run_config(run_dir)
    state_dir = run_dir / "state"
    logs_path = run_dir / "logs" / "events.jsonl"
    output_json = state_dir / "runtime-job.json"
    report_json = state_dir / "import-report.json"

    cmd = [
        sys.executable,
        str(IMPORT_COMPILER),
        "--controllers-csv",
        config["controllers_csv"],
        "--profiles-dir",
        config["profiles_dir"],
        "--output-json",
        str(output_json),
        "--report-json",
        str(report_json),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    _append_event(
        logs_path,
        "import_compiled",
        {"exit_code": result.returncode, "report_json": str(report_json.resolve())},
    )
    return result.returncode


def cmd_verify_simulator(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    config = _parse_run_config(run_dir)
    artifacts_dir = run_dir / "artifacts"
    logs_path = run_dir / "logs" / "events.jsonl"
    output_file = artifacts_dir / "simulator" / f"{args.profile}-{args.scenario}.json"

    cmd = [
        sys.executable,
        str(SIMULATOR_ORCH),
        "--controllers-csv",
        config["controllers_csv"],
        "--scenarios-dir",
        config["scenarios_dir"],
        "--profile",
        args.profile,
        "--scenario",
        args.scenario,
        "--strict",
        "--output",
        "json",
        "--output-file",
        str(output_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    _append_event(
        logs_path,
        "simulator_verified",
        {
            "exit_code": result.returncode,
            "profile": args.profile,
            "scenario": args.scenario,
            "artifact_json": str(output_file.resolve()),
        },
    )
    return result.returncode


def cmd_init_flow(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    runtime_job_path = run_dir / "state" / "runtime-job.json"
    flow_state_path = _flow_state_path(run_dir, args.controller_label)

    runtime_job = json.loads(runtime_job_path.read_text(encoding="utf-8"))
    controllers = runtime_job.get("controllers", [])
    target = None
    for controller in controllers:
        if controller.get("controller_label") == args.controller_label:
            target = controller
            break
    if target is None:
        print(f"error: controller not found in runtime job: {args.controller_label}")
        return 2

    step_defs = target.get("commissioning_flow", [])
    steps = []
    for step in step_defs:
        step_id = str(step.get("step_id", "")).strip()
        if not step_id:
            continue
        steps.append(
            {
                "step_id": step_id,
                "label": str(step.get("label", "")).strip(),
                "status": "pending",
                "records": [],
            }
        )

    flow_state = {
        "controller_label": args.controller_label,
        "profile_id": target.get("profile_id"),
        "initialized_at": _utc_timestamp(),
        "steps": steps,
    }
    flow_state_path.parent.mkdir(parents=True, exist_ok=True)
    flow_state_path.write_text(json.dumps(flow_state, indent=2), encoding="utf-8")
    _append_event(
        logs_path,
        "flow_initialized",
        {
            "controller_label": args.controller_label,
            "step_count": len(steps),
            "flow_state_json": str(flow_state_path.resolve()),
        },
    )
    print(
        f"flow_initialized=true controller_label={args.controller_label} "
        f"steps={len(steps)}"
    )
    return 0


def cmd_record_step(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    flow_state_path = _flow_state_path(run_dir, args.controller_label)
    flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))

    if flow_state.get("controller_label") != args.controller_label:
        print(
            f"error: flow state is for {flow_state.get('controller_label')}, "
            f"not {args.controller_label}"
        )
        return 2

    step = None
    for item in flow_state.get("steps", []):
        if item.get("step_id") == args.step_id:
            step = item
            break
    if step is None:
        print(f"error: step_id not found in flow state: {args.step_id}")
        return 2

    record = {
        "ts": _utc_timestamp(),
        "status": args.status,
        "technician_name": args.technician_name,
        "note": args.note,
    }
    records = step.setdefault("records", [])
    records.append(record)
    step["status"] = args.status
    step["technician_name"] = args.technician_name
    step["note"] = args.note

    flow_state_path.write_text(json.dumps(flow_state, indent=2), encoding="utf-8")
    _append_event(
        logs_path,
        "flow_step_recorded",
        {
            "controller_label": args.controller_label,
            "step_id": args.step_id,
            "status": args.status,
            "technician_name": args.technician_name,
            "flow_state_json": str(flow_state_path.resolve()),
        },
    )
    print(
        f"step_recorded=true controller_label={args.controller_label} "
        f"step_id={args.step_id} status={args.status}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Runtime skeleton CLI for commissioning app flows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_run = subparsers.add_parser("init-run", help="Initialize a run directory.")
    init_run.add_argument("--run-dir", required=True, type=Path)
    init_run.add_argument("--job-id", required=True)
    init_run.add_argument("--controllers-csv", required=True, type=Path)
    init_run.add_argument("--profiles-dir", required=True, type=Path)
    init_run.add_argument("--scenarios-dir", required=True, type=Path)
    init_run.set_defaults(handler=cmd_init_run)

    compile_import = subparsers.add_parser(
        "compile-import", help="Compile import model using run config."
    )
    compile_import.add_argument("--run-dir", required=True, type=Path)
    compile_import.set_defaults(handler=cmd_compile_import)

    verify_sim = subparsers.add_parser(
        "verify-simulator", help="Run simulator verification for one scenario."
    )
    verify_sim.add_argument("--run-dir", required=True, type=Path)
    verify_sim.add_argument("--profile", required=True, choices=["ci", "lab", "multisubnet"])
    verify_sim.add_argument("--scenario", required=True)
    verify_sim.add_argument(
        "--strict",
        action="store_true",
        help="Pass strict flag through to simulator verification.",
    )
    verify_sim.set_defaults(handler=cmd_verify_simulator)

    init_flow = subparsers.add_parser(
        "init-flow", help="Initialize commissioning flow state for one controller."
    )
    init_flow.add_argument("--run-dir", required=True, type=Path)
    init_flow.add_argument("--controller-label", required=True)
    init_flow.set_defaults(handler=cmd_init_flow)

    record_step = subparsers.add_parser(
        "record-step", help="Record technician signoff for a commissioning step."
    )
    record_step.add_argument("--run-dir", required=True, type=Path)
    record_step.add_argument("--controller-label", required=True)
    record_step.add_argument("--step-id", required=True)
    record_step.add_argument(
        "--status",
        required=True,
        choices=["pending", "passed", "failed", "skipped", "manual_passed"],
    )
    record_step.add_argument("--technician-name", required=True)
    record_step.add_argument("--note", default="")
    record_step.set_defaults(handler=cmd_record_step)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (OSError, json.JSONDecodeError, KeyError) as err:
        print(f"error: {err}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
