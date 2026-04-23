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

            controllers.append(
                {
                    "controller_label": label,
                    "profile_id": profile_id,
                    "profile": {
                        "profile_id": profile_id,
                        "display_name": str(profile.get("display_name", "")).strip(),
                        "schema_version": str(profile.get("schema_version", "")).strip(),
                    },
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
        steps.append(
            {
                "step_id": step_id,
                "label": label,
                "skippable": bool(item.get("skippable", False)),
                "requires_step_ids": requires_step_ids,
            }
        )
    return steps


def main() -> int:
    args = parse_args()
    try:
        profiles_by_id, profile_errors, profile_warnings = load_profiles(args.profiles_dir)
        runtime_model, report, exit_code = compile_model(
            controllers_csv=args.controllers_csv,
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
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(fallback, indent=2), encoding="utf-8")
        print("compile_ok=false errors=1 warnings=0")
        print(f"error: {err}")
        return 2

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(runtime_model, indent=2), encoding="utf-8")
    args.report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"compile_ok={'true' if report['compile_ok'] else 'false'} "
        f"errors={report['error_count']} warnings={report['warning_count']}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
