---
id: T-8jrndl
title: Derived read cache for large ledgers
status: blocked
priority: p3
size: l
created: 2026-08-28T02:34:33Z
blocked_on: external: ledger list measurably slow on a real project
tags: performance
---

## Spec

Directory scans are O(n) per command; below ~2k tasks this is fine. If a project outgrows that, add a gitignored derived cache (.ledger/cache.json) rebuilt on demand and NEVER committed - format stays unchanged. Trigger: ledger list latency noticeably slow on real projects.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T02:34:33Z [claude-2026-08-27-a] add: created: Derived read cache for large ledgers
- 2026-09-02T00:55:00Z [claude-2026-09-01-b] block: on external: ledger list measurably slow on a real project — observe-first; this repo: list 0.2s at 27 tasks
