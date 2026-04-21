# Project (living doc)

Audience: you, after a break. Update this when behavior, setup, or intent changes—ideally in the same commit as the code.

## Goal

One sentence: what this project does and who it is for.

## Non-goals (this phase)

What you are **not** building right now. Stops scope creep and silent expansion.

_(List explicit non-goals here.)_

## How to run

```bash
# fill in when you have commands
```

## How to verify

```bash
# tests, lint, or manual checks you actually run before merging
```

## Layout (10 lines max)

| Path | Purpose |
|------|---------|
| `src/` or app root | _describe when it exists_ |
| `docs/project.md` | This file |
| `docs/adr/` | Decision records (why, not how) |
| `docs/plans/` | Time-boxed slice plans; archive or delete when done |

## Architecture (short)

A few sentences: main pieces, data flow, external dependencies. Tests complement this; they do not replace “what we are building.”

## Definition of done (reuse every change)

- [ ] Behavior matches intent for this slice
- [ ] Verification command(s) above pass (or note why N/A)
- [ ] This file or an ADR updated if setup, behavior, or constraints changed
- [ ] Commit message states what changed

## Open questions

_(Track unresolved decisions; promote to ADR when you choose.)_
