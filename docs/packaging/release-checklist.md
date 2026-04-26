# Release checklist and smoke-test matrix (v1)

Use before tagging a release or handing a **Windows exe** / **Python** drop to the field.

## Pre-release checks

| Step | Command / action | Pass |
|------|------------------|------|
| Unit tests | `python3 -m unittest discover -s tests -p 'test_*.py'` | All green |
| Commissioning export | `tools/simulator/commissioning_export_smoke.sh` | Same as CI: empty report → JSON + unified CSV + HTML + XLSX + PDF + customer HTML/PDF |
| Large-sheet compile bench | `python3 tools/import/benchmark_compile.py --rows 500` | JSON timing line; `compile_ok` true |
| Unified CSV doc | `python3 tools/schema/gen_commissioning_report_unified_csv_doc.py` | After changing unified columns; commit updated `docs/schema/commissioning-report-unified-csv-v1.md` |
| Import compile | `python3 tools/runtime/app.py validate-import --run-dir <run>` | `compile_ok` in report |
| Optional Docker BACnet | `tools/simulator/docker_bacnet_smoke.sh` (requires Docker) | Script exits 0 |
| Optional BBMD lab | `tools/simulator/docker_bbmd_lab_smoke.sh` (requires Docker) | Foreign-device read to isolated subnet sim |
| Windows exe (if shipping) | Build per [`windows-exe.md`](windows-exe.md); run `dist\bacnet-commissioning.exe --help` | Exits 0 |

## Smoke matrix (CLI slices)

| Area | Scenario | Notes |
|------|-----------|--------|
| Run dir | `init-run` → `compile-import` → `init-flow` | Standard path; `config/runtime-config.json` includes **`events_log`** defaults (**ADR 0017**); optional env **`COMMISSIONING_EVENTS_MAX_BYTES`** / **`COMMISSIONING_EVENTS_RETENTION_FILES`** |
| List / graph | `print-job-graph`, `list-flows`, `show-flow`, `commissioning-guided-next` | After `init-flow` |
| BACnet read | `bacnet-read` on allowlisted point | Against sim or panel |
| BACnet read batch | `bacnet-read-batch --read ...` | Default **`--mode multiple`** (ReadPropertyMultiple); **`--mode sequential`** if device rejects RPM |
| BACnet write | `dry-run-bacnet-write --execute` | Allowlist + writable |
| BACnet COV | `bacnet-subscribe-cov` | After successful allowlisted read |
| BACnet batch write | `bacnet-write-batch --execute` | Default `--mode sequential`; optional **`--mode multiple`** (WritePropertyMultiple; device-dependent) |
| Point checkout | `bacnet-point-checkout` | Profile `point_checkout`; default **ReadPropertyMultiple** when ≥2 points (`--no-read-property-multiple` to force per-point reads) |
| Record step | `record-step` pass / skip / CHW stroke confirms | See README |
| Airflow | `commissioning-airflow-adjust-write`, `commissioning-airflow-closed-loop-iterate`, `commissioning-confirm-tachometer-reference` | Optional **`closed_loop`** block + MSV arm when profile requires |
| Operator UI | `operator-gui --run-dir <run> --gui-port 8765` | **`/guided`** flow UI; **`/dashboard`** all controllers + manual BACnet; **`/`** advanced CLI form |
| Tauri desktop | `cd desktop/tauri-operator && npm ci && npx tauri build` | Linux: `-c '{"bundle":{"targets":["deb"]}}'` for `.deb`; Windows: `npx tauri build -b nsis`; see **`docs/packaging/tauri-operator-desktop.md`** |
| Manual airflow | `commissioning-record-manual-airflow` | Before pass on `manual_airflow_verification_assisted` steps |
| Modulation | `bacnet-modulation-sweep` | After `init-flow` |
| Report | `export-commissioning-report` CSV / unified / HTML / XLSX / PDF / customer HTML+PDF | Unified HTML includes **modulation SVG charts** when sweep+SAT data exists; **`--xlsx-include-modulation`** adds **`modulation`** sheet; customer PDF = cover + table + notes |

## Known gaps (not blocking v1 CLI)

- Optional **Authenticode** signing: configure GitHub Actions secrets per [`windows-exe.md`](windows-exe.md) (skipped when unset).
- Full guided UI and closed-loop auto airflow to measured L/s.
