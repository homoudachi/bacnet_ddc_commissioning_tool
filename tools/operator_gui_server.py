#!/usr/bin/env python3
"""Browser UI for commissioning run-dir (stdlib HTTPServer).

Modes:

* **/** — Advanced form: POST to ``/cli`` with allowlisted subcommands + free-form extra args.
* **/guided** — Graphical guided flow: pick controller, view steps / next / blockers, **forms** for
  modulation sweep, airflow adjust, closed-loop iterate, manual airflow, valve prompts, tachometer
  confirm, plus session + record-step (all via the same ``tools/runtime/app.py`` CLI).
* **/dashboard** — All controllers from ``runtime-job.json`` on one screen: BACnet **read**,
  **read batch**, **write**, and **B/IP probe** per card (same allowlists as CLI).

Bind to **127.0.0.1** by default (local operator machine only).

Usage (from repo root)::

    python3 tools/runtime/app.py operator-gui --run-dir artifacts/my-run

Or directly::

    python3 tools/operator_gui_server.py --run-dir artifacts/my-run --port 8765
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CLI = ROOT / "tools" / "runtime" / "app.py"

# Prefix allowlist for POST /cli (free-form extra args).
ALLOWED_PREFIXES = (
    "show-flow",
    "show-session",
    "list-flows",
    "commissioning-guided-next",
    "set-session-value",
    "record-step",
    "probe-bip",
    "bacnet-read",
    "bacnet-read-batch",
    "dry-run-bacnet-write",
    "bacnet-subscribe-cov",
    "bacnet-write-batch",
    "commissioning-airflow-adjust-write",
    "commissioning-airflow-closed-loop-iterate",
    "commissioning-confirm-tachometer-reference",
    "commissioning-record-manual-airflow",
    "commissioning-confirm-prompt",
    "export-run-summary",
    "export-commissioning-report",
)

# Exact subcommands for JSON API (no user-controlled argv[0] beyond this set).
_GUIDED_API_COMMANDS = frozenset(
    {
        "list-flows",
        "commissioning-guided-next",
        "show-session",
        "set-session-value",
        "record-step",
        "probe-bip",
        "bacnet-point-checkout",
        "bacnet-read",
        "bacnet-read-batch",
        "dry-run-bacnet-write",
        "bacnet-modulation-sweep",
        "commissioning-airflow-adjust-write",
        "commissioning-airflow-closed-loop-iterate",
        "commissioning-confirm-tachometer-reference",
        "commissioning-record-manual-airflow",
        "commissioning-confirm-prompt",
    }
)


def _flow_state_path(run_dir: Path, controller_label: str) -> Path:
    return run_dir / "state" / "flows" / f"{controller_label}.json"


def _session_state_path(run_dir: Path, controller_label: str) -> Path:
    return run_dir / "state" / "sessions" / f"{controller_label}.json"


def _runtime_job_path(run_dir: Path) -> Path:
    return run_dir / "state" / "runtime-job.json"


def _dashboard_controller_summaries(job: dict[str, Any]) -> list[dict[str, Any]]:
    """Lightweight rows for dashboard cards (no full objects_by_id)."""
    out: list[dict[str, Any]] = []
    for c in job.get("controllers", []) or []:
        if not isinstance(c, dict):
            continue
        lab = str(c.get("controller_label", "")).strip()
        if not lab:
            continue
        prof = str(c.get("profile_id", "")).strip()
        b = c.get("bacnet") if isinstance(c.get("bacnet"), dict) else {}
        host = str(b.get("host", "")).strip()
        port_raw = b.get("port", "")
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = 0
        try:
            dev_inst = int(b.get("device_instance", 0))
        except (TypeError, ValueError):
            dev_inst = 0
        allow_r = c.get("commissioning_read_allowlist") or []
        allow_w = c.get("commissioning_write_allowlist") or []
        if not isinstance(allow_r, list):
            allow_r = []
        if not isinstance(allow_w, list):
            allow_w = []
        rc = sum(1 for x in allow_r if str(x).strip())
        wc = sum(1 for x in allow_w if str(x).strip())
        out.append(
            {
                "controller_label": lab,
                "profile_id": prof,
                "bacnet_host": host,
                "bacnet_port": port,
                "bacnet_device_instance": dev_inst,
                "read_allowlist_count": rc,
                "write_allowlist_count": wc,
            }
        )
    return out


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _controller_row(job: dict[str, Any], label: str) -> dict[str, Any] | None:
    for c in job.get("controllers", []) or []:
        if isinstance(c, dict) and str(c.get("controller_label", "")).strip() == label:
            return c
    return None


def _find_flow_step(flow: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    for s in flow.get("steps", []) or []:
        if isinstance(s, dict) and str(s.get("step_id", "")).strip() == step_id:
            return s
    return None


def _actions_list(step: dict[str, Any]) -> list[dict[str, Any]]:
    raw = step.get("actions")
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, dict)]


def _build_step_hints(*, run_dir: Path, controller_label: str, step_id: str) -> dict[str, Any]:
    """Pure JSON hints for /guided action forms (no subprocess)."""
    sid = str(step_id).strip()
    if not sid:
        return {"error": "step_id required"}
    label = str(controller_label).strip()
    if not label:
        return {"error": "controller required"}

    flow = _load_json(_flow_state_path(run_dir, label))
    if flow is None:
        return {"error": "flow_state_not_found", "path": str(_flow_state_path(run_dir, label))}

    step = _find_flow_step(flow, sid)
    if step is None:
        return {"error": "step_not_found", "step_id": sid}

    job = _load_json(_runtime_job_path(run_dir)) or {}
    ctrl = _controller_row(job, label)
    meta = ctrl.get("commissioning_meta") if isinstance(ctrl, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    av = meta.get("airflow_verification") if isinstance(meta.get("airflow_verification"), dict) else {}
    branches_meta = av.get("branches") if isinstance(av.get("branches"), list) else []

    actions = _actions_list(step)
    forms: list[dict[str, Any]] = []

    for act in actions:
        t = str(act.get("type", "")).strip()
        if t == "modulate_actuator_log_sat_for_report":
            forms.append(
                {
                    "id": "modulation_sweep",
                    "title": "Modulation sweep (writes command %, reads SAT/RAT, logs report)",
                    "profile": {
                        "command_object_id": act.get("command_object_id"),
                        "sat_object_id": act.get("result_supply_temperature_object_id"),
                    },
                }
            )
        elif t == "automatic_airflow_adjustment":
            oid = str(act.get("actuator_object_id", "")).strip()
            cl = act.get("closed_loop")
            has_cl = isinstance(cl, dict) and bool(cl.get("enabled"))
            if has_cl:
                forms.append(
                    {
                        "id": "airflow_closed_loop",
                        "title": "Closed-loop airflow iterate (profile closed_loop)",
                        "profile": {
                            "actuator_object_id": oid or None,
                            "flow_read_object_id": cl.get("flow_read_object_id") if isinstance(cl, dict) else None,
                        },
                    }
                )
            else:
                forms.append(
                    {
                        "id": "airflow_adjust",
                        "title": "Airflow adjust (write fan / actuator %)",
                        "profile": {"actuator_object_id": oid or None},
                    }
                )
        elif t == "manual_airflow_verification_assisted":
            raw_b = act.get("branch_ids")
            bid_set: list[str] = []
            if isinstance(raw_b, list):
                bid_set = [str(b).strip() for b in raw_b if str(b).strip()]
            branch_options: list[dict[str, Any]] = []
            for bid in bid_set:
                tool_choices: list[str] = []
                design = None
                for br in branches_meta:
                    if not isinstance(br, dict):
                        continue
                    if str(br.get("id", "")).strip() != bid:
                        continue
                    try:
                        d = br.get("design_flow_L_s")
                        if d is not None:
                            design = float(d)
                    except (TypeError, ValueError):
                        design = None
                    meas = br.get("measurement") if isinstance(br.get("measurement"), dict) else {}
                    al = meas.get("allowed_tools")
                    if isinstance(al, list):
                        tool_choices = [str(x).strip() for x in al if str(x).strip()]
                    break
                branch_options.append(
                    {
                        "branch_id": bid,
                        "design_flow_L_s": design,
                        "allowed_tools": tool_choices,
                    }
                )
            forms.append(
                {
                    "id": "manual_airflow",
                    "title": "Record manual airflow measurement (L/s)",
                    "profile": {"branch_options": branch_options},
                }
            )
        elif t == "operator_prompt_confirm":
            pid = str(act.get("prompt_id", "")).strip()
            if pid:
                forms.append(
                    {
                        "id": "valve_prompt",
                        "title": f"Valve / operator prompt confirm ({pid})",
                        "profile": {"prompt_id": pid, "prompt_text": act.get("prompt_text", "")},
                    }
                )
        elif t == "operator_confirm_tachometer_reference":
            forms.append(
                {
                    "id": "tachometer_confirm",
                    "title": "Confirm tachometer reference (BACnet read + session)",
                    "profile": {
                        "read_object_id": act.get("read_object_id"),
                        "session_key": act.get("session_key"),
                    },
                }
            )

    return {
        "controller_label": label,
        "step_id": sid,
        "step_label": str(step.get("label", "")).strip(),
        "forms": forms,
    }


def _argv_append_optional_bacnet(argv: list[str], body: dict[str, Any]) -> None:
    """Append --bacnet-* / --apdu-timeout when present on JSON body (guided API only)."""
    for key, flag in (
        ("bacnet_timeout_seconds", "--bacnet-timeout-seconds"),
        ("bacnet_retries", "--bacnet-retries"),
        ("bacnet_bind_port", "--bacnet-bind-port"),
        ("apdu_timeout", "--apdu-timeout"),
    ):
        if key not in body or body[key] is None or body[key] == "":
            continue
        argv.extend([flag, str(body[key])])


def _page(run_dir: Path) -> bytes:
    rd = html.escape(str(run_dir.resolve()))
    opts = "".join(f"<option>{html.escape(p)}</option>" for p in ALLOWED_PREFIXES)
    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Commissioning operator</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root {{ --bg: #f6f7f9; --card: #fff; --text: #1a1d21; --muted: #5c6570; --accent: #0b5fff; --border: #d8dee6; }}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; background: var(--bg); color: var(--text); line-height: 1.5; }}
.wrap {{ max-width: 44rem; margin: 0 auto; padding: 1.5rem 1.25rem 2.5rem; }}
h1 {{ font-size: 1.35rem; font-weight: 650; margin: 0 0 0.35rem; letter-spacing: -0.02em; }}
label {{ display: block; margin-top: 1rem; font-weight: 600; font-size: 0.82rem; color: var(--muted); }}
input, textarea, select {{
  width: 100%; margin-top: 0.35rem; padding: 0.55rem 0.65rem; border: 1px solid var(--border);
  border-radius: 8px; font-size: 0.95rem; background: #fff;
}}
textarea {{ font-family: ui-monospace, monospace; min-height: 7rem; }}
textarea:focus, select:focus {{ outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(11,95,255,0.15); }}
pre {{ background: #eef1f5; padding: 0.75rem; overflow: auto; border-radius: 8px; border: 1px solid var(--border); font-size: 0.85rem; }}
button {{
  margin-top: 1.1rem; padding: 0.55rem 1.15rem; border: none; border-radius: 8px;
  background: var(--accent); color: #fff; font-weight: 600; font-size: 0.95rem; cursor: pointer;
}}
button:hover {{ filter: brightness(1.06); }}
.meta {{ color: var(--muted); font-size: 0.9rem; margin: 0.35rem 0; }}
.meta a {{ color: var(--accent); font-weight: 500; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.15rem 1.25rem; margin-top: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
</style></head>
<body>
<div class="wrap">
<h1>Commissioning operator (local)</h1>
<p class="meta">Run dir: <code>{rd}</code></p>
<p class="meta"><a href="/guided">Guided flow UI</a> · <a href="/dashboard">Dashboard</a> (all controllers)</p>
<p class="meta">Commands run as subprocess to <code>tools/runtime/app.py</code>. Bind defaults to loopback only.</p>
<div class="card">
<form method="post" action="/cli">
<label for="cmdSel">Command</label>
<select id="cmdSel" name="command">{opts}</select>
<label for="extraArgs">Extra arguments (one per line)</label>
<textarea id="extraArgs" name="extra" placeholder="--controller-label FCU-01A&#10;--step-id some_step"></textarea>
<button type="submit">Run</button>
</form>
</div>
<p class="meta">Examples: <code>set-session-value</code> needs <code>--key rat_degC --value 22 --technician-name Me --note ...</code>;
<code>record-step</code> needs <code>--step-id ... --status passed --technician-name ...</code>.</p>
</div>
</body></html>"""
    return body.encode("utf-8")


