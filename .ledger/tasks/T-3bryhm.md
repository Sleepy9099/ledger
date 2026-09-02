---
id: T-3bryhm
title: add: non-blocking warning on similar existing task titles
status: in_progress
priority: p2
size: s
created: 2026-09-01T23:48:39Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T01:31:04Z
tags: discovery
---

## Spec

### Motivation (review §9, §18; DESIGN core bet 1)

A duplicate is cheapest to catch at filing time, and the laziest path is `add` itself — an advisory `search` step (T-ntt2zz) can be skipped; `add` cannot. `cmd_add` already loads every task via `load_all_tasks` purely to build the id-collision set for `new_task`; the title is never compared to anything and the emit carries no `errors`. Verified 2026-09-01: adding a byte-identical title to open task T-8jrndl succeeded silently with `errors: []`.

### Design

- `title_tokens(title) -> set[str]`: lowercase, split on non-alphanumerics, drop tokens shorter than 3 chars and a fixed ≤15-word `TITLE_STOPWORDS` module constant (the, and, for, with, from, into, when, that, this, add, fix, use, make, support, handle). Applied to `task.title` (already sanitize_inline'd). Deterministic; shared with tests and reusable by T-ntt2zz for a title-similarity mode.
- In `cmd_add`, after `new_task`, score every loaded task (tasks with non-fatal parse problems are still in the list; they are read-only, but a duplicate of a damaged task is still a duplicate). If either token set is empty (stopword-only or short titles such as "A", which the suite uses, or "Fix it") the pair is never a candidate — this also guards the division. Candidate rules: an OPEN task with `overlap = |A∩B| / min(|A|,|B|) >= 0.6` and `|A∩B| >= 2`, OR one token set a subset of the other with the smaller set >= 2 tokens (NO raw-string containment: it has no word boundaries and cannot tell "Task 12" from "Task 1234"); a DONE/DROPPED task only with an identical token set (re-filing finished or dropped work is the classic duplicate; loose matches on closed history would be noise). `score` = overlap for the overlap branch, 1.0 for subset/identical; order by (score desc, sort_key); cap 5.
- Non-blocking: the task IS created (exit 0, `ok: true`, `data.id`). `errors` carries one warning per candidate: code `similar-task`, `task` = the NEW id, severity `warning`, message `T-new looks similar to T-old (status) 'old title'`. fix_hint by class — OPEN: `if it is the same work: ledger drop T-new --why 'duplicate of T-old' and carry any new evidence into T-old with ledger note/step; otherwise ignore`; DONE/DROPPED: `T-old closed on <date>; if this is a regression or redo, keep T-new and ledger note T-new 'follows T-old'; if you re-filed finished work, ledger drop T-new --why 'duplicate of T-old'`. Once T-71aehi lands, the hints name `--duplicate-of`. `data.similar` lists `[{id, status, title, score}]`. Precedent for `ok: true` + warnings: `cmd_drop`'s `refs` warnings and `cmd_done`'s `done-loose-ends`; human mode renders `WARNING similar-task T-new: ...` via emit automatically.
- Why warn rather than refuse: a refusal makes `--force` reflexive, exactly the habit PROTOCOL fights for `done`; the `add:` Log line preserves the audit and `drop --why` is a two-second, truthful correction.
- `set --title` is out of scope (title edits are rare).

### Boundaries (DESIGN.md)

- Never inside `validate`; `similar-task` is a CLI-only code like `no-such-task`, NOT added to VALIDATION_CODES (the lockstep test in tests/test_validate.py is unchanged) — a fuzzy score must never be able to fail `--strict` CI.
- Never persisted: no Log line, header key or Commits line records the similarity (DESIGN §4 bans inferred relationships as evidence; the tool must not author them). The only durable trace is whatever the agent does next.
- Thresholds (0.6, ≥2 shared tokens, cap 5) and TITLE_STOPWORDS are module constants, not config.json keys, and not a compatibility promise.
- Scope is the local checkout; a duplicate filed on a sibling branch is invisible until merge (§7(a)/(f): detected, not prevented). No post-merge similarity check in `validate` (a fuzzy score must never fail CI); instead evaluate `scan` — the non-gating post-merge ritual command that already walks the corpus — as the advisory home for cross-branch duplicate detection (report similar pairs among open tasks; concurrent waves are exactly where cross-branch duplicates are minted), or record in this task's Log why not.
- Runs under the mutation lock `add` already holds (§7g); pure string work, no git; O(n·tokens). If T-8jrndl lands, read titles from the cache.
- Not covered by §11 or the Appendix — new territory, not a reversal. Docs: DESIGN §5 one bullet ("`add` warns, never refuses, on token-overlap-similar titles; advisory only, never in validate") and DESIGN §11 gains "semantic/LLM-based deduplication" (review §9 explicitly rejects model-based dedup).

### Backward compatibility

Output is additive; files are byte-identical to what older copies would write; older vendored copies simply do not warn.

### Tests (tests/test_cli.py)

- An exact-title duplicate of an OPEN task warns (silent today); a near-duplicate warns naming the older id, exit 0, `data.id` present, file created; unrelated titles → no warning; stopword-only overlap ("Fix the thing" vs "Add the thing") → no warning; `add "Fix it"` after an open "Add it" and a done "Fix it" → no warning, exit 0.
- Identical token set of a done task → warning with the closed-class hint; loosely similar done title → none.
- Cap 5, best-first ordering; `title_tokens` unit test (stopwords, short tokens, punctuation).
- `validate --strict --json` on a ledger with two near-identical open titles reports zero violations (guards the never-in-validate boundary); tests/test_property.py stays green.

## Next Steps

- [x] title_tokens helper + TITLE_STOPWORDS constant with unit test
- [x] Candidate scoring in cmd_add; similar-task warnings (CLI-only code) + data.similar
- [x] DESIGN §5 bullet and §11 'semantic/LLM-based deduplication' entry; tests incl. the validate-strict boundary

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: add: non-blocking warning on similar existing task titles
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'title_tokens helper + TITLE_STOPWORDS constant with unit test'
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'Candidate scoring in cmd_add; similar-task warnings (CLI-only code) + data.similar'
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'DESIGN §5 bullet and §11 'semantic/LLM-based deduplication' entry; tests incl. the validate-strict boundary'
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] note: Consistency pass 2026-09-01: suite uses title 'A' not 'Fix it'; evaluate `scan` (non-gating post-merge ritual) as the advisory home for cross-branch duplicate detection
- 2026-09-02T01:31:04Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T01:36:36Z [claude-2026-09-01-b] step: checked 'title_tokens helper + TITLE_STOPWORDS constant with unit test'
- 2026-09-02T01:36:37Z [claude-2026-09-01-b] step: checked 'Candidate scoring in cmd_add; similar-task warnings (CLI-only code) + data.similar'
- 2026-09-02T01:36:37Z [claude-2026-09-01-b] step: checked 'DESIGN §5 bullet and §11 'semantic/LLM-based deduplication' entry; tests incl. the validate-strict boundary'
- 2026-09-02T01:36:37Z [claude-2026-09-01-b] note: scan evaluated and adopted as the advisory cross-branch home: scan --json now reports similar_open_pairs (same scoring, open tasks only, capped at 20) so the post-merge ritual surfaces duplicates minted on concurrent branches; never in validate
