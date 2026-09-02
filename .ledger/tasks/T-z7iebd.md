---
id: T-z7iebd
title: ledger brief: bounded derived view of one task
status: done
priority: p2
size: s
created: 2026-09-01T23:48:39Z
closed: 2026-09-02T02:02:51Z
tags: ergonomics, context
---

## Spec

### Motivation (review §2, §22, §23)

Review §23 asks for a bounded derived view instead of lossy summarization. The destructive half is already prevented — `log-tamper` fails `--strict` CI when any historical Log line disappears — so only the retrieval side is missing: there is nothing between `list`'s header+counts (`task_brief`) and `show`'s everything (`task_full`: spec, all steps, all questions, all commits, ALL Log entries). `cmd_next` embeds `task_full`, so the mandatory session-start command returns the entire Log, and PROTOCOL_TEXT step 2 then tells the agent to read the file too — the same content enters context twice. PROTOCOL_TEXT says "recent Log" but no command can express "recent". Measured (70 Log lines): the `log` array is ~83% of `show --json`; `next --json` embeds the same payload; absolute size scales with note length. Per DESIGN §3.1 the header / Spec / Next Steps / Open Questions snapshot is bounded by construction; the unbounded, unselectable parts are `## Log` (no "recent") and dead ends (no marker — see T-yfvuya).

### Design

