"""Golden SHA-256 for operator GUI screenshots (see capture_operator_guided_screenshots.sh).

When `/guided`, `/dashboard`, or `/` HTML/CSS changes, run:

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
        "294eb332927e073558592696c562ac5814365714dfc71b36f26514f0479566ec"
    ),
    "operator-guided-ui-mobile.png": (
        "d89ea7bc326a7a1f2c5b16c87a5bea48a1b62874f1c55cc59d9fcd948e41bf6d"
    ),
    "operator-dashboard-wide.png": (
        "7b2d8908e23c2c9bde4d3173efc40ef26e80c1a63298e5c259050377864659d0"
    ),
    "operator-advanced-cli-form.png": (
        "16269a84af08331ff581521fb957d33dd4d705c6e2c8272299207cc740d9104c"
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
