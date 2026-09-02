# Ledger

A task/spec ledger for AI coding agents on long-running implementation
projects. One stdlib-only Python file, one directory of Markdown task files,
one validator that turns *"work in git history is traceable to the ledger"*
into a CI-enforced invariant.

Agents use it to carry specs, next steps, and open questions **between
sessions**; humans use it to steer and audit. Everything is plain files:
readable raw, git-diffable, and designed so concurrent branches almost never
merge-conflict.

## Bootstrap a project (the whole point)

```bash
# 1. copy the single file into the target repo
mkdir -p .ledger && cp path/to/ledger.py .ledger/ledger.py

# 2. initialize (records the coverage baseline, writes PROTOCOL.md,
#    appends the agent protocol to CLAUDE.md, adds the LF gitattribute)
python .ledger/ledger.py init

# 3. commit the bootstrap
git add -A && git commit -m "Add task ledger" -m "Ledger-Exempt: ledger bootstrap"
```

`init` also prints a ready-made pytest test for the host project's CI. That
single test is the enforcement layer:

```python
import json, subprocess, sys

def test_ledger_valid():
    r = subprocess.run(
        [sys.executable, ".ledger/ledger.py", "validate", "--coverage",
         "--strict", "--json"],
        capture_output=True, text=True)
    payload = json.loads(r.stdout)
    assert r.returncode == 0, json.dumps(payload["errors"], indent=2)
```

CI needs full history (`fetch-depth: 0` on GitHub Actions) — `validate`
refuses shallow clones rather than passing vacuously.

## The model in 60 seconds

- **One task = one file** at `.ledger/tasks/T-xxxxxx.md`: a strict `---`-fenced
  `key: value` header (id, title, status, priority p0–p3, size xs–xl,
  timestamps, depends_on, tags) plus Markdown sections `## Spec`,
  `## Next Steps`, `## Open Questions`, `## Commits`, `## Log`.
- **The Log is the journal**: every CLI mutation appends one timestamped,
  actor-tagged line. Append-only, last section in the file — concurrent
  appends merge cleanly, and deletions (of lines or whole task files) are
  machine-detected by `validate --coverage` (`log-tamper`).
- **Commit trailers are the audit truth**: every commit that advances a task
  ends with `Ledger-Task: T-xxxxxx`; genuinely unrelated commits carry
  `Ledger-Exempt: <reason>`. `validate --coverage` walks `baseline..HEAD` and
  fails on any commit with neither (commits touching only `.ledger/` and
  subjects matching `exempt_patterns` in config.json are exempt). Forgot the
  trailer on a pushed commit? `ledger link <id> <sha>` — the sha-verified,
  actor-tagged link line counts as coverage; a hand-edited `## Commits` line
  alone never does.
- **`done` requires evidence**: at least one linked commit, or an explicit
  `--no-code "reason"`. Unanswered `HUMAN:` questions block closing.
- **IDs are random** (`T-` + 6 of `[a-z0-9]`), so parallel branches never
  fight over a counter; new tasks are new files and merge trivially.
- **Parallel agents on one checkout are safe**: every mutating command
  serializes behind a cross-process lock (`.ledger/.lock`), so concurrent
  `next --claim` calls produce exactly one winner. Cross-branch coordination
  stays advisory — branches are the isolation model.

## Daily commands

