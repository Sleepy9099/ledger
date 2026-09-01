---
id: T-w0emnj
title: Protocol refresh: one-intent-one-verb ontology and the integration handoff
status: todo
priority: p2
size: m
created: 2026-09-01T23:48:39Z
tags: protocol, docs
---

## Spec

### Motivation (review §5, §10, §11, §26)

Three agent-facing gaps in the protocol text, each confirmed against the code on 2026-09-01:

1. Review §5: "'Do C first' does not establish a dependency unless the scheduler can see it" and "a note asking a future agent to act is not the action". The tool HAS scheduler-visible dependency verbs — `add --after` and `set --add-depends` / `--remove-depends` (self-reference and cycles refused at write time), honored by `compute_eligible` (only a `done` dependency satisfies; a dropped one never will, and `drop` warns with a `--remove-depends` fix_hint) — but PROTOCOL_TEXT never mentions `--after`, `--add-depends` or `block --on <task-id>`, and README "Daily commands" has no `set` row and no `--after`. An agent following only the protocol has no way to express ordering except a note — exactly the §5 failure. The verbs are discoverable only via `--help` and reactive fix_hints.

2. Review §10/§11 (worker/orchestrator model; "ready for integration" — the review's top recommendation, scored 6.5/10): a worker who has finished but is waiting for integration has no documented representation. Verified: plain `release --note "READY"` returns the task to `todo` and `next` re-dispatches it to the next worker; `block --on "external: integration"` keeps the claim, so the integrator's `done` is refused with `claim-held` unless `--force`, which PROTOCOL forbids for `done` refusals. But `release --blocked --on "external: ready for integration" --note "..."` already yields the handoff state with zero tool change: the claim is stripped; `next` skips it (`why: blocked_on external: ready for integration`); `list --status blocked --json` is the integrator queue (rows carry `blocked_on`); the integrator's `done --commit <sha>` succeeds without `--force`; `release <id> --note "integration failed: ..."` sends it back to `todo`; `validate --strict` stays clean throughout. The convention is merely undocumented and untested. A first-class `ready` status is deliberately NOT added here (DESIGN decision #6) — T-ik6wl7 holds that decision and the stranded-handoff aging question (a handed-off task carries no claim, so nothing ever flags it as forgotten).

3. Log completeness: `release --blocked --on X` logs only `release: <note>|released` — the blocker reaches the header but not the Log, so after `unblock` or `drop` the handoff reason vanishes from the task file (recoverable only through git history, which DESIGN §3 says is not the handoff medium). `block` already logs `on <blocked_on> — <why>`.

### Design (text)

Replace — do not append to — the "Decision you can't make?" and "Leave breadcrumbs" bullets of "While working" in PROTOCOL_TEXT with one compact block; PROTOCOL_TEXT grows by at most 8 lines (review §22: the block is always loaded; DESIGN core bet 1):

```
- One intent, one verb — prose in a note controls nothing:
  fact / dead end    -> `ledger note <id> "..."`
  new obligation     -> `ledger add ...` (never a note saying "someone should")
  X must land first  -> `ledger add --after X` / `ledger set <id> --add-depends X`
                        (`next` clears it itself when X is done; a dropped X never
                        satisfies — `drop` warns and hints `--remove-depends`)
  cannot proceed     -> `ledger block <id> --on human|<task-id>|"external: ..."`
                        (keeps your claim; NEVER auto-clears — `unblock` it yourself)
  human decides      -> `ledger question <id> add "..." --human`
  duplicate          -> `ledger drop <id> --why "duplicate of T-x"`; carry unique
                        evidence to T-x with `note` (no claim needed for `note`)
  landed             -> trailer `Ledger-Task: <id>` / `ledger done`
```

plus one sentence: "A note that asks a future session to act is not the action — file the task or step instead." When T-71aehi lands, the duplicate line names `--duplicate-of`.

Add under "Finishing a task": "If an integrator/orchestrator owns commits and closing in this project, hand off with `ledger release <id> --blocked --on "external: ready for integration" --note "what passed locally"` instead of `done`. The integrator lists `ledger list --status blocked --json` (rows whose `blocked_on` starts with `external: ready`), closes with `ledger done <id> --commit <sha>` (no `--force`), or sends it back with `ledger release <id> --note "integration failed: ..."`. An integrator may commit against a handed-off task with the normal `Ledger-Task:` trailer — the handoff is the authorization, so 'never work on a task you haven't claimed' reads 'claimed or handed to you'."

Mirror in README "Daily commands" (add `--after <id>` to the `add` row; add a `set <id> --priority|--size|--add-depends|--remove-depends|--add-tag` row — `set` is absent today; add the handoff line next to `release`), DESIGN §9 summary, DESIGN §5 near "Closing verbs honor claims", and DESIGN decision #6: "reconsidered after the first multi-agent wave; stays cut because `release --blocked --on "external: ..."` already yields the handoff state — see T-ik6wl7." Also fix the DESIGN wording drift: §1 "Deliberately absent: ... lock files" and §11 "index/counter/lock files and daemons" contradict §7(g)'s `.ledger/.lock`; reword both to "lock files as state".

### Design (code, xs)

`cmd_release` with `--blocked`: Log text becomes `blocked on <normalized blocked_on>` followed by ` — <note>` when `--note` is given (mirrors `block`'s `on <blocked_on> — <why>`; the separator is space, U+2014, space); verb stays `release` (one Log line per mutation, DESIGN §3). Without `--blocked` the line is unchanged. Include `blocked_on` in the human line (`released T-x -> blocked on human`). No validator reads Log text (only verbs are inspected), so older vendored copies are unaffected.

### Rollout

Edit PROTOCOL_TEXT in ledger.py only, then re-run `python .ledger/ledger.py init` in this repo (safe: the self-copy is skipped when source == dest; an existing config.json is untouched) so `.ledger/PROTOCOL.md` and the CLAUDE.md block regenerate; commit them together with README/DESIGN under a `Ledger-Task:` trailer. If T-2e587s has landed, bump PROTOCOL_VERSION in the same commit.

### DESIGN.md principles

Text plus one Log-text change; no storage, header, verb, status or hook change; PROTOCOL.md/CLAUDE.md are init-maintained documents (§1). Trust model: the new Log text is CLI-generated from the normalized header value and is parsed by no enforced check.

### Tests

- tests/test_cli.py: pin the handoff sequence end to end — worker `release --blocked --on "external: ready for integration"`; `next --claim` as another session returns `task: null` with the `blocked_on external:` why; integrator `done --commit HEAD` succeeds without `--force`; integrator `release --note` returns it to todo; `validate --strict` clean throughout.
- test_release_handoff: `release --blocked --on human --note x` → Log text `blocked on human — x`; `--on <fragment>` → the full resolved id; plain `release --note x` still yields `x`.
- init test: CLAUDE.md block and PROTOCOL.md contain `--add-depends`, "not the action" and "ready for integration"; re-init still yields exactly one block (the single-block invariant already exists; the content assertions are new).
- tests/test_dogfood.py: `.ledger/PROTOCOL.md` byte-equals `ledger_mod.PROTOCOL_TEXT` and CLAUDE.md contains init's exact block `f"{CLAUDE_BEGIN}\n\n{PROTOCOL_TEXT}\n{CLAUDE_END}"` — true today; guards future drift.

## Next Steps

- [ ] Rewrite the 'While working' bullets in PROTOCOL_TEXT into the ontology block (<= 8 lines growth) and add the handoff paragraph under 'Finishing a task'
- [ ] cmd_release --blocked: Log text 'blocked on <blocked_on> — <note>'; include blocked_on in the human line
- [ ] Re-run init in this repo; README Daily commands (set row, --after, handoff line); DESIGN §5/§9, decision #6 note, fix the §1/§11 lock-file wording drift
- [ ] Tests: end-to-end handoff sequence, release Log text, init wording assertions, dogfood PROTOCOL.md == PROTOCOL_TEXT

## Open Questions

## Commits

## Log

- 2026-09-01T23:48:39Z [claude-2026-09-01-a] add: created: Protocol refresh: one-intent-one-verb ontology and the integration handoff
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'Rewrite the 'While working' bullets in PROTOCOL_TEXT into the ontology block (<= 8 lines growth) and add the handoff paragraph under 'Finishing a task''
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'cmd_release --blocked: Log text 'blocked on <blocked_on> — <note>'; include blocked_on in the human line'
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'Re-run init in this repo; README Daily commands (set row, --after, handoff line); DESIGN §5/§9, decision #6 note, fix the §1/§11 lock-file wording drift'
- 2026-09-01T23:48:42Z [claude-2026-09-01-a] step: added 'Tests: end-to-end handoff sequence, release Log text, init wording assertions, dogfood PROTOCOL.md == PROTOCOL_TEXT'
