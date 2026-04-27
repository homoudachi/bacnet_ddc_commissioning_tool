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
        "b209f986524c454a3358b3fdb36603151d8779852e726fd1d4967554c33e37a2"
    ),
    "operator-guided-ui-mobile.png": (
        "ae606ffc2222671306016d7b123d2ef11fec8f9b254d571c4fb5a0b641c2805b"
    ),
    "operator-dashboard-wide.png": (
        "0f0d1cefef4b257c6a95afee3af55650902601a9b7139a7ea55e7d3704eaceca"
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
