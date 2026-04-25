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
        "8d999fd156a1d8e232ccfb7f28c023cc6aefb223a1078239aa49f358b8e90d29"
    ),
    "operator-guided-ui-mobile.png": (
        "4ac04309eafbb2cbfcfc0c600f53837680a764f7c3133b6d6bff385b078f9c02"
    ),
    "operator-advanced-cli-form.png": (
        "46273217b73fa148a5a99cb442d48e77b3e7ca69f0fac0e293bc526ff51aa1d4"
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
