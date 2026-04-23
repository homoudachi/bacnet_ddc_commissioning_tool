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
