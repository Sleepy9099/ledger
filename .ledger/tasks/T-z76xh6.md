---
id: T-z76xh6
title: ledger-ui: scaffold, LedgerClient adapter, project registry, worktrees
status: todo
priority: p1
size: m
created: 2026-10-01T22:31:28Z
tags: ui
---

## Spec

### Intent

A human-facing review UI for any repo's ledger, living in this repo under `ui/` and NEVER vendored: `init` copies only `.ledger/ledger.py`, the root pyproject packages only the `ledger` module (zero deps), and `ui/` gets its own `pyproject.toml` (`ledger-ui`, depends on NiceGUI). Decisions agreed with the human on 2026-10-01:

- Read-only in v1. No mutation verbs are exposed, not even `question resolve`; the Human Inbox shows a copyable `answers apply` command instead.
- Python (NiceGUI), maintainable and attractive. Browser tab by default; `--native` opens a desktop window (pywebview, optional extra).
- Points at other ledgers: OSBF, REAI2, recurrent_moe_expert are the first three. Project paths live in a user-level registry (`%APPDATA%\ledger-ui\projects.json` / `~/.config/ledger-ui/projects.json`), never inside a repo; never task state.
- Each project expands to its main checkout plus `git worktree list` entries; a worktree without `.ledger/ledger.py` is listed and skipped. Branches without a worktree are out of scope.
- Operator identity: every call passes `--session HUMAN`.

### Architecture

- `LedgerClient(checkout)`: runs `<checkout>/.ledger/ledger.py <cmd> --json --session HUMAN` with cwd=checkout and returns the decoded envelope `{ok, data, errors}`. The UI never parses or writes task Markdown and never re-implements ledger semantics: the target's own vendored copy is the authority for that repo.
- Capability gate from `doctor --json`: minimum 1.5.0; features keyed on tool_version (Activity needs 1.6.0 `log`).
- Calls run concurrently in a thread pool; results cached per (checkout, command) and invalidated when the newest mtime under `.ledger/tasks/` (or HEAD for git-backed calls) changes. `validate --coverage` is slow (20s on OSBF), so it runs only on demand in the background, cached by HEAD + task-dir stamp.
- Pure-Python view-model layer (attention items, counts, graph shaping) separated from NiceGUI pages so it is unit-testable without a browser.

### Tests

`ui/tests/` (separate from the core suite): client envelope decoding, capability gating, registry round-trip, worktree parsing, view-model derivations against a temp ledger driven by the real CLI.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-10-01T22:31:28Z [claude-2026-10-01-a] add: created: ledger-ui: scaffold, LedgerClient adapter, project registry, worktrees [p1/m] (tags: ui)
