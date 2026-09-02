---
id: T-h65ecn
title: linked-never-claimed fix_hint must name the remedy for the state you are in
status: done
priority: p2
size: xs
created: 2026-09-02T08:54:44Z
closed: 2026-09-02T09:16:32Z
tags: ergonomics
---

## Spec

### Defect (heavy-session feedback 2026-09-02, #4)

The hint says "claim tasks before committing against them" — true and useless once the commit has landed. The warning clears as soon as a `claim` Log line exists.

### Design

Hint: "the commit has landed — record the engagement now: `ledger claim <id>` then `ledger release <id> --note '...'` (or `ledger done <id>` if the work is finished); the warning clears once a claim line exists. Going forward, claim before committing." Test asserts the hint names claim + release and that claim/release clears it.

## Next Steps

## Open Questions

## Commits

- 62fd891 2026-09-02 init reports tool_copied; linked-never-claimed names the live remedy; scan --exempt-policy-preview is the dry run before the switch

## Log

- 2026-09-02T08:54:44Z [claude-2026-09-01-b] add: created: linked-never-claimed fix_hint must name the remedy for the state you are in [p2/xs] (tags: ergonomics)
- 2026-09-02T09:12:54Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T09:16:32Z [claude-2026-09-01-b] link: 62fd891 init reports tool_copied; linked-never-claimed names the live remedy; scan --exempt-policy-preview is the dry run before the switch
- 2026-09-02T09:16:32Z [claude-2026-09-01-b] done: evidence: 62fd891
