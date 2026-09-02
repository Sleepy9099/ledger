---
id: T-j0ngsk
title: ledger status: one-screen orchestrator overview (evaluate against report)
status: todo
priority: p3
size: s
created: 2026-09-02T03:37:50Z
tags: orchestration, ergonomics
---

## Spec

### Motivation

An orchestrator tracking sub-agents today composes four read-only calls: `report --json` (workers, active/stranded claims, blockers, human questions), `list --claimed --json` (who holds what), `questions --human --json` (decision queue incl. blocked-on-human reasons) and `next --json` (why / stale_blocks / resources_held / held). Everything needed exists; what may be missing is one bounded screen.

### Design (only if the composition proves clumsy in a real wave)

`ledger status [--tag TAG] [--json]`: open tasks by status; claims grouped by actor with staleness; blocked tasks grouped by kind (human / task / external) with reasons; stale blocks; resources held; similar open pairs; human questions count. Derived on read, no writes, no new codes; reuse held_resources, blocked_reason, similar_tasks, compute_eligible. Record the evidence (which calls were scripted by hand, by whom) here before claiming — the same observe-first rule as the report itself.

### Alternative

Leave as is: `report`'s human output already reads as a status line and the JSON is one call.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T03:37:50Z [claude-2026-09-01-b] add: created: ledger status: one-screen orchestrator overview (evaluate against report) [p3/s] (tags: orchestration, ergonomics)
