# ADR 0006 — Commissioning report: modulation samples and CSV export

## Status

Accepted

## Context

The commissioning report file (`artifacts/commissioning_report.json`) started with **`point_checkout_after_step`** entries from gated **`record-step`**. Product docs describe future **thermal modulation** tables (command %, SAT, RAT over time) for heating/cooling tests. We need a **scriptable path** to accumulate rows before a full flow engine executes profile **`modulate_actuator_log_sat_for_report`** actions.

## Decision

1. Bump report **`schema_version`** to **`0.2-commissioning-report`** when new entry kinds are appended (existing `0.1` files are upgraded on next write).
2. Add CLI commands:
   - **`append-commissioning-modulation-sample`** — one timestamped **`thermal_modulation_sample`** with multiple allowlisted reads (`--read` repeatable, `object_id` or `object_id:property`).
   - **`append-commissioning-modulation-batch`** — one **`thermal_modulation_batch`** wrapping multiple samples from a JSON file (for scripted sweeps).
3. Extend **`export-commissioning-report`** with **`--output-csv`** to flatten **`thermal_modulation_sample`** and nested batch samples into rows (`entry_ts`, `controller_label`, `step_id`, `report_ref`, `object_id`, `status`, `value_str`, …).
4. **`--allow-empty`** stub uses schema **0.2** for consistency.

## Consequences

- Operators or external scripts can log modulation **snapshots** without implementing the full step engine.
- CSV is **modulation-only**; point-checkout entries remain JSON-only until a unified export schema is defined.
- Full automation (writes + timed reads driven by profile actions) remains future work; these commands **read only** (writes stay on **`dry-run-bacnet-write --execute`** or future sweep command).
