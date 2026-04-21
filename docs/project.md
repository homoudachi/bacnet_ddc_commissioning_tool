# BACnet commissioning assistant — project record

Audience: future you. Update when intent, behavior, or exports change.

## Goal

Windows **portable executable** that acts as a **commissioning assistant** for BACnet-enabled controllers: command devices, run **automatic tests**, monitor results, and combine **automatic judgment** with **technician verification** (notes + name). Supports **many controllers** per job via an **imported target list**.

## Non-goals (current intent)

- **BACnet transports other than BACnet/IP** (no MS/TP, no BACnet/SC in scope here).
- **BACnet network security** (no BACnet/SC / secured channel; assume trusted-site / lab-style use aligned with “no security”).
- **Non-standard or vendor-proprietary objects** beyond what the **import** describes — surface area is **standard BACnet objects**, with **detail supplied by the import** (which points, properties, and semantics apply per site or per controller).

## Distribution

- **Portable `.exe`** (no installer requirement stated for v1).

## BACnet

| Topic | Decision |
|--------|----------|
| Transport | BACnet/IP only |
| Discovery | **Import list** — operators supply targets (e.g. IP / device identity); no Who-Is-first workflow required for v1 |
| Security | None for this design pass (document site assumptions in [Site-specific requirements](#site-specific-requirements) when known) |

## Commissioning scope (v1 capabilities described so far)

1. **Point checkout** — read / command / verify per imported standard-object definitions.
2. **Airflow estimation** — derived from **electric heat rise** (algorithm and inputs TBD when you specify heat model, safeties, and sensor points).
3. **Manual verification of airflow** — technician confirms real-world conditions against tool guidance or readings.
4. **Tests** — **Automatic** by default; each must be **skippable** or **manually passable** (override automatic fail or skip when the job demands it).

## Site-specific requirements

Real jobs have **rules you cannot fully encode yet**. Capture them here as you learn them: naming, sequences, minimum damper positions, interlocks, which points must never be commanded, order of operations, etc.

_(Add bullets when you can articulate them. “I’ll know it when I see the job” is fine until then — but this section is where those rules land.)_

## Job model

- **Many controllers** per job (single job spans multiple devices from the import).

## Technician sign-off

- **Notes + name** (per step, per test, or per job — refine when you design the UI).
- **Exports for records**: **PDF**, **CSV or XLSX**, and **log data** (raw or structured — define format when implementing).

## Localization and units

- **UI language:** English.
- **Units:** metric; **airflow in L/s** (state any secondary display, e.g. m³/h, if you add it later).

## Licensing

- **Free and open** — choose a specific license (e.g. MIT, Apache-2.0, GPL-3.0) when you add a `LICENSE` file; keep this line in sync with that choice.

## Reference hardware (what question 11 meant)

“Reference hardware” = **what physical BACnet controllers (makes/models)** or **simulators** you will plug in while developing and regression-testing, so you know the tool works on real stacks—not only in theory.

**Status:** not decided yet. When you have even one panel on your bench, list it here (vendor, model, firmware, how it is addressed on B/IP).

## How to run / verify

_(Fill in after the first runnable build.)_

```bash
# e.g. build portable exe, run smoke tests
```

## Definition of done (reuse)

- [ ] Behavior matches this doc for the slice you shipped.
- [ ] Verification command(s) pass (or N/A documented).
- [ ] This doc updated if exports, BACnet assumptions, test rules, or sign-off changed.
- [ ] Commit message states the behavioral change.

## Open questions

- **Electric heat rise → airflow:** equation, required point list, guardrails (min/max airflow, alarm on missing kW / delta-T).
- **Import file format:** schema for controllers, points, standard object/property detail, units, test definitions (if embedded in import).
- **PDF / XLSX stack:** libraries acceptable for FOSS + Windows portable build (XLSX often pulls in a spreadsheet dependency).
- **Log format:** binary, JSON lines, CSV, or rotating text; retention on disk.
- **Site-specific requirements:** see section above — how much is **data-driven in the import** vs **hard-coded per customer template**.