def _guided_page(run_dir: Path) -> bytes:
    rd = json.dumps(str(run_dir.resolve()))
    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Guided commissioning</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root {{
  --bg: #0f1419;
  --panel: #1a2332;
  --surface: #0d1218;
  --text: #e8eef5;
  --muted: #8b9cb3;
  --accent: #3d8bfd;
  --accent-dim: #2a6bc4;
  --ok: #2fb573;
  --warn: #e9a23b;
  --err: #f47174;
  --border: #2d3a4d;
  --radius: 8px;
  --radius-sm: 6px;
  --shadow: 0 2px 12px rgba(0,0,0,0.25);
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  margin: 0; background: var(--bg); color: var(--text); min-height: 100vh;
  line-height: 1.45;
}}
header {{
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;
  background: linear-gradient(180deg, #151c27 0%, var(--bg) 100%);
}}
header h1 {{ font-size: 1.15rem; margin: 0; font-weight: 650; letter-spacing: -0.02em; }}
header .meta {{ color: var(--muted); font-size: 0.85rem; }}
header a {{ color: var(--accent); text-decoration: none; }}
header a:hover {{ text-decoration: underline; }}
.layout {{
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.12fr);
  gap: 0; min-height: calc(100vh - 56px);
}}
@media (max-width: 900px) {{
  .layout {{ grid-template-columns: 1fr; }}
}}
.panel {{
  background: var(--panel); border-right: 1px solid var(--border);
  padding: 1rem 1.15rem; overflow: auto; max-height: calc(100vh - 56px);
}}
.panel:last-child {{ border-right: none; }}
label {{ display: block; font-size: 0.78rem; font-weight: 500; color: var(--muted); margin-top: 0.65rem; }}
select, input, textarea {{
  width: 100%; margin-top: 0.28rem; padding: 0.5rem 0.6rem;
  border-radius: var(--radius-sm); border: 1px solid var(--border);
  background: var(--surface); color: var(--text); font-size: 0.92rem;
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}}
select:hover, input:hover, textarea:hover {{ border-color: #3d4d66; }}
select:focus, input:focus, textarea:focus {{
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(61, 139, 253, 0.25);
}}
textarea {{ min-height: 4.5rem; font-family: ui-monospace, "Cascadia Code", monospace; font-size: 0.8rem; }}
button {{
  margin-top: 0.85rem; padding: 0.52rem 1rem; border-radius: var(--radius-sm); border: none;
  cursor: pointer; font-weight: 600; font-size: 0.9rem; background: var(--accent); color: #fff;
  transition: background 0.12s ease, transform 0.08s ease;
}}
button:hover {{ background: var(--accent-dim); }}
button:active {{ transform: scale(0.98); }}
button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
button.secondary {{ background: #3a4a5e; color: var(--text); }}
button.secondary:hover {{ background: #4a5d78; }}
button.danger {{ background: #a33; }}
.row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; align-items: center; }}
.badge {{
  display: inline-block; padding: 0.12rem 0.42rem; border-radius: 4px;
  font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;
}}
.badge.pending {{ background: #3a4a5e; color: #c5d4e8; }}
.badge.passed, .badge.manual_passed {{ background: #1e5c3d; color: #c8f0dc; }}
.badge.failed {{ background: #6b2224; color: #ffd4d5; }}
.badge.skipped {{ background: #5c4a1e; color: #f5e6b8; }}
.step-list {{ list-style: none; padding: 0; margin: 0.5rem 0 0; max-height: 44vh; overflow: auto; border-radius: var(--radius-sm); }}
.step-list li {{
  padding: 0.55rem 0.65rem; border-radius: var(--radius-sm); margin-bottom: 0.3rem;
  border: 1px solid transparent; cursor: pointer;
}}
.step-list li:hover {{ border-color: var(--border); background: rgba(13,18,24,0.5); }}
.step-list li.active {{ border-color: var(--accent); background: var(--surface); box-shadow: var(--shadow); }}
.step-list li .sid {{ font-family: ui-monospace, monospace; font-size: 0.78rem; color: var(--accent); }}
.flash {{
  margin-top: 0.75rem; padding: 0.65rem 0.85rem; border-radius: var(--radius-sm); font-size: 0.86rem;
  border-left: 3px solid transparent; max-width: 100%; word-break: break-word;
}}
.flash.err {{ background: #3a1a1c; color: #ffb4b6; border-left-color: var(--err); }}
.flash.ok {{ background: #1a2e24; color: #9ee5c0; border-left-color: var(--ok); }}
#blockers {{
  margin-top: 0.85rem; padding: 0.65rem 0.85rem; border-radius: var(--radius-sm);
  border: 1px solid #5c3d1e; background: rgba(92, 74, 30, 0.15);
}}
#blockers h3 {{ margin-top: 0; color: var(--warn); }}
#blockerList {{ margin: 0.35rem 0 0; padding-left: 1.15rem; color: #e8d4b8; font-size: 0.86rem; }}
.cmds {{ margin: 0.5rem 0 0; padding-left: 1.1rem; font-size: 0.82rem; color: var(--muted); }}
.cmds code {{ color: #b8d4ff; font-size: 0.76rem; }}
h2 {{ font-size: 1.02rem; margin: 0 0 0.35rem; font-weight: 650; letter-spacing: -0.015em; }}
h3 {{ font-size: 0.82rem; margin: 1.1rem 0 0.4rem; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }}
.section-lead {{ font-size: 0.82rem; color: var(--muted); margin: 0 0 0.5rem; max-width: 42rem; }}
details {{ margin-top: 0.5rem; color: var(--muted); font-size: 0.85rem; }}
details summary {{ cursor: pointer; }}
details summary:hover {{ color: var(--text); }}
.action-box {{
  border: 1px solid var(--border); border-radius: var(--radius); padding: 0.8rem; margin-top: 0.65rem;
  background: var(--surface);
}}
.action-box h4 {{ margin: 0 0 0.35rem; font-size: 0.88rem; color: var(--text); }}
.small {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.25rem; }}
.quick-section {{ margin-top: 0.5rem; }}
.quick-strip {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
  margin-top: 0.5rem;
}}
.quick-card {{
  padding: 0.75rem 0.85rem; border-radius: var(--radius); border: 1px solid var(--border);
  background: var(--surface); box-shadow: var(--shadow);
}}
.quick-card h4 {{ margin: 0 0 0.25rem; font-size: 0.82rem; color: var(--text); font-weight: 650; }}
.quick-card .hint {{ font-size: 0.74rem; color: var(--muted); margin: 0 0 0.4rem; line-height: 1.35; }}
.quick-card label:first-of-type {{ margin-top: 0; }}
.chk {{ display: flex; align-items: center; gap: 0.45rem; margin-top: 0.5rem; font-size: 0.82rem; color: var(--muted); }}
.chk input {{ width: auto; accent-color: var(--accent); }}
.sess-pre {{
  max-height: 10rem; overflow: auto; background: var(--surface); padding: 0.55rem 0.65rem;
  border-radius: var(--radius-sm); font-size: 0.76rem; border: 1px solid var(--border);
  font-family: ui-monospace, monospace; color: #c5d4e8;
}}
.tech-banner {{
  margin-top: 0.5rem; padding: 0.75rem 0.85rem; border-radius: var(--radius);
  border: 1px solid var(--border); background: var(--surface);
}}
.tech-banner label {{ margin-top: 0; font-size: 0.8rem; color: var(--text); font-weight: 600; }}
.tech-banner input {{ margin-top: 0.35rem; }}
.tech-banner .small {{ margin: 0.35rem 0 0; font-size: 0.74rem; color: var(--muted); }}
.row-actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-top: 0.45rem; }}
.row-actions button {{ margin-top: 0; }}
</style></head>
<body>
<header>
  <h1>Guided commissioning</h1>
  <span class="meta">Run dir: <code id="runDirDisp"></code></span>
  <span class="meta"><a href="/dashboard">Dashboard</a> · <a href="/">Advanced CLI</a></span>
</header>
<div class="layout">
  <div class="panel">
    <h2>Controller</h2>
    <label for="selCtl">Active controller</label>
    <select id="selCtl"></select>
    <button type="button" class="secondary" id="btnReload">Reload controllers</button>
    <div id="ctlFlash" class="flash" style="display:none"></div>
    <h3>All steps</h3>
    <ul class="step-list" id="stepList"></ul>
  </div>
  <div class="panel">
    <h2 id="focusTitle">Select a controller</h2>
    <p id="nextHint" class="meta"></p>
    <div class="row-actions">
      <button type="button" class="secondary" id="btnJumpNext">Jump to next open step</button>
    </div>
    <div class="tech-banner">
      <label for="commonTech">Shared technician name</label>
      <p class="small">Required for <strong>Quick BACnet writes</strong> and used as the default in the forms below. Saved in this browser until you clear it.</p>
      <input id="commonTech" placeholder="Your name (prefills other fields)" autocomplete="name"/>
    </div>
    <div class="quick-section">
      <h3>Quick BACnet</h3>
      <p class="section-lead">Reads and writes use the profile allowlists from <code>compile-import</code>. Batch read defaults to one ReadPropertyMultiple APDU (use sequential if the device rejects RPM).</p>
      <div class="quick-strip">
        <div class="quick-card">
          <h4>Read one point</h4>
          <p class="hint">Single ReadProperty — fastest for one object.</p>
          <label for="qrOid">Object id</label>
          <input id="qrOid" placeholder="e.g. ai_sat or msv_test_mode" autocomplete="off"/>
          <label for="qrProp">Property (optional)</label>
          <input id="qrProp" placeholder="presentValue" value="presentValue" autocomplete="off"/>
          <button type="button" class="secondary" id="btnQrRead">Read</button>
        </div>
        <div class="quick-card">
          <h4>Read batch</h4>
          <p class="hint">One id per line. Optional <code>object:property</code> per line. Max 32 lines.</p>
          <label for="qrbReads">Object ids</label>
          <textarea id="qrbReads" rows="4" placeholder="ai_sat&#10;msv_test_mode" spellcheck="false"></textarea>
          <label for="qrbMode">Transport</label>
          <select id="qrbMode" title="multiple = ReadPropertyMultiple; sequential = one ReadProperty per line">
            <option value="multiple" selected>Multiple (one APDU)</option>
            <option value="sequential">Sequential (compat)</option>
          </select>
          <button type="button" class="secondary" id="btnQrBatch">Read batch</button>
        </div>
        <div class="quick-card">
          <h4>Write present value</h4>
          <p class="hint">MSV values are whole state numbers. Check &quot;Execute&quot; to send on the wire.</p>
          <label for="qwOid">Object id</label>
          <input id="qwOid" placeholder="e.g. msv_test_mode" autocomplete="off"/>
          <label for="qwVal">Value</label>
          <input id="qwVal" placeholder="e.g. 3" inputmode="decimal" autocomplete="off"/>
          <div class="chk"><input type="checkbox" id="qwExec"/><label for="qwExec">Execute write (not dry-run)</label></div>
          <button type="button" class="secondary" id="btnQwWrite">Write</button>
        </div>
      </div>
    </div>
    <div id="detailFlash" class="flash" style="display:none"></div>
    <div id="blockers" style="display:none">
      <h3>Why this step is blocked</h3>
      <ul id="blockerList"></ul>
    </div>
    <h3>Suggested commands</h3>
    <ul class="cmds" id="cmdList"></ul>
    <details id="cmdDetails"><summary>Raw CLI hints</summary><pre id="cmdRaw" style="white-space:pre-wrap;font-size:0.75rem;margin:0.5rem 0 0"></pre></details>
    <div id="actionForms"></div>
    <h3>Tachometer confirm (focused step)</h3>
    <label>Technician</label>
    <input id="tachoTech" placeholder="defaults to shared name"/>
    <label>Note</label>
    <input id="tachoNote" placeholder="optional"/>
    <button type="button" class="secondary" id="btnTacho">Run tachometer confirm for this step</button>
    <h3>Session value</h3>
    <label>Key</label>
    <input id="sessKey" placeholder="e.g. rat_degC or skip code from skip_when"/>
    <label>Value</label>
    <input id="sessVal" placeholder="string value"/>
    <label>Technician</label>
    <input id="sessTech" placeholder="Your name"/>
    <label>Note</label>
    <input id="sessNote" placeholder="optional"/>
    <button type="button" id="btnSess">Save session value</button>
    <h3>Record step</h3>
    <label>Step ID</label>
    <input id="recSid" readonly />
    <label>Status</label>
    <select id="recStatus">
      <option value="passed">passed</option>
      <option value="manual_passed">manual_passed</option>
      <option value="failed">failed</option>
      <option value="skipped">skipped</option>
      <option value="pending">pending (reset)</option>
    </select>
    <label>Technician</label>
    <input id="recTech" placeholder="Your name"/>
    <label>Note</label>
    <input id="recNote" placeholder="optional"/>
    <div class="row">
      <button type="button" id="btnRecord">Record step</button>
      <button type="button" class="secondary" id="btnCheckout">Run point checkout</button>
    </div>
    <h3>Session keys (current)</h3>
    <pre id="sessKeys" class="sess-pre"></pre>
  </div>
</div>
<script>
const RUN_DIR = {rd};
const TECH_KEY = "bacnet_op_technician_name";
document.getElementById("runDirDisp").textContent = RUN_DIR;

function guidedQueryParams() {{
  try {{ return new URLSearchParams(window.location.search); }}
  catch (e) {{ return new URLSearchParams(); }}
}}

function loadSavedTechnician() {{
  try {{
    const v = sessionStorage.getItem(TECH_KEY);
    if (v) {{
      const el = document.getElementById("commonTech");
      if (el && !el.value.trim()) el.value = v;
    }}
  }} catch (e) {{}}
}}

function persistTechnician() {{
  try {{
    const v = document.getElementById("commonTech").value.trim();
    if (v) sessionStorage.setItem(TECH_KEY, v);
    else sessionStorage.removeItem(TECH_KEY);
  }} catch (e) {{}}
}}

document.getElementById("commonTech").addEventListener("input", persistTechnician);
document.getElementById("commonTech").addEventListener("change", persistTechnician);
loadSavedTechnician();

async function apiJson(path, opts) {{
  const r = await fetch(path, Object.assign({{ headers: {{ "Accept": "application/json" }} }}, opts || {{}}));
  const text = await r.text();
  let data = null;
  try {{ data = JSON.parse(text); }} catch (e) {{}}
  if (!r.ok) {{
    const msg = (data && data.error) ? data.error : text.slice(0, 400);
    throw new Error(msg || "request failed");
  }}
  return data;
}}

function showFlash(el, msg, isErr) {{
  el.style.display = "block";
  el.className = "flash " + (isErr ? "err" : "ok");
  el.textContent = msg;
}}

function formatReadSummary(j) {{
  const st = j.status || "";
  const vs = (j.read && j.read.value_str != null) ? j.read.value_str : (j.value_str || "");
  return "Read " + st + (vs ? ": " + vs : "");
}}

function formatBatchSummary(j) {{
  const rows = j.reads || [];
  const ok = rows.filter(r => (r.status || "") === "read_ok").length;
  const parts = [];
  for (const r of rows.slice(0, 5)) {{
    const oid = (r.profile_object_id || "").trim();
    const vs = (r.read && r.read.value_str != null) ? r.read.value_str : (r.value_str || "");
    if (oid) parts.push(vs ? (oid + "=" + vs) : oid);
  }}
  const more = rows.length > 5 ? " (+" + (rows.length - 5) + " more)" : "";
  return "Batch " + ok + "/" + rows.length + " OK" + (parts.length ? ": " + parts.join(", ") : "") + more;
}}

let controllers = [];
let guidance = null;
let selectedStepId = null;

async function loadControllers() {{
  const j = await apiJson("/api/v1/list-flows");
  controllers = (j.flows || []).map(f => f.controller_label).filter(Boolean);
  const sel = document.getElementById("selCtl");
  sel.innerHTML = "";
  for (const c of controllers) {{
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    sel.appendChild(o);
  }}
  if (controllers.length === 0) {{
    showFlash(document.getElementById("ctlFlash"), "No flow state found. Run compile-import then init-flow for a controller.", true);
  }} else {{
    document.getElementById("ctlFlash").style.display = "none";
    const qp = guidedQueryParams();
    const wantCtl = (qp.get("controller") || "").trim();
    const wantStep = (qp.get("step") || "").trim();
    if (wantCtl && controllers.includes(wantCtl)) {{
      document.getElementById("selCtl").value = wantCtl;
    }}
    await loadGuidance({{ preferStep: wantStep || null }});
  }}
}}

function badgeClass(st) {{
  const s = (st || "pending").toLowerCase();
  if (["passed", "manual_passed", "failed", "skipped", "pending"].includes(s)) return "badge " + s;
  return "badge pending";
}}

async function loadGuidance(opts) {{
  opts = opts || {{}};
  const preferStep = (opts.preferStep || "").trim();
  const c = document.getElementById("selCtl").value;
  if (!c) return;
  selectedStepId = null;
  guidance = await apiJson("/api/v1/guidance?controller=" + encodeURIComponent(c));
  const g = guidance.guidance || {{}};
  const steps = g.steps || [];
  const ul = document.getElementById("stepList");
  ul.innerHTML = "";
  for (const row of steps) {{
    const li = document.createElement("li");
    li.dataset.sid = row.step_id;
    li.innerHTML = `<span class="sid">${{row.step_id}}</span> — ${{row.label || ""}} ` +
      `<span class="${{badgeClass(row.status)}}">${{row.status}}</span>`;
    li.addEventListener("click", () => selectStep(row.step_id));
    ul.appendChild(li);
  }}
  const next = g.next_open_step;
  document.getElementById("nextHint").textContent = next
    ? `Next open: ${{next.step_id}} — ${{next.label || ""}} (${{next.status}})`
    : "All steps complete for this controller.";
  await loadSession();
  const stepIds = new Set((steps || []).map(s => s.step_id));
  if (preferStep && stepIds.has(preferStep)) {{
    selectStep(preferStep);
  }} else if (next && next.step_id) {{
    selectStep(next.step_id);
  }}
}}

async function loadSession() {{
  const c = document.getElementById("selCtl").value;
  if (!c) return;
  try {{
    const j = await apiJson("/api/v1/session?controller=" + encodeURIComponent(c));
    const keys = j.session_keys || [];
    document.getElementById("sessKeys").textContent = keys.length ? keys.join("\\n") : "(none)";
  }} catch (e) {{
    document.getElementById("sessKeys").textContent = "(could not load session)";
  }}
}}

async function renderActionForms(c, sid) {{
  const host = document.getElementById("actionForms");
  host.innerHTML = "";
  if (!c || !sid) return;
  let hints;
  try {{
    hints = await apiJson("/api/v1/step-hints?controller=" + encodeURIComponent(c) + "&step_id=" + encodeURIComponent(sid));
  }} catch (e) {{
    const p = document.createElement("p");
    p.className = "small";
    p.textContent = "Could not load step hints: " + e.message;
    host.appendChild(p);
    return;
  }}
  if (hints.error) {{
    const p = document.createElement("p");
    p.className = "small";
    p.textContent = hints.error;
    host.appendChild(p);
    return;
  }}
  const forms = hints.forms || [];
  if (!forms.length) {{
    const p = document.createElement("p");
    p.className = "small";
    p.textContent = "No built-in forms for this step type — use session / record-step or tachometer button if applicable.";
    host.appendChild(p);
    return;
  }}
  const h3 = document.createElement("h3");
  h3.textContent = "Guided actions for this step";
  host.appendChild(h3);
  for (const f of forms) {{
    const box = document.createElement("div");
    box.className = "action-box";
    const h4 = document.createElement("h4");
    h4.textContent = f.title || f.id;
    box.appendChild(h4);
    if (f.id === "modulation_sweep") {{
      const pr = f.profile || {{}};
      if (pr.command_object_id) {{
        const sm = document.createElement("div");
        sm.className = "small";
        sm.textContent = "Command object: " + pr.command_object_id + (pr.sat_object_id ? " · SAT: " + pr.sat_object_id : "");
        box.appendChild(sm);
      }}
      const lbl1 = document.createElement("label");
      lbl1.textContent = "Command percents (comma-separated, e.g. 0,50,100)";
      const inp1 = document.createElement("input");
      inp1.dataset.role = "mod-percents";
      inp1.placeholder = "0,50,100";
      box.appendChild(lbl1);
      box.appendChild(inp1);
      const lbl2 = document.createElement("label");
      lbl2.textContent = "Dwell seconds after each write";
      const inp2 = document.createElement("input");
      inp2.type = "number";
      inp2.step = "0.1";
      inp2.value = "0.2";
      box.appendChild(lbl2);
      box.appendChild(inp2);
      const lblT = document.createElement("label");
      lblT.textContent = "Technician";
      const inpT = document.createElement("input");
      inpT.dataset.role = "mod-tech";
      inpT.placeholder = "defaults to shared name";
      box.appendChild(lblT);
      box.appendChild(inpT);
      const lblN = document.createElement("label");
      lblN.textContent = "Note";
      const inpN = document.createElement("input");
      inpN.dataset.role = "mod-note";
      box.appendChild(lblN);
      box.appendChild(inpN);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Run modulation sweep";
      btn.addEventListener("click", async () => {{
        const perc = inp1.value.trim();
        const tech = inpT.value.trim() || document.getElementById("commonTech").value.trim();
        if (!perc || !tech) {{
          showFlash(document.getElementById("detailFlash"), "Percents and technician required.", true);
          return;
        }}
        try {{
          await apiJson("/api/v1/modulation-sweep", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              controller: c, step_id: sid,
              command_percents: perc,
              dwell_seconds: parseFloat(inp2.value || "0.2"),
              technician_name: tech,
              note: inpN.value.trim(),
            }}),
          }});
          showFlash(document.getElementById("detailFlash"), "Modulation sweep completed.", false);
          await loadSession();
        }} catch (e) {{
          showFlash(document.getElementById("detailFlash"), String(e.message), true);
        }}
      }});
      box.appendChild(btn);
    }} else if (f.id === "airflow_adjust") {{
      const lbl = document.createElement("label");
      lbl.textContent = "Fan / actuator command (0–100 %)";
      const inp = document.createElement("input");
      inp.type = "number";
      inp.step = "0.1";
      inp.dataset.role = "fan-pct";
      box.appendChild(lbl);
      box.appendChild(inp);
      const lblT = document.createElement("label");
      lblT.textContent = "Technician";
      const inpT = document.createElement("input");
      inpT.dataset.role = "air-tech";
      inpT.placeholder = "defaults to shared name";
      box.appendChild(lblT);
      box.appendChild(inpT);
      const lblN = document.createElement("label");
      lblN.textContent = "Note";
      const inpN = document.createElement("input");
      box.appendChild(lblN);
      box.appendChild(inpN);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Write airflow adjustment";
      btn.addEventListener("click", async () => {{
        const pct = parseFloat(inp.value);
        const tech = inpT.value.trim() || document.getElementById("commonTech").value.trim();
        if (!Number.isFinite(pct) || !tech) {{
          showFlash(document.getElementById("detailFlash"), "Valid percent and technician required.", true);
          return;
        }}
        try {{
          await apiJson("/api/v1/airflow-adjust", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              controller: c, step_id: sid,
              fan_command_percent: pct,
              technician_name: tech,
              note: inpN.value.trim(),
            }}),
          }});
          showFlash(document.getElementById("detailFlash"), "Airflow adjust written.", false);
          await loadSession();
        }} catch (e) {{
          showFlash(document.getElementById("detailFlash"), String(e.message), true);
        }}
      }});
      box.appendChild(btn);
    }} else if (f.id === "airflow_closed_loop") {{
      const lbl = document.createElement("label");
      lbl.textContent = "Optional initial fan % (leave blank for profile default)";
      const inp = document.createElement("input");
      inp.type = "number";
      inp.step = "0.1";
      box.appendChild(lbl);
      box.appendChild(inp);
      const lblT = document.createElement("label");
      lblT.textContent = "Technician";
      const inpT = document.createElement("input");
      inpT.placeholder = "defaults to operator";
      box.appendChild(lblT);
      box.appendChild(inpT);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Run closed-loop iterate";
      btn.addEventListener("click", async () => {{
        const raw = inp.value.trim();
        const tech = inpT.value.trim() || "operator";
        const body = {{ controller: c, step_id: sid, technician_name: tech, note: "guided UI" }};
        if (raw) body.initial_fan_command_percent = parseFloat(raw);
        try {{
          await apiJson("/api/v1/airflow-closed-loop", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify(body),
          }});
          showFlash(document.getElementById("detailFlash"), "Closed-loop iteration completed.", false);
          await loadSession();
        }} catch (e) {{
          showFlash(document.getElementById("detailFlash"), String(e.message), true);
        }}
      }});
      box.appendChild(btn);
    }} else if (f.id === "manual_airflow") {{
      const opts = f.profile && f.profile.branch_options ? f.profile.branch_options : [];
      const lblB = document.createElement("label");
      lblB.textContent = "Branch";
      const selB = document.createElement("select");
      for (const o of opts) {{
        const op = document.createElement("option");
        op.value = o.branch_id;
        op.textContent = o.branch_id + (o.design_flow_L_s != null ? " (design " + o.design_flow_L_s + " L/s)" : "");
        selB.appendChild(op);
      }}
      if (!opts.length) {{
        const op = document.createElement("option");
        op.value = "";
        op.textContent = "(no branches in profile)";
        selB.appendChild(op);
      }}
      box.appendChild(lblB);
      box.appendChild(selB);
      const lblF = document.createElement("label");
      lblF.textContent = "Measured flow (L/s)";
      const inpF = document.createElement("input");
      inpF.type = "number";
      inpF.step = "any";
      box.appendChild(lblF);
      box.appendChild(inpF);
      const lblTool = document.createElement("label");
      lblTool.textContent = "Measurement tool";
      const inpTool = document.createElement("input");
      inpTool.placeholder = "e.g. balometer";
      box.appendChild(lblTool);
      box.appendChild(inpTool);
      const lblT = document.createElement("label");
      lblT.textContent = "Technician";
      const inpT = document.createElement("input");
      box.appendChild(lblT);
      box.appendChild(inpT);
      const lblN = document.createElement("label");
      lblN.textContent = "Note";
      const inpN = document.createElement("input");
      box.appendChild(lblN);
      box.appendChild(inpN);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Record manual airflow";
      btn.addEventListener("click", async () => {{
        const bid = selB.value.trim();
        const tech = inpT.value.trim() || document.getElementById("commonTech").value.trim();
        const flow = parseFloat(inpF.value);
        const tool = inpTool.value.trim();
        if (!bid || !tech || !Number.isFinite(flow) || !tool) {{
          showFlash(document.getElementById("detailFlash"), "Branch, measured L/s, tool, and technician required.", true);
          return;
        }}
        try {{
          await apiJson("/api/v1/manual-airflow", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              controller: c, step_id: sid,
              branch_id: bid,
              measured_flow_L_s: flow,
              measurement_tool: tool,
              technician_name: tech,
              note: inpN.value.trim(),
            }}),
          }});
          showFlash(document.getElementById("detailFlash"), "Manual airflow recorded.", false);
          await loadSession();
          await loadGuidance();
        }} catch (e) {{
          showFlash(document.getElementById("detailFlash"), String(e.message), true);
        }}
      }});
      box.appendChild(btn);
    }} else if (f.id === "valve_prompt") {{
      const pid = (f.profile && f.profile.prompt_id) || "";
      const sm = document.createElement("div");
      sm.className = "small";
      sm.textContent = "Prompt ID: " + pid;
      box.appendChild(sm);
      if (f.profile && f.profile.prompt_text) {{
        const q = document.createElement("div");
        q.className = "small";
        q.textContent = String(f.profile.prompt_text);
        box.appendChild(q);
      }}
      const lblT = document.createElement("label");
      lblT.textContent = "Technician";
      const inpT = document.createElement("input");
      box.appendChild(lblT);
      box.appendChild(inpT);
      const lblN = document.createElement("label");
      lblN.textContent = "Note";
      const inpN = document.createElement("input");
      box.appendChild(lblN);
      box.appendChild(inpN);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Run valve / prompt confirm";
      btn.addEventListener("click", async () => {{
        const tech = inpT.value.trim() || document.getElementById("commonTech").value.trim();
        if (!pid || !tech) {{
          showFlash(document.getElementById("detailFlash"), "Technician required.", true);
          return;
        }}
        try {{
          await apiJson("/api/v1/confirm-prompt", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              controller: c, step_id: sid,
              prompt_id: pid,
              technician_name: tech,
              note: inpN.value.trim(),
            }}),
          }});
          showFlash(document.getElementById("detailFlash"), "Prompt confirmation recorded.", false);
          await loadSession();
        }} catch (e) {{
          showFlash(document.getElementById("detailFlash"), String(e.message), true);
        }}
      }});
      box.appendChild(btn);
    }}
    host.appendChild(box);
  }}
}}

