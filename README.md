# bacnet_ddc_commissioning_tool

## Documentation

- **Current repo status (2026-04-23):** docs-first project with early runnable tooling (simulator verifier/orchestrator, import compiler, and Python runtime CLI). BACnet **probes** use a tiny UDP helper; **ReadProperty / WriteProperty** use **[BACpypes3](https://bacpypes3.readthedocs.io/)** (`pip install -r requirements.txt`). There is no full end-user commissioning application yet.
- **[Living project doc](docs/project.md)** — product requirements, commissioning flows, examples, import direction, and reports (update as the product evolves).
- **[ADRs](docs/adr/)** — short decision records when choices are non-obvious.
- **[Slice plans](docs/plans/)** — time-boxed implementation plans; archive or remove when the slice ships.

## Planning next steps

- Start with the active foundation plan: **[docs/plans/2026-04-21-v1-foundation-plan.md](docs/plans/2026-04-21-v1-foundation-plan.md)**.
- Track cross-cutting decisions in **[Remaining to plan (before implementation)](docs/project.md#remaining-to-plan-before-implementation)** and **[Open questions](docs/project.md#open-questions)**.
- For BACnet simulation architecture and networking, use **[docs/simulator/README.md](docs/simulator/README.md)** and **[docs/plans/2026-04-21-bacnet-simulator-plan.md](docs/plans/2026-04-21-bacnet-simulator-plan.md)**.

## Current implementation slice

- List-first verification CLI: **[tools/simulator/list_verifier.py](tools/simulator/list_verifier.py)**
- Initial tests: **[tests/test_list_verifier.py](tests/test_list_verifier.py)**
- ADR lock-ins: **[docs/adr/](docs/adr/)** (0001-0003)
- Import compiler CLI: **[tools/import/compile_job.py](tools/import/compile_job.py)**
- Import compiler tests: **[tests/test_import_compiler.py](tests/test_import_compiler.py)**
- Runtime skeleton CLI: **[tools/runtime/app.py](tools/runtime/app.py)**
- BACnet façade (probe + present-value read/write): **[tools/bacnet/adapter.py](tools/bacnet/adapter.py)**
- Runtime CLI tests: **[tests/test_runtime_cli.py](tests/test_runtime_cli.py)** (includes **loopback BACnet** coverage for read, write execute, and point checkout via a small UDP fake peer—no panel required for CI).

## Runtime CLI quick start

```bash
# 1) Initialize run directory
python3 tools/runtime/app.py init-run \
  --run-dir artifacts/runtime-run \
  --job-id demo-job-001 \
  --controllers-csv docs/examples/site-controllers.template.csv \
  --profiles-dir docs/examples \
  --scenarios-dir docs/examples/simulator-scenarios

# 2) Compile import into runtime state
python3 tools/runtime/app.py compile-import --run-dir artifacts/runtime-run

# 2b) Dry-run compile only (writes artifacts/import-validation/, does not overwrite state/runtime-job.json)
python3 tools/runtime/app.py validate-import --run-dir artifacts/runtime-run

# 2c) Print controller / flow / object-count summary (requires compile-import first)
python3 tools/runtime/app.py print-job-graph --run-dir artifacts/runtime-run

# 3) Initialize commissioning flow state for one controller
python3 tools/runtime/app.py init-flow \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A

# 3a) Inspect flow state (JSON on stdout); logs flows_listed / flow_viewed
python3 tools/runtime/app.py list-flows --run-dir artifacts/runtime-run
python3 tools/runtime/app.py show-flow \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A

# 3b) Operator-entered session values (requires init-flow); state/sessions/<label>.json
python3 tools/runtime/app.py set-session-value \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A \
  --key rat_degC \
  --value "22.5" \
  --technician-name "Alex Tech" \
  --note "Manual RAT"
python3 tools/runtime/app.py show-session \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A

# 3c) Re-initialize after a mistake (backs up prior state to state/flow_backups/, logs flow_reinitialized)
python3 tools/runtime/app.py init-flow \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A \
  --force \
  --reset-technician-name "Lead Tech" \
  --reset-reason "Wrong unit selected; restarting flow from profile defaults"

# 3d) Export one JSON rollup for the run (after compile-import): controllers, flow presence, next open step
python3 tools/runtime/app.py export-run-summary --run-dir artifacts/runtime-run
# Optional: --output-json artifacts/runtime-run/artifacts/my-summary.json
# Optional: --output-csv artifacts/runtime-run/artifacts/run-summary.csv
# Optional: embed full blobs for single-file handoff (larger JSON):
#   --embed-import-report --embed-bip-list-summary

# 3e) BACnet WriteProperty (profile-driven allowlist + BACpypes3)
# Unit profile JSON must include commissioning_write_allowlist: ["msv_test_mode", ...]
# Default: dry-run uses minimal Who-Is probe only (no BACpypes3 write).
python3 tools/runtime/app.py dry-run-bacnet-write \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A \
  --object-id msv_test_mode \
  --value 3 \
  --technician-name "Alex Tech" \
  --note "Arm test mode state 3 (profile-defined meaning)"
# Live write (install: pip install -r requirements.txt):
# python3 tools/runtime/app.py dry-run-bacnet-write ... --execute [--bacnet-bind-port 47809] [--apdu-timeout 15]

# 3f) ReadProperty (BACpypes3); object_id must be in profile commissioning_read_allowlist
# python3 tools/runtime/app.py bacnet-read --run-dir artifacts/runtime-run \
#   --controller-label FCU-01A --object-id ai_sat [--property presentValue] [--apdu-timeout 15]

# 3g) Point checkout: read profile point_checkout[] in order (same allowlist rules per object)
# python3 tools/runtime/app.py bacnet-point-checkout --run-dir artifacts/runtime-run \
#   --controller-label FCU-01A [--strict] [--bacnet-bind-port 47809] [--apdu-timeout 15]

# 4) Record technician signoff for a step
python3 tools/runtime/app.py record-step \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A \
  --step-id half_design_airflow_auto \
  --status passed \
  --technician-name "Alex Tech" \
  --note "Reached target airflow in tolerance"
# When a profile step has step_type bacnet_point_checkout or run_point_checkout_on_pass,
# passing the step runs profile point_checkout BACnet reads first; on failure the step is not recorded.
# Optional: --bacnet-timeout-seconds 0.5 --bacnet-retries 1 --bacnet-bind-port 0 --apdu-timeout 15 [--bacnet-checkout-strict]

# 4b) Export append-only commissioning report (after gated record-step or future writers)
# python3 tools/runtime/app.py export-commissioning-report --run-dir artifacts/runtime-run
# python3 tools/runtime/app.py export-commissioning-report --run-dir artifacts/runtime-run --output-json my-report.json
# Optional: --allow-empty with --output-json writes {"entries":[]} stub when no report yet (CI / templates)
# Optional: --output-csv modulation.csv exports thermal_modulation_* rows only

# 4c) Append thermal modulation sample (allowlisted BACnet reads → commissioning_report.json)
# python3 tools/runtime/app.py append-commissioning-modulation-sample --run-dir artifacts/runtime-run \
#   --controller-label FCU-01A --read ai_sat --read msv_test_mode \
#   --technician-name "Alex Tech" --note "sweep t=0" --step-id heating_test \
#   --report-ref thermal_tests_for_report.heating

# 4d) Batch modulation reads from JSON file (list of {controller_label, reads:[...], ...})
# python3 tools/runtime/app.py append-commissioning-modulation-batch --run-dir artifacts/runtime-run \
#   --input-json my-samples.json [--default-technician "Alex Tech"]

# 4e) Modulation sweep from profile flow step (init-flow + modulate_actuator_log_sat_for_report action):
# python3 tools/runtime/app.py bacnet-modulation-sweep --run-dir artifacts/runtime-run \
#   --controller-label FCU-01A --step-id heating_test --command-percent 50 \
#   --dwell-seconds 0.5 --technician-name "Alex Tech" [--note "..."] [--report-ref override]

# Init-flow: second init for the same controller without --force is rejected (avoids silent overwrite).
# Record-step rule enforcement:
# - Outcomes use passed, manual_passed, failed, or skipped (pending is not recordable)
# - passed/manual_passed/failed require prior steps to be passed, manual_passed, or skipped (a prior failed blocks until resolved)
# - A step can only be marked skipped if that step is explicitly skippable in profile flow
# - A step with explicit requires_step_ids dependencies cannot pass/fail until those dependencies complete
# - Every transition appends step history with previous_status/attempted_status/new_status/reason_code
# - Rejected transitions are logged as flow_step_rejected with machine-readable rejection reason codes
# - list-flows / show-flow append flows_listed / flow_viewed; session commands append session_value_set / session_viewed

# 5) Verify one simulator scenario
python3 tools/runtime/app.py verify-simulator \
  --run-dir artifacts/runtime-run \
  --profile ci \
  --scenario happy-path \
  --strict

# 6) Probe one BACnet/IP endpoint from compiled controller list
python3 tools/runtime/app.py probe-bip \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A \
  --timeout-seconds 0.5 \
  --retries 1

# 7) Probe full BACnet/IP controller list (strict: all must be reachable)
python3 tools/runtime/app.py verify-bip-list \
  --run-dir artifacts/runtime-run \
  --strict \
  --timeout-seconds 0.5 \
  --retries 1

# 8) Probe full list in non-strict mode with known-unavailable overrides
python3 tools/runtime/app.py verify-bip-list \
  --run-dir artifacts/runtime-run \
  --timeout-seconds 0.5 \
  --retries 1 \
  --known-unavailable-file artifacts/runtime-run/config/bip-known-unavailable.json
```
