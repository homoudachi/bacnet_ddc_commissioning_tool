# Recommended modulation recipes (defaults — refine here)

This file is the **single place** to edit default sweep behavior before the engine reads profile overrides. Product code should load **profile-specific** overrides from the import when present; if absent, use these recommendations.

## Cooling valve (CHW plant on)

| Parameter | Recommended default | Notes |
|-----------|---------------------|--------|
| Shape | **Stepped ramp** | Safer than continuous slew on unknown hydronics |
| Steps | `0 → 25 → 50 → 75 → 100 → 75 → 50 → 25 → 0` (% command) | Round-trip shows hysteresis if any |
| Dwell per step | **90 seconds** | Increase if coil mass is large |
| Stabilization | Wait until **\|dSAT/dt\| < 0.1 °C/min** for **60 s** or dwell timeout | Whichever is **longer** per step |
| Sample interval for report | **15 seconds** | Plus one row at end of each step |
| Safety abort | **SAT < 10 °C** or **SAT > 40 °C** (profile-adjust) or **\|ΔSAT\| > 3 °C in 2 min** | Stop sweep, command valve toward safe |

## Electric heat (modulating AV)

| Parameter | Recommended default | Notes |
|-----------|---------------------|--------|
| Shape | **Stepped ramp** | Match cooling table shape for comparable reports |
| Steps | `0 → 20 → 40 → 60 → 80 → 100 → 60 → 40 → 20 → 0` (% command) | Skip 100 if interlock prevents |
| Dwell per step | **120 seconds** | Heat often slower than cooling coil |
| Stabilization | **\|dSAT/dt\| < 0.15 °C/min** for **60 s** | Profile-tunable |
| Sample interval | **15 seconds** | Same as cooling |
| Safety abort | **SAT > 55 °C** (profile) or **\|ΔSAT\| > 4 °C in 2 min** | Stop sweep, heat to 0 |

## Profile override path (JSON)

Put a block like this in the unit profile when you lock the schema (names illustrative):

```json
"modulation_recipe": {
  "cooling_valve": { "steps_percent": [0, 25, 50, 75, 100, 75, 50, 25, 0], "dwell_seconds": 90 },
  "electric_heat": { "steps_percent": [0, 20, 40, 60, 80, 100, 60, 40, 20, 0], "dwell_seconds": 120 }
}
```

If `modulation_recipe` is missing, the application uses the tables above.
