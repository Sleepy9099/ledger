---
id: T-00mrm7
title: ledger report: derived read-only wave and backlog metrics
status: todo
priority: p3
size: m
created: 2026-09-01T23:48:40Z
depends_on: T-71aehi, T-9iu47b, T-w0emnj
tags: metrics, orchestration
---

## Spec

### Motivation (review §12, §13, §16, §17, §25, §26)

Wave summaries and risk-convergence metrics: tasks closed/opened by priority, duplicates dropped, new blockers, reproduction ratio, human questions created, dependency changes, worker counts, claim-to-close durations, commits per task. The raw facts already exist — header created/closed/priority/status, the Log verbs written at the call sites (add claim release set note step question answer block unblock link done done(no-code) drop; claim times must come from `claim` Log lines because claimed_at is popped on release/done/drop) and trailer-linked commits via `walk_commits` — but nothing aggregates them: the only aggregate figures in the tool are `exempt-ratio` and scan's bucket counts, neither time-windowed nor task-scoped. Today a wave view is a 3-command composition (`list --tag wave --json`, `scan --since <sha> --json`, `show <W> --json`). DESIGN §11 cut velocity-style features for two reasons: they rot (answered here: nothing is stored) and they invite gaming (NOT answered: per-actor counters and durations are optimizable). This task therefore consciously and partially reverses §11 — the human question is the decision point. Trigger: implement only when a second wave shows that composition being scripted by hand; record the evidence here first.

### Command

`ledger report [--since TS|REF] [--until TS] [--tag TAG] [--task ID] [--actor NAME] [--no-git] [--json]` — read-only, lock-free, writes nothing. `--since REF` resolves a git ref to its committer time (`git show -s --format=%cI`, a new format; `scan --since` is an ancestry range and stays as is; commits are still drawn from the `baseline..HEAD` walk and then filtered by time). `--tag`: population = tasks carrying TAG (a header snapshot; join-time comes from the `(tags: ...)` suffix of the add line once T-9iu47b lands, or from `set: tags + -> ` lines — before T-9iu47b, `add --tag` leaves no Log line). The wave convention (T-9iu47b) puts a per-wave `wave:<slug>` tag on members and on work discovered mid-wave, so `--tag wave:<slug>` is the population that includes discovered work. `--task ID`: population = ID's depends_on members ∪ ids in its own `set: depends_on - -> <id>` Log lines (cmd_set's `{field} {old} -> {new}` text becomes a parsed contract — pin it with a test and a comment at the write site) — "a task and its members"; do not call it `--wave` (no wave concept in the tool, DESIGN §8/§11). No stored object.

### Output (all derived; `sources` flags say which figures are lower bounds)

work.opened / closed_done / closed_dropped by priority (priority at creation replayed from the oldest `set: priority X -> Y` line); dropped_duplicates from `closed_relation` (T-71aehi) plus a labeled heuristic bucket for prose drops; ratios.reproduction = opened / closed_done (null on 0) and duplicate_rate; blockers.new = `block` lines plus `release` lines whose text starts `blocked on ` (T-w0emnj), cleared = `unblock` lines; questions.human_created / answered / human_open_end (over OPEN_STATUSES, matching `questions --human`); dependencies.added / removed from `set: depends_on + -> ` / `- -> ` lines and `add` lines carrying `(after: ...)` (T-9iu47b); priority.raised / lowered; agents.workers (distinct `claim` actors), by_actor {claims, takeovers, releases, done incl. `done(no-code)`, notes}, stranded_claims (members with claimed_by set in any status — `block` retains claims — while the parent is closed; `active_claims` while it is open) using a `claim_is_stale_at(task, days, ref_ts)` helper because `claim_is_stale` compares to now; commits (null under `--no-git`, in a non-git tree, or on walk failure — never guessed): walk_commits + classify_commit filtered to the window by one `%cI` pass — linked/exempt/unlinked/dangling counts, tasks per linked commit, linked commits per done task; `final_commit` for `--task` = the parent's effective commit that is not an ancestor of any other (`git merge-base --is-ancestor`), because cmd_done writes `--commit` args first and then trailer backfills newest-first, so `## Commits` line position never encodes recency; durations {n, median, p90, max} for created_to_closed, first_claim_to_closed, created_to_first_claim; claim_to_ready null unless a ready event exists (T-ik6wl7). Ids inside Log text are matched with an unanchored, prefix-derived regex (`re.escape(ctx.prefix) + r"-[a-z0-9]{6}(?![a-z0-9])"`, as T-5z04ex specifies — `ctx.id_pattern()` is ^$-anchored and unusable on prose), never a literal `T-`. Deliberately out of scope (review §25 families the ledger never records): validation duration, integration and environmental failures, resource waits, regressions and post-wave hotfixes — orchestrator facts that live in wave `note` prose; the report must not pretend to derive them. Human mode: a compact fixed-width table.

### DESIGN.md principles

