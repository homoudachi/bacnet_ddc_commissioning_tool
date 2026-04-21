# BACnet commissioning assistant — project record

Audience: future you. Update when intent, behavior, or exports change.

## Goal

Windows **portable executable** that acts as a **commissioning assistant** for **BACnet-capable** controllers: command devices, run **automatic tests**, monitor results, and combine **automatic judgment** with **technician verification** (notes + name). Supports **many controllers** per job via an **imported target list**.

## Controllers and configuration

- **Hardware:** Any **BACnet-capable** controller that matches the imported object map (no vendor lock-in in the product description).
- **Application logic:** Configurations **authored by you** (or your team); the tool talks **standard BACnet**—inputs and outputs appear as **BACnet objects** on the network.
- **Test / override mode:** For each **class of test**, the controller exposes a **Multi-state Value (MSV)** that selects that test mode (examples: **fan tachometer verification**, **airflow verification**, **heating test**, **chilled-water (CHW) test** when plant is available, **cooling valve stroke without CHW**, and additional types as you add them). Writing the MSV is how the assistant arms the controller logic for that commissioning scenario; exact **state numbers ↔ meanings** live in the **import** per unit profile.

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
6. **Cooling valve stroke verify (no plant)** — For units with a **cooling valve**, you always want this **without chilled water** connected: command the valve **to 100%**, have the technician **confirm** travel / end position (or other evidence) via **prompt**, then command **to 0%** and **confirm again**. This proves stroke and direction independent of CHW availability. Full **CHW performance** tests remain separate when the plant is ready.

## Commissioning UX: predictable, seamless steps per unit

Each **equipment profile** defines an ordered **commissioning flow** (same steps in the same order for every unit of that type) so technicians always know what comes next. Where **half-design airflow** matters (for example before enabling electric heat), the flow is **one continuous path**, not disconnected screens:

