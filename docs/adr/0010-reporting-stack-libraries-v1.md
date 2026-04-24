# ADR 0010 — Reporting stack libraries (v1 slice)

## Status

Accepted

## Context

Commissioning outputs must be **technician- and customer-shareable** (CSV, spreadsheet, PDF). Multiple Python libraries exist; the portable Windows target (ADR 0009) needs dependencies that are **FOSS-friendly**, **maintained**, and **easy to vendor** in a frozen bundle.

## Decision

For **`export-commissioning-report`** unified rows (point checkout + **manual airflow measurements** + thermal modulation):

| Output | Library / mechanism | Notes |
|--------|---------------------|--------|
| **CSV** | Python **stdlib** `csv` | UTF-8; shared column contract with unified export. |
| **HTML** (print-to-PDF) | Python **stdlib** only | Simple table; operators use browser **Print → Save as PDF**. |
| **XLSX** | **openpyxl** (see `requirements.txt`) | Single sheet `commissioning`; no macros. |
| **PDF** (server-side table) | **fpdf2** (see `requirements.txt`) | Landscape A4 table; Helvetica / Latin-1–safe text; optional header image. |

**Not in v1:** styled customer templates, charts, or merged cells beyond a single data table. Long-lived **schema versioning** for the JSON commissioning report remains partially documented in `docs/project.md`; breaking changes should bump `schema_version` and be noted in the project doc.

## Consequences

- CI and local dev **must** install `requirements.txt` for XLSX/PDF export tests and BACnet writes.
- Integrators who need **exact** PDF branding should treat current PDF output as a **baseline table** until a template ADR or issue defines layout rules.
