---
id: T-71aehi
title: drop --duplicate-of / --superseded-by: machine-visible closed relations
status: todo
priority: p2
size: s
created: 2026-09-01T23:48:39Z
tags: discovery, ontology
---

## Spec

### Motivation (review §5, §9, §18)

"duplicate / unnecessary → drop or merge" is the one arrow of the review's ontology with no structured verb: `cmd_drop` writes `--why` (after sanitize_inline) as free text `drop: <why>`; no target id is parsed, no field records a survivor, and `list --json` (task_brief) carries no Log at all, so "which tasks were folded into T-x" and the review's dropped-duplicate rate (§18) need O(n) `show` calls plus a regex over English. The `xl-open` fix_hint ("drop this and re-add smaller") describes a superseded-by relation the tool cannot record either. Rejected workarounds: `block --on <survivor>` before drop is erased (drop pops blocked_on); `set --add-depends <survivor>` abuses the ordering edge and can be refused as a cycle; a tag gives no reverse view or re-point hint.

### Design

CLI: `drop <id> [--why "..."] [--duplicate-of <id-fragment> | --superseded-by <id-fragment>]`. At least one of `--why` / a relation is required, and the two relation flags are mutually exclusive — both raised as `LedgerError("usage", ..., exit_code=3)` inside cmd_drop (envelope preserved; mirror cmd_set's "nothing to change"), not as argparse groups. The target is resolved with `load_task_or_die(ctx, frag, for_write=False)` (`no-such-task` / `ambiguous-id` exit 2); target == self → `refs` (precedent: cmd_set self-dependency, normalize_blocked_on); target already `dropped` → `bad-state` with fix_hint "point at the live survivor" (a new use of the code — so far it is raised only about the acted-on task); a done target is fine. Every refusal is evaluated BEFORE the first save, so a refusal leaves no file changed.

Storage: NO header key and the closing verb stays `drop` — a new verb such as `drop(duplicate)` would fail the closing-verb check in every older vendored validator, and a header key would trip `unknown-key`, which `--strict` CI promotes to an error. The CLI generates a machine prefix inside the existing Log text, reusing `block`'s ` — ` separator: `drop: duplicate-of T-x — <why>` / `drop: superseded-by T-x — <why>` (the ` — <why>` part is optional). The hyphenated token is not natural English, so historical `--why "duplicate of T-x"` text is NOT retroactively reinterpreted; a hand-typed `--why "duplicate-of T-x — ..."` given without the flag is refused with `refs` ("use --duplicate-of so the target is validated") — the grammar prevents accidental, not deliberate, hand-authoring. Regex `CLOSED_RELATION_RE = ^(duplicate-of|superseded-by) (\S+)(?: — (.*))?$`, prefix-agnostic because `Task` has no config access and the id was validated at write time.

Reads — the first Log-text-derived read in the tool; diagnostic only, never an enforced guarantee (DESIGN §3), and the target id is NOT covered by the `refs` check (a canonical later dropped, or a chain A→B→C, is possible; consumers must tolerate that): `Task.closed_relation()` → `{"kind": "duplicate"|"superseded", "target": id}` from the `drop` line with the greatest timestamp (never line position — Log lines are order-insensitive under merges; two lines sharing the maximum timestamp that disagree → None). `task_brief` and `task_full` gain `closed_relation` (null when absent), so `list --json`, `next --json` and `show --json` carry it; `show` gains `absorbed: [{id, kind}]` — every task whose relation targets this one (a second `load_all_tasks` pass in cmd_show; cmd_show already does a full directory scan plus a git walk, so no new cost class). The survivor's file is NOT written: every command keeps touching one file and the reverse relation is derived on read. Downstream: cmd_drop's dependents warning fix_hint becomes `ledger set <dep> --remove-depends <dropped> --add-depends <target>` when a target exists and dep != target (cmd_set refuses self-dependency; best-effort — a cycle may still be refused), and `compute_eligible`'s why for a dependency on a dropped task reads `T-y (dropped, duplicate-of T-x)`. Human line: `dropped T-a as duplicate of T-x: <why>`. `--superseded-by` records a 1:1 replacement; splitting an xl task follows DESIGN §8 (keep the parent, add the parts as dependencies) and needs no relation. Docs: README `drop` line; DESIGN §2's Log line description gains one sentence on the CLI-authored `drop:` sub-grammar; DESIGN §5; PROTOCOL_TEXT "Task turned out unnecessary?" names the flag (regenerate PROTOCOL.md/CLAUDE.md via init; coordinate with T-w0emnj).

### DESIGN.md principles

The single Log append plus the header lines `drop` already writes; no index, no second file, no new key/verb/status/validation code (Appendix #6/#12 untouched; #9's body-line-over-header precedent; #20's CLI-authored grammar-in-prose precedent; #22: the Log stays CLI-only). The lockstep VALIDATION_CODES test must pass unchanged. §11's velocity cut is not reopened: the ratio stays with whatever builds wave summaries (T-00mrm7).

### Backward compatibility

Older validators parse the line as an ordinary `drop` event; `closed_relation` is null for every existing drop; no config/schema bump; T-mo9goc-style global installs of either version validate either corpus identically.

### Tests

- tests/test_cli.py: both flags write the grammar line; `show` of the dropped task reports `closed_relation`; `show` of the target reports `absorbed`; `list --status dropped --json` rows carry `closed_relation`; both flags together → exit 3 with envelope; neither flag nor --why → exit 3 (existing assertion kept); self → `refs`; dropped target → `bad-state`; unknown/ambiguous target → exit 2; hand-typed grammar in --why without the flag → `refs`; a --why containing newlines still parses (sanitize_inline collapses them).
- tests/test_hardening.py: dependents fix_hint re-points to the target and omits `--add-depends` when the dependent is the target; `next --json` why shows `(dropped, duplicate-of T-x)`.
- tests/test_format.py: round-trip identity for a file carrying the grammar line; the existing `--why "superseded by new design"` phrasing yields `closed_relation() is None`.
- tests/test_property.py: op_drop randomly passes a relation; validate stays clean.

## Next Steps

- [ ] cmd_drop flags, refusals before any write, CLI-authored Log grammar with the block-style separator
- [ ] Task.closed_relation() (max-timestamp rule) + closed_relation in task_brief/task_full + absorbed in show
- [ ] Downstream hints (drop dependents fix_hint, next why text), human line, docs (README, DESIGN §2/§5, PROTOCOL_TEXT drop line via init)
- [ ] Tests in test_cli/test_hardening/test_format/test_property

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: drop --duplicate-of / --superseded-by: machine-visible closed relations
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'cmd_drop flags, refusals before any write, CLI-authored Log grammar with the block-style separator'
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'Task.closed_relation() (max-timestamp rule) + closed_relation in task_brief/task_full + absorbed in show'
- 2026-09-01T23:48:43Z [claude-2026-09-01-a] step: added 'Downstream hints (drop dependents fix_hint, next why text), human line, docs (README, DESIGN §2/§5, PROTOCOL_TEXT drop line via init)'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'Tests in test_cli/test_hardening/test_format/test_property'
