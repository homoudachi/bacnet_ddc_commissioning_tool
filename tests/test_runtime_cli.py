import csv
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_CLI = ROOT / "tools" / "runtime" / "app.py"
FIXTURES = ROOT / "tests" / "fixtures"


def _run_runtime(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(RUNTIME_CLI), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _build_i_am_packet(device_instance: int) -> bytes:
    object_identifier = (8 << 22) | (device_instance & 0x3FFFFF)
    apdu = b"\x10\x00\xc4" + object_identifier.to_bytes(4, "big") + b"\x22\x00\x91\x00"
    npdu = b"\x01\x00"
    payload = npdu + apdu
    bvlc = b"\x81\x0a" + (len(payload) + 4).to_bytes(2, "big")
    return bvlc + payload


class _FakeBipUdpServer:
    def __init__(self, device_instance: int) -> None:
        self.device_instance = device_instance
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.port = 0

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=2):
            raise RuntimeError("fake bip server failed to start")

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(0.1)
            self.port = sock.getsockname()[1]
            self._ready.set()
            while not self._stop.is_set():
                try:
                    _data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                sock.sendto(_build_i_am_packet(self.device_instance), addr)
        finally:
            sock.close()


class RuntimeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.run_dir = FIXTURES / "runtime-run"

    def tearDown(self) -> None:
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)

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

    def test_validate_import_writes_separate_artifacts(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-validate-import",
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
        first_mtime = (self.run_dir / "state" / "runtime-job.json").stat().st_mtime_ns

        val_dir = self.run_dir / "artifacts" / "import-validation-custom"
        result = _run_runtime(
            "validate-import",
            "--run-dir",
            str(self.run_dir),
            "--output-dir",
            str(val_dir),
        )
        self.assertEqual(0, result.returncode)
        self.assertTrue((val_dir / "runtime-job.json").exists())
        self.assertTrue((val_dir / "import-report.json").exists())
        second_mtime = (self.run_dir / "state" / "runtime-job.json").stat().st_mtime_ns
        self.assertEqual(first_mtime, second_mtime)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("import_validated", events)

    def test_print_job_graph_after_compile(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-print-graph",
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

        result = _run_runtime("print-job-graph", "--run-dir", str(self.run_dir))
        self.assertEqual(0, result.returncode)
        self.assertIn("job-print-graph", result.stdout)
        self.assertIn("FCU-01A", result.stdout)
        self.assertIn("read_allowlist=", result.stdout)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("job_graph_printed", events)

    def test_bacnet_read_rejects_object_not_on_read_allowlist(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-bacnet-read-deny",
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
            "bacnet-read",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--object-id",
            "av_supply_fan_command",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("commissioning_read_allowlist", result.stdout)

    def test_export_run_summary_requires_runtime_job(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-export-no-compile",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)
        out_path = self.run_dir / "artifacts" / "custom-summary.json"
        result = _run_runtime(
            "export-run-summary",
            "--run-dir",
            str(self.run_dir),
            "--output-json",
            str(out_path),
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("compile-import", result.stdout)

    def test_export_run_summary_after_compile_and_init_flow(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-export-summary",
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

        result = _run_runtime("export-run-summary", "--run-dir", str(self.run_dir))
        self.assertEqual(0, result.returncode)
        default_path = self.run_dir / "artifacts" / "run-summary.json"
        self.assertTrue(default_path.exists())
        summary = json.loads(default_path.read_text(encoding="utf-8"))
        self.assertEqual("0.1-run-summary", summary["schema_version"])
        self.assertEqual("job-export-summary", summary["job_id"])
        self.assertEqual(3, len(summary["controllers"]))
        for row in summary["controllers"]:
            self.assertFalse(row["flow_initialized"])
            self.assertIsNone(row["next_open_step"])

        init_flow = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, init_flow.returncode)
        record = _run_runtime(
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
            "ok",
        )
        self.assertEqual(0, record.returncode)

        out2 = self.run_dir / "artifacts" / "summary-after-step.json"
        result2 = _run_runtime(
            "export-run-summary",
            "--run-dir",
            str(self.run_dir),
            "--output-json",
            str(out2),
        )
        self.assertEqual(0, result2.returncode)
        summary2 = json.loads(out2.read_text(encoding="utf-8"))
        fcu = [r for r in summary2["controllers"] if r["controller_label"] == "FCU-01A"][0]
        self.assertTrue(fcu["flow_initialized"])
        self.assertEqual("confirm_tachometer_reference_half_flow", fcu["next_open_step"]["step_id"])
        self.assertEqual("pending", fcu["next_open_step"]["status"])

        log_lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in log_lines]
        self.assertIn("run_summary_exported", events)

    def test_export_run_summary_writes_csv_when_requested(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-export-csv",
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

        csv_path = self.run_dir / "artifacts" / "run-summary.csv"
        result = _run_runtime(
            "export-run-summary",
            "--run-dir",
            str(self.run_dir),
            "--output-csv",
            str(csv_path),
        )
        self.assertEqual(0, result.returncode)
        self.assertTrue(csv_path.exists())
        text = csv_path.read_text(encoding="utf-8")
        self.assertIn("controller_label", text)
        self.assertIn("FCU-01A", text)

    def test_export_run_summary_embed_import_and_bip_blobs(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-export-embed",
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
        bip_result = _run_runtime(
            "verify-bip-list",
            "--run-dir",
            str(self.run_dir),
            "--timeout-seconds",
            "0.1",
            "--retries",
            "1",
        )
        self.assertEqual(2, bip_result.returncode)

        out_path = self.run_dir / "artifacts" / "summary-embedded.json"
        result = _run_runtime(
            "export-run-summary",
            "--run-dir",
            str(self.run_dir),
            "--output-json",
            str(out_path),
            "--embed-import-report",
            "--embed-bip-list-summary",
        )
        self.assertEqual(0, result.returncode)
        summary = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertIn("import_report", summary)
        self.assertTrue(summary["import_report"]["compile_ok"])
        self.assertIn("bip_list_summary", summary)
        self.assertEqual(3, summary["bip_list_summary"]["total"])

    def test_list_flows_empty_when_no_flow_state(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-list-flows-empty",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)

        result = _run_runtime("list-flows", "--run-dir", str(self.run_dir))
        self.assertEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual(0, payload["flow_count"])
        self.assertEqual([], payload["flows"])

    def test_list_flows_and_show_flow_after_init_flow(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-list-flows",
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

        list_result = _run_runtime("list-flows", "--run-dir", str(self.run_dir))
        self.assertEqual(0, list_result.returncode)
        listed = json.loads(list_result.stdout)
        self.assertEqual(1, listed["flow_count"])
        self.assertEqual("FCU-01A", listed["flows"][0]["controller_label"])
        self.assertEqual(
            "fcu_2pipe_chw_electric_heat_v1", listed["flows"][0]["profile_id"]
        )
        self.assertGreater(listed["flows"][0]["step_count"], 0)
        self.assertEqual(
            listed["flows"][0]["step_count"],
            listed["flows"][0]["status_counts"].get("pending", 0),
        )

        show_result = _run_runtime(
            "show-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, show_result.returncode)
        detail = json.loads(show_result.stdout)
        self.assertEqual("FCU-01A", detail["controller_label"])
        self.assertIn("steps", detail)
        self.assertGreater(len(detail["steps"]), 0)
        self.assertEqual("pending", detail["steps"][0]["status"])

        log_lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in log_lines]
        self.assertIn("flows_listed", events)
        self.assertIn("flow_viewed", events)

    def test_show_flow_errors_when_controller_has_no_flow_state(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-show-flow-missing",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)

        result = _run_runtime(
            "show-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "HRV-01",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("flow state not found", result.stdout)

    def test_set_session_value_requires_init_flow(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-session-no-flow",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)

        result = _run_runtime(
            "set-session-value",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--key",
            "rat_degC",
            "--value",
            "22.5",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Manual RAT",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("init-flow first", result.stdout)

    def test_set_session_value_and_show_session_round_trip(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-session-roundtrip",
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

        set_result = _run_runtime(
            "set-session-value",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--key",
            "rat_degC",
            "--value",
            "22.5",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Manual RAT for heat-rise",
        )
        self.assertEqual(0, set_result.returncode)
        self.assertIn("session_value_set=true", set_result.stdout)

        session_path = self.run_dir / "state" / "sessions" / "FCU-01A.json"
        self.assertTrue(session_path.exists())
        stored = json.loads(session_path.read_text(encoding="utf-8"))
        self.assertEqual("FCU-01A", stored["controller_label"])
        self.assertEqual("22.5", stored["values"]["rat_degC"]["value"])
        self.assertEqual("Alex Tech", stored["values"]["rat_degC"]["technician_name"])

        show_result = _run_runtime(
            "show-session",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, show_result.returncode)
        shown = json.loads(show_result.stdout)
        self.assertEqual("22.5", shown["values"]["rat_degC"]["value"])

        log_lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in log_lines]
        self.assertIn("session_value_set", events)
        self.assertIn("session_viewed", events)

    def test_show_session_errors_when_missing(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-show-session-missing",
            "--controllers-csv",
            str(ROOT / "docs" / "examples" / "site-controllers.template.csv"),
            "--profiles-dir",
            str(ROOT / "docs" / "examples"),
            "--scenarios-dir",
            str(ROOT / "docs" / "examples" / "simulator-scenarios"),
        )
        self.assertEqual(0, init_result.returncode)

        result = _run_runtime(
            "show-session",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("session state not found", result.stdout)

    def test_init_flow_rejects_second_init_without_force(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-init-twice",
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
        first = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, first.returncode)
        second = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(2, second.returncode)
        self.assertIn("already exists", second.stdout)

    def test_init_flow_force_replaces_state_and_backups_prior(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-init-force",
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
        first = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, first.returncode)
        record = _run_runtime(
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
            "first run",
        )
        self.assertEqual(0, record.returncode)

        second = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--force",
            "--reset-technician-name",
            "Lead Tech",
            "--reset-reason",
            "Wrong controller row; restarting commissioning",
        )
        self.assertEqual(0, second.returncode)

        flow_state = json.loads(
            (self.run_dir / "state" / "flows" / "FCU-01A.json").read_text(encoding="utf-8")
        )
        self.assertEqual("pending", flow_state["steps"][0]["status"])
        backups = list((self.run_dir / "state" / "flow_backups").glob("FCU-01A-*.json"))
        self.assertEqual(1, len(backups))
        prior = json.loads(backups[0].read_text(encoding="utf-8"))
        self.assertEqual("passed", prior["steps"][0]["status"])

        log_lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in log_lines]
        self.assertIn("flow_reinitialized", events)

    def test_init_flow_force_requires_audit_fields(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-init-force-audit",
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
        first = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
        )
        self.assertEqual(0, first.returncode)

        bad = _run_runtime(
            "init-flow",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--force",
            "--reset-technician-name",
            "",
            "--reset-reason",
            "",
        )
        self.assertEqual(2, bad.returncode)
        self.assertIn("--reset-technician-name", bad.stdout)

    def test_dry_run_bacnet_write_rejects_non_allowlisted_object(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-drywrite-deny",
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
            "dry-run-bacnet-write",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--object-id",
            "av_supply_fan_command",
            "--value",
            "50",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Should be blocked",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("commissioning_write_allowlist", result.stdout)

    def test_dry_run_bacnet_write_planned_with_localhost_udp_server(self) -> None:
        server = _FakeBipUdpServer(device_instance=21001)
        server.start()
        try:
            time.sleep(0.05)
            self.run_dir.mkdir(parents=True, exist_ok=True)
            csv_path = self.run_dir / "controllers-local.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "controller_label",
                        "profile_id",
                        "bacnet_device_instance",
                        "bacnet_ip",
                        "bacnet_port",
                        "building_floor",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "controller_label": "FCU-LOCAL",
                        "profile_id": "fcu_2pipe_chw_electric_heat_v1",
                        "bacnet_device_instance": "21001",
                        "bacnet_ip": "127.0.0.1",
                        "bacnet_port": str(server.port),
                        "building_floor": "L01",
                        "notes": "test",
                    }
                )

            init_result = _run_runtime(
                "init-run",
                "--run-dir",
                str(self.run_dir),
                "--job-id",
                "job-drywrite-ok",
                "--controllers-csv",
                str(csv_path),
                "--profiles-dir",
                str(ROOT / "docs" / "examples"),
                "--scenarios-dir",
                str(ROOT / "docs" / "examples" / "simulator-scenarios"),
            )
            self.assertEqual(0, init_result.returncode)
            compile_result = _run_runtime("compile-import", "--run-dir", str(self.run_dir))
            self.assertEqual(0, compile_result.returncode)

            result = _run_runtime(
                "dry-run-bacnet-write",
                "--run-dir",
                str(self.run_dir),
                "--controller-label",
                "FCU-LOCAL",
                "--object-id",
                "msv_test_mode",
                "--value",
                "3",
                "--technician-name",
                "Alex Tech",
                "--note",
                "Arm airflow verify mode",
                "--timeout-seconds",
                "0.5",
                "--retries",
                "1",
            )
        finally:
            server.stop()

        self.assertEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("dry_run_allowed", payload["status"])
        self.assertEqual(19, payload["target"]["object_type"])
        self.assertEqual(50, payload["target"]["object_instance"])
        artifact = (
            self.run_dir / "artifacts" / "bacnet_write_plans" / "FCU-LOCAL-msv_test_mode.json"
        )
        self.assertTrue(artifact.exists())

        log_lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in log_lines]
        self.assertIn("bacnet_write_planned", events)

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

    def test_probe_bip_writes_artifact_and_logs_event(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-bip-probe",
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
            "probe-bip",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--timeout-seconds",
            "0.1",
            "--retries",
            "1",
        )

        self.assertIn(result.returncode, (0, 2))
        artifact = self.run_dir / "artifacts" / "bip" / "FCU-01A.json"
        self.assertTrue(artifact.exists())
        summary = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual("FCU-01A", summary["controller_label"])
        self.assertIn(summary["status"], {"reachable_verified", "identity_mismatch", "unreachable_timeout"})

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("bip_probed", events)

    def test_verify_bip_list_writes_summary_artifact_and_logs_event(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-bip-list",
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
            "verify-bip-list",
            "--run-dir",
            str(self.run_dir),
            "--timeout-seconds",
            "0.1",
            "--retries",
            "1",
            "--strict",
        )

        self.assertEqual(2, result.returncode)
        summary_path = self.run_dir / "artifacts" / "bip" / "list-summary.json"
        self.assertTrue(summary_path.exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(3, summary["total"])
        self.assertIn("status_counts", summary)
        self.assertFalse(summary["strict_pass"])

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        self.assertIn("bip_list_verified", events)

    def test_verify_bip_list_non_strict_allows_known_unavailable(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-bip-list-nonstrict",
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

        overrides_path = self.run_dir / "config" / "bip-known-unavailable.json"
        overrides_path.write_text(
            json.dumps(
                {
                    "controller_labels": ["FCU-01A", "FCU-01B", "HRV-01"],
                    "allow_known_unavailable": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = _run_runtime(
            "verify-bip-list",
            "--run-dir",
            str(self.run_dir),
            "--timeout-seconds",
            "0.1",
            "--retries",
            "1",
            "--known-unavailable-file",
            str(overrides_path),
        )

        self.assertEqual(0, result.returncode)
        summary = json.loads(
            (self.run_dir / "artifacts" / "bip" / "list-summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(summary["strict_pass"])
        self.assertEqual(3, summary["status_counts"].get("known_unavailable", 0))

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

    def test_init_flow_persists_step_policy_and_history_fields(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-init-policy",
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
        flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
        target_step = [s for s in flow_state["steps"] if s["step_id"] == "half_design_airflow_auto"][
            0
        ]
        self.assertIn("skippable", target_step)
        self.assertIsInstance(target_step["skippable"], bool)
        self.assertIn("requires_step_ids", target_step)
        self.assertIsInstance(target_step["requires_step_ids"], list)
        self.assertIn("history", target_step)
        self.assertEqual([], target_step["history"])

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
        self.assertIn("history", step)
        self.assertGreaterEqual(len(step["history"]), 1)
        self.assertEqual("pending", step["history"][-1]["previous_status"])
        self.assertEqual("passed", step["history"][-1]["new_status"])
        self.assertEqual("status_update", step["history"][-1]["reason_code"])

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        parsed_events = [json.loads(line) for line in lines]
        events = [entry["event"] for entry in parsed_events]
        self.assertIn("flow_initialized", events)
        self.assertIn("flow_step_recorded", events)
        flow_step_event = [entry for entry in parsed_events if entry["event"] == "flow_step_recorded"][-1]
        self.assertEqual("pending", flow_step_event["previous_status"])
        self.assertEqual("passed", flow_step_event["new_status"])
        self.assertEqual("status_update", flow_step_event["reason_code"])

    def test_record_step_rejects_out_of_order_transition(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-ordering",
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

        # Attempt to complete step 2 before step 1.
        result = _run_runtime(
            "record-step",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--step-id",
            "confirm_tachometer_reference_half_flow",
            "--status",
            "passed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Tried to skip ahead",
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("invalid step transition", result.stdout)
        self.assertIn("cannot be marked passed before", result.stdout)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        parsed_events = [json.loads(line) for line in lines]
        rejection_events = [entry for entry in parsed_events if entry["event"] == "flow_step_rejected"]
        self.assertGreaterEqual(len(rejection_events), 1)
        self.assertEqual("PREREQ_ORDER", rejection_events[-1]["reason_code"])

    def test_record_step_rejects_skip_when_step_not_marked_skippable(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-skip-rule",
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
            "skipped",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Skipping first step",
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("invalid step transition", result.stdout)
        self.assertIn("is not skippable", result.stdout)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        parsed_events = [json.loads(line) for line in lines]
        rejection_events = [entry for entry in parsed_events if entry["event"] == "flow_step_rejected"]
        self.assertGreaterEqual(len(rejection_events), 1)
        self.assertEqual("STEP_NOT_SKIPPABLE", rejection_events[-1]["reason_code"])

    def test_record_step_rejects_when_explicit_dependency_not_satisfied(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-explicit-dependency",
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

        # Inject an explicit dependency on a later step to prove dependency checks
        # are enforced independently of index ordering.
        flow_state_path = self.run_dir / "state" / "flows" / "FCU-01A.json"
        flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
        for step in flow_state["steps"]:
            if step["step_id"] == "half_design_airflow_auto":
                step["requires_step_ids"] = ["heating_test"]
                break
        flow_state_path.write_text(json.dumps(flow_state, indent=2), encoding="utf-8")

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
            "Attempting explicit dependency bypass",
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("invalid step transition", result.stdout)
        self.assertIn("requires completed dependency", result.stdout)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        parsed_events = [json.loads(line) for line in lines]
        rejection_events = [entry for entry in parsed_events if entry["event"] == "flow_step_rejected"]
        self.assertGreaterEqual(len(rejection_events), 1)
        self.assertEqual("DEPENDENCY_UNSATISFIED", rejection_events[-1]["reason_code"])

    def test_record_step_rejection_appends_history_and_preserves_status(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-rejection-history",
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
            "confirm_tachometer_reference_half_flow",
            "--status",
            "passed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Attempting out-of-order transition",
        )
        self.assertEqual(2, result.returncode)

        flow_state_path = self.run_dir / "state" / "flows" / "FCU-01A.json"
        flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
        step = [
            s for s in flow_state["steps"] if s["step_id"] == "confirm_tachometer_reference_half_flow"
        ][0]
        self.assertEqual("pending", step["status"])
        self.assertIn("history", step)
        self.assertGreaterEqual(len(step["history"]), 1)
        rejection_entry = step["history"][-1]
        self.assertTrue(rejection_entry["rejected"])
        self.assertEqual("pending", rejection_entry["previous_status"])
        self.assertEqual("passed", rejection_entry["attempted_status"])
        self.assertEqual("pending", rejection_entry["new_status"])
        self.assertEqual("PREREQ_ORDER", rejection_entry["reason_code"])
        self.assertEqual("PREREQ_ORDER", rejection_entry["rejection_reason_code"])

    def test_record_step_rejects_when_dependency_id_missing_from_flow(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-missing-dependency",
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

        flow_state_path = self.run_dir / "state" / "flows" / "FCU-01A.json"
        flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
        for step in flow_state["steps"]:
            if step["step_id"] == "half_design_airflow_auto":
                step["requires_step_ids"] = ["missing-step-id"]
                break
        flow_state_path.write_text(json.dumps(flow_state, indent=2), encoding="utf-8")

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
            "Attempting transition with missing dependency id",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("not present in flow", result.stdout)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        parsed_events = [json.loads(line) for line in lines]
        rejection_events = [entry for entry in parsed_events if entry["event"] == "flow_step_rejected"]
        self.assertGreaterEqual(len(rejection_events), 1)
        self.assertEqual("DEPENDENCY_UNSATISFIED", rejection_events[-1]["reason_code"])

    def test_record_step_appends_history_for_multiple_updates(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-history-multi",
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

        first_result = _run_runtime(
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
            "First transition",
        )
        self.assertEqual(0, first_result.returncode)

        second_result = _run_runtime(
            "record-step",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--step-id",
            "half_design_airflow_auto",
            "--status",
            "manual_passed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Second transition",
        )
        self.assertEqual(0, second_result.returncode)

        flow_state_path = self.run_dir / "state" / "flows" / "FCU-01A.json"
        flow_state = json.loads(flow_state_path.read_text(encoding="utf-8"))
        step = [s for s in flow_state["steps"] if s["step_id"] == "half_design_airflow_auto"][
            0
        ]
        self.assertEqual("manual_passed", step["status"])
        self.assertGreaterEqual(len(step["records"]), 2)
        self.assertGreaterEqual(len(step["history"]), 2)
        first_history = step["history"][-2]
        second_history = step["history"][-1]
        self.assertEqual("pending", first_history["previous_status"])
        self.assertEqual("passed", first_history["new_status"])
        self.assertEqual("passed", second_history["previous_status"])
        self.assertEqual("manual_passed", second_history["new_status"])
        self.assertEqual("status_update", first_history["reason_code"])
        self.assertEqual("status_update", second_history["reason_code"])

    def test_record_step_rejects_pending_status_record(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-pending-record",
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
            "pending",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Trying to write pending",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("cannot record step with status 'pending'", result.stdout)

    def test_record_step_failed_requires_prior_steps_completed(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-fail-order",
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
            "confirm_tachometer_reference_half_flow",
            "--status",
            "failed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Out of order fail",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("invalid step transition", result.stdout)

        lines = (
            self.run_dir / "logs" / "events.jsonl"
        ).read_text(encoding="utf-8").strip().splitlines()
        parsed_events = [json.loads(line) for line in lines]
        rejection_events = [entry for entry in parsed_events if entry["event"] == "flow_step_rejected"]
        self.assertGreaterEqual(len(rejection_events), 1)
        self.assertEqual("PREREQ_ORDER", rejection_events[-1]["reason_code"])

    def test_record_step_failed_allowed_when_prerequisites_met(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-fail-ok",
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

        first = _run_runtime(
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
            "Airflow ok",
        )
        self.assertEqual(0, first.returncode)

        second = _run_runtime(
            "record-step",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--step-id",
            "confirm_tachometer_reference_half_flow",
            "--status",
            "failed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Tachometer mismatch",
        )
        self.assertEqual(0, second.returncode)

        flow_state = json.loads(
            (self.run_dir / "state" / "flows" / "FCU-01A.json").read_text(encoding="utf-8")
        )
        step = [
            s for s in flow_state["steps"] if s["step_id"] == "confirm_tachometer_reference_half_flow"
        ][0]
        self.assertEqual("failed", step["status"])
        self.assertEqual("failed", step["history"][-1]["new_status"])

    def test_record_step_prior_failed_blocks_later_steps(self) -> None:
        init_result = _run_runtime(
            "init-run",
            "--run-dir",
            str(self.run_dir),
            "--job-id",
            "job-flow-prior-fail-block",
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

        fail_first = _run_runtime(
            "record-step",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--step-id",
            "half_design_airflow_auto",
            "--status",
            "failed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Could not reach half design",
        )
        self.assertEqual(0, fail_first.returncode)

        second = _run_runtime(
            "record-step",
            "--run-dir",
            str(self.run_dir),
            "--controller-label",
            "FCU-01A",
            "--step-id",
            "confirm_tachometer_reference_half_flow",
            "--status",
            "passed",
            "--technician-name",
            "Alex Tech",
            "--note",
            "Try after prior failed",
        )
        self.assertEqual(2, second.returncode)
        self.assertIn("before 'half_design_airflow_auto' is completed", second.stdout)
