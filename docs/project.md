# BACnet commissioning assistant — project record

Audience: future you. Update when intent, behavior, or exports change.

## Project maturity snapshot (2026-04-28)

- Repository state: **documentation plus Python CLIs** (`tools/`: simulator list verification, import compiler with **duplicate BACnet/IP endpoint warnings** and **unknown CSV column** warnings per **ADR 0011**, plus optional **`bacnet_object_<logical_id>`** per-row **BACnet instance** overrides and **`rat_temperature_proxy`** validation warnings, **`tools/import/benchmark_compile.py`** for synthetic **large-sheet** compile timing, runtime commissioning helpers including **validate-import** dry compile, **print-job-graph** (per-controller **skip_gated_steps** / **modulation_action_steps** counts from compiled flow), **flow/session inspection**, **`commissioning-guided-next`** (compact JSON after **`init-flow`** with **`suggested_cli_commands`** + **`blocked_reasons`** per step), **`commissioning-airflow-closed-loop-iterate`** (optional profile **`closed_loop`** on **`automatic_airflow_adjustment`**), **`operator-gui`** + **`tools/operator_gui_server.py`** (local browser UI: **`/guided`** graphical flow + **`/`** advanced allowlisted CLI form), **run summary export** + optional **CSV**, **audited flow re-init**, **BACnet façade** [`tools/bacnet/adapter.py`](../tools/bacnet/adapter.py), **profile allowlisted BACnet read/write**, **`point_checkout`** batch reads, CLI flags **`--apdu-timeout`** / echoed **`bacnet_timeouts`** in artifacts, **record-step** policy (point checkout gate, **skip_when** session gate for skips, optional **modulation sweep** on pass), and **`bacnet-modulation-sweep`** with **multi-setpoint** and **session RAT** fallback). **Reporting:** **`export-commissioning-report`** unified integrator table (**`--output-html`** may embed **SVG** modulation charts from sweep + **`ai_sat`** reads); optional **customer** **`--output-customer-html`** / **`--output-customer-pdf`** (customer PDF: **cover + table + notes**); **`--output-xlsx --xlsx-include-modulation`** adds a **`modulation`** sheet. **Windows:** optional **PyInstaller** single-file **`bacnet-commissioning.exe`** ([`docs/packaging/windows-exe.md`](packaging/windows-exe.md), **ADR 0012**); CI may **Authenticode-sign** when repository secrets are configured. **ADRs 0009–0011** lock **v1 stack** (Python CLI), **reporting libraries** (stdlib + openpyxl + fpdf2), and **`site-controllers` v1 columns** ([`docs/schema/site-controllers-v1.csv.md`](schema/site-controllers-v1.csv.md)). **Unit tests** include a **loopback BACnet fake peer** (BACpypes3-shaped frames) exercising **`bacnet-read`**, **`dry-run-bacnet-write --execute`**, **`bacnet-point-checkout`**, and modulation paths without field hardware.
- This document is the source of truth for product intent; align runnable steps with [`README.md`](../README.md).
- Active implementation roadmap lives in: [`docs/plans/2026-04-21-v1-foundation-plan.md`](plans/2026-04-21-v1-foundation-plan.md). **Post–baseline sequencing** (UI, reports, closed-loop airflow; **Tier C** BBMD/COV/macvlan lab shipped **2026-04-25**): [`docs/plans/2026-04-28-post-v1-ui-airflow-reports-bacnet-lab.md`](plans/2026-04-28-post-v1-ui-airflow-reports-bacnet-lab.md).
- **Unified commissioning export contract:** [**ADR 0014**](adr/0014-unified-commissioning-report-export-contract.md) and [**`docs/schema/commissioning-report-unified-csv-v1.md`**](schema/commissioning-report-unified-csv-v1.md) (**generated** from `COMMISSIONING_REPORT_UNIFIED_FIELDNAMES` via **`tools/schema/gen_commissioning_report_unified_csv_doc.py`**).

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

## BACnet runtime assumptions (Python CLI)

