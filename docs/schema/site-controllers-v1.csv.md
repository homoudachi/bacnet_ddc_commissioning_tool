# Site controllers spreadsheet — v1 column contract

This document is the **canonical v1** description for the CSV consumed by `tools/import/compile_job.py` (same shape as `docs/examples/site-controllers.template.csv`). See **ADR 0011** (`docs/adr/0011-site-controllers-spreadsheet-v1-contract.md`).

## Required columns

| Column | Type | Rule |
|--------|------|------|
| `controller_label` | string | Non-empty; **unique** across all rows. |
| `profile_id` | string | Non-empty; must match `profile_id` in a profile JSON file in the import `--profiles-dir`. |
| `bacnet_device_instance` | integer | Non-empty; **unique** across all rows for v1; sent to BACnet as the expected device instance. |
| `bacnet_ip` | string | Non-empty; IPv4 literal or resolvable host (transport is BACnet/IP **UDP** only in v1). |
| `bacnet_port` | integer | **1–65535**; typical value **47808**. |

## Optional columns (v1)

| Column | Type | Rule |
|--------|------|------|
| `building_floor` | string | Copied to runtime controller row for display / audit. May be empty. |
| `notes` | string | Copied to runtime controller row. May be empty. |

## Optional per-row BACnet instance overrides (v1)

When several controllers share a **profile** but differ on **BACnet object instance numbers** (same object types, different instances), add columns named:

**`bacnet_object_<logical_id>`** → integer BACnet **instance** only

- **`<logical_id>`** must match an **`objects[].id`** string from the profile JSON (e.g. `msv_test_mode`, `ai_sat`).
- The compiler keeps **`object_type`**, **`writable`**, allowlists, and flow metadata from the profile; only **`bacnet.instance`** on the compiled **`objects_by_id`** entry is replaced for that controller row.
- **Empty cell** = no override for that object (profile default instance applies).
- **Invalid** logical id, non-integer cell, or negative instance → **`compile_ok: false`** with error codes **`unknown_bacnet_object_override_id`** or **`invalid_bacnet_object_instance_override`**.
- Applied overrides are also copied into **`commissioning_meta.controller_csv_object_instance_overrides`** (sorted keys) for audit / export.

These columns are **recognized** by the compiler and do **not** produce **`unknown_controller_csv_column`** warnings.

## Unknown columns

Spreadsheets often carry **extra** columns (site IDs, panel names, future overrides). The compiler **does not fail** on unknown headers; it emits a warning **`unknown_controller_csv_column`** in `import-report.json` for each unrecognized header so authors see them during `compile-import` / `validate-import`.

## Not in v1 (explicitly deferred)

- Per-row overrides of **`object_type`**, **property names**, or **device instance** (only BACnet **object instance** per logical id is supported via `bacnet_object_*` columns).
- **BACnet/SC**, **MS/TP**, **BBMD** addressing columns.
- **120+ controller** performance targets and stress harness — backlog; v1 focuses on correctness and clear validation errors.

## Example

See **`docs/examples/site-controllers.template.csv`**.
