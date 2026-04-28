"""operator-gui / operator_gui_server (Tier B2)."""

from __future__ import annotations

import json
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
        self.assertIn("/dashboard", body)

    def test_dashboard_page_contains_api_paths(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs_dash", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        body = mod._dashboard_page(ROOT).decode("utf-8")
        self.assertIn("/api/v1/dashboard-controllers", body)
        self.assertIn("/api/v1/dashboard-probe", body)
        self.assertIn("dash-grid", body)
        self.assertIn("/guided?controller=", body)
        self.assertIn("Open in guided", body)
        self.assertIn("bacnet_op_technician_name", body)
        self.assertIn("dash-flow-block", body)
        self.assertIn("Read mode / MSV", body)
        self.assertIn("Refresh I/O snapshot", body)

    def test_dashboard_controller_summaries(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs_sum", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        job = {
            "controllers": [
                {
                    "controller_label": "FCU-A",
                    "profile_id": "p1",
                    "bacnet": {"host": "10.0.0.1", "port": 47808, "device_instance": 21001},
                    "commissioning_read_allowlist": ["a", "b"],
                    "commissioning_write_allowlist": ["c"],
                    "point_checkout": [
                        {"object_id": "ai_sat", "property": "presentValue"},
                        {"object_id": "msv_test_mode", "property": "presentValue"},
                    ],
                    "objects_by_id": {
                        "msv_test_mode": {
                            "bacnet": {"object_type": "multiStateValue", "instance": 50},
                            "writable": True,
                        }
                    },
                }
            ]
        }
        rows = mod._dashboard_controller_summaries(job)
        self.assertEqual(1, len(rows))
        self.assertEqual("FCU-A", rows[0]["controller_label"])
        self.assertEqual("p1", rows[0]["profile_id"])
        self.assertEqual("10.0.0.1", rows[0]["bacnet_host"])
        self.assertEqual(47808, rows[0]["bacnet_port"])
        self.assertEqual(21001, rows[0]["bacnet_device_instance"])
        self.assertEqual(2, rows[0]["read_allowlist_count"])
        self.assertEqual(1, rows[0]["write_allowlist_count"])
        self.assertEqual(["ai_sat", "msv_test_mode"], rows[0]["dashboard_io_reads"])
        self.assertEqual("msv_test_mode", rows[0]["dashboard_test_mode_object_id"])
        self.assertFalse(rows[0]["flow_initialized"])

        import tempfile

        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td)
            flows = run_dir / "state" / "flows"
            flows.mkdir(parents=True)
            flow_payload = {
                "controller_label": "FCU-A",
                "steps": [
                    {"step_id": "s1", "label": "One", "status": "passed"},
                    {"step_id": "s2", "label": "Two", "status": "pending"},
                ],
            }
            (flows / "FCU-A.json").write_text(json.dumps(flow_payload), encoding="utf-8")
            rows2 = mod._dashboard_controller_summaries(job, run_dir=run_dir)
            self.assertTrue(rows2[0]["flow_initialized"])
            self.assertEqual(2, rows2[0]["flow_step_count"])
            self.assertEqual("s2", rows2[0]["flow_next_step_id"])
            self.assertFalse(rows2[0]["flow_complete"])

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
        self.assertIn("Quick BACnet", body)
        self.assertIn("bacnet-quick-read", body)
        self.assertIn("bacnet-quick-read-batch", body)
        self.assertIn("Guided commissioning", body)
        self.assertIn("/dashboard", body)
        self.assertIn("stepFilter", body)
        self.assertIn("btnJumpNext", body)
        self.assertIn("Jump to next open step", body)
        self.assertIn("bacnet_op_technician_name", body)
        self.assertIn("Shared technician name", body)

    def test_guided_api_command_allowlist_includes_point_checkout(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs3", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIn("bacnet-point-checkout", mod._GUIDED_API_COMMANDS)
        self.assertIn("bacnet-read-batch", mod._GUIDED_API_COMMANDS)
        self.assertIn("probe-bip", mod._GUIDED_API_COMMANDS)
        self.assertIn("dry-run-bacnet-write", mod._GUIDED_API_COMMANDS)
        self.assertIn("bacnet-read-batch", mod.ALLOWED_PREFIXES)
        self.assertIn("probe-bip", mod.ALLOWED_PREFIXES)

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
