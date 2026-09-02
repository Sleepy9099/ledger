---
id: T-z1dkju
title: Operator decision loop: questions with context, blocked-on-human rows, answers apply
status: in_progress
priority: p3
size: m
created: 2026-09-01T23:48:40Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T02:19:46Z
depends_on: T-w0emnj
tags: human-decisions, ergonomics
---

## Spec

### Motivation (review §6; touches §5, §23)

Review §6: collect human-gated questions → present a compact decision set → record each answer back → launch workers. The tool's primitives work (the review scores this 10/10) but the loop is manual. Confirmed 2026-09-01: `questions --human` rows are `{task, title, n, human, text}` with no priority/claim state and no context — `Task.questions()` parses only checkbox lines, so any options/recommendation an agent writes as continuation prose is preserved (Open Questions is free-edit) but invisible to `questions`, `show --json` and `done`; the protocol's second human-gate channel, `block --on human --why` (and `release --blocked --on human --note`), never appears in `questions --human` — the gate itself is visible in `next.blocked_on_human` and `list` headers, but the REASON lives only in the `block:` / `release:` Log line — while README promises "everything waiting on the operator"; and recording is one `question <id> resolve <n> --answer` per task per process (a shell loop over `questions --json` works; there is no batch path). An orchestrator can approximate the view by joining `questions --json` with `list --json`; what no composition yields is the continuation prose, the block reason, or a grouping key.

### Design A — `questions` decision view (read-only)

