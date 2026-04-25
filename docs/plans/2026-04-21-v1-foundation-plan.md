# V1 foundation plan (docs-first to executable baseline)

## Goal

Move this repository from "requirements and examples only" to a working baseline that can:

1. Load and validate site controller spreadsheets,
2. Simulate and/or connect to BACnet endpoints through a clean adapter,
3. Execute the first commissioning flow slices with auditable results, and
4. Export technician-ready records.

## Current status

- **2026-04-27:** Same baseline as 2026-04-26, plus **`tools/import/benchmark_compile.py`** (synthetic N-row compile timing; CI runs **`--rows 120`**), **`commissioning-guided-next`** CLI (compact flow JSON after **`init-flow`**), **Docker bacnet-dev** fourth FCU sim (**`47811`**, **`FCU-DOCKER-C`**) + smoke/assertion updates, **`export-commissioning-report --output-customer-html`** / **`--output-customer-pdf`** (thermal modulation–only customer table + striped unified HTML), optional **Authenticode** step in **windows-exe** workflow via **`tools/packaging/sign_windows_exe.ps1`** when secrets are set. Remaining v1 gaps: **full graphical guided UI**, **rich customer PDF templates** (beyond tabular exports), **closed-loop auto airflow** to measured L/s, **BBMD/macvlan** lab. See `README.md` and `docs/project.md`.
- **2026-04-28:** Sequenced backlog for those gaps (easier items first; **BBMD deferred**): [`docs/plans/2026-04-28-post-v1-ui-airflow-reports-bacnet-lab.md`](2026-04-28-post-v1-ui-airflow-reports-bacnet-lab.md). **Tier A (partial):** unified **`--output-html`** embeds **SVG modulation charts** (sweep command % vs `ai_sat`); **`--output-customer-pdf`** adds **cover + notes** pages; **`--output-xlsx --xlsx-include-modulation`** adds **`modulation`** sheet; **`commissioning-guided-next`** returns **`suggested_cli_commands`** + **`blocked_reasons`** per step; **`docs/project.md`** documents informal **500 / 2000 row** compile SLOs via `benchmark_compile.py`.
- **2026-04-28 (Tier B):** **`commissioning-airflow-closed-loop-iterate`** (profile **`closed_loop`** on **`automatic_airflow_adjustment`**); **`operator-gui`** + **`tools/operator_gui_server.py`** (local browser UI, allowlisted CLI subprocesses); profile **`rat_temperature_proxy`** + compile warnings + **`commissioning_meta`** copy.
- **2026-04-28 (Tauri):** **`desktop/tauri-operator/`** Tauri 2 operator shell + **`docs/packaging/tauri-operator-desktop.md`**, **`rust-toolchain.toml`**, CI **`.github/workflows/tauri-operator.yml`** (Linux `.deb` + Windows **NSIS** `.exe` artifacts; **macOS `.dmg`** and **signed NSIS** deferred—see post-v1 plan). Rust binary **`bacnet-commissioning-operator`**.
- Product intent is tracked in `docs/project.md`.
- This plan remains the high-level execution sequence; treat unchecked items as backlog unless superseded by newer ADRs. **Checklist:** `[x]` = shipped enough for baseline; notes in-line mark partials.

## Recommended sequencing (authoritative)

Use this order to reduce rework and unblock parallel work later.

### Phase 0 — lock critical decisions first

- [x] Create ADR: implementation stack and packaging target — **ADR 0009:** Python 3 CLI baseline for v1; **Windows portable exe** packaging/signing still TBD (`docs/project.md`).
- [x] Create ADR: internal job model and file format — **partial:** runtime **`state/runtime-job.json`** + import report contract documented via compiler + examples; formal ADR for long-lived schema versioning still optional.
- [x] Create ADR: reporting stack (PDF + CSV/XLSX library choices) — **ADR 0010:** stdlib CSV/HTML, **openpyxl** XLSX, **fpdf2** PDF for unified commissioning export; long-lived integrator schema ADR still optional.
- [x] Freeze "required columns" for `site-controllers` spreadsheet v1 — **ADR 0011** + **`docs/schema/site-controllers-v1.csv.md`**; compiler warns on unknown headers; **120+ row** performance / extended column set still open.
- [x] Freeze v1 pass/fail default fields that must appear in every profile — **partial:** **`docs/examples/pass-fail-defaults.recommended.md`** now includes a **v1 profile contract** checklist; numeric thresholds remain **profile-authored** for production.

**Deliverables**

- ADRs in `docs/adr/`
- Updated `docs/project.md` sections where TBD/open questions become decisions
- One canonical spreadsheet schema table in docs

### Phase 1 — bootstrap runtime and quality gates

