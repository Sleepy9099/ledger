---
id: T-eb6bas
title: list --mine and next.held for multi-claim sessions
status: in_progress
priority: p3
size: s
created: 2026-09-01T23:48:40Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T02:08:47Z
tags: ownership, ergonomics
---

## Spec

### Motivation (review §7, §26)

The tool already permits N claims per actor (`cmd_claim` and `cmd_next` never inspect the actor's other holdings — verified: a session holding two claims is handed a third by `next --claim`) and multi-task commits (one `Ledger-Task:` line per task) — exactly the style the review endorses. But a session cannot enumerate what IT holds without a client-side filter over `list --claimed --json` (rows do carry claimed_by / claimed_at), and `next` is an incomplete view: `why` names the actor's own FRESH in_progress claims, a held BLOCKED task shows as `blocked_on <reason>` with no holder, and an own STALE claim is not in `why` at all — it is eligible again and `next --claim` re-claims it logging `claim: taking over claim from <self>` (cmd_next lacks cmd_claim's holder == actor check — a bug). PROTOCOL_TEXT's session-end step speaks of a single "Unfinished task", so a multi-claim session has no protocol-blessed release-everything step and a stranded claim (§26) is the likely outcome.

### Design

- `list --mine`: `claimed_by == ctx.actor` (in_progress or blocked; no extra status gate, so a coherence violation stays visible); combinable with the other filters; mutually exclusive with `--unclaimed` (usage exit 3); refused with a usage error when the actor resolves to `unknown` (set LEDGER_SESSION / --session). Read-only and lock-free (add to the read-only list in tests/test_concurrency.py).
- `next`: `data.held` = every parsed task in the structurally-sound pool with `claimed_by == ctx.actor` and status in {in_progress, blocked}, EXCLUDING the task claimed by this invocation, each `{id, title, status, claimed_at, blocked_on, stale}` (`claim_is_stale`), on BOTH emit paths; human output prints `also holding: T-x [status] title` even when a task is eligible. Advisory — keyed on the resolved actor; no ownership-enforcement change (`claim-held` / `linked-never-claimed` untouched). `why` is left exactly as today.
- Fix cmd_next's self-takeover: `takeover = holder if flag == "stale_claim" and holder != ctx.actor else None`, so refreshing one's own stale claim logs `claim: claimed`, not `taking over claim from <self>`; document `stale_takeover` semantics for self-refresh.
- Protocol (PROTOCOL_TEXT session-end step 1; regenerate PROTOCOL.md / CLAUDE.md via init; README `claim / release` row; DESIGN §9): "Unfinished tasks (`ledger list --mine`): for each, make Next Steps reflect reality, then `ledger release <id> --note "..."`; for a held task that is already blocked, `ledger release <id> --blocked --on <same reason> --note ...` — a plain `release` would reset it to todo." Optionally session-start step 2: "if `held` is non-empty those are yours from earlier — resume them before taking more."

### DESIGN.md principles

No files or fields; derived at read time; `next --claim` computes `held` under the lock it already holds; `list` stays lock-free (§7g). Cross-reference T-fkywmw (adjacent, orthogonal). If T-2e587s has landed, bump PROTOCOL_VERSION.

### Tests (tests/test_cli.py; sessions via `--session a` / `--session b` because conftest pins LEDGER_SESSION)

`list --mine --json` after `claim` + `block --on human` returns both; another session's claim excluded; `--mine --unclaimed` → exit 3; `next --json` `held` lists two fresh claims with `stale: false` and a blocked one with `status: blocked` / `blocked_on`; the nothing-eligible path still carries `held`; with `set_stale_days(-1)` (helper lives in tests/test_hardening.py — import it or move it to conftest) `next --claim` by the same holder logs `claim: claimed`, not a self-takeover; human output lists `also holding:` only for tasks other than the one just claimed.

## Next Steps

- [x] list --mine (exclusive with --unclaimed; refuse on actor 'unknown'); add to the lock-free list
- [x] next: held on both emit paths (+ human 'also holding:' lines); fix the self-takeover Log line
- [x] PROTOCOL_TEXT session-end step (plural, release --blocked for held blocked tasks); re-run init; README; DESIGN §9
- [x] Tests with --session a/--session b

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: list --mine and next.held for multi-claim sessions
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'list --mine (exclusive with --unclaimed; refuse on actor 'unknown'); add to the lock-free list'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'next: held on both emit paths (+ human 'also holding:' lines); fix the self-takeover Log line'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'PROTOCOL_TEXT session-end step (plural, release --blocked for held blocked tasks); re-run init; README; DESIGN §9'
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'Tests with --session a/--session b'
- 2026-09-02T02:08:47Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T02:14:42Z [claude-2026-09-01-b] step: checked 'list --mine (exclusive with --unclaimed; refuse on actor 'unknown'); add to the lock-free list'
- 2026-09-02T02:14:42Z [claude-2026-09-01-b] step: checked 'next: held on both emit paths (+ human 'also holding:' lines); fix the self-takeover Log line'
- 2026-09-02T02:14:42Z [claude-2026-09-01-b] step: checked 'PROTOCOL_TEXT session-end step (plural, release --blocked for held blocked tasks); re-run init; README; DESIGN §9'
- 2026-09-02T02:14:42Z [claude-2026-09-01-b] step: checked 'Tests with --session a/--session b'
