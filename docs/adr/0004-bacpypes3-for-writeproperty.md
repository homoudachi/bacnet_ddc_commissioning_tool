# ADR 0004: BACpypes3 for WriteProperty; minimal UDP for smoke probes

## Status

Accepted (2026-04-23)

## Context

The repository needs BACnet/IP **Who-Is / I-Am** style checks without pulling a full protocol stack into every test path, while commissioning workflows must eventually issue **WriteProperty** (e.g. MSV test mode) with correct encoding and vendor context.

## Decision

- Keep **`tools/bacnet/bip_adapter.py`** as a **minimal UDP** helper for list-style **probe** smoke tests (no dependency on BACpypes).
- Use **[BACpypes3](https://bacpypes3.readthedocs.io/)** for **WriteProperty** and richer client flows (`tools/bacnet/bacpypes_client.py`), installed via **`requirements.txt`**.
- **Write allowlist** is **profile-authored**: `commissioning_write_allowlist` array of logical `objects[].id` values; the compiler copies it onto each controller row. Runtime still requires `writable: true` and a resolvable `objects_by_id` entry.

## Consequences

- CI and developers must `pip install -r requirements.txt` before `--execute` works; unit tests that only use `bip_adapter` still run without BACpypes for the probe path.
- Profile authors explicitly declare which logical objects may be written, separate from the full object map.