- [x] Create app skeleton (CLI + package structure + config loading + structured logging) — `tools/runtime/app.py`, `config/`, `logs/events.jsonl`.
- [x] Add test harness and CI checks — **unittest** in CI (`.github/workflows/simulator-verification.yml`); dedicated **format/lint** matrix still optional.
- [x] Add golden fixtures from `docs/examples/*.json` and `docs/examples/site-controllers.template.csv`.
- [x] Add a no-network "dry run" command that validates import and prints unit/test graph — **`validate-import`**, **`print-job-graph`**.

**Deliverables**

- Runnable developer entrypoint
- CI passing on every push
- Documented local run commands in `README.md` and `docs/project.md`

### Phase 2 — import compiler and validation UX

- [x] Implement spreadsheet parser and validator — **in repo** (`tools/import/compile_job.py`); **120+ row** performance / stress harness not yet dedicated.
- [x] Enforce uniqueness/consistency checks — device instance, ports, profiles, **duplicate BACnet IP:port** warnings, etc.; expand as new columns ship.
- [x] Produce normalized internal job model and human-readable validation errors — `runtime-job.json` + `import-report.json`.
- [x] Add import report output (warning/error summary for commissioning leads).

**Deliverables**

- Deterministic import output (JSON artifact or equivalent runtime snapshot)
- Validation tests with known bad-sheet fixtures
- Updated examples and docs for schema/versioning

### Phase 3 — BACnet adapter + simulator-first development

