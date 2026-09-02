---
id: T-jqulvk
title: Batch git subprocess calls in validate
status: blocked
priority: p3
size: s
created: 2026-08-28T03:02:19Z
blocked_on: external: validate --coverage measurably slow on a real history
tags: performance
---

## Spec

validate spawns one 'git rev-parse' per cached ## Commits line (sha-unreachable) and one 'git diff-tree' per untrailered commit. On large histories this is O(N) process spawns. Batch with 'git cat-file --batch-check' for sha existence and a single 'git log --name-only' pass for file lists. Only worth doing once a real project shows measurable validate latency.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T03:02:19Z [claude-2026-08-27-a] add: created: Batch git subprocess calls in validate
- 2026-09-02T00:55:00Z [claude-2026-09-01-b] block: on external: validate --coverage measurably slow on a real history — observe-first; measured 2026-09-01: validate --coverage --strict 0.8s over this repo's full history
- 2026-09-02T02:51:59Z [claude-2026-09-01-b] note: T-zl7jh5 landed 2026-09-01: with exempt_allowed_paths set, every explicit-exempt commit and every pattern-exempt true merge costs one git diff-tree in validate --coverage and scan; include exempt commits in the batching scope when this task is triggered
