---
id: T-ledxp4
title: Closed is terminal: done refuses every strict-CI-failing state; post-close mutations limited to an allowlist
status: in_progress
priority: p1
size: s
created: 2026-09-02T04:51:26Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T04:51:27Z
tags: lifecycle, integrity
---

## Spec

### Defect (review 2026-09-02, finding 3; verified against the code)

`set`, `step add/uncheck`, `question add` succeed on a done/dropped task (no status gate in cmd_set / cmd_step / cmd_question), and `done` closes with unchecked steps or unanswered normal questions as a WARNING, and with unanswered HUMAN questions under `--force` — yet `validate --strict` promotes `done-loose-ends` and always errors on `done-human-questions`. Lifecycle contradiction: close, mutate, strict CI rejects, repair needs more post-close mutation.

### Design

- `done` REFUSES (exit 2) every state strict CI would reject: no evidence (unchanged), unanswered HUMAN questions (no --force bypass any more), unchecked steps and unanswered normal questions (new refusal, same `done-loose-ends` code at error severity; fix_hint: check them with `step check`, mark moot with the `-- MOOT: reason` suffix, or delete the stale line; answer questions with `question resolve`). `--force` keeps overriding ONLY the foreign-fresh-claim guard. Still-open depends_on stays a warning (operator decision 2026-09-01; validate never checks it).
- Post-close allowlist: `note`, `link`, `step check`, `question resolve` (append-only or repair-only). `set`, `step add`, `step uncheck`, `question add`, `block`, `claim`, `release`, `unblock` refuse on done/dropped with `bad-state` and fix_hint "closed is terminal — a regression or redo is a new task (search first)".
- validate keeps `done-loose-ends` as a warning (hand edits / merges can still create it); repair = the allowlisted verbs or a prose edit.
- PROTOCOL_TEXT "Finishing a task" sentence updated (protocol 12; regenerate; stay under the size pin); DESIGN §5 done bullet and decision #12; README done row.
- Tests: refusals for each gate with fix_hints; allowlist verbs succeed after close; every refused verb leaves the file byte-identical; property op_done no longer uses --force; the strict-promotion fixture builds its loose-ends state by hand edit.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T04:51:26Z [claude-2026-09-01-b] add: created: Closed is terminal: done refuses every strict-CI-failing state; post-close mutations limited to an allowlist [p1/s] (tags: lifecycle, integrity)
- 2026-09-02T04:51:27Z [claude-2026-09-01-b] claim: claimed
