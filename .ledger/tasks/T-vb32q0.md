---
id: T-vb32q0
title: Exemption policy: implicit allowance narrowed to bookkeeping paths; ledger.py re-vendoring via the default globs; config.json changes need a task
status: todo
priority: p2
size: xs
created: 2026-09-02T11:44:57Z
tags: integrity
---

## Spec

### Defect (sweep 2026-09-02, correctness #3; verified)

`exempt_policy_globs` prepends `.ledger/**`, re-admitting `.ledger/ledger.py` and `config.json` that `is_bookkeeping_path` deliberately excludes: an exempt commit that rewrites the validator and appends "." to exempt_patterns passes.

### Design

The always-allowed prefix becomes the bookkeeping set (`.ledger/tasks/**`, `.ledger/PROTOCOL.md`, `.ledger/.lock`); `.ledger/ledger.py` joins DEFAULT_EXEMPT_ALLOWED_PATHS (re-vendoring is a legitimate tooling chore a host must be able to exempt); `.ledger/config.json` is policy and needs a task trailer — README/DESIGN say so, and `init --enable-exempt-policy`'s human output tells the operator to commit the config change under a task. Tests: the attack commit is flagged; a re-vendor exemption passes; a tasks-only commit stays free.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T11:44:57Z [claude-2026-09-01-b] add: created: Exemption policy: implicit allowance narrowed to bookkeeping paths; ledger.py re-vendoring via the default globs; config.json changes need a task [p2/xs] (tags: integrity)
