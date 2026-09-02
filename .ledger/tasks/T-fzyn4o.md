---
id: T-fzyn4o
title: Decide: next --claim returns the digest shape by default
status: in_progress
priority: p3
size: xs
created: 2026-09-01T23:48:40Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T02:02:53Z
depends_on: T-z7iebd, T-2e587s
tags: ergonomics, context, decision
---

## Spec

### Motivation (review §2, §22, §23)

The largest context lever in this area is the mandatory command, not the optional one: `cmd_next` embeds `task_full`, so `next --claim --json` returns the entire Log, and PROTOCOL_TEXT step 2 requires reading the file anyway — the full task enters context twice (human-mode `next` is already a one-line summary; this is `--json`-only, which the protocol mandates). T-z7iebd adds an opt-in `--brief`; this task is the follow-up decision on whether the DEFAULT should change — a JSON contract change visible to every host repo, so it must be a deliberate human decision rather than a side effect.

### Design (if approved)

`next` returns `data.task` in the digest shape T-z7iebd defines by default (`header`, `path`, `steps_open` / `steps_total` / `steps_done`, `human_gated_questions`, `open_questions` as a count, `recent_log` / `log_total`, `dead_ends`, `commits`, `effective_commits`, `last_activity`, `spec_lines`; the top-level `claimed`, `stale_takeover`, `why` and `blocked_on_human` keys are unchanged); decide whether a `spec` body is added to the digest for `next` only — if not, the PROTOCOL step-2 file read is the ONLY source of the Spec; `--full` restores `task_full`; the shape depends only on `--full`, never on data. `-n` rows stay `task_brief`. `show` keeps `task_full` (the explicit "everything" command) — `show` and `next` then diverge by design, and any host script treating them as interchangeable must use `--full`. PROTOCOL_TEXT step 2: "`ledger next --claim --json` — this is your task (bounded view; `--full` for everything). Read its file BEFORE writing code." Requires T-2e587s (it introduces TOOL_VERSION / PROTOCOL_VERSION; none exist today — DEFAULT_CONFIG `version` is the config-schema version) so the payload change and the protocol text ship with a version bump; re-run init in this repo so PROTOCOL.md / CLAUDE.md regenerate.

### Backward compatibility

Host scripts reading `data.task.log` / `.spec` from `next` must switch to `--full` or `show`; the tool's own tests read only `data.task.header.*`, `data.why`, `data.claimed`, `data.blocked_on_human`. Task files are untouched, so mixed-version repos stay valid.

### Tests

Default payload has the digest keys and no `log`; `--full` has the `task_full` keys; `next --claim` still claims and returns `claimed: true` with `header.claimed_by`; the 12-racer concurrency test keeps passing on `header.claimed_by`; PROTOCOL_TEXT mentions `--full`; `.ledger/PROTOCOL.md` == PROTOCOL_TEXT after init.

## Next Steps

- [x] Human answers; unblock or drop
- [x] If approved: switch the default, add --full, update PROTOCOL_TEXT step 2, bump PROTOCOL_VERSION/TOOL_VERSION, re-run init

## Open Questions

- [x] HUMAN: After `brief` lands, should `next` return `data.task` in the digest shape by default with `--full` restoring today's payload (removes the double-load at every session start; the tool's own tests read only header/why/claimed/blocked_on_human), or keep `task_full` as the default and rely on the opt-in `--brief` (zero contract risk for host scripts that parse data.task.log)? A data-dependent shape (switch only above a Log-length threshold) is rejected either way. -- ANSWERED (2026-09-02): Digest shape by default, --full restores task_full. Operator criteria: context-friendliness of the one mandatory command wins; the protocol already requires reading the task file, so the full Log entered context twice. Host scripts that parse data.task.log switch to --full or show; PROTOCOL_VERSION bumps in the same commit.

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Decide: next --claim returns the digest shape by default
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] step: added 'Human answers; unblock or drop'
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] step: added 'If approved: switch the default, add --full, update PROTOCOL_TEXT step 2, bump PROTOCOL_VERSION/TOOL_VERSION, re-run init'
- 2026-09-01T23:48:49Z [claude-2026-09-01-a] question: added (HUMAN): After `brief` lands, should `next` return `data.task` in the digest shape by default with `--full` restoring today's payload (removes the double-load at every session start; the tool's own tests read only header/why/claimed/blocked_on_human), or keep `task_full` as the default and rely on the opt-in `--brief` (zero contract risk for host scripts that parse data.task.log)? A data-dependent shape (switch only above a Log-length threshold) is rejected either way.
- 2026-09-01T23:48:49Z [claude-2026-09-01-a] set: depends_on + -> T-z7iebd
- 2026-09-01T23:48:49Z [claude-2026-09-01-a] set: depends_on + -> T-2e587s
- 2026-09-01T23:48:49Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
- 2026-09-02T00:06:25Z [claude-2026-09-01-a] note: Consistency pass 2026-09-01: payload description aligned with T-z7iebd's digest keys (no next_steps key; open_questions is a count in the digest)
- 2026-09-02T00:54:57Z [claude-2026-09-01-b] answer: 'HUMAN: After `brief` lands, should `next` return `data.task` in the digest shape by default with `--full` restoring today's payload (removes the double-load at every session start; the tool's own tests read only header/why/claimed/blocked_on_human), or keep `task_full` as the default and rely on the opt-in `--brief` (zero contract risk for host scripts that parse data.task.log)? A data-dependent shape (switch only above a Log-length threshold) is rejected either way.' -> Digest shape by default, --full restores task_full. Operator criteria: context-friendliness of the one mandatory command wins; the protocol already requires reading the task file, so the full Log entered context twice. Host scripts that parse data.task.log switch to --full or show; PROTOCOL_VERSION bumps in the same commit.
- 2026-09-02T00:54:58Z [claude-2026-09-01-b] unblock: -> todo
- 2026-09-02T02:02:53Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T02:02:54Z [claude-2026-09-01-b] step: checked 'Human answers; unblock or drop'
- 2026-09-02T02:08:32Z [claude-2026-09-01-b] step: checked 'If approved: switch the default, add --full, update PROTOCOL_TEXT step 2, bump PROTOCOL_VERSION/TOOL_VERSION, re-run init'
