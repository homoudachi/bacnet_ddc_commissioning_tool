# Unified commissioning report CSV — v1 column contract

This file is **generated**. Do not edit the **Column list** table by hand.

- **Source of truth (order + names):** `COMMISSIONING_REPORT_UNIFIED_FIELDNAMES` in `tools/runtime/app.py`.
- **Regenerate:** `python3 tools/schema/gen_commissioning_report_unified_csv_doc.py`
- **CI:** `python3 tools/schema/gen_commissioning_report_unified_csv_doc.py --check`
- **ADR:** [0014](../adr/0014-unified-commissioning-report-export-contract.md)

## Column list (order)

| Column | Used for |
|--------|----------|
| `entry_ts` | ISO timestamp from report entry |
| `kind` | Entry discriminator (see table below) |
| `controller_label` | Controller row |
| `step_id` | Profile commissioning step when applicable |
| `step_status` | Step outcome for point-checkout rows; often blank |
| `report_ref` | Profile `report_ref` when set |
| `technician_name` | Operator / technician |
| `note` | Free text |
| `all_read_ok` | Point checkout aggregate |
| `artifact_json` | Path to JSON artifact when applicable |
| `command_object_id` | Modulation / airflow-adjust / valve-prompt command object |
| `command_percent` | Written command % (modulation sweep, airflow adjust, valve prompt) |
| `dwell_seconds` | Modulation sweep dwell |
| `sweep_index` | Multi-point sweep index |
| `sweep_count` | Total sweeps in batch |
| `trigger` | e.g. `thermal_modulation_batch` |
| `object_id` | BACnet logical object for read rows |
| `property` | BACnet property (usually `presentValue`) |
| `status` | Read/write terminal status |
| `value_str` | Read value or semantic text (e.g. `confirmed` on valve prompt rows) |
| `read_source` | BACnet vs `session` on sweep rows; `bacnet` on tachometer confirm |
| `measurement_branch_id` | Manual airflow branch id |
| `measured_flow_L_s` | Measured airflow (L/s) |
| `measurement_tool` | e.g. `balometer` |
| `design_flow_L_s` | Branch design from profile when recorded |
| `session_key` | Session field for tachometer / manual airflow / valve confirm |
| `target_flow_ratio_of_design` | Profile ratio on `airflow_adjust_command` rows |
| `design_supply_airflow_L_s` | From `commissioning_meta.unit_specs` when present |
| `prompt_id` | CHW valve stroke `commissioning-confirm-prompt` id |

Many cells are **empty** for a given `kind`; integrators should treat blank as N/A.

## `kind` values (unified export)

| `kind` | Typical non-empty columns |
|--------|---------------------------|
| `point_checkout_after_step` | `step_status`, `all_read_ok`, `artifact_json`, per-read `object_id` / `property` / `status` |
| `thermal_modulation_sweep` | `command_object_id`, `command_percent`, `dwell_seconds`, sweep fields, per-read columns + `read_source` |
| `thermal_modulation_sample` | `readings` flattened per object |
| `manual_airflow_measurement` | `measurement_*`, `design_flow_L_s`, `session_key` |
| `tachometer_reference_confirmation` | `object_id` (read point), `value_str`, `read_source`, `session_key` |
| `airflow_adjust_command` | `command_object_id`, `command_percent`, `target_flow_ratio_of_design`, `design_supply_airflow_L_s` |
| `valve_prompt_confirmation` | `prompt_id`, `session_key`, `command_object_id`, `command_percent`, `value_str` |

## Versioning

- **Unified CSV v1** = this column set as shipped. **Breaking** changes (rename, reorder, remove) require a **v2** doc + ADR update and should bump or annotate consumer expectations.
- **JSON** `artifacts/commissioning_report.json` uses **`schema_version`** on the document (`0.2-commissioning-report` today); new **`kind`** values are backward-compatible for readers that ignore unknown kinds.
