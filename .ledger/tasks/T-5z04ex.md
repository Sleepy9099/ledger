---
id: T-5z04ex
title: Coverage repair: ledger link cannot fix a pushed untrailered commit
status: done
priority: p1
size: s
created: 2026-09-01T23:48:39Z
closed: 2026-09-02T01:06:44Z
tags: integrity, protocol
---

## Spec

### Defect (found while checking review §7/§19 against the code)

PROTOCOL_TEXT — mirrored by `init` into every host repo's CLAUDE.md block and `.ledger/PROTOCOL.md` — says "Forgot on a pushed commit? Repair with `ledger link <id> <sha>`", and the `coverage` fix_hint in `validate_git` says "repair with: ledger link <task-id> <sha7>". Neither is true. `classify_commit` buckets a commit from its trailers, its `Ledger-Exempt` reason, `exempt_patterns` and the touched paths only; `## Commits` is never consulted (`known` in `validate_git` is just the set of task ids). Verified 2026-09-01 in a scratch repo: untrailered commit → `coverage` error; `ledger link <id> HEAD` succeeds; `validate --coverage` still fails; `done` accepts the link as evidence; coverage stays red for that commit forever. An agent that follows the protocol's own repair therefore lands in an unrepairable `--strict` CI failure — the exact class the `linked-never-claimed` comment says the tool must never create.

Related, same code region: the `trailer-dangling` fix_hint ("fix the id with ledger link, or add the missing task") has the same flaw (`add` cannot mint a chosen id either), and a multi-id trailer line `Ledger-Task: T-a, T-b` — the grammar is one id per line (PROTOCOL "one per related task") — is parsed by `_parse_trailers` as ONE dangling id `'T-a, T-b'`: silent under plain `validate` (`linked-never-claimed` skips unknown ids; `done` later refuses with `done-evidence`), loud only under `--coverage`, with the same misleading hints. `ledger link` of both tasks does not clear it.

### Decision needed (see Open Questions)

(a) Keep DESIGN §4 as written — coverage is computed from git history only, trailers are immutable — and fix the text: unpushed → amend/reword the message; pushed → the commit stays flagged; `Ledger-Exempt` only if the commit is genuinely non-product; otherwise the operator decides (move `baseline`, or add an `exempt_patterns` entry) via a HUMAN question, never an agent edit of config.json.

(b) Let an explicit `link` count for coverage: a commit is linked iff a trailer names a known id OR some task's `## Commits` carries its sha7 AND that task's Log has a matching `link:` line. The link line is CLI-authored, sha-verified at write time, actor-tagged and tamper-protected once committed — an explicit claim like a trailer, not the inferred linkage §4 bans (branch names, file overlap). DESIGN §4's "never from task-file assertions" and "trailers are the audit truth" sentences are amended accordingly; `sha-unreachable` already handles stale lines.

Recommendation: (b). Under (a) the only ways to green CI after a forgotten trailer are an exemption (a lie — review §19) or hiding history behind `baseline`; under (b) the repair the protocol already promises becomes true and the Log line is auditable. Either way the text changes ship in the same commit.

### Design (both options)

- `coverage` fix_hint: "add `Ledger-Task: <id>` to the message (git commit --amend / rebase) if unpushed; if pushed: <per decision>; Ledger-Exempt only for commits with no product-work obligation" (coordinate wording with T-zl7jh5, which edits the same loop).
- Multi-id diagnostic, in `validate_git`'s dangling loop and `cmd_scan`'s dangling report: count id-shaped tokens with `re.findall(rf"{re.escape(ctx.prefix)}-[a-z0-9]{{6}}(?![a-z0-9])", raw)` (`ctx.id_pattern()` is ^$-anchored and unusable here). ≥2 tokens → message `commit <sha7> trailer names several task ids on one line: '<raw>'`, fix_hint `one 'Ledger-Task: <id>' line per task; <amend/pushed guidance>`; exactly 1 token with extra text → `trailer carries extra text after the id`; scan's dangling entry (existing key `id`) gains `hint: "multi-id-line"`. The tokens are NEVER used for linkage (DESIGN §4/§11 ban inferred linkage; decision #10: one canonical syntax). Codes, severities and VALIDATION_CODES unchanged.
- `trailer-dangling` fix_hint: "fix the id in the message if unpushed; otherwise <per decision>".
- PROTOCOL_TEXT "Forgot on a pushed commit?" sentence rewritten per the decision; regenerate `.ledger/PROTOCOL.md` and the CLAUDE.md block with `python .ledger/ledger.py init`; README trailer paragraph; DESIGN §4.

### DESIGN.md principles

(a) touches text only. (b) consciously amends §4 and is routed through the human question; it keeps every write per-task, keeps trailers as the primary channel, and never infers. No new files, header keys, verbs or validation codes.

### Tests

- tests/test_git_integration.py: untrailered commit → `coverage` with the new hint text; after `ledger link`: still `coverage` under (a), clean under (b); `Ledger-Task: T-x, T-y` (both existing) → exactly one `trailer-dangling` whose message contains "several", `scan --json` dangling hint `multi-id-line`, `linked` empty; `Ledger-Task: T-x (partial)` → "extra text", not "several"; `done <id>` on a task named only in a multi-id line → `done-evidence`; a `Ledger-Exempt` line clears `coverage` but not `trailer-dangling`.
- tests/test_cli.py init test: PROTOCOL.md no longer promises that `ledger link` repairs a pushed commit unless (b) was chosen.

