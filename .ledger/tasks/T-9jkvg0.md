---
id: T-9jkvg0
title: Signal blocks whose blocked_on task has closed
status: todo
priority: p3
size: s
created: 2026-09-01T23:48:40Z
tags: ontology, coherence
---

## Spec

### Motivation (review §5)

The review's ontology separates "must happen before → dependency" from "cannot proceed → block". In this tool the two have asymmetric lifecycles: depends_on is re-evaluated on every `next` (`compute_eligible`), whereas a `block --on <task-id>` is cleared only by a manual command — `unblock`, a plain `release`, or closing the blocked task itself — none of which is triggered when the TARGET closes. `compute_eligible` reports only `blocked_on T-x`; validate's refs check verifies grammar, self-reference and existence but never the target's status; `done` scans nothing; only `drop` scans dependents (by depends_on, not blocked_on); and blocked tasks are never stale-takeover candidates (the blocked branch returns before the stale check). A task-targeted block is therefore a silent dead end after the target ships — an ontology arrow with no completion signal. PROTOCOL_TEXT mentions only `block --on human`; README says `unblock reverses`.

### Design (read-side only)

- `compute_eligible`: when `blocked_on` names a task present in `by_id` (`human` / `external:` values can never collide) whose status is done/dropped, the why text becomes `blocked_on T-x (done — ledger unblock <id>)` or `blocked_on T-x (dropped — it will never close; ledger unblock <id>, then block --on the real reason)` (mirrors the existing self-reference refs hint); the `blocked_on T-x` prefix is preserved so existing substring assertions keep passing. The function returns a fourth value `stale_blocks: [{id, blocked_on, target_status}]` (sole caller cmd_next; no test imports it), emitted beside `blocked_on_human` in BOTH `next` envelopes. Note `why` is emitted unconditionally in code although DESIGN §5 says "when nothing is eligible" — fix that sentence.
- `cmd_done` and `cmd_drop`: after the close, a read-only `load_all_tasks` pass (as drop does today, under the lock already held) emits warning-severity `refs` entries for every OPEN task whose blocked_on equals the closed id, fix_hint `ledger unblock <that-id>` (unblock restores in_progress when a claim was retained via `block`, todo otherwise); `ok` stays true.
- Deliberately NOT done: no auto-unblock (it would write a second file per command, and the block's `--why` may name a reason beyond the target finishing); no validate code — a new warning is promoted by `--strict` and, being repairable by one `unblock`, is not forbidden by the design, but it changes CI behaviour and deserves its own task if wanted. Docs: DESIGN §5 `next` and `done` bullets; README `unblock reverses` gains "done/drop/next warn when the target task has closed"; PROTOCOL_TEXT unchanged (no new global rule).

### DESIGN.md principles

Read-only scans; no header/Log/file changes; `why` is the designed near-miss channel (§5); code `refs` at warning severity in a command envelope follows drop's precedent; VALIDATION_CODES and its lockstep test are untouched. See T-8jrndl for read cost.

### Tests (tests/test_cli.py)

Block a TODO task A on B (A unclaimed — `block` preserves a claim and `unblock` would restore in_progress, which is not eligible); `done B --no-code "shipped elsewhere"` (done-evidence refuses otherwise) → envelope warns for A with the unblock hint; `next --json` why for A contains "(done"; `stale_blocks` lists A; `unblock A` → eligible. Same with `drop B` (target_status dropped). Blocks on `human` / `external:` produce no entry; `test_next_reports_human_blockage` asserts `stale_blocks == []`. Claimed path: `release A --blocked --on B`, close B, `unblock A` → in_progress and A leaves `stale_blocks`. Existing `why` substring assertions keep passing; `validate --strict --no-git` output byte-identical before and after (guards the no-new-validation-code promise).

## Next Steps

- [ ] compute_eligible: annotated why text + fourth return value stale_blocks; emit on both next paths
- [ ] cmd_done/cmd_drop: read-only pass warning open tasks blocked on the closed id
- [ ] DESIGN §5 next/done bullets (fix the 'when nothing is eligible' wording); README unblock line; tests

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Signal blocks whose blocked_on task has closed
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] step: added 'compute_eligible: annotated why text + fourth return value stale_blocks; emit on both next paths'
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] step: added 'cmd_done/cmd_drop: read-only pass warning open tasks blocked on the closed id'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'DESIGN §5 next/done bullets (fix the 'when nothing is eligible' wording); README unblock line; tests'
