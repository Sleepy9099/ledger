---
id: T-j4rolv
title: Release 1.6.0 and re-vendor into OSBF, REAI2, recurrent_moe_expert
status: done
priority: p2
size: s
created: 2026-10-01T22:31:28Z
closed: 2026-10-01T22:37:00Z
depends_on: T-9jnibd
tags: release
---

## Spec

### Intent

Release 1.6.0 (the `ledger log` command) and re-vendor it into the human's three active projects, which all run 1.5.0 today:

- C:\Users\lorda\OneDrive\Desktop\SRC\OSBF (491 tasks; main checkout sits on a feature branch, plus worktrees)
- C:\Users\lorda\OneDrive\Desktop\SRC\REAI2 (1,132 tasks)
- C:\Users\lorda\OneDrive\Desktop\SRC\recurrent_moe_expert (141 tasks)

The human asked for this to be done by the agent (2026-10-01).

### Per repo

- Inspect `git status` / current branch first; do not sweep unrelated changes into the commit.
- Copy `.ledger/ledger.py`; PROTOCOL_VERSION is unchanged so `init` is not needed, but run `doctor --json` and `validate --coverage` after.
- Commit with `Ledger-Exempt: re-vendor ledger.py`, one commit per repo.

## Next Steps

- [x] Bump TOOL_VERSION + pyproject to 1.6.0
- [x] Re-vendor recurrent_moe_expert
- [x] Re-vendor REAI2
- [x] Re-vendor OSBF

## Open Questions

## Commits

- fbe399a 2026-10-01 Release 1.6.0: ledger log; record closure of T-9jnibd

## Log

- 2026-10-01T22:31:28Z [claude-2026-10-01-a] add: created: Release 1.6.0 and re-vendor into OSBF, REAI2, recurrent_moe_expert [p2/s] (after: T-9jnibd) (tags: release)
- 2026-10-01T22:35:07Z [claude-2026-10-01-a] claim: claimed
- 2026-10-01T22:35:07Z [claude-2026-10-01-a] step: added 'Bump TOOL_VERSION + pyproject to 1.6.0'
- 2026-10-01T22:35:07Z [claude-2026-10-01-a] step: added 'Re-vendor recurrent_moe_expert'
- 2026-10-01T22:35:08Z [claude-2026-10-01-a] step: added 'Re-vendor REAI2'
- 2026-10-01T22:35:08Z [claude-2026-10-01-a] step: added 'Re-vendor OSBF'
- 2026-10-01T22:35:20Z [claude-2026-10-01-a] step: checked 'Bump TOOL_VERSION + pyproject to 1.6.0'
- 2026-10-01T22:36:59Z [claude-2026-10-01-a] step: checked 'Re-vendor recurrent_moe_expert'
- 2026-10-01T22:36:59Z [claude-2026-10-01-a] step: checked 'Re-vendor REAI2'
- 2026-10-01T22:36:59Z [claude-2026-10-01-a] step: checked 'Re-vendor OSBF'
- 2026-10-01T22:36:59Z [claude-2026-10-01-a] note: Re-vendored via each repo's own ledger (policy treats ledger.py as code, so a task + trailer, not Ledger-Exempt): recurrent_moe_expert main ddaef2b/T-h7pzjp, REAI2 main 0ccd75fb/T-0acdmf (path-limited commit; the tree had unrelated in-flight agent changes, untouched), OSBF branch claude/agent-orchestrator-ledger-nwxedp 5971b3bc/T-zbonvx (the checked-out line; main is 997 commits behind). validate --coverage --strict green on all three; nothing pushed.
- 2026-10-01T22:36:59Z [claude-2026-10-01-a] link: fbe399a Release 1.6.0: ledger log; record closure of T-9jnibd
- 2026-10-01T22:37:00Z [claude-2026-10-01-a] done: evidence: fbe399a
- 2026-10-01T22:54:24Z [claude-2026-10-01-a] note: Landmine: REAI2 carries test_the_vendored_ledger_matches_upstream, which compares its .ledger/ledger.py byte-for-byte with TaskManager's working copy. Editing TaskManager's ledger.py turns REAI2's suite red until it is re-vendored (an REAI2 agent filed and dropped T-67asy0 for exactly that while 1.6.0 was mid-edit).
