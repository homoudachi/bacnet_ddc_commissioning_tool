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

## Code signing (optional)

**You do not need a certificate to build or run the exe** on your own machines. What signing buys you is mostly **trust on other people’s Windows PCs**:

- **Microsoft Defender SmartScreen** (and similar reputation systems) often treat a **new, unsigned** download as “unknown publisher.” Users may see **Windows protected your PC** or an extra **More info → Run anyway** step the first time. That friction usually **drops after enough reputation** (many installs over time) even without signing—but there is **no fixed timeline**, and it varies by file hash and distribution channel.
- **Authenticode signing** with a **publicly trusted** code-signing certificate (from a CA Microsoft trusts) is the standard way to **reduce** those warnings **immediately** for customers and IT departments who block unknown publishers.

**Cost (order of magnitude, 2026):** a **Standard OV code-signing** certificate is commonly on the order of **tens to low hundreds of USD per year** from commercial CAs (exact price depends on vendor, term, and org validation). **EV code-signing** certificates cost more and require a hardware token; they can help with **SmartScreen reputation** faster in some cases, but are **not** required for a basic “signed by known publisher” experience.

**Process:** buy the cert, complete **organization validation**, then sign the built `dist\bacnet-commissioning.exe` with **SignTool** (or your CI’s signing step) using the vendor’s instructions. **Private keys** must stay secret; many teams use a **cloud HSM** or **hardware token** rather than copying a `.pfx` around.

**When to skip signing:** internal tools, lab-only builds, or small pilots where technicians already trust the source—**unsigned is fine** if you accept the extra SmartScreen/IT friction. **When to add it:** shipping broadly to customers or **managed Windows** estates where **AppLocker / SmartScreen policy** blocks unsigned executables.

### CI (GitHub Actions)

The **windows-exe** workflow runs **`tools/packaging/sign_windows_exe.ps1`** after PyInstaller when these **repository secrets** are set (all optional; if `WINDOWS_CODESIGN_PFX_BASE64` is missing, signing is skipped):

| Secret | Purpose |
|--------|---------|
| `WINDOWS_CODESIGN_PFX_BASE64` | Base64-encoded **PFX** containing the code-signing cert + private key |
| `WINDOWS_CODESIGN_PFX_PASSWORD` | PFX password (may be empty) |
| `WINDOWS_CODESIGN_TIMESTAMP_URL` | RFC3161 timestamp URL (default in script: DigiCert) |

The Windows runner must include **SignTool** (Windows SDK); the script searches under `Program Files (x86)\Windows Kits\10\bin`.

## Notes

- **Antivirus** sometimes flags PyInstaller bundles; report false positives to your AV vendor if needed.
- For reproducible builds, pin dependency versions in `requirements.txt` before release tagging.
