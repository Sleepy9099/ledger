---
id: T-7xpvs1
title: Session identity: per-call setting in the protocol, actor reported by next, fallback warning on claims, no anonymous claims, already-holding refusal
status: todo
priority: p1
size: s
created: 2026-09-02T11:44:58Z
tags: protocol, ownership
---

## Spec

### Defects (sweep 2026-09-02, ergonomics #1, #2; correctness #8; verified)

In Claude Code / Codex every Bash call is a fresh shell, so "export a session id once" evaporates after one call and the actor silently falls back to `git config user.name`; `list --mine` then finds nothing and the agent's own task reads as a foreign fresh claim. `next --claim` takes a second task before reporting `held`. With no git identity, `claim` writes `claimed_by: unknown` for every session while `list --mine` refuses.

### Design

- PROTOCOL step 1: set `LEDGER_SESSION=<agent>-<YYYY-MM-DD>-<letter>` IN EVERY shell call (exports do not survive between tool calls) or pass `--session`; a `why` row claimed by an earlier session of yours is abandoned work — `claim --force` after `brief`.
- `next` data gains `actor: {id, source: flag|env|git|unknown}` on both paths; `claim` and `next --claim` emit a `session-fallback` warning row when the source is git; refuse (`usage`, the list --mine hint) when the actor is `unknown`.
- `next --claim` refuses with `already-holding` (exit 2) when the session holds a fresh in_progress claim, listing them with `ledger brief <id>` / `ledger release <id> --note`; `--force` allows a second claim (multi-claim sessions stay supported). `held` is computed BEFORE the claim.
- Tests: fallback warning, unknown refusal, already-holding refusal and --force, held-before-claim.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T11:44:58Z [claude-2026-09-01-b] add: created: Session identity: per-call setting in the protocol, actor reported by next, fallback warning on claims, no anonymous claims, already-holding refusal [p1/s] (tags: protocol, ownership)
