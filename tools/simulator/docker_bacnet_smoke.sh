#!/usr/bin/env sh
# Build/start Docker BACnet sims (bacnet-dev), verify-bip-list --strict, then bacnet-read smoke, tear down.
# Requires: docker, docker compose v2, repository root as cwd.

set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$ROOT/docker/simulator/docker-compose.yml"
RUN_DIR="${RUN_DIR:-$ROOT/artifacts/ci-docker-bacnet-sim-run}"

cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker not found; skipping Docker BACnet smoke"
  exit 0
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "error: docker compose not found; skipping Docker BACnet smoke"
  exit 0
fi

cleanup() {
  docker compose -f "$COMPOSE_FILE" --profile bacnet-dev down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f "$COMPOSE_FILE" --profile bacnet-dev up -d --build

rm -rf "$RUN_DIR"
python3 "$ROOT/tools/runtime/app.py" init-run \
  --run-dir "$RUN_DIR" \
  --job-id ci-docker-bacnet-sim \
  --controllers-csv "$ROOT/docs/examples/site-controllers.docker-bacnet-sim.csv" \
  --profiles-dir "$ROOT/docs/examples" \
  --scenarios-dir "$ROOT/docs/examples/simulator-scenarios"

python3 "$ROOT/tools/runtime/app.py" compile-import --run-dir "$RUN_DIR"

SUMMARY="$(python3 "$ROOT/tools/runtime/app.py" verify-bip-list \
  --run-dir "$RUN_DIR" \
  --strict \
  --timeout-seconds 2.0 \
  --retries 3)"

echo "$SUMMARY"
echo "$SUMMARY" | python3 -c "import json,sys
s=json.load(sys.stdin)
assert s.get('strict_pass') is True, s
assert s.get('total')==3, s
assert s.get('unresolved')==0, s
rows={r['controller_label']:r for r in s.get('rows',[])}
assert rows['FCU-DOCKER']['status']=='reachable_verified'
assert rows['FCU-DOCKER-B']['status']=='reachable_verified'
assert rows['HRV-DOCKER']['status']=='reachable_verified'
"

BACNET_READ_FLAGS="--timeout-seconds 2.0 --retries 3"

for pair in "FCU-DOCKER:ai_sat" "FCU-DOCKER-B:ai_sat" "HRV-DOCKER:msv_test_mode" "HRV-DOCKER:ai_supply_air_temperature"; do
  label="${pair%%:*}"
  oid="${pair##*:}"
  out="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read \
    --run-dir "$RUN_DIR" \
    --controller-label "$label" \
    --object-id "$oid" \
    $BACNET_READ_FLAGS)"
  echo "$out"
  echo "$out" | grep -q '"status": "read_ok"' || {
    echo "error: bacnet-read failed for $label $oid"
    exit 2
  }
done

WRITE_FLAGS="$BACNET_READ_FLAGS --technician-name CI-Smoke --note docker-bacnet-smoke"

# FCU: WriteProperty MSV then read back (instance 50).
w1="$(python3 "$ROOT/tools/runtime/app.py" dry-run-bacnet-write \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER \
  --object-id msv_test_mode --value 3 --execute $WRITE_FLAGS)"
echo "$w1"
echo "$w1" | grep -q '"status": "write_ok"' || { echo "error: FCU-DOCKER MSV write failed"; exit 2; }
r1="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER --object-id msv_test_mode $BACNET_READ_FLAGS)"
echo "$r1"
echo "$r1" | grep -q '"value_str": "3"' || { echo "error: FCU-DOCKER MSV not 3 after write"; exit 2; }

# HRV: WriteProperty MSV (instance 60) then read back.
w2="$(python3 "$ROOT/tools/runtime/app.py" dry-run-bacnet-write \
  --run-dir "$RUN_DIR" --controller-label HRV-DOCKER \
  --object-id msv_test_mode --value 2 --execute $WRITE_FLAGS)"
echo "$w2"
echo "$w2" | grep -q '"status": "write_ok"' || { echo "error: HRV-DOCKER MSV write failed"; exit 2; }
r2="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label HRV-DOCKER --object-id msv_test_mode $BACNET_READ_FLAGS)"
echo "$r2"
echo "$r2" | grep -q '"value_str": "2"' || { echo "error: HRV-DOCKER MSV not 2 after write"; exit 2; }

# Profile point_checkout lists (FCU: two points; HRV: one).
pc1="$(python3 "$ROOT/tools/runtime/app.py" bacnet-point-checkout \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER $BACNET_READ_FLAGS)"
echo "$pc1"
echo "$pc1" | grep -q '"all_read_ok": true' || { echo "error: FCU-DOCKER point-checkout failed"; exit 2; }

pc2="$(python3 "$ROOT/tools/runtime/app.py" bacnet-point-checkout \
  --run-dir "$RUN_DIR" --controller-label HRV-DOCKER $BACNET_READ_FLAGS)"
echo "$pc2"
echo "$pc2" | grep -q '"all_read_ok": true' || { echo "error: HRV-DOCKER point-checkout failed"; exit 2; }

echo "docker_bacnet_smoke_ok=true"
