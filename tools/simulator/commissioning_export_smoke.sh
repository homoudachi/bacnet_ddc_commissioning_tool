#!/usr/bin/env sh
# Smoke: export-commissioning-report empty stub (JSON + unified CSV + HTML + XLSX + PDF).
# Requires: python3, requirements.txt installed, cwd = repository root.

set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RUN_DIR="${RUN_DIR:-$ROOT/artifacts/ci-commissioning-export-smoke}"

cd "$ROOT"

rm -rf "$RUN_DIR"
python3 "$ROOT/tools/runtime/app.py" init-run \
  --run-dir "$RUN_DIR" \
  --job-id ci-commissioning-export-smoke \
  --controllers-csv "$ROOT/docs/examples/site-controllers.template.csv" \
  --profiles-dir "$ROOT/docs/examples" \
  --scenarios-dir "$ROOT/docs/examples/simulator-scenarios"

python3 "$ROOT/tools/runtime/app.py" export-commissioning-report \
  --run-dir "$RUN_DIR" \
  --allow-empty \
  --output-json "$RUN_DIR/artifacts/export-stub.json" \
  --output-csv-unified "$RUN_DIR/artifacts/export-unified.csv" \
  --output-html "$RUN_DIR/artifacts/export.html" \
  --output-xlsx "$RUN_DIR/artifacts/export.xlsx" \
  --output-pdf "$RUN_DIR/artifacts/export.pdf"

python3 - "$RUN_DIR" "$ROOT" <<'PY'
import csv
import importlib.util
import json
import pathlib
import sys

run = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])
stub = run / "artifacts" / "export-stub.json"
uni = run / "artifacts" / "export-unified.csv"
html = run / "artifacts" / "export.html"
xlsx = run / "artifacts" / "export.xlsx"
pdf = run / "artifacts" / "export.pdf"

for p in (stub, uni, html, xlsx, pdf):
    if not p.is_file():
        print(f"error: missing output {p}")
        sys.exit(2)

doc = json.loads(stub.read_text(encoding="utf-8"))
assert doc.get("entries") == [], doc
assert doc.get("job_id") == "ci-commissioning-export-smoke", doc

with uni.open(newline="", encoding="utf-8") as handle:
    reader = csv.reader(handle)
    header = next(reader)

rt = root / "tools" / "runtime" / "app.py"
sys.path.insert(0, str(rt.parent))
spec = importlib.util.spec_from_file_location("rt_app_smoke", rt)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)
expected = list(mod.COMMISSIONING_REPORT_UNIFIED_FIELDNAMES)
if header != expected:
    print("error: unified CSV header mismatch vs COMMISSIONING_REPORT_UNIFIED_FIELDNAMES")
    print("csv:", header)
    print("exp:", expected)
    sys.exit(2)

text = html.read_text(encoding="utf-8")
if "<!DOCTYPE html>" not in text or "prompt_id" not in text:
    print("error: HTML export missing expected content")
    sys.exit(2)

if not pdf.read_bytes().startswith(b"%PDF"):
    print("error: PDF export missing %PDF magic")
    sys.exit(2)

print("commissioning_export_smoke_ok=true")
PY