These notes apply to the **current** `tools/runtime/app.py` BACnet helpers (`probe-bip`, `bacnet-read`, **`bacnet-read-batch`**, `bacnet-point-checkout`, `dry-run-bacnet-write` with `--execute`). All of those go through **`CommissioningBACnetAdapter`** in [`tools/bacnet/adapter.py`](../tools/bacnet/adapter.py) (facade over the minimal UDP probe module and BACpypes3 client). They are **not** a substitute for site network design; they explain what the code assumes today.

- **Transport:** BACnet/IP **UDP** to the **host:port** on each controller row after `compile-import`. There is **no MS/TP, no BACnet/SC** in the commissioning façade. **Normal** reads/writes use directed **Who-Is** to the configured address (no workstation BBMD registration). Optional **lab** topology (**`bacnet-bbmd-lab`** Docker profile + **`tools/simulator/docker_bbmd_lab_smoke.sh`**) exercises **foreign-device** forwarding via a BBMD; see **ADR 0015**. **SubscribeCOV** (**`bacnet-subscribe-cov`**) and **batched writes** (**`bacnet-write-batch --execute`**) and **batched reads** (**`bacnet-read-batch`**, default ReadPropertyMultiple) extend the façade but still target the row’s **host:port** (not a spreadsheet BBMD column).
- **Directed discovery:** Before ReadProperty / WriteProperty, the BACpypes3 path issues **Who-Is** with **low_limit = high_limit = expected device instance** toward the **configured address** (not a global broadcast sweep). If the device does not answer, reads and writes stop with **no I-Am** / probe failure rather than guessing a target.
- **Timeouts (commissioning façade):** Who-Is wait for BACpypes3 reads/writes is **`max(3s, timeout_seconds × retries)`** where `timeout_seconds` / `retries` come from the CLI (`bacnet-read`, **`bacnet-read-batch`**, `bacnet-point-checkout`, `dry-run-bacnet-write --execute`). Confirmed Read/WriteProperty APDU timeout defaults to **8s** (`CommissioningBACnetAdapter.COMMISSIONING_APDU_TIMEOUT_SECONDS`); override per command with **`--apdu-timeout`** (must be a finite number **> 0**). Resolved values are echoed under **`bacnet_timeouts`** in read artifacts and write-plan JSON after execute.

## Commissioning report (v1 slice)

