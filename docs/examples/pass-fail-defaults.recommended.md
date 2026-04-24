# Recommended pass / fail criteria (defaults — refine here)

Use **profile overrides** in the import for site-specific limits. When absent, the tool can apply these **advisory** defaults and still allow **manual pass** / **skip with reason**.

## V1 profile contract (what every profile should carry)

This is the **defaults layer** companion to numeric tables below. Site JSON may add fields; the **compiler/runtime** expect at least:

| Area | Expectation |
|------|----------------|
| Identity | `profile_id`, `display_name`, `schema_version` (string; use `0.1-example` until a formal schema ADR freezes semver). |
| BACnet safety | `commissioning_write_allowlist` and `commissioning_read_allowlist` — arrays of logical `objects[].id` values (see ADR 0004). |
| Object map | `objects[]` with `id`, `bacnet.object_type`, `bacnet.instance`, and `writable` for anything the CLI may write. |
| Operator flow | `commissioning_flow[]` entries with `step_id` and `label`; use `step_type`, `skippable`, `skip_when`, `arms_test_mode_state_key`, `run_point_checkout_on_pass`, and `report_ref` as needed for the shipped CLI slices. |
| Thermal reporting | When a profile defines heating/cooling modulation for exports, include **numeric** limits or references (e.g. `thermal_tests_for_report`) so pass/fail is not only “advisory text” in this file. |

**Pass/fail numbers** belong in the **profile** for production jobs; keep **this markdown** as the team’s **starting defaults** and update both when you change thresholds.

## Cooling test (valve modulated, CHW on)

| Check | Default | Fail if |
|--------|---------|---------|
| Direction at mid stroke | At **50% valve**, SAT **≤** baseline at **0%** minus **0.5 °C** | SAT rises or unchanged (no cooling effect) — **fail** unless manual override |
| Full cooling | At **100% valve** (after dwell), SAT **≤** baseline at **0%** minus **2.0 °C** | Less than 2 °C drop — **warn**; **fail** if less than 0.5 °C |
| Recovery | Returning to **0%**, SAT returns within **1.5 °C** of original baseline | Large offset — **warn** (sticky valve / drift) |

`baseline` = average SAT over last **60 s** at **0%** before sweep.

## Heating test (heat AV modulated)

| Check | Default | Fail if |
|--------|---------|---------|
| Direction at mid stroke | At **50% heat**, SAT **≥** baseline at **0%** plus **1.0 °C** | No heat rise — **fail** unless override |
| Full heat | At **100% heat** (if allowed), SAT **≥** baseline plus **3.0 °C** | Less than 3 °C — **warn**; **fail** if less than 0.5 °C |
| Recovery | At **0% heat**, SAT within **1.5 °C** of baseline | **Warn** if outside |

## HRV heat recovery (see profile `heat_recovery_effectiveness`)

- **Effectiveness** or **temperature cross** checks are **profile-defined**; default only **warn** if **OAT, RAT, SAT** sensor spread is implausible (e.g. missing change after large fan change).
- **Fan speed matrix:** each speed set **pass** if logged temps stable and optional **calculated** effectiveness within **±10%** of expected (when calculation enabled).

## Manual override

Any **fail** may be marked **manual pass** with **notes + name** for the report.
