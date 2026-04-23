import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN_MATRIX = ROOT / "tools" / "simulator" / "run_matrix.py"


class RunMatrixTests(unittest.TestCase):
    def test_matrix_runner_writes_artifacts_and_returns_nonzero_on_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            controllers = tmpdir / "controllers.csv"
            scenarios = tmpdir / "scenarios"
            output_dir = tmpdir / "artifacts"
            matrix = tmpdir / "matrix.json"
            scenarios.mkdir(parents=True, exist_ok=True)

            controllers.write_text(
                "\n".join(
                    [
                        "controller_label,profile_id,bacnet_device_instance,bacnet_ip,bacnet_port,building_floor,notes",
                        "FCU-01A,fcu_2pipe_chw_electric_heat_v1,21001,192.168.1.50,47808,L01,example row",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            (scenarios / "happy-path.example.json").write_text(
                json.dumps(
                    {"rows": [{"controller_label": "FCU-01A", "status": "reachable_verified"}]},
                    indent=2,
                ),
                encoding="utf-8",
            )
            (scenarios / "identity-mismatch.example.json").write_text(
                json.dumps(
                    {"rows": [{"controller_label": "FCU-01A", "status": "identity_mismatch"}]},
                    indent=2,
                ),
                encoding="utf-8",
            )

            matrix.write_text(
                json.dumps(
                    [
                        {"profile": "ci", "scenario": "happy-path", "strict": True},
                        {"profile": "ci", "scenario": "identity-mismatch", "strict": True},
                    ],
                    indent=2,
                ),
                encoding="utf-8",
            )

            cmd = [
                sys.executable,
                str(RUN_MATRIX),
                "--controllers-csv",
                str(controllers),
                "--scenarios-dir",
                str(scenarios),
                "--output-dir",
                str(output_dir),
                "--matrix",
                str(matrix),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            self.assertEqual(2, result.returncode)
            self.assertIn("matrix_complete", result.stdout)
            happy_artifact = output_dir / "ci-happy-path.json"
            mismatch_artifact = output_dir / "ci-identity-mismatch.json"
            self.assertTrue(happy_artifact.exists())
            self.assertTrue(mismatch_artifact.exists())
            happy_json = json.loads(happy_artifact.read_text(encoding="utf-8"))
            mismatch_json = json.loads(mismatch_artifact.read_text(encoding="utf-8"))
            self.assertTrue(happy_json["strict_pass"])
            self.assertFalse(mismatch_json["strict_pass"])

