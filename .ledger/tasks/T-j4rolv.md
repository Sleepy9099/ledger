---
id: T-j4rolv
title: Release 1.6.0 and re-vendor into OSBF, REAI2, recurrent_moe_expert
status: in_progress
priority: p2
size: s
created: 2026-10-01T22:31:28Z
claimed_by: claude-2026-10-01-a
claimed_at: 2026-10-01T22:35:07Z
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
- [ ] Re-vendor recurrent_moe_expert
- [ ] Re-vendor REAI2
- [ ] Re-vendor OSBF

## Open Questions

## Commits

## Log

- 2026-10-01T22:31:28Z [claude-2026-10-01-a] add: created: Release 1.6.0 and re-vendor into OSBF, REAI2, recurrent_moe_expert [p2/s] (after: T-9jnibd) (tags: release)
- 2026-10-01T22:35:07Z [claude-2026-10-01-a] claim: claimed
- 2026-10-01T22:35:07Z [claude-2026-10-01-a] step: added 'Bump TOOL_VERSION + pyproject to 1.6.0'
- 2026-10-01T22:35:07Z [claude-2026-10-01-a] step: added 'Re-vendor recurrent_moe_expert'
- 2026-10-01T22:35:08Z [claude-2026-10-01-a] step: added 'Re-vendor REAI2'
- 2026-10-01T22:35:08Z [claude-2026-10-01-a] step: added 'Re-vendor OSBF'
- 2026-10-01T22:35:20Z [claude-2026-10-01-a] step: checked 'Bump TOOL_VERSION + pyproject to 1.6.0'
