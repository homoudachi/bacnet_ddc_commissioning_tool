# BACnet Simulator Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Docker-based BACnet simulation lab that can realistically emulate commissioning behavior while deterministically verifying every controller in the imported list.

**Architecture:** Use Docker Compose profiles to support three environments: deterministic CI (bridge network + static IPs), realistic bench LAN (macvlan), and multi-subnet/BBMD validation. Drive all verification from the imported controller list, using directed BACnet probes and object-level checks per row.

**Tech Stack:** Docker Compose, BACnet simulator containers (generic), scenario orchestrator, optional network impairment (`tc/netem`), integration test runner.

---

## File structure

- Create: `docker/simulator/docker-compose.yml`
- Create: `docs/simulator/README.md`
- Create: `docs/plans/2026-04-21-bacnet-simulator-plan.md`
- Modify: `docs/project.md` (BACnet simulation and CI section)
- Modify: `README.md` (link to simulator topology and plan)

---

### Task 1: Define simulator behavior contract and list-driven discovery strategy

**Files:**
- Modify: `docs/project.md`
- Create: `docs/simulator/README.md`
- Test: `docs/simulator/README.md` (review checklist)

- [ ] **Step 1: Write the failing test (documentation acceptance checklist)**

```markdown
Simulator docs are incomplete unless all are present:
1. "Find everything in list" algorithm (row-by-row verification)
2. Probe order (connectivity -> BACnet identity -> required points)
3. Retry/timeouts and unreachable device reporting
4. Deterministic CI mode and realistic lab mode
```

- [ ] **Step 2: Run review to confirm checklist currently fails**

Run: `rg "find everything|directed who-is|unreachable|macvlan|bbmd" docs/project.md docs/simulator/README.md`
Expected: Missing or partial coverage before updates.

- [ ] **Step 3: Write minimal documentation implementation**

```markdown
Add a "List-first discovery and verification" section describing:
- Input: imported controllers list (IP, port, device instance, profile_id)
- For each row:
  a) Directed probe to expected BACnet endpoint
  b) Confirm device identity matches row expectation
  c) Read required points/MSV map for profile
  d) Classify status: reachable, identity mismatch, point mismatch, timeout
- Aggregate summary: found X/Y, strict pass/fail gate for CI
```

- [ ] **Step 4: Verify checklist passes**

Run: `rg "List-first discovery and verification|identity mismatch|found X/Y|macvlan" docs/project.md docs/simulator/README.md`
Expected: All required concepts present.

- [ ] **Step 5: Commit**

```bash
git add docs/project.md docs/simulator/README.md
git commit -m "docs: define list-driven BACnet simulator verification contract"
```

---

### Task 2: Add Docker Compose topology spec with CI, lab, and multi-subnet profiles

**Files:**
- Create: `docker/simulator/docker-compose.yml`
- Create: `docs/simulator/README.md`
- Test: `docker/simulator/docker-compose.yml`

- [ ] **Step 1: Write the failing test**

```yaml
Expect compose topology to include:
- simulator devices
- scenario orchestrator
- test runner
- optional network impairment
- optional bbmd service
- separate profiles: ci, lab, multisubnet
```

- [ ] **Step 2: Run validation and confirm baseline fails before file exists**

Run: `docker compose -f docker/simulator/docker-compose.yml config`
Expected: Fails before file creation.

- [ ] **Step 3: Write minimal topology implementation**

```yaml
Define:
- ci_net bridge subnet with static service addresses
- lab_net macvlan for bench parity
- subnet_a/subnet_b for multisubnet tests with bbmd
- sim-device-{01..05}
- scenario-orchestrator
- test-runner
- netem sidecar (profile-gated)
```

- [ ] **Step 4: Verify topology parses**

Run: `docker compose -f docker/simulator/docker-compose.yml config >/tmp/simulator-compose.rendered.yaml`
Expected: Exit 0 and rendered compose output.

- [ ] **Step 5: Commit**

```bash
git add docker/simulator/docker-compose.yml docs/simulator/README.md
git commit -m "docs: add starter docker compose topology for bacnet simulator"
```

---

### Task 3: Define scenario matrix and CI gating rules

**Files:**
- Create/Modify: `docs/simulator/README.md`
- Modify: `README.md`
- Test: `docs/simulator/README.md`

- [ ] **Step 1: Write the failing test**

```markdown
Scenario matrix must include:
- happy path
- device timeout burst
- identity mismatch
- required-point missing
- CHW unavailable skip flow
```

- [ ] **Step 2: Run review to verify missing matrix initially**

Run: `rg "identity mismatch|timeout burst|required-point missing|CHW unavailable" docs/simulator/README.md`
Expected: Incomplete coverage before update.

- [ ] **Step 3: Write minimal implementation**

```markdown
Add "Scenario catalog" and "CI pass/fail rules":
- CI fails if any required list row unresolved
- CI fails on identity mismatch for strict mode
- CI allows configured known-unavailable rows only if explicitly marked
```

- [ ] **Step 4: Verify documentation includes gates**

Run: `rg "CI fails|required list row|strict mode|known-unavailable" docs/simulator/README.md README.md`
Expected: Gate conditions clearly present.

- [ ] **Step 5: Commit**

```bash
git add docs/simulator/README.md README.md
git commit -m "docs: add simulator scenario matrix and CI gates"
```

---

### Task 4: Add runbook for local lab execution and troubleshooting

**Files:**
- Modify: `docs/simulator/README.md`
- Test: `docs/simulator/README.md`

- [ ] **Step 1: Write the failing test**

```markdown
Runbook incomplete unless it includes:
- startup command by profile
- health check command
- log collection command
- common failure diagnostics
```

- [ ] **Step 2: Confirm missing runbook sections**

Run: `rg "docker compose|health|logs|troubleshooting" docs/simulator/README.md`
Expected: Missing some required runbook sections before update.

- [ ] **Step 3: Write minimal implementation**

```markdown
Add command snippets:
- docker compose up/down by profile
- device reachability checks
- per-service logs and rendered config output
- "why was device not found" troubleshooting checklist
```

- [ ] **Step 4: Verify runbook coverage**

Run: `rg "profile|reachability|not found|rendered config" docs/simulator/README.md`
Expected: Required runbook guidance present.

- [ ] **Step 5: Commit**

```bash
git add docs/simulator/README.md
git commit -m "docs: add bacnet simulator runbook and troubleshooting guide"
```

---

## Execution defaults (approved)

- Discovery mode: **list-first, verify-all** (attempt each imported row; no silent skips)
- Behavior fidelity: **generic BACnet**, vendor-neutral
- Initial CI networking: **bridge + static IPs**, then add `macvlan` and BBMD profiles
- Primary completion metric: every required imported device row is classified and reported

## Definition of done for simulator planning slice

- `docker/simulator/docker-compose.yml` exists and renders with `docker compose config`
- `docs/simulator/README.md` explains topology, list-driven verification, scenarios, and troubleshooting
- `docs/project.md` links to simulator plan/architecture and no longer treats simulator approach as vague TBD
- `README.md` points contributors to the simulator docs entrypoint
