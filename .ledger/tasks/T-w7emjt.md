---
id: T-w7emjt
title: Lock handle keyed per ledger directory; report tip search from the in-memory parent map
status: done
priority: p2
size: xs
created: 2026-09-02T11:44:58Z
closed: 2026-09-02T12:17:14Z
tags: concurrency, performance
---

## Spec

### Defects (sweep 2026-09-02, orchestration #10, correctness #7; verified)

`_LOCK_HANDLE` is process-global: an embedding host calling main() across two ledgers runs every later mutation unlocked (the second lock file is never created) and starves subprocess agents of the first. Key the handles by resolved ledger dir. `report`'s final-commit tip search runs one `merge-base --is-ancestor` per candidate pair (112 calls for a 20-commit wave): compute ancestry from the `Commit.parents` map already in memory (candidates outside the walk stay tips). Tests: two ledger dirs in one process both lock; tips computed without git calls (count them).

## Next Steps

## Open Questions

## Commits

- ece44c7 2026-09-02 Lock handles keyed per ledger directory; report tips from the parent map

## Log

- 2026-09-02T11:44:58Z [claude-2026-09-01-b] add: created: Lock handle keyed per ledger directory; report tip search from the in-memory parent map [p2/xs] (tags: concurrency, performance)
- 2026-09-02T12:11:42Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T12:17:14Z [claude-2026-09-01-b] link: ece44c7 Lock handles keyed per ledger directory; report tips from the parent map
- 2026-09-02T12:17:14Z [claude-2026-09-01-b] done: evidence: ece44c7
