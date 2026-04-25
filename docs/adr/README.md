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
| [0006](0006-commissioning-report-modulation-samples.md) | Commissioning report: thermal modulation samples/batch + CSV export | Accepted |
| [0007](0007-chw-valve-stroke-prompt-confirm-cli.md) | CHW valve stroke (no CHW): `commissioning-confirm-prompt` + `record-step` gate | Accepted |
| [0008](0008-docker-bacnet-device-sim.md) | Docker BACnet/IP lab device (`bacnet-dev` profile + CI smoke) | Accepted |
| [0009](0009-implementation-stack-python-cli-v1.md) | V1 implementation stack: Python 3 CLI baseline; portable exe deferred | Accepted |
| [0010](0010-reporting-stack-libraries-v1.md) | Reporting libraries: stdlib CSV/HTML; openpyxl XLSX; fpdf2 PDF | Accepted |
| [0011](0011-site-controllers-spreadsheet-v1-contract.md) | `site-controllers` CSV v1 columns + unknown-column warnings | Accepted |
| [0012](0012-windows-single-exe-pyinstaller.md) | Windows single-file exe via PyInstaller; in-process import/simulator | Accepted |
| [0013](0013-airflow-tachometer-checkpoint-cli.md) | Airflow adjust + tachometer confirm CLIs and record-step gates | Accepted |
| [0014](0014-unified-commissioning-report-export-contract.md) | Unified commissioning CSV/HTML/XLSX/PDF column contract (v1) | Accepted |
| [0015](0015-bbmd-lab-cov-write-batch.md) | BBMD lab compose, sim SubscribeCOV, CLI batch writes | Accepted |
