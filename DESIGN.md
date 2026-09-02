# Ledger — design document

A task/spec ledger for AI coding agents on long-running projects. One
stdlib-only Python file, one directory of Markdown task files, one validator
that turns "work is traceable to the ledger" into a CI-enforced invariant.

This document is the synthesis of a three-way design panel (agent-ergonomics,
git/merge-robustness, verifiability) plus the decision record for every
contested point. The implementation in `.ledger/ledger.py` follows it.

**Core bets (one from each panelist, kept because they survive the other
two's priorities):**

- *Agent-ergonomics:* compliance comes from making the correct path the
  laziest path — `ledger next --claim --json` is the one command an agent
  cannot skip, and enforcement rides on the commands agents can't avoid
  (`next`, `done`).
- *Git-robustness:* eliminate every shared mutable file — no index, no
  counter, no global event log, no archive moves. Every write touches exactly
  one small per-task file, so git's ordinary line merge almost never
  conflicts, and the rare conflict is 1 line or keep-both.
- *Verifiability:* honesty is enforced against git history, never against
  agent claims — commit trailers (and explicit, sha-verified `ledger link`
  records) are the audit truth, `validate --coverage` cross-checks history
  against task files, and every violation carries a machine-actionable
  `fix_hint`.

---

## 1. Directory layout

```
repo-root/
├── .gitattributes             # init appends: ".ledger/** text eol=lf"
├── CLAUDE.md                  # init appends the protocol block between
│                              #   <!-- LEDGER:BEGIN --> / <!-- LEDGER:END -->
└── .ledger/
    ├── ledger.py              # THE ENTIRE TOOL: one Python 3.10+ stdlib-only file
    ├── config.json            # project config (see below)
    ├── PROTOCOL.md            # canonical agent protocol text
    └── tasks/                 # one file per task: <id>.md — ALL statuses live
        ├── T-a3f9c2.md        #   here FOREVER (no archive directory)
        └── T-77be04.md
```

**Bootstrap** = copy `.ledger/ledger.py` into a repo, run
`python .ledger/ledger.py init`, commit.

**Deliberately absent:** index/cache files, counters, lock files as state, a
global event log, an `archive/` directory, git hooks. Every piece of mutable
state is either a per-task file or git history itself (the gitignored
`.ledger/.lock` of §7(g) is a transient OS mutex that holds no state).

`config.json`:

```json
{
  "version": 1,                       // storage-SCHEMA version at bootstrap; written once by init
  "prefix": "T",
  "baseline": "<sha of HEAD at init — commits before it are exempt from coverage>",
  "stale_claim_days": 7,
  "exempt_patterns": ["^Merge ", "^Revert "]
}
```

## 2. Task file format

One task = one UTF-8 (no BOM), LF-only Markdown file. Structure: a
`---`-fenced header of flat `key: value` lines (a strict subset — NOT YAML;
lists are bare comma-separated), then a Markdown body with recognized `## `
sections in canonical order. The tool always rewrites headers in canonical key
order so diffs stay minimal. Unknown header keys are a validate *warning*
(typo detection); unknown extra `## ` sections are preserved verbatim.

### Header fields (canonical order)

| field | required | value |
|---|---|---|
| `id` | yes | `T-` + 6 chars of `[a-z0-9]`; must equal filename stem |
| `title` | yes | one line, free text |
| `status` | yes | `todo` \| `in_progress` \| `blocked` \| `done` \| `dropped` |
| `priority` | yes | `p0`–`p3` (p0 = drop everything; default `p2`) |
| `size` | yes | `xs` \| `s` \| `m` \| `l` \| `xl` (xl = "split me"; `next` skips xl) |
| `created` | yes | UTC ISO-8601 Z; never rewritten |
| `closed` | iff done/dropped | set once by `done`/`drop` |
| `claimed_by` | iff in_progress | session/actor string (also allowed on blocked) |
| `claimed_at` | iff claimed_by | UTC ISO-8601 Z |
| `blocked_on` | iff blocked | `human` \| a task id \| `external: <note>` |
| `depends_on` | optional | comma-separated task ids (AND semantics, acyclic) |
| `tags` | optional | comma-separated slugs |

There is **no `updated` field** — it would conflict on every concurrent edit.
"Last activity" = max(created, claimed_at, newest Log timestamp), computed.

### Body sections (fixed order; empty sections keep their heading)

- `## Spec` — free Markdown; the durable what/why/acceptance criteria.
- `## Next Steps` — `- [ ]` / `- [x]` checkboxes; the resume-point.
- `## Open Questions` — checkboxes. `HUMAN:` prefix = operator-gated (blocks
  `done`); answered form: `- [x] text -- ANSWERED (YYYY-MM-DD): answer`.
  No question numbering (numbers duplicate under merges); the CLI addresses
  questions by printed index or unique substring.
- `## Commits` — append-only cache, one line per commit:
  `- <sha7> <YYYY-MM-DD> <subject>`. Git trailers are the truth (§4).
- `## Log` — **last section, append-only**. One line per event:
  `- <UTC-ISO> [<actor>] <verb>: <text>`. Verbs: add claim release note step
  question answer link block unblock set done done(no-code) note(dead-end)
  drop (`note(dead-end)` is written only by `note --dead-end`: a selection
  key for views, with no validation semantics — an unmarked dead end is a
  valid plain note). Lines are
  self-contained, timestamped, actor-tagged, and order-insensitive — any
  merge interleaving is semantically correct. One CLI-authored sub-grammar
  lives inside a `drop:` line's text: `duplicate-of T-x — why` /
  `superseded-by T-x — why` (written only by `drop --duplicate-of` /
  `--superseded-by`, target validated at write time) — the machine-visible
  "where did this work go" relation, read back as `closed_relation` /
  `absorbed` with no header key, verb or status added.

## 3. Ledger semantics: how history/audit is kept

Three layers — snapshot + embedded journal + git-as-forensic-audit:

1. **Snapshot:** header and Spec/Next Steps/Open Questions hold CURRENT state
   only. One file read answers "where are we", no replay, no CLI needed.
2. **Embedded journal:** the per-task `## Log` — every CLI mutation appends
   exactly one line automatically, so agents never have to remember to
   journal. It travels with the file through rebase/cherry-pick.
3. **Git history:** the tamper-evident byte-level audit. The protocol requires
   committing `.ledger/` changes with the code they describe, so
   `git log --follow` reconstructs every transition with authorship.

**Rejected:** a global append-only events file (merge hotspot, rebase-unsafe);
pure event-sourcing (raw reads become useless); git-history-only audit
(useless on shallow clones, terrible handoff medium).

**Trust model:** the Log is honest-agent convenience. Every *enforced*
guarantee (coverage, evidence-on-done, state coherence) is checked against git
history and file structure, never against Log prose. `log-tamper`
machine-checks that Log lines are never deleted.

## 4. Commit linking

**Primary channel — commit trailers (the truth):** every commit that advances
a task ends with `Ledger-Task: <id>` (repeatable). Out-of-scope commits carry
`Ledger-Exempt: <short reason>`. Trailers live in the commit message, so they
survive rebase, squash, and cherry-pick — exactly the operations that
invalidate SHAs. Following git trailer semantics, only the **final paragraph**
of the message is scanned — a `Ledger-Task:` line quoted mid-body (a docs
example, protocol text inside a squash message) is not a claim.

**Secondary channel:** `ledger link <id> <sha|HEAD>` verifies the sha exists,
appends to `## Commits` (dedup), and logs the link with the actor — retroactive
links are themselves auditable, and they COUNT FOR COVERAGE: a commit is
linked iff a trailer names a known id OR some task's `## Commits` carries its
sha AND that task's Log holds the matching `link:` line. Both halves are
required — the Commits line is a cache anyone can hand-edit; the Log line is
CLI-authored, sha-verified at write time, actor-tagged and tamper-protected
once committed — so an explicit link is an explicit claim on a par with a
trailer, not the inferred linkage banned below. It is the one truthful
repair for a forgotten trailer on a pushed commit, whose message is
immutable (an exemption would be a lie; moving `baseline` hides history).
An explicit link also supersedes a dangling id in that commit's trailer, so
a typo'd id never becomes a permanent strict-CI failure. A trailer line
naming several ids (`Ledger-Task: T-a, T-b`) is diagnosed as such but never
used for linkage — one canonical syntax (decision #10).

**Reconciliation:** `ledger scan` classifies every commit in `baseline..HEAD`
as **linked** / **exempt** (Ledger-Exempt, `exempt_patterns` match, or touches
only `.ledger/`) / **unlinked** / **dangling** (trailer names a nonexistent
id). `scan --write` backfills `## Commits` lines from trailers — a trailer IS
an explicit claim, so backfilling is not fabricated evidence. *Inferred*
linkage (branch names, file overlap) is banned. Root commits diff against the
empty tree (`--root`), merge commits use the combined diff (`--cc`, so a
clean merge introduces nothing but an evil merge's conflict-resolution
content is in scope), and a git failure classifies as unlinked — coverage
never passes on a guess.

**Why it stays honest:** coverage is computed FROM git history plus
explicit, sha-verified link records — never from prose, branch names or file
overlap; trailers are immutable once pushed; exemptions need an explicit
reason (and the exempt ratio is reported so abuse is visible); `done` refuses
to close without evidence; a trailer against a never-claimed task is flagged
(`linked-never-claimed`). The `coverage` fix_hint orders the remedies:
trailer (amend if unpushed), link (if pushed), `ledger add` a task if none
owns the work, and `Ledger-Exempt` last — only for commits with no
product-work obligation, never for code without a task.

## 5. CLI

Uniform envelope `{"ok", "data", "errors": [{code, severity, task, message,
fix_hint}]}` under `--json`. Exit codes: **0** ok, **1** validation errors,
**2** refusal, **3** usage. Ids resolve from any case-insensitive unambiguous
fragment; ambiguity is an error listing candidates. Actor: `--session` >
`LEDGER_SESSION` > `git config user.name` > `unknown`.

Commands: `init`, `add`, `list`, `show`, `next [--claim]`, `claim [--force]`,
`release [--blocked --on]`, `set`, `note`, `step add|check|uncheck`,
`question add|resolve`, `questions [--human]`, `block --on` / `unblock`,
`link`, `scan [--write]`, `done [--commit|--no-code|--force]`, `drop --why`,
`validate [--coverage] [--strict] [--no-git]`, `doctor`, `search`. (Exact
flags: `--help` or README.)

Notable semantics:

- `next` eligibility: `todo` (plus `in_progress` with a stale claim, flagged
  as a takeover), all `depends_on` done, not blocked, size ≠ xl. Sort:
  priority, created, id. `why` always explains every near-miss
  machine-readably (not only when nothing is eligible), `blocked_on_human`
  lists operator gates, and `stale_blocks` lists tasks blocked on a task
  that has since closed — a task-targeted block never auto-clears (its
  `--why` may name more than the target finishing), so `next`, `done` and
  `drop` signal it with an `unblock` hint instead of clearing it.
- `claim` is advisory (real isolation is git branches); fresh foreign claims
  refuse without `--force`; stale ones log a takeover.
- `done` is the only path to status done: auto-links `--commit` args and any
  trailer-claimed commits, then requires ≥1 commit line OR `--no-code
  "reason"`, and zero unanswered HUMAN questions (`--force` overrides). Warns
  on unchecked steps / unanswered normal questions / still-open `depends_on`
  (a dropped dependency counts as open — one reading of depends_on
  tool-wide, shared with `next` and `drop`).
- `set --add-depends` refuses self-references and cycles at write time.
- `add` warns, never refuses, when the new title is token-overlap-similar
  to an existing one (`similar-task`, warning tier in the command envelope;
  an open task needs ≥2 shared tokens and ≥60% overlap of the smaller set,
  a closed task only an identical token set). Advisory only: nothing is
  persisted, the code is CLI-only (never in `validate` — a fuzzy score must
  never fail CI), thresholds are code constants. `scan` reports similar
  OPEN pairs post-merge, where concurrent branches mint duplicates.
- `drop --duplicate-of <id>` / `--superseded-by <id>` close a task while
  naming its survivor: the relation is one Log line (§2), never a header
  field, and the reverse view (`show <survivor>` → `absorbed`) is derived on
  read, so the survivor's file is never written. A dropped dependency then
  shows as `T-y (dropped, duplicate-of T-x)` in `next`'s `why`, and `drop`'s
  dependents warning hints the re-point (`--remove-depends T-y
  --add-depends T-x`). Diagnostic only: the target is not covered by `refs`.
- Structurally broken files (bad-merge duplicate keys/sections, preamble)
  are read-only: every mutating command refuses them (exit 2, `corrupt-file`)
  until repaired, so a routine `note` can never launder away the other merge
  side's data. Encoding damage (CRLF/BOM) is deliberately NOT gated — its
  normalization is lossless and the next CLI write is the documented repair.
  As a last-resort net, every write re-parses its own output and refuses
  (`would-corrupt`) if it would not round-trip identically — the CLI can
  never author a file that reparses differently.
- Closing verbs honor claims: `release`, `done`, and `drop` all refuse to
  strip another session's *fresh* claim without `--force` (stale claims are
  fair game). Claims stay advisory across branches — this guards only the
  shared-checkout case.
- The integration handoff is a convention, not a status: a worker that has
  finished but does not own closing runs `release --blocked --on "external:
  ready for integration" --note "..."` — the claim is stripped (so the
  integrator's `done --commit` needs no `--force`), `next` skips it with a
  `blocked_on external:` why, `list --status blocked` is the integrator
  queue, and a plain `release --note` sends it back to todo. `release
  --blocked` writes `blocked on <blocked_on> — <note>` to the Log so the
  reason survives a later unblock/drop. The protocol's "never work on a
  task you haven't claimed" reads "claimed or handed to you".
- Section bodies are parsed fence-aware: `## ` lines inside ``` code fences
  are content, so specs may safely quote task-file examples. Unfenced `## `
  lines in CLI-supplied spec text are rejected at input (use `###` inside
  sections).

## 6. Validation invariants

Errors: `encoding` (UTF-8, no BOM, LF-only), `parse` (fences, key grammar,
duplicate keys — the bad-union-merge signature, required keys, section order,
Log-last), `conflict-markers`, `id-filename`, `id-unique` (the post-merge net
for random-ID collision), `enums` (status/priority/size/timestamps,
closed ≥ created), `refs` (dangling depends_on/blocked_on, cycles),
`state-coherence` (claim ⇔ in_progress/blocked pairing, blocked ⇒ blocked_on,
closed ⇔ done/dropped + closing Log line), `done-evidence` (**the core
anti-hallucination check**), `done-human-questions`; with `--coverage`:
`coverage` (**the verbatim "work is traceable" guarantee** — refuses shallow
clones loudly) and `trailer-dangling`.

Warnings (errors under `--strict`): `stale-claim`, `xl-open`,
`checkbox-grammar` (near-miss checkbox lines that would silently escape the
steps/questions machinery — and the HUMAN done gate), `done-loose-ends`
(steps / questions; the still-open-`depends_on` form is emitted by `done`
only, never by `validate`, so upgrading `ledger.py` can never turn strict
CI red on existing history),
`unknown-key`, `sha-unreachable` (legitimate after rebase; `scan --write`
repairs), `linked-never-claimed` (a trailer against a still-OPEN task with no claim
Log evidence at all — a released task is NOT flagged because its claim line
survives, and a closed task is NOT flagged because it cannot be claimed
retroactively and its closing Log line records engagement); with
`--coverage` additionally `log-tamper` — the append-only Log verified
**historically**: every commit in scope is checked parent→commit (merge
commits against each parent), so once a Log event enters repository history
no later state may remove or alter it, task-file deletions included, and a
HEAD→working-tree pass catches uncommitted tampering before the session's
final commit. A net baseline→now diff could not see add-then-delete
sequences; the per-commit walk can. All scans pin git config
(`diff.noprefix`/`mnemonicPrefix`/`external`, `core.quotePath`) so user
settings cannot silently blind them. Info (never promoted, `--coverage`
only): `exempt-ratio` — escape-hatch abuse stays visible.

All offline checks also run with `--no-git` for exported trees.

## 6a. Versions

Repos bootstrapped at different points in the tool's evolution must be able
to tell whether their vendored copy is stale and whether their task corpus
matches the schema that copy expects — offline, because the answer is
needed before any command can be trusted. Three constants in `ledger.py`:

- `TOOL_VERSION` — the file; bumps on every shipped behavior change.
- `SCHEMA_VERSION` — the §2 storage schema. Bump rule: any change an OLDER
  copy reports as an `enums` / `parse` / `state-coherence` ERROR (a new
  status value, a new required key, a new claim pairing) bumps it; a purely
  additive header key does not (older copies emit only the `unknown-key`
  warning). Today 1 = the §2 header. A task that adds a status value must
  itself add the row.
- `PROTOCOL_VERSION` — `PROTOCOL_TEXT`; every task that edits the literal
  bumps it and re-runs `init` so PROTOCOL.md / CLAUDE.md follow.

`config.json`'s `version` is the schema at bootstrap: written once by `init`
when it creates the file and by NOTHING else (a task-mutating command must
never touch config.json — core bet 2, no shared mutable file), so it can lag
both the tool and the corpus and is reported, not trusted. `doctor` infers
`corpus_schema_version` from the task headers instead: any status outside
the enum or any key outside the canonical header order means "corpus newer
than tool" (`repo_compatible: false`, exit 1, `schema-mismatch` — a doctor
code, not a validate code). Because an old copy will never have `doctor`,
the same signal rides on `validate`'s `enums` fix_hint, the one path every CI
runs. A copy that predates `doctor` answers argparse exit 3 with no
envelope: "tool predates doctor" is itself the diagnosis.

## 7. Merge / concurrency story

The only files that ever change are individual task files, so every merge
reduces to git's per-line merge on one small Markdown file.

- **(a) Two branches ADD tasks:** random ids ⇒ different filenames ⇒ zero
  conflicts, always. (Why there is no counter and no `TASK-042` scheme.)
- **(b) Same task, different sections:** `## ` headings act as merge anchors;
  git auto-merges silently. The common case.
- **(c) Both append to the same Log:** a textual conflict with a mechanical
  resolution — keep both sides' lines, delete the markers. Lines are
  timestamped and order-insensitive, so any interleaving is correct.
- **(d) Same header field changed both sides:** a visible 1-line conflict;
  resolve using the Log lines both sides carry. **No `merge=union`
  gitattribute** — silently keeping both status lines is worse than a rare
  visible conflict, and the duplicate-key check names the file if someone
  resolves badly.
- **(e) Rebase/squash/cherry-pick:** no global log to reorder; trailers travel
  with messages; `scan --write` re-materializes new shas; `sha-unreachable`
  flags stale ones.
- **(f) Cross-branch double-claims** reconcile at merge as a 1-line conflict;
  duplicated effort is detected, not prevented (a true lock needs a server —
  out of scope).
- **(g) Same-checkout concurrency is serialized:** every mutating command
  (including `next --claim` and `scan --write`) takes a ledger-wide
  cross-process lock (`.ledger/.lock`, `msvcrt.locking`/`fcntl.flock`)
  BEFORE reading task state and holds it for the process lifetime, so two
  parallel agent processes in one working tree cannot both read a task as
  todo and both "win" the claim. Bounded wait (10s, `LEDGER_LOCK_TIMEOUT`
  overrides) with a `lock-timeout` refusal, exit 2. Read-only commands stay
  lock-free. The lock file is gitignored by `init` and the OS releases the
  lock even on a crash.
- **Post-merge ritual:** `ledger validate --coverage` + `ledger scan --write`
  (`--coverage` is what runs the Log tamper checks).

## 8. IDs, ordering, dependencies

- **ID:** `T-` + 6 of `[a-z0-9]` via `secrets.choice` (36⁶ ≈ 2.2B). At 2,000
  tasks, lifetime collision odds ≈ 0.0001 — and only concurrently-created,
  unmerged tasks can even race; `id-unique` is the deterministic net.
  Lowercase-only for case-insensitive filesystems. IDs are immutable, never
  reused; `git grep T-a3f9c2` finds everything.
- **Ordering:** priority, then created, then id. No rank floats — manual
  total orders rot under merges; fine-grained sequencing is the depends_on DAG.
- **Dependencies:** flat `depends_on` on the dependent side only (AND
  semantics, acyclic, enforced at write AND validate time). No epics: a big
  task is split into peers the parent depends_on. The reverse edge is
  computed on read (`show` → `dependents`, `list --depends-on <id>`), never
  stored.
- **Waves are tasks** (the §11 cut applied, not reversed): a multi-agent
  wave is an ordinary task `add "Wave N: <objective>" -p p1 -s s --tag wave
  --tag wave:<slug> --after <m1> --after <m2> ...`. The orchestrator's
  `claim W` is the "wave open" marker (the `claim:` Log line records who
  and when, since `done` strips the claim fields) and hides W from
  workers' `next --claim`; `next` offers W only once every member is done
  and names each unmet member; `done W --commit <integration sha>` closes
  it (the merge commit carrying `Ledger-Task: W` in its final paragraph is
  the natural close) and warns if members are still open; `note W` works
  after close for the wave record (suite result, worker count, anomalies).
  The add Log line journals the selected set (`created: ... [p1/s] (after:
  T-a, T-b) (tags: ...)`), later `set: depends_on - -> T-x` lines record
  removals, so the selection needs no second file. Members and work
  discovered mid-wave carry `wave:<slug>` (discovered work must NOT join
  W's depends_on, which would gate the wave's own close); `list --tag
  wave:<slug>` is the population, `list --depends-on <m> --tag wave` answers
  "which wave was T-x in". Only the orchestrator writes W's header (a
  worker that drops a member notes it on the member and ignores drop's
  `--remove-depends` hint; the orchestrator applies it) — one writer per
  header line (§7(d)). At orchestrator session end while the wave is open,
  keep the claim or park it with `release W --blocked --on "external: wave
  open"`; never plain-`release` it (it would become claimable). Any future
  wave-specific TOOL surface — a field, status, command, directory or
  metric — is a §11 reversal to be routed through a human question.

