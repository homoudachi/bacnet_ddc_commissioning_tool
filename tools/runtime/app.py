#!/usr/bin/env python3
"""Runtime CLI skeleton for commissioning workflows."""

from __future__ import annotations

import argparse
import csv
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


def _sessions_dir(run_dir: Path) -> Path:
    return run_dir / "state" / "sessions"


def _session_state_path(run_dir: Path, controller_label: str) -> Path:
    return _sessions_dir(run_dir) / f"{controller_label}.json"


def _flow_backups_dir(run_dir: Path) -> Path:
    return run_dir / "state" / "flow_backups"


def _step_status_counts(steps: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in steps:
        status = str(item.get("status", "pending"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _sequencing_complete_statuses() -> frozenset[str]:
    return frozenset({"passed", "manual_passed", "skipped"})


def _is_sequencing_complete_status(status: str) -> bool:
    """Prior steps must reach this before later steps can record pass/fail/skip outcomes."""
    return status in _sequencing_complete_statuses()


def _next_open_step(steps: list[dict]) -> dict | None:
    """First step not in a sequencing-complete terminal state (for operator 'next' hint)."""
    complete = _sequencing_complete_statuses()
    for item in steps:
        status = str(item.get("status", "pending"))
        if status not in complete:
            return {
                "step_id": item.get("step_id"),
                "label": item.get("label"),
                "status": status,
            }
    return None


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
    if requested_status == "pending":
        return {
            "reason_code": "pending_not_recordable",
            "message": (
                "cannot record step with status 'pending'; "
                "use passed, failed, skipped, or manual_passed to record outcomes"
            ),
        }

    if requested_status == "skipped" and step.get("skippable") is not True:
        return {
            "reason_code": "step_not_skippable",
            "message": f"step '{step.get('step_id')}' is not skippable",
        }

    if requested_status in {"passed", "manual_passed", "failed"}:
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
            if not _is_sequencing_complete_status(prev_status):
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
        "pending_not_recordable": "INVALID_TRANSITION",
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


def cmd_validate_import(args: argparse.Namespace) -> int:
    """Compile import into an isolated directory without overwriting runtime-job.json."""
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    config = _parse_run_config(run_dir)
    out_dir = args.output_dir or (run_dir / "artifacts" / "import-validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    output_json = out_dir / "runtime-job.json"
    report_json = out_dir / "import-report.json"

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
        "import_validated",
        {
            "exit_code": result.returncode,
            "validation_dir": str(out_dir.resolve()),
            "report_json": str(report_json.resolve()),
        },
    )
    print(f"import_validated=true validation_dir={out_dir.resolve()}")
    return result.returncode


def cmd_print_job_graph(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    runtime_job_path = run_dir / "state" / "runtime-job.json"
    if not runtime_job_path.is_file():
        print(
            f"error: runtime job missing at {runtime_job_path}; run compile-import first"
        )
        return 2

    runtime_job = json.loads(runtime_job_path.read_text(encoding="utf-8"))
    config = _parse_run_config(run_dir)
    lines: list[str] = []
    lines.append(f"job_id={config.get('job_id')}")
    lines.append(
        f"controller_count={runtime_job.get('summary', {}).get('controller_count', len(runtime_job.get('controllers', [])))}"
    )
    for row in runtime_job.get("controllers", []):
        label = str(row.get("controller_label", "")).strip()
        flow = row.get("commissioning_flow", [])
        step_count = len(flow) if isinstance(flow, list) else 0
        objs = row.get("objects_by_id", {})
        obj_count = len(objs) if isinstance(objs, dict) else 0
        w_allow = row.get("commissioning_write_allowlist", [])
        r_allow = row.get("commissioning_read_allowlist", [])
        wn = len(w_allow) if isinstance(w_allow, list) else 0
        rn = len(r_allow) if isinstance(r_allow, list) else 0
        lines.append(
            f"  {label} profile_id={row.get('profile_id')} "
            f"steps={step_count} objects_by_id={obj_count} "
            f"write_allowlist={wn} read_allowlist={rn}"
        )

    text = "\n".join(lines) + "\n"
    print(text, end="")
    _append_event(
        logs_path,
        "job_graph_printed",
        {"line_count": len(lines)},
    )
    return 0


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

    if flow_state_path.is_file() and not bool(getattr(args, "force", False)):
        print(
            "error: commissioning flow state already exists for this controller; "
            "use init-flow --force with --reset-technician-name and --reset-reason to replace"
        )
        return 2

    if flow_state_path.is_file() and bool(getattr(args, "force", False)):
        tech = str(getattr(args, "reset_technician_name", "") or "").strip()
        reason = str(getattr(args, "reset_reason", "") or "").strip()
        if not tech or not reason:
            print(
                "error: --force requires non-empty --reset-technician-name and --reset-reason"
            )
            return 2
        backup_dir = _flow_backups_dir(run_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = _utc_timestamp().replace(":", "-")
        backup_path = backup_dir / f"{args.controller_label}-{stamp}.json"
        backup_path.write_bytes(flow_state_path.read_bytes())
        _append_event(
            logs_path,
            "flow_reinitialized",
            {
                "controller_label": args.controller_label,
                "previous_flow_backup_json": str(backup_path.resolve()),
                "reset_technician_name": tech,
                "reset_reason": reason,
            },
        )

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


def cmd_list_flows(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    flows_root = _flows_dir(run_dir)
    flows: list[dict] = []

    if flows_root.is_dir():
        for path in sorted(flows_root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            label = str(data.get("controller_label", "")).strip()
            if not label:
                label = path.stem
            steps = data.get("steps", [])
            if not isinstance(steps, list):
                steps = []
            flows.append(
                {
                    "controller_label": label,
                    "profile_id": data.get("profile_id"),
                    "flow_state_json": str(path.resolve()),
                    "step_count": len(steps),
                    "status_counts": _step_status_counts(steps),
                }
            )

    payload = {"flow_count": len(flows), "flows": flows}
    _append_event(
        logs_path,
        "flows_listed",
        {
            "flow_count": len(flows),
            "controller_labels": [row["controller_label"] for row in flows],
        },
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


def cmd_show_flow(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    flow_state_path = _flow_state_path(run_dir, args.controller_label)
    if not flow_state_path.is_file():
        print(
            f"error: flow state not found for controller_label={args.controller_label}"
        )
        return 2

    flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
    _append_event(
        logs_path,
        "flow_viewed",
        {
            "controller_label": args.controller_label,
            "flow_state_json": str(flow_state_path.resolve()),
        },
    )
    print(json.dumps(flow_state, sort_keys=True))
    return 0


def cmd_set_session_value(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    flow_state_path = _flow_state_path(run_dir, args.controller_label)
    if not flow_state_path.is_file():
        print(
            "error: commissioning flow not initialized; run init-flow first "
            f"(missing {flow_state_path})"
        )
        return 2

    key = str(args.key).strip()
    if not key:
        print("error: session key must be non-empty")
        return 2
    if len(key) > 128:
        print("error: session key exceeds maximum length (128)")
        return 2

    session_path = _session_state_path(run_dir, args.controller_label)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    if session_path.is_file():
        session_state = json.loads(session_path.read_text(encoding="utf-8"))
    else:
        session_state = {
            "controller_label": args.controller_label,
            "updated_at": _utc_timestamp(),
            "values": {},
        }

    if not isinstance(session_state.get("values"), dict):
        session_state["values"] = {}

    session_state["values"][key] = {
        "value": str(args.value),
        "technician_name": args.technician_name,
        "note": args.note,
        "ts": _utc_timestamp(),
    }
    session_state["updated_at"] = _utc_timestamp()
    session_path.write_text(json.dumps(session_state, indent=2), encoding="utf-8")

    _append_event(
        logs_path,
        "session_value_set",
        {
            "controller_label": args.controller_label,
            "session_key": key,
            "session_state_json": str(session_path.resolve()),
        },
    )
    print(
        f"session_value_set=true controller_label={args.controller_label} key={key}"
    )
    return 0


def cmd_show_session(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    session_path = _session_state_path(run_dir, args.controller_label)
    if not session_path.is_file():
        print(
            f"error: session state not found for controller_label={args.controller_label}"
        )
        return 2

    session_state = json.loads(session_path.read_text(encoding="utf-8"))
    _append_event(
        logs_path,
        "session_viewed",
        {
            "controller_label": args.controller_label,
            "session_state_json": str(session_path.resolve()),
        },
    )
    print(json.dumps(session_state, sort_keys=True))
    return 0


def cmd_export_run_summary(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
    output_json = args.output_json or (run_dir / "artifacts" / "run-summary.json")
    config = _parse_run_config(run_dir)
    runtime_job_path = run_dir / "state" / "runtime-job.json"
    if not runtime_job_path.is_file():
        print(
            f"error: runtime job missing at {runtime_job_path}; run compile-import first"
        )
        return 2

    runtime_job = json.loads(runtime_job_path.read_text(encoding="utf-8"))
    import_report_path = run_dir / "state" / "import-report.json"
    import_report = None
    if import_report_path.is_file():
        import_report = json.loads(import_report_path.read_text(encoding="utf-8"))

    bip_summary_path = run_dir / "artifacts" / "bip" / "list-summary.json"
    bip_list_summary = None
    if bip_summary_path.is_file():
        bip_list_summary = json.loads(bip_summary_path.read_text(encoding="utf-8"))

    controllers_out: list[dict] = []
    for row in runtime_job.get("controllers", []):
        label = str(row.get("controller_label", "")).strip()
        flow_path = _flow_state_path(run_dir, label)
        entry: dict = {
            "controller_label": label,
            "profile_id": row.get("profile_id"),
            "flow_initialized": flow_path.is_file(),
            "flow_state_json": str(flow_path.resolve()) if flow_path.is_file() else None,
            "step_count": None,
            "status_counts": None,
            "next_open_step": None,
        }
        if flow_path.is_file():
            try:
                flow_state = json.loads(flow_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                flow_state = {}
            steps = flow_state.get("steps", [])
            if not isinstance(steps, list):
                steps = []
            entry["step_count"] = len(steps)
            entry["status_counts"] = _step_status_counts(steps)
            entry["next_open_step"] = _next_open_step(steps)
        controllers_out.append(entry)

    summary = {
        "schema_version": "0.1-run-summary",
        "generated_at": _utc_timestamp(),
        "job_id": config.get("job_id"),
        "run_dir": str(run_dir.resolve()),
        "runtime_job_json": str(runtime_job_path.resolve()),
        "import_report_present": import_report is not None,
        "import_compile_ok": import_report.get("compile_ok") if import_report else None,
        "bip_list_summary_present": bip_list_summary is not None,
        "controllers": controllers_out,
    }
    if bool(getattr(args, "embed_import_report", False)) and import_report is not None:
        summary["import_report"] = import_report
    if bool(getattr(args, "embed_bip_list_summary", False)) and bip_list_summary is not None:
        summary["bip_list_summary"] = bip_list_summary

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = getattr(args, "output_csv", None)
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "controller_label",
            "profile_id",
            "flow_initialized",
            "step_count",
            "next_step_id",
            "next_step_status",
            "pending_count",
            "passed_count",
            "failed_count",
            "skipped_count",
            "manual_passed_count",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in controllers_out:
                counts = row.get("status_counts") or {}
                nxt = row.get("next_open_step") or {}
                writer.writerow(
                    {
                        "controller_label": row.get("controller_label", ""),
                        "profile_id": row.get("profile_id", ""),
                        "flow_initialized": str(bool(row.get("flow_initialized"))).lower(),
                        "step_count": row.get("step_count") if row.get("step_count") is not None else "",
                        "next_step_id": nxt.get("step_id", "") if isinstance(nxt, dict) else "",
                        "next_step_status": nxt.get("status", "") if isinstance(nxt, dict) else "",
                        "pending_count": counts.get("pending", 0),
                        "passed_count": counts.get("passed", 0),
                        "failed_count": counts.get("failed", 0),
                        "skipped_count": counts.get("skipped", 0),
                        "manual_passed_count": counts.get("manual_passed", 0),
                    }
                )

    _append_event(
        logs_path,
        "run_summary_exported",
        {
            "summary_json": str(output_json.resolve()),
            "csv_path": str(csv_path.resolve()) if csv_path else None,
        },
    )
    print(f"run_summary_exported=true summary_json={output_json.resolve()}")
    if csv_path:
        print(f"run_summary_csv=true csv_path={csv_path.resolve()}")
    return 0


def _load_bacpypes_client():
    spec = importlib.util.spec_from_file_location(
        "runtime_bacpypes_client", ROOT / "tools" / "bacnet" / "bacpypes_client.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load bacpypes_client module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cmd_dry_run_bacnet_write(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
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

    object_id = str(args.object_id).strip()
    profile_allow = target.get("commissioning_write_allowlist", [])
    if not isinstance(profile_allow, list) or not profile_allow:
        print(
            "error: profile has no commissioning_write_allowlist; "
            "add a non-empty array of logical object ids to the unit profile JSON"
        )
        return 2
    allowed = {str(x).strip() for x in profile_allow if str(x).strip()}
    if object_id not in allowed:
        print(
            f"error: object_id not in profile commissioning_write_allowlist: {object_id!r} "
            f"(allowed: {sorted(allowed)})"
        )
        return 2

    objects_by_id = target.get("objects_by_id", {})
    if not isinstance(objects_by_id, dict) or object_id not in objects_by_id:
        print(
            f"error: object_id not found in compiled runtime job for controller: {object_id}"
        )
        return 2
    meta = objects_by_id[object_id]
    if not isinstance(meta, dict) or not bool(meta.get("writable")):
        print(f"error: object {object_id!r} is not writable in profile")
        return 2
    bacnet = meta.get("bacnet", {})
    if not isinstance(bacnet, dict):
        print(f"error: invalid objects_by_id entry for {object_id!r}")
        return 2
    type_name = str(bacnet.get("object_type", "")).strip()
    try:
        object_instance = int(bacnet.get("instance"))
    except (TypeError, ValueError):
        print(f"error: invalid BACnet instance for {object_id!r}")
        return 2

    bip_mod = _load_bip_adapter()
    object_type_int = bip_mod.object_type_name_to_int(type_name)
    if object_type_int is None:
        print(f"error: unsupported BACnet object_type for writes: {type_name!r}")
        return 2

    addr = target.get("bacnet", {})
    host = str(addr.get("host", "")).strip()
    port = int(addr.get("port", 0))
    expected_instance = int(addr.get("device_instance", 0))

    dry_run = not bool(getattr(args, "execute", False))
    result = bip_mod.plan_write_property(
        host=host,
        port=port,
        expected_device_instance=expected_instance,
        object_type=object_type_int,
        object_instance=object_instance,
        property_id=int(bip_mod.BACNET_PROP_PRESENT_VALUE),
        value=int(args.value),
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        dry_run=True,
    )
    result["controller_label"] = args.controller_label
    result["profile_object_id"] = object_id
    result["technician_name"] = args.technician_name
    result["note"] = args.note

    if not dry_run and result.get("status") == "dry_run_allowed":
        try:
            client = _load_bacpypes_client()
        except (OSError, RuntimeError) as err:
            print(f"error: failed to load BACnet write client: {err}")
            return 2
        try:
            bind_port = int(getattr(args, "bacnet_bind_port", 0) or 0)
        except ValueError:
            bind_port = 0
        who_is_timeout = max(3.0, float(args.timeout_seconds) * max(1, int(args.retries)))
        try:
            exec_result = client.write_present_value(
                bind_port=bind_port,
                target_address=f"{host}:{port}",
                expected_device_instance=expected_instance,
                object_type=object_type_int,
                object_instance=object_instance,
                value=int(args.value),
                who_is_timeout=who_is_timeout,
                apdu_timeout=8.0,
            )
        except ModuleNotFoundError as err:
            print(
                "error: bacpypes3 is required for --execute "
                f"(pip install -r requirements.txt): {err}"
            )
            return 2
        except Exception as err:  # noqa: BLE001 — surface client failures to operator
            result["execute_error"] = str(err)
            result["status"] = "execute_failed"
        else:
            result["execute"] = exec_result
            result["status"] = str(exec_result.get("status", "execute_failed"))
            result["dry_run"] = False

    plans_dir = run_dir / "artifacts" / "bacnet_write_plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    artifact = plans_dir / f"{args.controller_label}-{object_id}.json"
    artifact.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    if result.get("status") == "write_ok":
        event = "bacnet_write_executed"
    elif result.get("status") in {"dry_run_allowed", "use_bacpypes_client"}:
        event = "bacnet_write_planned"
    else:
        event = "bacnet_write_blocked"
    _append_event(
        logs_path,
        event,
        {
            "controller_label": args.controller_label,
            "object_id": object_id,
            "status": result.get("status"),
            "artifact_json": str(artifact.resolve()),
        },
    )
    print(json.dumps(result, sort_keys=True))
    if result.get("status") in {"dry_run_allowed", "write_ok"}:
        return 0
    return 2


def cmd_bacnet_read(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    logs_path = run_dir / "logs" / "events.jsonl"
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

    object_id = str(args.object_id).strip()
    profile_allow = target.get("commissioning_read_allowlist", [])
    if not isinstance(profile_allow, list) or not profile_allow:
        print(
            "error: profile has no commissioning_read_allowlist; "
            "add a non-empty array of logical object ids to the unit profile JSON"
        )
        return 2
    allowed = {str(x).strip() for x in profile_allow if str(x).strip()}
    if object_id not in allowed:
        print(
            f"error: object_id not in profile commissioning_read_allowlist: {object_id!r} "
            f"(allowed: {sorted(allowed)})"
        )
        return 2

    objects_by_id = target.get("objects_by_id", {})
    if not isinstance(objects_by_id, dict) or object_id not in objects_by_id:
        print(
            f"error: object_id not found in compiled runtime job for controller: {object_id}"
        )
        return 2
    meta = objects_by_id[object_id]
    if not isinstance(meta, dict):
        print(f"error: invalid objects_by_id entry for {object_id!r}")
        return 2
    bacnet = meta.get("bacnet", {})
    if not isinstance(bacnet, dict):
        print(f"error: invalid objects_by_id entry for {object_id!r}")
        return 2
    type_name = str(bacnet.get("object_type", "")).strip()
    try:
        object_instance = int(bacnet.get("instance"))
    except (TypeError, ValueError):
        print(f"error: invalid BACnet instance for {object_id!r}")
        return 2

    bip_mod = _load_bip_adapter()
    object_type_int = bip_mod.object_type_name_to_int(type_name)
    if object_type_int is None:
        print(f"error: unsupported BACnet object_type for reads: {type_name!r}")
        return 2

    addr = target.get("bacnet", {})
    host = str(addr.get("host", "")).strip()
    port = int(addr.get("port", 0))
    expected_instance = int(addr.get("device_instance", 0))

    probe = bip_mod.probe_device(
        host=host,
        port=port,
        expected_device_instance=expected_instance,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
    )
    result: dict = {
        "controller_label": args.controller_label,
        "profile_object_id": object_id,
        "probe": probe,
    }
    if probe.get("status") != "reachable_verified":
        result["status"] = "blocked_probe_failed"
    else:
        try:
            client = _load_bacpypes_client()
        except (OSError, RuntimeError) as err:
            print(f"error: failed to load BACnet client: {err}")
            return 2
        try:
            bind_port = int(getattr(args, "bacnet_bind_port", 0) or 0)
        except ValueError:
            bind_port = 0
        who_is_timeout = max(3.0, float(args.timeout_seconds) * max(1, int(args.retries)))
        prop = str(args.property or "presentValue").strip() or "presentValue"
        try:
            read_result = client.read_present_value(
                bind_port=bind_port,
                target_address=f"{host}:{port}",
                expected_device_instance=expected_instance,
                object_type=object_type_int,
                object_instance=object_instance,
                property_name=prop,
                who_is_timeout=who_is_timeout,
                apdu_timeout=8.0,
            )
        except ModuleNotFoundError as err:
            print(
                "error: bacpypes3 is required for bacnet-read "
                f"(pip install -r requirements.txt): {err}"
            )
            return 2
        except Exception as err:  # noqa: BLE001
            result["status"] = "read_failed"
            result["read_error"] = str(err)
        else:
            result["read"] = read_result
            result["status"] = str(read_result.get("status", "read_failed"))

    reads_dir = run_dir / "artifacts" / "bacnet_reads"
    reads_dir.mkdir(parents=True, exist_ok=True)
    artifact = reads_dir / f"{args.controller_label}-{object_id}.json"
    artifact.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    event = (
        "bacnet_read_ok"
        if result.get("status") == "read_ok"
        else "bacnet_read_blocked"
    )
    _append_event(
        logs_path,
        event,
        {
            "controller_label": args.controller_label,
            "object_id": object_id,
            "status": result.get("status"),
            "artifact_json": str(artifact.resolve()),
        },
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "read_ok" else 2


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

    validate_import = subparsers.add_parser(
        "validate-import",
        help="Dry-run compile to artifacts/import-validation (does not overwrite state/runtime-job.json).",
    )
    validate_import.add_argument("--run-dir", required=True, type=Path)
    validate_import.add_argument(
        "--output-dir",
        type=Path,
        help="Destination directory (default: <run-dir>/artifacts/import-validation).",
    )
    validate_import.set_defaults(handler=cmd_validate_import)

    print_graph = subparsers.add_parser(
        "print-job-graph",
        help="Print human-readable summary of controllers and commissioning flow sizes.",
    )
    print_graph.add_argument("--run-dir", required=True, type=Path)
    print_graph.set_defaults(handler=cmd_print_job_graph)

    export_summary = subparsers.add_parser(
        "export-run-summary",
        help="Write aggregated run summary JSON (controllers, flow hints, import/BIP flags).",
    )
    export_summary.add_argument("--run-dir", required=True, type=Path)
    export_summary.add_argument(
        "--output-json",
        type=Path,
        help="Destination JSON (default: <run-dir>/artifacts/run-summary.json).",
    )
    export_summary.add_argument(
        "--embed-import-report",
        action="store_true",
        help="Include full import-report.json object under key import_report when present.",
    )
    export_summary.add_argument(
        "--embed-bip-list-summary",
        action="store_true",
        help="Include full list-summary.json object under key bip_list_summary when present.",
    )
    export_summary.add_argument(
        "--output-csv",
        type=Path,
        help="Also write controller rollup as CSV (same rows as summary controllers).",
    )
    export_summary.set_defaults(handler=cmd_export_run_summary)

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

    dry_write = subparsers.add_parser(
        "dry-run-bacnet-write",
        help="Validate allowlisted WriteProperty intent (default dry-run; no frame sent).",
    )
    dry_write.add_argument("--run-dir", required=True, type=Path)
    dry_write.add_argument("--controller-label", required=True)
    dry_write.add_argument(
        "--object-id",
        required=True,
        help="Profile object id (e.g. msv_test_mode).",
    )
    dry_write.add_argument(
        "--value",
        required=True,
        type=int,
        help="Integer present-value to write (e.g. MSV state number).",
    )
    dry_write.add_argument("--technician-name", required=True)
    dry_write.add_argument("--note", default="")
    dry_write.add_argument("--timeout-seconds", type=float, default=0.5)
    dry_write.add_argument("--retries", type=int, default=1)
    dry_write.add_argument(
        "--bacnet-bind-port",
        type=int,
        default=0,
        help="Local UDP bind port for BACpypes3 client (0 = OS-assigned).",
    )
    dry_write.add_argument(
        "--execute",
        action="store_true",
        help="Send WriteProperty via BACpypes3 (requires pip install -r requirements.txt).",
    )
    dry_write.set_defaults(handler=cmd_dry_run_bacnet_write)

    bacnet_read = subparsers.add_parser(
        "bacnet-read",
        help="ReadProperty via BACpypes3 for allowlisted profile object (requires bacpypes3).",
    )
    bacnet_read.add_argument("--run-dir", required=True, type=Path)
    bacnet_read.add_argument("--controller-label", required=True)
    bacnet_read.add_argument(
        "--object-id",
        required=True,
        help="Profile object id (must be in commissioning_read_allowlist).",
    )
    bacnet_read.add_argument(
        "--property",
        default="presentValue",
        help="BACnet property name (default: presentValue).",
    )
    bacnet_read.add_argument("--timeout-seconds", type=float, default=0.5)
    bacnet_read.add_argument("--retries", type=int, default=1)
    bacnet_read.add_argument(
        "--bacnet-bind-port",
        type=int,
        default=0,
        help="Local UDP bind port for BACpypes3 client (0 = OS-assigned).",
    )
    bacnet_read.set_defaults(handler=cmd_bacnet_read)

    init_flow = subparsers.add_parser(
        "init-flow", help="Initialize commissioning flow state for one controller."
    )
    init_flow.add_argument("--run-dir", required=True, type=Path)
    init_flow.add_argument("--controller-label", required=True)
    init_flow.add_argument(
        "--force",
        action="store_true",
        help="Replace existing flow state; requires reset audit fields and backs up prior file.",
    )
    init_flow.add_argument(
        "--reset-technician-name",
        default="",
        help="With --force, who authorized replacing existing flow state.",
    )
    init_flow.add_argument(
        "--reset-reason",
        default="",
        help="With --force, why the prior flow state is being discarded.",
    )
    init_flow.set_defaults(handler=cmd_init_flow)

    list_flows = subparsers.add_parser(
        "list-flows",
        help="List commissioning flow state files for this run (summary JSON).",
    )
    list_flows.add_argument("--run-dir", required=True, type=Path)
    list_flows.set_defaults(handler=cmd_list_flows)

    show_flow = subparsers.add_parser(
        "show-flow",
        help="Print full commissioning flow JSON for one controller.",
    )
    show_flow.add_argument("--run-dir", required=True, type=Path)
    show_flow.add_argument("--controller-label", required=True)
    show_flow.set_defaults(handler=cmd_show_flow)

    set_session = subparsers.add_parser(
        "set-session-value",
        help="Store operator-entered session value for a controller (e.g. manual RAT).",
    )
    set_session.add_argument("--run-dir", required=True, type=Path)
    set_session.add_argument("--controller-label", required=True)
    set_session.add_argument(
        "--key",
        required=True,
        help="Session field key (e.g. rat_degC).",
    )
    set_session.add_argument(
        "--value",
        required=True,
        help="Value to store (string; caller may pass numeric text).",
    )
    set_session.add_argument("--technician-name", required=True)
    set_session.add_argument("--note", default="")
    set_session.set_defaults(handler=cmd_set_session_value)

    show_session = subparsers.add_parser(
        "show-session",
        help="Print session values JSON for one controller.",
    )
    show_session.add_argument("--run-dir", required=True, type=Path)
    show_session.add_argument("--controller-label", required=True)
    show_session.set_defaults(handler=cmd_show_session)

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
