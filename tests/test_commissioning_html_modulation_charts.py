"""Unified HTML export: inline SVG modulation charts (Tier A2)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "tools" / "runtime" / "app.py"


def _load_app():
    sys.path.insert(0, str(APP.parent))
    spec = importlib.util.spec_from_file_location("rt_app_charts", APP)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CommissioningHtmlModulationChartsTests(unittest.TestCase):
    def test_unified_html_includes_modulation_chart_section(self) -> None:
        mod = _load_app()
        doc = {
            "job_id": "chart-job",
            "schema_version": "0.2-commissioning-report",
            "entries": [
                {
                    "kind": "thermal_modulation_sweep",
                    "ts": "2026-01-01T00:00:00Z",
                    "controller_label": "FCU-CHART",
                    "step_id": "heat",
                    "report_ref": "",
                    "technician_name": "Test",
                    "command_object_id": "av_electric_heat_command",
                    "command_percent": 40,
                    "dwell_seconds": 0.1,
                    "readings": [
                        {
                            "logical_object_id": "ai_sat",
                            "status": "read_ok",
                            "value_str": "20.0",
                            "source": "bacnet",
                        },
                    ],
                },
                {
                    "kind": "thermal_modulation_sweep",
                    "ts": "2026-01-01T00:00:00Z",
                    "controller_label": "FCU-CHART",
                    "step_id": "heat",
                    "report_ref": "",
                    "technician_name": "Test",
                    "command_object_id": "av_electric_heat_command",
                    "command_percent": 60,
                    "dwell_seconds": 0.1,
                    "readings": [
                        {
                            "logical_object_id": "ai_sat",
                            "status": "read_ok",
                            "value_str": "24.5",
                            "source": "bacnet",
                        },
                    ],
                },
            ],
        }
        rows = mod._commissioning_report_unified_csv_rows(doc)
        html = mod._commissioning_report_unified_rows_to_html(
            "chart-job", "0.2-commissioning-report", rows, doc=doc
        )
        self.assertIn("commissioning-mod-chart", html)
        self.assertIn("Modulation (command % vs SAT)", html)
        self.assertIn("FCU-CHART", html)


if __name__ == "__main__":
    unittest.main()
