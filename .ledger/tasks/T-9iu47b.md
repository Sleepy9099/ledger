---
id: T-9iu47b
title: Wave-as-task convention: dependents lookup, list --depends-on, journaled add
status: todo
priority: p2
size: s
created: 2026-09-01T23:48:39Z
tags: orchestration
---

## Spec

### Motivation (review §12, §13, §26; DESIGN §8, §11)

The review asks for a Wave object above tasks recording selected members, orchestrator, start/end, final commit, validation result and anomalies. DESIGN §11 leaves epics/sprints out and §8 says a big task is split into peers the parent depends_on. Verified 2026-09-01 in a scratch repo that an ordinary task tagged `wave` whose `depends_on` lists the selected members already gives almost all of it: `add "Wave N: ..." --tag wave --after m1 --after m2` (fragments resolve; `_clean_tag` accepts anything but commas); `next` offers it only when every member is `done` and `compute_eligible` names each unmet member with its status; the orchestrator's `claim W` at wave start ignores depends_on and hides W from workers' `next --claim`; `done W --commit <sha>` accepts a merge commit (`git_resolve_commit` uses `ref^{commit}`) and a `.ledger/`-only stamp commit also satisfies done-evidence; `note`/`link` work after close for suite results and anomalies; older vendored copies see an ordinary task file. What is missing is ergonomic: no reverse lookup (`task_full` has no dependents; `list` has no `--depends-on`; today `list --json` rows expose depends_on and need a client-side filter), the initial selection is not journaled (`add` logs only `created: <title>`; only `set` journals `depends_on + -> T-x` / `depends_on - -> T-x` — note cmd_set's exact `{field} {old} -> {new}` text), and the convention is undocumented. Enforcement is deliberately left alone: `cmd_done` never consults depends_on (a wave can be stamped with members open, exit 0, validate clean) — that is T-naq65o's question.

### Design (tool)

1. `task_full` gains `"dependents": [ids]` — every task of any status whose `depends_on` contains this id, in `sort_key` order; computed on read, never stored. `task_full` is also used by `next` (which already holds the task list); `cmd_show` must call `load_all_tasks` itself (`load_task_or_die` returns only the single Task) or `task_full` takes an optional `all_tasks` parameter. `show` human output adds `# dependents: T-a, T-b` next to `# effective_commits:`.
2. `list --depends-on <id-fragment>`: resolve via `load_task_or_die` (read-only ctx, no lock; `no-such-task` / `ambiguous-id` exit 2), keep tasks whose depends_on contains it; composes with `--tag`, `--status`, `--claimed`. "Which wave was T-x in" = `ledger list --depends-on T-x --tag wave`. `list --tag` stays single-valued and exact.
3. `add` journals the initial selection: Log text `created: <title> [<priority>/<size>]` plus ` (after: T-a, T-b)` (fully resolved, de-duplicated ids in the given order — the same string written to the header) and ` (tags: a, b)` when present. The `created: ` prefix is kept so old and new corpora read uniformly; no code parses Log text, and no existing test pins the add Log text (tests check verb/actor only).
4. No new header key, status, validation code or directory.

### Design (convention — documented as an expansion of DESIGN §8 and in README; PROTOCOL_TEXT untouched)

- Open: `ledger add "Wave N: <objective>" -p p1 -s s --tag wave --after <m1> ...`, then `ledger claim <W>` — the claim is the "wave open" marker. The `claim:` Log line (actor + timestamp) is the durable record of who opened the wave and when, because `done` strips claimed_by/claimed_at. `note <W>` at each integration step keeps the claim fresh: after `stale_claim_days` (default 7) a stale wave claim is a `stale-claim` warning (error under --strict) and, once every member is done, a takeover candidate for any worker's `next --claim`. At orchestrator session end while the wave is open, do NOT plain-`release W` (it returns to todo and becomes claimable once members are done); keep the claim, or `release W --blocked --on "external: wave open"` and resume with `unblock W` + `claim W` (a `note W` while parked keeps the block's Log activity fresh should T-ik6wl7's stale-block warning be adopted).
- Only the orchestrator writes W's header (`set W --remove-depends`, `claim`, `done`). A worker that drops a member notes the reason on the member and IGNORES drop's `set W --remove-depends` fix_hint — the orchestrator applies it on the integration branch, keeping W's depends_on line to a single writer (DESIGN §7(d)). The Log (the add line with `(after: ...)` plus `set: depends_on - -> <m>` lines) is the durable record of the selected set; Next Steps holds the orchestrator's integration steps only — do not repurpose checkboxes as a member list (review §21).
- Close: `ledger done <W> --commit <integration sha>` (a merge commit carrying `Ledger-Task: <W>` in its final paragraph is the natural close; the Log records `done: evidence: <sha7>[, ...]` — every ## Commits line). `done W` records an orchestrator assertion; the tool verifies nothing about member closure — check members with `show W` (depends_on) or `list --depends-on`; `next`'s why cannot help while W is claimed (the fresh-claim branch returns before the depends_on check).
- Wave record: `note <W> "suite: ...; lint: ...; workers: N; anomalies: ..."` — allowed after close. Lookup: `show <m>` → dependents; `list --depends-on <m> --tag wave`; `list --tag wave --status done` lists finished waves. The wave task carries the canonical `wave` tag (so `list --tag wave` lists waves) plus a per-wave `wave:<slug>` tag; members and any work discovered mid-wave carry `wave:<slug>` too (`add ... --tag wave:<slug>`, `set <id> --add-tag wave:<slug>`) — discovered work must NOT be added to W's depends_on, which would gate the wave's own close. `list --tag wave:<slug>` then lists selected plus discovered work, the population T-00mrm7 reports on. `list --tag` is single-valued, so filter on one tag per call; put date/objective in the title.

### DESIGN.md principles

A wave IS a task file — nothing new on disk; dependents are computed on read (no shared mutable file); the only write change is more text on the append-only add Log line; ~40 lines. §8's parent-depends_on-peers rule applied to a sprint-shaped grouping; §11 excludes waves as a TOOL feature and this task adds zero wave-specific surface (the three tool changes are generic dependency-graph ergonomics). The DESIGN paragraph must cross-reference §11 and state that any future wave-specific tool surface (field, status, command, directory, metric) is a §11 reversal to be routed through a human question.

### Backward compatibility

Older copies parse, validate and schedule a wave task identically; they merely lack `--depends-on` and the `dependents` field (additive). The changed add Log line is free text; log-tamper compares whole lines.

### Tests

- tests/test_cli.py: `show` of a member lists the wave in `dependents` (also when the wave is done) and `next --json` carries it; `list --depends-on <m>` returns exactly the dependents and composes with `--tag wave`; ambiguous/unknown fragment → exit 2.
- Add Log line: `created: First task [p1/s] (tags: alpha)` (test_add_show_shapes), `(after: T-...)` suffix (test_add_spec_from_stdin_and_after), plain `created: <title>` otherwise.
- tests/test_git_integration.py end-to-end: members + wave, claim wave, trailered member commits, merge with `Ledger-Task: <W>` in the final paragraph, `done <W> --commit HEAD`, `validate --coverage --strict` clean, `scan` classifies the merge as linked.
- tests/test_property.py: extend op_add to randomly pass `--after <existing id>` and `--tag`.
- README "Daily commands": add `add ... [--after id] [--tag t]` and `list [--depends-on id]` (neither --after nor --tag is listed today).

## Next Steps

- [ ] task_full gains dependents (computed on read; show + next); show human line
- [ ] list --depends-on <fragment>; add journals [prio/size] (after: ...) (tags: ...)
- [ ] DESIGN §8 expansion + §11 cross-reference; README Daily commands rows for add --after/--tag and list --depends-on
- [ ] Tests: dependents/depends-on, add Log line, end-to-end wave scenario in test_git_integration, op_add extension in test_property

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: Wave-as-task convention: dependents lookup, list --depends-on, journaled add
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'task_full gains dependents (computed on read; show + next); show human line'
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'list --depends-on <fragment>; add journals [prio/size] (after: ...) (tags: ...)'
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'DESIGN §8 expansion + §11 cross-reference; README Daily commands rows for add --after/--tag and list --depends-on'
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'Tests: dependents/depends-on, add Log line, end-to-end wave scenario in test_git_integration, op_add extension in test_property'
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] note: Completeness pass 2026-09-01: per-wave `wave:<slug>` tag on members and mid-wave discovered work (depends_on cannot hold discovered work without gating the wave's close); parked-wave note re stale-block aging
