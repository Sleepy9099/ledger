---
id: T-ntt2zz
title: ledger search: ranked text search across task files
status: todo
priority: p2
size: s
created: 2026-09-01T23:48:39Z
tags: discovery, ergonomics
---

## Spec

### Motivation (review §9, §18, §28 item 4)

The review's one ergonomic recommendation: before filing, search existing tasks for the symbol / component / error; if an owner exists, enrich it, depend on it or link to it. A high dropped-duplicate rate means titles and specs are hard to retrieve. Today the tool has no cross-task text retrieval at all: `cmd_list` filters only header enums and one exact tag (`args.tag not in task.tags` — verified `list --tag perf` misses a `performance` tag); `load_task_or_die` resolves fragments against ids only (`show cache` → `no-such-task`, `show 8jr` → T-8jrndl); the only substring matching is the per-task step/question selector in `_resolve_checkbox_line`. An agent asking "is there already a task about the tokenizer?" must grep `.ledger/tasks/` and gets filenames with no status, ranking or snippet. Duplicate prevention today is 100% agent discipline.

### Command

```
ledger search TERM [TERM ...] [--any] [--regex] [--in FIELD[,FIELD...]]
              [--status S]... [--open] [-n N] [--json]
```

- Read-only: `make_ctx(args)` without the mutation lock; scans through the existing `load_all_tasks` (so T-8jrndl's cache, if it ever lands, speeds it up for free). Parse/encoding problems pass through in `errors` exactly as `cmd_list` does.
- Matching: each TERM is a case-insensitive literal substring; `--regex` switches every term to `re.search(term, text, re.I)`. Terms AND by default (every term must hit somewhere in the task, not necessarily in the same field); `--any` makes it OR.
- Fields (`--in`, comma-separated, default all) are defined over RAW section text so nothing in a task file is unreachable: `id`, `title` (header values); `tags` (Task.tags); `spec` = get_section("Spec"); `steps` = get_section("Next Steps"); `questions` = get_section("Open Questions") (so `HUMAN:` markers and continuation prose match); `commits` = get_section("Commits") lines; `log` = get_section("Log") lines (verb and text both match). Do NOT build fields from `steps()`/`questions()`/`log()` — they drop prose, the HUMAN prefix and verbs.
- Status: default ALL statuses (a done task answers "already fixed"; a dropped one usually names the canonical task). `--open` restricts to OPEN_STATUSES; `--status` is repeatable with the same choices as `list`.
- Ranking: field weights title 8, id 6, tags 6, spec 4, steps 3, questions 3, commits 2, log 1. Score = sum over terms of the highest-weight field that term hit, plus 1 if the task is open. Ties fall back to `sort_key` (priority, created, id). Weights are code constants — not config keys, never stored (this is not the stored rank cut by decision #16).
- `-n N` caps rows (default 20, mirroring `next -n`); `count` reports the total before the cap.
- Usage errors (unknown `--in` field, invalid `--regex` term) are raised as `LedgerError("usage", ..., exit_code=3)` from cmd_search (precedent `_check_section_body`), NOT via argparse `choices`, so `--json` callers still get the envelope. Zero hits → exit 0, `ok: true`, `count: 0` — an empty result is an answer.
- JSON: `{"query": {terms, mode, regex, fields}, "count", "tasks": [{...task_brief..., "score", "matched_in": [...], "snippets": {field: first matching raw line, whitespace-collapsed, ≤160 chars centred on the hit}}]}`. Human mode: one row `T-xxxxxx  status  p2  m  title  [title,spec]` plus one indented snippet per matched field.

### Protocol change

Edit the "Discover new work?" bullet in PROTOCOL_TEXT only (the single source): "Discover new work? First `ledger search <symbol|component|error> --json`. An open task already covers it → enrich it (`ledger note` / `ledger step <id> add`); new work that must follow it → `ledger add ... --after <id>`; nothing → `ledger add "title" -p p2 -s s --spec -`." Then re-run `python .ledger/ledger.py init` in this repo so `.ledger/PROTOCOL.md` (written verbatim) and the CLAUDE.md marker block regenerate; commit them together. Also: DESIGN §5 command list, DESIGN §9 summary ("search, then add"), README "Daily commands" block, and a DESIGN Appendix decision 25: "`search` is an on-demand O(n) scan over `load_all_tasks`; no index or cache file — the derived cache remains T-8jrndl's separate, opt-in decision."

### DESIGN.md principles

Writes nothing; no index, cache or daemon (§1, §11); stdlib `re` only; no header/Log change. §11 cuts spec-EDITING commands because agents edit prose better with their own tools; `search` stays on the CLI side of that line because it is structure-aware (parsed header enums, section-typed hits, task_brief rows in the decision-17 envelope) rather than a grep replacement; `git grep T-xxxxxx` remains the answer for a known id. `search` never calls git and never feeds `validate`, `done` or coverage — a `commits` hit is a cache-line match (§4), results are retrieval hints. It is an advisory protocol step; the unavoidable command is `add`, which is why the sibling task T-3bryhm adds an add-time pre-flight.

### Backward compatibility

No file-format, header, enum, Log or validate change. On a pre-search vendored copy the failure is argparse-level: exit 3, EMPTY stdout, usage text on stderr — no JSON envelope; agents should treat a JSON decode failure on `ledger search` as "stale copy; run `ledger doctor`" (T-2e587s).

### Tests (new tests/test_search.py plus additions)

- A title hit outranks a spec-only hit outranks a log-only hit; equal scores fall back to priority order; an open task outranks a closed one at equal field score.
- AND vs `--any`; `--in title` excludes a spec-only hit; `--regex` matches `parse_[a-z]+`; invalid regex → exit 3, code `usage`, envelope present; unknown `--in` field → same (pattern: test_usage_errors_exit_3).
- Default includes done and dropped; `--open` and `--status dropped` filter; `-n 1` caps rows while `count` reports the total.
- Snippet contains the term and is ≤ 160 chars; a term hitting only the id resolves (beside test_id_fragment_resolution, which stays id-only for `show`).
- A structurally broken task file still yields a `parse` entry in `errors` without aborting (mirror of list).
- `("search", "x")` added to test_every_command_emits_envelope (tests/test_cli.py) and to the read-only command list in tests/test_concurrency.py (lock-free pinned).
- New assertion (none exists on wording today) that PROTOCOL_TEXT and init's CLAUDE.md block contain `ledger search`.

## Next Steps

- [ ] Implement cmd_search over load_all_tasks with raw-section fields, AND/--any, --regex, --in, --status/--open, -n, snippets
- [ ] Edit the 'Discover new work?' bullet in PROTOCOL_TEXT; re-run init in this repo; README Daily commands; DESIGN §5/§9 and Appendix decision 25
- [ ] tests/test_search.py plus envelope and lock-free list entries

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: ledger search: ranked text search across task files
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'Implement cmd_search over load_all_tasks with raw-section fields, AND/--any, --regex, --in, --status/--open, -n, snippets'
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'Edit the 'Discover new work?' bullet in PROTOCOL_TEXT; re-run init in this repo; README Daily commands; DESIGN §5/§9 and Appendix decision 25'
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'tests/test_search.py plus envelope and lock-free list entries'
