import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_CLI = ROOT / "tools" / "runtime" / "app.py"
FIXTURES = ROOT / "tests" / "fixtures"


def _run_runtime(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(RUNTIME_CLI), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


class RuntimeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.run_dir = FIXTURES / "runtime-run"

    def test_init_run_creates_layout_config_and_log(self) -> None:
        result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-001",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )

        self.assertEqual(0, result.returncode)
        self.assertTrue((self.run_dir / "config" / "runtime-config.json").exists())
        self.assertTrue((self.run_dir / "logs" / "events.jsonl").exists())
        self.assertTrue((self.run_dir / "state").exists())
        self.assertTrue((self.run_dir / "artifacts").exists())

        config = json.loads(
            (self.run_dir / "config" / "runtime-config.json").read_text(encoding="utf-8")
        )
        self.assertEqual("job-001", config["job_id"])
        self.assertIn("controllers_csv", config)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        self.assertGreaterEqual(len(lines), 1)
        first_event = json.loads(lines[0])
        self.assertEqual("run_initialized", first_event["event"])

    def test_compile_import_uses_run_config_and_writes_state_outputs(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-compile",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)

        result = _run_runtime("compile-import", "--run-dir", str(self.run_dir))

        self.assertEqual(0, result.returncode)
        runtime_job = self.run_dir / "state" / "runtime-job.json"
        report = self.run_dir / "state" / "import-report.json"
        self.assertTrue(runtime_job.exists())
        self.assertTrue(report.exists())

        report_obj = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(report_obj["compile_ok"])

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("import_compiled", events)

    def test_verify_simulator_writes_artifact_and_logs_event(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-verify",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)

        result = _run_runtime(
            "verify-simulator",
            "--run-dir",
            str(self.run_dir),
            "--profile",
            "ci",
            "--scenario",
            "happy-path",
            "--strict",
        )

        self.assertEqual(0, result.returncode)
        artifact = self.run_dir / "artifacts" / "simulator" / "ci-happy-path.json"
        self.assertTrue(artifact.exists())
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertTrue(summary["strict_pass"])
        self.assertEqual("ci", summary["profile"])

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("simulator_verified", events)

    def test_init_flow_creates_controller_flow_state(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-init",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)
        compile_result = _run_runtime("compile-import", "--run-dir", str(self.run_dir))
        self.assertEqual(0, compile_result.returncode)

        result = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )

        self.assertEqual(0, result.returncode)
        flow_state_path = self.run_dir / "state" / "flows" / "FCU-01A.json"
        self.assertTrue(flow_state_path.exists())
        flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
        self.assertEqual("FCU-01A", flow_state["controller_label"])
        self.assertGreater(len(flow_state["steps"]), 0)
        self.assertEqual("pending", flow_state["steps"][0]["status"])

    def test_record_step_updates_status_and_captures_technician_signoff(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-record",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)
        compile_result = _run_runtime("compile-import", "--run-dir", str(self.run_dir))
        self.assertEqual(0, compile_result.returncode)
        init_flow_result = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, init_flow_result.returncode)

        result = _run_runtime(
            "record-step",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--step-id",
            "half_design_airflow_auto",
            "--status",
            "passed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Reached target airflow in tolerance",
        )

        self.assertEqual(0, result.returncode)
        flow_state = json.loads(
            (self.run_dir / "state" / "flows" / "FCU-01A.json").read_text(
                encoding="utf-8"
            )
        )
        step = [s for s in flow_state["steps"] if s["step_id"] == "half_design_airflow_auto"][
            0
        ]
        self.assertEqual("passed", step["status"])
        self.assertEqual("Alex Tech", step["technician_name"])
        self.assertIn("Reached target airflow", step["note"])

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("flow_initialized", events)
        self.assertIn("flow_step_recorded", events)
