# Plan: UI, reports, closed-loop airflow, BACnet lab (post–v1 baseline)

Audience: implementers continuing after the **v1 foundation** slice (Python CLI, Docker `bacnet-dev`, unified + customer exports, `commissioning-guided-next`). This document **orders work by difficulty / dependency** so easier wins ship first. **BBMD and macvlan** are **explicitly deferred** unless a concrete need appears—they touch network topology, image layout, and CI runner constraints and are **not** “easy” compared to the items below.

## Principles

1. **Ship vertical slices** (behavior + tests + docs) rather than half-finished horizontal layers.
2. **Keep BACnet/IP unicast + directed Who-Is** as the default transport story until BBMD is scoped (ADR update).
3. **Reuse** `commissioning_report.json`, `COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`, and existing export paths; add new `kind`s or columns only with schema/version discipline (**ADR 0014**).

---

## Tier A — easier / lower risk (do first)

These mostly extend **existing** CLI, exports, or profiles without new transports.

| # | Item | Why “easier” | Suggested approach | Done when |
|---|------|----------------|-------------------|-----------|
| A1 | **Customer PDF polish** (sections, title block, optional multi-sheet XLSX) | fpdf2 + openpyxl already in tree; layout code is local | Add optional `--output-pdf-sections` or a `customer` template mode: cover page (job_id, date, logo), then modulation table, then optional “notes” block; mirror section breaks in XLSX as extra sheets if useful | Golden PDF byte-compare or structural checks + manual visual once; docs in `docs/packaging/release-checklist.md` |
| A2 | **Charts in HTML export** (not PDF first) | Browsers handle SVG/Canvas; no new Python chart deps if using simple SVG | For `--output-html`, embed inline SVG sparklines or small charts per controller (e.g. command % vs SAT from modulation rows) generated from the same normalized row list; print-to-PDF still works | HTML contains chart markup; one unittest with fixed rows asserts SVG path or data attributes |
| A3 | **`commissioning-guided-next` → richer JSON** | Already shipped thin slice | Add `blocked_reasons` / `requires_step_ids` / next recommended CLI command name per step (string hints only, no new subprocess) | Tests + README example for scripting operators |
| A4 | **Large-sheet compiler targets** | `benchmark_compile.py` exists | Define SLO table (e.g. 500 / 2000 rows) in docs; optional CI job on `workflow_dispatch` only to avoid slowing every PR; consider streaming CSV if memory becomes an issue | ADR or `docs/project.md` locks targets; benchmark script documented |

---

## Tier B — medium effort (core product depth)

| # | Item | Why harder | Suggested approach | Done when |
|---|------|------------|---------------------|-----------|
| B1 | **Closed-loop assisted airflow** (tool drives fan toward target L/s using measured feedback) | Needs stable measurement cadence, safety bounds, and profile contract for “stop” conditions | Profile: optional `automatic_airflow_adjustment.closed_loop` with `measurement_session_keys`, `max_iterations`, `tolerance_L_s`, `min_command_percent`, `max_command_percent`. CLI: `commissioning-airflow-adjust-iterate` or extend existing adjust command with `--max-steps` + BACnet reads of branch flows if exposed; else document “session-only” feedback from operator-entered L/s between steps | Integration test against fake BACnet or Docker sim; ADR 0013 extension |
| B2 | **Guided operator UI** (minimal desktop shell) | Packaging, state sync with run-dir, UX scope | **Phase B2a:** Tauri or Electron **read-only** viewer: run-dir picker, show `commissioning-guided-next` + `show-flow` + session JSON. **Phase B2b:** forms for `set-session-value`, `record-step`, confirm prompts. Reuse CLI as child process initially to avoid rewriting BACnet in JS | Shipable preview build + ADR for shell choice |
| B3 | **RAT / HRV proxy rules** | Product policy + validation warnings | Encode eligibility in import or profile; `validate-import` warnings; `docs/project.md` algorithm | Tests for warning codes + example profile |

---

## Tier C — deferred unless prioritized (includes BBMD)

| # | Item | Rationale | If you revisit later |
|---|------|-----------|---------------------|
| C1 | **BBMD / foreign device** | Requires **BACpymes3** (or stack) features, **static BBMD table** in device sim, second subnet in Compose, and CI that can exercise **cross-subnet** paths—easy to get wrong on `ubuntu-latest` and GitHub networking | New ADR: BBMD topology + which commands must work (directed unicast vs broadcast); separate `docker compose` profile `bacnet-bbmd-lab`; extend `list_verifier` / runtime only after sim proves packets |
| C2 | **macvlan “lab” profile** | Host-specific (parent iface, subnet); poor fit for default CI | Document runbook for on-prem bench only; keep `bacnet-dev` as CI default |
| C3 | **COV / subscribe, write batching** | Adapter and test matrix growth | ADR for read path; start with COV on 1–2 object types in sim |

---

## Recommended order of execution

1. **A1 → A2 → A3** (reporting and operator ergonomics without BACnet transport changes).  
2. **A4** in parallel or right after A1 (numbers for sales/support confidence).  
3. **B1** once profile keys and safety caps are agreed (`docs/project.md` + example profile).  
4. **B2a** then **B2b** (UI after JSON hints are stable).  
5. **B3** when a site asks for HRV↔FCU RAT linkage.  
6. **C1–C3** only with explicit stakeholder ask and ADR.

---

## References

- Foundation plan: [`2026-04-21-v1-foundation-plan.md`](2026-04-21-v1-foundation-plan.md)  
- Product intent: [`../project.md`](../project.md)  
- Airflow CLI: **ADR 0013**  
- Unified export: **ADR 0014**  
- Docker sim: **ADR 0008**, [`../simulator/README.md`](../simulator/README.md)  

---

## Revision

- **2026-04-28:** Initial plan (tiered sequencing; BBMD deferred).