Reads only; no index / counter / cache (T-8jrndl is a transparent accelerator if it lands); stdlib `statistics` / `datetime`; no daemons; never feeds `next`, `done` or `validate`; Log-text-derived figures inherit §3's honest-agent trust level and are labeled in `sources` — only the `commits` block is computed from git history; kept out of PROTOCOL_TEXT and documented under an "Operator diagnostics" README heading, not in "Daily commands" (core bet 1: keep the metric off the agent's lazy path). classify_commit spawns one `git diff-tree` per untrailered commit, so the commits block is O(N) subprocesses on large windows — see T-jqulvk.

### Backward compatibility

Additive command; consumes only existing verbs/text; older vendored copies are unaffected; files written by older copies yield nulls / `sources.*=false` for facts they never recorded.

### Tests

tests/test_cli.py: a small ledger exercising every counter (three priorities, a tagged member, claim, trailered commit, `done --commit HEAD`, `drop --why`, `block --on human`, `question --human`, `set --add-depends`, `set --priority`); `--since <ts>` excludes the opens but counts a later close; `--tag`; `--task` includes a member removed via `set --remove-depends` (pins the `set` text format); `--since HEAD~1` resolves; `--no-git` and the non-git `plain` fixture return `commits: null` with ok:true; `("report",)` in the envelope test; output identical before/after validate/next (no state written); `final_commit` is the stamp even when older trailered commits were backfilled after it. tests/test_dogfood.py: `report --json` on this repo returns ok.

## Next Steps

- [ ] Human answers the §11 question; unblock only once the trigger below has fired
- [ ] Implement the read-only command over headers, Log lines and walk_commits (+ one %cI pass); sources flags
- [ ] README 'Operator diagnostics' section (not Daily commands); DESIGN §5/§11 note; tests

## Open Questions

- [x] HUMAN: DESIGN §11 cut sprint/velocity features because they rot AND invite gaming. A derived, never-stored `ledger report` answers rot but not gaming (per-actor counters and duration percentiles are optimizable by the agents that write the Log). Ship as specified (recommended — kept out of PROTOCOL_TEXT, never feeds next/done/validate, documented as operator diagnostics), ship without the per-actor block, or defer until a second wave shows the 3-command composition being scripted by hand? -- ANSWERED (2026-09-02): Ship as specified, including the per-actor block. Operator criteria 2026-09-01 add 'what allows an orchestrator to accurately track what sub agents are doing and course correct' — a derived, never-stored report is exactly that view; it stays out of PROTOCOL_TEXT and never feeds next/done/validate, so gaming has no lever. The 'second wave' trigger is superseded by the operator's stated priority.

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: ledger report: derived read-only wave and backlog metrics
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] step: added 'Human answers the §11 question; unblock only once the trigger below has fired'
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] step: added 'Implement the read-only command over headers, Log lines and walk_commits (+ one %cI pass); sources flags'
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] step: added 'README 'Operator diagnostics' section (not Daily commands); DESIGN §5/§11 note; tests'
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] question: added (HUMAN): DESIGN §11 cut sprint/velocity features because they rot AND invite gaming. A derived, never-stored `ledger report` answers rot but not gaming (per-actor counters and duration percentiles are optimizable by the agents that write the Log). Ship as specified (recommended — kept out of PROTOCOL_TEXT, never feeds next/done/validate, documented as operator diagnostics), ship without the per-actor block, or defer until a second wave shows the 3-command composition being scripted by hand?
- 2026-09-01T23:48:46Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
- 2026-09-02T00:06:23Z [claude-2026-09-01-a] set: depends_on + -> T-71aehi
- 2026-09-02T00:06:23Z [claude-2026-09-01-a] set: depends_on + -> T-9iu47b
- 2026-09-02T00:06:23Z [claude-2026-09-01-a] set: depends_on + -> T-w0emnj
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] note: Consistency pass 2026-09-01: depends_on T-71aehi/T-9iu47b/T-w0emnj (consumes their Log formats); tag join-time wording fixed; id regex must be unanchored (ctx.id_pattern is ^$-anchored); §25 families out of scope named; per-wave tag population
- 2026-09-02T00:54:56Z [claude-2026-09-01-b] answer: 'HUMAN: DESIGN §11 cut sprint/velocity features because they rot AND invite gaming. A derived, never-stored `ledger report` answers rot but not gaming (per-actor counters and duration percentiles are optimizable by the agents that write the Log). Ship as specified (recommended — kept out of PROTOCOL_TEXT, never feeds next/done/validate, documented as operator diagnostics), ship without the per-actor block, or defer until a second wave shows the 3-command composition being scripted by hand?' -> Ship as specified, including the per-actor block. Operator criteria 2026-09-01 add 'what allows an orchestrator to accurately track what sub agents are doing and course correct' — a derived, never-stored report is exactly that view; it stays out of PROTOCOL_TEXT and never feeds next/done/validate, so gaming has no lever. The 'second wave' trigger is superseded by the operator's stated priority.
- 2026-09-02T00:54:57Z [claude-2026-09-01-b] unblock: -> todo
