---
id: T-y7j9tx
title: Decide: enforce 'committed while claimed' (linked-outside-claim)
status: blocked
priority: p3
size: s
created: 2026-09-01T23:48:40Z
blocked_on: human
tags: ownership, decision
---

## Spec

### Context (review §7)

The review's invariant is "every task advanced by a worker was explicitly claimed by that worker" (it scores ownership 10/10 for the observed wave). The tool enforces less, by design: `linked-never-claimed` flags a trailered commit only when the task is todo/blocked AND no `claim` Log line ever existed. Verified 2026-09-01: (1) after claim + release, any later trailered commit by anyone passes `--strict` — DESIGN §6 documents this as intended because the claim line survives; (2) a commit against a task another session holds FRESH passes `--strict`. The "by that worker" half is structurally unenforceable: git author identity and LEDGER_SESSION are unrelated strings (`resolve_actor`: flag > env > git user.name) and no trailer carries the session. Claims are advisory across branches (DESIGN §5, §7(f)); the tool DOES enforce fresh-foreign-claim refusal on claim/release/done/drop, stale takeover with a Log line, and same-checkout serialization.

### Options (Open Questions)

(A) `linked-outside-claim`: build claim windows from the Log — `claim` opens; `release` (including `--blocked`) or a takeover `claim` by another actor closes; `block` keeps the claim and is not a closer; closed tasks are skipped and no reopen exists — and flag trailered commits whose author date falls outside every window. `Commit.date` already holds the author date at day precision (`%as`); second precision needs `%at` / `%aI` as a 7th walk field plus aware-datetime parsing (`parse_ts` accepts only Z stamps). It catches only hole (1), and with a ±1 day tolerance only commits landing more than a day after a release; hole (2) is inside the holder's window and invisible; squash merges rewrite author dates to merge time, so a false positive on an OPEN task has NO repair (claiming now opens a window at now; notes are invisible; the Log is append-only) — a permanent `--strict` failure of the class the `linked-never-claimed` comment forbids, unless the code is emitted at `info` tier (never promoted) or paired with an acknowledgement mechanism. It would also flag every integrator commit against a not-yet-closed task under the review's own §10 model, and widens the check to in_progress tasks. (B) a `Ledger-Session: <actor>` trailer matched to the claim actor — true "by that worker" for commits carrying it; extends the trailer key set (decision #10 ruled explicit keys over an overloaded one and cut an inline syntax; it did not fix the count at two) but runs against decision #14 (per-write ceremony agents fumble) and the §3 trust model (a session trailer is an agent assertion, not git truth); needs TRAILER_RE and `_parse_trailers` changes. (C) keep claims advisory; revisit only when a wave shows commits landing against unclaimed-but-once-claimed tasks. Recommendation: C. If evidence appears: A at `info` tier before B.

### Related

T-fkywmw (write-path claim nonce — different mechanism, same defer-until-observed stance); T-jqulvk (touches the walk format); T-ik6wl7.

## Next Steps

- [ ] Human picks A/B/C; if C, drop this task with the answer as --why
- [ ] If A: implement at info tier with the interval rules below; if B: extend TRAILER_RE/_parse_trailers and the claim-actor match

## Open Questions

- [ ] HUMAN: Enforce 'committed while claimed'? (A) `linked-outside-claim` from Log claim windows vs commit author dates — catches only commits landing outside every window, misses commits during a foreign fresh claim, and a squash-merge false positive on an open task has no repair unless emitted at `info` tier; (B) a `Ledger-Session:` trailer matched to the claim actor — true 'by that worker' but per-commit ceremony (decision #14) and an agent assertion (§3 trust model); (C) keep claims advisory as DESIGN §5/§7(f) rule and revisit only if a wave shows commits landing against unclaimed-but-once-claimed tasks. Recommendation: C; if evidence appears, A at info tier before B.

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Decide: enforce 'committed while claimed' (linked-outside-claim)
- 2026-09-01T23:48:47Z [claude-2026-09-01-a] step: added 'Human picks A/B/C; if C, drop this task with the answer as --why'
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] step: added 'If A: implement at info tier with the interval rules below; if B: extend TRAILER_RE/_parse_trailers and the claim-actor match'
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] question: added (HUMAN): Enforce 'committed while claimed'? (A) `linked-outside-claim` from Log claim windows vs commit author dates — catches only commits landing outside every window, misses commits during a foreign fresh claim, and a squash-merge false positive on an open task has no repair unless emitted at `info` tier; (B) a `Ledger-Session:` trailer matched to the claim actor — true 'by that worker' but per-commit ceremony (decision #14) and an agent assertion (§3 trust model); (C) keep claims advisory as DESIGN §5/§7(f) rule and revisit only if a wave shows commits landing against unclaimed-but-once-claimed tasks. Recommendation: C; if evidence appears, A at info tier before B.
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
