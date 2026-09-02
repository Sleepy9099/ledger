---
id: T-841lcp
title: Hard context budgets: bound every digest family and next's why with truncation metadata
status: in_progress
priority: p1
size: s
created: 2026-09-02T04:51:26Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T04:56:44Z
tags: context, ergonomics
---

## Spec

### Defect (review 2026-09-02, finding 2)

task_digest caps only recent_log; steps_open, human_gated_questions, dead_ends, commits, dependents are unbounded, and cmd_next's `why` (plus blocked_on_human, stale_blocks, held) carries one row per skipped open task — the mandatory session-start payload scales with backlog size.

### Design

- One helper `bounded(rows, limit, retrieve_with)` returning the capped rows and a truncation record; one payload-level key `truncated: {field: {total, omitted, retrieve_with}}` present only when something was cut (uniform contract, additive JSON).
- Limits as code constants (DIGEST_LIMITS): steps_open 25, human_gated_questions 10, dead_ends 10, commits 10, dependents 20, recent_log (`--last`); next: why 30, blocked_on_human 20, stale_blocks 20, held 20. Ordering before the cut is the existing sort (priority first), so the omitted rows are the least urgent.
- retrieve_with strings: `ledger show <id> --json` (digest families), `ledger list --status todo --json` / `ledger questions --human --json` (next lists), `ledger brief <id> --last N`.
- `next --full` and `show` stay unbounded (explicit "everything" commands). Human output prints `(+N more: <retrieve_with>)`.
- Docs: DESIGN §5 next/brief bullets; README brief row. Tests: each family truncates with correct total/omitted; no `truncated` key when nothing is cut; the why cap keeps priority order; --full unbounded.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T04:51:26Z [claude-2026-09-01-b] add: created: Hard context budgets: bound every digest family and next's why with truncation metadata [p1/s] (tags: context, ergonomics)
- 2026-09-02T04:56:44Z [claude-2026-09-01-b] claim: claimed
