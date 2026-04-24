# ADR 0011 — `site-controllers` spreadsheet v1 column contract

## Status

Accepted

## Context

Large jobs are **spreadsheet-first** (`docs/project.md`). The import compiler (`tools/import/compile_job.py`) already enforces a **minimum** CSV header set. Authors need a **single canonical list** of which columns exist in v1, which are required, and what happens to unknown columns, without waiting for the full “120+ column” site-specific spec.

## Decision

1. **Canonical documentation** for v1 lives in **`docs/schema/site-controllers-v1.csv.md`** (human-readable table + example). This ADR points there. **Per-row BACnet object instance overrides** use dynamic CSV headers **`bacnet_object_<logical_id>`** (integer instance only; logical id must exist in the profile **`objects`** list); see the schema doc.
2. **Required columns** (must be present, non-empty per row where applicable), enforced today:
   - `controller_label` — unique per job; stable identifier in artifacts.
   - `profile_id` — must match a `*.json` profile in the configured `--profiles-dir`.
   - `bacnet_device_instance` — positive integer; **unique per job** in v1.
   - `bacnet_ip` — IPv4 host string (no BBMD / BACnet/SC in v1 transport).
   - `bacnet_port` — integer **1–65535** (typically **47808**).
3. **Optional columns** (recognized and copied into runtime display metadata today):
   - `building_floor`
   - `notes`
4. **Optional per-controller BACnet addressing:** any header matching **`bacnet_object_<logical_id>`** where `<logical_id>` is a profile **`objects[].id`** supplies an **integer BACnet instance** override for that logical object on that row only (`object_type` remains from the profile).
5. **Unknown columns:** the compiler **ignores** cell values for headers it does not recognize and emits an **`import-report.json` warning** with code **`unknown_controller_csv_column`** so large customer sheets with extra columns do not fail import silently. Headers matching the **`bacnet_object_<logical_id>`** pattern are treated as optional override columns and are **not** **`unknown_controller_csv_column`** warnings (validation happens per row when cells are non-empty).

## Consequences

- Adding new **fixed-name** optional columns requires updating **`KNOWN_CONTROLLER_COLUMNS`**, **`docs/schema/site-controllers-v1.csv.md`**, this ADR if semantics change, and tests in **`tests/test_import_compiler.py`**. The **`bacnet_object_*`** pattern is intentionally open-ended so new profile object ids do not require compiler changes.
- Duplicate BACnet **IP:port** with different device instances remains a **warning** (existing behavior), not a hard error, unless tightened in a future ADR.
