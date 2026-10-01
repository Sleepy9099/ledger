---
id: T-sl1bow
title: ledger-ui: Projects, Overview, Work + inspector, Human Inbox, Validation
status: todo
priority: p1
size: l
created: 2026-10-01T22:31:29Z
depends_on: T-z76xh6
tags: ui
---

## Spec

### Intent

The v1 screens of the read-only review UI (see the scaffold task for architecture and decisions). Every figure comes from existing CLI JSON: `doctor`, `list`, `show`, `questions --human`, `report`, `next` (without `--claim`), `validate --coverage`.

### Screens

- Projects: one card per registered project / checkout — health (doctor compatibility, version), open / active / blocked / HUMAN counts, attention badge.
- Overview (per checkout): "needs attention" first — HUMAN questions (with how many tasks wait on them), tasks blocked on human, stale claims, stale blocks (from `next`), compatibility warnings; then active work grouped by actor, next eligible tasks, recent closes.
- Work: filterable/sortable task table (status, priority, size, tag, owner, resource, blocked-on, text search); a right-hand inspector (no navigation away) rendering `show`: header summary, Spec as Markdown, Next Steps checklist (read-only), Open Questions with answers, Commits, dependencies/dependents as links, Log as a timeline.
- Human Inbox: every open HUMAN question across the checkout with its context lines (options / recommendation), tasks blocked on human; a copyable `answers apply` command — no writes.
- Validation: run on demand; group rows by code with severity, message and fix_hint rendered verbatim (the UI never invents recovery logic).

### Look

Dark/light aware, dense but calm; status/priority colour coding consistent across screens; keyboard search (Ctrl+K) to jump to a task.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-10-01T22:31:29Z [claude-2026-10-01-a] add: created: ledger-ui: Projects, Overview, Work + inspector, Human Inbox, Validation [p1/l] (after: T-z76xh6) (tags: ui)
