# ADR 0007 — CHW valve stroke (no CHW): operator prompt confirmations in CLI

## Status

Accepted

## Context

The product requires a **cooling valve stroke without CHW**: command **100%** and **0%** with **recorded technician confirmations** before the commissioning step can be marked **passed**. Profiles already describe **`write_analog_percent`** on **`ao_chw_valve`** plus **`operator_prompt_confirm`** actions, but the runtime had no executable slice.

## Decision

1. **`compile-import`** and **`init-flow`** persist **`arms_test_mode_state_key`** on commissioning flow steps when present in the profile.
2. Add **`commissioning-confirm-prompt`** (`--run-dir`, `--controller-label`, `--step-id`, `--prompt-id`, …): for a matching **`operator_prompt_confirm`** that follows **`write_analog_percent`** on **`ao_chw_valve`**, verify **`msv_test_mode`** is state **6** when the step uses **`chw_valve_stroke_no_plant`** (or **`step_id` `cooling_valve_stroke_no_chw`**), **WriteProperty** the preceding **percent** to **`ao_chw_valve`**, then set **`session_values["prompt_confirm.<prompt_id>"]`** to **`true`** with technician metadata.
3. **`record-step`** for **`passed` / `manual_passed`** on gated steps (**`cooling_valve_stroke_no_chw`** or **`arms_test_mode_state_key: chw_valve_stroke_no_plant`** with the same action pattern) requires all derived **`prompt_confirm.*`** session keys to be truthy; otherwise reject with **`operator_prompts_not_confirmed`** / event reason **`PROMPTS_NOT_CONFIRMED`**.

## Consequences

- Stroke + confirm is **auditable** (session JSON + **`commissioning_prompt_confirmed`** in **`events.jsonl`**).
- Operators must run **one CLI invocation per prompt** after arming MSV; a future UI can wrap the same contract.
