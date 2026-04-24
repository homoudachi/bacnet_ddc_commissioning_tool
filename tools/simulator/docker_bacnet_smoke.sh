#!/usr/bin/env sh
# Build/start Docker BACnet sims (bacnet-dev), strict verify-bip-list for two rows, tear down.
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

echo "docker_bacnet_smoke_ok=true"
