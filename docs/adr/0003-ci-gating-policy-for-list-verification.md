# ADR-0003: CI gating policy for list-first verification

## Status

Accepted

## Context

The simulator lab requires deterministic pass/fail behavior in CI so failures are
actionable. The project intent is to verify every imported controller row and fail
if required rows are not validated. We also need a controlled exception path for
intentionally unavailable rows in non-strict runs.

## Decision

Adopt two evaluator modes in the verifier CLI:

1. `--strict` mode (default for CI pipelines):
   - Any row that is not `reachable_verified` fails the run.
   - This includes `identity_mismatch`, `required_point_missing`,
     `unreachable_timeout`, `write_rejected`, and `known_unavailable`.
2. Non-strict mode:
   - `known_unavailable` is allowed only when scenario input explicitly sets
     `allow_known_unavailable: true` for that row.
   - Any other non-`reachable_verified` status still fails the run.

The CLI prints a deterministic summary line:

- `found=<n> total=<n> unresolved=<n> strict_pass=<true|false> strict_mode=<true|false>`

and status counters per class to support CI logs and artifact parsing.

## Consequences

Positive:

- CI failures become explicit and reproducible.
- Operators can use controlled non-strict runs for planned outages.
- Status classes map directly to troubleshooting guidance.

Costs:

- Scenario files must include explicit allow flags for planned unavailable rows.
- Additional tests are required to enforce output contract and mode differences.

Follow-up obligations:

- Keep `docs/simulator/README.md` gating section synchronized with CLI behavior.
- Add regression tests whenever new status classes are introduced.
