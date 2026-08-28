# Ledger protocol (required workflow for agents)

All implementation work in this repo is tracked in `.ledger/tasks/` via
`python .ledger/ledger.py` (called `ledger` below). Task files are plain
Markdown — you may READ them directly. Headers, `## Commits`, and `## Log`
are written ONLY through the CLI; you may edit Spec / Next Steps /
Open Questions prose directly with your file tools. Always pass `--json`
and parse `{"ok", "data", "errors"}`; every error carries a `fix_hint`.

## Session start — always

1. Export a session id once: `LEDGER_SESSION=claude-<YYYY-MM-DD>-<letter>`.
2. `ledger next --claim --json` — this is your task. Read its file (Spec,
   Next Steps, Open Questions, recent Log) BEFORE writing code; that is
   your handoff from previous sessions. If `task` is null, `why` explains
   it — report that to the human instead of inventing work.
3. `ledger questions --human --json` — surface anything listed to the
   human in your first message.

## While working

- Discover new work? `ledger add "title" -p p2 -s s --spec -` (pipe the
  spec via stdin). Never keep planned work only in your context window,
  and do NOT silently expand your current task.
- Decision you can't make? `ledger question <id> add "..." --human` and
  keep going on unblocked parts, or `ledger block <id> --on human` if
  fully stuck.
- Leave breadcrumbs the next session needs — dead ends especially:
  `ledger note <id> "..."`. Check finished steps
  (`ledger step <id> check <n>`), add discovered ones
  (`ledger step <id> add "..."`). The file is your memory, not the
  conversation.
- Inside Spec / Next Steps / Open Questions use `###` or deeper headings —
  a `## ` line starts a new file section. Fenced ``` examples are safe.
  Checkbox lines must be exactly `- [ ] text` / `- [x] text`.
- EVERY commit that advances a task ends with a trailer line:
  `Ledger-Task: <id>` (one per related task). Genuinely unrelated
  commits use `Ledger-Exempt: <short reason>`. Forgot on a pushed
  commit? Repair with `ledger link <id> <sha>`.
- Commit `.ledger/` changes together with the code they describe.

## Finishing a task

- `ledger done <id> --commit HEAD` — it refuses without commit evidence
  or with unanswered HUMAN questions. That refusal is correct; fix the
  reasons it reports, do not --force it. Task turned out unnecessary?
  `ledger drop <id> --why "..."`.

## Session end — never skip, even out of context budget

1. Unfinished task: make Next Steps reflect reality, then
   `ledger release <id> --note "where I stopped and why"`.
2. `ledger validate --coverage --strict --json` — fix every violation
   you caused (follow the fix_hints) BEFORE your final commit.

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
  never work on a task you haven't claimed.
