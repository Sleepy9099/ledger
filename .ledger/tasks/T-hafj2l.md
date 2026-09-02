---
id: T-hafj2l
title: Orchestration signals: scan contended, claim on external handoffs, done refuses unreachable evidence, resource contention in next, set --add-tag lease guard, holder-only staleness, list --member-of, report handoffs, last_handoff in the digest
status: done
priority: p2
size: m
created: 2026-09-02T11:44:58Z
closed: 2026-09-02T12:28:58Z
tags: orchestration
---

## Spec

### Findings (sweep 2026-09-02, orchestration #2, #4, #5, #6, #7, #8, #11; ergonomics #15; verified)

1. A header-field deletion (release --force / done) on one branch never conflicts with body activity on the other; `scan` gains `contended: [{task, actors, since}]` — tasks whose Log shows events by two or more actors after the newest claim line (derived, stored nowhere).
2. A task handed off with `release --blocked --on "external: ..."` cannot be claimed by the integrator (`bad-state`) and `unblock` re-opens it to any worker: `claim` accepts a blocked task whose blocked_on starts with `external:` and carries no claim — sets in_progress, journals `claimed (was blocked on external: ...)`.
3. `done --commit <sha>` accepts a sha unreachable from every ref: `link` warns, `done` refuses without `--force`.
4. `next` gains `resource_contention: {slug: [holders...]}` (additive; `resources_held` unchanged) so a forced double-hold is visible where the design points.
5. `set --add-tag resource:<slug>` on an in_progress task goes through `_resource_guard` (refuse / `--force` with the journaled suffix).
6. Staleness of a claimed task is measured from the HOLDER's own activity (claimed_at + Log lines by claimed_by), so an orchestrator's diagnostic note no longer resets a stranded worker's clock; unclaimed blocked tasks keep any-activity.
7. `list --member-of <id>`: the task's depends_on members as rows; `report` gains `handoffs: {awaiting_integration: N, ids: [...]}` (blocked_on starting `external: ready`).
8. `task_digest` gains `last_handoff` {ts, actor, verb, text} from the newest release/block line, rendered first in `brief`.
Tests for each; DESIGN §5/§7/§8 sentences; README rows.

## Next Steps

## Open Questions

## Commits

- 55cc7eb 2026-09-02 Orchestration signals: contended tasks, ownable handoffs, reachable evidence, visible resource contention, guarded lease tags, holder-only staleness, wave members, handoff counts, last_handoff in the digest

## Log

- 2026-09-02T11:44:58Z [claude-2026-09-01-b] add: created: Orchestration signals: scan contended, claim on external handoffs, done refuses unreachable evidence, resource contention in next, set --add-tag lease guard, holder-only staleness, list --member-of, report handoffs, last_handoff in the digest [p2/m] (tags: orchestration)
- 2026-09-02T12:22:46Z [claude-2026-09-01-b] claim: claimed
- 2026-09-02T12:28:57Z [claude-2026-09-01-b] link: 55cc7eb Orchestration signals: contended tasks, ownable handoffs, reachable evidence, visible resource contention, guarded lease tags, holder-only staleness, wave members, handoff counts, last_handoff in the digest
- 2026-09-02T12:28:58Z [claude-2026-09-01-b] done: evidence: 55cc7eb
