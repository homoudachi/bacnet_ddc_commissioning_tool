# bacnet_ddc_commissioning_tool

## Documentation

- **Current repo status (2026-04-21):** docs-first project with early runnable tooling (simulator verifier/orchestrator and import compiler). There is no full end-user commissioning application yet.
- **[Living project doc](docs/project.md)** — product requirements, commissioning flows, examples, import direction, and reports (update as the product evolves).
- **[ADRs](docs/adr/)** — short decision records when choices are non-obvious.
- **[Slice plans](docs/plans/)** — time-boxed implementation plans; archive or remove when the slice ships.

## Planning next steps

- Start with the active foundation plan: **[docs/plans/2026-04-21-v1-foundation-plan.md](docs/plans/2026-04-21-v1-foundation-plan.md)**.
- Track cross-cutting decisions in **[Remaining to plan (before implementation)](docs/project.md#remaining-to-plan-before-implementation)** and **[Open questions](docs/project.md#open-questions)**.
- For BACnet simulation architecture and networking, use **[docs/simulator/README.md](docs/simulator/README.md)** and **[docs/plans/2026-04-21-bacnet-simulator-plan.md](docs/plans/2026-04-21-bacnet-simulator-plan.md)**.

## Current implementation slice

- List-first verification CLI: **[tools/simulator/list_verifier.py](tools/simulator/list_verifier.py)**
- Initial tests: **[tests/test_list_verifier.py](tests/test_list_verifier.py)**
- ADR lock-ins: **[docs/adr/](docs/adr/)** (0001-0003)
- Import compiler CLI: **[tools/import/compile_job.py](tools/import/compile_job.py)**
- Import compiler tests: **[tests/test_import_compiler.py](tests/test_import_compiler.py)**
