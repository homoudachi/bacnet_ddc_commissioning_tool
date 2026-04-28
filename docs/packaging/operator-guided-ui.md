# Operator GUI (`operator-gui`) — guided screenshots

The **guided** view is at **`http://127.0.0.1:<port>/guided`** after starting:

```bash
python3 tools/runtime/app.py operator-gui --run-dir <run-dir> --gui-port 8765
```

The **Quick BACnet** strip uses three cards: **Read one point**, **Read batch** (lines → **`bacnet-read-batch`**; transport **Multiple** vs **Sequential**), and **Write present value**. Success toasts summarize values (batch shows first few `object=value` pairs). The advanced **`/`** page uses a light card layout aligned with the guided header link.

**Shared technician:** On **`/guided`**, enter your name in **Shared technician name** before Quick BACnet writes (and as the default for modulation, session, record-step, etc.). The browser stores it in **`sessionStorage`** under **`bacnet_op_technician_name`** so it survives reloads; **`/dashboard`** toolbar uses the same key so guided and dashboard stay in sync.

**Deep links:** **`/guided?controller=FCU-01A&step=half_design_airflow_auto`** selects that controller and step when they exist (otherwise falls back to **next open**). Choosing a step updates the URL with **`history.replaceState`** for bookmarking.

**Jump to next:** **Jump to next open step** selects **`next_open_step`** from **`commissioning-guided-next`** and scrolls it into view in the step list.

**`/dashboard`** lists every controller from **`runtime-job.json`** in a responsive grid. Each card shows **flow progress** (from **`state/flows/<label>.json`** after **`init-flow`**), **Read mode / MSV** (uses profile **`msv_test_mode`** or the first **multiStateValue** in **`objects_by_id`**), and **Refresh I/O snapshot** (batch read of the first few **`point_checkout`** objects — on demand, no background polling). Cards also have **Probe B/IP** (`probe-bip`), the same manual **read / read batch / write** controls as guided (toolbar **Technician** is required for writes), per-card result toasts, and **Open in guided →** (`/guided?controller=…`). Long BACnet calls disable the clicked button and show a short **Working…** label.

**Guided step list:** **Filter steps** narrows the list by step id or label substring. **`j`** / **`k`** move among **visible** steps when focus is not in an input. BACnet and other slow actions show **busy** button state.

## Screenshots in this repo

Static captures (example run with `docs/examples/site-controllers.template.csv` + **`init-flow`** for **FCU-01A**) live under **`docs/assets/`**:

| File | Description |
|------|-------------|
| [`operator-guided-ui-wide.png`](../assets/operator-guided-ui-wide.png) | Desktop-width guided view (two columns) |
| [`operator-guided-ui-mobile.png`](../assets/operator-guided-ui-mobile.png) | Narrow viewport (stacked layout) |
| [`operator-dashboard-wide.png`](../assets/operator-dashboard-wide.png) | Dashboard: all controllers + manual BACnet |
| [`operator-advanced-cli-form.png`](../assets/operator-advanced-cli-form.png) | Advanced **`/`** allowlisted CLI form |

## Regenerating locally

From the repository root (requires **`google-chrome-stable`** on `PATH`):

```bash
tools/packaging/capture_operator_guided_screenshots.sh update
```

Optional: `RUN_DIR`, `OPERATOR_GUI_SCREENSHOT_PORT`, `CHROME_BIN`.

After changing **`/guided`**, **`/dashboard`**, or **`/`** HTML/CSS, re-run **`update`**, commit the PNGs, and update **`tests/test_operator_guided_screenshots_checksums.py`** (the script prints the new SHA-256 lines).

## CI

`simulator-verification` runs **`tools/packaging/capture_operator_guided_screenshots.sh check`** so accidental PNG drift is caught unless checksums are updated with the images.
