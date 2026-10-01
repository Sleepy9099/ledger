---
id: T-sketg4
title: ledger-ui: full dependency graph with load-more
status: done
priority: p2
size: m
created: 2026-10-01T22:31:29Z
closed: 2026-10-01T22:54:35Z
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

- ea4fb61 2026-10-01 Add ledger-ui: a read-only review UI for any number of ledgers

## Log

- 2026-10-01T22:31:29Z [claude-2026-10-01-a] add: created: ledger-ui: full dependency graph with load-more [p2/m] (after: T-sl1bow) (tags: ui)
- 2026-10-01T22:54:12Z [claude-2026-10-01-a] claim: claimed
- 2026-10-01T22:54:24Z [claude-2026-10-01-a] note: Real shapes: OSBF open scope = 153 nodes / 293 edges / 23 layers (hubs with out-degree 15-17); REAI2 = 93 nodes / 43 edges / 4 layers. Longest-path layering piled sources into column 0 with long edges; sources now sit one column left of their earliest dependent.
- 2026-10-01T22:54:35Z [claude-2026-10-01-a] link: ea4fb61 Add ledger-ui: a read-only review UI for any number of ledgers
- 2026-10-01T22:54:35Z [claude-2026-10-01-a] done: evidence: ea4fb61
