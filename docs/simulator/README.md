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

## Docker topology profiles

Use one Compose file with profiles so the same structure works in CI and lab environments.

### `ci` profile (first priority)

- Bridge network with static container IPs
- Deterministic behavior and repeatable tests
- No dependency on broadcast discovery
- Best fit for automated regression

### `lab` profile

- `macvlan` network so simulator devices appear as first-class LAN hosts
- Better parity with bench tools and packet capture workflows
- Still executes list-first verification logic

### `multisubnet` profile

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

### 1) Render and inspect topology

```bash
docker compose -f docker/simulator/docker-compose.yml --profile ci config >/tmp/simulator-compose.ci.yaml
docker compose -f docker/simulator/docker-compose.yml --profile lab config >/tmp/simulator-compose.lab.yaml
docker compose -f docker/simulator/docker-compose.yml --profile multisubnet config >/tmp/simulator-compose.multisubnet.yaml
```

### 2) Start a profile

```bash
docker compose -f docker/simulator/docker-compose.yml --profile ci up -d
```

For bench networking:

```bash
LAB_PARENT_IFACE=eth0 docker compose -f docker/simulator/docker-compose.yml --profile lab up -d
```

### 3) Health checks

```bash
docker compose -f docker/simulator/docker-compose.yml ps
docker compose -f docker/simulator/docker-compose.yml logs scenario-orchestrator-ci
docker compose -f docker/simulator/docker-compose.yml logs test-runner-ci
```

### 4) Shut down

```bash
docker compose -f docker/simulator/docker-compose.yml down
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
- Product record: `docs/project.md`

## Verification status (2026-04-21)

- `docker compose -f docker/simulator/docker-compose.yml --profile ci config` succeeded
- `docker compose -f docker/simulator/docker-compose.yml --profile lab config` succeeded
- `docker compose -f docker/simulator/docker-compose.yml --profile multisubnet config` succeeded
