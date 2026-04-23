import csv
import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "simulator" / "list_verifier.py"
FIXTURES = ROOT / "tests" / "fixtures"


def _write_csv(path: pathlib.Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "controller_label",
        "profile_id",
        "bacnet_device_instance",
        "bacnet_ip",
        "bacnet_port",
        "building_floor",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _run_verifier(list_csv: pathlib.Path, scenario_json: pathlib.Path, strict: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(CLI),
        "--controllers-csv",
        str(list_csv),
        "--scenario-json",
        str(scenario_json),
    ]
    if strict:
        cmd.append("--strict")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _run_verifier_json(
    list_csv: pathlib.Path, scenario_json: pathlib.Path, strict: bool = True
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(CLI),
        "--controllers-csv",
        str(list_csv),
        "--scenario-json",
        str(scenario_json),
        "--output",
        "json",
    ]
    if strict:
        cmd.append("--strict")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _run_verifier_json_to_file(
    list_csv: pathlib.Path,
    scenario_json: pathlib.Path,
    output_file: pathlib.Path,
    strict: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(CLI),
        "--controllers-csv",
        str(list_csv),
        "--scenario-json",
        str(scenario_json),
        "--output",
        "json",
        "--output-file",
        str(output_file),
    ]
    if strict:
        cmd.append("--strict")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class ListVerifierCliTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURES.mkdir(parents=True, exist_ok=True)

    def test_happy_path_strict_passes_when_all_rows_verified(self) -> None:
        controllers = FIXTURES / "controllers-happy.csv"
        scenario = FIXTURES / "scenario-happy.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                },
                {
                    "controller_label": "HRV-01",
                    "profile_id": "hrv_counterflow_erv_v1",
                    "bacnet_device_instance": "22001",
                    "bacnet_ip": "192.168.1.60",
                    "bacnet_port": "47808",
                    "building_floor": "Roof",
                    "notes": "example row",
                },
            ],
        )
        _write_json(
            scenario,
            {
                "rows": [
                    {"controller_label": "FCU-01A", "status": "reachable_verified"},
                    {"controller_label": "HRV-01", "status": "reachable_verified"},
                ]
            },
        )

        result = _run_verifier(controllers, scenario, strict=True)

        self.assertEqual(0, result.returncode)
        self.assertIn("found=2 total=2 unresolved=0 strict_pass=true", result.stdout)

    def test_strict_fails_on_identity_mismatch(self) -> None:
        controllers = FIXTURES / "controllers-mismatch.csv"
        scenario = FIXTURES / "scenario-mismatch.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_json(
            scenario,
            {"rows": [{"controller_label": "FCU-01A", "status": "identity_mismatch"}]},
        )

        result = _run_verifier(controllers, scenario, strict=True)

        self.assertEqual(2, result.returncode)
        self.assertIn("identity_mismatch=1", result.stdout)
        self.assertIn("strict_pass=false", result.stdout)

    def test_non_strict_allows_known_unavailable_only_when_flagged(self) -> None:
        controllers = FIXTURES / "controllers-known-unavailable.csv"
        scenario = FIXTURES / "scenario-known-unavailable.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_json(
            scenario,
            {
                "rows": [
                    {
                        "controller_label": "FCU-01A",
                        "status": "known_unavailable",
                        "allow_known_unavailable": True,
                    }
                ]
            },
        )

        result = _run_verifier(controllers, scenario, strict=False)

        self.assertEqual(0, result.returncode)
        self.assertIn("known_unavailable=1", result.stdout)
        self.assertIn("strict_mode=false", result.stdout)

    def test_missing_scenario_row_is_counted_as_unreachable_timeout(self) -> None:
        controllers = FIXTURES / "controllers-missing-scenario.csv"
        scenario = FIXTURES / "scenario-missing-scenario.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_json(scenario, {"rows": []})

        result = _run_verifier(controllers, scenario, strict=True)

        self.assertEqual(2, result.returncode)
        self.assertIn("unreachable_timeout=1", result.stdout)

    def test_invalid_status_returns_error(self) -> None:
        controllers = FIXTURES / "controllers-invalid-status.csv"
        scenario = FIXTURES / "scenario-invalid-status.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_json(
            scenario,
            {"rows": [{"controller_label": "FCU-01A", "status": "not_a_real_status"}]},
        )

        result = _run_verifier(controllers, scenario, strict=True)

        self.assertEqual(2, result.returncode)
        self.assertIn("Unsupported status", result.stdout)

    def test_invalid_scenario_top_level_returns_controlled_error(self) -> None:
        controllers = FIXTURES / "controllers-invalid-top-level.csv"
        scenario = FIXTURES / "scenario-invalid-top-level.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        scenario.write_text("[]", encoding="utf-8")

        result = _run_verifier(controllers, scenario, strict=True)

        self.assertEqual(2, result.returncode)
        self.assertIn("Scenario JSON top-level value must be an object", result.stdout)

    def test_non_strict_rejects_known_unavailable_when_flag_not_boolean_true(self) -> None:
        controllers = FIXTURES / "controllers-known-unavailable-flag-type.csv"
        scenario = FIXTURES / "scenario-known-unavailable-flag-type.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_json(
            scenario,
            {
                "rows": [
                    {
                        "controller_label": "FCU-01A",
                        "status": "known_unavailable",
                        "allow_known_unavailable": "true",
                    }
                ]
            },
        )

        result = _run_verifier(controllers, scenario, strict=False)

        self.assertEqual(2, result.returncode)
        self.assertIn("strict_pass=false", result.stdout)

    def test_missing_required_csv_header_returns_error(self) -> None:
        controllers = FIXTURES / "controllers-missing-header.csv"
        scenario = FIXTURES / "scenario-missing-header.json"
        with controllers.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "controller_label",
                    "profile_id",
                    "bacnet_device_instance",
                    "bacnet_ip",
                    "building_floor",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "building_floor": "L01",
                    "notes": "missing bacnet_port",
                }
            )
        _write_json(
            scenario,
            {"rows": [{"controller_label": "FCU-01A", "status": "reachable_verified"}]},
        )

        result = _run_verifier(controllers, scenario, strict=True)

        self.assertEqual(2, result.returncode)
        self.assertIn("Missing required CSV columns", result.stdout)

    def test_json_output_mode_emits_machine_readable_summary(self) -> None:
        controllers = FIXTURES / "controllers-json-mode.csv"
        scenario = FIXTURES / "scenario-json-mode.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                },
                {
                    "controller_label": "HRV-01",
                    "profile_id": "hrv_counterflow_erv_v1",
                    "bacnet_device_instance": "22001",
                    "bacnet_ip": "192.168.1.60",
                    "bacnet_port": "47808",
                    "building_floor": "Roof",
                    "notes": "example row",
                },
            ],
        )
        _write_json(
            scenario,
            {
                "rows": [
                    {"controller_label": "FCU-01A", "status": "reachable_verified"},
                    {"controller_label": "HRV-01", "status": "identity_mismatch"},
                ]
            },
        )

        result = _run_verifier_json(controllers, scenario, strict=True)

        self.assertEqual(2, result.returncode)
        parsed = json.loads(result.stdout)
        self.assertEqual(2, parsed["total"])
        self.assertEqual(1, parsed["found"])
        self.assertEqual(1, parsed["unresolved"])
        self.assertFalse(parsed["strict_pass"])
        self.assertEqual(1, parsed["status_counts"]["identity_mismatch"])

    def test_json_output_can_be_written_to_output_file(self) -> None:
        controllers = FIXTURES / "controllers-json-artifact.csv"
        scenario = FIXTURES / "scenario-json-artifact.json"
        output_file = FIXTURES / "verifier-artifact.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_json(
            scenario,
            {
                "rows": [
                    {"controller_label": "FCU-01A", "status": "reachable_verified"},
                ]
            },
        )

        result = _run_verifier_json_to_file(
            controllers, scenario, output_file, strict=True
        )

        self.assertEqual(0, result.returncode)
        self.assertTrue(output_file.exists())
        parsed = json.loads(output_file.read_text(encoding="utf-8"))
        self.assertEqual(1, parsed["total"])
        self.assertTrue(parsed["strict_pass"])
