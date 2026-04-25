"""Contract tests for Docker BACnet CI smoke (no Docker required).

Ensures profiles and smoke script stay aligned so analog WriteProperty is exercised
when `tools/simulator/docker_bacnet_smoke.sh` runs in CI.
"""

from __future__ import annotations

import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DockerBacnetSmokeContractTests(unittest.TestCase):
    def test_docker_sim_csv_uses_fcu_profile_with_analog_write_allowlist(self) -> None:
        csv_path = ROOT / "docs" / "examples" / "site-controllers.docker-bacnet-sim.csv"
        text = csv_path.read_text(encoding="utf-8")
        self.assertIn("fcu_2pipe_chw_electric_heat_docker_sim_v1", text)
        self.assertNotIn("FCU-DOCKER,fcu_2pipe_chw_electric_heat_v1,", text)

    def test_fcu_docker_sim_profile_allows_analog_writes_and_reads(self) -> None:
        path = ROOT / "docs" / "examples" / "unit-profile-fcu.docker-bacnet-sim.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["profile_id"], "fcu_2pipe_chw_electric_heat_docker_sim_v1")
        w = data["commissioning_write_allowlist"]
        self.assertIn("msv_test_mode", w)
        self.assertIn("av_electric_heat_command", w)
        self.assertIn("ao_chw_valve", w)
        r = data["commissioning_read_allowlist"]
        for oid in ("ai_sat", "msv_test_mode", "av_electric_heat_command", "ao_chw_valve"):
            self.assertIn(oid, r)
        ids = {e["object_id"] for e in data["point_checkout"]}
        self.assertTrue({"av_electric_heat_command", "ao_chw_valve"}.issubset(ids))

    def test_hrv_example_profile_allows_fan_commands_for_docker_smoke(self) -> None:
        path = ROOT / "docs" / "examples" / "unit-profile-hrv.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        w = data["commissioning_write_allowlist"]
        self.assertIn("av_supply_fan_command", w)
        self.assertIn("av_exhaust_fan_command", w)
        r = data["commissioning_read_allowlist"]
        self.assertIn("av_supply_fan_command", r)
        self.assertIn("av_exhaust_fan_command", r)
        ids = {e["object_id"] for e in data["point_checkout"]}
        self.assertIn("av_supply_fan_command", ids)
        self.assertIn("av_exhaust_fan_command", ids)

    def test_docker_bacnet_smoke_script_exercises_analog_writes(self) -> None:
        script = ROOT / "tools" / "simulator" / "docker_bacnet_smoke.sh"
        body = script.read_text(encoding="utf-8")
        for needle in (
            "av_electric_heat_command",
            "ao_chw_valve",
            "FCU-DOCKER-C:ai_sat",
            "HRV-DOCKER:av_supply_fan_command",
            "HRV-DOCKER:av_exhaust_fan_command",
            "bacnet-subscribe-cov",
            "bacnet-write-batch",
            "--mode multiple",
            "bacnet_read_property_multiple",
            "bacnet-read-batch",
            "readPropertyMultiple",
        ):
            self.assertIn(needle, body, msg=f"missing smoke fragment: {needle!r}")

    def test_bbmd_lab_smoke_script_exists(self) -> None:
        script = ROOT / "tools" / "simulator" / "docker_bbmd_lab_smoke.sh"
        body = script.read_text(encoding="utf-8")
        self.assertIn("bacnet-bbmd-lab", body)
        self.assertIn("bacnet-bbmd-probe", body)


if __name__ == "__main__":
    unittest.main()