1. **Automatic airflow adjustment** — tool drives the **fan speed AV (0–100%)** (and any other declared actuators) toward the **0.5 × design** airflow target using the profile’s measurement rules.
2. **Confirm tachometer reference at that operating point** — when flow is correct per the tool, the technician **confirms** the **tachometer value** read from BACnet (see [Tachometer value](#tachometer-value-not-rpm)); that value is **stored for the session** as the reference for interlocks and checks.
3. **Manual airflow verification** — technician performs the real-world measurement (L/s); assisted balancing UI stays in the same narrative.
4. **Downstream tests** (e.g. heating) only proceed when prior steps are satisfied, using the **confirmed** half-flow tachometer reference—not a guessed RPM curve.

Steps, targets, and which MSV state arms each segment live in the **import**.

## Tachometer value (not “RPM”)

The field device is often a **pulse** train; the controller exposes an **Analog Value** (or similar) we call the **tachometer value** (informally **tacho value**). It may **correlate** with speed but **engineering units are not assumed to be RPM**—scaling and meaning are **profile-defined**. Interlocks and “half flow” references compare **this BACnet value**, not a hard-coded RPM.

## Analog commands (0–100%)

- **Supply (and exhaust, if applicable) fan speed:** written as **AV 0–100%** (not only binary fan).
- **Variable electric heat:** **0–100% on an AV** (modulating heat), not modeled here as simple on/off stages unless a profile explicitly uses discrete stages.

## Return air temperature (RAT) sources

Many units **do not have a RAT BACnet point**. The tool must accept **return-side temperature** from one of:

- **Operator-entered value** for the session or step (typed in when commissioning), and/or
- **External measurement** merged into the workflow—e.g. a **Bluetooth temperature sensor** (or any other handheld) with a defined pairing/read path in software **later**; until implemented, **manual entry** is the fallback.

Document per **equipment profile** which source is valid and required uncertainty (if any).

## Site-specific requirements

**Variation across unit types:** Different units have different I/O, interlocks, and **MSV** test modes. Each **equipment profile** in the import is authoritative—avoid hard-coding one rooftop’s logic into the core app.

### Example — electric heat enable interlock (FCU-style family)

- **Tachometer value:** Pulse at the field; controller exposes an **AV** as **tachometer value** (units per import—not assumed RPM).
- **Half-design airflow gate:** Heat is allowed only after the **seamless workflow** in [Commissioning UX](#commissioning-ux-predictable-seamless-steps-per-unit): automatic adjustment to **~0.5 × design** flow, **operator confirmation** of the tachometer value at that point, and **manual airflow verification**. Thereafter the interlock compares **current tachometer value** to the **stored confirmed reference** (with optional hysteresis in the profile).
- **Heat command:** **AV 0–100%** modulating electric heat per program.
- **SAT:** As defined in the import.

### Example — HRV (no electric heat in profile)

- **Two streams, measured first:** Adjust **supply** and **exhaust (return-side)** fan **AV commands (0–100%)** using **measured** airflow on each branch until each stream is at **half of its design flow (L/s)** (not half of command—**half of design as verified by measurement** in the assisted tool).
- **Then reduce speed:** From that proven operating point, **reduce both fan commands by about 15%** (exact percentage is a **profile parameter**, e.g. 15%, not hard-coded in the app).
- **Current switch pickup:** **Adjust the current switch** (field setpoint / sensitivity) so it **just comes on** at this reduced-flow operating point—so the **BI** reliably indicates “fan running” without nuisance trips at idle. The technician confirms **BI active** after the adjustment.
- **No heater** on these units: **no heat-rise test**; **airflow is manually verified** with **tool-assisted balancing** before/after as defined in the import.

_(Add more profiles: CHW-only, other recovery layouts, gas heat, etc.)_

## Import schema (direction)

Schema is still being designed; it must carry **everything needed to commission one unit type** without hard-coded site knowledge in code:

- **BACnet object map** — instances, types (AI/AV/AO/BI/BV/MSV/…), properties used, COV vs polled, units.
- **Per-unit specifications** — **heater size** (capacity per stage if applicable), **design airflow** (L/s), and for **heat recovery** and similar layouts: **return / exhaust / outdoor** flows as required by that profile.
- **Test mode MSVs** — one MSV (or clear MSV set) per **test category**; **state list** ↔ human-readable test name; safe transitions (e.g. leaving heating test).
- **Airflow verification** — which **measurement tool** applies (pitot traverse rules, balometer, grid, hot-wire, etc.) and how readings map to **pass/fail** or **balancing targets** for **assisted airflow balancing**.
- **Cooling valve (no CHW)** — valve **command object**, **100% then 0%** sequence, and **prompt text** (or checklist) for what the technician must confirm at each end.
- **Interlocks and limits** — thresholds (e.g. 50% design), min/max fan during tests, points that must not be written in certain modes.

Exact file format (JSON, YAML, SQLite job DB, etc.) is TBD; the above is the **information model** the first schema version must implement.

### Example profiles (illustrative JSON)

These files are **starting sketches** (`schema_version: "0.1-example"`). They are not a frozen contract—adjust object types, instance numbers, MSV state maps, and formulas to match your controller programs.

| File | Intent |
|------|--------|
| [examples/unit-profile-fcu.example.json](examples/unit-profile-fcu.example.json) | FCU: MSV modes, **tachometer value AV**, fan **AV 0–100%**, heat **AV 0–100%**, CHW valve **stroke verify without plant** (100% prompt → 0% prompt), RAT manual/Bluetooth, **commissioning_flow** (half-flow chain → heating), interlock uses **stored** half-flow tacho reference. |
| [examples/unit-profile-hrv.example.json](examples/unit-profile-hrv.example.json) | HRV: dual streams, **tachometer value** AVs, fan **AVs 0–100%**; **measured** half-design L/s on supply and exhaust, then **~15% fan command reduction**, then **field-adjust current switch** so **BI just picks up**; **no heat**, assisted + manual airflow. |

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
- **Half-design reference:** optional hysteresis when comparing **live tachometer value** to the **session-stored** value captured after auto-adjust + operator confirm.
- **Bluetooth / external sensors:** pairing, calibration, audit trail (who accepted which reading).
- **PDF / XLSX stack:** libraries acceptable for FOSS + Windows portable build.
- **Log format:** binary, JSON lines, CSV, or rotating text; retention on disk.
