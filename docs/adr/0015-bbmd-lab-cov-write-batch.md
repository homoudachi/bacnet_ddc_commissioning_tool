# ADR 0015 — BBMD lab topology, COV subscribe, and write batching

## Status

Accepted

## Context

Post–v1 work needed:

1. A **repeatable** way to exercise **BACnet/IP BBMD + foreign device** forwarding without relying on customer site BBMD tables.
2. **SubscribeCOV** / unconfirmed notifications for commissioning workflows that prefer push over polling.
3. **Write batching** (fewer Who-Is / stack setups) when touching multiple writable points on the same controller in one operator action.

## Decision

1. **Docker profile `bacnet-bbmd-lab`** (`docker/simulator/docker-compose.yml`):
   - **`bacnet-bbmd-lab`**: BACpypes3 **BBMDApplication** sidecar (`bbmd_runner.py`) on host UDP **47830**, with **BDT** peer **`172.29.255.255:47808`** (directed broadcast into the isolated bridge).
   - **`bacnet-fcu-bbmd-isolated`**: FCU-shaped sim on **`172.29.0.10:47808`** (device instance **21004**) reachable only from the lab networks (not published on localhost).
   - **`bacnet-bbmd-probe`**: one-shot **foreign device** client (`probe_foreign_read.py`) using **`network_mode: service:bacnet-bbmd-lab`**, registering with the local BBMD and reading **`analogInput,2`** from the isolated device.
2. **COV in lab sim** (`docker/simulator/bacnet-device/server.py`): handles **SubscribeCOV** for **FCU `analogInput,2`** and **HRV `analogInput,15`** (supply air); sends **UnconfirmedCOVNotification** on subscribe and after matching **WriteProperty**; cancel via SubscribeCOV with null lifetime/confirmed per BACnet stack behavior.
3. **Adapter + CLI**:
   - **`CommissioningBACnetAdapter.subscribe_cov_unconfirmed_wait_value`** → **`bacnet-subscribe-cov`** (requires prior read allowlist + successful read).
   - **`CommissioningBACnetAdapter.write_present_values_batch`** → **`bacnet-write-batch --execute`** (sequential WriteProperty, single NormalApplication / Who-Is).
4. **macvlan bench**: optional compose overlay **`docker-compose.macvlan.example.yml`** + runbook **`docs/simulator/macvlan-lab.md`** (host-specific; not default CI).

## Consequences

- Default **`bacnet-dev`** CI behavior is unchanged except **extra smoke steps** (`bacnet-subscribe-cov`, `bacnet-write-batch`) in `docker_bacnet_smoke.sh`.
- BBMD lab is **additional** CI when Docker is available (`docker_bbmd_lab_smoke.sh`).
- COV coverage is **narrow** (subset of objects); extending objects requires sim + tests.
- **WritePropertyMultiple** (true single APDU multi-object) is **not** implemented; “batching” here means **one stack session, sequential writes**.
