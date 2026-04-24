"""Smoke for tools/import/benchmark_compile.py (no large CSV committed)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCH = ROOT / "tools" / "import" / "benchmark_compile.py"


class BenchmarkCompileTests(unittest.TestCase):
    def test_benchmark_runs_small_sheet(self) -> None:
        r = subprocess.run(
            [sys.executable, str(BENCH), "--rows", "120"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, r.returncode, msg=r.stderr + r.stdout)
        out = json.loads(r.stdout.strip())
        self.assertEqual(120, out["rows"])
        self.assertTrue(out["compile_ok"])
        self.assertEqual(120, out["controller_count"])
        self.assertIsNotNone(out.get("seconds"))


if __name__ == "__main__":
    unittest.main()
