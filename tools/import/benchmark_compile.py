#!/usr/bin/env python3
"""Stress-style harness: compile a synthetic N-row site-controllers CSV.

Measures wall time for ``compile_model`` (no subprocess). Use before/after
import compiler changes or to sanity-check large-sheet performance locally::

    python3 tools/import/benchmark_compile.py --rows 500
    python3 tools/import/benchmark_compile.py --rows 2000 --profile-id bench_fcu_v1

Requires a minimal profile JSON matching ``--profile-id`` under ``--profiles-dir``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILE_JOB = ROOT / "tools" / "import" / "compile_job.py"


def _load_compile_job():
    import importlib.util

    spec = importlib.util.spec_from_file_location("compile_job", COMPILE_JOB)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load compile_job")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_minimal_profile(path: Path, profile_id: str) -> None:
    """Single FCU-shaped profile for bulk addressing rows (instances are CSV-driven)."""
    data = {
        "schema_version": "0.1-benchmark",
        "profile_id": profile_id,
        "display_name": "Benchmark FCU (minimal objects)",
        "commissioning_write_allowlist": ["msv_test_mode"],
        "commissioning_read_allowlist": ["ai_sat", "msv_test_mode"],
        "point_checkout": [{"object_id": "ai_sat", "property": "presentValue"}],
        "objects": [
            {
                "id": "msv_test_mode",
                "writable": True,
                "bacnet": {"object_type": "multiStateValue", "instance": 50},
            },
            {
                "id": "ai_sat",
                "writable": False,
                "bacnet": {"object_type": "analogInput", "instance": 2},
            },
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_bulk_csv(path: Path, *, rows: int, profile_id: str) -> None:
    fieldnames = [
        "controller_label",
        "profile_id",
        "bacnet_device_instance",
        "bacnet_ip",
        "bacnet_port",
        "building_floor",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=fieldnames)
        w.writeheader()
        for i in range(rows):
            w.writerow(
                {
                    "controller_label": f"BENCH-{i:05d}",
                    "profile_id": profile_id,
                    "bacnet_device_instance": str(30000 + i),
                    "bacnet_ip": "192.168.200.1",
                    "bacnet_port": "47808",
                    "building_floor": "B99",
                    "notes": "benchmark_compile synthetic row",
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=500, help="Number of controller rows (default 500).")
    parser.add_argument(
        "--profile-id",
        default="bench_fcu_v1",
        help="profile_id written into synthetic CSV and minimal profile file.",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=None,
        help="Directory with profile JSONs (default: temp dir with one minimal profile).",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Print temp directory path and do not delete it (for inspection).",
    )
    args = parser.parse_args()
    if args.rows < 1:
        print("error: --rows must be >= 1", file=sys.stderr)
        return 2

    mod = _load_compile_job()

    def _run_in_dir(tmp: Path) -> int:
        prof_dir = args.profiles_dir or tmp
        if args.profiles_dir is None:
            _write_minimal_profile(prof_dir / f"{args.profile_id}.json", args.profile_id)
        csv_path = tmp / "controllers.csv"
        _write_bulk_csv(csv_path, rows=args.rows, profile_id=args.profile_id)

        profiles_by_id, p_err, p_warn = mod.load_profiles(prof_dir)
        t0 = time.perf_counter()
        runtime_model, report, code = mod.compile_model(
            csv_path,
            profiles_by_id,
            initial_errors=list(p_err),
            initial_warnings=list(p_warn),
        )
        elapsed = time.perf_counter() - t0

        summary = runtime_model.get("summary", {})
        out = {
            "rows": args.rows,
            "seconds": round(elapsed, 4),
            "rows_per_second": round(args.rows / elapsed, 1) if elapsed > 0 else None,
            "compile_ok": bool(report.get("compile_ok")),
            "controller_count": summary.get("controller_count"),
            "error_count": report.get("error_count"),
            "warning_count": report.get("warning_count"),
            "exit_code": code,
        }
        print(json.dumps(out, indent=2))
        return int(code)

    if args.keep_temp:
        tmp = Path(tempfile.mkdtemp(prefix="bench-compile-"))
        print(f"temp_dir={tmp}", file=sys.stderr)
        try:
            return _run_in_dir(tmp)
        finally:
            pass  # keep for inspection
    with tempfile.TemporaryDirectory(prefix="bench-compile-") as tmp_str:
        return _run_in_dir(Path(tmp_str))


if __name__ == "__main__":
    raise SystemExit(main())
