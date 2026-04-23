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
3. Extend **`export-commissioning-report`** with **`--output-csv`** to flatten **`thermal_modulation_sample`**, **`thermal_modulation_batch`**, and **`thermal_modulation_sweep`** (extra columns `command_object_id`, `command_percent`, `dwell_seconds` where applicable).
4. **`--allow-empty`** stub uses schema **0.2** for consistency.
5. **`bacnet-modulation-sweep`** writes command percent(s) then reads SAT/RAT/context per profile **`modulate_actuator_log_sat_for_report`** action. **`--command-percents`** runs one **`thermal_modulation_sweep`** entry per value. When BACnet RAT is absent or not in **`objects_by_id`**, **`session_return_air_temperature_key`** supplies a reading row with **`source: session`** (operator must **`set-session-value`**). **`record-step`** may run the same sweep on **`passed` / `manual_passed`** when **`--modulation-command-percents`** is supplied (or **`--no-run-modulation-on-pass`** to disable).

## Consequences

- Operators or external scripts can log modulation **snapshots** without implementing the full step engine.
- CSV is **modulation-only**; point-checkout entries remain JSON-only until a unified export schema is defined. Sweep rows may include **`read_source`** (`bacnet` / `session`).
- **`append-commissioning-modulation-sample`** / **`append-commissioning-modulation-batch`** are read-only; **`bacnet-modulation-sweep`** performs allowlisted **WriteProperty** then reads. A full profile-driven step engine (dwell policies, aborts, UI) remains future work.
