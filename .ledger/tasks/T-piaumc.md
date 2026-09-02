---
id: T-piaumc
title: Small fixes from the 2026-09-02 review: post-claim resources_held, stale_takeover on self-refresh, config type validation, answers-apply wording
status: todo
priority: p2
size: xs
created: 2026-09-02T04:51:27Z
tags: hygiene
---

## Spec

### Items (all verified)

1. `next --claim` reports the PRE-claim `resources_held` (computed before apply_claim): recompute after the claim so the just-leased resources appear.
2. Refreshing one's own stale claim through `next --claim` reports `stale_takeover: true` although no takeover occurred: `stale_takeover` = a takeover from ANOTHER actor happened.
3. Malformed config types (`stale_claim_days: "x"`, `exempt_patterns: "str"`, `prefix: 5`, `baseline: 3`) raise uncaught exceptions instead of the `config` envelope: validate types once in make_ctx (LedgerError config, exit 2, fix_hint naming the key and the expected type).
4. README describes `answers apply` as all-or-nothing; it is prevalidated and resumable but writes one file at a time — say so.
Tests for 1–3.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T04:51:27Z [claude-2026-09-01-b] add: created: Small fixes from the 2026-09-02 review: post-claim resources_held, stale_takeover on self-refresh, config type validation, answers-apply wording [p2/xs] (tags: hygiene)
