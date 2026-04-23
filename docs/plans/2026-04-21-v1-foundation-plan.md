# V1 foundation plan (docs-first to executable baseline)

## Goal

Move this repository from "requirements and examples only" to a working baseline that can:

1. Load and validate site controller spreadsheets,
2. Simulate and/or connect to BACnet endpoints through a clean adapter,
3. Execute the first commissioning flow slices with auditable results, and
4. Export technician-ready records.

## Current status

- **2026-04-23:** Runnable Python CLIs, unit tests, and GitHub Actions exist; see `README.md` and `docs/project.md`. The checklist below is still useful for remaining v1 gaps (stack ADRs, portable packaging, full flow engine).
- Product intent is tracked in `docs/project.md`.
- This plan remains the high-level execution sequence; treat unchecked items as backlog unless superseded by newer ADRs.

## Recommended sequencing (authoritative)

Use this order to reduce rework and unblock parallel work later.

### Phase 0 — lock critical decisions first

- [ ] Create ADR: implementation stack and packaging target (recommended default: Go + Fyne + Windows portable exe workflow).
- [ ] Create ADR: internal job model and file format (`.json` generated from spreadsheet + profile library).
- [ ] Create ADR: reporting stack (PDF + CSV/XLSX library choices and schema).
- [ ] Freeze "required columns" for `site-controllers` spreadsheet v1.
- [ ] Freeze v1 pass/fail default fields that must appear in every profile.

**Deliverables**

- ADRs in `docs/adr/`
- Updated `docs/project.md` sections where TBD/open questions become decisions
- One canonical spreadsheet schema table in docs

### Phase 1 — bootstrap runtime and quality gates

- [ ] Create app skeleton (CLI + package structure + config loading + structured logging).
- [ ] Add test harness and CI checks (format, lint, unit test, fixture validation).
- [ ] Add golden fixtures from `docs/examples/*.json` and `docs/examples/site-controllers.template.csv`.
- [ ] Add a no-network "dry run" command that validates import and prints unit/test graph.

**Deliverables**

- Runnable developer entrypoint
- CI passing on every push
- Documented local run commands in `README.md` and `docs/project.md`

### Phase 2 — import compiler and validation UX

- [ ] Implement spreadsheet parser and validator for `~120 controllers` scale.
- [ ] Enforce uniqueness/consistency checks (IP/device ID/profile references/object overrides).
- [ ] Produce normalized internal job model and human-readable validation errors.
- [ ] Add import report output (warning/error summary for commissioning leads).

**Deliverables**

- Deterministic import output (JSON artifact or equivalent runtime snapshot)
- Validation tests with known bad-sheet fixtures
- Updated examples and docs for schema/versioning

### Phase 3 — BACnet adapter + simulator-first development

- [ ] Implement BACnet abstraction layer (read/write/subscribe/timeouts/retry policy).
- [x] Add simulator-backed integration tests for core read/write and mode transitions (loopback fake BACnet peer in `tests/test_runtime_cli.py` exercises `bacnet-read`, `dry-run-bacnet-write --execute`, and `bacnet-point-checkout` against BACpypes3-shaped frames).
- [ ] Add commissioning safety constraints (write allowlist, per-mode restrictions, abort rules).
- [ ] Document network assumptions and expected failure handling behavior.

**Deliverables**

- Stable adapter interface usable by commissioning flow engine
- CI integration suite using simulator containers or mock devices
- First operator-visible diagnostic logs for comms failures

### Phase 4 — commissioning flow engine (v1 slices)

- [ ] Implement point checkout flow.
- [ ] Implement airflow adjustment + technician confirmation checkpoints.
- [ ] Implement cooling valve stroke test (no CHW) with mandatory human confirmation records.
- [ ] Implement heating/cooling modulation test scaffolds with skippable/manual-pass controls.

**Deliverables**

- Executable per-profile step engine
- Persisted step/test state with technician name + notes
- Regression tests for skip/manual pass/abort and interlock behavior

### Phase 5 — reporting and Windows distribution

- [ ] Implement report model for unified heating/cooling output tables (SAT + RAT + command + time/step).
- [ ] Export CSV first, then PDF/XLSX from same normalized dataset.
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
