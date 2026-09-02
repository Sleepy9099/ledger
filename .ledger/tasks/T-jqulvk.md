---
id: T-jqulvk
title: Batch git subprocess calls in validate
status: in_progress
priority: p3
size: s
created: 2026-08-28T03:02:19Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T12:30:32Z
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
- 2026-09-02T11:25:18Z [claude-2026-09-01-b] note: Trigger measured 2026-09-02 on this repo (82 commits): validate --coverage 2.0s / 45 git calls, scan 1.8s / 40, report 4.9s / 123. Breakdown: 37 per-commit diff-tree --name-only calls (one per bookkeeping/unlinked classification) in each of the three, plus 85 rev-parse --show-toplevel in report because Ctx.repo is a PROPERTY re-running git on every access. Plan: cache Ctx.repo; one  pass caching file lists on Commit (root commits and combined merge diffs included), used by classify_commit and exempt_policy_offenders; keep the per-sha rev-parse only for link/baseline resolution.
- 2026-09-02T11:25:18Z [claude-2026-09-01-b] unblock: -> todo
- 2026-09-02T11:25:31Z [claude-2026-09-01-b] note: Correction to the previous note (a shell quoting slip dropped the command): the batch pass is: git log --cc --name-only --format=%x01%H <baseline>..HEAD (root commits show their full file list; merge commits list only combined-diff files), parsed once into a sha -> files map cached on the walk.
- 2026-09-02T12:30:32Z [claude-2026-09-01-b] claim: claimed