## Next Steps

- [x] Human answers the (a)/(b) question below; unblock
- [x] Rewrite the coverage and trailer-dangling fix_hints and the PROTOCOL_TEXT 'Forgot on a pushed commit?' sentence per the answer; regenerate PROTOCOL.md/CLAUDE.md with init
- [x] Add the multi-id trailer-line diagnostic to validate_git and scan (message/hint only, no linkage)
- [x] Tests in tests/test_git_integration.py per the spec; DESIGN §4 amended per the answer

## Open Questions

- [x] HUMAN: Pushed commit without a trailer: (a) keep DESIGN §4 (coverage from trailers only) and make the fix_hint/protocol say the commit stays flagged unless exempt/baseline is moved by the operator, or (b) let an explicit `ledger link` (sha-verified, actor-tagged, tamper-protected `link:` Log line + ## Commits line) count as coverage for that sha? Recommendation: (b) — (a) leaves only a lying exemption or a hidden baseline move as repairs. -- ANSWERED (2026-09-02): (b) an explicit ledger link counts as coverage. Operator criteria 2026-09-01: agents need a truthful repair for a pushed untrailered commit; (a) leaves only a lying exemption or a hidden baseline move, which strands an autonomous agent in unrepairable strict CI. The link line is sha-verified, actor-tagged and tamper-protected, so it is an explicit claim, not inferred linkage.

## Commits

- 0d6ac20 2026-09-01 Make explicit links count for coverage; diagnose multi-id trailer lines

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: Coverage repair: ledger link cannot fix a pushed untrailered commit
- 2026-09-01T23:48:40Z [claude-2026-09-01-a] step: added 'Human answers the (a)/(b) question below; unblock'
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'Rewrite the coverage and trailer-dangling fix_hints and the PROTOCOL_TEXT 'Forgot on a pushed commit?' sentence per the answer; regenerate PROTOCOL.md/CLAUDE.md with init'
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'Add the multi-id trailer-line diagnostic to validate_git and scan (message/hint only, no linkage)'
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] step: added 'Tests in tests/test_git_integration.py per the spec; DESIGN §4 amended per the answer'
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] question: added (HUMAN): Pushed commit without a trailer: (a) keep DESIGN §4 (coverage from trailers only) and make the fix_hint/protocol say the commit stays flagged unless exempt/baseline is moved by the operator, or (b) let an explicit `ledger link` (sha-verified, actor-tagged, tamper-protected `link:` Log line + ## Commits line) count as coverage for that sha? Recommendation: (b) — (a) leaves only a lying exemption or a hidden baseline move as repairs.
- 2026-09-01T23:48:41Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
- 2026-09-02T00:33:21Z [claude-2026-09-01-b] note: Session claude-2026-09-01-b found an uncommitted partial rewrite of the coverage/trailer-dangling fix_hints (option-a wording) in ledger.py; discarded it uncommitted because the (a)/(b) decision is still open — the Spec's Design section already carries everything needed to implement either answer
- 2026-09-02T00:54:55Z [claude-2026-09-01-b] answer: 'HUMAN: Pushed commit without a trailer: (a) keep DESIGN §4 (coverage from trailers only) and make the fix_hint/protocol say the commit stays flagged unless exempt/baseline is moved by the operator, or (b) let an explicit `ledger link` (sha-verified, actor-tagged, tamper-protected `link:` Log line + ## Commits line) count as coverage for that sha? Recommendation: (b) — (a) leaves only a lying exemption or a hidden baseline move as repairs.' -> (b) an explicit ledger link counts as coverage. Operator criteria 2026-09-01: agents need a truthful repair for a pushed untrailered commit; (a) leaves only a lying exemption or a hidden baseline move, which strands an autonomous agent in unrepairable strict CI. The link line is sha-verified, actor-tagged and tamper-protected, so it is an explicit claim, not inferred linkage.
- 2026-09-02T00:54:55Z [claude-2026-09-01-b] unblock: -> todo
- 2026-09-02T00:56:02Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T00:56:02Z [claude-2026-09-01-b] step: checked 'Human answers the (a)/(b) question below; unblock'
- 2026-09-02T01:06:27Z [claude-2026-09-01-b] step: checked 'Rewrite the coverage and trailer-dangling fix_hints and the PROTOCOL_TEXT 'Forgot on a pushed commit?' sentence per the answer; regenerate PROTOCOL.md/CLAUDE.md with init'
- 2026-09-02T01:06:27Z [claude-2026-09-01-b] step: checked 'Add the multi-id trailer-line diagnostic to validate_git and scan (message/hint only, no linkage)'
- 2026-09-02T01:06:27Z [claude-2026-09-01-b] step: checked 'Tests in tests/test_git_integration.py per the spec; DESIGN §4 amended per the answer'
- 2026-09-02T01:06:27Z [claude-2026-09-01-b] note: The discarded option-(a) hint wording nevertheless reached commit 88863da (T-71aehi) — the working tree was restored between checkout and that commit, cause unknown (OneDrive sync suspected). Replaced here by the option-(b) implementation; no functional effect in between.
- 2026-09-02T01:06:44Z [claude-2026-09-01-b] link: 0d6ac20 Make explicit links count for coverage; diagnose multi-id trailer lines
- 2026-09-02T01:06:44Z [claude-2026-09-01-b] done: evidence: 0d6ac20
