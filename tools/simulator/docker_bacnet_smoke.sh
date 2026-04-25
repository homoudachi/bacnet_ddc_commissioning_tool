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
assert s.get('total')==4, s
assert s.get('unresolved')==0, s
rows={r['controller_label']:r for r in s.get('rows',[])}
assert rows['FCU-DOCKER']['status']=='reachable_verified'
assert rows['FCU-DOCKER-B']['status']=='reachable_verified'
assert rows['FCU-DOCKER-C']['status']=='reachable_verified'
assert rows['HRV-DOCKER']['status']=='reachable_verified'
"

BACNET_READ_FLAGS="--timeout-seconds 2.0 --retries 3"

for pair in \
  "FCU-DOCKER:ai_sat" \
  "FCU-DOCKER-B:ai_sat" \
  "FCU-DOCKER-C:ai_sat" \
  "HRV-DOCKER:msv_test_mode" \
  "HRV-DOCKER:ai_supply_air_temperature" \
  "HRV-DOCKER:av_supply_fan_command" \
  "HRV-DOCKER:av_exhaust_fan_command"; do
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

# SubscribeCOV (unconfirmed) on FCU supply air temp: first notification from lab sim.
cov_out="$(python3 "$ROOT/tools/runtime/app.py" bacnet-subscribe-cov \
  --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER \
  --object-id ai_sat \
  $BACNET_READ_FLAGS \
  --wait-seconds 8.0 \
  --subscriber-process-id 9001)"
echo "$cov_out"
echo "$cov_out" | grep -q '"status": "cov_ok"' || {
  echo "error: bacnet-subscribe-cov failed for FCU-DOCKER ai_sat"
  exit 2
}

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

# FCU: batched writes (single Who-Is) — MSV + heat AV, then read-back.
batch_out="$(python3 "$ROOT/tools/runtime/app.py" bacnet-write-batch \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER --execute $WRITE_FLAGS \
  --write msv_test_mode=2 --write av_electric_heat_command=41.0)"
echo "$batch_out"
echo "$batch_out" | grep -q '"status": "batch_ok"' || {
  echo "error: bacnet-write-batch failed for FCU-DOCKER"
  exit 2
}
rbatch_msv="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER --object-id msv_test_mode $BACNET_READ_FLAGS)"
echo "$rbatch_msv"
echo "$rbatch_msv" | grep -q '"value_str": "2"' || { echo "error: FCU-DOCKER MSV not 2 after batch"; exit 2; }
rbatch_heat="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER --object-id av_electric_heat_command $BACNET_READ_FLAGS)"
echo "$rbatch_heat"
echo "$rbatch_heat" | grep -q '"value_str": "41.0"' || { echo "error: FCU-DOCKER heat AV not 41 after batch"; exit 2; }

# FCU: single WritePropertyMultiple APDU (MSV + heat AV), then read-back.
batch_wpm="$(python3 "$ROOT/tools/runtime/app.py" bacnet-write-batch \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER --execute $WRITE_FLAGS \
  --mode multiple \
  --write msv_test_mode=4 --write av_electric_heat_command=12.5)"
echo "$batch_wpm"
echo "$batch_wpm" | grep -q '"bacnet_service": "writePropertyMultiple"' || {
  echo "error: expected writePropertyMultiple in batch JSON"
  exit 2
}
echo "$batch_wpm" | grep -q '"status": "batch_ok"' || {
  echo "error: bacnet-write-batch --mode multiple failed"
  exit 2
}
rwpm_msv="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER --object-id msv_test_mode $BACNET_READ_FLAGS)"
echo "$rwpm_msv"
echo "$rwpm_msv" | grep -q '"value_str": "4"' || { echo "error: FCU-DOCKER MSV not 4 after WPM batch"; exit 2; }
rwpm_heat="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER --object-id av_electric_heat_command $BACNET_READ_FLAGS)"
echo "$rwpm_heat"
echo "$rwpm_heat" | grep -q '"value_str": "12.5"' || { echo "error: FCU-DOCKER heat AV not 12.5 after WPM batch"; exit 2; }

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

