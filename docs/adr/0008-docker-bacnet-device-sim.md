# ADR 0008 — Docker BACnet/IP lab device (bacnet-dev)

## Status

Accepted

## Context

Unit tests use an in-process UDP fake. Operators and CI still need a **portable** BACnet endpoint that matches **real UDP** semantics without physical panels. The previous `docker/simulator/docker-compose.yml` referenced **non-existent** placeholder images.

## Decision

1. Add **`docker/simulator/bacnet-device/`**: Python 3.12 + **bacpypes3**, UDP server with Who-Is / ReadProperty / WriteProperty **presentValue** for the same object instances as the unittest fake (FCU-shaped).
2. Replace root **`docker/simulator/docker-compose.yml`** with a minimal **`bacnet-dev`** profile that **builds** that image and publishes **`127.0.0.1:47808/udp`** (plus a **second** instance on **`127.0.0.1:47809`** / device **21002** for multi-row list checks).
3. Add **`docs/examples/site-controllers.docker-bacnet-sim.csv`** (two rows: **`FCU-DOCKER`**, **`FCU-DOCKER-B`**).
4. CI: run **`tools/simulator/docker_bacnet_smoke.sh`** after unit tests (script **no-ops** if `docker` is missing; otherwise **`verify-bip-list --strict`** must pass for **both** rows).

## Consequences

- Multi-device / BBMD / macvlan topologies remain **documentation-only** until separate images exist.
- Host port **47808** must be free when using the published mapping.
