---
id: T-a3yss4
title: ledger repair: journaled header repair for merge/hand-edit incoherence, with state-coherence fix_hints
status: done
priority: p1
size: s
created: 2026-09-02T11:44:58Z
closed: 2026-09-02T12:02:17Z
tags: integrity, ergonomics
---

## Spec

### Defect (sweep 2026-09-02, ergonomics #3; verified)

Five state-coherence errors (claim fields on a closed task, missing/extra closed, blocked_on on a non-blocked task, unpaired claim fields) ship with no fix_hint, no CLI verb accepts the state, and the protocol both forbids hand edits and (for merges) instructs them.

### Design

- `ledger repair <id>`: derives the coherent header from status and the Log — drops claim fields on done/dropped or todo, drops blocked_on when not blocked, sets/drops `closed` from the closing Log line, pairs claimed_at with claimed_by (from the newest claim line) — reports each change, journals one `repair:` line, refuses (`nothing-to-repair`) when already coherent, never touches sections. Add `repair` to the closed-task allowlist.
- Every state-coherence violation gets a fix_hint naming `ledger repair <id>` (and, for a closing line vs open status, the two resolutions).
- PROTOCOL Never line: "never edit headers ... by hand EXCEPT to resolve a merge conflict (then `ledger repair <id>` + `validate`)". Header-conflict line: name `repair`.
- Tests: each incoherent state repaired to strict-clean; Log line; refusal when coherent; unknown keys untouched.

## Next Steps

## Open Questions

## Commits

- c3745e3 2026-09-02 ledger repair: journaled header repair with state-coherence hints

## Log

- 2026-09-02T11:44:58Z [claude-2026-09-01-b] add: created: ledger repair: journaled header repair for merge/hand-edit incoherence, with state-coherence fix_hints [p1/s] (tags: integrity, ergonomics)
- 2026-09-02T11:58:53Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T12:02:16Z [claude-2026-09-01-b] link: c3745e3 ledger repair: journaled header repair with state-coherence hints
- 2026-09-02T12:02:17Z [claude-2026-09-01-b] done: evidence: c3745e3
