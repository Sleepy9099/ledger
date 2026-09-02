<!-- LEDGER:BEGIN -->

# Ledger protocol (required workflow for agents)

All implementation work in this repo is tracked in `.ledger/tasks/` via
`python .ledger/ledger.py` (called `ledger` below). Task files are plain
Markdown — you may READ them directly. Headers, `## Commits`, and `## Log`
are written ONLY through the CLI; you may edit Spec / Next Steps /
Open Questions prose directly with your file tools. Always pass `--json`
and parse `{"ok", "data", "errors"}`; every error carries a `fix_hint`.

## Session start — always

1. Export a session id once: `LEDGER_SESSION=claude-<YYYY-MM-DD>-<letter>`.
2. `ledger next --claim --json` — this is your task (a bounded digest:
   open steps, HUMAN questions, dead ends, recent Log; `--full` for
   everything). Read its file (Spec, Next Steps, Open Questions) BEFORE
   writing code; that is your handoff. `held` lists tasks you already hold
   from earlier — resume those before taking more. If `task` is null,
   `why` explains it — report that instead of inventing work.
3. `ledger questions --human --json` — surface anything listed to the
   human in your first message.
4. Before implementing, `ledger search <symbol|component|error> --json`
   surfaces prior dead ends and landmines recorded on other tasks.

## While working

- One intent, one verb — prose in a note controls nothing:
  fact / dead end    -> `ledger note <id> "..."` (`--dead-end` for what
                        did NOT work: the most valuable breadcrumb)
  new obligation     -> `ledger search <term> --json` first; an open task
                        covers it -> enrich it (`note` / `step add`); must
                        follow it -> `add --after <id>`; else `ledger add
                        "title" -p p2 -s s --spec -` (never a note saying
                        "someone should")
  X must land first  -> `ledger add --after X` / `set <id> --add-depends X`
                        (`next` clears it when X is done; a dropped X never
                        satisfies — `drop` hints `--remove-depends`)
  cannot proceed     -> `ledger block <id> --on human|<task-id>|"external: ..."`
                        (keeps your claim; NEVER auto-clears — `unblock` it)
  human decides      -> `ledger question <id> add "..." --human`, options
                        and your recommendation on indented lines under it
                        (`questions --human` shows them); keep going elsewhere
  duplicate          -> `ledger drop <id> --duplicate-of T-x`; carry unique
                        evidence to T-x with `note` (no claim needed)
  landed             -> trailer `Ledger-Task: <id>` / `ledger done`
  A note that asks a future session to act is not the action — file the
  task or step. Do NOT silently expand your task; if investigation shows
  the Spec's premise is wrong, correct the Spec, `note` it, and implement
  the corrected intent — that is not scope expansion.
- Check finished steps (`ledger step <id> check <n>`), add discovered ones
  (`step <id> add "..."`); the file is your memory, not the conversation.
- Inside Spec / Next Steps / Open Questions use `###` or deeper headings —
  a `## ` line starts a new file section. Fenced ``` examples are safe.
  Checkbox lines must be exactly `- [ ] text` / `- [x] text`.
- EVERY commit that advances a task ends with a trailer line in its LAST
  paragraph: `Ledger-Task: <id>` (one per related task). Genuinely
  unrelated commits use `Ledger-Exempt: <short reason>`. Forgot the
  trailer? Unpushed: amend the message. Pushed: `ledger link <id> <sha>`
  — an explicit link counts as coverage.
- Commit `.ledger/` changes together with the code they describe.

## Finishing a task

- `ledger done <id> --commit HEAD` — it refuses without commit evidence
  or with unanswered HUMAN questions. That refusal is correct; fix the
  reasons it reports, do not --force it. Unnecessary? `ledger drop <id>
  --why "..."` (`--duplicate-of` / `--superseded-by <id>` name the survivor).
- If an integrator owns commits and closing here, hand off instead of
  `done`: `ledger release <id> --blocked --on "external: ready for integration"
  --note "what passed locally"`. The integrator queue is `ledger list
  --status blocked --json`; the integrator closes with `ledger done <id>
  --commit <sha>` (no --force) or sends it back with `ledger release <id>
  --note "integration failed: ..."`, and may commit against the handed-off
  task with the normal trailer — the handoff is the authorization.

## Session end — never skip, even out of context budget

1. Every unfinished task you hold (`ledger list --mine --json`): make
   Next Steps reflect reality, then `ledger release <id> --note "where I
   stopped and why"` (already blocked? `release <id> --blocked --on <same
   reason> --note "..."` — a plain release resets it to todo).
2. `ledger validate --coverage --strict --json` — fix every violation
   you caused (follow the fix_hints) BEFORE your final commit. On an
   unmerged worker branch this checks that branch only; the integrator
   runs it (and the full suite) on the integrated tree.

## After any merge or rebase

- Run `ledger validate --coverage` and `ledger scan --write`, then fix what
  they report (--coverage also runs the Log tamper checks).
- Log-section conflict: keep BOTH sides' lines, delete the markers
  (lines are timestamped; order does not matter).
- Header-field conflict: pick the value matching the latest real event
  per the Log lines, then re-run `ledger validate`.

## Never

- Never edit headers, `## Commits`, or `## Log` by hand; never delete or
  rewrite existing Log lines (CI detects tampering).
- Never mint task ids by hand; only `ledger add`.
- Never delete a task file (`drop` instead), never mark work done
  without evidence, never commit code for work that has no task, and
  never work on a task you haven't claimed (or been handed).

<!-- LEDGER:END -->
