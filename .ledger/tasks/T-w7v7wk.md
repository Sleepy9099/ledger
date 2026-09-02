---
id: T-w7v7wk
title: report: replay state at the window end instead of reading current headers
status: todo
priority: p1
size: m
created: 2026-09-02T04:51:26Z
tags: orchestration
---

## Spec

### Defect (review 2026-09-02, finding 1; verified)

cmd_report filters EVENTS by the window but derives human_open_end, active_claims and stranded_claims from CURRENT headers/questions, so a report for an earlier cutoff shows today's state. Also `questions.answered` counts every answer next to human-specific siblings, and `final_commit` picks the first of several incomparable tips as if unique.

### Design

- Replay per task through `until`: claim/release/done/drop Log lines rebuild claimed_by/claimed_at/status at the cutoff (claim sets the holder; release/done/drop clear it; `block` retains; `unblock` no change); questions: `question` lines with `(HUMAN)` open a human question, `answer` lines whose text starts with `'HUMAN: ` close one — human_open_end = opened − answered through `until` (a HUMAN question edited by hand into prose is a lower bound: say so in `sources`). Staleness at the cutoff uses the replayed last activity <= until.
- Fields: `questions.answered` splits into `human_answered` and `answered_total`; `final_commit` only when exactly one tip survives, else null plus `final_commit_candidates`.
- No window → replay collapses to current state (keep the fast path). Tests: the review's reproduction (open HUMAN question + active claim at the cutoff, answered and released later → report --until cutoff shows human_open_end 1 and the claim active); a takeover chain; two incomparable tips → candidates.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T04:51:26Z [claude-2026-09-01-b] add: created: report: replay state at the window end instead of reading current headers [p1/m] (tags: orchestration)
