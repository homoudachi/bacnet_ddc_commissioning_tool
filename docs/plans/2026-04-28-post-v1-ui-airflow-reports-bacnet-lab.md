# Plan: UI, reports, closed-loop airflow, BACnet lab (post–v1 baseline)

Audience: implementers continuing after the **v1 foundation** slice (Python CLI, Docker `bacnet-dev`, unified + customer exports, `commissioning-guided-next`). This document **orders work by difficulty / dependency** so easier wins ship first. **Tier C** (BBMD lab, macvlan bench overlay, COV + write batch + **WritePropertyMultiple**) is **shipped** (**ADR 0015**); larger transport work (multi-BBMD tables, full router lab) remains backlog until an ADR scopes it.

## Principles

1. **Ship vertical slices** (behavior + tests + docs) rather than half-finished horizontal layers.
2. **Keep BACnet/IP unicast + directed Who-Is** as the default transport story until BBMD is scoped (ADR update).
3. **Reuse** `commissioning_report.json`, `COMMISSIONING_REPORT_UNIFIED_FIELDNAMES`, and existing export paths; add new `kind`s or columns only with schema/version discipline (**ADR 0014**).

---

## Tier A — easier / lower risk (do first)

These mostly extend **existing** CLI, exports, or profiles without new transports.

| # | Item | Why “easier” | Suggested approach | Done when |
|---|------|----------------|-------------------|-----------|
| A1 | **Customer PDF polish** (sections, title block, optional multi-sheet XLSX) | fpdf2 + openpyxl already in tree; layout code is local | **`--output-customer-pdf`:** cover page (job_id, schema, generated UTC, logo) + modulation table + optional notes page from modulation entry `note` fields. **`--output-xlsx --xlsx-include-modulation`:** second sheet `modulation`. | Shipped **2026-04-28**; see `docs/packaging/release-checklist.md` |
| A2 | **Charts in HTML export** (not PDF first) | Browsers handle SVG/Canvas; no new Python chart deps if using simple SVG | **`--output-html`:** after `thermal_modulation_sweep` rows with `ai_sat` read_ok, inline SVG per controller (command % vs SAT polyline). | Shipped **2026-04-28**; `tests/test_commissioning_html_modulation_charts.py` |
| A3 | **`commissioning-guided-next` → richer JSON** | Already shipped thin slice | Each step includes **`suggested_cli_commands`** (strings) and **`blocked_reasons`** (prereq / `skip_when` gates); compact row already had **`requires_step_ids`** when present. | Shipped **2026-04-28**; `tests/test_runtime_cli.py` |
| A4 | **Large-sheet compiler targets** | `benchmark_compile.py` exists | **SLO** documented in `docs/project.md` (developer machine, CPython 3.12); CI keeps **`--rows 120`** smoke. Optional `workflow_dispatch` benchmark: backlog unless CI noise is acceptable. | Shipped **2026-04-28** (doc targets); optional workflow still open |

---

## Tier B — medium effort (core product depth)

| # | Item | Why harder | Suggested approach | Done when |
|---|------|------------|---------------------|-----------|
| B1 | **Closed-loop assisted airflow** (tool drives fan toward target L/s using measured feedback) | Needs stable measurement cadence, safety bounds, and profile contract for “stop” conditions | **`commissioning-airflow-closed-loop-iterate`** + profile **`automatic_airflow_adjustment.closed_loop`** (BACnet flow read + iterative fan %). | Shipped **2026-04-28**; ADR 0013 §6; `tests/test_runtime_cli.py` |
| B2 | **Guided operator UI** (minimal desktop shell) | Packaging, state sync with run-dir, UX scope | **`operator-gui`** (stdlib **HTTPServer**): **`/guided`** flow UI + **`/`** CLI form; **`desktop/tauri-operator/`** **Tauri 2** shell (Rust spawns **`python3 tools/runtime/app.py`**; see **`docs/packaging/tauri-operator-desktop.md`**). | Shipped **2026-04-28**; guided UI expanded **2026-04-25**; README screenshots + **CI checksum** for PNGs (**`tools/packaging/capture_operator_guided_screenshots.sh`**) |
| B3 | **RAT / HRV proxy rules** | Product policy + validation warnings | Profile **`rat_temperature_proxy`** (`enabled`, `proxy_controller_label`, `proxy_read_object_id`); **`compile-import`** copies into **`commissioning_meta`** and emits **`rat_temperature_proxy_*`** warnings when misconfigured. | Shipped **2026-04-28**; `tests/test_import_compiler.py` |

