# ADR 0005 — Commissioning BACnet adapter façade

## Status

Accepted

## Context

The runtime mixed two concerns: **minimal UDP Who-Is / I-Am probes** (`bip_adapter.py`) and **BACpypes3 ReadProperty / WriteProperty** (`bacpypes_client.py`). Call sites imported each module separately, which makes it harder to evolve timeouts, discovery policy, or swap implementations without touching every command.

## Decision

Introduce **`tools/bacnet/adapter.py`** with **`CommissioningBACnetAdapter`**: a small façade that exposes **probe**, **plan_write_property** (dry-run path), **read_present_value**, **write_present_value**, and batched **read / write property multiple** helpers (see **ADR 0015** / **ADR 0016**), plus helpers such as **`format_ipv4_target`**, **`present_value_property_id`**, and **derived timeouts** (`effective_who_is_timeout`, `commissioning_apdu_timeout_seconds(override=None)`) so CLI commands do not duplicate magic numbers and can pass an optional **APDU timeout override** validated in one place. The runtime CLI loads this class once (lazy singleton) and routes all BACnet I/O through it. **`bip_adapter.py`** and **`bacpypes_client.py`** remain the low-level implementations.

## Consequences

- New commissioning features should call the **adapter** first; extend the façade when adding operations (e.g. subscribe) rather than importing BACpypes from scattered modules.
- The façade still uses dynamic `importlib` loading of sibling files (same packaging constraints as before); a future package layout could replace that without changing CLI behavior.
- Unit tests can mock **`_bip_mod`** / **`_client_mod`** on the adapter instance for focused tests.
