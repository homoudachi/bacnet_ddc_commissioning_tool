# ADR 0011 — `site-controllers` spreadsheet v1 column contract

## Status

Accepted

## Context

Large jobs are **spreadsheet-first** (`docs/project.md`). The import compiler (`tools/import/compile_job.py`) already enforces a **minimum** CSV header set. Authors need a **single canonical list** of which columns exist in v1, which are required, and what happens to unknown columns, without waiting for the full “120+ column” site-specific spec.

## Decision

1. **Canonical documentation** for v1 lives in **`docs/schema/site-controllers-v1.csv.md`** (human-readable table + example). This ADR points there; row-level semantics for object overrides stay **out of scope** until a future schema version adds supported override columns.
2. **Required columns** (must be present, non-empty per row where applicable), enforced today:
   - `controller_label` — unique per job; stable identifier in artifacts.
   - `profile_id` — must match a `*.json` profile in the configured `--profiles-dir`.
   - `bacnet_device_instance` — positive integer; **unique per job** in v1.
   - `bacnet_ip` — IPv4 host string (no BBMD / BACnet/SC in v1 transport).
   - `bacnet_port` — integer **1–65535** (typically **47808**).
3. **Optional columns** (recognized and copied into runtime display metadata today):
   - `building_floor`
   - `notes`
4. **Unknown columns:** the compiler **ignores** cell values for headers it does not recognize and emits an **`import-report.json` warning** with code **`unknown_controller_csv_column`** so large customer sheets with extra columns do not fail import silently.

## Consequences

- Adding first-class columns (e.g. per-row BACnet object overrides) requires updating **`REQUIRED_COLUMNS` / known header set**, **`docs/schema/site-controllers-v1.csv.md`**, this ADR if the contract changes, and tests in **`tests/test_import_compiler.py`**.
- Duplicate BACnet **IP:port** with different device instances remains a **warning** (existing behavior), not a hard error, unless tightened in a future ADR.
