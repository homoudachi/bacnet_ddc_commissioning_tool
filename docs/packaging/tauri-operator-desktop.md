# Tauri desktop operator (commissioning CLI shell)

The **`desktop/tauri-operator`** app is a minimal **Tauri 2** window that runs **`python3 tools/runtime/app.py`** from the **repository root** (same pattern as the stdlib `operator-gui`, but packaged as a desktop binary).

## Prerequisites

- **Rust** stable (see `rust-toolchain.toml` in repo root; Tauri 2 currently needs a recent stable, e.g. **≥ 1.85**).
- **Node.js** + **npm** (for `@tauri-apps/cli`).
- **Linux:** WebKitGTK and related dev packages (Debian/Ubuntu example):

```bash
sudo apt-get install -y libwebkit2gtk-4.1-dev build-essential libssl-dev \
  libayatana-appindicator3-dev librsvg2-dev libxdo-dev pkg-config
```

- **Windows:** MSVC build tools + WebView2 (see [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/)).

## Build

From the repository root:

```bash
cd desktop/tauri-operator
npm ci
npx tauri build
```

Artifacts (Linux):

- Binary: `desktop/tauri-operator/src-tauri/target/release/desktoptauri-operator`
- Debian package: `desktop/tauri-operator/src-tauri/target/release/bundle/deb/*.deb`

## Run directory

The UI asks for an **absolute** path to a commissioning **run directory** (same as `--run-dir` for the Python CLI). The app validates that the path exists before invoking Python.

## Python interpreter

By default the app runs **`python3`**. Override with:

```bash
export BACNET_COMMISSIONING_PYTHON3=/path/to/python3.12
```

## Security note

The Rust backend **spawns** the Python interpreter with operator-supplied arguments (bounded length). Use only on **trusted** machines; prefer **read-only** commands in the dropdown for routine checks.
