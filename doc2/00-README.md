# doc2 — Implementation Plans

`docs/` is the **submission deliverable** (architecture, schema, plan, decisions, ai-prompts) and is
graded. It stays as-is and is only updated at the end of each session with what actually happened.

`doc2/` is the **working plan** — the hyper-detailed spec I build from. Nothing here is a
deliverable; it is the blueprint that makes `docs/` easy to write honestly at the end.

## Read in this order

| # | File | What it settles |
|---|------|-----------------|
| 01 | [current-state-audit.md](01-current-state-audit.md) | Exactly what exists today, what is dead code, and the 11 defects already in the tree |
| 02 | [domain-model.md](02-domain-model.md) | Entities, invariants, the invoice state machine, and every ambiguity in the brief ruled on |
| 03 | [database-schema.md](03-database-schema.md) | Field-by-field DDL, constraints, indexes, triggers, migration order |
| 04 | [authorization-matrix.md](04-authorization-matrix.md) | Role × action matrix, the RLS policy rewrite, how RLS and DRF permissions divide labour |
| 05 | [api-contract.md](05-api-contract.md) | Every endpoint: method, body, response, every error code and message |
| 06 | [backend-build-plan.md](06-backend-build-plan.md) | File-by-file build order with acceptance criteria per step |
| 07 | [frontend-build-plan.md](07-frontend-build-plan.md) | Routes, components, state, the exact screens for each of the 10 goals |
| 08 | [testing-plan.md](08-testing-plan.md) | Test matrix mapped to the 10 goals; what must be Postgres-backed |
| 09 | [seed-data-plan.md](09-seed-data-plan.md) | The demo dataset, designed so every screen has something to show |
| 10 | [deployment-plan.md](10-deployment-plan.md) | Hosting, env vars, deploy order, cold-start note |
| 11 | [git-and-sessions.md](11-git-and-sessions.md) | Commit strategy and the 12-hour session schedule |
| 12 | [docs-deliverables.md](12-docs-deliverables.md) | How each of the five graded docs gets filled, and from what |
| 13 | [risks-and-decisions.md](13-risks-and-decisions.md) | Open questions, risk register, decisions queued for `docs/decisions.md` |
| 14 | [backend-code-scaffolds.md](14-backend-code-scaffolds.md) | Skeletons for errors, querysets, filters, serializers, services, views, urls, settings |
| 15 | [frontend-code-scaffolds.md](15-frontend-code-scaffolds.md) | API client, auth context, the hooks, route table, theme tokens |
| 16 | [reference.md](16-reference.md) | Dependencies, env vars, commands, endpoint index, and the ruling/defect/invariant indexes |

## Conventions used throughout

- **`[NEW]` / `[MODIFY]` / `[DELETE]`** prefix every file reference in a build step.
- **Goal N** always refers to the numbered requirement in the root `README.md`.
- **AM** = account manager, **BA** = billing admin.
- **Money** is always `Decimal` / `NUMERIC(12,2)`. A float in a money path is a bug, full stop.
- **Dates** are `DATE` (no time) for billing periods and due dates; **timestamps** are `TIMESTAMPTZ`
  in UTC. `TIME_ZONE = "UTC"`, `USE_TZ = True` is already set and stays set.
- **"Today"** in business logic is always `django.utils.timezone.localdate()` — never
  `datetime.date.today()`, which ignores the configured timezone.

## The one-line summary of the whole plan

Auth (Goal 1) is built. Everything else is one new Django app, `src.billing`, whose entire
correctness story is: *a small set of invariants, enforced three times — in the service layer with
readable errors, in the database with constraints and triggers, and in RLS for row visibility.*
The frontend is a thin client over that API; it never re-implements a rule.
