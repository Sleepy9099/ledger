---
id: T-qcsyyz
title: Fix same-second ordering flake in the resource-lease test
status: done
priority: p1
size: xs
created: 2026-09-02T03:48:07Z
closed: 2026-09-02T03:48:21Z
tags: infra
---

## Spec

### Defect

First CI run after the 2026-09-01 push (run 33588067183) failed 3 of 4 matrix jobs on `test_next_skips_held_resources_and_falls_through`: `list --resource gpu` returned the waiter before the holder because both were created in the same second at the same priority, so sort_key fell through to the random id. Same flake class fixed twice earlier this session in other tests (pin priorities or compare as sets).

### Fix

Give the holder priority p0 so every ordering the test asserts is deterministic; run the test repeatedly and the full suite under -n auto before pushing.

### Follow-up idea (not done here)

A test-only helper that asserts order-insensitively, or a conftest fixture that spaces `created` stamps, would remove the class; file only if a fourth instance appears.

## Next Steps

## Open Questions

## Commits

- 76c20e2 2026-09-01 Pin a same-second ordering tie in the resource-lease test

## Log

- 2026-09-02T03:48:07Z [claude-2026-09-01-b] add: created: Fix same-second ordering flake in the resource-lease test [p1/xs] (tags: infra)
- 2026-09-02T03:48:07Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T03:48:21Z [claude-2026-09-01-b] link: 76c20e2 Pin a same-second ordering tie in the resource-lease test
- 2026-09-02T03:48:21Z [claude-2026-09-01-b] done: evidence: 76c20e2
