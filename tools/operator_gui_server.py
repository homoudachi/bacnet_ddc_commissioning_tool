#!/usr/bin/env python3
"""Minimal browser UI for commissioning run-dir (Tier B2 — stdlib only).

Serves a single-page form that POSTs to ``/cli`` and runs ``tools/runtime/app.py``
subcommands with validated allowlist. Intended for local operator use only
(bind to 127.0.0.1 by default).

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


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CLI = ROOT / "tools" / "runtime" / "app.py"

ALLOWED_PREFIXES = (
    "show-flow",
    "show-session",
    "list-flows",
    "commissioning-guided-next",
    "set-session-value",
    "record-step",
    "bacnet-read",
    "commissioning-airflow-adjust-write",
    "commissioning-airflow-closed-loop-iterate",
    "commissioning-confirm-tachometer-reference",
    "commissioning-record-manual-airflow",
    "commissioning-confirm-prompt",
    "export-run-summary",
    "export-commissioning-report",
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


class _Handler(BaseHTTPRequestHandler):
    run_dir: Path = ROOT

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def do_GET(self) -> None:
        if self.path != "/" and not self.path.startswith("/?"):
            self.send_error(404)
            return
        data = _page(self.run_dir)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path != "/cli":
            self.send_error(404)
            return
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
<p><a href="/">Back</a></p>
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
    print(f"operator_gui_listening=true url=http://{host}:{port}/ run_dir={run_dir}")
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