- **File:** `artifacts/commissioning_report.json` (append-only JSON document: `schema_version`, `job_id`, `entries[]`). New runs use **`schema_version` `0.2-commissioning-report`** when modulation entries are added; older files may still show `0.1` until the next append.
- **Population:** When **`record-step`** records **`passed`** or **`manual_passed`** and the step has **`step_type: bacnet_point_checkout`** or **`run_point_checkout_on_pass: true`**, the runtime runs **`point_checkout`** BACnet reads **before** persisting the step. If any read fails, **`record-step` exits 2** and the step stays at its prior status. On success, an entry with **`kind: point_checkout_after_step`** is appended (includes **`report_ref`** when set on the profile step, read summary, artifact path to timestamped **`bacnet_point_checkout/*.json`**). **`commissioning-record-manual-airflow`** appends **`kind: manual_airflow_measurement`** (`branch_id`, `session_key`, `measured_flow_L_s`, `measurement_tool`, optional `design_flow_L_s`, technician + note). **`commissioning-confirm-tachometer-reference`** appends **`kind: tachometer_reference_confirmation`** (`read_object_id`, `reading_value_str`, `session_key`). **`commissioning-airflow-adjust-write`** appends **`kind: airflow_adjust_command`** (`actuator_object_id`, `command_percent`, `target_flow_ratio_of_design`, optional `design_supply_airflow_L_s` from **`commissioning_meta.unit_specs`**). **`commissioning-confirm-prompt`** (CHW valve stroke) appends **`kind: valve_prompt_confirmation`** (`prompt_id`, `session_key`, `command_object_id`, `command_percent`).
- **Skip gating (CHW readiness slice):** Profile steps may list **`skip_when`** (string codes). For **`record-step --status skipped`**, if the step is **`skippable`** and **`skip_when`** is non-empty, the runtime requires **`set-session-value`** on **at least one** listed key with a **truthy** string (`true`, `1`, `yes`, …) so “skip cooling because CHW is not ready” is explicitly recorded before the skip is accepted. Rejected attempts log **`flow_step_rejected`** with reason **`SKIP_GATE`**.
- **Thermal modulation (operator / script slice):** **`append-commissioning-modulation-sample`** performs one or more allowlisted **`bacnet-read`** operations and appends **`kind: thermal_modulation_sample`** with **`readings[]`** (`object_id`, `property`, `status`, `value_str`). **`append-commissioning-modulation-batch`** reads a JSON list of samples (each with `controller_label`, `reads` as strings or `{object_id, property}`) and appends a single **`thermal_modulation_batch`** entry. **`bacnet-modulation-sweep`** (requires **`init-flow`** first) loads the profile step’s **`modulate_actuator_log_sat_for_report`** action from compiled **`commissioning_flow`**: writes **`command_object_id`** present-value (**`Real`** for analog AV/AO; **`Unsigned`** for MSV), dwells, then reads SAT, optional RAT (BACnet when resolvable, else **`session_return_air_temperature_key`** from session state), and **`optional_context_object_ids`**; **`--command-percents`** runs multiple writes with one **`thermal_modulation_sweep`** entry each. The same sweep runs from **`record-step`** on pass when the step defines the action (**`--modulation-command-percents`** required, or **`--no-run-modulation-on-pass`** to skip).
- **Export:** **`export-commissioning-report`** prints the file or copies it with **`--output-json`**. **`--output-csv`** writes flattened **`thermal_modulation_*`** rows (timestamp, controller, step/report refs, per-object read status/value, optional **`read_source`** for BACnet vs session on sweep rows). **`--output-csv-unified`** writes one CSV across **`point_checkout_after_step`**, **`manual_airflow_measurement`**, **`tachometer_reference_confirmation`**, **`airflow_adjust_command`**, **`valve_prompt_confirmation`**, and all thermal modulation kinds (shared columns; sweep extras: **`step_status`**, **`all_read_ok`**, **`artifact_json`**, **`sweep_index`**, **`trigger`**, etc., left blank when not applicable; manual-airflow extras: **`measurement_branch_id`**, **`measured_flow_L_s`**, **`measurement_tool`**, **`design_flow_L_s`**; tachometer row uses **`object_id`** / **`value_str`** / **`read_source`**; airflow-adjust uses **`command_object_id`** / **`command_percent`** plus **`target_flow_ratio_of_design`** and **`design_supply_airflow_L_s`**; **`session_key`** is set for tachometer + manual-airflow rows; valve prompt rows set **`prompt_id`**, **`command_object_id`**, **`command_percent`**, **`value_str`** `confirmed`). **`--output-html`** writes the same unified rows as a simple **printable HTML** table (open in a browser, **Print → Save as PDF**; no extra Python dependencies). **`--output-xlsx`** writes the same unified rows to a workbook (sheet **`commissioning`**; requires **`openpyxl`**). **`--output-pdf`** writes a **server-side** landscape PDF table of the same unified rows (requires **`fpdf2`**). PDF header image: **`--pdf-logo-image`**, else **`<run-dir>/artifacts/branding/logo.png`** ( **`init-run`** copies the neutral **`docs/examples/branding/commissioning-logo-placeholder.png`** there when missing so PDFs work out of the box), else the **same** bundled placeholder path, else a minimal **vector** “site logo” box. With **`--allow-empty`**, you may write empty **JSON stub** and/or **headers-only CSV** / **empty HTML** / **header-only XLSX** / **minimal PDF** when the report file does not exist yet (at least one output path flag must be set).
- **Binding:** The client binds **`0.0.0.0:<bacnet_bind_port>`** (default **0** = ephemeral). Multi-homed hosts and **host firewalls** can block replies or change source address selection; operators may need to open **UDP 47808** (or the site port) inbound/outbound and align subnets with the panel vendor’s guidance.
- **Safety:** Writes are limited to **`commissioning_write_allowlist`** and profile **`writable`** objects; reads use **`commissioning_read_allowlist`**. This is **not** full “per commissioning mode” interlocks—that remains product/policy work on top of the allowlists.