```text
python .ledger/ledger.py <command> [--json]

next --claim      the agent entry point: highest-priority eligible task,
                  claimed; explains WHY if nothing is eligible
add "title" -p p1 -s m --spec -      create a task (spec via stdin);
    [--after <id>] [--tag t]         --after = scheduler-visible dependency;
                                     warns (never refuses) on similar titles
show <id> | list [--status ...]      read state (any unique id fragment works;
list --depends-on <id> [--tag wave]  show carries dependents; this is the
                                     reverse lookup, e.g. which wave held T-x)
set <id> --priority|--size|--title   edit header fields; --add-depends /
    |--add-depends|--remove-depends  --remove-depends keep the DAG honest
note <id> "text" [--dead-end]        append a Log breadcrumb (--dead-end
                                     marks what did NOT work: selectable)
step <id> add|check|uncheck <n|text> manage Next Steps checkboxes
question <id> add "..." [--human]    open a question (--human gates done)
question <id> resolve <n> --answer   answer one
questions --human                    everything waiting on the operator
claim / release --note "handoff"     session start / session end
release <id> --blocked --on "external: ready for integration" --note "..."
                                     hand off to an integrator (PROTOCOL.md)
block <id> --on human|T-x|external:  explicit blockage; unblock reverses
                                     (done/drop/next flag blocks whose
                                     target task has since closed)
link <id> <sha|HEAD>                 attach commit evidence
scan --write                         reconcile git trailers -> ## Commits
done <id> [--commit HEAD]            close with evidence (refuses otherwise)
drop <id> --why "..."                close as won't-do (files never deleted);
     [--duplicate-of|--superseded-by <id>]  names the survivor machine-visibly
validate [--coverage] [--strict]     every invariant; exit 1 on violations
doctor                               offline: tool/schema/protocol versions,
                                     is the vendored copy or corpus stale?
```

All commands accept `--json` and print `{"ok", "data", "errors"}`; every
error carries a machine-actionable `fix_hint`. Exit codes: 0 ok,
1 validation errors, 2 refusal, 3 usage.

Agent identity comes from `--session`, else the `LEDGER_SESSION` env var,
else `git config user.name` — set the env once per session.

## Versions

`ledger.py` carries three independent version lines, all printed by
`ledger doctor --json` (and `ledger --version`): **tool** (this file),
**schema** (the task-file storage format — bumped only for changes an older
copy would report as an `enums`/`parse`/`state-coherence` error) and
**protocol** (the `PROTOCOL_TEXT` block `init` mirrors into PROTOCOL.md and
CLAUDE.md). `config.json`'s `version` is the schema the repo was
bootstrapped at; it is written once by `init` and by nothing else.

`doctor` is fully offline: it infers the corpus schema from the task headers
themselves (an unknown status or header key means "written by a newer
ledger.py" — exit 1, `schema-mismatch`, fix: `python <newer>/ledger.py init`),
compares the vendored copy's version with the running one, and checks that
PROTOCOL.md / the CLAUDE.md block match this copy's protocol text
(`protocol-stale` warning, fix: re-run `init`). A copy that predates `doctor`
answers with argparse exit 3 and no JSON envelope — treat that as "tool
predates doctor: re-vendor".

## Merge rules (also in PROTOCOL.md)

- Parallel `add`s never conflict (different files).
- Both sides appended to the same `## Log`: **keep both sides' lines, delete
  the markers** — lines are timestamped and order-insensitive.
- Same header line changed on both sides: a 1-line conflict; pick the value
  matching the latest real event per the Log. A lazy both-lines resolution is
  caught by `validate` (duplicate-key check).
- After any merge/rebase: `python .ledger/ledger.py validate --coverage` and
  `python .ledger/ledger.py scan --write`.

## Editing policy

Headers, `## Commits`, and `## Log` are CLI-only. Spec / Next Steps /
Open Questions prose may be edited directly with file tools — `validate`
polices the structural boundary.

## This repository

This repo is the source of the tool and dogfoods it (`.ledger/tasks/` tracks
the tool's own roadmap).

- [.ledger/ledger.py](.ledger/ledger.py) — the entire tool (source of truth;
  this is the file you copy into other repos)
- [.ledger/PROTOCOL.md](.ledger/PROTOCOL.md) — the agent protocol, verbatim
- [DESIGN.md](DESIGN.md) — the full design rationale and decision record
- [tests/](tests/) — the tool's own suite (`python -m pytest`): format
  round-trips, CLI contract, one fixture per validation code, real-git merge
  scenarios, and an anti-corruption property test
