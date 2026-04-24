# ADR 0014 — Unified commissioning report export (CSV v1 contract)

## Status

Accepted

## Context

`export-commissioning-report --output-csv-unified` (and HTML/XLSX/PDF built from the same row list) is the **integrator-facing** surface for spreadsheets and BI. Column names and order were only implicit in `tools/runtime/app.py`. Several **`kind`** values were added over time (modulation, point checkout, manual airflow, tachometer, airflow adjust, valve prompt). Without a written contract, downstream parsers break silently when columns shift.

## Decision

1. **Canonical column order** — **`COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`** in `tools/runtime/app.py` is the **single source of truth** for unified export headers.
2. **Human-readable mirror** — [`docs/schema/commissioning-report-unified-csv-v1.md`](../schema/commissioning-report-unified-csv-v1.md) is **generated** from that tuple via **`python3 tools/schema/gen_commissioning_report_unified_csv_doc.py`** (per-column descriptions live in **`COLUMN_HELP`** in that script). **`--check`** is used in CI so the committed doc cannot drift from code.
3. **Versioning rules**
   - **Additive** changes (new optional column at end, new `kind` with sparse columns) — update the schema doc + this ADR note; prefer **append-only** columns.
   - **Breaking** changes (rename, reorder, remove column) — bump to **unified CSV v2** (new doc filename / section), announce in `docs/project.md`, and treat as a migration for integrators.
4. **JSON report** — `commissioning_report.json` **`schema_version`** (e.g. `0.2-commissioning-report`) is independent; new `kind` payloads remain **backward-compatible** if consumers ignore unknown `kind` values.

## Consequences

- PRs that add/rename/remove unified columns must update **`COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`** and **`COLUMN_HELP`** in `tools/schema/gen_commissioning_report_unified_csv_doc.py`, then run **`python3 tools/schema/gen_commissioning_report_unified_csv_doc.py`** to refresh the markdown (and ADR if versioning rules change).
- **Customer modulation table** (`--output-customer-html` / `--output-customer-pdf`) uses a **narrow** fixed column set (**`COMMISSIONING_REPORT_CUSTOMER_MODULATION_FIELDNAMES`** in `tools/runtime/app.py`) over **`_commissioning_report_modulation_rows`** only; it is **not** part of the unified CSV v1 tuple and may evolve independently for shareable heat/cool summaries.
- Customer-branded PDF layouts (ADR 0010) still sit on top of this flat contract until a dedicated template ADR exists.
