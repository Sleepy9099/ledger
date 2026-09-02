---
id: T-dk0iid
title: Normalize line endings repo-wide: .gitattributes text=auto eol=lf
status: todo
priority: p3
size: xs
created: 2026-09-02T03:37:50Z
tags: infra
---

## Spec

### Motivation

`init` pins `.ledger/** text eol=lf` for the host repo, but this tool repo's other files rely on the developer's `core.autocrlf`, so every commit on Windows prints "LF will be replaced by CRLF" warnings and checkouts differ by platform. A stdlib-only Python project should be LF everywhere.

### Design

Add `* text=auto eol=lf` above the existing `.ledger/**` line; run `git add --renormalize .` (expected no-op: the index is already LF) and confirm `git status` is clean before committing.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T03:37:50Z [claude-2026-09-01-b] add: created: Normalize line endings repo-wide: .gitattributes text=auto eol=lf [p3/xs] (tags: infra)
