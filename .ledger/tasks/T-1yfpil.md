---
id: T-1yfpil
title: Exemption policy dry-run: scan --exempt-policy-preview counts the blast radius before the switch
status: done
priority: p2
size: s
created: 2026-09-02T08:54:44Z
closed: 2026-09-02T09:16:32Z
tags: integrity
---

## Spec

### Defect (heavy-session feedback 2026-09-02, #5)

Enabling exempt_allowed_paths is a config edit whose blast radius is only visible after making it (reported: 4 errors → 19, fifteen of them exempt-policy over landed commits). `init --enable-exempt-policy` is forward-only, which avoids that — but nobody can see the count first, and a hand-planted key (no `since`) hits history.

### Design

- `scan --exempt-policy-preview`: evaluate the configured globs (or DEFAULT_EXEMPT_ALLOWED_PATHS when the key is absent) against every exempt commit in scope, IGNORING `exempt_policy_since`, and report `exempt_policy_preview: {globs, would_violate: N, before_head: N (what a forward-only enable skips), commits: [{sha, subject, paths[:5]}], generated_artifact_hint: paths matching *.lock etc.}`. Opt-in because it costs one diff-tree per explicit-exempt commit.
- `doctor`'s `exempt-policy-off` fix_hint names the preview first, then the forward-only enable; README migration paragraph too.
- `validate` warns `exempt-policy-retroactive` (info tier) when `exempt_allowed_paths` is set without `exempt_policy_since` and at least one violation predates the key's introduction? — NO: keep validate unchanged; the preview + hint is the whole feature.
- Tests: preview counts violating commits and lists paths with the policy off and on; `since` is ignored by the preview; the human line.

## Next Steps

## Open Questions

## Commits

- 62fd891 2026-09-02 init reports tool_copied; linked-never-claimed names the live remedy; scan --exempt-policy-preview is the dry run before the switch

## Log

- 2026-09-02T08:54:44Z [claude-2026-09-01-b] add: created: Exemption policy dry-run: scan --exempt-policy-preview counts the blast radius before the switch [p2/s] (tags: integrity)
- 2026-09-02T09:12:55Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T09:16:32Z [claude-2026-09-01-b] link: 62fd891 init reports tool_copied; linked-never-claimed names the live remedy; scan --exempt-policy-preview is the dry run before the switch
- 2026-09-02T09:16:32Z [claude-2026-09-01-b] done: evidence: 62fd891
