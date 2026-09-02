---
id: T-lbnlok
title: sha-unreachable asks a machine-dependent question: check reachability from HEAD, not local object existence
status: done
priority: p1
size: s
created: 2026-09-02T08:54:43Z
closed: 2026-09-02T08:56:39Z
tags: integrity
---

## Spec

### Defect (heavy-session feedback 2026-09-02, #1; verified)

`validate` decides `sha-unreachable` with `git_sha_exists` = `git rev-parse --verify <sha>^{commit}`, i.e. "does the object exist locally". After a history rewrite the machine that rewrote it still resolves the old commits (reflog, `refs/original/*`), while every clone — and CI — does not. So the gate is green for the rewriter and red for everyone else. Reported: 42 (task, sha) pairs over 35 files after one `git filter-branch`, all resolving locally.

### Design

- One `git rev-list HEAD` into a set (a single subprocess, replacing one `rev-parse` per cited line); a `## Commits` sha is reachable iff some HEAD-reachable sha starts with it (7–40 hex). Pre-baseline commits are reachable and stay valid links.
- Use the same set in `report`'s final-commit candidates.
- `git_sha_exists` stays for `link`/`baseline` resolution (resolving a ref is a different question).
- Test: rewrite history (amend/filter) so the old sha survives only in the reflog; the old copy passed, the new one flags it in the same checkout; a clone agrees.

## Next Steps

## Open Questions

## Commits

- e16d343 2026-09-02 sha-unreachable asks HEAD reachability, not local object existence

## Log

- 2026-09-02T08:54:43Z [claude-2026-09-01-b] add: created: sha-unreachable asks a machine-dependent question: check reachability from HEAD, not local object existence [p1/s] (tags: integrity)
- 2026-09-02T08:54:44Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T08:56:39Z [claude-2026-09-01-b] link: e16d343 sha-unreachable asks HEAD reachability, not local object existence
- 2026-09-02T08:56:39Z [claude-2026-09-01-b] done: evidence: e16d343
