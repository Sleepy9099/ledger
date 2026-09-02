---
id: T-yfvuya
title: note --dead-end: machine-selectable negative-knowledge marker
status: done
priority: p2
size: xs
created: 2026-09-01T23:48:39Z
closed: 2026-09-02T01:20:45Z
tags: memory
---

## Spec

### Motivation (review §4, §23)

The review calls negative knowledge the Log's most valuable content and wants a "dead ends" field in the bounded view (T-z7iebd). `cmd_note` writes verb `note` with free text; PROTOCOL_TEXT asks for "dead ends especially" but nothing marks them, so no view can select or count them and a future agent sees them only by reading every line. Verified 2026-09-01: LOG_LINE_RE's verb slot `[a-z][a-z()_-]*` already admits `note(dead-end)` (mirroring `done(no-code)`); such a line parses with no problems, round-trips byte-identically through `save_task`'s guard, is included in `Task.log()` and `last_activity()`, is protected by `log-tamper`, and no validator has a verb whitelist — the only verb comparisons in the file are the closing-verb set, `done(no-code)` and `claim` — so every existing vendored copy accepts it.

### Design (option A, recommended)

The `note` subparser gains `--dead-end` (store_true); `cmd_note` passes `"note(dead-end)" if args.dead_end else "note"` to `Task.append_log` (unchanged). The response `data` always carries `"verb"` (either value). Any consumer of `show --json` can select `log[].verb == "note(dead-end)"` today; T-z7iebd's `dead_ends` field uses the same key. Docs: DESIGN §2's verb list gains `note(dead-end)` immediately after `done(no-code)` (keeps the sub-type grammar visibly paired); PROTOCOL_TEXT: if T-w0emnj has landed, edit the ontology block's `fact / dead end` line to name `--dead-end`; otherwise change "dead ends especially" to "dead ends especially: `ledger note <id> "..." --dead-end`" — regenerate PROTOCOL.md and the CLAUDE.md block via init; README `note` line. `release --note` does not gain the flag (record dead ends with `note --dead-end` before releasing).

