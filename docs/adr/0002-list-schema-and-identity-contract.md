# ADR-0002: List schema and identity verification contract for simulator runs

## Status

Accepted

## Context

The simulator/test harness must "find everything in the list" for BACnet controller imports. To avoid ambiguous behavior and hidden skips, we need a clear minimum schema and deterministic matching strategy between imported rows and simulator outcomes.

Without a locked contract, different tools might match rows differently (by IP only, by label only, or by device instance), causing false positives in CI and unreliable commissioning readiness checks.

## Decision

The simulator verification contract uses a required CSV schema and explicit row identity mapping:

- Required CSV columns:
  - `controller_label`
  - `profile_id`
  - `bacnet_device_instance`
  - `bacnet_ip`
  - `bacnet_port`
- Optional CSV columns:
  - `building_floor`
  - `notes`
- Each controller row is keyed by `controller_label` for scenario mapping in v1.
- Scenario input JSON must contain `rows`, where each row includes:
  - `controller_label`
  - `status`
  - optional `allow_known_unavailable`
- Allowed status values:
  - `reachable_verified`
  - `unreachable_timeout`
  - `identity_mismatch`
  - `required_point_missing`
  - `write_rejected`
  - `known_unavailable`

In v1 implementation, any controller row missing from scenario input is classified as `unreachable_timeout` to enforce full-list accounting.

## Consequences

### Positive

- Ensures every imported row receives a terminal classification.
- Prevents silent skips and hidden partial coverage in simulator runs.
- Keeps CI behavior deterministic and auditable.

### Negative / trade-offs

- v1 mapping by `controller_label` requires labels to be stable and unique.
- Additional schema validation will be needed as we expand beyond current CSV template constraints.

### Follow-up obligations

- Add explicit duplicate-label validation in a follow-up verifier slice.
- Extend identity checks to include `bacnet_device_instance` mismatch details in scenario/output records.
- Keep docs and example CSVs aligned if required columns evolve.
