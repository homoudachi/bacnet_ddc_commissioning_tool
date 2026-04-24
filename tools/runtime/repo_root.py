"""Resolve repository root (directory that contains ``tools/``).

Supports **PyInstaller** ``--onefile`` / ``--onedir`` bundles: bundled data lives under
``sys._MEIPASS`` when ``sys.frozen`` is true.
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    """Absolute path to repo root (contains ``tools/`` and ``docs/``)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass).resolve()
            if (base / "tools").is_dir():
                return base
    return Path(__file__).resolve().parents[2]