## 9. Agent protocol

Canonical text lives in `.ledger/PROTOCOL.md`; `init` maintains the same block
in `CLAUDE.md` between `<!-- LEDGER:BEGIN/END -->` markers. Summary: session
start = `next --claim --json` + read the file + surface `questions --human`
+ `search` the symbol before implementing; while working = one intent, one
verb (`note` a fact, `search` then `add` an obligation,
`--after` / `--add-depends` an ordering, `block` a blocker, `question
--human` a decision, `drop --duplicate-of` a duplicate — a note asking a
future session to act is not the action), trailer every commit; finish =
`done --commit HEAD` (respect refusals) or hand off with `release --blocked
--on "external: ready for integration"`; session end = `release --note` +
`validate --coverage --strict` and fix what you caused; never hand-edit
headers/Commits/Log, never mint ids, never delete task files. The
always-loaded protocol block is size-pinned by a test so every later edit
replaces wording rather than appends.

## 10. Testing strategy

- **Unit:** canonical round-trip identity, parse⇄serialize fixed point,
  structured views, unknown key/section preservation, parse-problem detection.
- **CLI contract:** every command via subprocess with `--json`; envelope shape
  and the 0/1/2/3 exit table asserted on success and refusal paths.
- **Violation completeness:** one trigger fixture per validate code, plus a
  lockstep test pinning the code table.