function selectStep(sid) {{
  selectedStepId = sid;
  for (const li of document.querySelectorAll("#stepList li")) {{
    li.classList.toggle("active", li.dataset.sid === sid);
  }}
  if (!guidance) return;
  const row = (guidance.guidance.steps || []).find(s => s.step_id === sid);
  document.getElementById("focusTitle").textContent = row
    ? `${{row.step_id}} — ${{row.label || ""}}`
    : sid;
  document.getElementById("recSid").value = sid || "";
  const bf = document.getElementById("detailFlash");
  bf.style.display = "none";
  const br = row && row.blocked_reasons && row.blocked_reasons.length;
  const bl = document.getElementById("blockers");
  const ul = document.getElementById("blockerList");
  ul.innerHTML = "";
  if (br) {{
    bl.style.display = "block";
    for (const r of row.blocked_reasons) {{
      const li = document.createElement("li");
      li.textContent = r;
      ul.appendChild(li);
    }}
  }} else {{
    bl.style.display = "none";
  }}
  const cmds = document.getElementById("cmdList");
  cmds.innerHTML = "";
  const list = (row && row.suggested_cli_commands) || [];
  if (!list.length) {{
    const li = document.createElement("li");
    li.innerHTML = "<code>record-step …</code>";
    cmds.appendChild(li);
  }} else {{
    for (const line of list) {{
      const li = document.createElement("li");
      const code = document.createElement("code");
      code.textContent = line;
      li.appendChild(code);
      cmds.appendChild(li);
    }}
  }}
  document.getElementById("cmdRaw").textContent = list.length ? list.join("\\n") : "";
  const c = document.getElementById("selCtl").value;
  renderActionForms(c, sid);
  updateGuidedUrl();
}}

