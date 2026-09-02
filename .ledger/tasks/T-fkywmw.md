---
id: T-fkywmw
title: Claim lease nonce (compare-and-swap)
status: blocked
priority: p3
size: s
created: 2026-08-28T11:54:59Z
blocked_on: external: a stale-process overwrite observed after a takeover
depends_on: T-q59p4n
tags: concurrency
---

## Spec

Optional strengthening after the cross-process lock lands: give each claim a random claim_generation nonce; mutations from a claiming session present it, so a long-stale process cannot overwrite a task after takeover. Reviewer and we agree this is NOT needed if all mutations re-check ownership under the global lock - implement only if stale-process overwrites are observed in practice.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T11:54:59Z [claude-2026-08-28-a] add: created: Claim lease nonce (compare-and-swap)
- 2026-09-02T00:55:00Z [claude-2026-09-01-b] block: on external: a stale-process overwrite observed after a takeover — observe-first by its own spec; blocked on the trigger so next explains it instead of dispatching it
