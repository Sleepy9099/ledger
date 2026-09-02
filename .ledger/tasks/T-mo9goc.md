---
id: T-mo9goc
title: Optional pipx/uvx packaging shim
status: in_progress
priority: p3
size: m
created: 2026-08-28T02:34:33Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T03:29:39Z
tags: distribution
---

## Spec

Keep .ledger/ledger.py single-file deploy as the primary channel. Add a thin pyproject entry point so 'uvx ledger' / 'pipx run' work for humans who want a global command. Must not add runtime dependencies or break the copy-one-file bootstrap.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T02:34:33Z [claude-2026-08-27-a] add: created: Optional pipx/uvx packaging shim
- 2026-09-02T03:29:39Z [claude-2026-09-01-b] claim: claimed
