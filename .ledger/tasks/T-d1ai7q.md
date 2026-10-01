---
id: T-d1ai7q
title: ledger-ui: Activity timeline on ledger log
status: done
priority: p2
size: s
created: 2026-10-01T22:31:29Z
closed: 2026-10-01T22:54:36Z
depends_on: T-sl1bow, T-9jnibd
tags: ui
---

## Spec

### Intent

Activity timeline in the review UI, built on the 1.6.0 `ledger log --json` command (one subprocess call for the whole corpus). Hidden, with an explanatory note, on checkouts whose vendored copy is older than 1.6.0.

### Design

- Day-grouped timeline, newest first: actor, verb (claim / done / note(dead-end) / block / release / question ...), task link, text.
- Filters: actor (OSBF has 100+ worker ids, so a searchable select plus a prefix grouping like `w-*`), verb, task, tag, time window.
- Paged with `-n` and a "load more" that widens the window; clicking a task opens the shared inspector.

## Next Steps

## Open Questions

## Commits

- ea4fb61 2026-10-01 Add ledger-ui: a read-only review UI for any number of ledgers

## Log

- 2026-10-01T22:31:29Z [claude-2026-10-01-a] add: created: ledger-ui: Activity timeline on ledger log [p2/s] (after: T-sl1bow, T-9jnibd) (tags: ui)
- 2026-10-01T22:54:12Z [claude-2026-10-01-a] claim: claimed
- 2026-10-01T22:54:36Z [claude-2026-10-01-a] link: ea4fb61 Add ledger-ui: a read-only review UI for any number of ledgers
- 2026-10-01T22:54:36Z [claude-2026-10-01-a] done: evidence: ea4fb61
