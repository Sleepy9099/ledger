---
id: T-mo9goc
title: Optional pipx/uvx packaging shim
status: done
priority: p3
size: m
created: 2026-08-28T02:34:33Z
closed: 2026-09-02T03:36:54Z
tags: distribution
---

## Spec

Keep .ledger/ledger.py single-file deploy as the primary channel. Add a thin pyproject entry point so 'uvx ledger' / 'pipx run' work for humans who want a global command. Must not add runtime dependencies or break the copy-one-file bootstrap.

## Next Steps

## Open Questions

## Commits

- f6adf3b 2026-09-01 Optional pipx/uvx packaging shim around the single file

## Log

- 2026-08-28T02:34:33Z [claude-2026-08-27-a] add: created: Optional pipx/uvx packaging shim
- 2026-09-02T03:29:39Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T03:36:54Z [claude-2026-09-01-b] link: f6adf3b Optional pipx/uvx packaging shim around the single file
- 2026-09-02T03:36:54Z [claude-2026-09-01-b] done: evidence: f6adf3b
