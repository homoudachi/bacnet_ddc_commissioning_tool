# ADR 0008 — Docker BACnet/IP lab device (bacnet-dev)

## Status

Accepted

## Context

Unit tests use an in-process UDP fake. Operators and CI still need a **portable** BACnet endpoint that matches **real UDP** semantics without physical panels. The previous `docker/simulator/docker-compose.yml` referenced **non-existent** placeholder images.

## Decision

1. Add **`docker/simulator/bacnet-device/`**: Python 3.12 + **bacpypes3**, UDP server with Who-Is / ReadProperty / WriteProperty **presentValue**; **`SIM_PROFILE=fcu`** matches FCU unittest fake instances; **`SIM_PROFILE=hrv`** matches **`docs/examples/unit-profile-hrv.example.json`** (MSV **60**, fan commands, temps, BI **9**).
2. **`bacnet-dev`** profile: **four** services on **`127.0.0.1:47808`**, **`47809`**, **`47810`**, **`47811`** (FCU ×3 + HRV-shaped sim).
3. **`docs/examples/site-controllers.docker-bacnet-sim.csv`**: **`FCU-DOCKER`**, **`FCU-DOCKER-B`**, **`FCU-DOCKER-C`**, **`HRV-DOCKER`**. FCU rows use profile **`fcu_2pipe_chw_electric_heat_docker_sim_v1`** (**`unit-profile-fcu.docker-bacnet-sim.example.json`**) so CI can allowlist **analog** writes (**`av_electric_heat_command`**, **`ao_chw_valve`**) without changing the canonical **`unit-profile-fcu.example.json`**.
4. CI: **`docker_bacnet_smoke.sh`** → **`verify-bip-list --strict`**, **`bacnet-read`** spot checks (FCU **`ai_sat`** on all three FCU rows; HRV **`msv_test_mode`**, **`ai_supply_air_temperature`**, **`av_supply_fan_command`**, **`av_exhaust_fan_command`**), **`dry-run-bacnet-write --execute`** + read-back on **`msv_test_mode`** (FCU + HRV), **analog** writes + read-back on FCU heat AV / valve AO and HRV fan command AVs, and **`bacnet-point-checkout`**, when Docker is available.

## Consequences

- Multi-device / BBMD / macvlan topologies remain **documentation-only** until separate images exist.
- Host port **47808** must be free when using the published mapping.
