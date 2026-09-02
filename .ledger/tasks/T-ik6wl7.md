---
id: T-ik6wl7
title: Decide: first-class ready status and stranded-handoff aging
status: blocked
priority: p3
size: s
created: 2026-09-01T23:48:40Z
blocked_on: human
tags: lifecycle, decision
---

## Spec

### Context (review §10, §11, §26, §28 item 1)

The review's top recommendation is an explicit `ready_for_integration` state ("probably the most important lifecycle addition"). T-w0emnj documents that `release --blocked --on "external: ready for integration"` already yields the handoff state with no schema change (verified 2026-09-01: skipped by `next` with a `blocked_on external:` why; the integrator's `done --commit` succeeds without `--force`; a plain `release` sends it back). This task holds the two decisions that convention leaves open so they are made deliberately rather than by drift. Do not implement anything while blocked on human; if both answers are "no", `drop` this task with the answers as `--why`.

### Decision 1: a first-class `ready` status (reverses DESIGN decision #6, which cut `review` because no reviewer role was in scope)

Recommendation: keep it cut until a second wave shows the documented convention insufficient. If it is added, the design that survived adversarial review: `STATUSES` gains `ready` (also in OPEN_STATUSES so `questions`, `list` and the drop-dependency warning keep treating it as open); `ledger ready <id> [--note] [--force]` from `in_progress` only, by the fresh claim holder, refusing on unanswered HUMAN questions (a human-gated task is `block --on human`, not integrable) and warning on loose ends; `compute_eligible` gains an explicit `ready → ineligible (awaiting integration)` branch BEFORE the depends_on/xl gates (otherwise a ready task in OPEN_STATUSES falls through and becomes eligible); `done`, `drop` and `release` skip `_guard_foreign_claim` when the status is `ready` (all three call sites); `claim` by the holder reopens, a foreign fresh `claim` refuses; claim fields OPTIONAL on `ready` (as on `blocked`) so a cross-branch ready-vs-release merge — which auto-merges the claim-field deletion three lines away from the conflicting status line — still validates; a `ready` task without a `ready` Log line is a `state-coherence` error (hand-edit detector); a stale ready task is NEVER a `next` takeover candidate (finished work must not be re-dispatched) and surfaces via `stale-claim` worded per what `claim_is_stale` actually measures ("no Log activity for N days", since any note refreshes last_activity). DESIGN edits: header table, §2 verb list, §5 commands / eligibility / "closing verbs honor claims", §6 state-coherence definition, §9, decision #6, README "Daily commands". The costs that decide it: an older vendored validator reports both `enums` and `state-coherence` on a `ready` file (loud); an older `claim` by ANY session silently takes over a ready task, because the claim-held guard lives inside the in_progress branch — a silent ownership failure in the upgrade window; older `done`/`drop`/`release` by a non-holder still refuse with `claim-held`; `next` on the old copy hides the task with no `why` entry. Requires T-2e587s (SCHEMA_VERSION 2 == STATUSES includes ready; `doctor` names the mismatch) — leave a `note` on T-2e587s rather than editing its Spec.

### Decision 2: stranded-handoff aging

Two blind spots, verified 2026-09-01. (1) A handed-off task has no claim, so nothing ever flags it: `stale-claim` needs `claimed_at`, and validate has no age check for `external:` blocks (`validate --strict` stays clean). (2) A blocked task that RETAINED its claim never ages either: the `stale-claim` branch in validate_offline is gated on `status == "in_progress"`, while `block` keeps claimed_by/claimed_at (legal per DESIGN §2) — so a worker that vanishes right after `block --on human` holds a claim indefinitely with a clean `--strict`; extending that branch to `status in ("in_progress", "blocked") and claimed_at` needs no new code path or code. Review §26 requires "no claims are stranded"; a forgotten handoff is the equivalent. Options for (1): (a) a new warning `stale-block` for `blocked_on: external:` handoffs with no Log activity for `stale_claim_days` — a new VALIDATION_CODES entry plus its lockstep fixture, promoted under `--strict` CI, repairable by `unblock` / `done` / `release` (the design's bar for a warning is repairability); it must not catch deliberately parked long-lived blocks such as T-9iu47b's `external: wave open` — scope it to the `external: ready` prefix, or key it on Log activity so a `note` refreshes it; (b) process only — the integrator polls `list --status blocked`. Recommendation: (a) scoped to handoffs, plus the (2) extension, once the convention has been used in a wave. Note: "requires T-2e587s" above is deliberately NOT a depends_on — a dependency would hide this decision from `next`.

### Related

T-fkywmw (claim nonce — different mechanism, same defer-until-observed stance); T-y7j9tx (the ownership-enforcement decision); T-eb6bas (per-session holdings view).

## Next Steps

- [ ] Human answers both questions; unblock or drop
- [ ] If a ready status is approved: implement per the verified design below and note T-2e587s about SCHEMA_VERSION 2
- [ ] If stranded-handoff aging is approved: add the stale-block warning + lockstep fixture

## Open Questions

- [ ] HUMAN: Add a sixth status `ready` (`ledger ready <id>`) as the review's #1 recommendation, reversing DESIGN decision #6, or keep it cut because `release --blocked --on "external: ready for integration"` already yields the handoff state (documented by the protocol-refresh task)? Recommendation: keep it cut until a second wave shows the convention insufficient; the verified enum design is recorded in this spec for that case.
- [ ] HUMAN: Stranded work that never ages: (1) a handed-off task carries no claim, so nothing flags it (stale-claim needs claimed_at; validate has no age check for external: blocks); (2) a blocked task that retained its claim never ages either (the stale-claim branch is gated on status in_progress). Add a `stale-block` warning for `external: ready` handoffs with no Log activity for stale_claim_days (new VALIDATION_CODES entry, promoted under --strict, repaired by unblock/done/release; must not catch deliberately parked blocks such as `external: wave open`) and extend stale-claim to claim-retaining blocked tasks, or keep both process-only (integrator polls list --status blocked)? Recommendation: add both, after the handoff convention has been used once.

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Decide: first-class ready status and stranded-handoff aging
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] step: added 'Human answers both questions; unblock or drop'
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] step: added 'If a ready status is approved: implement per the verified design below and note T-2e587s about SCHEMA_VERSION 2'
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] step: added 'If stranded-handoff aging is approved: add the stale-block warning + lockstep fixture'
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] question: added (HUMAN): Add a sixth status `ready` (`ledger ready <id>`) as the review's #1 recommendation, reversing DESIGN decision #6, or keep it cut because `release --blocked --on "external: ready for integration"` already yields the handoff state (documented by the protocol-refresh task)? Recommendation: keep it cut until a second wave shows the convention insufficient; the verified enum design is recorded in this spec for that case.
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] question: added (HUMAN): A handed-off task carries no claim, so nothing ever flags it as forgotten (stale-claim needs claimed_at; validate has no age check for external: blocks). Add a `stale-block` warning for `blocked_on: external:` with no Log activity for stale_claim_days (new VALIDATION_CODES entry, promoted under --strict, repaired by unblock/done/release), or keep it process-only (integrator polls list --status blocked)? Recommendation: add it, scoped to external: blocks, after the convention has been used once.
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] note: Completeness pass 2026-09-01: Decision 2 widened — stale-claim is gated on status in_progress, so claim-retaining blocked tasks never age; the new warning must not catch deliberately parked blocks; 'requires T-2e587s' is deliberately not a depends_on
