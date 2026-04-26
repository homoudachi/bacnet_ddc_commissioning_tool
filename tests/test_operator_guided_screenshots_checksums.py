"""Golden SHA-256 for operator GUI screenshots (see capture_operator_guided_screenshots.sh).

When /guided or / HTML/CSS changes, run:

  tools/packaging/capture_operator_guided_screenshots.sh update

Then update the hashes below to match `sha256sum docs/assets/operator-*.png`.
"""

from __future__ import annotations

import hashlib
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]

_EXPECTED_SHA256 = {
    "operator-guided-ui-wide.png": (
        "232ee913bf88b528ad9c549e5f0b4101c6763beb2004c5b7688dd4d16496360a"
    ),
    "operator-guided-ui-mobile.png": (
        "4b303f211d522ac0c51a42f49117575b66732cf670dcbe3d381d8f8cccb50e0d"
    ),
    "operator-advanced-cli-form.png": (
        "f4c5f22a9e8f11c85eedb172b2fe4f1e2dee19a13716d062ba171bcf1f61d2b8"
    ),
}


class OperatorGuidedScreenshotChecksumTests(unittest.TestCase):
    def test_committed_pngs_match_expected_sha256(self) -> None:
        assets = ROOT / "docs" / "assets"
        for name, expected in _EXPECTED_SHA256.items():
            path = assets / name
            self.assertTrue(path.is_file(), msg=f"missing {path}")
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(
                expected,
                h,
                msg=(
                    f"{name} changed (got {h}). Run "
                    f"tools/packaging/capture_operator_guided_screenshots.sh update "
                    f"and refresh tests/test_operator_guided_screenshots_checksums.py"
                ),
            )


if __name__ == "__main__":
    unittest.main()
