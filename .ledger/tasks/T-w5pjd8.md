---
id: T-w5pjd8
title: Step outcome suffix (MOOT/DELEGATED/REJECTED): implement only if observed
status: blocked
priority: p3
size: s
created: 2026-09-01T23:48:40Z
blocked_on: human
tags: format
---

## Spec

### Motivation (review §21, §20)

A `[x]` can mean completed, made moot, delegated or rejected; the review says add richer state only once confusion is observed, and that Task must stay simple. Today `- [x]` is binary at every layer: `CHECKBOX_RE` captures the rest of the line as free text, `Task.steps()` returns `{n, text, done}`, and `done` / validate's `done-loose-ends` / `task_brief` equate checked with completed. Verified 2026-09-01 in a scratch ledger: a suffix such as `- [x] text -- MOOT: reason`, `-- DELEGATED: T-abc123` or `-- REJECTED: measured 12% slower` parses as a done step, survives `step check` / `uncheck` byte-for-byte (cmd_step rewrites `- [mark] {group(2)}`), is `step add`-authorable, resolves by substring on the delegated id, and passes `validate --strict` with zero warnings — whereas the marker characters agents improvise (`[X]`, `[~]`, `[-]`, `-[x]`) trip `checkbox-grammar` and FAIL strict CI. So a `-- WORD: note` suffix is the only grammar-compatible annotation, needs no tool change to use now, and mirrors the Open Questions grammar (`-- ANSWERED (date): answer`, decision #20). The Log already records the why (the `step` verb echoes the full line; `note`); the residual risk is a snapshot-only read of Next Steps. Do NOT implement on theoretical grounds — the same discipline as T-fkywmw, T-8jrndl and T-jqulvk.

### Trigger (what "observed" means)

At least one concrete case in a ledger-using repo where an agent or human misread a checked-but-not-executed step: re-did DELEGATED work, reported a MOOT step as implemented, or `done` closed a task whose only checked steps were REJECTED and a human had to reopen. Record it (repo, task id, Log line) here via `ledger note` before claiming.

### Phase 0 (may land any time; xs; no behaviour change)

A regression test pinning current behaviour so nobody later tightens the grammar into rejecting suffixes: a hand-written `- [x] foo -- MOOT: bar` parses `done: true`, round-trips through `step uncheck` / `check` unchanged, and `validate --strict --no-git` emits no `checkbox-grammar`. One sentence in DESIGN §2 under Next Steps: "a trailing `-- WORD: note` is free text; prefer it over marker characters, which `checkbox-grammar` rejects". PROTOCOL_TEXT untouched (review §22).

### Design (when triggered; option B)

Grammar `- [x] <text> -- <OUTCOME>: <note>` with OUTCOME in `MOOT | DELEGATED | REJECTED` (uppercase, exact spacing). `STEP_OUTCOME_RE` beside `ANSWERED_RE`; `Task.steps()` emits additive `outcome` (`null | "moot" | "delegated" | "rejected"`) and `outcome_note`, and `text` becomes the base text (as `questions()` strips the ANSWERED suffix); `done` stays `mark == "x"` — an outcome never counts as evidence (`done-evidence` still requires commits; §11's evidence-vocabulary cut is not reopened). CLI: `step <id> check <sel> [--moot "reason" | --delegated <task> | --rejected "reason"]`, mutually exclusive via a usage LedgerError (exit 3); `--delegated` resolves the target and refuses `no-such-task` (exit 2), writing the resolved id; the rewritten line replaces any existing suffix; Log `step: checked '<base>' (<outcome>: <note>)`; `uncheck` strips the suffix (a reopened step has no outcome). Selectors unchanged (a suffix widens the substring pool; `ambiguous-selector` stays the loud failure). No validate code in the first cut (a near-miss suffix is plain text, exactly as a misspelled `-- answered` is today). `show` / `list --json` gain the two keys. This EXTENDS DESIGN §2 and decision #20 to a second section — update both in the same commit.

### Backward compatibility

`CHECKBOX_RE` unchanged; suffixes sit inside group(2), so older copies validate clean and report `done: true` with the suffix inline; JSON consumers comparing full text read `text` + `outcome_note`. A tool-version feature, not a schema bump (T-2e587s).

### Tests (when triggered)

tests/test_format.py: each OUTCOME parses into outcome / outcome_note / base text; a non-outcome `-- foo: bar` yields `outcome: null`; round-trip identity. tests/test_cli.py: each flag writes the exact suffix and Log line; mutual exclusion exit 3; unknown delegated id → exit 2, file untouched; `uncheck` strips; re-check replaces rather than doubles; selector by delegated task id resolves. tests/test_validate.py: suffixed lines emit no `checkbox-grammar`; `done` on a task whose steps are all outcomed emits no `done-loose-ends`; VALIDATION_CODES unchanged. tests/test_property.py: `op_step_outcome`.

## Next Steps

- [ ] Human confirms B (or A/C); unblock
- [ ] Phase 0 (any time): regression test pinning that a `-- WORD: note` suffix stays strict-clean; one DESIGN §2 sentence
- [ ] When triggered: STEP_OUTCOME_RE, steps() keys, step check flags, docs, tests

## Open Questions

- [ ] HUMAN: Step outcomes: (A) nothing — agents may annotate `- [x] text -- MOOT: reason` as free text (already legal and strict-clean) and record the why with `ledger note`; drop this task. (B) keep this p3 observe-first task holding the parsed-suffix design, implement only after a real misread is recorded; land the Phase-0 regression pin now. (C) implement the suffix parsing now. Recommendation: B — it costs one task file, leaves DESIGN §2 unchanged until there is evidence (review §21's own rule), and durably records that the marker-character alternatives ([~], [-], [X]) fail strict CI.

## Commits

## Log

- 2026-09-01T23:48:40Z [claude-2026-09-01-a] add: created: Step outcome suffix (MOOT/DELEGATED/REJECTED): implement only if observed
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] step: added 'Human confirms B (or A/C); unblock'
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] step: added 'Phase 0 (any time): regression test pinning that a `-- WORD: note` suffix stays strict-clean; one DESIGN §2 sentence'
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] step: added 'When triggered: STEP_OUTCOME_RE, steps() keys, step check flags, docs, tests'
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] question: added (HUMAN): Step outcomes: (A) nothing — agents may annotate `- [x] text -- MOOT: reason` as free text (already legal and strict-clean) and record the why with `ledger note`; drop this task. (B) keep this p3 observe-first task holding the parsed-suffix design, implement only after a real misread is recorded; land the Phase-0 regression pin now. (C) implement the suffix parsing now. Recommendation: B — it costs one task file, leaves DESIGN §2 unchanged until there is evidence (review §21's own rule), and durably records that the marker-character alternatives ([~], [-], [X]) fail strict CI.
- 2026-09-01T23:48:48Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
