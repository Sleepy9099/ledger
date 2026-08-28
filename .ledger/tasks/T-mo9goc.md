---
id: T-mo9goc
title: Optional pipx/uvx packaging shim
status: todo
priority: p3
size: m
created: 2026-08-28T02:34:33Z
tags: distribution
---

## Spec

Keep .ledger/ledger.py single-file deploy as the primary channel. Add a thin pyproject entry point so 'uvx ledger' / 'pipx run' work for humans who want a global command. Must not add runtime dependencies or break the copy-one-file bootstrap.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T02:34:33Z [claude-2026-08-27-a] add: created: Optional pipx/uvx packaging shim
