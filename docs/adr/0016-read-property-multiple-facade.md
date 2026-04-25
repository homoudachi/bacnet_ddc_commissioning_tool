# ADR 0016: ReadPropertyMultiple in commissioning BACnet façade

## Status

Accepted

## Context

Point checkout and similar flows issued **one ReadProperty per object**, which is correct but chatty on multi-point profiles. **WritePropertyMultiple** was already exposed for batched writes (**ADR 0015**). Operators benefit from a symmetric **ReadPropertyMultiple** path when the device supports it.

## Decision

1. **`tools/bacnet/bacpypes_client.py`:** add `read_present_values_property_multiple`, calling BACpypes3 `NormalApplication.read_property_multiple` with a list of `(object_type, object_instance, property_name)` after a single Who-Is to the target.
2. **`CommissioningBACnetAdapter`:** delegate `read_present_values_property_multiple` to the client module (same pattern as write batching).
3. **`bacnet-point-checkout` / automatic checkout on `record-step`:** when **two or more** resolved checkout rows exist, use **one** ReadPropertyMultiple (plus one B/IP probe) by default; merge results into the same per-row JSON shape as sequential ReadProperty (each row includes `bacnet_service: readPropertyMultiple`).
4. **Escape hatch:** `--no-read-property-multiple` on `bacnet-point-checkout` and `--bacnet-checkout-no-read-property-multiple` on `record-step` force per-point ReadProperty (debug or broken peers).
5. **Docker lab sim:** handle **ReadPropertyMultiple** for **present-value** only, mirroring ReadProperty behavior, so CI exercises the full stack.

## Consequences

- Fewer round trips for typical FCU profiles with four checkout points.
- Artifacts include `bacnet_read_property_multiple: true|false` on `bacnet-point-checkout` payloads for transparency.
- Devices that reject RPM still work when operators pass the opt-out flags (or when only one point resolves).
