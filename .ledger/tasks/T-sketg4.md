---
id: T-sketg4
title: ledger-ui: full dependency graph with load-more
status: todo
priority: p2
size: m
created: 2026-10-01T22:31:29Z
depends_on: T-sl1bow
tags: ui
---

## Spec

### Intent

Dependency graph view in the review UI. The human wants the FULL graph (or at least a "load more"), not just a neighbourhood: OSBF has ~120 open tasks and REAI2 1,132 total.

### Design

- Edges from `list --json` `depends_on` (all statuses), so no extra subprocess calls.
- Default scope: all open tasks plus the closed tasks they directly depend on; "load more" widens by one dependency layer of closed tasks at a time, and "show everything" renders the whole corpus.
- Layered (left-to-right, dependencies first) layout computed in Python, rendered with ECharts graph via NiceGUI so pan/zoom/drag work at 1,000+ nodes.
- Node colour = status, size = task size, border = priority; HUMAN-blocked and stale-claim nodes flagged. Clicking a node opens the same inspector as the Work view; a focus mode dims everything outside a node's ancestors/descendants.
- Isolated tasks (no edges) are grouped separately so they don't swamp the layout.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-10-01T22:31:29Z [claude-2026-10-01-a] add: created: ledger-ui: full dependency graph with load-more [p2/m] (after: T-sl1bow) (tags: ui)
