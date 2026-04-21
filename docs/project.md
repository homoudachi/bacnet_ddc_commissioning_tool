# BACnet commissioning assistant — project record

Audience: future you. Update when intent, behavior, or exports change.

## Goal

Windows **portable executable** that acts as a **commissioning assistant** for **BACnet-capable** controllers: command devices, run **automatic tests**, monitor results, and combine **automatic judgment** with **technician verification** (notes + name). Supports **many controllers** per job via an **imported target list**.

## Controllers and configuration

- **Hardware:** Any **BACnet-capable** controller that matches the imported object map (no vendor lock-in in the product description).
- **Application logic:** Configurations **authored by you** (or your team); the tool talks **standard BACnet**—inputs and outputs appear as **BACnet objects** on the network.
- **Test / override mode:** For each **class of test**, the controller exposes a **Multi-state Value (MSV)** that selects that test mode (examples: **fan tachometer verification**, **airflow verification**, **heating test**, **chilled-water (CHW) test**, and additional types as you add them). Writing the MSV is how the assistant arms the controller logic for that commissioning scenario; exact **state numbers ↔ meanings** live in the **import** per unit profile.

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
2. **Airflow estimation (electric heat)** — use the **standard heat-rise / sensible-heat** relationship (kW and ΔT family). **Inputs:** **heater command**, **heater capacity**, **supply air temperature (SAT)**, and a **return-air-side temperature** for ΔT. **There is often no BACnet RAT sensor** on site; see [Return air temperature (RAT) sources](#return-air-temperature-rat-sources). **Supply airflow** is **automatically modulated** (e.g. fan speed / VFD within limits in the import) to **approach design**; then **manual verification** of real airflow (L/s) remains the commissioning record.
3. **Manual verification of airflow** — technician confirms measured or inferred airflow against design after the automatic modulation / estimation pass.
4. **Assisted airflow balancing** — same job data should support **guided balancing** (which branch to adjust, target vs measured, instrument choice)—see [Import schema (direction)](#import-schema-direction).
5. **Tests** — **Automatic** by default; each must be **skippable** or **manually passable** (override automatic fail or skip when the job demands it).

## Return air temperature (RAT) sources

Many units **do not have a RAT BACnet point**. The tool must accept **return-side temperature** from one of:

- **Operator-entered value** for the session or step (typed in when commissioning), and/or
- **External measurement** merged into the workflow—e.g. a **Bluetooth temperature sensor** (or any other handheld) with a defined pairing/read path in software **later**; until implemented, **manual entry** is the fallback.

Document per **equipment profile** which source is valid and required uncertainty (if any).

## Site-specific requirements

**Variation across unit types:** Different units have different I/O, interlocks, and **MSV** test modes. Each **equipment profile** in the import is authoritative—avoid hard-coding one rooftop’s logic into the core app.

### Example — electric heat enable interlock (one program family)

- **Fan tachometer:** Physical signal is a **pulse train**; the **controller conditions it** and exposes a **BACnet Analog Value (AV)** (or equivalent analog) representing **fan speed / RPM** (scaling and units per import).
- **Interlock:** Electric heat is only allowed when **fan proof / speed** is **above 50% of design airflow** (or equivalent scaled signal per import). Implement as: tach-derived signal must exceed **0.5 × design airflow** before heat is permitted or before the tool marks the heat test as “allowed.”
- **SAT:** Supply air temperature point as defined in the import.

_(Add more profiles: CHW-only, heat recovery with **supply + return design flows**, gas heat, etc.)_

## Import schema (direction)

Schema is still being designed; it must carry **everything needed to commission one unit type** without hard-coded site knowledge in code:

- **BACnet object map** — instances, types (AI/AV/AO/BI/BV/MSV/…), properties used, COV vs polled, units.
- **Per-unit specifications** — **heater size** (capacity per stage if applicable), **design airflow** (L/s), and for **heat recovery** and similar layouts: **return / exhaust / outdoor** flows as required by that profile.
- **Test mode MSVs** — one MSV (or clear MSV set) per **test category**; **state list** ↔ human-readable test name; safe transitions (e.g. leaving heating test).
- **Airflow verification** — which **measurement tool** applies (pitot traverse rules, balometer, grid, hot-wire, etc.) and how readings map to **pass/fail** or **balancing targets** for **assisted airflow balancing**.
- **Interlocks and limits** — thresholds (e.g. 50% design), min/max fan during tests, points that must not be written in certain modes.

Exact file format (JSON, YAML, SQLite job DB, etc.) is TBD; the above is the **information model** the first schema version must implement.

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

“Reference hardware” = **BACnet controllers** and **field instruments** you use on the bench and on site for development and regression.

| Item | Notes |
|------|--------|
| Controllers | BACnet/IP devices running your configurations |
| Instruments | TBD: reference balometer / anemometer / Bluetooth temp device for RAT substitute trials |
| Network | BACnet/IP; device identity as supplied in import |

Add **model, firmware, B/IP address + Device ID** per bench controller when you lock a regression set.

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
- **RAT workflow:** default to **manual entry** until Bluetooth (or other) device support exists; define **where** in the job file optional `rat_source: manual | bluetooth | bacnet_object` lives.
- **MSV contracts:** canonical **state numbers** per test type across profiles, or fully profile-local only?
- **50% threshold:** confirm comparison signal (**RPM**, **estimated airflow**, **dedicated flow AV**) per profile.
- **Bluetooth / external sensors:** pairing, calibration, audit trail (who accepted which reading).
- **PDF / XLSX stack:** libraries acceptable for FOSS + Windows portable build.
- **Log format:** binary, JSON lines, CSV, or rotating text; retention on disk.
