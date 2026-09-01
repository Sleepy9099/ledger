---
id: T-6kyk2x
title: Advisory resource leases derived from claims (measure first)
status: blocked
priority: p3
size: s
created: 2026-09-01T23:48:40Z
blocked_on: human
tags: concurrency, orchestration
---

## Spec

### Motivation (review §14, §15, §20, §25)

A claim stops two agents doing the same task, not consuming the same GPU / integration DB / full suite. `compute_eligible` gates only on status, block, fresh claim, depends_on and xl; there is no cross-task exclusion besides depends_on, nothing records that an agent waited, and the mutation lock serializes one checkout's claim race only (cross-branch stays advisory, DESIGN §7(f)). The review's own rule: add a lease only for measured contention — nothing is measurable today. A max-active-workers knob is NOT proposed: the ledger knows claims, not workers (one worker may hold several related claims — review §7; per-branch checkouts hide other workers' claims until merge; a refused worker has no wait primitive without a daemon). Admission belongs in the spawner, which can read `list --claimed --json` today.

### Gate — do not claim this task before it is true

A host project has used Phase 0 for at least one concurrent wave and either (a) three or more `wait: resource` Log notes exist across that wave, or (b) one observed collision (two agents simultaneously on the same declared resource caused a failed or aborted run). Record the evidence in this task's Log first. The gate counts Log prose written by agents (DESIGN §3: honest-agent convenience) — it is a human decision input, not a tool measurement.

### Phase 0 — measurement with the existing tool (no code; host-project text placed in CLAUDE.md OUTSIDE the LEDGER block)

Declare: `ledger add "..." --tag resource:gpu --tag resource:full-suite`; for existing tasks `ledger set <id> --add-tag resource:integration-db` (tags accept any comma-free slug in every vendored version; `list --tag` is exact and case-sensitive). See holders: `ledger list --status in_progress --tag resource:gpu --json` (lists stale holders too; `next --json`'s why is the fresh-claim view). Record a wait: `ledger note <id> "wait: resource gpu held by T-x; waited ~12m"` — countable with `git grep -h "wait: resource" .ledger/tasks | wc -l`. Nothing to upgrade.

### Phase 1 — advisory lease derived from claims (the tool change; option A)

Vocabulary: a task's resources are its tags with the `resource:` prefix; the slug is compared as an opaque exact string like `list --tag` (no grammar enforced beyond `_clean_tag`; an optional `resource-tag-grammar` warning for slugs outside `[a-z0-9][a-z0-9._:-]*`, following the `checkbox-grammar` precedent, may be added). `Task.resources` beside `tags`. Lease = a fresh claim on a task declaring the resource: `held(r)` = tasks with `status == in_progress` (a blocked task may retain claimed_by but does not hold — the rule keys on status), `not claim_is_stale(t)` (which keys on last_activity, so any Log activity keeps the lease alive; a stranded holder blocks the resource for up to `stale_claim_days`, and the orchestrator must sweep stranded claims with `release --force` / `claim --force`) and `r in t.resources`. Acquisition paths: `claim`, `next --claim` AND `unblock` of a task that still carries a claim (cmd_unblock restores in_progress from a claim that `block` retained; `release --blocked` strips it). Release paths: release, done, drop, release --blocked. No new state, no new write path.
- `next` (`compute_eligible`): after the xl gate, skip tasks whose resource is held by a DIFFERENT task with `why: resource <r> held by <T-x> (claimed by <session> at <ts>)`; `next --claim` falls through to the best free task — that is the whole of resource-aware admission. Add `resources_held: {r: T-x}` to BOTH `next` emit sites (human-mode `next` prints `why` only when nothing is eligible; the teaching moment is under --json, which the protocol mandates).
- `claim` and `unblock`: refuse with `resource-held` (exit 2, fix_hint "wait for <T-x> to release, pick another task, or --force if you will serialize the resource yourself") unless `--force` (add `--force` to the unblock parser). Only OTHER tasks' fresh claims count as holders — the target task's own prior or stale claim never does; a stale takeover of A is still refused when a different fresh task holds one of A's resources (matching what `next` does after the stale flag). With `--force` the claim Log line gains `(resource <r> also held by <T-x>)` via an optional `extra` parameter on `apply_claim` (also passed empty by next --claim).
- `validate`: new code `resource-contention` — two fresh-claimed in_progress tasks share a resource (reachable via `claim --force`, `unblock --force`, a cross-branch merge, a hand-edited header, or an older copy that ignored the gate). Tier is part of the human question: `info` (never promoted, like `exempt-ratio`) or `warning` (then the bootstrapped `--strict` CI fails on any double-hold until one holder releases — a deliberate departure from today's `claim --force`, which leaves a clean state). Add to VALIDATION_CODES and the lockstep test.
- `list --resource <slug>` = sugar for `--tag resource:<slug>` (single-valued, exact, ANDed with `--tag`); `task_brief` / `task_full` gain a computed `resources` list. Header unchanged.

### Explicitly out of scope

No `resources:` header key in Phase 1 (Phase 2 only if the human chooses B: sequence after T-2e587s so `doctor` can report "corpus newer than tool" instead of "probably a typo"; note that old and new copies would emit byte-identical files because unknown keys serialize after `tags` — the incompatibility is validate/JSON-only). No wait/poll loop, daemon, per-resource lock file or file-level locks (DESIGN §7(f), §11). No new status (Appendix #6) — a resource wait is expressed as "next gave me a different task", exactly like a foreign claim. No capacity > 1 per resource. No cross-branch enforcement. No `max_active_workers` knob.

### DESIGN.md principles

The declaration is a tag inside the task file; the lease is a pure function of claim fields that already live there; no registry, counter or sidecar; zero new writes. A cross-branch double-hold merges cleanly (different files) and surfaces as `resource-contention` in the post-merge ritual — "detected, not prevented" (§7(f)). ~60 lines across compute_eligible, cmd_claim, cmd_unblock, validate_offline, cmd_list. Introduces a prefix dialect inside `tags` (decision #5 avoided dialects for header lists) — acknowledge in DESIGN §2's tags row. Do NOT add resource guidance to PROTOCOL_TEXT (review §22: keep the always-loaded prompt small); the `why` line teaches the agent at the moment it matters. `resource-contention` is a header-derived hygiene signal in the `stale-claim` family, not an enforced guarantee — the tool cannot verify that a resource is actually in use.

### Backward compatibility

`resource:x` is an ordinary tag, legal, preserved on rewrite and never flagged by any version's `validate`; older `next` ignores the gate; older `list --tag resource:x` already works; mixed-version fleets degrade to advisory-by-convention with no CI breakage unless two fresh claims share a resource under the warning tier. New copy on an old corpus: no `resource:` tags means no gates and identical `next` order.

### Tests

tests/test_cli.py: `next` skips a resource-held task and its `why` names the holder id and session; `next` falls through to the next free task and `next --claim` claims it; after `release`, `done` and `drop` of the holder the skipped task becomes eligible; a holder whose timestamps are rewritten to 2020 (stale) does not hold; a `blocked` holder does not hold; `-n` listing excludes held tasks; `resources_held` on both emit paths. claim/unblock: `resource-held` refusal exit 2 with fix_hint; `--force` succeeds and the claim Log line carries the suffix; self re-claim and stale self-takeover are not refused; `unblock` on a blocked holder whose resource is now held elsewhere is refused, `unblock --force` succeeds and `validate` reports `resource-contention`. validate: fixture with two forced claims sharing `resource:gpu`; lockstep table updated. list: `--resource gpu` equals `--tag resource:gpu`; `task_brief` exposes `resources`. tests/test_concurrency.py: 12 parallel `next --claim` against two todo tasks both tagged `resource:full-suite` produce exactly one claim; every loser reports `task: null` with the resource `why` line. tests/test_property.py: sequences with `--tag resource:*` and `claim --force` leave non-strict validate clean.

## Next Steps

- [ ] Human answers representation / timing / warning-tier; unblock only when the measurement gate is met
- [ ] Phase 1: Task.resources, next gate + resources_held, claim/unblock resource-held refusal with --force, resource-contention validate code, list --resource
- [ ] DESIGN §2 tags row, §5 eligibility, §7(h); README; tests incl. the concurrency race

## Open Questions

- [ ] HUMAN: Resource leases: (1) representation — A) a `resource:<slug>` tag convention that next/claim/validate interpret (zero header-schema change; every vendored copy validates clean; recommended) or B) a new `resources:` header key (cleaner JSON and typo detection, but every repo must upgrade its vendored ledger.py first: older copies emit unknown-key, promoted to error by --strict CI, and hide the key from --json)? (2) timing — keep this filed at p3 gated on measured contention (recommended; the review's own rule) or drop until a wave records waits? (3) the `resource-contention` validate code: `info` (never promoted, like exempt-ratio) or `warning` (then --strict CI fails on any double-hold, including sanctioned `--force` ones, until a holder releases)?

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Advisory resource leases derived from claims (measure first)
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] step: added 'Human answers representation / timing / warning-tier; unblock only when the measurement gate is met'
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] step: added 'Phase 1: Task.resources, next gate + resources_held, claim/unblock resource-held refusal with --force, resource-contention validate code, list --resource'
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] step: added 'DESIGN §2 tags row, §5 eligibility, §7(h); README; tests incl. the concurrency race'
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] question: added (HUMAN): Resource leases: (1) representation — A) a `resource:<slug>` tag convention that next/claim/validate interpret (zero header-schema change; every vendored copy validates clean; recommended) or B) a new `resources:` header key (cleaner JSON and typo detection, but every repo must upgrade its vendored ledger.py first: older copies emit unknown-key, promoted to error by --strict CI, and hide the key from --json)? (2) timing — keep this filed at p3 gated on measured contention (recommended; the review's own rule) or drop until a wave records waits? (3) the `resource-contention` validate code: `info` (never promoted, like exempt-ratio) or `warning` (then --strict CI fails on any double-hold, including sanctioned `--force` ones, until a holder releases)?
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
