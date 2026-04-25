"""operator-gui / operator_gui_server (Tier B2)."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "tools" / "runtime" / "app.py"


class OperatorGuiTests(unittest.TestCase):
    def test_operator_gui_help(self) -> None:
        r = subprocess.run(
            [sys.executable, str(RUNTIME), "operator-gui", "--help"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, r.returncode, msg=r.stderr)
        self.assertIn("--gui-port", r.stdout)

    def test_operator_gui_server_page_contains_allowlisted_commands(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        body = mod._page(ROOT).decode("utf-8")
        self.assertIn("commissioning-guided-next", body)
        self.assertIn("record-step", body)
        self.assertIn("commissioning-airflow-closed-loop-iterate", body)
        self.assertIn("/guided", body)

    def test_guided_page_contains_flow_ui_and_api_paths(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs2", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        body = mod._guided_page(ROOT).decode("utf-8")
        self.assertIn("/api/v1/list-flows", body)
        self.assertIn("/api/v1/guidance", body)
        self.assertIn("/api/v1/record-step", body)
        self.assertIn("Quick read", body)
        self.assertIn("bacnet-quick-read", body)
        self.assertIn("bacnet-quick-read-batch", body)
        self.assertIn("Guided commissioning", body)

    def test_guided_api_command_allowlist_includes_point_checkout(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs3", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIn("bacnet-point-checkout", mod._GUIDED_API_COMMANDS)
        self.assertIn("bacnet-read-batch", mod._GUIDED_API_COMMANDS)
        self.assertIn("dry-run-bacnet-write", mod._GUIDED_API_COMMANDS)
        self.assertIn("bacnet-read-batch", mod.ALLOWED_PREFIXES)

    def test_build_step_hints_valve_and_modulation(self) -> None:
        import importlib.util
        import tempfile

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs4", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as td:
            rd = pathlib.Path(td)
            (rd / "state" / "flows").mkdir(parents=True)
            (rd / "state").mkdir(parents=True, exist_ok=True)
            flow = {
                "controller_label": "FCU-1",
                "steps": [
                    {
                        "step_id": "cooling_valve_stroke_no_chw",
                        "label": "Valve",
                        "status": "pending",
                        "actions": [
                            {
                                "type": "operator_prompt_confirm",
                                "prompt_id": "chw_valve_at_100",
                                "prompt_text": "Confirm",
                            },
                            {
                                "type": "modulate_actuator_log_sat_for_report",
                                "command_object_id": "ao_chw_valve",
                                "result_supply_temperature_object_id": "ai_sat",
                            },
                        ],
                    }
                ],
            }
            (rd / "state" / "flows" / "FCU-1.json").write_text(
                __import__("json").dumps(flow), encoding="utf-8"
            )
            job = {
                "controllers": [
                    {
                        "controller_label": "FCU-1",
                        "commissioning_meta": {
                            "airflow_verification": {
                                "branches": [
                                    {
                                        "id": "supply_terminal_main",
                                        "design_flow_L_s": 100.0,
                                        "measurement": {"allowed_tools": ["balometer"]},
                                    }
                                ]
                            }
                        },
                    }
                ]
            }
            (rd / "state" / "runtime-job.json").write_text(
                __import__("json").dumps(job), encoding="utf-8"
            )
            hints = mod._build_step_hints(
                run_dir=rd, controller_label="FCU-1", step_id="cooling_valve_stroke_no_chw"
            )
            self.assertNotIn("error", hints)
            ids = [f["id"] for f in hints["forms"]]
            self.assertIn("valve_prompt", ids)
            self.assertIn("modulation_sweep", ids)

            hints2 = mod._build_step_hints(
                run_dir=rd, controller_label="FCU-1", step_id="manual_airflow_verify_half_then_design"
            )
            self.assertEqual(hints2.get("error"), "step_not_found")

    def test_session_state_path_helper(self) -> None:
        import importlib.util
        import tempfile

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs5", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            rd = pathlib.Path(td)
            sp = mod._session_state_path(rd, "FCU-1")
            self.assertFalse(sp.is_file())


if __name__ == "__main__":
    unittest.main()
