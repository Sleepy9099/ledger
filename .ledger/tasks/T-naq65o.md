---
id: T-naq65o
title: done: warn when depends_on still lists open tasks
status: done
priority: p2
size: xs
created: 2026-09-01T23:48:39Z
closed: 2026-09-02T01:25:32Z
tags: orchestration, coherence
---

## Spec

### Motivation (review §13, §26)

A wave close should mean every selected member is done, dropped or explicitly deferred. `cmd_done` never reads `depends_on`: its refusals are `done-evidence` and `done-human-questions`, its warnings unchecked steps and unanswered questions; `validate_offline`'s depends_on checks are unknown-ref and cycles only. Verified 2026-09-01: a task was closed with `--commit HEAD` (and separately with `--no-code`) while one dependency was `in_progress` and another `todo` — exit 0, no warning, `validate --strict` silent. `cmd_drop` already warns in the REVERSE direction (dropping a prerequisite warns its open dependents with a `set --remove-depends` fix_hint); this adds the symmetric warning so the two closing verbs treat the DAG consistently. For an ordinary task, closing over open prerequisites is the same coherence smell as closing with unchecked steps, which `done` already warns about. See T-9iu47b for the convention this protects.

### Design (option a, recommended)

In `cmd_done`, alongside the existing loose-ends warnings, call `load_all_tasks(ctx)` once (as `cmd_drop` does, under the mutation lock already held) and compute the dependencies whose status is not `done`. If non-empty, append `err("done-loose-ends", f"{n} depends_on task(s) still open: {details}", task=task.id, severity="warning", fix_hint="close or drop them first, or ledger set <id> --remove-depends <dep> if the dependency no longer holds")`, building `details` like compute_eligible's why (`T-x (in_progress)`) so the orchestrator sees which members are in_progress / todo / blocked. Reusing `done-loose-ends` means no VALIDATION_CODES change (the lockstep test is untouched). CLI-time only; deliberately NOT added to `validate`, so upgrading ledger.py can never turn `--strict` CI red on existing history. Warnings never change the exit code. `blocked` members still warn (OPEN_STATUSES includes blocked; the ledger has no deferred state, and `next` treats blocked as ineligible). Docs: DESIGN §5 `done` bullet gains "or still-open depends_on"; §6 notes the check is CLI-time only.

### Open decisions (Open Questions)