Alternative B: keep verb `note` and a `DEAD-END:` text prefix mirroring the `HUMAN:` question marker (decision #20). A is preferred because decision #22 makes the Log CLI-only, so the verb slot is the sanctioned place for machine-selectable sub-typing, and the flag guarantees canonical spelling (the grammar itself also admits `note(deadend)`, which is why the marker must be flag-generated, not typed).

### Scope bound and trust model

Exactly one note sub-type; a general breadcrumb taxonomy (measurement, hypothesis, decision, ...) is out of scope and any further `note(<qualifier>)` needs its own human question (DESIGN §11 cuts vocabularies that rot; decision #13 cut an evidence-token vocabulary — one qualifier with a single consumer is not that). No validate code keys on it in either direction: an unmarked dead end stays a valid plain note and is never a violation. Precedent contrast: `done(no-code)` carries validation semantics; `note(dead-end)` deliberately carries none — it is a selection key for views only.

### Backward compatibility

Older copies parse, round-trip and tamper-protect the line; they reject only the flag (argparse exit 3). If T-2e587s has landed, bump PROTOCOL_VERSION in the same commit.

### Tests

- tests/test_cli.py (new fixture — do not extend the test that pins the exact plain-note verb list): `note --dead-end` writes the exact verb; `show` returns it; plain `note` still writes `note`; `data["verb"]` on both.
- tests/test_format.py: a CANONICAL variant containing a `note(dead-end)` line round-trips byte-identically and `log()` reports the verb (mirror the existing append_log round-trip case).
- tests/test_git_integration.py: committing then deleting a `note(dead-end)` line triggers `log-tamper`.
- tests/test_property.py: `op_note` randomly adds `--dead-end`; `validate --no-git` stays clean.
- tests/test_validate.py: a task closed with `done --no-code` whose extra Log lines are `note(dead-end)` passes `--no-git --strict`.

## Next Steps

- [x] Human picks A/B/C; unblock
- [x] note subparser --dead-end; cmd_note passes note(dead-end); data.verb
- [x] DESIGN §2 verb list, PROTOCOL_TEXT 'dead ends especially' line (re-run init), README note line
- [x] Tests: cli (new fixture), format round-trip, log-tamper, property, validate strict

## Open Questions

- [x] HUMAN: Negative-knowledge marker form: (A) `ledger note <id> "..." --dead-end` writes verb `note(dead-end)` mirroring `done(no-code)` — recommended: LOG_LINE_RE already admits it, no validator has a verb whitelist, log-tamper covers it, and the flag guarantees canonical spelling; it extends the DESIGN §2 verb list, which is why this is asked. (B) keep verb `note` and a `DEAD-END:` text prefix mirroring the `HUMAN:` marker — zero vocabulary change but a convention agents can misspell. (C) no marker — the brief view shows recent notes only. -- ANSWERED (2026-09-02): (A) note --dead-end writes verb note(dead-end). Operator criteria: machine-selectable so brief/next can surface negative knowledge without agents re-reading history; the flag guarantees canonical spelling for multiple agents; zero validate impact.

## Commits

- 703cd3e 2026-09-01 Add note --dead-end: a machine-selectable negative-knowledge marker

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: note --dead-end: machine-selectable negative-knowledge marker
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'Human picks A/B/C; unblock'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'note subparser --dead-end; cmd_note passes note(dead-end); data.verb'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'DESIGN §2 verb list, PROTOCOL_TEXT 'dead ends especially' line (re-run init), README note line'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] step: added 'Tests: cli (new fixture), format round-trip, log-tamper, property, validate strict'
- 2026-09-01T23:48:44Z [claude-2026-09-01-a] question: added (HUMAN): Negative-knowledge marker form: (A) `ledger note <id> "..." --dead-end` writes verb `note(dead-end)` mirroring `done(no-code)` — recommended: LOG_LINE_RE already admits it, no validator has a verb whitelist, log-tamper covers it, and the flag guarantees canonical spelling; it extends the DESIGN §2 verb list, which is why this is asked. (B) keep verb `note` and a `DEAD-END:` text prefix mirroring the `HUMAN:` marker — zero vocabulary change but a convention agents can misspell. (C) no marker — the brief view shows recent notes only.
- 2026-09-01T23:48:45Z [claude-2026-09-01-a] block: on human — decision recorded in Open Questions; do not implement until answered
- 2026-09-02T00:06:24Z [claude-2026-09-01-a] note: Consistency pass 2026-09-01: the 'dead ends especially' sentence lives in a bullet T-w0emnj replaces; doc step now targets the ontology block when T-w0emnj has landed
- 2026-09-02T00:54:56Z [claude-2026-09-01-b] answer: 'HUMAN: Negative-knowledge marker form: (A) `ledger note <id> "..." --dead-end` writes verb `note(dead-end)` mirroring `done(no-code)` — recommended: LOG_LINE_RE already admits it, no validator has a verb whitelist, log-tamper covers it, and the flag guarantees canonical spelling; it extends the DESIGN §2 verb list, which is why this is asked. (B) keep verb `note` and a `DEAD-END:` text prefix mirroring the `HUMAN:` marker — zero vocabulary change but a convention agents can misspell. (C) no marker — the brief view shows recent notes only.' -> (A) note --dead-end writes verb note(dead-end). Operator criteria: machine-selectable so brief/next can surface negative knowledge without agents re-reading history; the flag guarantees canonical spelling for multiple agents; zero validate impact.
- 2026-09-02T00:54:56Z [claude-2026-09-01-b] unblock: -> todo
- 2026-09-02T01:15:18Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T01:16:01Z [claude-2026-09-01-b] step: checked 'Human picks A/B/C; unblock'
- 2026-09-02T01:20:31Z [claude-2026-09-01-b] step: checked 'note subparser --dead-end; cmd_note passes note(dead-end); data.verb'
- 2026-09-02T01:20:31Z [claude-2026-09-01-b] step: checked 'DESIGN §2 verb list, PROTOCOL_TEXT 'dead ends especially' line (re-run init), README note line'
- 2026-09-02T01:20:31Z [claude-2026-09-01-b] step: checked 'Tests: cli (new fixture), format round-trip, log-tamper, property, validate strict'
- 2026-09-02T01:20:45Z [claude-2026-09-01-b] link: 703cd3e Add note --dead-end: a machine-selectable negative-knowledge marker
- 2026-09-02T01:20:45Z [claude-2026-09-01-b] done: evidence: 703cd3e
