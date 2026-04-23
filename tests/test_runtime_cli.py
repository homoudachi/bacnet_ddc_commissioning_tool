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
