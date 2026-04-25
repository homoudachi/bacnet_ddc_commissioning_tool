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
| Windows exe (if shipping) | Build per [`windows-exe.md`](windows-exe.md); run `dist\bacnet-commissioning.exe --help` | Exits 0 |

## Smoke matrix (CLI slices)

| Area | Scenario | Notes |
|------|-----------|--------|
| Run dir | `init-run` → `compile-import` → `init-flow` | Standard path |
| List / graph | `print-job-graph`, `list-flows`, `show-flow`, `commissioning-guided-next` | After `init-flow` |
| BACnet read | `bacnet-read` on allowlisted point | Against sim or panel |
| BACnet write | `dry-run-bacnet-write --execute` | Allowlist + writable |
| Point checkout | `bacnet-point-checkout` | Profile `point_checkout` |
| Record step | `record-step` pass / skip / CHW stroke confirms | See README |
| Airflow | `commissioning-airflow-adjust-write`, `commissioning-airflow-closed-loop-iterate`, `commissioning-confirm-tachometer-reference` | Optional **`closed_loop`** block + MSV arm when profile requires |
| Operator UI | `operator-gui --run-dir <run> --gui-port 8765` | Localhost only; smoke allowlisted commands |
| Tauri desktop | `cd desktop/tauri-operator && npm ci && npx tauri build` | Linux `.deb` under `src-tauri/target/release/bundle/deb/`; see **`docs/packaging/tauri-operator-desktop.md`** |
| Manual airflow | `commissioning-record-manual-airflow` | Before pass on `manual_airflow_verification_assisted` steps |
| Modulation | `bacnet-modulation-sweep` | After `init-flow` |
| Report | `export-commissioning-report` CSV / unified / HTML / XLSX / PDF / customer HTML+PDF | Unified HTML includes **modulation SVG charts** when sweep+SAT data exists; **`--xlsx-include-modulation`** adds **`modulation`** sheet; customer PDF = cover + table + notes |

## Known gaps (not blocking v1 CLI)

- Optional **Authenticode** signing: configure GitHub Actions secrets per [`windows-exe.md`](windows-exe.md) (skipped when unset).
- Full guided UI and closed-loop auto airflow to measured L/s.
