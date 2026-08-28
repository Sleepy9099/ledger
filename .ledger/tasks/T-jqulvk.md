---
id: T-jqulvk
title: Batch git subprocess calls in validate
status: todo
priority: p3
size: s
created: 2026-08-28T03:02:19Z
tags: performance
---

## Spec

validate spawns one 'git rev-parse' per cached ## Commits line (sha-unreachable) and one 'git diff-tree' per untrailered commit. On large histories this is O(N) process spawns. Batch with 'git cat-file --batch-check' for sha existence and a single 'git log --name-only' pass for file lists. Only worth doing once a real project shows measurable validate latency.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T03:02:19Z [claude-2026-08-27-a] add: created: Batch git subprocess calls in validate
