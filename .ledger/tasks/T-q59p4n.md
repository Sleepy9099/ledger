---
id: T-q59p4n
title: Cross-process mutation lock
status: in_progress
priority: p1
size: m
created: 2026-08-28T11:54:59Z
claimed_by: claude-2026-08-28-a
claimed_at: 2026-08-28T12:04:31Z
tags: concurrency
---

## Spec

Serialize all state-changing commands (add, claim, next --claim, release, set, note, step, question, block, unblock, link, scan --write, done, drop) behind one ledger-wide cross-process lock so read->decide->write sequences cannot race between concurrent agent processes on the SAME checkout.

Motivation: two processes can both read a task as todo and both 'successfully' claim it; last writer wins silently. os.replace already prevents torn files - the missing property is serialization of DECISIONS made from shared state.

Design constraints:
- stdlib only: msvcrt.locking on Windows, fcntl.flock on POSIX, over a .ledger/.lock file; O_CREAT|O_EXCL lockfile fallback otherwise.
- Acquire BEFORE loading task state in every mutating command; bounded wait with a clear exit-2 refusal on timeout (code: lock-timeout).
- Read-only commands (list/show/next without --claim/questions/validate/scan without --write) stay lock-free.
- Cross-branch concurrency remains advisory-by-design (branches are the isolation model); this lock covers same-checkout multi-agent runs only.
- Update DESIGN.md 'atomically claims' wording to match reality, and add a stress regression test: N parallel 'next --claim' against one eligible task -> exactly one winner, all others get a truthful refusal or a different task.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T11:54:59Z [claude-2026-08-28-a] add: created: Cross-process mutation lock
- 2026-08-28T12:04:31Z [claude-2026-08-28-a] claim: claimed
