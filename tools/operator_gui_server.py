#!/usr/bin/env python3
"""Browser UI for commissioning run-dir (stdlib HTTPServer).

Two modes:

* **/** — Advanced form: POST to ``/cli`` with allowlisted subcommands + free-form extra args.
* **/guided** — Graphical guided flow: pick controller, view steps / next / blockers, set session
  values, record step outcomes (calls the same ``tools/runtime/app.py`` CLI under the hood).

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
    "bacnet-read",
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
        "bacnet-point-checkout",
        "bacnet-read",
        "bacnet-modulation-sweep",
        "commissioning-airflow-adjust-write",
        "commissioning-airflow-closed-loop-iterate",
        "commissioning-confirm-tachometer-reference",
        "commissioning-record-manual-airflow",
        "commissioning-confirm-prompt",
    }
)


def _page(run_dir: Path) -> bytes:
    rd = html.escape(str(run_dir.resolve()))
    opts = "".join(f"<option>{html.escape(p)}</option>" for p in ALLOWED_PREFIXES)
    body = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Commissioning operator</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 52rem; }}
label {{ display: block; margin-top: 0.75rem; font-weight: 600; }}
input, textarea, select {{ width: 100%; box-sizing: border-box; margin-top: 0.25rem; }}
textarea {{ font-family: ui-monospace, monospace; min-height: 6rem; }}
pre {{ background: #f4f4f4; padding: 0.75rem; overflow: auto; }}
button {{ margin-top: 1rem; padding: 0.4rem 1rem; }}
.meta {{ color: #555; font-size: 0.9rem; }}
</style></head>
<body>
<h1>Commissioning operator (local)</h1>
<p class="meta">Run dir: <code>{rd}</code></p>
<p class="meta"><a href="/guided">Open guided commissioning flow UI</a></p>
<p class="meta">Commands run as subprocess to <code>tools/runtime/app.py</code>. Bind defaults to loopback only.</p>
<form method="post" action="/cli">
<label>Command</label>
<select name="command">{opts}</select>
<label>Extra arguments (one per line, e.g. <code>--controller-label FCU-01A</code>)</label>
<textarea name="extra" placeholder="--controller-label FCU-01A&#10;--step-id some_step"></textarea>
<button type="submit">Run</button>
</form>
<p class="meta">Examples: <code>set-session-value</code> needs <code>--key rat_degC --value 22 --technician-name Me --note ...</code>;
<code>record-step</code> needs <code>--step-id ... --status passed --technician-name ...</code>.</p>
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
  --text: #e8eef5;
  --muted: #8b9cb3;
  --accent: #3d8bfd;
  --ok: #2fb573;
  --warn: #e9a23b;
  --err: #f47174;
  --border: #2d3a4d;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  margin: 0; background: var(--bg); color: var(--text); min-height: 100vh;
}}
header {{
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;
}}
header h1 {{ font-size: 1.1rem; margin: 0; font-weight: 600; }}
header .meta {{ color: var(--muted); font-size: 0.85rem; }}
header a {{ color: var(--accent); }}
.layout {{
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
  gap: 0; min-height: calc(100vh - 56px);
}}
@media (max-width: 900px) {{
  .layout {{ grid-template-columns: 1fr; }}
}}
.panel {{
  background: var(--panel); border-right: 1px solid var(--border);
  padding: 1rem 1.1rem; overflow: auto; max-height: calc(100vh - 56px);
}}
.panel:last-child {{ border-right: none; }}
label {{ display: block; font-size: 0.8rem; color: var(--muted); margin-top: 0.75rem; }}
select, input, textarea {{
  width: 100%; margin-top: 0.25rem; padding: 0.45rem 0.55rem;
  border-radius: 6px; border: 1px solid var(--border);
  background: #0d1218; color: var(--text); font-size: 0.95rem;
}}
textarea {{ min-height: 4.5rem; font-family: ui-monospace, monospace; font-size: 0.82rem; }}
button {{
  margin-top: 0.85rem; padding: 0.5rem 1rem; border-radius: 6px; border: none;
  cursor: pointer; font-weight: 600; background: var(--accent); color: #fff;
}}
button.secondary {{ background: #3a4a5e; color: var(--text); }}
button.danger {{ background: #a33; }}
.row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
.badge {{
  display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px;
  font-size: 0.75rem; font-weight: 600;
}}
.badge.pending {{ background: #3a4a5e; }}
.badge.passed, .badge.manual_passed {{ background: #1e5c3d; }}
.badge.failed {{ background: #6b2224; }}
.badge.skipped {{ background: #5c4a1e; }}
.step-list {{ list-style: none; padding: 0; margin: 0.5rem 0 0; max-height: 42vh; overflow: auto; }}
.step-list li {{
  padding: 0.5rem 0.55rem; border-radius: 6px; margin-bottom: 0.35rem;
  border: 1px solid transparent; cursor: pointer;
}}
.step-list li:hover {{ border-color: var(--border); }}
.step-list li.active {{ border-color: var(--accent); background: #0d1218; }}
.step-list li .sid {{ font-family: ui-monospace, monospace; font-size: 0.8rem; color: var(--accent); }}
.flash {{
  margin-top: 0.75rem; padding: 0.6rem 0.75rem; border-radius: 6px; font-size: 0.88rem;
}}
.flash.err {{ background: #3a1a1c; color: #ffb4b6; }}
.flash.ok {{ background: #1a2e24; color: #9ee5c0; }}
.cmds {{ margin: 0.5rem 0 0; padding-left: 1.1rem; font-size: 0.82rem; color: var(--muted); }}
.cmds code {{ color: #b8d4ff; font-size: 0.78rem; }}
h2 {{ font-size: 1rem; margin: 0 0 0.5rem; }}
h3 {{ font-size: 0.9rem; margin: 1rem 0 0.35rem; color: var(--muted); font-weight: 600; }}
</style></head>
<body>
<header>
  <h1>Guided commissioning</h1>
  <span class="meta">Run dir: <code id="runDirDisp"></code></span>
  <span class="meta"><a href="/">Advanced CLI form</a></span>
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
    <div id="detailFlash" class="flash" style="display:none"></div>
    <div id="blockers" style="display:none">
      <h3>Why this step is blocked</h3>
      <ul id="blockerList"></ul>
    </div>
    <h3>Suggested commands</h3>
    <ul class="cmds" id="cmdList"></ul>
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
    <pre id="sessKeys" style="max-height:10rem;overflow:auto;background:#0d1218;padding:0.5rem;border-radius:6px;font-size:0.78rem"></pre>
  </div>
</div>
<script>
const RUN_DIR = {rd};
document.getElementById("runDirDisp").textContent = RUN_DIR;

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
    await loadGuidance();
  }}
}}

function badgeClass(st) {{
  const s = (st || "pending").toLowerCase();
  if (["passed", "manual_passed", "failed", "skipped", "pending"].includes(s)) return "badge " + s;
  return "badge pending";
}}

async function loadGuidance() {{
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
  if (next && next.step_id) selectStep(next.step_id);
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
}}

document.getElementById("btnReload").addEventListener("click", loadControllers);
document.getElementById("selCtl").addEventListener("change", loadGuidance);

document.getElementById("btnSess").addEventListener("click", async () => {{
  const c = document.getElementById("selCtl").value;
  const key = document.getElementById("sessKey").value.trim();
  const val = document.getElementById("sessVal").value;
  const tech = document.getElementById("sessTech").value.trim();
  const note = document.getElementById("sessNote").value.trim();
  if (!key || !tech) {{
    showFlash(document.getElementById("detailFlash"), "Session key and technician are required.", true);
    return;
  }}
  try {{
    await apiJson("/api/v1/set-session", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, key, value: val, technician_name: tech, note }}),
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
  if (!step_id || !technician_name) {{
    showFlash(document.getElementById("detailFlash"), "Step ID and technician are required.", true);
    return;
  }}
  try {{
    await apiJson("/api/v1/record-step", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ controller: c, step_id, status, technician_name, note }}),
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

loadControllers().catch(e => showFlash(document.getElementById("ctlFlash"), String(e.message), true));
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
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/cli":
            self._post_cli()
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
<p><a href="/">Back</a> · <a href="/guided">Guided UI</a></p>
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
        f"guided_url=http://{host}:{port}/guided run_dir={run_dir}"
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
