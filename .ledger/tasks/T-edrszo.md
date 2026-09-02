---
id: T-edrszo
title: Docs and test drift from the 2026-09-02 sweep
status: in_progress
priority: p3
size: xs
created: 2026-09-02T11:44:59Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T12:29:00Z
tags: docs
---

## Spec

### Findings (docs review, all verified by quote)

DESIGN §5 says brief's dead ends are "uncapped" (they are capped at 10 — the §5 budgets paragraph and README are right); DESIGN §6 omits `resource-contention`; the §1 config example omits `protocol_adapters`; decision #11's bookkeeping set omits `.lock`; README "Daily commands" omits `set --add-tag/--remove-tag`, `done --no-code/--force`, `drop --force`, `claim/release/unblock --force`, `--no-git` on show/brief/next; `claim-held` and ~20 CLI-only codes appear in no doc (covered by the refusal-code table in the protocol task). Tests missing: `scan --since`, `no-such-question`, `no-git` (link/unlink/scan on the plain fixture), `bad-row`, multi-sha `link`/`unlink`, `answers apply`'s own corrupt-file branch. Fix all; keep the untested-surface table in this task's Log for the next sweep.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T11:44:59Z [claude-2026-09-01-b] add: created: Docs and test drift from the 2026-09-02 sweep [p3/xs] (tags: docs)
- 2026-09-02T12:29:00Z [claude-2026-09-01-b] claim: claimed
