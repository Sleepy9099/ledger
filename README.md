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

### Optional: a global `ledger` command

The single file stays the primary channel (it is what every host repo
runs in CI). For a human who wants `ledger` on the PATH, the repo also
packages that same file as a console script — no runtime dependencies:

```bash
pipx install git+https://github.com/Sleepy9099/ledger
# or, without installing:
uvx --from git+https://github.com/Sleepy9099/ledger ledger --version
```

Inside a host repo, `ledger doctor` then tells you whether the global copy
and the vendored `.ledger/ledger.py` differ (`vendored-stale`); re-run
`init` from whichever is newer.

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
                  claimed, as a bounded digest (--full for show's shape);
                  explains WHY if nothing is eligible
add "title" -p p1 -s m --spec -      create a task (spec via stdin);
    [--after <id>] [--tag t]         --after = scheduler-visible dependency;
                                     warns (never refuses) on similar titles
brief <id> [--last N]                bounded digest: open steps, HUMAN
                                     questions, dead ends, recent Log — every
                                     family capped; `truncated` says what was
                                     cut and how to fetch it (Spec = the file)
show <id> | list [--status ...]      read state (any unique id fragment works;
list --depends-on <id> [--tag wave]  show carries dependents; this is the
                                     reverse lookup, e.g. which wave held T-x)
set <id> --priority|--size|--title   edit header fields; --add-depends /
    |--add-depends|--remove-depends  --remove-depends keep the DAG honest
search TERM... [--any] [--regex]     ranked retrieval across every task
    [--in title,spec,log] [--open]   (search before filing; dead ends and
                                     landmines live on other tasks)
note <id> "text" [--dead-end]        append a Log breadcrumb (--dead-end
                                     marks what did NOT work: selectable)
step <id> add|check|uncheck <n|text> manage Next Steps checkboxes
question <id> add "..." [--human]    open a question (--human gates done)
question <id> resolve <n> --answer   answer one
questions [--human] [--task <id>]    the operator decision view: open
                                     questions with their indented context
                                     (options, recommendation), task state,
                                     a grouping key, plus every task blocked
                                     on human with its recorded reason
answers apply <file|->               record answers in batch: feed back the
                                     `questions --json` envelope with an
                                     `answer` on each row (all-or-nothing,
                                     re-runnable; rows without answers skip)
claim / release --note "handoff"     session start / session end
list --resource <slug>               tasks declaring a resource lease
list --mine                          everything this session holds (the
                                     session-end release list; next --json
                                     also carries it as `held`)
release <id> --blocked --on "external: ready for integration" --note "..."
                                     hand off to an integrator (PROTOCOL.md)
block <id> --on human|T-x|external:  explicit blockage; unblock reverses
                                     (done/drop/next flag blocks whose
                                     target task has since closed)
link <id> <sha|HEAD>                 attach commit evidence
scan --write                         reconcile git trailers -> ## Commits
done <id> [--commit HEAD]            close with evidence; refuses on open
                                     steps/questions; closed is terminal
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

## Operator diagnostics

`ledger report [--since TS|REF] [--until TS] [--tag TAG] [--task ID]
[--actor NAME] [--no-git] --json` is the orchestrator's view of a wave or
a backlog window: tasks opened / done / dropped by priority (priority at
creation replayed from `set:` lines), duplicates dropped (machine relation
vs. a labeled prose heuristic), reproduction and duplicate ratios, blockers
new / cleared, HUMAN questions created / answered / still open at the
window's end (claims and questions are REPLAYED from the Log through
`--until`, so a historical report shows that moment, not today), dependency
edges added / removed, priorities raised / lowered, workers and per-actor
counters (claims, takeovers, releases, done, notes, dead ends), active and
stranded claims at the end of the window, claim-to-close durations
(median / p90 / max), and — from git history only — linked / exempt /
unlinked / dangling commits in the window plus, for `--task`, the wave's
final integration commit. `--task <wave>` = the task and its members
(including members removed later); `--tag wave:<slug>` = members plus work
discovered mid-wave. Everything is recomputed on each call and nothing is
stored, so it cannot rot; Log-derived figures carry the honest-agent trust
level and `sources` says which are lower bounds. It is deliberately absent
from the agent protocol and from "Daily commands": it never feeds `next`,
`done` or `validate`.

## Resource leases (advisory)

Tag a task `resource:<slug>` (`add ... --tag resource:gpu`, or
`set <id> --add-tag resource:full-suite`) and a fresh in_progress claim on
it leases that resource: `next` skips other tasks declaring the same slug
(the `why` names the holder; `resources_held` maps every lease), `claim` /
`unblock` refuse with `resource-held` unless `--force`, and `validate`
reports a double-hold as `resource-contention` (info only — never fails
CI). `list --resource gpu` lists the declarers. Derived from claim fields;
nothing new is stored, and a blocked or stale holder does not hold.

## Exemptions are policy, not convention

`Ledger-Exempt: <reason>` means "no product-work obligation exists" —
merge/revert mechanics, ledger bookkeeping, generated artifacts, docs, CI
metadata — never "an obligation exists but filing a task is inconvenient".
`init` writes `exempt_allowed_paths` into a NEW project's config.json
(`docs/**`, `*.md`, `.github/**`, `.gitignore`, `.gitattributes`,
`LICENSE*`, `*.lock`, `package-lock.json`, `tests/test_ledger.py`; `.ledger/**`
is always allowed): with the key set, an exempt commit — the explicit
trailer, and a `^Merge`-pattern TRUE merge via its combined diff, so an evil
merge's conflict-resolution content counts — may touch only matching paths;
anything else is an `exempt-policy` error naming the offending paths (the
commit stays exempt, so `coverage` never fires alongside). Existing repos
(key absent) are unchanged until they opt in. Glob rules: `dir/**` is a
prefix, a glob containing `/` matches the full path (`*` and `?` never
cross `/`, `**` does — gitignore-like, not fnmatch), a `/`-less glob
matches the basename at any depth. Widening the list is a project decision
— ask via a HUMAN question. Known gap: a single-parent squash merge whose
subject matches `^Merge ` stays exempt — put the `Ledger-Task:` trailer in
the squash message's last paragraph instead.

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
- [tests/](tests/) — the tool's own suite (`python -m pytest`; with
  `pip install pytest-xdist`, `python -m pytest -n auto` runs it several
  times faster — every test owns a temp repo): format round-trips, CLI
  contract, one fixture per validation code, real-git merge scenarios, and
  an anti-corruption property test
