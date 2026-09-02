---
id: T-6zi51x
title: Exemption policy migration: forward-only activation, doctor visibility, bookkeeping vs executable ledger paths, ratio by channel
status: in_progress
priority: p1
size: m
created: 2026-09-02T04:51:26Z
claimed_by: claude-2026-09-01-b
claimed_at: 2026-09-02T05:04:50Z
tags: integrity
---

## Spec

### Defect (review 2026-09-02, finding 4)

exempt_allowed_paths is written by init into NEW config files only; re-vendoring never enables it and doctor stays silent, so existing adopters upgrade to 1.2.0 with unrestricted exemptions. The implicit path exemption treats all of `.ledger/**` as bookkeeping although `.ledger/ledger.py` (executable) and `config.json` (policy) are not; a global `*.md` allowance can exempt runtime-relevant agent instructions; the exempt ratio is one aggregate that the one-closure-commit-per-task workflow dilutes.

### Design

- `exempt_policy_since: <sha>` config key (forward-only): commits that are ancestors of (or equal to) it are never path-checked, so a repo adopts the policy without rewriting history. `init --enable-exempt-policy` on an EXISTING repo writes the default globs plus `exempt_policy_since = HEAD` (an explicit operator flag; the only config write besides first init; idempotent).
- doctor reports `exempt_policy: {active, since, globs}` and warns `exempt-policy-off` with the enable command when the key is absent.
- Implicit path exemption narrows from `.ledger/**` to bookkeeping paths: `.ledger/tasks/**`, `.ledger/PROTOCOL.md`, `.ledger/.lock`; `.ledger/ledger.py` and `.ledger/config.json` need a trailer or an explicit exemption (in a host repo `Ledger-Exempt: re-vendor ledger.py`; `.ledger/**` stays in the allowed globs so that exemption passes the path policy). DESIGN §4 / decision #11 wording; this repo's history must still validate (check before committing).
- `*.md` stays in the default (docs are the classic exemption) but README says repos whose Markdown carries runtime prompts should narrow it; CLAUDE.md/AGENTS.md protocol blocks are init-generated bookkeeping.
- exempt-ratio message and scan data break the count down by channel: explicit trailer / subject pattern / bookkeeping paths.
- Tests: since-ref skips older commits and checks newer ones; doctor warning and `init --enable-exempt-policy` (config bytes otherwise unchanged; idempotent); a ledger.py-only untrailered commit is now `coverage`; a tasks-only commit stays exempt; ratio breakdown.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T04:51:26Z [claude-2026-09-01-b] add: created: Exemption policy migration: forward-only activation, doctor visibility, bookkeeping vs executable ledger paths, ratio by channel [p1/m] (tags: integrity)
- 2026-09-02T05:04:50Z [claude-2026-09-01-b] claim: claimed