Warn (a) / refuse with `--force` override (b — must then also update PROTOCOL_TEXT "it refuses without commit evidence or with unanswered HUMAN questions", DESIGN §5, README, the `--force` help text, and add a decision-record entry) / silent (c). Dropped deps: ALIGN with `next` and `drop` (a dropped dep is unmet; a still-listed dropped dep warns with cmd_drop's own `--remove-depends` hint — one reading of depends_on tool-wide, recommended) or exclude dropped (then DESIGN §8 must say "satisfied by done for scheduling, by done-or-dropped for closing coherence").

### DESIGN.md principles

Reads other files, writes only the closing task; no new fields; ~12 lines; no daemons; one `done:` Log line as today. DESIGN §8's parent-depends_on-peers pattern gains visibility for its one blind spot without any epic/wave object (§11 unchanged). No cache (T-8jrndl is the roadmap home for read cost).

### Backward compatibility

Older vendored copies do not warn; no CLAUDE.md/PROTOCOL text change under (a).

### Tests (tests/test_cli.py, self-contained)

W --after A --after B --after C; claim A; drop C; `done W --no-code "x"` → exactly one `done-loose-ends` whose message contains "depends_on" and names A and B (and C per the dropped-dep answer); assertions match on message text because the code is shared with the steps/questions warnings. `done A`, then W2 --after A → no depends_on warning. The `--commit` path warns identically. Under (b): a `--force` override case and refuse-then-close-members-then-succeed.

## Next Steps

- [x] Human answers warn/refuse and the dropped-dep question; unblock
- [x] cmd_done: load_all_tasks once, append the done-loose-ends warning with per-dep status details
- [x] DESIGN §5 done bullet and §6 note; self-contained test in tests/test_cli.py

## Open Questions

- [x] HUMAN: When `done` closes a task whose depends_on still names open tasks: (a) emit a `done-loose-ends` warning naming them and still close (recommended — mirrors the unchecked-steps warning, exit code unchanged, zero CI impact), (b) refuse with exit 2 unless --force (changes `done` semantics tool-wide: PROTOCOL_TEXT, DESIGN §5, README, --force help, decision record), or (c) stay silent? And should a still-listed DROPPED dependency warn (ALIGN with next/drop, which treat a dropped dep as unmet and ask for --remove-depends — recommended) or count as satisfied (then DESIGN §8 must state the two readings)? -- ANSWERED (2026-09-02): (a) emit a done-loose-ends warning naming the still-open dependencies and close anyway; a still-listed DROPPED dependency counts as unmet (align with next and drop). Operator criteria: warnings never block autonomy, and one reading of depends_on tool-wide is easier to maintain than two.

## Commits

- abe2399 2026-09-01 done warns when depends_on still lists open tasks

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: done: warn when depends_on still lists open tasks
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'Human answers warn/refuse and the dropped-dep question; unblock'
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'cmd_done: load_all_tasks once, append the done-loose-ends warning with per-dep status details'
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'DESIGN §5 done bullet and §6 note; self-contained test in tests/test_cli.py'
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] question: added (HUMAN): When `done` closes a task whose depends_on still names open tasks: (a) emit a `done-loose-ends` warning naming them and still close (recommended — mirrors the unchecked-steps warning, exit code unchanged, zero CI impact), (b) refuse with exit 2 unless --force (changes `done` semantics tool-wide: PROTOCOL_TEXT, DESIGN §5, README, --force help, decision record), or (c) stay silent? And should a still-listed DROPPED dependency warn (ALIGN with next/drop, which treat a dropped dep as unmet and ask for --remove-depends — recommended) or count as satisfied (then DESIGN §8 must state the two readings)?
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
- 2026-09-02T00:54:55Z [claude-2026-09-01-b] answer: 'HUMAN: When `done` closes a task whose depends_on still names open tasks: (a) emit a `done-loose-ends` warning naming them and still close (recommended — mirrors the unchecked-steps warning, exit code unchanged, zero CI impact), (b) refuse with exit 2 unless --force (changes `done` semantics tool-wide: PROTOCOL_TEXT, DESIGN §5, README, --force help, decision record), or (c) stay silent? And should a still-listed DROPPED dependency warn (ALIGN with next/drop, which treat a dropped dep as unmet and ask for --remove-depends — recommended) or count as satisfied (then DESIGN §8 must state the two readings)?' -> (a) emit a done-loose-ends warning naming the still-open dependencies and close anyway; a still-listed DROPPED dependency counts as unmet (align with next and drop). Operator criteria: warnings never block autonomy, and one reading of depends_on tool-wide is easier to maintain than two.
- 2026-09-02T00:54:56Z [claude-2026-09-01-b] unblock: -> todo
- 2026-09-02T01:20:47Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T01:20:47Z [claude-2026-09-01-b] step: checked 'Human answers warn/refuse and the dropped-dep question; unblock'
- 2026-09-02T01:25:19Z [claude-2026-09-01-b] step: checked 'cmd_done: load_all_tasks once, append the done-loose-ends warning with per-dep status details'
- 2026-09-02T01:25:19Z [claude-2026-09-01-b] step: checked 'DESIGN §5 done bullet and §6 note; self-contained test in tests/test_cli.py'
- 2026-09-02T01:25:32Z [claude-2026-09-01-b] link: abe2399 done warns when depends_on still lists open tasks
- 2026-09-02T01:25:32Z [claude-2026-09-01-b] done: evidence: abe2399
