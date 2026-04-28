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
| `bacnet-fcu-sim-03` | `127.0.0.1:47811` | 21003 | Extra FCU-shaped device for multi-controller lab smoke |
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

Expected: `"strict_pass": true`, `"total": 4`, all controllers **`reachable_verified`**.

After probes, CI also runs **`bacnet-read`** (FCU **`ai_sat`** and **`av_supply_fan_command`** on all three FCU rows, HRV **`msv_test_mode`**, **`ai_supply_air_temperature`**, **`av_supply_fan_command`**, **`av_exhaust_fan_command`**), **`bacnet-subscribe-cov`** on FCU **`ai_sat`**, **`bacnet-write-batch`** (FCU MSV + heat AV, sequential then **`--mode multiple`** WritePropertyMultiple), **`dry-run-bacnet-write --execute`** on **`msv_test_mode`** (FCU + HRV) plus **analog** writes on FCU **`av_supply_fan_command`** / **`av_electric_heat_command`** / **`ao_chw_valve`** and HRV fan commands (each with read-back), and **`bacnet-point-checkout`** for both profiles.

## BBMD + foreign-device lab (profile `bacnet-bbmd-lab`)

Isolated-subnet FCU sim + BACpypes3 **BBMD** + one-shot **foreign-device** read probe. When Docker is available:

```bash
tools/simulator/docker_bbmd_lab_smoke.sh
```

Details: **ADR 0015** (`docs/adr/0015-bbmd-lab-cov-write-batch.md`).

## macvlan bench (host LAN)

See **[`docs/simulator/macvlan-lab.md`](../docs/simulator/macvlan-lab.md)** and **`docker-compose.macvlan.example.yml`**.

## Stop

```bash
docker compose -f docker/simulator/docker-compose.yml --profile bacnet-dev down
```

## Implementation notes

- Image: `docker/simulator/bacnet-device/` — Python 3.12 + **bacpypes3**, same object instances as the in-process test fake (`analogInput` 2, `multiStateValue` 50, `analogValue` 3/4, `analogOutput` 5).
- Environment: `DEVICE_INSTANCE`, `BACNET_UDP_PORT`, `SIM_PROFILE` (`fcu` default or `hrv` for HRV example objects), optional `SIM_*` initial values (see `server.py`). FCU profile: **`SIM_AV_SUPPLY_FAN`** (analogValue **3**, supply fan command) is separate from **`SIM_AV_HEAT`** (instance **4**, electric heat).
