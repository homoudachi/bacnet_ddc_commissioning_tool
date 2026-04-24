# Docker BACnet simulator (lab)

This folder contains a **small, buildable** BACnet/IP UDP device used for local integration against the runtime CLI (`probe-bip`, `bacnet-read`, etc.).

## Build and run

From the repository root:

```bash
docker compose -f docker/simulator/docker-compose.yml --profile bacnet-dev up -d --build
```

The service listens on **UDP 47808** on the host loopback (`127.0.0.1:47808`).

## Smoke test with the runtime CLI

```bash
RUN=artifacts/docker-bacnet-sim-run
python3 tools/runtime/app.py init-run \
  --run-dir "$RUN" \
  --job-id docker-bacnet-sim \
  --controllers-csv docs/examples/site-controllers.docker-bacnet-sim.csv \
  --profiles-dir docs/examples \
  --scenarios-dir docs/examples/simulator-scenarios

python3 tools/runtime/app.py compile-import --run-dir "$RUN"

python3 tools/runtime/app.py probe-bip \
  --run-dir "$RUN" \
  --controller-label FCU-DOCKER \
  --timeout-seconds 1.0 \
  --retries 2
```

Expected: `reachable_verified` in the JSON output.

## Stop

```bash
docker compose -f docker/simulator/docker-compose.yml --profile bacnet-dev down
```

## Implementation notes

- Image: `docker/simulator/bacnet-device/` — Python 3.12 + **bacpypes3**, same object instances as the in-process test fake (`analogInput` 2, `multiStateValue` 50, `analogValue` 3/4, `analogOutput` 5).
- Environment: `DEVICE_INSTANCE` (default `21001`), `BACNET_UDP_PORT` (default `47808`), optional `SIM_*` initial values (see `server.py`).