- **Git integration:** real temp repos scripting every merge-story scenario
  (parallel adds, dual Log appends + keep-both resolution, header conflict +
  bad union resolution caught, trailer coverage buckets, tamper detection,
  shallow-clone refusal, empty-repo bootstrap).
- **Anti-corruption property:** random valid CLI sequences must always leave
  `validate` clean — the tool can never author an invalid ledger.
- **Cross-platform:** all writes LF/UTF-8-no-BOM on Windows and POSIX; CRLF
  corruption detected and self-repaired on the next CLI write.

## 11. Deliberately left out

Archive directories (rename/edit conflicts), global NDJSON event logs
(every-merge conflict magnet), index/counter files, lock files as state (the
§7(g) mutex holds none) and daemons, git hooks
(don't survive clone; CI validate is the layer), `merge=union` drivers,
epics/sprints/due-dates/velocity (PM features that rot and invite gaming;
a wave is an ordinary task whose depends_on lists its members — §8),
evidence-token vocabularies (commits carry their tests), an `updated` field,
inferred commit linkage (fabricated evidence), YAML/TOML parsing (dependency
or 3.11+ / write-less; the strict subset is ~50 lines and merges better), and
spec-editing CLI commands (agents edit prose better with their own tools),
and semantic / LLM-based deduplication (the add-time warning is a
deterministic token-overlap hint; a model's opinion must never gate CI).

---

## Appendix: decision record (contested points and rulings)

1. **Tool location:** single-file `.ledger/ledger.py` — the entire bootstrap
   is one directory copy; the repo root stays clean.
2. **Task filename:** `<id>.md`, title inside the file — slug-in-filename
   forces renames when titles change, breaking blame/`--follow`.
3. **ID scheme:** `T-` + 6 of `[a-z0-9]` (36⁶ space) — 130× fewer collisions
   than 6-hex at the same length; lowercase for case-insensitive filesystems.
4. **Header delimiters:** `---` on both sides — renderers treat it as
   front-matter; the closing fence is an unambiguous parse anchor.
5. **Header lists:** bare comma-separated — smallest parser, no dialect for
   agents to get wrong.
6. **Status enum:** todo | in_progress | blocked | done | dropped; a `review`
   state was cut (no reviewer role in scope). Reconsidered 2026-09-01 after
   the first multi-agent wave review asked for `ready_for_integration`:
   stays cut, because `release --blocked --on "external: ready for
   integration"` already yields the handoff state with no schema change
   (§5); forgotten handoffs age via `stale-block` instead.
7. **No `updated` field** — guaranteed 1-line conflict on every concurrent
   edit; derived from claimed_at + newest Log line instead.
8. **History model:** per-task append-only `## Log` (last section) + git
   history as forensic audit. A global NDJSON event log was rejected
   unanimously (hottest merge conflict point, rebase-unsafe).
9. **Commit cache:** `## Commits` body lines, not a header field —
   append-only lines at a stable anchor merge cleanly; a mutating header line
   does not.
10. **Trailer keys:** `Ledger-Task:` + `Ledger-Exempt:` — two explicit keys
    beat an overloaded one; a second inline `[T-x]` syntax was cut (one
    canonical channel stays honest).
11. **Coverage scope:** EVERY commit in `baseline..HEAD` needs a trailer, an
    exemption, or to touch only `.ledger/` — path-glob scoping silently
    shrinks the guarantee.
12. **Close verb:** `done` (mirrors the status value exactly — one less name
    to remember; enum-verb symmetry beat 2-of-3 majority for `close`).
    Closed is terminal: done/dropped are refused by every mutating verb; a
    regression or redo is a new task (search first).
13. **Done evidence:** ≥1 linked commit OR `--no-code "reason"`; a pytest
    node-id evidence vocabulary was cut (commits carry their tests).
14. **Session identity:** flag > env > git user.name — a mandatory per-write
    flag is exactly the repetition agents fumble.
15. **Archive directory: CUT** — file moves reintroduce the rename/edit
    conflict class this design exists to eliminate.
16. **Ordering:** priority/created/id; a `rank` integer was cut — manual total
    orders rot under merges.
17. **JSON envelope + exit-code table** on every command — uniformity is what
    agents can parse reliably; violation codes are kebab-case strings with
    `fix_hint` (self-documenting beats numeric lookup tables).
18. **`merge=union`: rejected unanimously** — silent header corruption is
    worse than a rare visible conflict.
19. **Unreachable sha7:** warning by default (rebases legitimately orphan
    shas), error under `--strict`.
20. **Open-question grammar:** checkboxes + `HUMAN:` marker + `-- ANSWERED`
    suffix — human-gating without merge-fragile question numbering.
21. **Selector addressing:** 1-based index OR unique substring — substring is
    the merge-safe form (indexes go stale after merges).
22. **Editing boundary:** header/Commits/Log are CLI-only; Spec/Next
    Steps/Open Questions prose is free-edit; validate polices the line.
23. **Git hooks: none** — they don't survive clone and create false security;
    CI validate is the only enforcement layer.
24. **`next` skips xl tasks** and says so in `why` — forces decomposition at
    the moment it matters.
25. **`search` is an on-demand O(n) scan** over `load_all_tasks` with
    code-constant field weights (title 8, id 6, tags 6, spec 4, steps 3,
    questions 3, commits 2, log 1, +1 open) over RAW section text; no
    index or cache file — the derived cache remains T-8jrndl's separate,
    opt-in decision. It stays on the CLI side of the §11 spec-editing cut
    because it is structure-aware (typed hits, header rows), not a grep
    replacement; `git grep T-xxxxxx` remains the answer for a known id. It
    never feeds `validate`, `done` or coverage — results are retrieval
    hints. Pre-search vendored copies fail with argparse exit 3 and no
    envelope: treat a JSON decode failure on `search` as "stale copy".
