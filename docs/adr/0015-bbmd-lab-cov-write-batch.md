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
   - **`bacnet-bbmd-lab`**: BACpypes3 **BBMDApplication** sidecar (`bbmd_runner.py`) on host UDP **47830**, with **BDT** peer **`172.29.0.255:47808`** (directed broadcast into the isolated **`172.29.0.0/24`** bridge).
   - **`bacnet-fcu-bbmd-isolated`**: FCU-shaped sim on **`172.29.0.10:47808`** (device instance **21004**) reachable only from the lab networks (not published on localhost).
   - **`bacnet-bbmd-probe`**: one-shot **foreign device** client (`probe_foreign_read.py`) using **`network_mode: service:bacnet-bbmd-lab`**, registering with the local BBMD and reading **`analogInput,2`** from the isolated device.
2. **COV in lab sim** (`docker/simulator/bacnet-device/server.py`): handles **SubscribeCOV** for **FCU `analogInput,2`** and **HRV `analogInput,15`** (supply air); sends **UnconfirmedCOVNotification** on subscribe and after matching **WriteProperty** / **WritePropertyMultiple**; cancel via SubscribeCOV with null lifetime/confirmed per BACnet stack behavior.
3. **WritePropertyMultiple in lab sim**: same `server.py` handles **WritePropertyMultiple** for **present-value** on the same object set as single **WriteProperty** (all writes in the APDU must succeed or the sim sends no ack). **ReadPropertyMultiple** for **present-value** supports **`bacnet-point-checkout`** batching (**ADR 0016**) and **`bacnet-read-batch`** (**ADR 0018**).
4. **Adapter + CLI**:
   - **`CommissioningBACnetAdapter.subscribe_cov_unconfirmed_wait_value`** → **`bacnet-subscribe-cov`** (requires prior read allowlist + successful read).
   - **`CommissioningBACnetAdapter.write_present_values_batch`** → **`bacnet-write-batch --execute --mode sequential`** (sequential WriteProperty, single NormalApplication / Who-Is).
   - **`CommissioningBACnetAdapter.write_present_values_property_multiple`** → **`bacnet-write-batch --execute --mode multiple`** (one **WritePropertyMultiple** confirmed service; **not** all field panels support it).
   - **`bacnet-read-batch`** → **`--mode multiple`** (ReadPropertyMultiple) or **`--mode sequential`** (ReadProperty chain); see **ADR 0018**.
5. **macvlan bench**: optional compose overlay **`docker-compose.macvlan.example.yml`** + runbook **`docs/simulator/macvlan-lab.md`** (host-specific; not default CI).

## Consequences

- Default **`bacnet-dev`** CI includes **`bacnet-subscribe-cov`**, **`bacnet-write-batch`** (sequential + **multiple**), **`bacnet-read-batch`**, and related smoke assertions in `docker_bacnet_smoke.sh`.
- BBMD lab is **additional** CI when Docker is available (`docker_bbmd_lab_smoke.sh`).
- COV coverage is **narrow** (subset of objects); extending objects requires sim + tests.
- **WritePropertyMultiple** is implemented for the **lab sim** and the **commissioning client**; real panels may reject or partially support the service—operators should fall back to **`--mode sequential`** when needed.