### BACnet failure handling (operator-visible)

CLI and JSON artifacts use a small set of **terminal statuses** (see also artifact JSON under `artifacts/bacnet_reads/`, `artifacts/bacnet_write_plans/`, `artifacts/bacnet_point_checkout/`).

| Status (examples) | Meaning |
|--------------------|--------|
| `reachable_verified` / `identity_mismatch` / `unreachable_timeout` | Outcome of the **minimal Who-Is / I-Am probe** (`probe-bip`, dry-run write probe, or the probe step inside read/write). |
| `blocked_probe_failed` | Read or write did not proceed because **no matching I-Am** (or probe not verified) for the expected device instance. |
| `config_error` | Profile or compiled job issue **before** BACnet (e.g. empty allowlist, object id not on allowlist, missing `objects_by_id`). |
| `read_ok` / `write_ok` | BACnet service completed as expected (write may be **simple ack**). |
| `read_rejected` / `write_rejected` | Device returned a BACnet **error, reject, or abort** (string captured in the artifact). |
| `read_failed` / `execute_failed` / `client_load_failed` | Local exception, timeout waiting for the stack, or **bacpypes3 not installed** (`pip install -r requirements.txt`). |

Structured **audit lines** continue to append to `logs/events.jsonl` for each command invocation (with optional size-based rotation to `events.jsonl.N`; see **ADR 0017**).

## Commissioning scope (v1 capabilities described so far)

