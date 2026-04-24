"""Tests for ``tools.runtime.repo_root`` (PyInstaller-friendly path resolution)."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class RepoRootTests(unittest.TestCase):
    def test_repo_root_contains_tools_and_docs(self) -> None:
        from tools.runtime.repo_root import repo_root

        base = repo_root()
        self.assertTrue((base / "tools" / "import" / "compile_job.py").is_file())
        self.assertTrue((base / "docs" / "examples").is_dir())


if __name__ == "__main__":
    unittest.main()
