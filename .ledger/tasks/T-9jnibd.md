---
id: T-9jnibd
title: ledger log: corpus-wide read-only Log event stream
status: in_progress
priority: p1
size: m
created: 2026-10-01T22:31:28Z
claimed_by: claude-2026-10-01-a
claimed_at: 2026-10-01T22:31:29Z
tags: cli, operator
---

## Spec

### Motivation

The human review UI (ui/, not vendored) needs a cross-task activity timeline. Today the only way to get Log lines across the corpus is one `show` per task: ~350ms each, so REAI2 (1,132 tasks) would take minutes. `list` carries no Log. A corpus-wide read command is the missing primitive; it is also the event stream an orchestrator would otherwise script by hand (compare T-j0ngsk's evidence rule).

### Design

`ledger log [--since TS|REF] [--until TS|REF] [--actor A] [--task ID] [--verb V]... [--tag TAG] [-n N] [--json]`

- Read-only, lock-free; never stored, never fed to next / done / validate; kept out of PROTOCOL_TEXT (operator diagnostics, like `report`).
- One row per parsed Log line: `{ts, actor, verb, text, task, title, status}`; newest first by timestamp, ties broken by task id then file order (Log lines are order-insensitive under merges).
- `--since` / `--until` reuse `_window_bound` (YYYY-MM-DD, Z stamp, or git ref); `--since` inclusive, `--until` inclusive.
- `--task` resolves a fragment like every other command; `--verb` is repeatable and matches the verb exactly (`note(dead-end)` is its own verb).
- `-n` caps rows (default 50, `0` = unlimited) and the cut is reported under the uniform `truncated: {events: {total, omitted, retrieve_with}}` key; `count` is the pre-cap total.
- A corrupt file is reported, not fatal (`emit_read`).
- Human output: `ts  actor  task  verb: text`.

### Release

Lands in 1.6.0 (TOOL_VERSION + pyproject); the protocol text is unchanged, so PROTOCOL_VERSION stays 17.

## Next Steps

- [x] Implement cmd_log + parser entry
- [x] Tests in tests/test_log.py
- [x] DESIGN.md §5 + README command docs
- [x] Bump TOOL_VERSION/pyproject to 1.6.0 -- MOOT: the bump ships under T-j4rolv (release task)

## Open Questions

## Commits

## Log

- 2026-10-01T22:31:28Z [claude-2026-10-01-a] add: created: ledger log: corpus-wide read-only Log event stream [p1/m] (tags: cli, operator)
- 2026-10-01T22:31:29Z [claude-2026-10-01-a] claim: claimed
- 2026-10-01T22:31:34Z [claude-2026-10-01-a] step: added 'Implement cmd_log + parser entry'
- 2026-10-01T22:31:34Z [claude-2026-10-01-a] step: added 'Tests in tests/test_log.py'
- 2026-10-01T22:31:35Z [claude-2026-10-01-a] step: added 'DESIGN.md §5 + README command docs'
- 2026-10-01T22:31:35Z [claude-2026-10-01-a] step: added 'Bump TOOL_VERSION/pyproject to 1.6.0'
- 2026-10-01T22:34:44Z [claude-2026-10-01-a] step: checked 'Implement cmd_log + parser entry'
- 2026-10-01T22:34:44Z [claude-2026-10-01-a] step: checked 'Tests in tests/test_log.py'
- 2026-10-01T22:34:44Z [claude-2026-10-01-a] step: checked 'DESIGN.md §5 + README command docs'
- 2026-10-01T22:34:44Z [claude-2026-10-01-a] step: checked 'Bump TOOL_VERSION/pyproject to 1.6.0 -- MOOT: the bump ships under T-j4rolv (release task)'
- 2026-10-01T22:34:45Z [claude-2026-10-01-a] note: REAI2 (1,132 tasks, 11,028 Log lines): log -n 0 --json in ~0.5s vs one show per task (~350ms each).
