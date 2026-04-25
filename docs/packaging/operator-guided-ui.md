# Operator GUI (`operator-gui`) — guided screenshots

The **guided** view is at **`http://127.0.0.1:<port>/guided`** after starting:

```bash
python3 tools/runtime/app.py operator-gui --run-dir <run-dir> --gui-port 8765
```

The guided strip includes **Quick read** (single allowlisted point), **Quick read batch** (multiple **`--read`** lines → **`bacnet-read-batch`**, default ReadPropertyMultiple), and **Quick write**.

## Screenshots in this repo

Static captures (example run with `docs/examples/site-controllers.template.csv` + **`init-flow`** for **FCU-01A**) live under **`docs/assets/`**:

| File | Description |
|------|-------------|
| [`operator-guided-ui-wide.png`](../assets/operator-guided-ui-wide.png) | Desktop-width guided view (two columns) |
| [`operator-guided-ui-mobile.png`](../assets/operator-guided-ui-mobile.png) | Narrow viewport (stacked layout) |
| [`operator-advanced-cli-form.png`](../assets/operator-advanced-cli-form.png) | Advanced **`/`** allowlisted CLI form |

## Regenerating locally

From the repository root (requires **`google-chrome-stable`** on `PATH`):

```bash
tools/packaging/capture_operator_guided_screenshots.sh update
```

Optional: `RUN_DIR`, `OPERATOR_GUI_SCREENSHOT_PORT`, `CHROME_BIN`.

After changing **`/guided`** or **`/`** HTML/CSS, re-run **`update`**, commit the three PNGs, and update **`tests/test_operator_guided_screenshots_checksums.py`** (the script prints the new SHA-256 lines).

## CI

`simulator-verification` runs **`tools/packaging/capture_operator_guided_screenshots.sh check`** so accidental PNG drift is caught unless checksums are updated with the images.
