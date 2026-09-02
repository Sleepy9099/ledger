---
id: T-v2elrs
title: Robustness bundle: init config envelope, internal-error envelope, --prefix validation, iterative cycle check, unknown-section warning, honest ok on read commands
status: in_progress
priority: p2
size: s
created: 2026-09-02T11:44:57Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T12:02:19Z
tags: hygiene
---

## Spec

### Defects (sweep 2026-09-02, correctness #4, #5, #9, #10, #11)

1. `init` tracebacks on unreadable config.json — route through the `config` envelope like make_ctx.
2. `main()` catches only LedgerError: add a last-resort handler that emits an `internal` envelope (message = exception type + text, fix_hint = "report this with the command and the traceback", exit 2) and prints the traceback to stderr.
3. `init --prefix` is unvalidated (`a:b` bricks add on Windows): `\w{1,8}` (unicode word chars, no separators) in init and validate_config.
4. The validate cycle check is recursive and O(n^2): iterative, matching `_would_cycle`.
5. An unfenced `## ` heading inside Spec silently becomes an unknown section that the next write relocates: new warning `unknown-section` (VALIDATION_CODES, lockstep, DESIGN §6; fix_hint: use ### or a fence).
6. Read commands emit `ok: true` with error-severity `parse` rows: `ok` becomes false and the exit code 1 whenever an error-severity row is present (data still populated); protocol/README say `ok` is the success signal. Update the tests that expect rc 0 with a corrupt file present.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T11:44:57Z [claude-2026-09-01-b] add: created: Robustness bundle: init config envelope, internal-error envelope, --prefix validation, iterative cycle check, unknown-section warning, honest ok on read commands [p2/s] (tags: hygiene)
- 2026-09-02T12:02:19Z [claude-2026-09-01-b] claim: claimed
