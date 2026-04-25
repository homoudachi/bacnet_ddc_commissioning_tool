# ADR 0018: `bacnet-read-batch` (ReadPropertyMultiple + sequential fallback)

## Status

Accepted

## Context

Operators sometimes need **several allowlisted reads** on one controller in one action (checkout bursts, quick diagnostics). **`bacnet-read`** is one object at a time. **ReadPropertyMultiple** reduces round trips when the device supports it; some panels do not.

## Decision

1. Add CLI **`bacnet-read-batch`** with repeatable **`--read OBJECT_ID[:property]`** (default property **`presentValue`**), same **read allowlist** and **`objects_by_id`** resolution as **`bacnet-read`**.
2. **`--mode multiple`** (default): one **ReadPropertyMultiple** confirmed service after the usual **B/IP probe** + **Who-Is** (BACpypes3 `read_property_multiple` with a **flat** parameter list per stack API).
3. **`--mode sequential`**: one **Who-Is**, then **ReadProperty** per object (stops on first BACnet error; partial rows returned).
4. **Lab sim** (`docker/simulator/bacnet-device/server.py`): answer **ReadPropertyMultiple** for **present-value** on the same object set as **ReadProperty**, so CI can exercise the path.
5. **Artifacts / audit**: write **`artifacts/bacnet_reads/<controller>-read-batch.json`** and append **`bacnet_read_batch`** to **`logs/events.jsonl`**.

## Consequences

- Default **`docker_bacnet_smoke.sh`** includes a **`bacnet-read-batch`** assertion for **FCU-DOCKER**.
- Field devices that reject RPM: use **`--mode sequential`** (or split into separate **`bacnet-read`** calls).