function updateGuidedUrl() {{
  const c = document.getElementById("selCtl").value;
  const sid = selectedStepId || document.getElementById("recSid").value.trim();
  try {{
    const u = new URL(window.location.href);
    if (c) u.searchParams.set("controller", c);
    else u.searchParams.delete("controller");
    if (sid) u.searchParams.set("step", sid);
    else u.searchParams.delete("step");
    history.replaceState(null, "", u.pathname + u.search);
  }} catch (e) {{}}
}}

document.getElementById("btnJumpNext").addEventListener("click", () => {{
  const g = guidance && guidance.guidance;
  const next = g && g.next_open_step;
  if (next && next.step_id) {{
    selectStep(next.step_id);
    for (const li of document.querySelectorAll("#stepList li")) {{
      if (li.dataset.sid === next.step_id) {{
        li.scrollIntoView({{ block: "nearest", behavior: "smooth" }});
        break;
      }}
    }}
  }} else {{
    showFlash(document.getElementById("detailFlash"), "No open step for this controller.", true);
  }}
}});

document.getElementById("btnReload").addEventListener("click", loadControllers);
document.getElementById("selCtl").addEventListener("change", () => {{ loadGuidance(); }});

document.getElementById("btnSess").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const key = document.getElementById("sessKey").value.trim();
  const val = document.getElementById("sessVal").value;
  const tech = document.getElementById("sessTech").value.trim();
  const note = document.getElementById("sessNote").value.trim();
  const techUse = tech || document.getElementById("commonTech").value.trim();
  if (!key || !techUse) {{
    showFlash(document.getElementById("detailFlash"), "Session key and technician (or shared name) are required.", true);
    return;
  }}
  try {{
    await apiJson("/api/v1/set-session", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, key, value: val, technician_name: techUse, note }}),
    }});
    showFlash(document.getElementById("detailFlash"), "Session value saved.", false);
    await loadSession();
    await loadGuidance();
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

