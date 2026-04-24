# Windows single-file executable (PyInstaller)

The commissioning CLI is packaged as **one console `.exe`** using **PyInstaller** (`--onefile`). Code signing is **not** configured here (SmartScreen may warn on first run).

## Prerequisites

- **Windows 10/11** x64
- **Python 3.12** (64-bit) on PATH
- This repository checked out (or a source tree with the same layout)

## Build steps

From the **repository root**:

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-packaging.txt
python -m PyInstaller tools\packaging\runtime.spec
```

Output: **`dist\bacnet-commissioning.exe`**

## What is bundled

- Runtime entrypoint: `tools/runtime/app.py` (with `tools/runtime/repo_root.py` on the import path)
- **`docs/examples/`** tree (unit profile JSON, template CSV, simulator scenarios, branding placeholder) so defaults like bundled PDF logo paths resolve inside the frozen bundle
- **`bacpypes3`**, **`openpyxl`**, **`fpdf2`** (via PyInstaller hooks / `collect_all`)

Operators still pass **`--profiles-dir`**, **`--controllers-csv`**, and **`--run-dir`** pointing at **their** site files; only examples ship inside the exe.

## Smoke test

```bat
dist\bacnet-commissioning.exe --help
```

## Notes

- **Antivirus** sometimes flags PyInstaller bundles; report false positives to your AV vendor if needed.
- For reproducible builds, pin dependency versions in `requirements.txt` before release tagging.
