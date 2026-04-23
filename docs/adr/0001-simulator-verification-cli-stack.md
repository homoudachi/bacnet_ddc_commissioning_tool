# ADR-0001: Simulator verification CLI stack

## Status

Accepted

## Context

The repository was docs-first with no executable verifier. We needed a minimal, deterministic implementation that can run in CI and local development to enforce list-first, verify-all behavior before larger BACnet runtime work begins.

## Decision

Use **Python 3 standard library** for the first simulator verification CLI (`tools/simulator/list_verifier.py`) and tests (`unittest`) with no third-party dependencies.

Initial command contract:

- Input: controllers CSV and scenario JSON
- Behavior: evaluate every controller row and emit summary counts/statuses
- Exit code: 0 when gate passes, 2 when gate fails or input is invalid

## Consequences

- **Pros:** Fast bootstrap, no dependency management overhead, easy to run in CI and cloud agents.
- **Cons:** Future BACnet protocol-level runtime may require a different language/runtime or additional Python packages.
- **Follow-up:** If runtime stack changes (for example to Go for production app), keep this verifier as a stable CI contract or supersede with a new ADR and migration note.