# FCU: analog WriteProperty (heat AV) + read-back.
wheat="$(python3 "$ROOT/tools/runtime/app.py" dry-run-bacnet-write \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER \
  --object-id av_electric_heat_command --value 37.5 --execute $WRITE_FLAGS)"
echo "$wheat"
echo "$wheat" | grep -q '"status": "write_ok"' || { echo "error: FCU-DOCKER heat AV write failed"; exit 2; }
rheat="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER --object-id av_electric_heat_command $BACNET_READ_FLAGS)"
echo "$rheat"
echo "$rheat" | grep -q '"value_str": "37.5"' || { echo "error: FCU-DOCKER heat AV not 37.5 after write"; exit 2; }

# FCU: analog WriteProperty (CHW valve AO) + read-back.
wvalve="$(python3 "$ROOT/tools/runtime/app.py" dry-run-bacnet-write \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER-B \
  --object-id ao_chw_valve --value 62 --execute $WRITE_FLAGS)"
echo "$wvalve"
echo "$wvalve" | grep -q '"status": "write_ok"' || { echo "error: FCU-DOCKER-B valve AO write failed"; exit 2; }
rvalve="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER-B --object-id ao_chw_valve $BACNET_READ_FLAGS)"
echo "$rvalve"
echo "$rvalve" | grep -q '"value_str": "62"' || { echo "error: FCU-DOCKER-B valve AO not 62 after write"; exit 2; }

# HRV: analog WriteProperty on supply + exhaust fan commands + read-back.
wsup="$(python3 "$ROOT/tools/runtime/app.py" dry-run-bacnet-write \
  --run-dir "$RUN_DIR" --controller-label HRV-DOCKER \
  --object-id av_supply_fan_command --value 55 --execute $WRITE_FLAGS)"
echo "$wsup"
echo "$wsup" | grep -q '"status": "write_ok"' || { echo "error: HRV-DOCKER supply fan AV write failed"; exit 2; }
rsup="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label HRV-DOCKER --object-id av_supply_fan_command $BACNET_READ_FLAGS)"
echo "$rsup"
echo "$rsup" | grep -q '"value_str": "55"' || { echo "error: HRV-DOCKER supply fan AV not 55 after write"; exit 2; }

wexh="$(python3 "$ROOT/tools/runtime/app.py" dry-run-bacnet-write \
  --run-dir "$RUN_DIR" --controller-label HRV-DOCKER \
  --object-id av_exhaust_fan_command --value 33 --execute $WRITE_FLAGS)"
echo "$wexh"
echo "$wexh" | grep -q '"status": "write_ok"' || { echo "error: HRV-DOCKER exhaust fan AV write failed"; exit 2; }
rexh="$(python3 "$ROOT/tools/runtime/app.py" bacnet-read --run-dir "$RUN_DIR" \
  --controller-label HRV-DOCKER --object-id av_exhaust_fan_command $BACNET_READ_FLAGS)"
echo "$rexh"
echo "$rexh" | grep -q '"value_str": "33"' || { echo "error: HRV-DOCKER exhaust fan AV not 33 after write"; exit 2; }

# Profile point_checkout lists (FCU: four points; HRV: three).
pc1="$(python3 "$ROOT/tools/runtime/app.py" bacnet-point-checkout \
  --run-dir "$RUN_DIR" --controller-label FCU-DOCKER $BACNET_READ_FLAGS)"
echo "$pc1"
echo "$pc1" | grep -q '"all_read_ok": true' || { echo "error: FCU-DOCKER point-checkout failed"; exit 2; }

pc2="$(python3 "$ROOT/tools/runtime/app.py" bacnet-point-checkout \
  --run-dir "$RUN_DIR" --controller-label HRV-DOCKER $BACNET_READ_FLAGS)"
echo "$pc2"
echo "$pc2" | grep -q '"all_read_ok": true' || { echo "error: HRV-DOCKER point-checkout failed"; exit 2; }

echo "docker_bacnet_smoke_ok=true"
