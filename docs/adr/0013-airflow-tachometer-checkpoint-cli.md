# ADR 0013 — Airflow adjustment + tachometer confirmation (CLI checkpoints)

## Status

Accepted

## Context

The foundation plan calls for **airflow adjustment** and **technician confirmation** before downstream commissioning (e.g. half-design flow then **tachometer reference** for heat interlocks). Profiles already describe **`automatic_airflow_adjustment`** and **`operator_confirm_tachometer_reference`** actions, but there was no operator CLI to drive BACnet writes/reads and no **`record-step`** gate tying confirmations to step pass.

## Decision

1. **`commissioning-airflow-adjust-write`** — operator command: resolve **`automatic_airflow_adjustment`** on a **`--step-id`**, **`WriteProperty`** **`presentValue`** on **`actuator_object_id`** with **`--fan-command-percent`** (0–100). When the step **`arms_test_mode_state_key`** is **`airflow_verify`**, require BACnet **`msv_test_mode`** **state 3** before writing (same safety idea as valve stroke MSV arm). Enforce **write allowlist** + **`writable`**.
2. **`commissioning-confirm-tachometer-reference`** — resolve **`operator_confirm_tachometer_reference`** on **`--step-id`**, BACnet-read **`read_object_id`**, persist profile **`session_key`** with **`value: "true"`** (truthy for gates) and **`reading_value_str`** holding the BACnet text (numeric readings are **not** used alone as `value` because **`record-step`** truthy checks treat plain numbers as non-confirming).
3. **`record-step` gates** — after prerequisite ordering: if the step has **`operator_confirm_tachometer_reference`**, require the session key truthy before **`passed` / `manual_passed`**. If an **`automatic_airflow_adjustment`** action lists optional **`tachometer_reference_session_key`** (same string as the tachometer step’s **`session_key`**), require that flag before passing the **adjustment** step (links “wrote fan %” to “technician confirmed tacho”).
4. **`compile-import`** — copy profile **`unit_specs`** into each controller’s **`commissioning_meta`** so the adjust CLI can echo **design_supply_airflow_L_s** (and future fields) without re-reading profile JSON at runtime.
5. **`commissioning-record-manual-airflow`** — for **`manual_airflow_verification_assisted`**, record **`--measured-flow-L-s`** and **`--measurement-tool`** under the derived or overridden session keys; **`record-step passed`** requires non-empty measured values for each listed **`branch_id`**. **`compile-import`** also copies **`airflow_verification`** into **`commissioning_meta`** for tool/design validation.

## Consequences

- **Profiles** opt into the adjustment-step gate by adding **`tachometer_reference_session_key`**; the shipped **`unit-profile-fcu.example.json`** omits it so existing **`record-step`** demos against **`docs/examples`** stay unchanged.
- **Manual airflow steps** in the shipped FCU example gain a **hard gate** on pass until **`commissioning-record-manual-airflow`** is run for **`supply_terminal_main`** (or profile overrides **`session_keys`**).
- Interlocks that compare **live tachometer vs session reference** remain **profile / future engine** work beyond this CLI slice.