New read-only subcommand `brief <id> [--last N] [--no-git]` (default N=10), plus an opt-in `--brief` flag on `show` and `next` that REPLACES the `task_full` shape of `data` / `data.task` with the digest shape (without `--brief` the payload is byte-for-byte today's). `next -n` rows keep the existing `task_brief` header+counts shape and are NOT the brief view. Name the new helper `task_digest` — do not reuse `task_brief`, and do not reuse its key `open_steps` (an int there) for a list here.

`task_digest(ctx, task, last, trailer_map)` returns:
- `header`: the HEADER_ORDER projection.
- `steps_open`: `Task.steps()` entries with `done == False`, KEEPING the original `n` (indexes run over all checkbox lines, so `step check <n>` keeps working; across merges prefer the substring selector); `steps_total`, `steps_done`.
- `human_gated_questions`: every `HUMAN:` question, answered or not, with `n, text, answered, answer, answered_by` (actor of the matching `answer` Log line, else null; the tool does not verify that a human answered — the prefix marks who SHOULD decide); `answer` is null when a checked HUMAN line carries no ANSWERED suffix. This differs from `questions --human`, which is cross-task and drops answered ones. `open_questions` = count of all unanswered (same key and meaning as task_brief).
- `recent_log`: the last N entries after a stable sort of `Task.log()` by `ts` (Log lines are order-insensitive under merges; `last_activity` already takes max(ts) the same way); `log_total`.
- `dead_ends`: Log entries selected by the marker T-yfvuya decides; present and empty until it lands; uncapped.
- `commits` (`Task.commits()`) and `effective_commits` via one `trailer_links` call exactly as show/next do today; `--no-git` skips the walk (`trailer_links` already returns {} without a repo, so the result equals the `## Commits` shas — spawn avoidance, not a new code path; never infers linkage, DESIGN §4).
- `last_activity`, `path`, `spec_lines` (line count only — the Spec body is deliberately EXCLUDED so the one file read stays the authority, DESIGN §3; PROTOCOL step 2 still says read the file).
Only `recent_log` is bounded — say so in the docs. Human rendering (~15 lines): id/prio/size/title/status/claimed_by, `open steps:` (with n), `human:`, `dead ends:`, `recent:` (`ts verb: text`), `commits:`, last_activity. Ids resolve via `load_task_or_die(for_write=False)` as `show` does (lock-free; works on structurally broken files; same refusals). `--last`/`--no-git` are accepted by `brief`, and by `show`/`next` only together with `--brief`; `validate --no-git` is unchanged.

Protocol: REPLACE the clause in PROTOCOL_TEXT step 2 ("Read its file (Spec, Next Steps, Open Questions, recent Log)") with "Read its file (Spec, Next Steps, Open Questions; `ledger brief <id> --json` for the recent Log on long tasks)"; re-run init in this repo so PROTOCOL.md/CLAUDE.md regenerate (sequence after T-w0emnj, which owns the PROTOCOL_TEXT budget; if T-2e587s has landed, bump PROTOCOL_VERSION in the same commit); README "Daily commands"; DESIGN §5 command list. Switching `next`'s DEFAULT payload is T-fzyn4o (a human decision); this task leaves defaults untouched.

### DESIGN.md principles

Same directory scan as `show`, no writes; no format change; stdlib over existing structured views; no cache (T-8jrndl is a different problem — directory-scan latency, not payload size); read commands stay lock-free (§7g); §11 rejects spec-EDITING commands, a read view is outside it; informational only (trust model: Log-derived fields are agent-authored prose).

### Backward compatibility

Task files untouched; a pre-brief vendored copy gives argparse exit 3 (T-2e587s doctor is the detector); `show`/`next` default payloads and the keys pinned by tests/test_cli.py are unchanged.

### Tests

- tests/test_cli.py: envelope keys; `--last 3` returns the 3 newest by ts and `log_total` equals the full count; `steps_open` preserve the original `n` (add 3 steps, check #1 → n=2,3); human-gated questions include answered ones with `answer`/`answered_by`; `dead_ends` present (empty); `spec_lines`; task file bytes unchanged after `brief`; `show --brief` / `next --brief` use the digest shape while plain calls keep the `task_full` keys; `next -n 3 --brief` keeps `data.tasks[]` as header+counts rows.
- `("brief", tid)` in test_every_command_emits_envelope and in the read-only list in tests/test_concurrency.py (lock-free pinned).
- `plain` fixture: `effective_commits == commits shas`; `repo` fixture with `--no-git` same; after a trailer-only commit `brief`'s effective_commits contains sha[:7] while `commits` is empty (new assertion — none exists for show today).
- tests/test_property.py: `brief` on a random id → rc 0.

## Next Steps

- [x] task_digest() over existing structured views; brief subcommand with --last/--no-git
- [x] --brief on show and next (replaces the task_full shape; -n rows unchanged)
- [x] Replace the PROTOCOL_TEXT step-2 clause; re-run init; README; DESIGN §5
- [x] Tests incl. envelope + lock-free lists, plain fixture, trailer-only effective_commits

## Open Questions

## Commits

- 458d326 2026-09-01 Add ledger brief: a bounded derived view of one task

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: ledger brief: bounded derived view of one task
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'task_digest() over existing structured views; brief subcommand with --last/--no-git'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added '--brief on show and next (replaces the task_full shape; -n rows unchanged)'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'Replace the PROTOCOL_TEXT step-2 clause; re-run init; README; DESIGN §5'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'Tests incl. envelope + lock-free lists, plain fixture, trailer-only effective_commits'
- 2026-09-02T00:06:25Z [claude-2026-09-01-a] note: Consistency pass 2026-09-01: sequence the PROTOCOL_TEXT edit after T-w0emnj; bump PROTOCOL_VERSION if T-2e587s has landed
- 2026-09-02T01:54:41Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T01:56:58Z [claude-2026-09-01-b] step: checked 'task_digest() over existing structured views; brief subcommand with --last/--no-git'
- 2026-09-02T01:56:58Z [claude-2026-09-01-b] step: checked '--brief on show and next (replaces the task_full shape; -n rows unchanged)'
- 2026-09-02T01:56:58Z [claude-2026-09-01-b] step: checked 'Replace the PROTOCOL_TEXT step-2 clause; re-run init; README; DESIGN §5'
- 2026-09-02T01:56:59Z [claude-2026-09-01-b] step: checked 'Tests incl. envelope + lock-free lists, plain fixture, trailer-only effective_commits'
- 2026-09-02T02:02:51Z [claude-2026-09-01-b] link: 458d326 Add ledger brief: a bounded derived view of one task
- 2026-09-02T02:02:51Z [claude-2026-09-01-b] done: evidence: 458d326
