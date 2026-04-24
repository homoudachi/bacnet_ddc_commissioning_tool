# Docker BACnet simulator (lab)

This folder contains a **small, buildable** BACnet/IP UDP device used for local integration against the runtime CLI (`probe-bip`, `bacnet-read`, etc.).

## Build and run

From the repository root:

```bash
docker compose -f docker/simulator/docker-compose.yml --profile bacnet-dev up -d --build
```

Services (profile **`bacnet-dev`**):

| Container | Host UDP | Device instance | Notes |
|-----------|----------|-----------------|--------|
| `bacnet-fcu-sim` | `127.0.0.1:47808` | 21001 | `SIM_PROFILE=fcu` (default): FCU object instances |
| `bacnet-fcu-sim-02` | `127.0.0.1:47809` | 21002 | FCU profile; different SAT/MSV via `SIM_*` |
| `bacnet-hrv-sim` | `127.0.0.1:47810` | 22001 | `SIM_PROFILE=hrv`: MSV instance **60**, temps, fan cmds (see `server.py`) |

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

python3 tools/runtime/app.py verify-bip-list \
  --run-dir "$RUN" \
  --strict \
  --timeout-seconds 1.0 \
  --retries 2
```

Expected: `"strict_pass": true`, `"total": 3`, all controllers **`reachable_verified`**.

After probes, CI also runs **`bacnet-read`** against **`FCU-DOCKER`** / **`FCU-DOCKER-B`** (`ai_sat`) and **`HRV-DOCKER`** (`msv_test_mode`) to exercise **ReadProperty** through **bacpypes3** to the containers.

## Stop

```bash
docker compose -f docker/simulator/docker-compose.yml --profile bacnet-dev down
```

## Implementation notes

- Image: `docker/simulator/bacnet-device/` — Python 3.12 + **bacpypes3**, same object instances as the in-process test fake (`analogInput` 2, `multiStateValue` 50, `analogValue` 3/4, `analogOutput` 5).
- Environment: `DEVICE_INSTANCE`, `BACNET_UDP_PORT`, `SIM_PROFILE` (`fcu` default or `hrv` for HRV example objects), optional `SIM_*` initial values (see `server.py`).
