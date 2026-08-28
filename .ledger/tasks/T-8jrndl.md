---
id: T-8jrndl
title: Derived read cache for large ledgers
status: todo
priority: p3
size: l
created: 2026-08-28T02:34:33Z
tags: performance
---

## Spec

Directory scans are O(n) per command; below ~2k tasks this is fine. If a project outgrows that, add a gitignored derived cache (.ledger/cache.json) rebuilt on demand and NEVER committed - format stays unchanged. Trigger: ledger list latency noticeably slow on real projects.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T02:34:33Z [claude-2026-08-27-a] add: created: Derived read cache for large ledgers
