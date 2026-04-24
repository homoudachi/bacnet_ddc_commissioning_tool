# BACnet simulator lab

This document defines how the simulator lab should work for both deterministic CI and realistic bench networking.

## Primary objective

Always try to find and verify **every controller row** in the imported list.

- No silent skips
- No "best effort" pass when required rows are unresolved
- Every row receives a final status classification

## List-first discovery and verification (authoritative behavior)

Input is the imported controller list (for example: IP, UDP port, expected BACnet Device Instance, `profile_id`, required points).

For each row, execute this sequence:

1. **Directed probe** to the row's expected endpoint (unicast first)
2. **Identity check** by reading BACnet device identity data and matching expected Device Instance
3. **Required object check** for row/profile points needed by commissioning logic
4. **Read/write sanity check** for writable points in simulator-safe mode
5. **Final classification** and reason code

Supported row classifications:

- `reachable_verified`
- `unreachable_timeout`
- `identity_mismatch`
- `required_point_missing`
- `write_rejected`
- `known_unavailable` (allowed only if explicitly marked in test input)

CI strict mode must fail when any required row is not `reachable_verified`.

## Docker BACnet device (implemented)

A **runnable** single-device simulator ships in this repository:

- Compose: `docker/simulator/docker-compose.yml` — profile **`bacnet-dev`**
- Image source: `docker/simulator/bacnet-device/` (Python + bacpypes3 UDP server)
- Runbook: `docker/simulator/README.md`

CI runs `tools/simulator/docker_bacnet_smoke.sh` (builds images, starts **three** sim containers on `127.0.0.1:47808`–`47810`, then **`verify-bip-list --strict`**, **`bacnet-read`**, **`dry-run-bacnet-write --execute`** + read-back, **`bacnet-point-checkout`**, then tears down).

## Docker topology profiles (longer-term lab spec)

The sections below describe a **multi-service** lab layout (orchestrator, multiple devices, BBMD). That topology is **not** wired to public images yet; use **`bacnet-dev`** above for day-to-day BACnet smoke tests.

### `ci` profile (planned multi-device)

- Bridge network with static container IPs
- Deterministic behavior and repeatable tests
- No dependency on broadcast discovery
- Best fit for automated regression

### `lab` profile (planned)

- `macvlan` network so simulator devices appear as first-class LAN hosts
- Better parity with bench tools and packet capture workflows
- Still executes list-first verification logic

### `multisubnet` profile (planned)

- Two simulated BACnet subnets
- BBMD service included
- Validates cross-subnet discovery and routing assumptions

### `ci-netem` profile (optional)

- Network impairment sidecar for latency/loss/jitter testing
- Used to validate timeout/retry behavior before field testing

## Scenario catalog

Minimum scenario set:

1. **happy_path**: all listed devices reachable and correct identity/points
2. **timeout_burst**: intermittent timeout windows
3. **identity_mismatch**: reachable device with wrong Device Instance
4. **required_point_missing**: profile-required object missing or wrong type
5. **chw_unavailable**: cooling plant unavailable path with skip reason flow

Starter scenario fixtures in-repo:

- `docs/examples/simulator-scenarios/happy-path.example.json`
- `docs/examples/simulator-scenarios/identity-mismatch.example.json`
- `docs/examples/simulator-scenarios/timeout-burst.example.json`
- `docs/examples/simulator-scenarios/required-point-missing.example.json`

## CI pass/fail gates

CI run fails if any of the following is true:

- Any required list row has no terminal classification
- Any required list row is not `reachable_verified`
- Any row is `identity_mismatch` in strict mode
- Any row is `required_point_missing` in strict mode

CI run may pass with `known_unavailable` only when explicitly marked in scenario input for that run.

## Runbook

### 0) Verify list-first gate locally (CLI smoke test)

```bash
python3 tools/simulator/list_verifier.py \
  --controllers-csv docs/examples/site-controllers.template.csv \
  --scenario-json docs/examples/simulator-scenarios/happy-path.example.json \
  --strict
```

Expected summary includes:

- `found=3 total=3 unresolved=0 strict_pass=true`
- `reachable_verified=3`

Machine-readable summary:

```bash
python3 tools/simulator/list_verifier.py \
  --controllers-csv docs/examples/site-controllers.template.csv \
  --scenario-json docs/examples/simulator-scenarios/identity-mismatch.example.json \
  --strict \
  --output json
```

### 0b) Run the orchestrator wrapper (profile + scenario)

```bash
python3 tools/simulator/orchestrator.py \
  --controllers-csv docs/examples/site-controllers.template.csv \
  --scenarios-dir docs/examples/simulator-scenarios \
  --profile ci \
  --scenario happy-path \
  --strict
```

JSON output mode through orchestrator:

```bash
python3 tools/simulator/orchestrator.py \
  --controllers-csv docs/examples/site-controllers.template.csv \
  --scenarios-dir docs/examples/simulator-scenarios \
  --profile ci \
  --scenario identity-mismatch \
  --strict \
  --output json
```

### 0c) Run scenario matrix and write artifact files

```bash
python3 tools/simulator/run_matrix.py \
  --controllers-csv docs/examples/site-controllers.template.csv \
  --scenarios-dir docs/examples/simulator-scenarios \
  --output-dir artifacts/simulator
```

This writes one JSON result per case, for example:

- `artifacts/simulator/ci-happy-path.json`
- `artifacts/simulator/ci-identity-mismatch.json`
- `artifacts/simulator/ci-required-point-missing.json`
- `artifacts/simulator/ci-timeout-burst.json`

### 1) BACnet device (current)

See **`docker/simulator/README.md`** for build/run and **`probe-bip`** smoke.

### 2) Planned multi-service compose (not shipped as images)

When multi-device images exist, render configs with:

```bash
# docker compose -f docker/simulator/docker-compose.yml --profile ci config
```

## Troubleshooting: "why was a device not found?"

Use this checklist in order:

1. Confirm row exists in imported controller list used by test run
2. Confirm expected IP/port and Device Instance in row
3. Confirm target simulator service is up and on expected profile/network
4. Inspect orchestrator logs for probe timeout vs identity mismatch
5. Inspect test-runner summary for final row classification
6. For `lab` mode, verify `LAB_PARENT_IFACE` and subnet/gateway match host LAN
7. For `multisubnet`, verify BBMD service is running and attached to both subnets

## References

- Topology spec: `docker/simulator/docker-compose.yml`
- Simulator planning sequence: `docs/plans/2026-04-21-bacnet-simulator-plan.md`
- Verifier CLI: `tools/simulator/list_verifier.py`
- Orchestrator wrapper: `tools/simulator/orchestrator.py`
- Product record: `docs/project.md`

## Verification status

- **2026-04-26:** `docker compose … --profile bacnet-dev up --build` + `tools/simulator/docker_bacnet_smoke.sh` exercises **`verify-bip-list --strict`** against three sim containers (two FCU + one HRV profile).
