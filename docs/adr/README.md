# Architecture Decision Records (ADRs)

Use when a choice is **non-obvious** or you will forget **why** you chose it.

## How to add one

1. Copy `template.md` to `NNNN-short-title-in-kebab-case.md` (next number after the highest in this folder).
2. Fill **Context**, **Decision**, **Consequences**. Keep it short; future you reads this under time pressure.
3. Commit with the code that implements or reflects the decision when possible.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-simulator-verification-cli-stack.md) | Simulator verifier implementation stack (Python 3 CLI baseline) | Accepted |
| [0002](0002-list-schema-and-identity-contract.md) | Controller list schema and identity verification contract | Accepted |
| [0003](0003-ci-gating-policy-for-list-verification.md) | CI strict/non-strict gating policy for row classifications | Accepted |
| [0004](0004-bacpypes3-for-writeproperty.md) | BACpypes3 for WriteProperty; minimal UDP for smoke probes | Accepted |
| [0005](0005-commissioning-bacnet-adapter-facade.md) | `CommissioningBACnetAdapter` façade over B/IP probe + BACpypes3 client | Accepted |
