"""CI guard: generated unified commissioning CSV schema doc matches code."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
GEN = ROOT / "tools" / "schema" / "gen_commissioning_report_unified_csv_doc.py"


class UnifiedCommissioningCsvSchemaDocTests(unittest.TestCase):
    def test_generated_schema_doc_matches_code(self) -> None:
        r = subprocess.run(
            [sys.executable, str(GEN), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            0,
            r.returncode,
            msg=(r.stderr or r.stdout or "gen_commissioning_report_unified_csv_doc.py --check failed"),
        )


if __name__ == "__main__":
    unittest.main()
