# Plan: Operator UI refinement (guided + dashboard + advanced)

Audience: implementers iterating on **`tools/operator_gui_server.py`** after the first **guided**, **dashboard**, and **advanced CLI** pages shipped.

## Goal

Make the local operator UI **faster for repeat field use**, **easier to navigate** across controllers and steps, and **visually consistent**—without replacing the stdlib server or duplicating commissioning policy in JavaScript.

## Non-goals (this slice)

- Replacing **HTTPServer** with a SPA framework.
- Moving **record-step** / allowlist rules into the browser (server-side CLI remains authoritative).
- macOS **Tauri** layout changes unless they are one-line shell/docs updates.

## Assessment (current strengths / gaps)

**Strengths**

- **/guided** exposes real **`commissioning-guided-next`** data, action forms tied to profile actions, and **Quick BACnet** with RPM batching.
- **/dashboard** gives per-controller read / batch / write / probe without leaving the run-dir context.
- **/advanced** remains an escape hatch for uncommon CLI flags.

**Gaps**

1. **Technician name** sits low on **/guided** even though **Quick BACnet writes** and several forms require it first—operators scroll unnecessarily.
2. **No deep links** from dashboard cards back into **/guided** for the same controller (and no URL to bookmark a controller + step).
3. **Loading / in-flight** feedback is minimal on long BACnet calls (probe, batch read, modulation).
4. **Visual drift**: **/dashboard** input chrome differs slightly from **/guided**; **/** (advanced) is light-themed while the rest is dark—acceptable but jarring when hopping links.
5. **Discoverability**: operators may not notice **RPM vs sequential** batch mode without reading the hint every time.

## Phased work

### Phase 1 — Quick wins (shipped incrementally in repo)

- [x] Move **shared technician** block above **Quick BACnet** on **/guided**; persist **`commonTech`** (and dashboard **`dashTech`**) in **`sessionStorage`**.
- [x] **Deep links**: **`/guided?controller=…&step=…`**; dashboard cards link **“Open in guided”** with controller query.
- [x] **“Jump to next open step”** control when **`commissioning-guided-next`** reports **`next_open_step`**.
- [x] Align **/dashboard** control styling closer to **/guided** (surface tokens, slightly larger tap targets).

### Phase 2 — Feedback and resilience

- [ ] Disable primary buttons and show **“Working…”** (or `aria-busy`) during **`fetch`** for BACnet and long-running actions; re-enable on settle.
- [ ] Optional **last BACnet result** strip (collapsed by default) storing the last JSON **status** line per page for support screenshots.

### Phase 3 — Navigation and power use

- [ ] **Search / filter** step list by id or label substring when flows have many steps.
- [ ] **Keyboard**: `j` / `k` for next/previous step in the focused controller (when focus is not in an input).

### Phase 4 — Theming (optional)

- [ ] Either **darken /advanced** to match guided/dashboard, or add a **compact “operator”** stylesheet shared across all three routes via duplicated `:root` tokens reduced to one Python helper (small refactor).

## Files

- Primary: `tools/operator_gui_server.py`
- Tests: `tests/test_operator_gui_server.py`
- Screenshot automation (when visuals change): `tools/packaging/capture_operator_guided_screenshots.sh`, `tests/test_operator_guided_screenshots_checksums.py`
- Product cross-links: `docs/project.md`, `docs/packaging/operator-guided-ui.md`

## Verification

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_*.py'
```

Pass: all tests green; manually open **`/guided?controller=…`**, **`/dashboard`**, and confirm technician persistence across reload on the same origin.

## Revision

- **2026-04-24:** Initial plan (post-dashboard assessment).