- [x] Implement BACnet abstraction layer (read/write/subscribe/timeouts/retry policy) — **v1 slice:** stable façade [`tools/bacnet/adapter.py`](../bacnet/adapter.py) (`CommissioningBACnetAdapter`) used by the runtime CLI for probe + present-value read/write; **subscribe** and richer retry policy remain future work.
- [x] Add simulator-backed integration tests for core read/write and mode transitions (loopback fake BACnet peer in `tests/test_runtime_cli.py` exercises `bacnet-read`, `dry-run-bacnet-write --execute`, and `bacnet-point-checkout` against BACpypes3-shaped frames).
- [x] Add commissioning safety constraints (write allowlist, per-mode restrictions, abort rules) — **v1:** profile **`commissioning_write_allowlist`** / **`commissioning_read_allowlist`** + **`writable`** in job model; **per-mode / sweep abort rules** not encoded in CLI yet.
- [x] Document network assumptions and expected failure handling behavior (see [`docs/project.md`](../project.md#bacnet-runtime-assumptions-python-cli)).

**Deliverables**

- Stable adapter interface usable by commissioning flow engine — **yes** (`CommissioningBACnetAdapter`).
- CI integration suite using simulator containers or mock devices — **partial:** list verifier + **loopback BACnet fake** in unittest; **Docker BACnet sim** — **`docker/simulator/`** `bacnet-dev` profile (**four** UDP ports: three FCU-shaped + one **HRV**-shaped via `SIM_PROFILE=hrv`) + CI **`verify-bip-list --strict`** smoke (`tools/simulator/docker_bacnet_smoke.sh`, includes **`bacnet-subscribe-cov`** + **`bacnet-write-batch`** sequential + **`--mode multiple`**). Optional **`bacnet-bbmd-lab`** + `docker_bbmd_lab_smoke.sh` exercises BBMD/foreign-device path (**ADR 0015**). Full orchestrator-in-container topology still optional.
- First operator-visible diagnostic logs for comms failures — **partial:** JSON artifacts + `events.jsonl`; richer comms diagnostics TBD.

### Phase 4 — commissioning flow engine (v1 slices)

- [x] Implement point checkout flow — **v1:** **`bacnet-point-checkout`** CLI; **`record-step`** can run the same reads when a profile step uses **`step_type: bacnet_point_checkout`** or **`run_point_checkout_on_pass`**; results append **`artifacts/commissioning_report.json`**; **guided UI** still future.
- [x] Implement airflow adjustment + technician confirmation checkpoints — **v1:** **`commissioning-airflow-adjust-write`** (WriteProperty on profile **`automatic_airflow_adjustment`** actuator; when step **`arms_test_mode_state_key`** is **`airflow_verify`**, requires **`msv_test_mode`** state **3** first), **`commissioning-confirm-tachometer-reference`** (BACnet read + session flag for **`operator_confirm_tachometer_reference`**); optional **`tachometer_reference_session_key`** on the adjustment action gates **`record-step passed`** until confirmed; **`commissioning_meta.unit_specs`** copied from profile for operator context (e.g. design airflow). **Not** closed-loop auto modulation to measured L/s.
- [x] Implement cooling valve stroke test (no CHW) with mandatory human confirmation records — **v1:** **`commissioning-confirm-prompt`** re-writes **`ao_chw_valve`** for each **`operator_prompt_confirm`** after a **`write_analog_percent`** on that object, sets **`session prompt_confirm.<prompt_id>`**; **`record-step passed/manual_passed`** on **`cooling_valve_stroke_no_chw`** or steps with **`arms_test_mode_state_key: chw_valve_stroke_no_plant`** requires those session flags ( **`PROMPTS_NOT_CONFIRMED`** if missing). **Not** full UI prompts.
- [x] Implement heating/cooling modulation test scaffolds with skippable/manual-pass controls — **partial:** **`bacnet-modulation-sweep`** (multi **`--command-percents`**, session RAT via **`session_return_air_temperature_key`**) + optional **`record-step`** sweep on pass; **`skip_when`** + session truthy gate for **`record-step skipped`**; **`print-job-graph`** surfaces **`skip_gated_steps`** / **`modulation_action_steps`**; **`commissioning-record-manual-airflow`** + **`record-step`** gate for **`manual_airflow_verification_assisted`** (measured L/s per branch); **`compile-import`** copies **`airflow_verification`** into **`commissioning_meta`**. **Not** full guided step engine / skip UI.

**Deliverables**

- Executable per-profile step engine
- Persisted step/test state with technician name + notes
- Regression tests for skip/manual pass/abort and interlock behavior

### Phase 5 — reporting and Windows distribution

- [x] Implement report model for unified heating/cooling output tables (SAT + RAT + command + time/step) — **partial:** unified export already carries modulation **command** + per-read **SAT/RAT** (and **`read_source`**); **`manual_airflow_measurement`** rows now join the same **CSV/HTML/XLSX/PDF** table with **L/s** + branch + tool for assisted airflow verification. **Customer-facing** narrow **HTML/PDF** for **modulation-only** rows (**`--output-customer-html`** / **`--output-customer-pdf`**). Full **charting** / branded PDF templates still open.
- [x] Export CSV first — **partial:** **`export-run-summary --output-csv`** (controller × flow status rollup); **not** yet the unified modulation table contract.
- [x] **Partial:** append-only **`export-commissioning-report`** / **`artifacts/commissioning_report.json`** for **point checkout after step**, **CLI-appended thermal modulation samples/batches**, **`bacnet-modulation-sweep`** / optional **`record-step`** sweep rows (**`thermal_modulation_sweep`** with BACnet vs session **`read_source`** in CSV), **manual / tachometer / airflow / valve** checkpoint kinds. **`export-commissioning-report --output-csv-unified`** flattens all into one CSV (**ADR 0014** + **`docs/schema/commissioning-report-unified-csv-v1.md`**). **Not** yet styled customer PDF tables.
- [x] Then PDF/XLSX from same normalized dataset — **partial:** **`export-commissioning-report`** **`--output-html`**, **`--output-xlsx`**, **`--output-pdf`** on the unified row model (**ADR 0010**); CI smoke **`tools/simulator/commissioning_export_smoke.sh`**. **Not** yet styled customer PDF templates or charts.
- [x] Package portable Windows executable — **partial:** **PyInstaller** one-file **`bacnet-commissioning.exe`** + [`docs/packaging/windows-exe.md`](packaging/windows-exe.md) + CI artifact workflow; **signing/release checklist** still open.
- [x] Add release checklist and smoke-test matrix — [`docs/packaging/release-checklist.md`](packaging/release-checklist.md).

**Deliverables**

- Customer-shareable report artifacts
- Versioned portable build output
- Release and verification docs

## Decision points where your input is valuable

I can proceed with defaults, but these choices materially affect rework risk:

1. **Implementation stack**  
   Recommended default: **Go** (runtime + import + report backend) with a lightweight desktop shell.  
   Your input helps if you have strong constraints (team familiarity, existing libraries, vendor SDKs).

2. **UI depth in v1**  
   Recommended default: "operator utility UI" (step guidance + confirmations + reports), not polished enterprise UI.  
   Your input helps if customer-facing UX polish is a hard requirement for first deployment.

3. **Report contract priority**  
   Recommended default: freeze CSV column contract first, then mirror to PDF/XLSX.  
   Your input helps if a specific client template must be matched exactly from day one.

4. **Simulator strategy**  
   Recommended default: start with open-source BACnet simulator + deterministic fixtures before live-panel loops.  
   Your input helps if you already rely on a specific simulator or hardware-in-the-loop bench setup.

## If no further input is provided

Proceed with the recommended defaults above, execute phases in order, and treat ADR outputs as the lock points that keep docs and implementation aligned.
