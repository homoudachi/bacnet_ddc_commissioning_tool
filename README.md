# bacnet_ddc_commissioning_tool

## Documentation

- **Current repo status (2026-04-21):** docs-first project with early runnable tooling (simulator verifier/orchestrator and import compiler). There is no full end-user commissioning application yet.
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
- Runtime CLI tests: **[tests/test_runtime_cli.py](tests/test_runtime_cli.py)**

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

# 3) Initialize commissioning flow state for one controller
python3 tools/runtime/app.py init-flow \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A

# 4) Record technician signoff for a step
python3 tools/runtime/app.py record-step \
  --run-dir artifacts/runtime-run \
  --controller-label FCU-01A \
  --step-id half_design_airflow_auto \
  --status passed \
  --technician-name "Alex Tech" \
  --note "Reached target airflow in tolerance"

# Record-step rule enforcement:
# - A step cannot be marked passed/manual_passed until all prior steps are completed
# - A step can only be marked skipped if that step is explicitly skippable in profile flow
# - A step with explicit requires_step_ids dependencies cannot pass until those dependencies complete
# - Every transition appends step history with previous_status/attempted_status/new_status/reason_code
# - Rejected transitions are logged as flow_step_rejected with machine-readable rejection reason codes

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
