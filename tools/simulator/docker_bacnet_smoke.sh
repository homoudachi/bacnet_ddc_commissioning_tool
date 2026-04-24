#!/usr/bin/env sh
# Build/start Docker BACnet sim, probe FCU-DOCKER via runtime CLI, tear down.
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

OUT="$(python3 "$ROOT/tools/runtime/app.py" probe-bip \
  --run-dir "$RUN_DIR" \
  --controller-label FCU-DOCKER \
  --timeout-seconds 2.0 \
  --retries 3)"

echo "$OUT"
echo "$OUT" | grep -q 'reachable_verified' || {
  echo "error: probe-bip did not report reachable_verified"
  exit 2
}

echo "docker_bacnet_smoke_ok=true"
