"""Unit tests for ``tools/runtime/events_log.py`` (``events.jsonl`` rotation)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "runtime"))

import events_log as el  # noqa: E402


class EventsLogRotationTests(unittest.TestCase):
    def tearDown(self) -> None:
        for key in (
            "COMMISSIONING_EVENTS_MAX_BYTES",
            "COMMISSIONING_EVENTS_RETENTION_FILES",
        ):
            os.environ.pop(key, None)

    def test_config_from_runtime_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "config").mkdir(parents=True)
            (run_dir / "config" / "runtime-config.json").write_text(
                json.dumps(
                    {
                        "job_id": "x",
                        "events_log": {
                            "rotate_max_bytes": 5000,
                            "retention_files": 4,
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            cfg = el.events_log_config(run_dir)
            self.assertEqual(5000, cfg["rotate_max_bytes"])
            self.assertEqual(4, cfg["retention_files"])

    def test_env_overrides_config(self) -> None:
        os.environ["COMMISSIONING_EVENTS_MAX_BYTES"] = "9000"
        os.environ["COMMISSIONING_EVENTS_RETENTION_FILES"] = "5"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "config").mkdir(parents=True)
            (run_dir / "config" / "runtime-config.json").write_text(
                json.dumps(
                    {
                        "job_id": "x",
                        "events_log": {
                            "rotate_max_bytes": 100,
                            "retention_files": 99,
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            cfg = el.events_log_config(run_dir)
            self.assertEqual(9000, cfg["rotate_max_bytes"])
            self.assertEqual(5, cfg["retention_files"])

    def test_rotate_renames_and_caps_files(self) -> None:
        os.environ["COMMISSIONING_EVENTS_MAX_BYTES"] = "80"
        os.environ["COMMISSIONING_EVENTS_RETENTION_FILES"] = "3"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            logs = run_dir / "logs"
            logs.mkdir(parents=True)
            (run_dir / "config").mkdir(parents=True)
            (run_dir / "config" / "runtime-config.json").write_text(
                json.dumps({"job_id": "j", "events_log": {}}, indent=2),
                encoding="utf-8",
            )
            log_path = el.events_jsonl_path(run_dir)
            log_path.write_text("x" * 100 + "\n", encoding="utf-8")
            el.maybe_rotate_events_jsonl(run_dir)
            self.assertFalse(log_path.is_file())
            self.assertTrue((logs / "events.jsonl.1").is_file())
            self.assertEqual(101, (logs / "events.jsonl.1").stat().st_size)

            # As after real appends: new active log then rotate again.
            log_path.write_text("y" * 100 + "\n", encoding="utf-8")
            el.maybe_rotate_events_jsonl(run_dir)
            self.assertFalse(log_path.is_file())
            self.assertTrue((logs / "events.jsonl.1").is_file())
            self.assertTrue((logs / "events.jsonl.2").is_file())
            self.assertFalse((logs / "events.jsonl.3").exists())

            # Third rotation: oldest archive (.2) removed; keep two archives + future active
            log_path.write_text("z" * 100 + "\n", encoding="utf-8")
            el.maybe_rotate_events_jsonl(run_dir)
            self.assertFalse(log_path.is_file())
            self.assertTrue((logs / "events.jsonl.1").is_file())
            self.assertTrue((logs / "events.jsonl.2").is_file())
            self.assertFalse((logs / "events.jsonl.3").exists())

    def test_parse_human_sizes(self) -> None:
        self.assertEqual(2048, el._parse_positive_int("2k", name="t"))
        self.assertEqual(3 * 1024 * 1024, el._parse_positive_int("3m", name="t"))


if __name__ == "__main__":
    unittest.main()
