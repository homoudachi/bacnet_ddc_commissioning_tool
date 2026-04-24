# ADR 0008 — Docker BACnet/IP lab device (bacnet-dev)

## Status

Accepted

## Context

Unit tests use an in-process UDP fake. Operators and CI still need a **portable** BACnet endpoint that matches **real UDP** semantics without physical panels. The previous `docker/simulator/docker-compose.yml` referenced **non-existent** placeholder images.

## Decision

1. Add **`docker/simulator/bacnet-device/`**: Python 3.12 + **bacpypes3**, UDP server with Who-Is / ReadProperty / WriteProperty **presentValue**; **`SIM_PROFILE=fcu`** matches FCU unittest fake instances; **`SIM_PROFILE=hrv`** matches **`docs/examples/unit-profile-hrv.example.json`** (MSV **60**, fan commands, temps, BI **9**).
2. **`bacnet-dev`** profile: **three** services on **`127.0.0.1:47808`**, **`47809`**, **`47810`** (FCU ×2 + HRV-shaped sim).
3. **`docs/examples/site-controllers.docker-bacnet-sim.csv`**: **`FCU-DOCKER`**, **`FCU-DOCKER-B`**, **`HRV-DOCKER`**.
4. CI: **`docker_bacnet_smoke.sh`** → **`verify-bip-list --strict`**, **`bacnet-read`** spot checks (including HRV **`ai_supply_air_temperature`** — allowlist extended in **`unit-profile-hrv.example.json`**), **`dry-run-bacnet-write --execute`** + read-back on **`msv_test_mode`** for FCU and HRV, and **`bacnet-point-checkout`**, when Docker is available.

## Consequences

- Multi-device / BBMD / macvlan topologies remain **documentation-only** until separate images exist.
- Host port **47808** must be free when using the published mapping.
