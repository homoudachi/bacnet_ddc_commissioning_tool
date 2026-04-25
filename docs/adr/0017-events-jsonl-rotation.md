# ADR 0017: `logs/events.jsonl` size rotation and retention

## Status

Accepted

## Context

Commissioning commands append JSON Lines to **`logs/events.jsonl`** per run directory. Long jobs (many modulation steps, BACnet retries) can grow that file without bound. Operators and CI need a **predictable disk cap** without changing the append-only audit semantics of each line.

## Decision

1. **Size-based rotation only** (no time-based rotation): before each append, if **`events.jsonl`** exceeds **`rotate_max_bytes`**, rename the current file to **`events.jsonl.1`**, shift existing **`events.jsonl.N` → `events.jsonl.(N+1)`**, and delete the oldest archive so the **total** retained file count is **`retention_files`** (active + numbered archives).
2. **Defaults:** **`rotate_max_bytes` = 16 MiB**, **`retention_files` = 8** (≈128 MiB worst case per run for this log family).
3. **`init-run`** writes an **`events_log`** object into **`config/runtime-config.json`** with those defaults so runs are self-describing; operators may edit JSON for long campaigns.
4. **Environment overrides** (portable exe / automation without editing run config):
   - **`COMMISSIONING_EVENTS_MAX_BYTES`** — integer bytes or suffix **`k` / `m` / `g`** (e.g. `2m`, `512k`).
   - **`COMMISSIONING_EVENTS_RETENTION_FILES`** — integer **≥ 2** (total files including active).
   When set, env wins over **`runtime-config.json`** for that key.

Implementation lives in **`tools/runtime/events_log.py`**; **`tools/runtime/app.py`** calls **`maybe_rotate_events_jsonl(run_dir)`** inside **`_append_event`** (same process as the writer, so rotation is atomic enough for commissioning use).

## Consequences

- **`events.jsonl.1`**, **`events.jsonl.2`**, … may appear under **`logs/`**; tools that only tail **`events.jsonl`** still see the live tail; full audit may require concatenating archives **newest-first** or reading all matching files.
- Very small **`rotate_max_bytes`** in tests causes frequent rotation; production should keep defaults unless disk is tight.
- Time-based or line-count rotation remains out of scope unless a future ADR adds it.
