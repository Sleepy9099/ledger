---
id: T-dv4vku
title: fix_hint audit: done-evidence reopen clause, xl-open size, why retrieve_with, indexed done hints, done-loose-ends validate hint, task-null reason, refused done reports links
status: done
priority: p2
size: xs
created: 2026-09-02T11:44:58Z
closed: 2026-09-02T12:22:43Z
tags: ergonomics
---

## Spec

### Findings (sweep 2026-09-02, ergonomics #5, #7, #8; orchestration #13; verified)

- done-evidence hint names a nonexistent `reopen`: "ledger link <id> <sha> (allowed on closed tasks)".
- xl-open hint leaves the task xl forever: add `--size l` to the split hint.
- `next`'s why truncation retrieve_with names `list`, which carries no `ineligible_because`: use `ledger next --full --json`.
- done's refusal hints interpolate the real `n` of the offending step/question.
- validate's `done-loose-ends` has no fix_hint: `step <id> check <n>` (append `-- MOOT:`), `question resolve`, or delete the line (prose is free-edit).
- `next` with `task: null` and `why: []` adds `reason`: "no tasks", "every task is closed", "every open task is ineligible — see why".
- A refused `done` that already linked commits reports `linked: [...]` in its data and the hint names `ledger unlink`.
Tests for each.

## Next Steps

## Open Questions

## Commits

- 09996e5 2026-09-02 fix_hint audit: real commands, real indexes, real retrieval

## Log

- 2026-09-02T11:44:58Z [claude-2026-09-01-b] add: created: fix_hint audit: done-evidence reopen clause, xl-open size, why retrieve_with, indexed done hints, done-loose-ends validate hint, task-null reason, refused done reports links [p2/xs] (tags: ergonomics)
- 2026-09-02T12:20:37Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T12:22:43Z [claude-2026-09-01-b] link: 09996e5 fix_hint audit: real commands, real indexes, real retrieval
- 2026-09-02T12:22:43Z [claude-2026-09-01-b] done: evidence: 09996e5