document.getElementById("btnRecord").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const step_id = document.getElementById("recSid").value.trim();
  const status = document.getElementById("recStatus").value;
  const technician_name = document.getElementById("recTech").value.trim();
  const note = document.getElementById("recNote").value.trim();
  const techRec = technician_name || document.getElementById("commonTech").value.trim();
  if (!step_id || !techRec) {{
    showFlash(document.getElementById("detailFlash"), "Step ID and technician (or shared name) are required.", true);
    return;
  }}
  try {{
    await apiJson("/api/v1/record-step", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, step_id, status, technician_name: techRec, note }}),
    }});
    showFlash(document.getElementById("detailFlash"), "Step recorded.", false);
    await loadGuidance();
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

document.getElementById("btnCheckout").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  try {{
    const j = await apiJson("/api/v1/bacnet-point-checkout?controller=" + encodeURIComponent(c), {{
      method: "POST",
    }});
    const ok = j.all_read_ok ? "Point checkout OK." : "Point checkout had failures (see CLI output).";
    showFlash(document.getElementById("detailFlash"), ok, !j.all_read_ok);
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

document.getElementById("btnQrRead").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const object_id = document.getElementById("qrOid").value.trim();
  const property = (document.getElementById("qrProp").value.trim() || "presentValue");
  const technician_name = document.getElementById("commonTech").value.trim();
  if (!c || !object_id) {{
    showFlash(document.getElementById("detailFlash"), "Controller and object id required.", true);
    return;
  }}
  try {{
    const j = await apiJson("/api/v1/bacnet-quick-read", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, object_id, property }}),
    }});
    showFlash(document.getElementById("detailFlash"), formatReadSummary(j), (j.status || "") !== "read_ok");
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

document.getElementById("btnQrBatch").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const raw = document.getElementById("qrbReads").value || "";
  const mode = document.getElementById("qrbMode").value || "multiple";
  const reads = raw.split(/\\r?\\n/).map(s => s.trim()).filter(Boolean);
  if (!c || reads.length === 0) {{
    showFlash(document.getElementById("detailFlash"), "Controller and at least one read line required.", true);
    return;
  }}
  try {{
    const j = await apiJson("/api/v1/bacnet-quick-read-batch", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, reads, mode }}),
    }});
    const msg = (j.all_read_ok ? "" : "Some reads failed. ") + formatBatchSummary(j);
    showFlash(document.getElementById("detailFlash"), msg, !j.all_read_ok);
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

document.getElementById("btnQwWrite").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const object_id = document.getElementById("qwOid").value.trim();
  const raw = document.getElementById("qwVal").value.trim();
  const technician_name = document.getElementById("commonTech").value.trim();
  const execute = document.getElementById("qwExec").checked;
  if (!c || !object_id || !raw) {{
    showFlash(document.getElementById("detailFlash"), "Controller, object id, and value required.", true);
    return;
  }}
  if (!technician_name) {{
    showFlash(document.getElementById("detailFlash"), "Set shared technician name first.", true);
    return;
  }}
  try {{
    const j = await apiJson("/api/v1/bacnet-quick-write", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, object_id, value: raw, technician_name, note: "guided quick write", execute }}),
    }});
    const st = j.status || "";
    const line = execute
      ? ("Write " + st + ": " + object_id + "=" + raw)
      : ("Dry-run " + st + ": " + object_id + "=" + raw);
    showFlash(document.getElementById("detailFlash"), line, execute && st !== "write_ok");
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

document.getElementById("btnTacho").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const step_id = document.getElementById("recSid").value.trim();
  const technician_name = document.getElementById("tachoTech").value.trim() || document.getElementById("commonTech").value.trim();
  const note = document.getElementById("tachoNote").value.trim();
  if (!step_id || !technician_name) {{
    showFlash(document.getElementById("detailFlash"), "Select a step and enter technician (or shared name).", true);
    return;
  }}
  try {{
    await apiJson("/api/v1/tachometer-confirm", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, step_id, technician_name, note }}),
    }});
    showFlash(document.getElementById("detailFlash"), "Tachometer reference confirmed.", false);
    await loadSession();
    await loadGuidance();
  }} catch (e) {{
    showFlash(document.getElementById("detailFlash"), String(e.message), true);
  }}
}});