---

## Tier C — BACnet lab transport (shipped)

| # | Item | Notes | Done when |
|---|------|-------|-----------|
| C1 | **BBMD / foreign device** | Isolated /24 + BBMD + sidecar **ForeignApplication** probe | **`bacnet-bbmd-lab`** profile, **`tools/simulator/docker_bbmd_lab_smoke.sh`**, **ADR 0015** |
| C2 | **macvlan “lab” profile** | Bench-only overlay | **`docker-compose.macvlan.example.yml`**, **`docs/simulator/macvlan-lab.md`** |
| C3 | **COV / subscribe, write batching** | Sim SubscribeCOV + **`bacnet-write-batch`** (`sequential` or **`multiple`** = WritePropertyMultiple) | **`bacnet-subscribe-cov`**, **`bacnet-write-batch`**, **`docker_bacnet_smoke.sh`** |

### Tier C — follow-on backlog (not shipped)

| Item | Notes |
|------|--------|
| **Multi-BBMD / distributed BDT** | More than one BBMD peer table row, NAT-BBMD, or production FDT policy—needs site-driven ADR. |

**Shipped follow-on:** **ReadPropertyMultiple** — `CommissioningBACnetAdapter.read_present_values_property_multiple`; **`bacnet-point-checkout`** and automatic **`record-step`** checkout batch with one RPM when two or more points resolve (**ADR 0016**); Docker lab sim handles RPM for present-value.

---

## Recommended order of execution

1. **A1 → A2 → A3** (reporting and operator ergonomics without BACnet transport changes).  
2. **A4** in parallel or right after A1 (numbers for sales/support confidence).  
3. **B1** once profile keys and safety caps are agreed (`docs/project.md` + example profile).  
4. **B2a** then **B2b** (UI after JSON hints are stable).  
5. **B3** when a site asks for HRV↔FCU RAT linkage.  
6. **C1–C3** shipped (**ADR 0015**, including **WritePropertyMultiple** on **`bacnet-write-batch --mode multiple`**); use the **Tier C follow-on** table above for the next transport slices.

### Tauri packaging (optional extras, deferred)

The **Tauri operator** CI ships **Ubuntu `.deb`** and **Windows NSIS** artifacts only. **macOS `.dmg`** builds and **signed NSIS** installers remain **out of scope** for default automation until a release asks for them (runner cost, Apple notarization, and certificate handling). See [`docs/packaging/tauri-operator-desktop.md`](../packaging/tauri-operator-desktop.md).

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
- **2026-04-28:** Tier A items A1–A4 marked shipped in-repo (see foundation plan current status); Tier B marked shipped; Tier C later shipped **2026-04-25**.
- **2026-04-24:** Documented intentional deferral of **macOS `.dmg`** and **signed NSIS** for the Tauri operator (CI stays Linux + Windows only).
- **2026-04-25:** Tier **C1–C3** shipped (BBMD lab profile, macvlan example + runbook, COV + write batch CLI); see **ADR 0015**.
- **2026-04-25:** **WritePropertyMultiple** path: lab sim + **`bacnet-write-batch --mode multiple`** + CI smoke; ADR 0015 updated.
- **2026-04-25:** **`operator-gui` `/guided`** — graphical commissioning flow (controllers, steps, blockers, session, record-step, point checkout API).
- **2026-04-25:** Guided UI **screenshots in README** + **`capture_operator_guided_screenshots.sh check`** in CI; PNG SHA-256 unit test.
