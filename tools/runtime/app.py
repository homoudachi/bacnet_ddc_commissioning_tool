#!/usr/bin/env python3
"""Runtime CLI skeleton for commissioning workflows."""

from __future__ import annotations

import argparse
import json
import importlib.util
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMPORT_COMPILER = ROOT / "tools" / "import" / "compile_job.py"
SIMULATOR_ORCH = ROOT / "tools" / "simulator" / "orchestrator.py"
BIP_ADAPTER = ROOT / "tools" / "bacnet" / "bip_adapter.py"


def _load_bip_adapter():
    spec = importlib.util.spec_from_file_location("runtime_bip_adapter", BIP_ADAPTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load B/IP adapter module: {BIP_ADAPTER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def _probe_bip(
    host: str,
    port: int,
    expected_device_instance: int,
    timeout_seconds: float,
    retries: int,
) -> dict:
    bip_adapter = _load_bip_adapter()
    return bip_adapter.probe_device(
        host=host,
        port=port,
        expected_device_instance=expected_device_instance,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )


def _flows_dir(run_dir: Path) -> Path:
    return run_dir / "state" / "flows"


def _flow_state_path(run_dir: Path, controller_label: str) -> Path:
    return _flows_dir(run_dir) / f"{controller_label}.json"


def _is_terminal_prereq_status(status: str) -> bool:
    return status in {"passed", "manual_passed", "skipped"}


def _lookup_step_by_id(steps: list[dict], step_id: str) -> dict | None:
    for item in steps:
        if item.get("step_id") == step_id:
            return item
    return None


def _validate_step_transition(
    steps: list[dict],
    step: dict,
    requested_status: str,
) -> dict[str, str] | None:
    """Return reason dict when transition is invalid, otherwise None."""
    if requested_status == "skipped" and step.get("skippable") is not True:
        return {
            "reason_code": "step_not_skippable",
            "message": f"step '{step.get('step_id')}' is not skippable",
        }

    if requested_status in {"passed", "manual_passed"}:
        step_id = step.get("step_id")
        requires_step_ids = step.get("requires_step_ids", [])
        if isinstance(requires_step_ids, list):
            for required_id in requires_step_ids:
                required = _lookup_step_by_id(steps, str(required_id))
                if required is None:
                    return {
                        "reason_code": "dependency_missing_from_flow",
                        "message": (
                            f"step '{step_id}' requires completed dependency "
                            f"'{required_id}' which is not present in flow"
                        ),
                    }
                required_status = str(required.get("status", "pending"))
                if not _is_terminal_prereq_status(required_status):
                    return {
                        "reason_code": "dependency_not_completed",
                        "message": (
                            f"step '{step_id}' requires completed dependency "
                            f"'{required_id}'"
                        ),
                    }
        current_index = next(
            (idx for idx, item in enumerate(steps) if item.get("step_id") == step_id),
            None,
        )
        if current_index is None:
            return {
                "reason_code": "step_not_found_in_sequence",
                "message": f"step '{step_id}' not found in flow sequence",
            }
        for prev in steps[:current_index]:
            prev_status = str(prev.get("status", "pending"))
            if not _is_terminal_prereq_status(prev_status):
                return {
                    "reason_code": "prior_step_incomplete",
                    "message": (
                        f"step '{step_id}' cannot be marked {requested_status} "
                        f"before '{prev.get('step_id')}' is completed"
                    ),
                }
    return None


def _normalize_rejection_reason(reason_code: str) -> str:
    mapping = {
        "step_not_skippable": "STEP_NOT_SKIPPABLE",
        "dependency_not_completed": "DEPENDENCY_UNSATISFIED",
        "dependency_missing_from_flow": "DEPENDENCY_UNSATISFIED",
        "prior_step_incomplete": "PREREQ_ORDER",
        "step_not_found_in_sequence": "PREREQ_ORDER",
    }
    return mapping.get(reason_code, "INVALID_TRANSITION")


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
        requires_step_ids = []
        if isinstance(step.get("requires_step_ids"), list):
            for required_id in step["requires_step_ids"]:
                text = str(required_id).strip()
                if text:
                    requires_step_ids.append(text)
        steps.append(
            {
                "step_id": step_id,
                "label": str(step.get("label", "")).strip(),
                "status": "pending",
                "skippable": step.get("skippable") is True,
                "requires_step_ids": requires_step_ids,
                "records": [],
                "history": [],
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

    steps = flow_state.get("steps", [])
    transition_error = _validate_step_transition(
        steps=steps,
        step=step,
        requested_status=args.status,
    )
    previous_status = str(step.get("status", "pending"))
    if transition_error is not None:
        normalized_reason = _normalize_rejection_reason(
            transition_error.get("reason_code", "")
        )
        rejection_message = str(
            transition_error.get("message", "invalid step transition")
        )
        history = step.setdefault("history", [])
        history.append(
            {
                "ts": _utc_timestamp(),
                "previous_status": previous_status,
                "attempted_status": args.status,
                "new_status": previous_status,
                "reason_code": normalized_reason,
                "rejection_reason_code": normalized_reason,
                "rejected": True,
                "message": rejection_message,
            }
        )
        flow_state_path.write_text(json.dumps(flow_state, indent=2), encoding="utf-8")
        _append_event(
            logs_path,
            "flow_step_rejected",
            {
                "controller_label": args.controller_label,
                "step_id": args.step_id,
                "previous_status": previous_status,
                "attempted_status": args.status,
                "reason_code": normalized_reason,
                "rejection_reason_code": normalized_reason,
                "rejection_message": rejection_message,
                "technician_name": args.technician_name,
                "flow_state_json": str(flow_state_path.resolve()),
            },
        )
        print(f"error: invalid step transition: {rejection_message}")
        return 2

    record = {
        "ts": _utc_timestamp(),
        "status": args.status,
        "technician_name": args.technician_name,
        "note": args.note,
    }
    records = step.setdefault("records", [])
    records.append(record)
    history = step.setdefault("history", [])
    history.append(
        {
            "ts": _utc_timestamp(),
            "previous_status": previous_status,
            "attempted_status": args.status,
            "new_status": args.status,
            "reason_code": "status_update",
            "rejected": False,
        }
    )
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
            "previous_status": previous_status,
            "new_status": args.status,
            "reason_code": "status_update",
            "technician_name": args.technician_name,
            "flow_state_json": str(flow_state_path.resolve()),
        },
    )
    print(
        f"step_recorded=true controller_label={args.controller_label} "
        f"step_id={args.step_id} status={args.status}"
    )
    return 0


def cmd_probe_bip(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    artifacts_path = run_dir / "artifacts" / "bip"

    runtime_job_path = run_dir / "state" / "runtime-job.json"
    runtime_job = json.loads(runtime_job_path.read_text(encoding="utf-8"))
    target = None
    for controller in runtime_job.get("controllers", []):
        if controller.get("controller_label") == args.controller_label:
            target = controller
            break
    if target is None:
        print(f"error: controller not found in runtime job: {args.controller_label}")
        return 2

    bacnet = target.get("bacnet", {})
    host = str(bacnet.get("host", "")).strip()
    port = int(bacnet.get("port"))
    expected_instance = int(bacnet.get("device_instance"))

    result = _probe_bip(
        host=host,
        port=port,
        expected_device_instance=expected_instance,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
    )
    result["controller_label"] = args.controller_label

    artifact_file = artifacts_path / f"{args.controller_label}.json"
    artifacts_path.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")

    _append_event(
        logs_path,
        "bip_probed",
        {
            "controller_label": args.controller_label,
            "host": host,
            "port": port,
            "expected_device_instance": expected_instance,
            "status": result.get("status"),
            "artifact_json": str(artifact_file.resolve()),
        },
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "reachable_verified" else 2


def cmd_verify_bip_list(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    runtime_job = json.loads((run_dir / "state" / "runtime-job.json").read_text(encoding="utf-8"))

    bip_artifacts_dir = run_dir / "artifacts" / "bip"
    bip_artifacts_dir.mkdir(parents=True, exist_ok=True)

    status_counts: dict[str, int] = {}
    rows: list[dict] = []
    total = 0
    unresolved = 0
    strict_pass = True

    allow_labels = {label.strip() for label in args.allow_known_unavailable}
    if args.known_unavailable_file:
        data = json.loads(args.known_unavailable_file.read_text(encoding="utf-8"))
        if bool(data.get("allow_known_unavailable", False)):
            for label in data.get("controller_labels", []):
                text = str(label).strip()
                if text:
                    allow_labels.add(text)

    for controller in runtime_job.get("controllers", []):
        total += 1
        controller_label = str(controller.get("controller_label", "")).strip()
        bacnet = controller.get("bacnet", {})
        host = str(bacnet.get("host", "")).strip()
        port = int(bacnet.get("port", 0))
        expected_instance = int(bacnet.get("device_instance", 0))

        probe = _probe_bip(
            host=host,
            port=port,
            expected_device_instance=expected_instance,
            timeout_seconds=args.timeout_seconds,
            retries=args.retries,
        )
        probe["controller_label"] = controller_label
        if controller_label in allow_labels and probe.get("status") == "unreachable_timeout":
            probe["status"] = "known_unavailable"
            probe["allow_known_unavailable"] = True

        status = str(probe.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status != "reachable_verified":
            unresolved += 1

        if args.strict:
            if status != "reachable_verified":
                strict_pass = False
        else:
            if status == "known_unavailable":
                if not bool(probe.get("allow_known_unavailable") is True):
                    strict_pass = False
            elif status != "reachable_verified":
                strict_pass = False

        artifact_file = bip_artifacts_dir / f"{controller_label}.json"
        artifact_file.write_text(json.dumps(probe, sort_keys=True), encoding="utf-8")
        rows.append(probe)

    summary = {
        "total": total,
        "found": total - unresolved,
        "unresolved": unresolved,
        "strict_mode": bool(args.strict),
        "strict_pass": bool(strict_pass),
        "status_counts": status_counts,
        "rows": rows,
    }

    summary_path = bip_artifacts_dir / "list-summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    _append_event(
        logs_path,
        "bip_list_verified",
        {
            "total": total,
            "unresolved": unresolved,
            "strict_mode": bool(args.strict),
            "strict_pass": bool(strict_pass),
            "summary_json": str(summary_path.resolve()),
        },
    )
    print(json.dumps(summary, sort_keys=True))
    return 0 if strict_pass else 2


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

    probe_bip = subparsers.add_parser(
        "probe-bip", help="Probe one BACnet/IP endpoint and classify identity."
    )
    probe_bip.add_argument("--run-dir", required=True, type=Path)
    probe_bip.add_argument("--controller-label", required=True)
    probe_bip.add_argument("--timeout-seconds", type=float, default=0.5)
    probe_bip.add_argument("--retries", type=int, default=1)
    probe_bip.set_defaults(handler=cmd_probe_bip)

    verify_bip_list = subparsers.add_parser(
        "verify-bip-list", help="Probe all controllers in runtime job via BACnet/IP."
    )
    verify_bip_list.add_argument("--run-dir", required=True, type=Path)
    verify_bip_list.add_argument(
        "--strict",
        action="store_true",
        help="Require every controller to be reachable_verified.",
    )
    verify_bip_list.add_argument("--timeout-seconds", type=float, default=0.5)
    verify_bip_list.add_argument("--retries", type=int, default=1)
    verify_bip_list.add_argument(
        "--allow-known-unavailable",
        action="append",
        default=[],
        help="Controller labels allowed to classify as known_unavailable in non-strict mode.",
    )
    verify_bip_list.add_argument(
        "--known-unavailable-file",
        type=Path,
        help="Optional JSON file with {controller_labels:[], allow_known_unavailable:true}.",
    )
    verify_bip_list.set_defaults(handler=cmd_verify_bip_list)

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