loadControllers().catch(e => showFlash(document.getElementById("ctlFlash"), String(e.message), true));
</script>
</body></html>"""
    return body.encode("utf-8")


def _dashboard_page(run_dir: Path) -> bytes:
    rd = json.dumps(str(run_dir.resolve()))
    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Commissioning dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root {{
  --bg: #0f1419; --panel: #151c27; --surface: #0d1218; --text: #e8eef5; --muted: #8b9cb3;
  --accent: #3d8bfd; --accent-dim: #2a6bc4; --ok: #2fb573; --err: #f47174; --border: #2d3a4d;
  --radius: 8px; --radius-sm: 6px; --shadow: 0 2px 12px rgba(0,0,0,0.25);
}}
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0;
  background: var(--bg); color: var(--text); line-height: 1.45; min-height: 100vh; }}
header {{
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;
  background: linear-gradient(180deg, #151c27 0%, var(--bg) 100%);
}}
header h1 {{ font-size: 1.1rem; margin: 0; font-weight: 650; }}
header .meta {{ color: var(--muted); font-size: 0.85rem; }}
header a {{ color: var(--accent); text-decoration: none; }}
header a:hover {{ text-decoration: underline; }}
.toolbar {{
  padding: 0.85rem 1.25rem; border-bottom: 1px solid var(--border);
  background: var(--panel); display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end;
}}
.toolbar label {{ font-size: 0.78rem; color: var(--muted); display: block; margin-bottom: 0.2rem; }}
.toolbar input {{ padding: 0.45rem 0.55rem; border-radius: var(--radius-sm); border: 1px solid var(--border);
  background: var(--surface); color: var(--text); min-width: 12rem; }}
.toolbar button {{ margin: 0; padding: 0.45rem 0.9rem; border-radius: var(--radius-sm); border: none;
  background: var(--accent); color: #fff; font-weight: 600; cursor: pointer; }}
.toolbar button:hover {{ background: var(--accent-dim); }}
#globalFlash {{ margin: 0.75rem 1.25rem; padding: 0.6rem 0.85rem; border-radius: var(--radius-sm); display: none;
  font-size: 0.88rem; border-left: 3px solid transparent; }}
#globalFlash.err {{ background: #3a1a1c; color: #ffb4b6; border-left-color: var(--err); }}
#globalFlash.ok {{ background: #1a2e24; color: #9ee5c0; border-left-color: var(--ok); }}
.dash-wrap {{ padding: 1rem 1.25rem 2rem; }}
.dash-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 0.85rem;
}}
.dash-card {{
  border: 1px solid var(--border); border-radius: var(--radius); padding: 0.85rem 1rem;
  background: var(--surface); box-shadow: var(--shadow);
}}
.dash-card h2 {{ margin: 0 0 0.25rem; font-size: 1rem; font-weight: 650; }}
.dash-card .sub {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 0.5rem; line-height: 1.35; }}
.dash-card label {{ display: block; font-size: 0.72rem; color: var(--muted); margin-top: 0.5rem; font-weight: 500; }}
.dash-card input, .dash-card textarea, .dash-card select {{
  width: 100%; margin-top: 0.2rem; padding: 0.45rem 0.55rem; font-size: 0.88rem;
  border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: var(--text);
  transition: border-color 0.12s ease, box-shadow 0.12s ease;
}}
.dash-card input:focus, .dash-card textarea:focus, .dash-card select:focus {{
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(61, 139, 253, 0.22);
}}
.dash-card textarea {{ min-height: 3.2rem; font-family: ui-monospace, monospace; font-size: 0.78rem; }}
.dash-card .row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.45rem; }}
.dash-card button {{
  margin-top: 0.45rem; padding: 0.45rem 0.85rem; border: none; border-radius: var(--radius-sm);
  font-size: 0.85rem; font-weight: 600; cursor: pointer; background: #3a4a5e; color: var(--text);
  min-height: 2.35rem;
}}
.dash-card button.primary {{ background: var(--accent); color: #fff; }}
.dash-card button:hover {{ filter: brightness(1.08); }}
.dash-guided-link {{
  display: inline-block; margin-top: 0.45rem; font-size: 0.82rem; font-weight: 600;
  color: var(--accent); text-decoration: none;
}}
.dash-guided-link:hover {{ text-decoration: underline; }}
.dash-card .probe-out {{ font-size: 0.74rem; color: var(--muted); margin-top: 0.35rem; font-family: ui-monospace, monospace; }}
.dash-card .flash {{ margin-top: 0.45rem; padding: 0.45rem 0.55rem; border-radius: var(--radius-sm); font-size: 0.78rem; display: none;
  border-left: 3px solid transparent; word-break: break-word; }}
.dash-card .flash.err {{ background: #3a1a1c; color: #ffb4b6; border-left-color: var(--err); }}
.dash-card .flash.ok {{ background: #1a2e24; color: #9ee5c0; border-left-color: var(--ok); }}
.chk {{ display: flex; align-items: center; gap: 0.35rem; margin-top: 0.35rem; font-size: 0.78rem; color: var(--muted); }}
.chk input {{ width: auto; accent-color: var(--accent); }}
.empty {{ color: var(--muted); padding: 1rem 0; }}
</style></head>
<body>
<header>
  <h1>Commissioning dashboard</h1>
  <span class="meta">Run dir: <code id="runDirDisp"></code></span>
  <span class="meta"><a href="/guided">Guided</a> · <a href="/">Advanced CLI</a></span>
</header>
<div class="toolbar">
  <div>
    <label for="dashTech">Technician (writes)</label>
    <input id="dashTech" placeholder="Required for BACnet writes" autocomplete="name"/>
  </div>
  <div>
    <button type="button" id="btnDashReload">Reload controllers</button>
  </div>
</div>
<div id="globalFlash"></div>
<div class="dash-wrap">
  <p class="sub" style="color:var(--muted);font-size:0.82rem;margin:0 0 0.75rem">
    One card per controller from <code>runtime-job.json</code>. Reads and writes use the same profile allowlists as the CLI.
    Use <strong>Sequential</strong> batch mode if the device rejects ReadPropertyMultiple.
  </p>
  <div class="dash-grid" id="dashGrid"></div>
</div>
<script>
const RUN_DIR = {rd};
const TECH_KEY = "bacnet_op_technician_name";
document.getElementById("runDirDisp").textContent = RUN_DIR;

function loadDashTech() {{
  try {{
    const v = sessionStorage.getItem(TECH_KEY);
    const el = document.getElementById("dashTech");
    if (v && el && !el.value.trim()) el.value = v;
  }} catch (e) {{}}
}}
function persistDashTech() {{
  try {{
    const v = document.getElementById("dashTech").value.trim();
    if (v) sessionStorage.setItem(TECH_KEY, v);
    else sessionStorage.removeItem(TECH_KEY);
  }} catch (e) {{}}
}}
document.getElementById("dashTech").addEventListener("input", persistDashTech);
document.getElementById("dashTech").addEventListener("change", persistDashTech);
loadDashTech();

function showGlobal(msg, isErr) {{
  const el = document.getElementById("globalFlash");
  el.style.display = "block";
  el.className = isErr ? "err" : "ok";
  el.textContent = msg;
}}

function cardFlash(card, msg, isErr) {{
  const el = card.querySelector(".dash-local-flash");
  if (!el) return;
  el.style.display = "block";
  el.className = "flash dash-local-flash " + (isErr ? "err" : "ok");
  el.textContent = msg;
}}

async function apiJson(path, opts) {{
  const r = await fetch(path, Object.assign({{ headers: {{ "Accept": "application/json" }} }}, opts || {{}}));
  const text = await r.text();
  let data = null;
  try {{ data = JSON.parse(text); }} catch (e) {{}}
  if (!r.ok) {{
    const msg = (data && data.error) ? data.error : text.slice(0, 400);
    throw new Error(msg || "request failed");
  }}
  return data;
}}

function formatReadSummary(j) {{
  const st = j.status || "";
  const vs = (j.read && j.read.value_str != null) ? j.read.value_str : (j.value_str || "");
  return "Read " + st + (vs ? ": " + vs : "");
}}

function formatBatchSummary(j) {{
  const rows = j.reads || [];
  const ok = rows.filter(r => (r.status || "") === "read_ok").length;
  const parts = [];
  for (const r of rows.slice(0, 4)) {{
    const oid = (r.profile_object_id || "").trim();
    const vs = (r.read && r.read.value_str != null) ? r.read.value_str : (r.value_str || "");
    if (oid) parts.push(vs ? (oid + "=" + vs) : oid);
  }}
  const more = rows.length > 4 ? " (+" + (rows.length - 4) + ")" : "";
  return ok + "/" + rows.length + " OK" + (parts.length ? ": " + parts.join(", ") : "") + more;
}}

function buildCard(row) {{
  const lab = row.controller_label;
  const card = document.createElement("div");
  card.className = "dash-card";
  card.dataset.controller = lab;
  const host = row.bacnet_host || "";
  const port = row.bacnet_port || "";
  const inst = row.bacnet_device_instance;
  const sub = document.createElement("div");
  sub.className = "sub";
  sub.textContent = (row.profile_id || "") + " · " + host + ":" + port + " · device " + inst +
    " · " + (row.read_allowlist_count || 0) + " reads / " + (row.write_allowlist_count || 0) + " writes allowlisted";
  const h = document.createElement("h2");
  h.textContent = lab;
  card.appendChild(h);
  card.appendChild(sub);
  const lg = document.createElement("a");
  lg.className = "dash-guided-link";
  lg.href = "/guided?controller=" + encodeURIComponent(lab);
  lg.textContent = "Open in guided →";
  card.appendChild(lg);

  const bProbe = document.createElement("button");
  bProbe.type = "button";
  bProbe.textContent = "Probe B/IP";
  const probeOut = document.createElement("div");
  probeOut.className = "probe-out";
  bProbe.addEventListener("click", async () => {{
    try {{
      const j = await apiJson("/api/v1/dashboard-probe", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ controller: lab }}),
      }});
      const st = (j.probe && j.probe.status) || j.status || "?";
      probeOut.textContent = "probe: " + st;
      cardFlash(card, "Probe " + st, st !== "reachable_verified");
    }} catch (e) {{
      probeOut.textContent = "";
      cardFlash(card, String(e.message), true);
    }}
  }});
  card.appendChild(bProbe);
  card.appendChild(probeOut);

  const lr1 = document.createElement("label");
  lr1.textContent = "Read — object id";
  const inRoid = document.createElement("input");
  inRoid.placeholder = "e.g. ai_sat";
  inRoid.autocomplete = "off";
  const lr2 = document.createElement("label");
  lr2.textContent = "Property";
  const inRprop = document.createElement("input");
  inRprop.value = "presentValue";
  const bRead = document.createElement("button");
  bRead.className = "primary";
  bRead.type = "button";
  bRead.textContent = "Read";
  bRead.addEventListener("click", async () => {{
    const oid = inRoid.value.trim();
    const prop = (inRprop.value || "presentValue").trim();
    if (!oid) {{ cardFlash(card, "Object id required.", true); return; }}
    try {{
      const j = await apiJson("/api/v1/bacnet-quick-read", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ controller: lab, object_id: oid, property: prop }}),
      }});
      cardFlash(card, formatReadSummary(j), (j.status || "") !== "read_ok");
    }} catch (e) {{ cardFlash(card, String(e.message), true); }}
  }});
  card.appendChild(lr1);
  card.appendChild(inRoid);
  card.appendChild(lr2);
  card.appendChild(inRprop);
  card.appendChild(bRead);

  const lb = document.createElement("label");
  lb.textContent = "Read batch — one id per line";
  const ta = document.createElement("textarea");
  ta.placeholder = "ai_sat\\nmsv_test_mode";
  ta.spellcheck = false;
  const lm = document.createElement("label");
  lm.textContent = "Transport";
  const sel = document.createElement("select");
  sel.innerHTML = '<option value="multiple">Multiple (one APDU)</option><option value="sequential">Sequential</option>';
  const bBatch = document.createElement("button");
  bBatch.type = "button";
  bBatch.textContent = "Read batch";
  bBatch.addEventListener("click", async () => {{
    const reads = (ta.value || "").split(/\\r?\\n/).map(s => s.trim()).filter(Boolean);
    if (!reads.length) {{ cardFlash(card, "Enter at least one line.", true); return; }}
    try {{
      const j = await apiJson("/api/v1/bacnet-quick-read-batch", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ controller: lab, reads, mode: sel.value }}),
      }});
      const msg = (j.all_read_ok ? "" : "Some failed. ") + formatBatchSummary(j);
      cardFlash(card, msg, !j.all_read_ok);
    }} catch (e) {{ cardFlash(card, String(e.message), true); }}
  }});
  card.appendChild(lb);
  card.appendChild(ta);
  card.appendChild(lm);
  card.appendChild(sel);
  card.appendChild(bBatch);

  const lw1 = document.createElement("label");
  lw1.textContent = "Write — object id";
  const inWoid = document.createElement("input");
  inWoid.autocomplete = "off";
  const lw2 = document.createElement("label");
  lw2.textContent = "Value";
  const inWval = document.createElement("input");
  inWval.inputMode = "decimal";
  const ex = document.createElement("label");
  ex.className = "chk";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  const sp = document.createElement("span");
  sp.textContent = "Execute on wire";
  ex.appendChild(cb);
  ex.appendChild(sp);
  const bWr = document.createElement("button");
  bWr.className = "primary";
  bWr.type = "button";
  bWr.textContent = "Write";
  bWr.addEventListener("click", async () => {{
    const oid = inWoid.value.trim();
    const raw = inWval.value.trim();
    const tech = document.getElementById("dashTech").value.trim();
    if (!oid || !raw) {{ cardFlash(card, "Object id and value required.", true); return; }}
    if (!tech) {{ cardFlash(card, "Set technician (toolbar) for writes.", true); return; }}
    try {{
      const j = await apiJson("/api/v1/bacnet-quick-write", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          controller: lab, object_id: oid, value: raw, technician_name: tech,
          note: "dashboard manual", execute: cb.checked,
        }}),
      }});
      const st = j.status || "";
      const line = cb.checked ? ("Write " + st + ": " + oid + "=" + raw) : ("Dry-run " + st + ": " + oid + "=" + raw);
      cardFlash(card, line, cb.checked && st !== "write_ok");
    }} catch (e) {{ cardFlash(card, String(e.message), true); }}
  }});
  card.appendChild(lw1);
  card.appendChild(inWoid);
  card.appendChild(lw2);
  card.appendChild(inWval);
  card.appendChild(ex);
  card.appendChild(bWr);

  const fl = document.createElement("div");
  fl.className = "flash dash-local-flash";
  card.appendChild(fl);
  return card;
}}

async function loadDashboard() {{
  const grid = document.getElementById("dashGrid");
  grid.innerHTML = "";
  document.getElementById("globalFlash").style.display = "none";
  try {{
    const j = await apiJson("/api/v1/dashboard-controllers");
    const rows = j.controllers || [];
    if (!rows.length) {{
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "No controllers in runtime job. Run compile-import.";
      grid.appendChild(p);
      return;
    }}
    for (const row of rows) {{
      grid.appendChild(buildCard(row));
    }}
  }} catch (e) {{
    showGlobal(String(e.message), true);
  }}
}}

document.getElementById("btnDashReload").addEventListener("click", loadDashboard);
loadDashboard();
</script>
</body></html>"""
    return body.encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    run_dir: Path = ROOT

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def _send_json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any] | None:
        ln = int(self.headers.get("Content-Length", "0"))
        if ln <= 0 or ln > 1_000_000:
            return {}
        raw = self.rfile.read(ln).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _run_app_argv(self, argv: list[str], *, timeout: int = 600) -> tuple[int, str, str]:
        """Run runtime CLI; argv must not include python or script path."""
        if not argv or argv[0] not in _GUIDED_API_COMMANDS:
            raise ValueError("invalid command")
        full = [
            sys.executable,
            str(RUNTIME_CLI),
            *argv,
            "--run-dir",
            str(self.run_dir.resolve()),
        ]
        proc = subprocess.run(
            full,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _parse_stdout_json(self, stdout: str) -> Any:
        text = stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/":
            if self.path != "/" and not self.path.startswith("/?"):
                self.send_error(404)
                return
            data = _page(self.run_dir)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/guided":
            data = _guided_page(self.run_dir)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/dashboard":
            data = _dashboard_page(self.run_dir)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/v1/dashboard-controllers":
            job = _load_json(_runtime_job_path(self.run_dir))
            if job is None:
                self._send_json(
                    400,
                    {"error": "runtime-job.json missing; run compile-import for this run-dir"},
                )
                return
            self._send_json(
                200,
                {"controllers": _dashboard_controller_summaries(job)},
            )
            return
        if path == "/api/v1/list-flows":
            code, out, err = self._run_app_argv(["list-flows"])
            if code != 0:
                self._send_json(
                    502,
                    {"error": "list-flows failed", "stderr": err[-4000:], "stdout": out[-4000:]},
                )
                return
            data = self._parse_stdout_json(out)
            if not isinstance(data, dict):
                self._send_json(502, {"error": "invalid JSON from list-flows", "raw": out[:2000]})
                return
            self._send_json(200, data)
            return
        qs = urllib.parse.urlparse(self.path).query
        q = urllib.parse.parse_qs(qs)
        if path == "/api/v1/guidance":
            ctl = (q.get("controller") or [""])[0].strip()
            if not ctl:
                self._send_json(400, {"error": "missing controller query parameter"})
                return
            code, out, err = self._run_app_argv(
                ["commissioning-guided-next", "--controller-label", ctl]
            )
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "commissioning-guided-next failed",
                        "stderr": err[-4000:],
                        "stdout": out[-4000:],
                    },
                )
                return
            data = self._parse_stdout_json(out)
            if not isinstance(data, dict):
                self._send_json(502, {"error": "invalid JSON from guided-next", "raw": out[:2000]})
                return
            self._send_json(200, data)
            return
        if path == "/api/v1/session":
            ctl = (q.get("controller") or [""])[0].strip()
            if not ctl:
                self._send_json(400, {"error": "missing controller query parameter"})
                return
            if not _session_state_path(self.run_dir, ctl).is_file():
                self._send_json(200, {"session_keys": [], "session": None})
                return
            code, out, err = self._run_app_argv(["show-session", "--controller-label", ctl])
            if code != 0:
                self._send_json(
                    400,
                    {"error": "show-session failed", "stderr": err[-4000:], "stdout": out[-4000:]},
                )
                return
            data = self._parse_stdout_json(out)
            if not isinstance(data, dict):
                self._send_json(502, {"error": "invalid JSON from show-session", "raw": out[:2000]})
                return
            keys = sorted((data.get("values") or {}).keys()) if isinstance(data.get("values"), dict) else []
            self._send_json(200, {"session_keys": keys, "session": data})
            return
        if path == "/api/v1/step-hints":
            ctl = (q.get("controller") or [""])[0].strip()
            sid = (q.get("step_id") or [""])[0].strip()
            if not ctl or not sid:
                self._send_json(400, {"error": "missing controller or step_id query parameter"})
                return
            hints = _build_step_hints(run_dir=self.run_dir, controller_label=ctl, step_id=sid)
            if hints.get("error") == "step_id required":
                self._send_json(400, hints)
                return
            if "error" in hints and hints["error"] in {"flow_state_not_found", "step_not_found"}:
                self._send_json(404, hints)
                return
            self._send_json(200, hints)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/cli":
            self._post_cli()
            return
        if path == "/api/v1/dashboard-probe":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            if not ctl or len(ctl) > 128:
                self._send_json(400, {"error": "controller required"})
                return
            argv = ["probe-bip", "--controller-label", ctl]
            ts = body.get("timeout_seconds")
            if ts is not None and str(ts).strip() != "":
                argv.extend(["--timeout-seconds", str(ts)])
            rt = body.get("retries")
            if rt is not None and str(rt).strip() != "":
                try:
                    argv.extend(["--retries", str(int(rt))])
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "invalid retries"})
                    return
            code, out, err = self._run_app_argv(argv, timeout=120)
            data = self._parse_stdout_json(out)
            if code != 0 or not isinstance(data, dict):
                self._send_json(
                    400,
                    {
                        "error": "probe-bip failed",
                        "stderr": err[-4000:],
                        "stdout": out[-4000:],
                        "parsed": data,
                    },
                )
                return
            self._send_json(200, {"controller_label": ctl, "probe": data})
            return
        if path == "/api/v1/set-session":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            key = str(body.get("key", "")).strip()
            val = str(body.get("value", ""))
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "")).strip()
            if not ctl or not key or not tech:
                self._send_json(400, {"error": "controller, key, and technician_name required"})
                return
            code, out, err = self._run_app_argv(
                [
                    "set-session-value",
                    "--controller-label",
                    ctl,
                    "--key",
                    key,
                    "--value",
                    val,
                    "--technician-name",
                    tech,
                    "--note",
                    note,
                ]
            )
            if code != 0:
                self._send_json(
                    400,
                    {"error": "set-session-value failed", "stderr": err[-4000:], "stdout": out[-4000:]},
                )
                return
            self._send_json(200, {"ok": True, "stdout": out.strip()})
            return
        if path == "/api/v1/record-step":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            status = str(body.get("status", "")).strip()
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "")).strip()
            if not ctl or not sid or not status or not tech:
                self._send_json(400, {"error": "controller, step_id, status, technician_name required"})
                return
            code, out, err = self._run_app_argv(
                [
                    "record-step",
                    "--controller-label",
                    ctl,
                    "--step-id",
                    sid,
                    "--status",
                    status,
                    "--technician-name",
                    tech,
                    "--note",
                    note,
                ]
            )
            if code != 0:
                self._send_json(
                    400,
                    {"error": "record-step failed", "stderr": err[-4000:], "stdout": out[-4000:]},
                )
                return
            self._send_json(200, {"ok": True, "stdout": out.strip()})
            return
        if path == "/api/v1/bacnet-point-checkout":
            qs = urllib.parse.urlparse(self.path).query
            q = urllib.parse.parse_qs(qs)
            ctl = (q.get("controller") or [""])[0].strip()
            if not ctl:
                body = self._read_json_body()
                if body is None:
                    self._send_json(400, {"error": "invalid JSON body"})
                    return
                if isinstance(body, dict):
                    ctl = str(body.get("controller", "")).strip()
            if not ctl:
                self._send_json(400, {"error": "missing controller"})
                return
            code, out, err = self._run_app_argv(
                ["bacnet-point-checkout", "--controller-label", ctl],
                timeout=900,
            )
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "bacnet-point-checkout failed",
                        "stderr": err[-4000:],
                        "stdout": out[-4000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "raw_stdout": out[:4000]})
            return
        if path == "/api/v1/modulation-sweep":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            perc = str(body.get("command_percents", "")).strip()
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "") or "")
            if not ctl or not sid or not perc or not tech:
                self._send_json(400, {"error": "controller, step_id, command_percents, technician_name required"})
                return
            parts = [p.strip() for p in perc.split(",") if p.strip()]
            if not parts or len(parts) > 32:
                self._send_json(400, {"error": "command_percents: 1–32 comma-separated values"})
                return
            for p in parts:
                try:
                    v = float(p)
                except ValueError:
                    self._send_json(400, {"error": f"invalid percent token: {p!r}"})
                    return
                if not (0.0 <= v <= 100.0):
                    self._send_json(400, {"error": f"percent out of 0–100: {p!r}"})
                    return
            try:
                dwell = float(body.get("dwell_seconds", 0.2))
            except (TypeError, ValueError):
                self._send_json(400, {"error": "dwell_seconds must be a number"})
                return
            if not (0.0 < dwell <= 120.0):
                self._send_json(400, {"error": "dwell_seconds must be in (0, 120]"})
                return
            argv = [
                "bacnet-modulation-sweep",
                "--controller-label",
                ctl,
                "--step-id",
                sid,
                "--command-percents",
                perc,
                "--dwell-seconds",
                str(dwell),
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            rr = str(body.get("report_ref", "") or "").strip()
            if rr:
                argv.extend(["--report-ref", rr])
            _argv_append_optional_bacnet(argv, body)
            code, out, err = self._run_app_argv(argv, timeout=1800)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "bacnet-modulation-sweep failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/airflow-adjust":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "") or "")
            try:
                pct = float(body.get("fan_command_percent"))
            except (TypeError, ValueError, KeyError):
                self._send_json(400, {"error": "fan_command_percent must be a number"})
                return
            if not (0.0 <= pct <= 100.0):
                self._send_json(400, {"error": "fan_command_percent must be 0–100"})
                return
            if not ctl or not sid or not tech:
                self._send_json(400, {"error": "controller, step_id, technician_name required"})
                return
            argv = [
                "commissioning-airflow-adjust-write",
                "--controller-label",
                ctl,
                "--step-id",
                sid,
                "--fan-command-percent",
                str(pct),
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            _argv_append_optional_bacnet(argv, body)
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "commissioning-airflow-adjust-write failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/airflow-closed-loop":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            tech = str(body.get("technician_name", "operator") or "operator").strip()
            note = str(body.get("note", "") or "")
            if not ctl or not sid:
                self._send_json(400, {"error": "controller and step_id required"})
                return
            argv = [
                "commissioning-airflow-closed-loop-iterate",
                "--controller-label",
                ctl,
                "--step-id",
                sid,
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            if body.get("initial_fan_command_percent") is not None and str(
                body.get("initial_fan_command_percent")
            ).strip() != "":
                try:
                    ip = float(body["initial_fan_command_percent"])
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "initial_fan_command_percent must be a number"})
                    return
                argv.extend(["--initial-fan-command-percent", str(ip)])
            _argv_append_optional_bacnet(argv, body)
            code, out, err = self._run_app_argv(argv, timeout=1800)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "commissioning-airflow-closed-loop-iterate failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/manual-airflow":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            bid = str(body.get("branch_id", "")).strip()
            tool = str(body.get("measurement_tool", "")).strip()
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "") or "")
            flow_raw = body.get("measured_flow_L_s")
            if not ctl or not sid or not bid or not tool or not tech:
                self._send_json(
                    400,
                    {"error": "controller, step_id, branch_id, measurement_tool, technician_name required"},
                )
                return
            try:
                flow_ls = float(str(flow_raw).strip())
            except (TypeError, ValueError):
                self._send_json(400, {"error": "measured_flow_L_s must be a number"})
                return
            if flow_ls <= 0.0:
                self._send_json(400, {"error": "measured_flow_L_s must be > 0"})
                return
            if len(bid) > 128 or len(tool) > 128:
                self._send_json(400, {"error": "branch_id or measurement_tool too long"})
                return
            argv = [
                "commissioning-record-manual-airflow",
                "--controller-label",
                ctl,
                "--step-id",
                sid,
                "--branch-id",
                bid,
                "--measured-flow-L-s",
                str(flow_ls),
                "--measurement-tool",
                tool,
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            _argv_append_optional_bacnet(argv, body)
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "commissioning-record-manual-airflow failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/confirm-prompt":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            pid = str(body.get("prompt_id", "")).strip()
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "") or "")
            if not ctl or not sid or not pid or not tech:
                self._send_json(400, {"error": "controller, step_id, prompt_id, technician_name required"})
                return
            if len(pid) > 128:
                self._send_json(400, {"error": "prompt_id too long"})
                return
            hints = _build_step_hints(run_dir=self.run_dir, controller_label=ctl, step_id=sid)
            allowed = {
                str((f.get("profile") or {}).get("prompt_id", "")).strip()
                for f in (hints.get("forms") or [])
                if f.get("id") == "valve_prompt"
            }
            allowed.discard("")
            if allowed and pid not in allowed:
                self._send_json(400, {"error": f"prompt_id not in step profile: {sorted(allowed)}"})
                return
            argv = [
                "commissioning-confirm-prompt",
                "--controller-label",
                ctl,
                "--step-id",
                sid,
                "--prompt-id",
                pid,
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            _argv_append_optional_bacnet(argv, body)
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "commissioning-confirm-prompt failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/tachometer-confirm":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            sid = str(body.get("step_id", "")).strip()
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "") or "")
            if not ctl or not sid or not tech:
                self._send_json(400, {"error": "controller, step_id, technician_name required"})
                return
            hints = _build_step_hints(run_dir=self.run_dir, controller_label=ctl, step_id=sid)
            if not any(f.get("id") == "tachometer_confirm" for f in (hints.get("forms") or [])):
                self._send_json(
                    400,
                    {"error": "this step has no operator_confirm_tachometer_reference action"},
                )
                return
            argv = [
                "commissioning-confirm-tachometer-reference",
                "--controller-label",
                ctl,
                "--step-id",
                sid,
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            _argv_append_optional_bacnet(argv, body)
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "commissioning-confirm-tachometer-reference failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/bacnet-quick-read":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            oid = str(body.get("object_id", "")).strip()
            prop = str(body.get("property", "presentValue") or "presentValue").strip() or "presentValue"
            if not ctl or not oid:
                self._send_json(400, {"error": "controller and object_id required"})
                return
            if len(oid) > 128 or len(prop) > 64:
                self._send_json(400, {"error": "object_id or property too long"})
                return
            argv = [
                "bacnet-read",
                "--controller-label",
                ctl,
                "--object-id",
                oid,
                "--property",
                prop,
            ]
            _argv_append_optional_bacnet(argv, body)
            if body.get("timeout_seconds") is not None and str(body.get("timeout_seconds")).strip() != "":
                argv.extend(["--timeout-seconds", str(body["timeout_seconds"])])
            if body.get("retries") is not None and str(body.get("retries")).strip() != "":
                argv.extend(["--retries", str(int(body["retries"]))])
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "bacnet-read failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": False, "raw_stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/bacnet-quick-read-batch":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            reads_raw = body.get("reads")
            mode = str(body.get("mode", "multiple") or "multiple").strip().lower()
            if not ctl:
                self._send_json(400, {"error": "controller required"})
                return
            if mode not in {"multiple", "sequential"}:
                self._send_json(400, {"error": "mode must be multiple or sequential"})
                return
            if not isinstance(reads_raw, list) or not reads_raw:
                self._send_json(400, {"error": "reads must be a non-empty JSON array of strings"})
                return
            specs: list[str] = []
            for item in reads_raw:
                s = str(item).strip()
                if not s:
                    continue
                if len(s) > 160:
                    self._send_json(400, {"error": "read spec too long"})
                    return
                specs.append(s)
            if len(specs) > 32:
                self._send_json(400, {"error": "too many read specs (max 32)"})
                return
            if not specs:
                self._send_json(400, {"error": "no non-empty read specs"})
                return
            argv = ["bacnet-read-batch", "--controller-label", ctl, "--mode", mode]
            for spec in specs:
                argv.extend(["--read", spec])
            _argv_append_optional_bacnet(argv, body)
            if body.get("timeout_seconds") is not None and str(body.get("timeout_seconds")).strip() != "":
                argv.extend(["--timeout-seconds", str(body["timeout_seconds"])])
            if body.get("retries") is not None and str(body.get("retries")).strip() != "":
                argv.extend(["--retries", str(int(body["retries"]))])
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "bacnet-read-batch failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": False, "raw_stdout": out.strip()[:8000]})
            return
        if path == "/api/v1/bacnet-quick-write":
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return
            ctl = str(body.get("controller", "")).strip()
            oid = str(body.get("object_id", "")).strip()
            raw_val = body.get("value")
            tech = str(body.get("technician_name", "")).strip()
            note = str(body.get("note", "") or "")
            execute = bool(body.get("execute"))
            if not ctl or not oid or not tech:
                self._send_json(400, {"error": "controller, object_id, technician_name required"})
                return
            if len(oid) > 128:
                self._send_json(400, {"error": "object_id too long"})
                return
            try:
                v = float(str(raw_val).strip())
            except (TypeError, ValueError, AttributeError):
                self._send_json(400, {"error": "value must be a number"})
                return
            try:
                iv = int(round(v))
            except (ValueError, OverflowError):
                self._send_json(400, {"error": "value out of range"})
                return
            argv = [
                "dry-run-bacnet-write",
                "--controller-label",
                ctl,
                "--object-id",
                oid,
                "--value",
                str(iv),
                "--technician-name",
                tech,
                "--note",
                str(note),
            ]
            _argv_append_optional_bacnet(argv, body)
            if body.get("timeout_seconds") is not None and str(body.get("timeout_seconds")).strip() != "":
                argv.extend(["--timeout-seconds", str(body["timeout_seconds"])])
            if body.get("retries") is not None and str(body.get("retries")).strip() != "":
                argv.extend(["--retries", str(int(body["retries"]))])
            if execute:
                argv.append("--execute")
            code, out, err = self._run_app_argv(argv, timeout=900)
            data = self._parse_stdout_json(out)
            if code != 0:
                self._send_json(
                    400,
                    {
                        "error": "dry-run-bacnet-write failed",
                        "stderr": err[-8000:],
                        "stdout": out[-8000:],
                        "parsed": data,
                    },
                )
                return
            if isinstance(data, dict):
                self._send_json(200, data)
            else:
                self._send_json(200, {"ok": True, "stdout": out.strip()[:8000]})
            return
        self.send_error(404)

    def _post_cli(self) -> None:
        ln = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(ln).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        cmd = (form.get("command") or [""])[0].strip()
        extra_lines = (form.get("extra") or [""])[0].splitlines()
        if not cmd or not cmd.startswith(ALLOWED_PREFIXES):
            self._respond(400, b"invalid command")
            return
        extra_args: list[str] = []
        for line in extra_lines:
            t = line.strip()
            if t:
                extra_args.append(t)
        argv = [
            sys.executable,
            str(RUNTIME_CLI),
            cmd,
            "--run-dir",
            str(self.run_dir.resolve()),
            *extra_args,
        ]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            self._respond(504, b"command timed out (10m)")
            return
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        esc = html.escape(out)
        page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Result</title>
<style>body{{font-family:system-ui;margin:1rem}} pre{{background:#f4f4f4;padding:0.75rem}}</style>
</head><body>
<p>exit_code: {proc.returncode}</p>
<pre>{esc}</pre>
<p><a href="/">Back</a> · <a href="/guided">Guided UI</a> · <a href="/dashboard">Dashboard</a></p>
</body></html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def _respond(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_operator_gui_server(*, run_dir: Path, host: str, port: int) -> None:
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"error: run-dir is not a directory: {run_dir}")
    _Handler.run_dir = run_dir
    httpd = HTTPServer((host, port), _Handler)
    print(
        f"operator_gui_listening=true url=http://{host}:{port}/ "
        f"guided_url=http://{host}:{port}/guided "
        f"dashboard_url=http://{host}:{port}/dashboard run_dir={run_dir}"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\noperator_gui_stopped=true")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    run_operator_gui_server(run_dir=args.run_dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
