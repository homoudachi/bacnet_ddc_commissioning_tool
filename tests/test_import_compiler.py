import csv
import json
import pathlib
import shutil
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "tools" / "import" / "compile_job.py"
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


def _write_profile(
    path: pathlib.Path,
    profile_id: str,
    display_name: str,
    *,
    write_allowlist: list[str] | None = None,
    read_allowlist: list[str] | None = None,
    point_checkout: list[dict] | None = None,
    commissioning_flow: list[dict] | None = None,
) -> None:
    data: dict = {
                "schema_version": "0.1-example",
                "profile_id": profile_id,
                "display_name": display_name,
                "objects": [
                    {
                        "id": "msv_test_mode",
                        "writable": True,
                        "bacnet": {
                            "object_type": "multiStateValue",
                            "instance": 50,
                        },
                    },
                    {
                        "id": "ai_sat",
                        "writable": False,
                        "bacnet": {"object_type": "analogInput", "instance": 2},
                    },
                    {
                        "id": "av_supply_fan_command",
                        "writable": True,
                        "bacnet": {"object_type": "analogValue", "instance": 3},
                    },
                ],
    }
    if write_allowlist is not None:
        data["commissioning_write_allowlist"] = write_allowlist
    if read_allowlist is not None:
        data["commissioning_read_allowlist"] = read_allowlist
    if point_checkout is not None:
        data["point_checkout"] = point_checkout
    if commissioning_flow is not None:
        data["commissioning_flow"] = commissioning_flow
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _run_compiler(
    controllers_csv: pathlib.Path,
    profiles_dir: pathlib.Path,
    output_json: pathlib.Path,
    report_json: pathlib.Path,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(COMPILER),
        "--controllers-csv",
        str(controllers_csv),
        "--profiles-dir",
        str(profiles_dir),
        "--output-json",
        str(output_json),
        "--report-json",
        str(report_json),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class ImportCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.profiles_dir = FIXTURES / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if FIXTURES.exists():
            shutil.rmtree(FIXTURES)

    def test_compile_job_happy_path_writes_runtime_model(self) -> None:
        controllers = FIXTURES / "controllers-compile-happy.csv"
        output_json = FIXTURES / "runtime-job-happy.json"
        report_json = FIXTURES / "runtime-job-happy-report.json"

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
        _write_profile(
            self.profiles_dir / "unit-profile-fcu.example.json",
            profile_id="fcu_2pipe_chw_electric_heat_v1",
            display_name="FCU example",
            write_allowlist=["msv_test_mode"],
            read_allowlist=["ai_sat"],
        )
        _write_profile(
            self.profiles_dir / "unit-profile-hrv.example.json",
            profile_id="hrv_counterflow_erv_v1",
            display_name="HRV example",
            write_allowlist=["msv_test_mode"],
            read_allowlist=["msv_test_mode"],
            point_checkout=[{"object_id": "msv_test_mode", "property": "presentValue"}],
        )

        result = _run_compiler(controllers, self.profiles_dir, output_json, report_json)

        self.assertEqual(0, result.returncode)
        self.assertIn("compile_ok=true", result.stdout)
        runtime = json.loads(output_json.read_text(encoding="utf-8"))
        self.assertEqual(2, runtime["summary"]["controller_count"])
        self.assertEqual(2, len(runtime["controllers"]))
        self.assertEqual("FCU example", runtime["controllers"][0]["profile"]["display_name"])
        self.assertEqual(["msv_test_mode"], runtime["controllers"][0]["commissioning_write_allowlist"])
        self.assertEqual(["ai_sat"], runtime["controllers"][0]["commissioning_read_allowlist"])
        self.assertEqual(
            [{"object_id": "msv_test_mode", "property": "presentValue"}],
            runtime["controllers"][1]["point_checkout"],
        )
        fcu_objs = runtime["controllers"][0].get("objects_by_id", {})
        self.assertIn("msv_test_mode", fcu_objs)
        self.assertEqual("multiStateValue", fcu_objs["msv_test_mode"]["bacnet"]["object_type"])
        self.assertEqual(50, fcu_objs["msv_test_mode"]["bacnet"]["instance"])
        self.assertTrue(fcu_objs["msv_test_mode"]["writable"])
        report = json.loads(report_json.read_text(encoding="utf-8"))
        self.assertEqual([], report["errors"])

    def test_compile_includes_commissioning_step_metadata(self) -> None:
        controllers = FIXTURES / "controllers-compile-stepmeta.csv"
        output_json = FIXTURES / "runtime-job-stepmeta.json"
        report_json = FIXTURES / "runtime-job-stepmeta-report.json"
        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-X",
                    "profile_id": "profile_stepmeta",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "",
                },
            ],
        )
        _write_profile(
            self.profiles_dir / "unit-profile-stepmeta.json",
            profile_id="profile_stepmeta",
            display_name="Step meta test",
            read_allowlist=["ai_sat"],
            point_checkout=[{"object_id": "ai_sat", "property": "presentValue"}],
            commissioning_flow=[
                {
                    "step_id": "gate_point_checkout",
                    "label": "BACnet point checkout gate",
                    "step_type": "bacnet_point_checkout",
                    "report_ref": "test.point_checkout_gate",
                },
                {
                    "step_id": "normal_step",
                    "label": "Normal",
                    "run_point_checkout_on_pass": True,
                    "report_ref": "test.after_pass",
                },
            ],
        )
        result = _run_compiler(controllers, self.profiles_dir, output_json, report_json)
        self.assertEqual(0, result.returncode)
        runtime = json.loads(output_json.read_text(encoding="utf-8"))
        flow = runtime["controllers"][0]["commissioning_flow"]
        self.assertEqual(2, len(flow))
        self.assertEqual("bacnet_point_checkout", flow[0]["step_type"])
        self.assertEqual("test.point_checkout_gate", flow[0]["report_ref"])
        self.assertFalse(flow[0]["run_point_checkout_on_pass"])
        self.assertTrue(flow[1]["run_point_checkout_on_pass"])
        self.assertEqual("test.after_pass", flow[1]["report_ref"])

    def test_compile_fails_when_profile_is_missing(self) -> None:
        controllers = FIXTURES / "controllers-compile-missing-profile.csv"
        output_json = FIXTURES / "runtime-job-missing-profile.json"
        report_json = FIXTURES / "runtime-job-missing-profile-report.json"

        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "missing_profile_id",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "example row",
                }
            ],
        )
        _write_profile(
            self.profiles_dir / "unit-profile-fcu.example.json",
            profile_id="fcu_2pipe_chw_electric_heat_v1",
            display_name="FCU example",
        )

        result = _run_compiler(controllers, self.profiles_dir, output_json, report_json)

        self.assertEqual(2, result.returncode)
        self.assertIn("compile_ok=false", result.stdout)
        report = json.loads(report_json.read_text(encoding="utf-8"))
        self.assertEqual("missing_profile", report["errors"][0]["code"])

    def test_compile_fails_on_duplicate_device_instance(self) -> None:
        controllers = FIXTURES / "controllers-compile-duplicate-instance.csv"
        output_json = FIXTURES / "runtime-job-duplicate-instance.json"
        report_json = FIXTURES / "runtime-job-duplicate-instance-report.json"

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
                    "controller_label": "FCU-01B",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.51",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "duplicate instance",
                },
            ],
        )
        _write_profile(
            self.profiles_dir / "unit-profile-fcu.example.json",
            profile_id="fcu_2pipe_chw_electric_heat_v1",
            display_name="FCU example",
        )

        result = _run_compiler(controllers, self.profiles_dir, output_json, report_json)

        self.assertEqual(2, result.returncode)
        report = json.loads(report_json.read_text(encoding="utf-8"))
        codes = {entry["code"] for entry in report["errors"]}
        self.assertIn("duplicate_bacnet_device_instance", codes)

    def test_compile_fails_on_invalid_bacnet_port(self) -> None:
        controllers = FIXTURES / "controllers-compile-invalid-port.csv"
        output_json = FIXTURES / "runtime-job-invalid-port.json"
        report_json = FIXTURES / "runtime-job-invalid-port-report.json"

        _write_csv(
            controllers,
            [
                {
                    "controller_label": "FCU-01A",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21001",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "not-a-port",
                    "building_floor": "L01",
                    "notes": "invalid port",
                }
            ],
        )
        _write_profile(
            self.profiles_dir / "unit-profile-fcu.example.json",
            profile_id="fcu_2pipe_chw_electric_heat_v1",
            display_name="FCU example",
        )

        result = _run_compiler(controllers, self.profiles_dir, output_json, report_json)

        self.assertEqual(2, result.returncode)
        report = json.loads(report_json.read_text(encoding="utf-8"))
        self.assertEqual("invalid_bacnet_port", report["errors"][0]["code"])

    def test_compile_warns_on_duplicate_bacnet_ip_port_different_device(self) -> None:
        controllers = FIXTURES / "controllers-compile-dup-ip.csv"
        output_json = FIXTURES / "runtime-job-dup-ip.json"
        report_json = FIXTURES / "runtime-job-dup-ip-report.json"

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
                    "notes": "row a",
                },
                {
                    "controller_label": "FCU-01B",
                    "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                    "bacnet_device_instance": "21002",
                    "bacnet_ip": "192.168.1.50",
                    "bacnet_port": "47808",
                    "building_floor": "L01",
                    "notes": "same endpoint different instance",
                },
            ],
        )
        _write_profile(
            self.profiles_dir / "unit-profile-fcu.example.json",
            profile_id="fcu_2pipe_chw_electric_heat_v1",
            display_name="FCU example",
            write_allowlist=["msv_test_mode"],
            read_allowlist=["ai_sat"],
        )

        result = _run_compiler(controllers, self.profiles_dir, output_json, report_json)

        self.assertEqual(0, result.returncode)
        report = json.loads(report_json.read_text(encoding="utf-8"))
        codes = [w["code"] for w in report["warnings"]]
        self.assertIn("duplicate_bacnet_ip_port_different_device", codes)

