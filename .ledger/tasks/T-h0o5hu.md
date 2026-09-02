---
id: T-h0o5hu
title: Control bytes: reject in inputs, flag in validate, treat binary diffs as tamper
status: done
priority: p1
size: xs
created: 2026-09-02T11:44:57Z
closed: 2026-09-02T11:53:15Z
tags: integrity
---

## Spec

### Defect (sweep 2026-09-02, correctness #2; verified)

A NUL byte in a task file makes git classify it as binary; `git log -p` / `diff` then print `Binary files ... differ` and `_tamper_violations` sees no removed lines — Log lines can be deleted with CI green. The tool will write such a file itself (`add --spec -` with a NUL; `sanitize_inline` strips only CR/LF).

### Design

- `sanitize_inline` and `_check_section_body` strip C0 control characters other than tab (raise `usage` for --spec text that contains them? — strip, and say so in the envelope's human line: agents paste terminal output).
- validate `encoding`: any C0 byte other than \t \n in a task file is an error ("git treats this file as binary; the append-only Log cannot be verified").
- `_tamper_violations`: a `Binary files` line inside the patch is a `log-tamper` violation for that file ("cannot verify: file is binary").
- Tests for all three.

## Next Steps

## Open Questions

## Commits

- 5aa53ca 2026-09-02 Control bytes: stripped on input, flagged by validate, binary diffs are tamper

## Log

- 2026-09-02T11:44:57Z [claude-2026-09-01-b] add: created: Control bytes: reject in inputs, flag in validate, treat binary diffs as tamper [p1/xs] (tags: integrity)
- 2026-09-02T11:48:03Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T11:53:15Z [claude-2026-09-01-b] link: 5aa53ca Control bytes: stripped on input, flagged by validate, binary diffs are tamper
- 2026-09-02T11:53:15Z [claude-2026-09-01-b] done: evidence: 5aa53ca
