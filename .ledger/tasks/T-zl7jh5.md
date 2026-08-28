---
id: T-zl7jh5
title: Path-policy for Ledger-Exempt commits
status: todo
priority: p2
size: m
created: 2026-08-28T11:54:59Z
tags: integrity
---

## Spec

Make exemptions policy-aware: new config key exempt_allowed_paths (list of globs). When set, a commit carrying Ledger-Exempt may only touch files matching those globs (plus .ledger/** always); an exempt commit touching anything else is a coverage error with a fix_hint naming the offending paths. When the key is ABSENT (existing configs), behavior is unchanged (free-text exemptions + exempt-ratio visibility) so upgrading ledger.py never breaks a repo.

init writes a conservative default for new projects: docs/**, *.md, .github/**, .gitignore, .gitattributes, LICENSE*.

Rationale: today 'Ledger-Exempt: misc' on an application-code commit structurally satisfies coverage; 'every implementation change maps to intended work' should be enforceable, not conventional. Subject-pattern exemptions (^Merge, ^Revert) unaffected. Tests: exempt commit touching src-like path fails under policy, passes without the key; docs-only exempt commit passes under policy.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T11:54:59Z [claude-2026-08-28-a] add: created: Path-policy for Ledger-Exempt commits
