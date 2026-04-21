# Recommended pass / fail criteria (defaults — refine here)

Use **profile overrides** in the import for site-specific limits. When absent, the tool can apply these **advisory** defaults and still allow **manual pass** / **skip with reason**.

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
