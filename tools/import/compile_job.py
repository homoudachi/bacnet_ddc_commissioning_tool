#!/usr/bin/env python3
"""Compile controller spreadsheet + profile library into a runtime job model."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "controller_label",
    "profile_id",
    "bacnet_device_instance",
    "bacnet_ip",
    "bacnet_port",
]

# Optional columns copied into runtime rows today; anything else is ignored with a warning.
KNOWN_CONTROLLER_COLUMNS = frozenset(REQUIRED_COLUMNS) | frozenset(
    [
        "building_floor",
        "notes",
    ]
)

# Per-row BACnet addressing: ``bacnet_object_<logical_id>`` overrides ``instance`` for that
# profile ``objects[].id`` while keeping ``object_type`` and allowlists from the profile.
BACNET_OBJECT_INSTANCE_COL_PREFIX = "bacnet_object_"


def _is_bacnet_object_instance_column(name: str) -> bool:
    col = str(name).strip()
    return col.startswith(BACNET_OBJECT_INSTANCE_COL_PREFIX) and len(col) > len(
        BACNET_OBJECT_INSTANCE_COL_PREFIX
    )


def _parse_per_row_object_instance_overrides(
    row: dict[str, str],
    row_index: int,
    controller_label: str,
    objects_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Parse ``bacnet_object_<logical_id>`` columns into logical id → BACnet instance int."""
    errors: list[dict[str, Any]] = []
    overrides: dict[str, int] = {}
    for key, raw_val in row.items():
        if key is None:
            continue
        col = str(key).strip()
        if not _is_bacnet_object_instance_column(col):
            continue
        logical_id = col[len(BACNET_OBJECT_INSTANCE_COL_PREFIX) :].strip()
        if not logical_id:
            _error(
                errors,
                code="invalid_bacnet_object_override_column",
                message=f"column {col!r} must be bacnet_object_<logical_id> with non-empty id",
                controller_label=controller_label,
                row=row_index,
            )
            continue
        val = (raw_val or "").strip()
        if not val:
            continue
        if logical_id not in objects_by_id:
            _error(
                errors,
                code="unknown_bacnet_object_override_id",
                message=(
                    f"column {col!r}: object id {logical_id!r} is not defined "
                    f"in the profile objects list"
                ),
                controller_label=controller_label,
                row=row_index,
            )
            continue
        try:
            inst = int(val)
        except ValueError:
            _error(
                errors,
                code="invalid_bacnet_object_instance_override",
                message=f"column {col!r}: expected integer BACnet instance, got {val!r}",
                controller_label=controller_label,
                row=row_index,
            )
            continue
        if inst < 0:
            _error(
                errors,
                code="invalid_bacnet_object_instance_override",
                message=f"column {col!r}: BACnet instance must be >= 0",
                controller_label=controller_label,
                row=row_index,
            )
            continue
        overrides[logical_id] = inst
    return errors, overrides


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile site controller list into normalized runtime model."
    )
    parser.add_argument("--controllers-csv", required=True, type=Path)
    parser.add_argument("--profiles-dir", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--report-json", required=True, type=Path)
    return parser.parse_args()


def _error(
    errors: list[dict[str, Any]],
    code: str,
    message: str,
    controller_label: str | None = None,
    row: int | None = None,
) -> None:
    entry: dict[str, Any] = {"code": code, "message": message}
    if controller_label:
        entry["controller_label"] = controller_label
    if row is not None:
        entry["row"] = row
    errors.append(entry)


def _warning(warnings: list[dict[str, Any]], code: str, message: str) -> None:
    warnings.append({"code": code, "message": message})


def _bacnet_endpoint_key(host: str, port: int) -> str:
    return f"{host.strip().lower()}:{int(port)}"


def load_profiles(
    profiles_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    profiles_by_id: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            _error(
                errors,
                code="invalid_profile_file",
                message=f"{path.name}: {err}",
            )
            continue

        profile_id = str(data.get("profile_id", "")).strip()
        if not profile_id:
            _warning(
                warnings,
                code="profile_missing_id",
                message=f"{path.name}: missing profile_id",
            )
            continue
        if profile_id in profiles_by_id:
            _warning(
                warnings,
                code="duplicate_profile_id",
                message=f"{path.name}: duplicate profile_id {profile_id}; last one wins",
            )
        profiles_by_id[profile_id] = data
    return profiles_by_id, errors, warnings


def parse_int(value: str, field: str) -> int:
    text = value.strip()
    if not text:
        raise ValueError(f"missing required {field}")
    return int(text)


def compile_model(
    controllers_csv: Path,
    profiles_by_id: dict[str, dict[str, Any]],
    initial_errors: list[dict[str, Any]],
    initial_warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    errors = list(initial_errors)
    warnings = list(initial_warnings)
    controllers: list[dict[str, Any]] = []
    labels_seen: set[str] = set()
    instances_seen: set[int] = set()
    # host:port -> list of (controller_label, device_instance, row)
    endpoint_rows: dict[str, list[tuple[str, int, int]]] = {}

    try:
        handle = controllers_csv.open("r", encoding="utf-8", newline="")
    except OSError as err:
        _error(errors, code="controllers_csv_read_failed", message=str(err))
        return build_outputs(
            controllers=controllers,
            profiles_by_id=profiles_by_id,
            errors=errors,
            warnings=warnings,
        )

    with handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        missing = sorted(set(REQUIRED_COLUMNS) - header)
        if missing:
            _error(
                errors,
                code="missing_required_columns",
                message=f"missing required csv columns: {', '.join(missing)}",
            )
            return build_outputs(
                controllers=controllers,
                profiles_by_id=profiles_by_id,
                errors=errors,
                warnings=warnings,
            )

        for col in sorted(header - KNOWN_CONTROLLER_COLUMNS):
            name = str(col).strip()
            if not name:
                continue
            if _is_bacnet_object_instance_column(name):
                continue
            _warning(
                warnings,
                code="unknown_controller_csv_column",
                message=(
                    f"unknown controller CSV column {name!r}: values are ignored in v1; "
                    f"see docs/schema/site-controllers-v1.csv.md"
                ),
            )

        for row_index, row in enumerate(reader, start=2):
            label = (row.get("controller_label") or "").strip()
            if not label:
                _error(
                    errors,
                    code="missing_controller_label",
                    message="missing controller_label",
                    row=row_index,
                )
                continue
            if label in labels_seen:
                _error(
                    errors,
                    code="duplicate_controller_label",
                    message=f"duplicate controller_label: {label}",
                    controller_label=label,
                    row=row_index,
                )
                continue
            labels_seen.add(label)

            profile_id = (row.get("profile_id") or "").strip()
            if not profile_id:
                _error(
                    errors,
                    code="missing_profile_id",
                    message="missing profile_id",
                    controller_label=label,
                    row=row_index,
                )
                continue
            profile = profiles_by_id.get(profile_id)
            if profile is None:
                _error(
                    errors,
                    code="missing_profile",
                    message=f"profile_id not found in profiles dir: {profile_id}",
                    controller_label=label,
                    row=row_index,
                )
                continue

            try:
                device_instance = parse_int(
                    value=row.get("bacnet_device_instance") or "",
                    field="bacnet_device_instance",
                )
            except ValueError:
                _error(
                    errors,
                    code="invalid_bacnet_device_instance",
                    message="invalid bacnet_device_instance",
                    controller_label=label,
                    row=row_index,
                )
                continue
            if device_instance in instances_seen:
                _error(
                    errors,
                    code="duplicate_bacnet_device_instance",
                    message=f"duplicate bacnet_device_instance: {device_instance}",
                    controller_label=label,
                    row=row_index,
                )
                continue
            instances_seen.add(device_instance)

            host = (row.get("bacnet_ip") or "").strip()
            if not host:
                _error(
                    errors,
                    code="missing_bacnet_ip",
                    message="missing bacnet_ip",
                    controller_label=label,
                    row=row_index,
                )
                continue

            port_text = (row.get("bacnet_port") or "").strip()
            try:
                port = int(port_text)
                if port < 1 or port > 65535:
                    raise ValueError("out of range")
            except ValueError:
                _error(
                    errors,
                    code="invalid_bacnet_port",
                    message=f"invalid bacnet_port: {port_text}",
                    controller_label=label,
                    row=row_index,
                )
                continue

            ep_key = _bacnet_endpoint_key(host, port)
            endpoint_rows.setdefault(ep_key, []).append((label, device_instance, row_index))

            allow_ids: list[str] = []
            raw_allow = profile.get("commissioning_write_allowlist")
            if isinstance(raw_allow, list):
                for item in raw_allow:
                    text = str(item).strip()
                    if text:
                        allow_ids.append(text)

            read_allow_ids: list[str] = []
            raw_read = profile.get("commissioning_read_allowlist")
            if isinstance(raw_read, list):
                for item in raw_read:
                    text = str(item).strip()
                    if text:
                        read_allow_ids.append(text)

            unit_specs = profile.get("unit_specs")
            airflow_verification = profile.get("airflow_verification")
            commissioning_meta: dict[str, Any] = {}
            if isinstance(unit_specs, dict):
                commissioning_meta["unit_specs"] = unit_specs
            if isinstance(airflow_verification, dict):
                commissioning_meta["airflow_verification"] = airflow_verification

            objects_by_id = _extract_objects_by_id(profile)
            ov_errors, instance_overrides = _parse_per_row_object_instance_overrides(
                row=row,
                row_index=row_index,
                controller_label=label,
                objects_by_id=objects_by_id,
            )
            if ov_errors:
                errors.extend(ov_errors)
                continue
            if instance_overrides:
                commissioning_meta["controller_csv_object_instance_overrides"] = {
                    k: instance_overrides[k] for k in sorted(instance_overrides)
                }
                for oid, inst in instance_overrides.items():
                    entry = objects_by_id.get(oid)
                    if entry is None:
                        continue
                    bac = entry.get("bacnet")
                    if not isinstance(bac, dict):
                        continue
                    entry["bacnet"] = {**bac, "instance": inst}

            controllers.append(
                {
                    "controller_label": label,
                    "profile_id": profile_id,
                    "profile": {
                        "profile_id": profile_id,
                        "display_name": str(profile.get("display_name", "")).strip(),
                        "schema_version": str(profile.get("schema_version", "")).strip(),
                    },
                    "commissioning_write_allowlist": allow_ids,
                    "commissioning_read_allowlist": read_allow_ids,
                    "commissioning_meta": commissioning_meta,
                    "objects_by_id": objects_by_id,
                    "point_checkout": _extract_point_checkout(profile),
                    "commissioning_flow": _extract_commissioning_steps(profile),
                    "bacnet": {
                        "device_instance": device_instance,
                        "host": host,
                        "port": port,
                    },
                    "building_floor": (row.get("building_floor") or "").strip(),
                    "notes": (row.get("notes") or "").strip(),
                }
            )

    for ep_key, rows in endpoint_rows.items():
        if len(rows) < 2:
            continue
        instances = {r[1] for r in rows}
        labels = sorted({r[0] for r in rows})
        if len(instances) > 1:
            _warning(
                warnings,
                code="duplicate_bacnet_ip_port_different_device",
                message=(
                    f"multiple controllers share BACnet/IP endpoint {ep_key} "
                    f"with different device_instance values: {', '.join(labels)}"
                ),
            )
        elif len(rows) > 1:
            _warning(
                warnings,
                code="duplicate_bacnet_ip_port_same_device",
                message=(
                    f"multiple controller rows target the same BACnet/IP endpoint {ep_key} "
                    f"and device_instance {next(iter(instances))}: {', '.join(labels)}"
                ),
            )

    return build_outputs(
        controllers=controllers,
        profiles_by_id=profiles_by_id,
        errors=errors,
        warnings=warnings,
    )


def build_outputs(
    controllers: list[dict[str, Any]],
    profiles_by_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    compile_ok = len(errors) == 0
    runtime_model = {
        "schema_version": "0.1-runtime",
        "summary": {
            "compile_ok": compile_ok,
            "controller_count": len(controllers),
            "profile_count": len(profiles_by_id),
        },
        "controllers": controllers,
        "profile_library": sorted(profiles_by_id),
    }
    report = {
        "compile_ok": compile_ok,
        "controller_count": len(controllers),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    return runtime_model, report, (0 if compile_ok else 2)


def _extract_objects_by_id(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map profile logical object id -> minimal BACnet addressing for runtime tooling."""
    out: dict[str, dict[str, Any]] = {}
    raw = profile.get("objects")
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("id", "")).strip()
        if not oid:
            continue
        bacnet = item.get("bacnet") if isinstance(item.get("bacnet"), dict) else {}
        object_type = str(bacnet.get("object_type", "")).strip()
        instance = bacnet.get("instance")
        if not object_type or instance is None:
            continue
        try:
            inst_int = int(instance)
        except (TypeError, ValueError):
            continue
        out[oid] = {
            "bacnet": {"object_type": object_type, "instance": inst_int},
            "writable": bool(item.get("writable")),
        }
    return out


def _extract_point_checkout(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Optional ordered list of read checks for point checkout (object_id + property)."""
    out: list[dict[str, Any]] = []
    raw = profile.get("point_checkout")
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        oid = str(item.get("object_id", "")).strip()
        if not oid:
            continue
        prop = str(item.get("property", "presentValue")).strip() or "presentValue"
        out.append({"object_id": oid, "property": prop})
    return out


def _extract_commissioning_steps(profile: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    raw_flow = profile.get("commissioning_flow")
    if not isinstance(raw_flow, list):
        return steps

    for item in raw_flow:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("step_id", "")).strip()
        label = str(item.get("label", "")).strip()
        if not step_id:
            continue
        raw_requires = item.get("requires_step_ids", [])
        requires_step_ids: list[str] = []
        if isinstance(raw_requires, list):
            for dep in raw_requires:
                dep_id = str(dep).strip()
                if dep_id:
                    requires_step_ids.append(dep_id)
        step_type = str(item.get("step_type", "")).strip() or "standard"
        run_pc = item.get("run_point_checkout_on_pass")
        run_point_checkout_on_pass = bool(run_pc) if run_pc is not None else False
        report_ref = str(item.get("report_ref", "")).strip()
        step_row: dict[str, Any] = {
            "step_id": step_id,
            "label": label,
            "step_type": step_type,
            "run_point_checkout_on_pass": run_point_checkout_on_pass,
            "skippable": bool(item.get("skippable", False)),
            "requires_step_ids": requires_step_ids,
        }
        arms_key = str(item.get("arms_test_mode_state_key", "")).strip()
        if arms_key:
            step_row["arms_test_mode_state_key"] = arms_key
        raw_skip_when = item.get("skip_when")
        if isinstance(raw_skip_when, list) and raw_skip_when:
            skip_codes: list[str] = []
            for code in raw_skip_when:
                text = str(code).strip()
                if text:
                    skip_codes.append(text)
            if skip_codes:
                step_row["skip_when"] = skip_codes
        if report_ref:
            step_row["report_ref"] = report_ref
        raw_actions = item.get("actions")
        if isinstance(raw_actions, list) and raw_actions:
            step_row["actions"] = raw_actions
        steps.append(step_row)
    return steps


def run_compile(
    controllers_csv: Path,
    profiles_dir: Path,
    output_json: Path,
    report_json: Path,
) -> int:
    """Compile controllers CSV + profile library; write runtime + import report JSON.

    Used by the runtime CLI and by PyInstaller single-file builds (no subprocess).
    """
    try:
        profiles_by_id, profile_errors, profile_warnings = load_profiles(profiles_dir)
        runtime_model, report, exit_code = compile_model(
            controllers_csv=controllers_csv,
            profiles_by_id=profiles_by_id,
            initial_errors=profile_errors,
            initial_warnings=profile_warnings,
        )
    except (OSError, ValueError, json.JSONDecodeError) as err:
        fallback = {
            "compile_ok": False,
            "controller_count": 0,
            "error_count": 1,
            "warning_count": 0,
            "errors": [{"code": "fatal", "message": str(err)}],
            "warnings": [],
        }
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(fallback, indent=2), encoding="utf-8")
        print("compile_ok=false errors=1 warnings=0")
        print(f"error: {err}")
        return 2

    output_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(runtime_model, indent=2), encoding="utf-8")
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"compile_ok={'true' if report['compile_ok'] else 'false'} "
        f"errors={report['error_count']} warnings={report['warning_count']}"
    )
    return exit_code


def main() -> int:
    args = parse_args()
    return run_compile(
        args.controllers_csv,
        args.profiles_dir,
        args.output_json,
        args.report_json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
