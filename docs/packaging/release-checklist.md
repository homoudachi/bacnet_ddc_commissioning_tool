# Release checklist and smoke-test matrix (v1)

Use before tagging a release or handing a **Windows exe** / **Python** drop to the field.

## Pre-release checks

| Step | Command / action | Pass |
|------|------------------|------|
| Unit tests | `python3 -m unittest discover -s tests -p 'test_*.py'` | All green |
| Import compile | `python3 tools/runtime/app.py validate-import --run-dir <run>` | `compile_ok` in report |
| Optional Docker BACnet | `tools/simulator/docker_bacnet_smoke.sh` (requires Docker) | Script exits 0 |
| Windows exe (if shipping) | Build per [`windows-exe.md`](windows-exe.md); run `dist\bacnet-commissioning.exe --help` | Exits 0 |

## Smoke matrix (CLI slices)

| Area | Scenario | Notes |
|------|-----------|--------|
| Run dir | `init-run` → `compile-import` → `init-flow` | Standard path |
| List / graph | `print-job-graph`, `list-flows`, `show-flow` | After compile |
| BACnet read | `bacnet-read` on allowlisted point | Against sim or panel |
| BACnet write | `dry-run-bacnet-write --execute` | Allowlist + writable |
| Point checkout | `bacnet-point-checkout` | Profile `point_checkout` |
| Record step | `record-step` pass / skip / CHW stroke confirms | See README |
| Airflow | `commissioning-airflow-adjust-write`, `commissioning-confirm-tachometer-reference` | Optional profile keys |
| Manual airflow | `commissioning-record-manual-airflow` | Before pass on `manual_airflow_verification_assisted` steps |
| Modulation | `bacnet-modulation-sweep` | After `init-flow` |
| Report | `export-commissioning-report` CSV / unified / HTML / XLSX / PDF | Includes `manual_airflow_measurement` after `commissioning-record-manual-airflow` |

## Known gaps (not blocking v1 CLI)

- Code signing for Windows (SmartScreen).
- Full guided UI and closed-loop auto airflow to measured L/s.
