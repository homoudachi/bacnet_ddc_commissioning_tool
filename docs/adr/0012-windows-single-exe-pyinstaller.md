# ADR 0012 — Windows portable build: PyInstaller single-file exe

## Status

Accepted

## Context

The product targets a **Windows portable `.exe`** without an installer for early field use. The implementation is **Python 3** (ADR 0001 family). Subprocess-based helpers (`python tools/import/compile_job.py`, orchestrator → list_verifier) **break** under PyInstaller `--onefile` because there is no separate `python` interpreter beside loose `.py` files.

## Decision

- **Bundler:** **PyInstaller** `--onefile` (console) producing **`bacnet-commissioning.exe`**.
- **Entry:** `tools/runtime/app.py` with **`pathex`** including `tools/runtime` so `from repo_root import repo_root` resolves.
- **Repo root when frozen:** `tools/runtime/repo_root.py` uses **`sys._MEIPASS`** when `sys.frozen` is true (bundle layout includes `tools/` and `docs/examples/` under the extract dir).
- **No subprocess for import / simulator:** `compile_job.run_compile(...)`, `list_verifier.run_verifier(...)`, and `orchestrator.run_orchestrator(...)` are invoked **in-process** from `app.py`. Dynamically loaded modules are registered in **`sys.modules`** before `exec_module` so `@dataclass` and similar resolve `__module__` correctly.
- **Signing:** **out of scope** for this slice (document SmartScreen / AV caveats in `docs/packaging/windows-exe.md`).

## Consequences

- **CI:** `.github/workflows/windows-exe.yml` builds and uploads the artifact on **`windows-latest`**.
- **Local dev:** unchanged; still `python3 tools/runtime/app.py …`. Optional `python -m PyInstaller tools/packaging/runtime.spec` from repo root.
- **Bundle size:** includes full `tools/` tree plus `docs/examples/`; acceptable for v1; trim in a future ADR if needed.
