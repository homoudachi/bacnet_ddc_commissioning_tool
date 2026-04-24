"""Ensure docs/schema/commissioning-report-unified-csv-v1.md matches runtime column order."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_DIR = str(ROOT / "tools" / "runtime")
SCHEMA_DOC = ROOT / "docs" / "schema" / "commissioning-report-unified-csv-v1.md"
RUNTIME_APP = ROOT / "tools" / "runtime" / "app.py"


def _load_commissioning_report_unified_fieldnames() -> tuple[str, ...]:
    if RUNTIME_DIR not in sys.path:
        sys.path.insert(0, RUNTIME_DIR)
    spec = importlib.util.spec_from_file_location("runtime_app_schema_test", RUNTIME_APP)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNTIME_APP}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return tuple(mod.COMMISSIONING_REPORT_UNIFIED_FIELDNAMES)


def _columns_from_schema_markdown(text: str) -> list[str]:
    if "## Column list (order)" not in text:
        raise ValueError("schema doc missing Column list section")
    section = text.split("## Column list (order)", 1)[1]
    if "## `" in section:  # next ## heading starting with backtick e.g. ## `kind`
        section = section.split("## `", 1)[0]
    elif "## " in section[1:]:
        # fallback: first ## after column section (kind table uses ## `kind`)
        idx = section.find("\n## ", 1)
        if idx != -1:
            section = section[:idx]
    cols: list[str] = []
    for line in section.splitlines():
        m = re.match(r"^\|\s*`([^`]+)`\s*\|", line.strip())
        if m:
            cols.append(m.group(1))
    return cols


class UnifiedCommissioningCsvSchemaDocTests(unittest.TestCase):
    def test_schema_doc_column_order_matches_code(self) -> None:
        doc_text = SCHEMA_DOC.read_text(encoding="utf-8")
        doc_cols = _columns_from_schema_markdown(doc_text)
        code_cols = list(_load_commissioning_report_unified_fieldnames())
        self.assertEqual(
            code_cols,
            doc_cols,
            msg=(
                "Update docs/schema/commissioning-report-unified-csv-v1.md or "
                "COMMISSIONING_REPORT_UNIFIED_FIELDNAMES in tools/runtime/app.py so they match."
            ),
        )


if __name__ == "__main__":
    unittest.main()
