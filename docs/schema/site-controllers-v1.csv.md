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

## Unknown columns

Spreadsheets often carry **extra** columns (site IDs, panel names, future overrides). The compiler **does not fail** on unknown headers; it emits a warning **`unknown_controller_csv_column`** in `import-report.json` for each unrecognized header so authors see them during `compile-import` / `validate-import`.

## Not in v1 (explicitly deferred)

- Per-row **BACnet object overrides** (e.g. alternate instance numbers) — not read from the CSV today; use profile JSON or duplicate profiles as needed.
- **BACnet/SC**, **MS/TP**, **BBMD** addressing columns.
- **120+ controller** performance targets and stress harness — backlog; v1 focuses on correctness and clear validation errors.

## Example

See **`docs/examples/site-controllers.template.csv`**.
