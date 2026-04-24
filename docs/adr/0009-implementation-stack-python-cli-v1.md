# ADR 0009 — Implementation stack for v1 (Python CLI baseline)

## Status

Accepted

## Context

The product vision includes a **Windows portable executable**, but the repository already ships a **Python 3** CLI (`tools/runtime/`, `tools/import/`, `tools/bacnet/`) with **unittest** CI and BACnet integration via **BACpypes3** (see ADR 0004/0005). A second stack (e.g. Go desktop, .NET) would duplicate import, BACnet, and reporting work without a committed migration plan.

## Decision

- **V1 implementation stack:** **Python 3** (stdlib + pinned dependencies in `requirements.txt`) for import compiler, runtime CLI, BACnet façade, commissioning report export (CSV / HTML / XLSX / PDF), and tests.
- **Windows portable packaging:** **explicitly deferred** beyond documenting constraints in `docs/project.md` (signing, SmartScreen, AV false positives). No commitment to PyInstaller vs Nuitka vs other bundler until a dedicated ADR or release slice.
- **Optional future UI:** any “operator utility” shell may **wrap** the same Python entrypoints or call shared libraries; that choice does not change the v1 baseline stack above.

## Consequences

- New features should land in **Python** with **unittest** coverage unless a deliberate migration ADR supersedes this one.
- Release engineering (code signing, installer vs portable folder) remains **documentation + backlog**, not implied by the current codebase layout alone.
