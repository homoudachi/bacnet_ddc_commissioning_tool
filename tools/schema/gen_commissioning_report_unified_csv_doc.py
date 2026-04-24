#!/usr/bin/env python3
"""Generate ``docs/schema/commissioning-report-unified-csv-v1.md`` from runtime column list.

Single source of truth for **column order** and **names**:
``COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`` in ``tools/runtime/app.py``.
Human descriptions live in ``COLUMN_HELP`` below; update when you add columns.

Usage::

    python3 tools/schema/gen_commissioning_report_unified_csv_doc.py
    python3 tools/schema/gen_commissioning_report_unified_csv_doc.py --check

``--check`` exits 0 only if the on-disk doc matches generated output (for CI).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_APP = ROOT / "tools" / "runtime" / "app.py"
RUNTIME_DIR = ROOT / "tools" / "runtime"
DEFAULT_OUT = ROOT / "docs" / "schema" / "commissioning-report-unified-csv-v1.md"

# Human descriptions keyed by column name (must cover every fieldname from code).
COLUMN_HELP: dict[str, str] = {
    "entry_ts": "ISO timestamp from report entry",
    "kind": "Entry discriminator (see table below)",
    "controller_label": "Controller row",
    "step_id": "Profile commissioning step when applicable",
    "step_status": "Step outcome for point-checkout rows; often blank",
    "report_ref": "Profile `report_ref` when set",
    "technician_name": "Operator / technician",
    "note": "Free text",
    "all_read_ok": "Point checkout aggregate",
    "artifact_json": "Path to JSON artifact when applicable",
    "command_object_id": "Modulation / airflow-adjust / valve-prompt command object",
    "command_percent": "Written command % (modulation sweep, airflow adjust, valve prompt)",
    "dwell_seconds": "Modulation sweep dwell",
    "sweep_index": "Multi-point sweep index",
    "sweep_count": "Total sweeps in batch",
    "trigger": "e.g. `thermal_modulation_batch`",
    "object_id": "BACnet logical object for read rows",
    "property": "BACnet property (usually `presentValue`)",
    "status": "Read/write terminal status",
    "value_str": "Read value or semantic text (e.g. `confirmed` on valve prompt rows)",
    "read_source": "BACnet vs `session` on sweep rows; `bacnet` on tachometer confirm",
    "measurement_branch_id": "Manual airflow branch id",
    "measured_flow_L_s": "Measured airflow (L/s)",
    "measurement_tool": "e.g. `balometer`",
    "design_flow_L_s": "Branch design from profile when recorded",
    "session_key": "Session field for tachometer / manual airflow / valve confirm",
    "target_flow_ratio_of_design": "Profile ratio on `airflow_adjust_command` rows",
    "design_supply_airflow_L_s": "From `commissioning_meta.unit_specs` when present",
    "prompt_id": "CHW valve stroke `commissioning-confirm-prompt` id",
}

KIND_SECTION = """## `kind` values (unified export)

| `kind` | Typical non-empty columns |
|--------|---------------------------|
| `point_checkout_after_step` | `step_status`, `all_read_ok`, `artifact_json`, per-read `object_id` / `property` / `status` |
| `thermal_modulation_sweep` | `command_object_id`, `command_percent`, `dwell_seconds`, sweep fields, per-read columns + `read_source` |
| `thermal_modulation_sample` | `readings` flattened per object |
| `manual_airflow_measurement` | `measurement_*`, `design_flow_L_s`, `session_key` |
| `tachometer_reference_confirmation` | `object_id` (read point), `value_str`, `read_source`, `session_key` |
| `airflow_adjust_command` | `command_object_id`, `command_percent`, `target_flow_ratio_of_design`, `design_supply_airflow_L_s` |
| `valve_prompt_confirmation` | `prompt_id`, `session_key`, `command_object_id`, `command_percent`, `value_str` |
"""

VERSIONING_SECTION = """## Versioning

- **Unified CSV v1** = this column set as shipped. **Breaking** changes (rename, reorder, remove) require a **v2** doc + ADR update and should bump or annotate consumer expectations.
- **JSON** `artifacts/commissioning_report.json` uses **`schema_version`** on the document (`0.2-commissioning-report` today); new **`kind`** values are backward-compatible for readers that ignore unknown kinds.
"""


def _load_fieldnames() -> tuple[str, ...]:
    if str(RUNTIME_DIR) not in sys.path:
        sys.path.insert(0, str(RUNTIME_DIR))
    spec = importlib.util.spec_from_file_location("runtime_app_gen_schema", RUNTIME_APP)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNTIME_APP}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return tuple(mod.COMMISSIONING_REPORT_UNIFIED_FIELDNAMES)


def generate_document() -> str:
    names = _load_fieldnames()
    missing = [n for n in names if n not in COLUMN_HELP]
    if missing:
        raise SystemExit(
            "error: COLUMN_HELP missing keys (add descriptions in "
            f"tools/schema/gen_commissioning_report_unified_csv_doc.py): {missing}"
        )
    extra = set(COLUMN_HELP) - set(names)
    if extra:
        raise SystemExit(
            "error: COLUMN_HELP has keys not in COMMISSIONING_REPORT_UNIFIED_FIELDNAMES: "
            f"{sorted(extra)}"
        )

    lines = [
        "# Unified commissioning report CSV — v1 column contract",
        "",
        "This file is **generated**. Do not edit the **Column list** table by hand.",
        "",
        "- **Source of truth (order + names):** `COMMISSIONING_REPORT_UNIFIED_FIELDNAMES` in `tools/runtime/app.py`.",
        "- **Regenerate:** `python3 tools/schema/gen_commissioning_report_unified_csv_doc.py`",
        "- **CI:** `python3 tools/schema/gen_commissioning_report_unified_csv_doc.py --check`",
        "- **ADR:** [0014](../adr/0014-unified-commissioning-report-export-contract.md)",
        "",
        "## Column list (order)",
        "",
        "| Column | Used for |",
        "|--------|----------|",
    ]
    for col in names:
        lines.append(f"| `{col}` | {COLUMN_HELP[col]} |")
    lines.extend(
        [
            "",
            "Many cells are **empty** for a given `kind`; integrators should treat blank as N/A.",
            "",
            KIND_SECTION.rstrip() + "\n",
            VERSIONING_SECTION.rstrip() + "\n",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Markdown output path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if output file differs from generated text",
    )
    args = parser.parse_args()
    text = generate_document()
    out = Path(args.output)
    if args.check:
        if not out.is_file():
            print(f"error: missing {out}", file=sys.stderr)
            return 1
        existing = out.read_text(encoding="utf-8")
        if existing != text:
            print(
                f"error: {out} is out of date; run:\n"
                f"  python3 tools/schema/gen_commissioning_report_unified_csv_doc.py",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {out} matches generated content")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
