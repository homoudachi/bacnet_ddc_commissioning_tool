"""operator-gui / operator_gui_server (Tier B2)."""

from __future__ import annotations

import pathlib
import subprocess
import sys
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
        self.assertIn("Guided commissioning", body)

    def test_guided_api_command_allowlist_includes_point_checkout(self) -> None:
        import importlib.util

        p = ROOT / "tools" / "operator_gui_server.py"
        spec = importlib.util.spec_from_file_location("ogs3", p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIn("bacnet-point-checkout", mod._GUIDED_API_COMMANDS)


if __name__ == "__main__":
    unittest.main()
