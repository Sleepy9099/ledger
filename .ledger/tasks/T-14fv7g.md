---
id: T-14fv7g
title: Validate integrity bundle: closing-line vs open status, log-tamper at error tier, fail-closed shallow and tamper passes, hunk-aware diff parser
status: todo
priority: p1
size: s
created: 2026-09-02T11:44:57Z
tags: integrity
---

## Spec

### Defects (sweep 2026-09-02, orchestration #1, #9; correctness #12, #13, #14)

1. The documented header-conflict rule ("pick the value matching the latest Log event") can re-open a closed task: a Log with a `done:` line and `status: in_progress` validates clean. Add to `state-coherence`: a closing Log line (done / done(no-code) / drop) with an open status or a missing `closed` is an error; fix_hint names both resolutions (restore the closed header, or — if the close was wrong — this is a new task; closed is terminal).
2. `log-tamper` is a git-verified fact yet a warning: the documented post-merge ritual (`validate --coverage`, no --strict) exits 0 on a deleted Log line. Promote to error (VALIDATION_CODES, lockstep test, DESIGN §6, README).
3. `git_is_shallow` returns False on any git failure. Fall back to `.git/shallow` existence; if still unknown, refuse coverage with "cannot determine clone depth".
4. The log-tamper pass returns silently when git fails or when the tasks dir is not inside the repo (symlink/junction/subst): emit a `log-tamper` violation saying the check could not run.
5. `_tamper_violations` treats any content line starting `--- ` / `+++ ` as a file header: make the parser hunk-aware (headers only between `diff --git` and the first `@@`).
Tests for each.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T11:44:57Z [claude-2026-09-01-b] add: created: Validate integrity bundle: closing-line vs open status, log-tamper at error tier, fail-closed shallow and tamper passes, hunk-aware diff parser [p1/s] (tags: integrity)
