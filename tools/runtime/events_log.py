"""Size-based rotation for per-run ``logs/events.jsonl`` (JSON Lines audit)."""

from __future__ import annotations

import json
import os
from pathlib import Path


_DEFAULT_ROTATE_MAX_BYTES = 16 * 1024 * 1024
_DEFAULT_RETENTION_FILES = 8


def events_jsonl_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "events.jsonl"


def _parse_positive_int(raw: str, *, name: str) -> int:
    text = str(raw).strip().lower().replace("_", "")
    if not text:
        raise ValueError(f"{name}: empty")
    mult = 1
    if text.endswith("k"):
        mult = 1024
        text = text[:-1]
    elif text.endswith("m"):
        mult = 1024 * 1024
        text = text[:-1]
    elif text.endswith("g"):
        mult = 1024 * 1024 * 1024
        text = text[:-1]
    value = int(float(text) * mult)
    if value < 1:
        raise ValueError(f"{name}: must be >= 1")
    return value


def events_log_limits_from_env() -> tuple[int | None, int | None]:
    """Return (rotate_max_bytes, retention_files) or None if env not set."""
    max_b: int | None = None
    ret_f: int | None = None
    raw_max = os.environ.get("COMMISSIONING_EVENTS_MAX_BYTES", "").strip()
    if raw_max:
        max_b = _parse_positive_int(raw_max, name="COMMISSIONING_EVENTS_MAX_BYTES")
    raw_ret = os.environ.get("COMMISSIONING_EVENTS_RETENTION_FILES", "").strip()
    if raw_ret:
        ret_f = int(raw_ret)
        if ret_f < 2:
            raise ValueError("COMMISSIONING_EVENTS_RETENTION_FILES must be >= 2")
    return max_b, ret_f


def events_log_config(run_dir: Path) -> dict[str, int]:
    """Effective rotation config: runtime-config ``events_log`` merged with defaults; env wins."""
    env_max, env_ret = events_log_limits_from_env()
    rotate = env_max if env_max is not None else _DEFAULT_ROTATE_MAX_BYTES
    retention = env_ret if env_ret is not None else _DEFAULT_RETENTION_FILES

    cfg_path = run_dir / "config" / "runtime-config.json"
    if cfg_path.is_file():
        try:
            doc = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
        el = doc.get("events_log")
        if isinstance(el, dict):
            if env_max is None:
                raw = el.get("rotate_max_bytes", rotate)
                try:
                    rotate = int(raw)
                except (TypeError, ValueError):
                    rotate = _DEFAULT_ROTATE_MAX_BYTES
            if env_ret is None:
                raw_r = el.get("retention_files", retention)
                try:
                    retention = int(raw_r)
                except (TypeError, ValueError):
                    retention = _DEFAULT_RETENTION_FILES

    if rotate < 1:
        rotate = 1
    if retention < 2:
        retention = 2
    return {"rotate_max_bytes": rotate, "retention_files": retention}


def maybe_rotate_events_jsonl(run_dir: Path) -> None:
    """If ``events.jsonl`` exceeds configured size, archive it as ``.1`` and shift older ``.N`` up.

    ``retention_files`` is the **total** number of files kept: one active ``events.jsonl`` plus
    archived ``events.jsonl.1`` … ``events.jsonl.(retention_files - 1)``.
    """
    log_path = events_jsonl_path(run_dir)
    if not log_path.is_file():
        return

    cfg = events_log_config(run_dir)
    max_bytes = int(cfg["rotate_max_bytes"])
    retention = int(cfg["retention_files"])

    try:
        size = log_path.stat().st_size
    except OSError:
        return
    if size <= max_bytes:
        return

    logs_dir = log_path.parent
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Highest archive suffix = retention - 1 (active file has no suffix).
    k = max(1, retention - 1)
    oldest = logs_dir / f"events.jsonl.{k}"
    try:
        oldest.unlink(missing_ok=True)
    except OSError:
        pass

    for idx in range(k - 1, 0, -1):
        src = logs_dir / f"events.jsonl.{idx}"
        if src.is_file():
            dst = logs_dir / f"events.jsonl.{idx + 1}"
            try:
                src.replace(dst)
            except OSError:
                return

    try:
        log_path.replace(logs_dir / "events.jsonl.1")
    except OSError:
        return


def default_events_log_section() -> dict[str, int]:
    return {
        "rotate_max_bytes": _DEFAULT_ROTATE_MAX_BYTES,
        "retention_files": _DEFAULT_RETENTION_FILES,
    }
