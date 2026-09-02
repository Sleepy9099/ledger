---
id: T-rgawkv
title: HITL authority: document that answers are session-recorded, not proven human; operator-only command split is host-specific
status: done
priority: p3
size: xs
created: 2026-09-02T04:51:27Z
closed: 2026-09-02T05:14:15Z
tags: human-decisions, docs
---

## Spec

### Finding (review 2026-09-02, finding 6)

Any session can `question resolve` or `answers apply`; the recorded actor is the applying session, so the ledger cannot prove a human supplied the answer. Acceptable for the honest-agent local model (DESIGN §3) but it must not be described as an enforceable approval boundary.

### Design

Docs only now: README (questions/answers section) and DESIGN §3 trust model state it plainly — the HUMAN: marker records who SHOULD decide, the answer line records who APPLIED it. A model-safe vs operator-only command split depends on the host sandbox (which commands an autonomous agent may run): record as an open host-integration question, not a tool change; revisit if a host needs enforcement (then a signed or out-of-band answer channel is the design, not a flag).

## Next Steps

## Open Questions

## Commits

- b755b0c 2026-09-02 State the HITL trust boundary plainly

## Log

- 2026-09-02T04:51:27Z [claude-2026-09-01-b] add: created: HITL authority: document that answers are session-recorded, not proven human; operator-only command split is host-specific [p3/xs] (tags: human-decisions, docs)
- 2026-09-02T05:14:14Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T05:14:15Z [claude-2026-09-01-b] link: b755b0c State the HITL trust boundary plainly
- 2026-09-02T05:14:15Z [claude-2026-09-01-b] done: evidence: b755b0c
