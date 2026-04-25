#!/usr/bin/env sh
# BBMD + foreign-device lab smoke: isolated subnet device reachable via sidecar probe.
# Requires: docker, docker compose v2, repository root as cwd.

set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$ROOT/docker/simulator/docker-compose.yml"

cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker not found; skipping BBMD lab smoke"
  exit 0
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "error: docker compose not found; skipping BBMD lab smoke"
  exit 0
fi

cleanup() {
  docker compose -f "$COMPOSE_FILE" --profile bacnet-bbmd-lab down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f "$COMPOSE_FILE" --profile bacnet-bbmd-lab up -d --build \
  bacnet-bbmd-lab bacnet-fcu-bbmd-isolated

sleep 2

OUT="$(docker compose -f "$COMPOSE_FILE" --profile bacnet-bbmd-lab run --rm --no-deps bacnet-bbmd-probe 2>&1)" || {
  echo "$OUT"
  echo "error: bbmd probe failed"
  exit 2
}
echo "$OUT"
echo "$OUT" | grep -q '"status": "read_ok"' || {
  echo "error: expected read_ok from foreign-device probe"
  exit 2
}
echo "$OUT" | grep -q '"value_str"' || {
  echo "error: expected value_str in probe JSON"
  exit 2
}

echo "docker_bbmd_lab_smoke_ok=true"