1. Rows gain `priority`, `status`, `size`, `claimed_by` (may be non-null on blocked tasks), `kind: "question"`; every row keeps an integer `n`.
2. `context`: the non-empty, non-checkbox lines of `## Open Questions` between this checkbox and the next (same line-level parse as `Task.questions()`: no fence awareness; prose before the first checkbox belongs to no row; near-miss checkbox lines land in the preceding context — validate already warns `checkbox-grammar`; exclude `#` heading lines). Opportunistic: the CLI never authors it. Either add one PROTOCOL_TEXT sentence ("put options and your recommendation on indented lines under the question so `questions --human` shows them"; regenerate via init) or state explicitly that no protocol change is made.
3. `key`: `casefold()`, collapse whitespace, strip trailing `?.!` — a grouping HINT for consumers (rows with equal key are candidate duplicates for the operator to confirm); NOT a selector for `question resolve`, which addresses by index or raw substring (decision #21).
4. Blocked-on-human tasks go in a sibling array `data.blocked_on_human` (the key `next` already uses), never interleaved into `questions`: `{id, title, priority, status, size, claimed_by, reason, reason_source}`. `reason` comes from the newest Log line whose verb is `block` or `release`: a `block` line `on human — <reason>` (separator space, U+2014, space) → the reason; a `release` line whose text starts with `blocked on ` (the format T-w0emnj introduces) → strip `blocked on <blocked_on>` and the ` — ` separator and use the remainder (`""` when nothing follows); an older `release` line → its text unless it is the default `released`; otherwise `""`; NEVER fall back to an older `block` line (a stale reason after block / unblock / release-blocked). The header `blocked_on` stays the only authoritative fact.
5. Ordering `sort_key`; human rendering `T-x #n [HUMAN] (p1, in_progress by claude-…): text` plus indented context lines; block rows `T-x [BLOCKED on human] (p1, blocked by …): reason`. Optional `--task <fragment>` (repeatable), resolved against the already-loaded list with load_task_or_die's exact-then-substring rule (no extra directory scan). README lines for `questions`.

### Design B — `answers apply <file|->` (mutating; one lock hold)

Input: the `questions --json` envelope (`data.questions`) or a bare list; rows `{task, n?, text?, answer?, kind?}` (unknown keys ignored) — rows without `answer` or with `kind == "block"` are `skipped` (a partially filled file is valid; re-run later). Parse the input BEFORE taking the lock (malformed JSON → `usage`, exit 3, before the lock). Load all tasks once under the lock; resolve each row's task fragment against that list; group rows per task and apply them to the single in-memory Task (one `save_task` per file). Selector: `n` is honoured only when `Task.questions()[n-1]["text"]` (display form, HUMAN: stripped) equals the row's `text`; otherwise `_resolve_checkbox_line(content, text, want_unchecked=True)` (substring is the merge-safe address, decision #21); `n` alone behaves like `question resolve <n>`. Already answered with byte-equal text → `skipped` (`already-answered`); with different text → `bad-state`; two rows resolving to one checkbox → `duplicate-target`. Resolve every row before writing any file; a multi-row refusal uses cmd_done's pattern (`emit(args, False, {...}, errors=[...]); return 2`) because LedgerError carries one violation; writes are then sequential per file (same shape as `_backfill_from_trailers`), so a re-run after an interruption is safe via the skip rule. Extract `_answer_question(task, selector, answer, actor)` from `cmd_question` so `resolve` and `apply` cannot drift (ANSWERED line `<raw text incl. HUMAN: prefix> -- ANSWERED (date): answer`, Log `answer:` verb) — files identical modulo the second-resolution Log timestamp. Output `data.applied` / `data.skipped`. Not in PROTOCOL_TEXT (operator-facing, same audience as `questions --human`); add to DESIGN §5's command list and README.

### DESIGN.md principles

A: a pure derived read; no `blocked_reason` header (decision #7); the block reason is read from the Log like `last_activity`; DESIGN §11 rejects evidence-token vocabularies, not question options — options stay free prose per decisions #20/#22. B: the input file lives outside `.ledger/` and is never committed; every write is one task file via save_task; the Log verb stays `answer`; trust: the tool cannot verify a human authored the answers — the Log actor is the applying session (DESIGN §3).

### Backward compatibility

Additive JSON keys; files identical to `resolve` output; older copies lack the flags / subcommand.

### Tests

A: rows carry the new fields after `claim`; context equals exactly the two prose lines under the first checkbox (edit the section with file tools), second row `""`; equal `key` for "Which vendor?" vs "which  vendor"; block rows via `block --on human --why` and via `release --blocked --on human --note` (reason_source), and a stale reason never resurfaces after block / unblock / release-blocked; `--on T-y` never appears; `unblock` removes the row; `show` and `list --status blocked` shapes unchanged; all `questions` rows have integer `n`; `--task` scoping; the existing dashboard test holds.
B: a 2-row file across two tasks → both answered, one `answer` Log line each, `done` no longer refuses; stale `n` with matching `text` → text wins; one bad row → exit 2, both files byte-identical, errors name the row's task; skips; stdin `-`; malformed JSON → exit 3 before the lock; equality with `resolve` modulo timestamps/date; same-task two-row case (file written once); lock-timeout refusal mirroring test_lock_timeout_is_a_clean_refusal (do NOT add to the read-only list); `("answers", "apply", <path>)` in the envelope test; a test_property op.

## Next Steps

- [x] questions: row enrichment, context, key, sibling blocked_on_human array with reason/reason_source, optional --task
- [x] answers apply: parse before lock, load once, selector rule, all-rows-resolve-before-write, cmd_done-style multi-error refusal, _answer_question extraction
- [x] README (questions fields; answers apply); DESIGN §5 command list; optional PROTOCOL_TEXT sentence on writing options under a question
- [x] Tests for both parts incl. lock-timeout and envelope entries

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Operator decision loop: questions with context, blocked-on-human rows, answers apply
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'questions: row enrichment, context, key, sibling blocked_on_human array with reason/reason_source, optional --task'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'answers apply: parse before lock, load once, selector rule, all-rows-resolve-before-write, cmd_done-style multi-error refusal, _answer_question extraction'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'README (questions fields; answers apply); DESIGN §5 command list; optional PROTOCOL_TEXT sentence on writing options under a question'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'Tests for both parts incl. lock-timeout and envelope entries'
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] set: depends_on + -> T-w0emnj
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] note: Consistency pass 2026-09-01: release-line reason parser must handle the `blocked on <x> — <note>` text T-w0emnj introduces; depends_on T-w0emnj added
- 2026-09-02T02:19:46Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T02:28:44Z [claude-2026-09-01-b] step: checked 'questions: row enrichment, context, key, sibling blocked_on_human array with reason/reason_source, optional --task'
- 2026-09-02T02:28:44Z [claude-2026-09-01-b] step: checked 'answers apply: parse before lock, load once, selector rule, all-rows-resolve-before-write, cmd_done-style multi-error refusal, _answer_question extraction'
- 2026-09-02T02:28:44Z [claude-2026-09-01-b] step: checked 'README (questions fields; answers apply); DESIGN §5 command list; optional PROTOCOL_TEXT sentence on writing options under a question'
- 2026-09-02T02:28:44Z [claude-2026-09-01-b] step: checked 'Tests for both parts incl. lock-timeout and envelope entries'
