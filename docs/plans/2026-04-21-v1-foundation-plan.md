# V1 foundation plan (docs-first to executable baseline)

## Goal

Move this repository from "requirements and examples only" to a working baseline that can:

1. Load and validate site controller spreadsheets,
2. Simulate and/or connect to BACnet endpoints through a clean adapter,
3. Execute the first commissioning flow slices with auditable results, and
4. Export technician-ready records.

## Current status

- **2026-04-25:** Same baseline as 2026-04-24, plus **commissioning_report** hooks for **multi-point `bacnet-modulation-sweep`** (`--command-percents`), **session RAT** via `session_return_air_temperature_key` when BACnet RAT is absent, optional **`record-step`** sweep on pass (`--modulation-command-percents` / `--no-run-modulation-on-pass`), **`skip_when`** + session truthy gate for **`record-step skipped`** (CHW readiness), and **`print-job-graph`** counts **`skip_gated_steps`** / **`modulation_action_steps`** per controller. Remaining v1 gaps: **portable Windows packaging**, **Docker BACnet sim lab**, **full commissioning flow engine** (guided steps beyond CLI slices), **unified heat/cool report model** + PDF/XLSX. See `README.md` and `docs/project.md`.
- Product intent is tracked in `docs/project.md`.
- This plan remains the high-level execution sequence; treat unchecked items as backlog unless superseded by newer ADRs. **Checklist:** `[x]` = shipped enough for baseline; notes in-line mark partials.

## Recommended sequencing (authoritative)

Use this order to reduce rework and unblock parallel work later.

### Phase 0 — lock critical decisions first

- [ ] Create ADR: implementation stack and packaging target (**current code:** Python 3 CLI baseline; **portable exe / Go+Fyne** still TBD — see `docs/project.md` → *Remaining to plan*).
- [x] Create ADR: internal job model and file format — **partial:** runtime **`state/runtime-job.json`** + import report contract documented via compiler + examples; formal ADR for long-lived schema versioning still optional.
- [ ] Create ADR: reporting stack (PDF + CSV/XLSX library choices and schema) — **partial:** CSV export slice exists (`export-run-summary --output-csv`).
- [ ] Freeze "required columns" for `site-controllers` spreadsheet v1 (template + compiler enforce core columns; **120+ row** column spec still open).
- [ ] Freeze v1 pass/fail default fields that must appear in every profile (recommended defaults live in `docs/examples/` markdown; **profile contract freeze** open).

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
- CI integration suite using simulator containers or mock devices — **partial:** list verifier + **loopback BACnet fake** in unittest; **Docker BACnet sim** — **`docker/simulator/`** `bacnet-dev` profile (**three** UDP ports: two FCU-shaped + one **HRV**-shaped via `SIM_PROFILE=hrv`) + CI **`verify-bip-list --strict`** smoke (`tools/simulator/docker_bacnet_smoke.sh`). Full orchestrator/BBMD lab topology still optional.
- First operator-visible diagnostic logs for comms failures — **partial:** JSON artifacts + `events.jsonl`; richer comms diagnostics TBD.

### Phase 4 — commissioning flow engine (v1 slices)

- [x] Implement point checkout flow — **v1:** **`bacnet-point-checkout`** CLI; **`record-step`** can run the same reads when a profile step uses **`step_type: bacnet_point_checkout`** or **`run_point_checkout_on_pass`**; results append **`artifacts/commissioning_report.json`**; **guided UI** still future.
- [ ] Implement airflow adjustment + technician confirmation checkpoints.
- [x] Implement cooling valve stroke test (no CHW) with mandatory human confirmation records — **v1:** **`commissioning-confirm-prompt`** re-writes **`ao_chw_valve`** for each **`operator_prompt_confirm`** after a **`write_analog_percent`** on that object, sets **`session prompt_confirm.<prompt_id>`**; **`record-step passed/manual_passed`** on **`cooling_valve_stroke_no_chw`** or steps with **`arms_test_mode_state_key: chw_valve_stroke_no_plant`** requires those session flags ( **`PROMPTS_NOT_CONFIRMED`** if missing). **Not** full UI prompts.
- [ ] Implement heating/cooling modulation test scaffolds with skippable/manual-pass controls — **partial:** **`bacnet-modulation-sweep`** (multi **`--command-percents`**, session RAT via **`session_return_air_temperature_key`**) + optional **`record-step`** sweep on pass; **`skip_when`** + session truthy gate for **`record-step skipped`**; **`print-job-graph`** surfaces **`skip_gated_steps`** / **`modulation_action_steps`**; **not** full guided step engine / skip UI.

**Deliverables**

- Executable per-profile step engine
- Persisted step/test state with technician name + notes
- Regression tests for skip/manual pass/abort and interlock behavior

### Phase 5 — reporting and Windows distribution

- [ ] Implement report model for unified heating/cooling output tables (SAT + RAT + command + time/step).
- [x] Export CSV first — **partial:** **`export-run-summary --output-csv`** (controller × flow status rollup); **not** yet the unified modulation table contract.
- [x] **Partial:** append-only **`export-commissioning-report`** / **`artifacts/commissioning_report.json`** for **point checkout after step**, **CLI-appended thermal modulation samples/batches**, **`bacnet-modulation-sweep`** / optional **`record-step`** sweep rows (**`thermal_modulation_sweep`** with BACnet vs session **`read_source`** in CSV). **`export-commissioning-report --output-csv-unified`** flattens **point checkout + modulation** into one CSV (shared column contract v1). **Not** yet PDF tables or a frozen long-lived schema ADR for that CSV.
- [ ] Then PDF/XLSX from same normalized dataset — **partial:** **`export-commissioning-report`** **`--output-html`** (browser print-to-PDF), **`--output-xlsx`** (**openpyxl**), **`--output-pdf`** (**fpdf2**, landscape table). **Not** yet styled customer PDF templates or charts.
- [ ] Package portable Windows executable and document signing/release process.
- [ ] Add release checklist and smoke-test matrix.

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
