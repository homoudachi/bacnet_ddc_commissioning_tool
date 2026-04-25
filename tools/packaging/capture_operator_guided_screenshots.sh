#!/usr/bin/env sh
# Capture /guided and / operator UI screenshots (headless Chrome). Run from repo root.
#
# Usage:
#   tools/packaging/capture_operator_guided_screenshots.sh          # same as "update"
#   tools/packaging/capture_operator_guided_screenshots.sh update   # write docs/assets/*.png
#   tools/packaging/capture_operator_guided_screenshots.sh check    # CI: compare to committed PNGs
#
# Requires: google-chrome-stable, Python 3, compiled examples (same as README quick start).

set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-update}"
case "$MODE" in
  update|check) ;;
  *) echo "error: usage: $0 [update|check]"; exit 2 ;;
esac

RUN_DIR="${RUN_DIR:-$ROOT/artifacts/operator-ui-screenshot-run}"
PORT="${OPERATOR_GUI_SCREENSHOT_PORT:-9788}"
CHROME="${CHROME_BIN:-google-chrome-stable}"
ASSETS="$ROOT/docs/assets"

rm -rf "$RUN_DIR"
mkdir -p "$ASSETS"

python3 "$ROOT/tools/runtime/app.py" init-run \
  --run-dir "$RUN_DIR" \
  --job-id operator-ui-screenshot \
  --controllers-csv "$ROOT/docs/examples/site-controllers.template.csv" \
  --profiles-dir "$ROOT/docs/examples" \
  --scenarios-dir "$ROOT/docs/examples/simulator-scenarios"

python3 "$ROOT/tools/runtime/app.py" compile-import --run-dir "$RUN_DIR"
python3 "$ROOT/tools/runtime/app.py" init-flow --run-dir "$RUN_DIR" --controller-label FCU-01A

python3 "$ROOT/tools/operator_gui_server.py" --run-dir "$RUN_DIR" --host 127.0.0.1 --port "$PORT" &
GUI_PID=$!
cleanup() {
  kill "$GUI_PID" 2>/dev/null || true
}
trap cleanup EXIT
sleep 0.7

shot() {
  local url="$1"
  local out="$2"
  local w="${3:-1400}"
  local h="${4:-900}"
  "$CHROME" --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
    --window-size="${w},${h}" --virtual-time-budget=8000 \
    --screenshot="$out" "$url" 2>/dev/null || {
    echo "error: screenshot failed for $url"
    exit 2
  }
}

sha_file() {
  sha256sum "$1" | awk '{print $1}'
}

if [ "$MODE" = "check" ]; then
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"; cleanup' EXIT
  shot "http://127.0.0.1:${PORT}/guided" "$WORK/operator-guided-ui-wide.png" 1400 900
  shot "http://127.0.0.1:${PORT}/guided" "$WORK/operator-guided-ui-mobile.png" 420 900
  shot "http://127.0.0.1:${PORT}/" "$WORK/operator-advanced-cli-form.png" 900 820
  for name in operator-guided-ui-wide.png operator-guided-ui-mobile.png operator-advanced-cli-form.png; do
    a="$ASSETS/$name"
    b="$WORK/$name"
    ha="$(sha_file "$a")"
    hb="$(sha_file "$b")"
    if [ "$ha" != "$hb" ]; then
      echo "error: screenshot mismatch for $name"
      echo "  committed: $ha"
      echo "  captured:  $hb"
      echo "  Run: tools/packaging/capture_operator_guided_screenshots.sh update"
      echo "  Then commit docs/assets/$name and tests/test_operator_guided_screenshots_checksums.py"
      exit 2
    fi
  done
  echo "operator_guided_screenshots_checksum_ok=true"
  exit 0
fi

shot "http://127.0.0.1:${PORT}/guided" "$ASSETS/operator-guided-ui-wide.png" 1400 900
shot "http://127.0.0.1:${PORT}/guided" "$ASSETS/operator-guided-ui-mobile.png" 420 900
shot "http://127.0.0.1:${PORT}/" "$ASSETS/operator-advanced-cli-form.png" 900 820

echo "screenshots_ok=true paths=$ASSETS/operator-guided-ui-wide.png ..."
echo "sha256 (update tests/test_operator_guided_screenshots_checksums.py if UI changed):"
for f in "$ASSETS/operator-guided-ui-wide.png" "$ASSETS/operator-guided-ui-mobile.png" "$ASSETS/operator-advanced-cli-form.png"; do
  echo "  $(basename "$f") $(sha_file "$f")"
done
