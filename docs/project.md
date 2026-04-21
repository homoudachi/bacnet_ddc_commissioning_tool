# BACnet commissioning assistant — project record

Audience: future you. Update when intent, behavior, or exports change.

## Goal

Windows **portable executable** that acts as a **commissioning assistant** for BACnet-enabled controllers: command devices, run **automatic tests**, monitor results, and combine **automatic judgment** with **technician verification** (notes + name). Supports **many controllers** per job via an **imported target list**.

## Controllers and configuration

- **Hardware:** Innatech controllers.
- **Application logic:** Custom configurations **authored by you**; the tool assumes familiarity with those programs but does not embed vendor-secret protocols—**BACnet objects** expose **inputs and outputs** as seen on the network.
- **Test / override mode:** Controllers support a **test mode** that can **override automatic logic** so commissioning can drive outputs and observe behavior safely within that mode (exact BACnet representation: document per program when you lock the import schema).

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
2. **Airflow estimation (electric heat)** — use the **standard heat-rise / sensible-heat** relationship (same family of formula used in field airflow estimation from kW and ΔT). **Inputs:** **heater command** (on/off or staged as your programs expose), **heater capacity**, **supply air temperature (SAT)**, **return air temperature (RAT)**. **Supply airflow** is **automatically modulated** (e.g. fan speed / VFD command within safe limits) to **approach design** conditions; then **manual verification** of real airflow (L/s) remains the commissioning record.
3. **Manual verification of airflow** — technician confirms measured or inferred airflow against design after the automatic modulation / estimation pass.
4. **Tests** — **Automatic** by default; each must be **skippable** or **manually passable** (override automatic fail or skip when the job demands it).

## Site-specific requirements

**Variation across unit types:** There are **other unit types with different I/O and interlocks** than the template below. Treat each **equipment profile** (or import bundle) as authoritative for which analogs, thresholds, and test-mode behavior apply—avoid hard-coding one rooftop’s logic into the core app.

### Example — electric heat enable interlock (one program family)

- **Fan tachometer:** **Analog input (AI)**, **2–20 mA** in normal operation, engineering value represents **fan RPM** (scale per job in import).
- **Interlock:** Electric heat is only allowed when the inferred or scaled **fan airflow / speed** is **above 50% of design airflow** (same threshold concept as “design” used elsewhere in the job). Implement as: tach / RPM or converted airflow must exceed **0.5 × design airflow** before heat stages are permitted or before the tool marks the heat test as “allowed.”
- **SAT:** **Supply air temperature** as an **analog input** (object details per import).

_(Add more profiles: cooling-only, gas heat, different fan proof, etc., as separate bullets or linked profile names.)_

## Job model

- **Many controllers** per job (single job spans multiple devices from the import).

## Technician sign-off

- **Notes + name** (per step, per test, or per job — refine when you design the UI).
- **Exports for records**: **PDF**, **CSV or XLSX**, and **log data** (raw or structured — define format when implementing).

## Localization and units

- **UI language:** English.
- **Units:** metric; **airflow in L/s** (state any secondary display, e.g. m³/h, if you add it later).

## Licensing

- **MIT License** — see repository root `LICENSE`. Update the copyright year/name there if you want a different legal name than listed.

## Reference hardware (what question 11 meant)

“Reference hardware” = **what physical BACnet controllers** you use on the bench for development and regression.

| Item | Notes |
|------|--------|
| Vendor | Innatech |
| Application | Your custom configurations (document model/firmware revision when you lock a test matrix) |
| Network | BACnet/IP; device identity as supplied in import |

Add **specific model numbers, firmware, and one B/IP address + Device ID** per bench controller when available.

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

- **Heat-rise → airflow:** confirm exact **formula variant** (sensible only vs mixed, latent ignored?), **staging** of electric heat (kW per step), and **minimum fan / maximum SAT** limits during auto modulation.
- **Import file format:** still **undefined** — needs schema for: controller list, **equipment profile** (unit type), BACnet object instances for SAT/RAT/heater command/capacity/fan tach, **mA→RPM→airflow** scaling, **design airflow (L/s)**, test definitions, and **test mode** invocation (which object/property to write).
- **50% threshold:** confirm whether the interlock compares **RPM**, **estimated airflow from heat rise**, or a **dedicated airflow AI** when present on other profiles.
- **“RAT” wording:** confirm **return air temperature** (for ΔT with SAT) vs any profile that uses **return fan speed** or other return-side signals—modulation target is assumed to be **supply fan / airflow** unless the import says otherwise.
- **PDF / XLSX stack:** libraries acceptable for FOSS + Windows portable build (XLSX often pulls in a spreadsheet dependency).
- **Log format:** binary, JSON lines, CSV, or rotating text; retention on disk.
