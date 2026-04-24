# ADR 0014 — Unified commissioning report export (CSV v1 contract)

## Status

Accepted

## Context

`export-commissioning-report --output-csv-unified` (and HTML/XLSX/PDF built from the same row list) is the **integrator-facing** surface for spreadsheets and BI. Column names and order were only implicit in `tools/runtime/app.py`. Several **`kind`** values were added over time (modulation, point checkout, manual airflow, tachometer, airflow adjust, valve prompt). Without a written contract, downstream parsers break silently when columns shift.

## Decision

1. **Canonical column order** — **`COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`** in `tools/runtime/app.py` is the **single source of truth** for unified export headers.
2. **Human-readable mirror** — [`docs/schema/commissioning-report-unified-csv-v1.md`](../schema/commissioning-report-unified-csv-v1.md) documents each column and maps **`kind`** → typical populated fields.
3. **Versioning rules**
   - **Additive** changes (new optional column at end, new `kind` with sparse columns) — update the schema doc + this ADR note; prefer **append-only** columns.
   - **Breaking** changes (rename, reorder, remove column) — bump to **unified CSV v2** (new doc filename / section), announce in `docs/project.md`, and treat as a migration for integrators.
4. **JSON report** — `commissioning_report.json` **`schema_version`** (e.g. `0.2-commissioning-report`) is independent; new `kind` payloads remain **backward-compatible** if consumers ignore unknown `kind` values.

## Consequences

- PRs that change **`COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`** or row shaping must **update the schema doc** (and ADR if versioning rules change).
- Customer-branded PDF layouts (ADR 0010) still sit on top of this flat contract until a dedicated template ADR exists.