1. **Point checkout** — read / command / verify per imported standard-object definitions.
2. **Airflow estimation (electric heat)** — use the **standard heat-rise / sensible-heat** relationship (kW and ΔT family). **Inputs:** **heater command**, **heater capacity**, **supply air temperature (SAT)**, and a **return-air-side temperature** for ΔT. **There is often no BACnet RAT sensor** on site; see [Return air temperature (RAT) sources](#return-air-temperature-rat-sources). **Supply airflow** is **automatically modulated** (e.g. fan speed / VFD within limits in the import) to **approach design**; then **manual verification** of real airflow (L/s) remains the commissioning record.
3. **Manual verification of airflow** — technician confirms measured or inferred airflow against design after the automatic modulation / estimation pass. **Python CLI slice:** **`commissioning-record-manual-airflow`** stores measured **L/s** per profile branch in session (default key **`manual_airflow_measured_<branch_id>_L_s`**; optional per-branch overrides via **`session_keys`** on the **`manual_airflow_verification_assisted`** action). **`record-step --status passed`** on such steps requires those session values; **`--measurement-tool`** must match **`airflow_verification.branches[].measurement.allowed_tools`** when the profile defines them. When the step **`arms_test_mode_state_key`** is **`airflow_verify`**, **MSV state 3** is verified over BACnet before recording.
4. **Assisted airflow balancing** — same job data should support **guided balancing** (which branch to adjust, target vs measured, instrument choice)—see [Import schema (direction)](#import-schema-direction). **Python CLI slice:** **`commissioning-airflow-adjust-write`** writes the profile **`automatic_airflow_adjustment`** actuator (e.g. fan **%**); when the step arms **`airflow_verify`**, **`msv_test_mode`** must read as BACnet state **3** first. **`commissioning-confirm-tachometer-reference`** performs a BACnet read for **`operator_confirm_tachometer_reference.read_object_id`** and sets the profile **`session_key`** to confirmed (**`value`** `true`, reading in **`reading_value_str`**). Optional **`tachometer_reference_session_key`** on the adjustment action (same string as the tachometer step’s **`session_key`**) gates **`record-step passed`** on the adjustment step until that session flag is set. **`compile-import`** copies **`unit_specs`** into each controller’s **`commissioning_meta`** for run-dir context.
5. **Tests** — **Automatic** by default; each must be **skippable** or **manually passable** (override automatic fail or skip when the job demands it).
6. **Cooling valve stroke verify (no plant)** — For units with a **cooling valve**, you always want this **without chilled water** connected: command the valve **to 100%**, have the technician **confirm** travel / end position (or other evidence) via **prompt**, then command **to 0%** and **confirm again**. This proves stroke and direction independent of CHW availability. **Python CLI slice:** after arming **`msv_test_mode`** to **`chw_valve_stroke_no_plant`** (state **6**), run **`commissioning-confirm-prompt`** once per **`prompt_id`** (writes **`ao_chw_valve`** then sets **`session prompt_confirm.<prompt_id>`**); then **`record-step --status passed`** on **`cooling_valve_stroke_no_chw`** (or any step with that **`arms_test_mode_state_key`** and the same action pattern) is accepted only when all required **`prompt_confirm.*`** keys are truthy.
7. **Proper cooling test (CHW)** — When the plant is ready, run a **full cooling / CHW performance** test: **modulate** the **cooling valve** (or profile-defined cooling demand), log **command vs time**, and log **supply air temperature (SAT)** as the **result** signal. If **chilled water is not available yet**, the technician must be able to **skip** this test (with reason recorded) and complete the rest of commissioning; return when CHW is ready to clear the skip or re-run.
8. **Proper heating test** — Same reporting shape as cooling: **modulate** the **heat command** (e.g. **AV 0–100%**), log command over time, and log **SAT** (and any other profile-defined result points) so cause and effect appear together in the **commissioning report** (PDF / CSV / XLSX / logs).

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

- **Operator-entered value** for the session or step (typed in when commissioning) — **this is v1** for FCUs without BACnet RAT.
- **BACnet RAT** when the controller exposes it (see [example profiles](examples/unit-profile-fcu.example.json)).
- **Bluetooth** (or other external probes) — **optional in the product roadmap only; not implemented in v1** (no pairing, no drivers). Keep a **reserved** source in the schema so profiles stay forward-compatible.
- **Cross-unit proxy (idea):** If **HRV commissioning runs first** on a site, an **HRV’s return-air BACnet point** might be used as a **proxy** for space return temperature for nearby FCUs **only** when you explicitly wire that relationship in the job file (same air path / open plan). Treat as **advanced** and easy to get wrong—default remains **manual RAT** unless the import declares the proxy with warnings. **Profile slice:** optional **`rat_temperature_proxy`** (`enabled`, `proxy_controller_label`, `proxy_read_object_id`); **`compile-import`** copies it to **`commissioning_meta`** and warns when the proxy controller or read object is misconfigured (runtime modulation still uses **`session_return_air_temperature_key`** unless you extend the engine to read the proxy point).

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
- **Then reduce speed:** From that proven operating point, **reduce both fan commands by a relative percentage** of their values at half-flow—e.g. **20% relative** means each command becomes **× (1 − 0.20) = 0.80** of what it was at measured half-design (not “minus 20 percentage points” on the AV scale). The **exact percentage is a profile parameter** (15% relative was discussed; **20% relative** is a reasonable default to try in the field).
- **Current switch pickup:** **Adjust the current switch** (field setpoint / sensitivity) so it **just comes on** at this reduced-flow operating point—so the **BI** reliably indicates “fan running” without nuisance trips at idle. The technician confirms **BI active** after the adjustment.
- **No heater** on these units: **no heat-rise test**; **airflow is manually verified** with **tool-assisted balancing** before/after as defined in the import.
- **Heat recovery testing:** HRVs expose **OAT**, **RAT**, **SAT** (and exhaust-side air temp per program). The tool should run **additional tests**: log those sensors at **several paired supply/exhaust fan speeds** (matrix in the import), with optional **calculated effectiveness** when the sensor layout makes a formula **viable**—treat calculations as **advisory** until validated against your core geometry. See [examples/unit-profile-hrv.example.json](examples/unit-profile-hrv.example.json) `heat_recovery_testing`.

_(Add more profiles: CHW-only, other recovery layouts, gas heat, etc.)_

## Import schema (direction)

Schema is still being designed; it must carry **everything needed to commission one unit type** without hard-coded site knowledge in code:

- **BACnet object map** — instances, types (AI/AV/AO/BI/BV/MSV/…), properties used, COV vs polled, units.
- **Per-unit specifications** — **heater size** (capacity per stage if applicable), **design airflow** (L/s), and for **heat recovery** and similar layouts: **return / exhaust / outdoor** flows as required by that profile.
- **Test mode MSVs** — one MSV (or clear MSV set) per **test category**; **state list** ↔ human-readable test name; safe transitions (e.g. leaving heating test).
- **Airflow verification** — which **measurement tool** applies (pitot traverse rules, balometer, grid, hot-wire, etc.) and how readings map to **pass/fail** or **balancing targets** for **assisted airflow balancing**.
- **Cooling valve (no CHW)** — valve **command object**, **100% then 0%** sequence, and **prompt text** (or checklist) for what the technician must confirm at each end.
- **CHW cooling test (plant)** — pass/fail criteria when CHW is on; **`skippable`** with **recorded reason** when plant is not ready; **report series**: modulated **valve %** + **SAT** + **RAT** vs time (or per step).
- **Heating test** — **report series**: modulated **heat %** + **SAT** + **RAT** vs time (or per step); align columns with cooling for comparable PDF/CSV tables.
- **Interlocks and limits** — thresholds (e.g. 50% design), min/max fan during tests, points that must not be written in certain modes.

Exact file format (JSON, YAML, SQLite job DB, etc.) is TBD; the above is the **information model** the first schema version must implement.

### Site data at scale (~120 controllers) — spreadsheet-first

- **Ideal authoring surface:** one **editable spreadsheet** (CSV or XLSX) with **all columns needed per controller row** (BACnet IP, device instance, `profile_id`, floor/zone labels, object overrides if any, notes). Large sites stay maintainable in Excel/LibreOffice and diff better than hand-edited JSON.
- **Import pipeline:** **spreadsheet → validated internal model** (JSON or DB blob generated on load). The app ships or references **profile JSON** files for unit *types*; the sheet is mostly **instances and addressing**.
- **Config checker and helper:** validate **required columns**, **IP/Device ID uniqueness**, **profile_id exists**, **reachable** (optional ping), **read a small object set** before full job run, and surface **human-readable fixes** (wrong column name, missing port, duplicate row). A **helper** can suggest column headers from a chosen profile template.

### Modulation and pass/fail defaults (refine in one place)

- **Modulation recipes (recommended defaults):** [examples/modulation-recipes.recommended.md](examples/modulation-recipes.recommended.md) — stepped valve and heat sweeps, dwell, stabilization, safety aborts. Profiles may override via `modulation_recipe` when the schema is locked.
- **Pass / fail criteria (recommended defaults):** [examples/pass-fail-defaults.recommended.md](examples/pass-fail-defaults.recommended.md) — cooling/heating direction checks, HRV advisory rules. Profiles override with numeric limits per site.

### BACnet simulation and CI

- **Goal:** heavy **automated simulation and regression** before relying on field panels alone.
- **Shipped slice:** `docker/simulator/` **bacnet-dev** profile — **buildable** BACnet/IP UDP sim (`docker/simulator/bacnet-device/`) with **`SIM_PROFILE`** (`fcu` / `hrv`), **four** published ports on loopback, CI smoke via `tools/simulator/docker_bacnet_smoke.sh` + `docs/examples/site-controllers.docker-bacnet-sim.csv`.
- **Longer-term baseline (spec):** Docker lab with multiple profiles (`ci` / `lab` / `multisubnet`) — see [docs/simulator/README.md](simulator/README.md) “planned” sections.
- **Discovery and verification mode:** list-first, verify-all. The system attempts every imported controller row and emits a terminal status for each row (no silent skip).
- **Strict CI gate:** fail CI when required rows are unresolved, identity mismatched, or missing required points.
- **Design references:** [docs/simulator/README.md](simulator/README.md), [docs/plans/2026-04-21-bacnet-simulator-plan.md](plans/2026-04-21-bacnet-simulator-plan.md), and [docker/simulator/docker-compose.yml](../docker/simulator/docker-compose.yml).

### Build and signing (Windows portable exe)

**Shipped slice:** **PyInstaller** `--onefile` → **`bacnet-commissioning.exe`** (see [**`docs/packaging/windows-exe.md`**](packaging/windows-exe.md) and **ADR 0012**). **Code signing** is optional for v1 (unsigned builds run; **SmartScreen** may show an extra “unknown publisher” step—see **Code signing** in that doc for cost and when to buy a cert); **AV false-positive** mitigation is operator/IT policy for now.

### Example profiles (illustrative JSON)

These files are **starting sketches** (`schema_version: "0.1-example"`). They are not a frozen contract—adjust object types, instance numbers, MSV state maps, and formulas to match your controller programs.

| File | Intent |
|------|--------|
| [examples/unit-profile-fcu.example.json](examples/unit-profile-fcu.example.json) | FCU with optional BACnet **ai_rat**; thermal reports SAT+RAT. |
| [examples/unit-profile-fcu-no-bacnet-rat.example.json](examples/unit-profile-fcu-no-bacnet-rat.example.json) | FCU variant: **no BACnet RAT** — **session-only** `rat_degC` (manual); Bluetooth reserved not implemented. |
| [examples/unit-profile-hrv.example.json](examples/unit-profile-hrv.example.json) | HRV: airflow + current switch; **heat_recovery_testing** (OAT/RAT/SAT at **multiple fan speeds**, optional calculated effectiveness). |
| [examples/site-controllers.template.csv](examples/site-controllers.template.csv) | Minimal **one-row-per-controller** columns for large sites; expand with profile-specific columns as the checker matures. |
| [examples/modulation-recipes.recommended.md](examples/modulation-recipes.recommended.md) | Default **modulation** sweeps and dwells — **edit here first**. |
| [examples/pass-fail-defaults.recommended.md](examples/pass-fail-defaults.recommended.md) | Default **pass/fail** thresholds — **edit here first**. |

## Job model

- **Many controllers** per job (single job spans multiple devices from the import).

## Technician sign-off

- **Notes + name** (per step, per test, or per job — refine when you design the UI).
- **Exports for records**: **PDF**, **CSV or XLSX**, and **log data** (raw or structured — define format when implementing).

### Reports — heating and cooling tests

**Cooling** and **heating** performance tests must appear **in the report** with the same idea: what was **commanded** (valve or heat **modulated** over a profile-defined sweep or steps) and what happened to **supply air temperature (SAT)** as the primary **result**. Include **return air temperature (RAT)** in the **same time- or step-series** when available: **BACnet RAT** object in the profile, or **manual / Bluetooth** values carried in the session and written into the same table rows (so every row has SAT and RAT columns even if RAT is operator-entered). Also allow timestamps (or step index), actuator **%**, and secondary columns from the import (fan %, outdoor air, etc.). The valve **stroke-without-CHW** check remains a separate line item (end stops only); the **modulation + SAT (+ RAT)** block is the substantive **cooling test** / **heating test** for the customer record.

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

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Runtime commands (init-run through export-run-summary, record-step, simulator/BIP checks): [`README.md`](../README.md).

## Definition of done (reuse)

- [ ] Behavior matches this doc for the slice you shipped.
- [ ] Verification command(s) pass (or N/A documented).
- [ ] This doc updated if exports, BACnet assumptions, test rules, or sign-off changed.
- [ ] Commit message states the behavioral change.

## Remaining to plan (before implementation)

These are the main gaps once requirements feel “complete enough” to start coding:

- **Spreadsheet column spec** — **v1 required/optional core** is frozen in [**`docs/schema/site-controllers-v1.csv.md`**](schema/site-controllers-v1.csv.md) and **ADR 0011**; **per-row BACnet object instance** overrides use **`bacnet_object_<logical_id>`** columns. Full **120+ controller** sheet ergonomics / performance targets and richer overrides (object type, properties) remain backlog.
- **Sheet → runtime compiler** — **shipped baseline** in `tools/import/compile_job.py` + `compile-import` / `validate-import`; **`tools/import/benchmark_compile.py`** for synthetic timing. **Large-sheet SLO (informal, dev laptop, CPython 3.12):** compile-only `compile_model` should stay **under ~2s for 500 rows** and **under ~10s for 2000 rows** as an order-of-magnitude guard (re-run after major compiler changes); CI runs **`--rows 120`** only.
- **HRV effectiveness equation** — lock **sensor placement** vs math for each program version; until then keep **advisory** only.
- **RAT proxy rules** — optional profile **`rat_temperature_proxy`** (`enabled`, `proxy_controller_label`, `proxy_read_object_id`); **`compile-import`** warns on unknown controller / missing read allowlist; metadata under **`commissioning_meta.rat_temperature_proxy`** (runtime use still profile-driven).
- **Tauri desktop operator** — optional **`desktop/tauri-operator/`** app (see **`docs/packaging/tauri-operator-desktop.md`**) for a packaged window around the Python CLI; **`rust-toolchain.toml`** pins stable for CI/agents.
- **Report layout** — PDF section order, logo/branding, one table vs multiple charts; **CSV vs XLSX** column order frozen for integrators.
- **Structured log** — append-only **JSON Lines** at `logs/events.jsonl` per run-dir; **size-based rotation** with defaults in `config/runtime-config.json` → **`events_log`** (`rotate_max_bytes`, `retention_files`) and optional env **`COMMISSIONING_EVENTS_MAX_BYTES`** / **`COMMISSIONING_EVENTS_RETENTION_FILES`** (**ADR 0017**). Archives: `logs/events.jsonl.1`, `.2`, …
- **Docker BACnet sim (beyond bacnet-dev)** — **`bacnet-bbmd-lab`** + optional **macvlan** overlay shipped (**ADR 0015**, `docs/simulator/macvlan-lab.md`); **orchestrator-in-container** multi-site topology still optional.
- **BACnet stack** — **PyInstaller exe** baseline shipped; **COV subscribe**; **`bacnet-write-batch`** with **`--mode sequential`** or **`--mode multiple`** (WritePropertyMultiple, lab-sim tested); **`bacnet-read-batch`** with **`--mode multiple`** (ReadPropertyMultiple) or **`--mode sequential`**; **`bacnet-point-checkout`** batches with **ReadPropertyMultiple** when two or more points resolve (**ADR 0016**; opt-out flags on CLI); richer **sweep-timeouts** still optional.
- **Build and signing** — still **TBD** (toolchain, certificate, release channel).

## Open questions

- **Heat-rise → airflow:** confirm exact **formula variant** (sensible only vs mixed, latent ignored?), **staging** of electric heat (kW per step), and **minimum fan / maximum SAT** limits during auto modulation.
- **RAT workflow:** **manual entry** for v1 on FCUs without BACnet RAT; **Bluetooth** schema slot only — no implementation; **HRV RAT proxy** for FCUs — only if explicitly declared in job; for **reports**, how often to prompt for RAT during a long modulation sweep (each step vs start/end only).
- **MSV contracts:** canonical **state numbers** per test type across profiles, or fully profile-local only?
- **Half-design reference:** optional hysteresis when comparing **live tachometer value** to the **session-stored** value captured after auto-adjust + operator confirm.
- **Bluetooth / external sensors:** deferred — pairing, calibration, audit trail (who accepted which reading).
- **PDF / XLSX stack:** **locked for v1** — **openpyxl** (XLSX), **fpdf2** (PDF table); see **ADR 0010** and `requirements.txt`.
- **Log format:** binary, JSON lines, CSV, or rotating text; retention on disk.
