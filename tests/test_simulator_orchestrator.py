import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORCH = ROOT / "tools" / "simulator" / "orchestrator.py"
FIXTURES = ROOT / "tests" / "fixtures"


def _run_orchestrator(
    controllers_csv: pathlib.Path,
    scenario_dir: pathlib.Path,
    profile: str,
    scenario_name: str,
    strict: bool = True,
    output: str = "text",
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(ORCH),
        "--controllers-csv",
        str(controllers_csv),
        "--scenarios-dir",
        str(scenario_dir),
        "--profile",
        profile,
        "--scenario",
        scenario_name,
        "--output",
        output,
    ]
    if strict:
        cmd.append("--strict")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class SimulatorOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.scenarios = FIXTURES / "scenario-set"
        self.scenarios.mkdir(parents=True, exist_ok=True)
        self.controllers = FIXTURES / "controllers-orchestrator.csv"
        self.controllers.write_text(
            "\n".join(
                [
                    "controller_label,profile_id,bacnet_device_instance,bacnet_ip,bacnet_port,building_floor,notes",
                    "FCU-01A,fcu_2pipe_chw_electric_heat_v1,21001,192.168.1.50,47808,L01,example row",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_orchestrator_runs_verifier_for_profile_and_scenario(self) -> None:
        (self.scenarios / "happy-path.example.json").write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "controller_label": "FCU-01A",
                            "status": "reachable_verified",
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = _run_orchestrator(
            controllers_csv=self.controllers,
            scenario_dir=self.scenarios,
            profile="ci",
            scenario_name="happy-path",
            strict=True,
        )

        self.assertEqual(0, result.returncode)
        self.assertIn("strict_pass=true", result.stdout)

    def test_orchestrator_errors_when_scenario_file_missing(self) -> None:
        result = _run_orchestrator(
            controllers_csv=self.controllers,
            scenario_dir=self.scenarios,
            profile="ci",
            scenario_name="missing-scenario",
            strict=True,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("scenario file not found", result.stdout)

    def test_orchestrator_supports_json_output_mode(self) -> None:
        (self.scenarios / "happy-path.example.json").write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "controller_label": "FCU-01A",
                            "status": "reachable_verified",
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = _run_orchestrator(
            controllers_csv=self.controllers,
            scenario_dir=self.scenarios,
            profile="ci",
            scenario_name="happy-path",
            strict=True,
            output="json",
        )

        self.assertEqual(0, result.returncode)
        parsed = json.loads(result.stdout)
        self.assertEqual(1, parsed["total"])
        self.assertTrue(parsed["strict_pass"])

