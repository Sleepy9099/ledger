#!/usr/bin/env python3
"""Ledger — a task/spec ledger for AI coding agents on long-running projects.

Single file, Python 3.10+ standard library only. Deployed as .ledger/ledger.py
in a host repository. Storage is one Markdown file per task under
.ledger/tasks/ — directly readable by agents and humans, git-merge-friendly,
and validated by `ledger validate` (the command host projects run in CI).

Invoke:   python .ledger/ledger.py <command> [--json] ...
Protocol: .ledger/PROTOCOL.md
"""
from __future__ import annotations

import argparse
import atexit
import dataclasses
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import msvcrt  # Windows
except ImportError:
    msvcrt = None
try:
    import fcntl  # POSIX
except ImportError:
    fcntl = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUSES = ("todo", "in_progress", "blocked", "done", "dropped")
PRIORITIES = ("p0", "p1", "p2", "p3")
SIZES = ("xs", "s", "m", "l", "xl")
OPEN_STATUSES = ("todo", "in_progress", "blocked")

HEADER_ORDER = (
    "id", "title", "status", "priority", "size", "created", "closed",
    "claimed_by", "claimed_at", "blocked_on", "depends_on", "tags",
)
REQUIRED_KEYS = ("id", "title", "status", "priority", "size", "created")
LIST_KEYS = ("depends_on", "tags")

KNOWN_SECTIONS = ("Spec", "Next Steps", "Open Questions", "Commits", "Log")

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
HEADER_LINE_RE = re.compile(r"^([a-z_]+): (.*)$")
ANY_KEY_RE = re.compile(r"^([A-Za-z_-]+):\s*(.*)$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")
LOG_LINE_RE = re.compile(
    r"^- (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) \[([^\]]+)\] ([a-z][a-z()_-]*): (.*)$")
COMMIT_LINE_RE = re.compile(r"^- ([0-9a-f]{7,40}) (\d{4}-\d{2}-\d{2}) (.*)$")
CHECKBOX_RE = re.compile(r"^- \[([ x])\] (.*)$")
LOOSE_BOX_RE = re.compile(r"^\s*[-*+]\s*\[[^\]]{0,2}\]")
ANSWERED_RE = re.compile(r"^(.*?) -- ANSWERED \((\d{4}-\d{2}-\d{2})\): (.*)$")
# CLI-authored sub-grammar of a `drop:` Log line: `duplicate-of T-x — why`.
# The hyphenated token is not natural English, so a historical free-text
# `--why "duplicate of T-x"` is never reinterpreted as a machine relation.
CLOSED_RELATION_RE = re.compile(
    r"^(duplicate-of|superseded-by) (\S+)(?: — (.*))?$")
CLOSED_RELATION_KIND = {"duplicate-of": "duplicate", "superseded-by": "superseded"}
CLOSED_RELATION_TOKEN = {v: k for k, v in CLOSED_RELATION_KIND.items()}
TRAILER_RE = re.compile(r"^(Ledger-Task|Ledger-Exempt):[ \t]*(.+?)[ \t]*$", re.M)
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7}|\|{7})( |$)")
ID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"

GITATTRIBUTES_LINE = ".ledger/** text eol=lf"
GITIGNORE_LINE = ".ledger/.lock"
CLAUDE_BEGIN = "<!-- LEDGER:BEGIN -->"
CLAUDE_END = "<!-- LEDGER:END -->"

# Three independent version lines (see DESIGN "Versions"):
#   TOOL_VERSION     — this file. Bump on every behavior change that ships.
#   SCHEMA_VERSION   — the task-file storage schema (DESIGN §2). Bump ONLY
#                      for a change an older copy reports as an enums / parse
#                      / state-coherence ERROR (new status, new required key,
#                      new claim pairing); a purely additive header key does
#                      not bump it (older copies emit only unknown-key).
#   PROTOCOL_VERSION — PROTOCOL_TEXT. Bump whenever that literal changes.
# `ledger doctor` reports all three offline; config.json's "version" is the
# storage-schema version the repo was bootstrapped at (written once by init,
# never by a task-mutating command — config.json must not become a merge hot
# spot).
TOOL_VERSION = "1.2.0"
SCHEMA_VERSION = 1
PROTOCOL_VERSION = 12
CANONICAL_SOURCE = "github.com/Sleepy9099/ledger"

DEFAULT_CONFIG = {
    "version": SCHEMA_VERSION,
    "prefix": "T",
    "baseline": None,
    "stale_claim_days": 7,
    "exempt_patterns": ["^Merge ", "^Revert "],
}
# Written by init into a NEW config.json only — deliberately NOT in
# DEFAULT_CONFIG, which would switch the policy on for every existing repo
# the moment it re-vendors ledger.py. Absent key = policy off = today's
# behavior. Globs: `dir/**` prefix, a glob with `/` against the full path,
# a `/`-less glob against the basename at any depth. `.ledger/**` is always
# allowed. Includes the bootstrap CI snippet path and generic lockfiles.
DEFAULT_EXEMPT_ALLOWED_PATHS = [
    "docs/**", "*.md", ".github/**", ".gitignore", ".gitattributes",
    "LICENSE*", "*.lock", "package-lock.json", "tests/test_ledger.py",
]

# All violation codes ledger validate can emit, with their default severity.
# Tests keep this table and the trigger fixtures in lockstep.
VALIDATION_CODES = {
    "encoding": "error",
    "parse": "error",
    "conflict-markers": "error",
    "id-filename": "error",
    "id-unique": "error",
    "enums": "error",
    "refs": "error",
    "state-coherence": "error",
    "done-evidence": "error",
    "done-human-questions": "error",
    "coverage": "error",            # git, --coverage only
    "trailer-dangling": "error",    # git, --coverage only
    "exempt-policy": "error",       # git, --coverage only; exempt_allowed_paths set
    "stale-claim": "warning",
    "stale-block": "warning",       # an `external: ready` handoff nobody picked up
    "xl-open": "warning",
    "checkbox-grammar": "warning",
    "done-loose-ends": "warning",
    "unknown-key": "warning",
    "sha-unreachable": "warning",   # git
    "linked-never-claimed": "warning",  # git
    "log-tamper": "warning",        # git, --coverage only
    "exempt-ratio": "info",         # git, --coverage only; never promoted
    "resource-contention": "info",  # two fresh claims lease one resource; never promoted
}

PROTOCOL_TEXT = """# Ledger protocol (required workflow for agents)

All implementation work in this repo is tracked in `.ledger/tasks/` via
`python .ledger/ledger.py` (called `ledger` below). Task files are plain
Markdown; read them directly. Headers, `## Commits`, and `## Log` are
written ONLY through the CLI; edit Spec / Next Steps / Open Questions prose
directly with your file tools. Always pass `--json` and parse
`{"ok", "data", "errors"}`; every error carries a `fix_hint`.

## Session start — always

1. Export a session id once: `LEDGER_SESSION=claude-<YYYY-MM-DD>-<letter>`.
2. `ledger next --claim --json` — this is your task (a bounded digest:
   open steps, HUMAN questions, dead ends, recent Log; `--full` for
   everything). Read its file (Spec, Next Steps, Open Questions) BEFORE
   writing code; that is your handoff. `held` lists tasks you already hold
   from earlier — resume those before taking more. If `task` is null,
   `why` explains it — report that instead of inventing work.
3. `ledger questions --human --json` — surface anything listed in your
   first message.
4. Before implementing, `ledger search <symbol> --json` surfaces dead ends
   and landmines recorded on other tasks.

## While working

- One intent, one verb — prose in a note controls nothing:
  fact / dead end    -> `ledger note <id> "..."` (`--dead-end` for what
                        did NOT work)
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
  task or step. Do NOT silently expand your task; if the Spec's premise
  proves wrong, correct the Spec, `note` it, and implement the corrected
  intent — that is not scope expansion.
- Check finished steps (`ledger step <id> check <n>`), add discovered ones
  (`step <id> add "..."`); the file is your memory, not the conversation.
- Inside Spec / Next Steps / Open Questions use `###` or deeper headings —
  a `## ` line starts a new file section. Fenced ``` examples are safe.
  Checkbox lines must be exactly `- [ ] text` / `- [x] text`.
- EVERY commit that advances a task ends with a trailer line in its LAST
  paragraph: `Ledger-Task: <id>` (one per related task). Forgot the
  trailer? Unpushed: amend the message. Pushed: `ledger link <id> <sha>`
  — an explicit link counts as coverage. `Ledger-Exempt: <reason>` is
  ONLY for commits with no product-work obligation (merge/revert
  mechanics, ledger bookkeeping, generated artifacts, docs, CI metadata);
  code or tests without a task need `ledger add` first, never an exemption.
- Commit `.ledger/` changes together with the code they describe.

## Finishing a task

- `ledger done <id> --commit HEAD` — it refuses without commit evidence,
  with unanswered questions or with unchecked steps (check, mark `-- MOOT:`
  or delete them); fix what it reports, never --force. Closed is terminal.
  Unnecessary? `ledger drop <id> --why "..."` (`--duplicate-of` /
  `--superseded-by <id>` name the survivor).
- If an integrator owns commits and closing here, hand off instead of
  `done`: `ledger release <id> --blocked --on "external: ready for integration"
  --note "what passed locally"`. The integrator queue is `ledger list
  --status blocked --json`; the integrator closes with `ledger done <id>
  --commit <sha>` (no --force) or sends it back with `ledger release <id>
  --note "integration failed: ..."`; committing against a handed-off task
  needs no claim — the handoff is the authorization.

## Session end — never skip, even out of context budget

1. Every unfinished task you hold (`ledger list --mine --json`): make
   Next Steps reflect reality, then `ledger release <id> --note "where I
   stopped and why"` (already blocked? `release <id> --blocked --on <same
   reason> --note "..."` — a plain release resets it to todo).
2. `ledger validate --coverage --strict --json` — fix every violation
   you caused (follow the fix_hints) BEFORE your final commit. On a worker
   branch this checks that branch only; the integrator re-runs it (and the
   full suite) on the integrated tree.

## After any merge or rebase

- Run `ledger validate --coverage` and `ledger scan --write`; fix what
  they report. Log-section conflict: keep BOTH sides' lines, delete the
  markers (timestamped, order-free). Header-field conflict: pick the value
  matching the latest Log event, then re-run `ledger validate`.

## Never

- Never edit headers, `## Commits`, or `## Log` by hand; never delete or
  rewrite existing Log lines (CI detects it).
- Never mint task ids by hand; only `ledger add`. Never edit
  `exempt_patterns` / `exempt_allowed_paths` to make a commit pass — ask
  via a HUMAN question.
- Never delete a task file (`drop` instead), never mark work done
  without evidence, never commit code that has no task, and
  never work on a task you haven't claimed (or been handed).
"""

CI_SNIPPET = '''import json
import subprocess
import sys


def test_ledger_valid():
    r = subprocess.run(
        [sys.executable, ".ledger/ledger.py", "validate", "--coverage",
         "--strict", "--json"],
        capture_output=True, text=True)
    payload = json.loads(r.stdout)
    assert r.returncode == 0, json.dumps(payload["errors"], indent=2)
'''

# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime(TS_FMT)


def parse_ts(ts: str) -> datetime | None:
    if not ts or not TS_RE.match(ts):
        return None
    return datetime.strptime(ts, TS_FMT).replace(tzinfo=timezone.utc)


def sanitize_inline(text: str) -> str:
    """One logical line: no newlines, no CRs."""
    return re.sub(r"[\r\n]+", "; ", str(text)).strip()


def sanitize_actor(actor: str) -> str:
    out = re.sub(r"[\[\]\r\n]", "_", str(actor)).strip()
    return out or "unknown"


def atomic_write(path: Path, text: str) -> None:
    """Write UTF-8, no BOM, LF-only, trailing newline, atomically."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip("\n") + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ledger-tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def err(code: str, message: str, task: str | None = None,
        fix_hint: str | None = None, severity: str = "error") -> dict:
    return {"code": code, "severity": severity, "task": task,
            "message": message, "fix_hint": fix_hint}


# ---------------------------------------------------------------------------
# Task file model: parse / serialize
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Task:
    header: dict
    sections: list  # list of [name, content]; order preserved from file
    path: Path | None = None

    # -- header accessors ---------------------------------------------------
    @property
    def id(self) -> str:
        return self.header.get("id", "")

    @property
    def title(self) -> str:
        return self.header.get("title", "")

    @property
    def status(self) -> str:
        return self.header.get("status", "")

    @property
    def priority(self) -> str:
        return self.header.get("priority", "")

    @property
    def size(self) -> str:
        return self.header.get("size", "")

    def list_field(self, key: str) -> list[str]:
        raw = self.header.get(key, "")
        return [x.strip() for x in raw.split(",") if x.strip()] if raw else []

    @property
    def depends_on(self) -> list[str]:
        return self.list_field("depends_on")

    @property
    def tags(self) -> list[str]:
        return self.list_field("tags")

    @property
    def resources(self) -> list[str]:
        """`resource:<slug>` tags: the resources a fresh claim on this task
        leases (DESIGN §7(h)). A prefix dialect inside tags — no header
        key, so every vendored copy validates the file unchanged."""
        return [t[len("resource:"):] for t in self.tags
                if t.startswith("resource:") and len(t) > len("resource:")]

    # -- sections -----------------------------------------------------------
    def get_section(self, name: str) -> str:
        for n, content in self.sections:
            if n == name:
                return content
        return ""

    def set_section(self, name: str, content: str) -> None:
        content = content.strip("\n")
        for pair in self.sections:
            if pair[0] == name:
                pair[1] = content
                return
        self.sections.append([name, content])

    # -- structured views ---------------------------------------------------
    def steps(self) -> list[dict]:
        out = []
        for line in self.get_section("Next Steps").split("\n"):
            m = CHECKBOX_RE.match(line)
            if m:
                out.append({"n": len(out) + 1, "text": m.group(2),
                            "done": m.group(1) == "x"})
        return out

    def questions(self) -> list[dict]:
        out = []
        for line in self.get_section("Open Questions").split("\n"):
            m = CHECKBOX_RE.match(line)
            if not m:
                continue
            checked, text = m.group(1) == "x", m.group(2)
            am = ANSWERED_RE.match(text)
            base = am.group(1) if am else text
            answer = am.group(3) if am else None
            human = base.startswith("HUMAN:")
            display = base[len("HUMAN:"):].strip() if human else base
            out.append({"n": len(out) + 1, "text": display, "human": human,
                        "answered": checked, "answer": answer})
        return out

    def commits(self) -> list[dict]:
        out = []
        for line in self.get_section("Commits").split("\n"):
            m = COMMIT_LINE_RE.match(line)
            if m:
                out.append({"sha": m.group(1), "date": m.group(2),
                            "subject": m.group(3)})
        return out

    def log(self) -> list[dict]:
        out = []
        for line in self.get_section("Log").split("\n"):
            m = LOG_LINE_RE.match(line)
            if m:
                out.append({"ts": m.group(1), "actor": m.group(2),
                            "verb": m.group(3), "text": m.group(4)})
        return out

    def closed_relation(self) -> dict | None:
        """{"kind": "duplicate"|"superseded", "target": id} from the newest
        `drop:` Log line that carries the CLI-authored relation grammar.

        Newest by TIMESTAMP, never by line position (Log lines are
        order-insensitive under merges); two lines sharing the maximum
        timestamp that disagree yield None. Diagnostic only — the target is
        not covered by the refs check and may itself have closed since.
        """
        drops = [e for e in self.log() if e["verb"] == "drop"]
        if not drops:
            return None
        newest = max(e["ts"] for e in drops)
        found: list[dict | None] = []
        for e in drops:
            if e["ts"] != newest:
                continue
            m = CLOSED_RELATION_RE.match(e["text"])
            found.append({"kind": CLOSED_RELATION_KIND[m.group(1)],
                          "target": m.group(2)} if m else None)
        first = found[0]
        if any(f != first for f in found):
            return None
        return first

    def last_activity(self) -> str:
        candidates = [self.header.get("created", ""),
                      self.header.get("claimed_at", ""),
                      self.header.get("closed", "")]
        candidates += [e["ts"] for e in self.log()]
        valid = [c for c in candidates if TS_RE.match(c or "")]
        return max(valid) if valid else ""

    # -- mutations ----------------------------------------------------------
    def append_log(self, actor: str, verb: str, text: str) -> None:
        line = f"- {now_ts()} [{sanitize_actor(actor)}] {verb}: {sanitize_inline(text)}"
        cur = self.get_section("Log")
        self.set_section("Log", (cur + "\n" + line) if cur else line)

    def append_commit_line(self, sha7: str, date: str, subject: str) -> bool:
        """Append a commit cache line; returns False if already present."""
        if any(c["sha"].startswith(sha7) or sha7.startswith(c["sha"])
               for c in self.commits()):
            return False
        line = f"- {sha7} {date} {sanitize_inline(subject)}"
        cur = self.get_section("Commits")
        self.set_section("Commits", (cur + "\n" + line) if cur else line)
        return True


def parse_task(text: str) -> tuple[Task | None, list[dict]]:
    """Parse a task file. Returns (task_or_None, problems).

    Problems are violation dicts with code 'parse'. A None task means the
    file was structurally unusable; a returned task may still carry problems.
    """
    problems: list[dict] = []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, [err("parse", "missing opening '---' header fence",
                          fix_hint="task files start with a --- fenced header")]
    fence_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fence_end = i
            break
    if fence_end is None:
        return None, [err("parse", "missing closing '---' header fence",
                          fix_hint="close the header with a --- line")]

    header: dict = {}
    for i in range(1, fence_end):
        line = lines[i]
        if not line.strip():
            continue
        m = HEADER_LINE_RE.match(line)
        if not m:
            problems.append(err(
                "parse", f"malformed header line {i + 1}: {line!r}",
                fix_hint="header lines are 'key: value' with a lowercase key"))
            continue
        key, val = m.group(1), m.group(2).strip()
        if key in header:
            problems.append(err(
                "parse",
                f"duplicate header key '{key}' (values: {header[key]!r} and {val!r})"
                " — signature of a bad merge resolution",
                fix_hint="keep exactly one line per key; consult ## Log for the "
                         "latest real value"))
        else:
            header[key] = val

    for key in REQUIRED_KEYS:
        if key not in header:
            problems.append(err("parse", f"missing required header key '{key}'"))

    sections: list = []
    cur_name: str | None = None
    cur_lines: list[str] = []
    in_code_fence = False
    for line in lines[fence_end + 1:]:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            cur_lines.append(line)
            continue
        m = None if in_code_fence else SECTION_RE.match(line)
        if m:
            if cur_name is None:
                if any(x.strip() for x in cur_lines):
                    problems.append(err(
                        "parse", "content before the first '## ' section",
                        fix_hint="move stray content into a named ## section"))
            else:
                sections.append([cur_name, "\n".join(cur_lines).strip("\n")])
            cur_name, cur_lines = m.group(1), []
        else:
            cur_lines.append(line)
    if cur_name is not None:
        sections.append([cur_name, "\n".join(cur_lines).strip("\n")])
    elif any(x.strip() for x in cur_lines):
        problems.append(err("parse", "body has content but no '## ' sections"))

    names = [n for n, _ in sections]
    for known in KNOWN_SECTIONS:
        if names.count(known) > 1:
            problems.append(err("parse", f"section '## {known}' appears more than once",
                                fix_hint="merge the duplicate sections into one"))
    known_seq = [n for n in names if n in KNOWN_SECTIONS]
    expected = [n for n in KNOWN_SECTIONS if n in known_seq]
    if known_seq != expected:
        problems.append(err(
            "parse",
            f"known sections out of canonical order: {known_seq} "
            f"(expected {expected})",
            fix_hint="order sections Spec, Next Steps, Open Questions, Commits, Log"))
    if names and "Log" in names and names[-1] != "Log":
        problems.append(err("parse", "'## Log' must be the last section",
                            fix_hint="move sections added after Log above it"))

    task = Task(header=header, sections=sections)
    return task, problems


def serialize_task(task: Task) -> str:
    out = ["---"]
    for key in HEADER_ORDER:
        val = task.header.get(key)
        if val is not None and str(val).strip() != "":
            out.append(f"{key}: {val}")
    for key, val in task.header.items():
        if key not in HEADER_ORDER and val is not None and str(val).strip() != "":
            out.append(f"{key}: {val}")
    out.append("---")
    out.append("")

    known = {name: task.get_section(name) for name in KNOWN_SECTIONS}
    unknown = [[n, c] for n, c in task.sections if n not in KNOWN_SECTIONS]
    ordered = ([[n, known[n]] for n in ("Spec", "Next Steps", "Open Questions",
                                        "Commits")]
               + unknown + [["Log", known["Log"]]])
    for name, content in ordered:
        out.append(f"## {name}")
        out.append("")
        if content:
            out.append(content)
            out.append("")
    text = "\n".join(out)
    return text.rstrip("\n") + "\n"


def new_task(prefix: str, existing_ids: set[str], title: str, priority: str,
             size: str) -> Task:
    while True:
        tid = f"{prefix}-" + "".join(secrets.choice(ID_CHARS) for _ in range(6))
        if tid not in existing_ids:
            break
    header = {"id": tid, "title": sanitize_inline(title), "status": "todo",
              "priority": priority, "size": size, "created": now_ts()}
    sections = [[n, ""] for n in KNOWN_SECTIONS]
    return Task(header=header, sections=sections)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def run_git(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "").strip()
    except FileNotFoundError:
        return 127, ""


def git_toplevel(start: Path) -> Path | None:
    rc, out = run_git(["rev-parse", "--show-toplevel"], start)
    return Path(out) if rc == 0 and out else None


def git_head(repo: Path) -> str | None:
    rc, out = run_git(["rev-parse", "--verify", "--quiet", "HEAD"], repo)
    return out if rc == 0 and out else None


def git_sha_exists(repo: Path, sha: str) -> bool:
    rc, _ = run_git(["rev-parse", "--verify", "--quiet", sha + "^{commit}"], repo)
    return rc == 0


def git_resolve_commit(repo: Path, ref: str) -> dict | None:
    rc, out = run_git(["show", "-s", "--no-show-signature",
                       "--format=%H%x1f%h%x1f%as%x1f%s", ref + "^{commit}"], repo)
    if rc != 0 or not out:
        return None
    parts = out.split("\x1f")
    if len(parts) != 4:
        return None
    return {"sha": parts[0], "sha7": parts[1], "date": parts[2],
            "subject": parts[3]}


def git_is_shallow(repo: Path) -> bool:
    rc, out = run_git(["rev-parse", "--is-shallow-repository"], repo)
    return rc == 0 and out == "true"


@dataclasses.dataclass
class Commit:
    sha: str
    sha7: str
    date: str
    subject: str
    body: str
    parents: list[str]
    task_ids: list[str]
    exempt_reason: str | None
    ctime: str = ""  # committer time, UTC ISO Z (report windows)


def iso_to_utc_z(value: str) -> str | None:
    """`%cI` / any offset-aware ISO-8601 -> the ledger's UTC Z stamp."""
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(TS_FMT)


def _parse_trailers(body: str) -> tuple[list[str], str | None]:
    """Ledger trailers from the FINAL paragraph only (git trailer semantics).

    A 'Ledger-Task:' line quoted mid-body — a docs example, protocol text in a
    squash message — is not a claim.
    """
    paragraphs = [p for p in re.split(r"\n[ \t]*\n", body.strip()) if p.strip()]
    if not paragraphs:
        return [], None
    task_ids, exempt = [], None
    for m in TRAILER_RE.finditer(paragraphs[-1]):
        if m.group(1) == "Ledger-Task":
            task_ids.append(m.group(2))
        elif exempt is None:
            exempt = m.group(2)
    return task_ids, exempt


def walk_commits(repo: Path, baseline: str | None,
                 since: str | None = None) -> tuple[list[Commit] | None, str | None]:
    """Walk commits in scope, newest first. Returns (commits, error_message)."""
    if git_head(repo) is None:
        return [], None
    if since:
        range_spec = f"{since}..HEAD"
    elif baseline:
        if not git_sha_exists(repo, baseline):
            return None, (f"baseline {baseline} is not reachable in this clone; "
                          "deepen the clone (fetch-depth: 0) or fix "
                          ".ledger/config.json")
        range_spec = f"{baseline}..HEAD"
    else:
        range_spec = "HEAD"
    # NUL separators: git forbids NUL in messages, so parsing cannot be
    # confused by message content (unlike \x1e/\x1f, which CAN appear).
    fmt = "%H%x00%h%x00%as%x00%s%x00%P%x00%cI%x00%B%x00%x1e"
    rc, out = run_git(["log", "--no-show-signature", f"--format={fmt}",
                       range_spec], repo)
    if rc != 0:
        return None, f"git log {range_spec} failed"
    commits = []
    for record in out.split("\x00\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x00", 6)
        if len(parts) != 7:
            continue
        sha, sha7, date, subject, parents, ctime, body = parts
        task_ids, exempt = _parse_trailers(body)
        commits.append(Commit(sha=sha.strip(), sha7=sha7, date=date,
                              subject=subject, body=body,
                              parents=parents.split(), task_ids=task_ids,
                              exempt_reason=exempt,
                              ctime=iso_to_utc_z(ctime) or ""))
    return commits, None


def commit_files(repo: Path, sha: str, merge: bool) -> list[str] | None:
    """Files a commit introduces. None on git failure (callers fail CLOSED).

    Merge commits use the combined diff (--cc): a clean merge introduces
    nothing and lists nothing; conflict resolutions / evil merges list the
    files whose result differs from every parent.
    """
    if merge:
        args = ["diff-tree", "--cc", "--name-only", "-r", sha]
    else:
        args = ["diff-tree", "--no-commit-id", "--name-only", "-r", "--root",
                sha]
    # quotePath=false: non-ASCII paths come back unquoted, so glob policies
    # see `docs/ä.md`, not `"docs/\303\244.md"`
    rc, out = run_git(["-c", "core.quotePath=false", *args], repo)
    if rc != 0:
        return None
    return [line for line in out.split("\n")
            if line.strip() and not re.fullmatch(r"[0-9a-f]{40}", line.strip())]


EXEMPT_POLICY_HINT = (
    "exemptions are only for commits with no product-work obligation; this "
    "work needs a task: `ledger add \"...\"`, then a `Ledger-Task:` trailer "
    "(unpushed) or `ledger link <id> <sha>` (pushed). Widening "
    "exempt_allowed_paths is a project decision — ask via a HUMAN question, "
    "do not edit config.json to make this commit pass; a machine-produced "
    "diff (generated artifacts) is the one case for widening")


def exempt_policy_globs(config: dict) -> list[str] | None:
    """The allowed-path globs, `.ledger/**` always first; None = policy off."""
    raw = config.get("exempt_allowed_paths")
    if raw is None:
        return None
    if (not isinstance(raw, list)
            or any(not isinstance(g, str) or not g.strip() for g in raw)):
        raise LedgerError(
            "config", "exempt_allowed_paths must be a list of non-empty "
            "glob strings", fix_hint="fix .ledger/config.json")
    return [".ledger/**"] + [g.strip() for g in raw]


def _glob_re(glob: str) -> re.Pattern:
    """gitignore-like: `*` and `?` never cross `/`, `**` crosses anything.
    (stdlib fnmatch lets `*` swallow directories — `build/*.js` would match
    `build/sub/x.js` — which is the surprising rule.)"""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile("^" + out + "$")


def path_allowed(path: str, globs: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    for g in globs:
        if g.endswith("/**"):
            prefix = g[:-3]
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif "/" in g:
            if _glob_re(g).match(path):
                return True
        elif _glob_re(g).match(name):
            return True
    return False


def exempt_policy_offenders(commit: Commit, repo: Path, globs: list[str],
                            exempt_res: list[re.Pattern]) -> list[str] | None:
    """Paths an exempt commit touches outside the policy, or None when the
    policy does not apply to it. Applies to the explicit `Ledger-Exempt`
    channel and — decision (b), 2026-09-01 — to pattern-exempt TRUE merges
    via the combined diff (a clean merge lists nothing; only evil-merge
    content shows). Single-parent pattern exemptions (^Revert, squash
    merges) stay exempt: the squash gap is documented, not closed."""
    merge = len(commit.parents) > 1
    if commit.exempt_reason is not None:
        pass
    elif merge and any(p.search(commit.subject) for p in exempt_res):
        pass
    else:
        return None
    files = commit_files(repo, commit.sha, merge=merge)
    if files is None:
        return ["(git diff-tree failed — refusing to guess)"]
    return [f for f in files if not path_allowed(f, globs)]


def compile_exempt_patterns(config: dict) -> list[re.Pattern]:
    out = []
    for pattern in config.get("exempt_patterns", []):
        try:
            out.append(re.compile(pattern))
        except re.error as e:
            raise LedgerError(
                "config",
                f"invalid regex in config exempt_patterns: {pattern!r} ({e})",
                fix_hint="fix the pattern in .ledger/config.json")
    return out


SHA_TOKEN_RE = re.compile(r"[0-9a-f]{7,40}")


def explicit_links(tasks: list) -> dict[str, set[tuple[str, str]]]:
    """sha prefix (first 7 chars) -> {(sha_token, task_id)} for every
    `## Commits` line whose task Log ALSO carries a CLI-authored `link:` line
    naming the same commit.

    Both halves are required: the Commits line alone is a cache anyone can
    hand-edit; the Log line is sha-verified at write time, actor-tagged and
    tamper-protected once committed. Together they are an explicit claim on
    a par with a trailer (DESIGN §4) — never inferred linkage.
    """
    out: dict[str, set[tuple[str, str]]] = {}
    for t in tasks:
        tokens = []
        for e in t.log():
            if e["verb"] != "link":
                continue
            first = e["text"].split(" ", 1)[0]
            if SHA_TOKEN_RE.fullmatch(first):
                tokens.append(first)
        for c in t.commits():
            s = c["sha"]
            if any(s.startswith(tok) or tok.startswith(s) for tok in tokens):
                out.setdefault(s[:7], set()).add((s, t.id))
    return out


def explicit_link_tasks(commit: Commit,
                        explicit: dict | None) -> list[str]:
    if not explicit:
        return []
    return sorted({tid for s, tid in explicit.get(commit.sha[:7], ())
                   if commit.sha.startswith(s)})


def classify_commit(commit: Commit, repo: Path, known_ids: set[str],
                    exempt_res: list[re.Pattern],
                    explicit: dict | None = None) -> tuple[str, list[str]]:
    """Returns (bucket, dangling_ids). Buckets: linked | exempt | unlinked.

    `explicit` is explicit_links(); a commit an agent linked with
    `ledger link` after pushing counts as linked exactly like a trailer.
    """
    dangling = [t for t in commit.task_ids if t not in known_ids]
    if any(t in known_ids for t in commit.task_ids):
        return "linked", dangling
    if explicit_link_tasks(commit, explicit):
        return "linked", dangling
    if commit.exempt_reason is not None:
        return "exempt", dangling
    if any(p.search(commit.subject) for p in exempt_res):
        return "exempt", dangling
    if dangling:
        return "unlinked", dangling
    files = commit_files(repo, commit.sha, merge=len(commit.parents) > 1)
    if files is None:
        return "unlinked", dangling  # git failed: never exempt on a guess
    if not files or all(f.startswith(".ledger/") for f in files):
        return "exempt", dangling
    return "unlinked", dangling


# ---------------------------------------------------------------------------
# Ledger context and task IO
# ---------------------------------------------------------------------------


class LedgerError(Exception):
    def __init__(self, code: str, message: str, fix_hint: str | None = None,
                 exit_code: int = 2, task: str | None = None):
        super().__init__(message)
        self.violation = err(code, message, task=task, fix_hint=fix_hint)
        self.exit_code = exit_code


@dataclasses.dataclass
class Ctx:
    ledger_dir: Path
    config: dict
    actor: str
    json_mode: bool

    @property
    def tasks_dir(self) -> Path:
        return self.ledger_dir / "tasks"

    @property
    def repo(self) -> Path | None:
        return git_toplevel(self.ledger_dir.parent)

    @property
    def prefix(self) -> str:
        return self.config.get("prefix", "T")

    def id_pattern(self) -> re.Pattern:
        return re.compile(rf"^{re.escape(self.prefix)}-[a-z0-9]{{6}}$")


# ---------------------------------------------------------------------------
# Cross-process mutation lock
#
# os.replace makes individual file writes atomic, but a mutating command is a
# read -> decide -> write sequence over shared task state: without
# serialization, two agent processes on the SAME checkout can both read a task
# as todo and both "successfully" claim it. Every mutating command therefore
# takes one ledger-wide lock BEFORE loading task state and holds it until the
# process exits (the OS releases it even on crash). Cross-BRANCH concurrency
# stays advisory by design — separate checkouts are the isolation model.
# ---------------------------------------------------------------------------

LOCK_FILENAME = ".lock"
_LOCK_HANDLE: int | None = None  # keeps the locked fd alive for process life


def _remove_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _acquire_mutation_lock(ledger_dir: Path) -> None:
    global _LOCK_HANDLE
    if _LOCK_HANDLE is not None:
        return
    try:
        timeout = float(os.environ.get("LEDGER_LOCK_TIMEOUT", "") or 10.0)
    except ValueError:
        timeout = 10.0
    lock_path = ledger_dir / LOCK_FILENAME
    deadline = time.monotonic() + timeout
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    while True:
        try:
            if msvcrt is not None:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            elif fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                # exotic platform without either: O_EXCL sidecar lockfile
                sidecar = str(lock_path) + ".pid"
                side_fd = os.open(sidecar,
                                  os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.write(side_fd, str(os.getpid()).encode("ascii"))
                os.close(side_fd)
                atexit.register(_remove_quietly, sidecar)
            _LOCK_HANDLE = fd  # held until process exit; OS releases it
            return
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise LedgerError(
                    "lock-timeout",
                    f"could not acquire the ledger lock ({lock_path}) within "
                    f"{timeout:.1f}s — another ledger process holds it",
                    fix_hint="retry; raise LEDGER_LOCK_TIMEOUT (seconds) if "
                             "long-running ledger operations are expected")
            time.sleep(0.05)


def find_ledger_dir(start: Path | None = None) -> Path | None:
    p = (start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        d = candidate / ".ledger"
        if d.is_dir():
            return d
    return None


def resolve_actor(args) -> str:
    if getattr(args, "session", None):
        return sanitize_actor(args.session)
    env = os.environ.get("LEDGER_SESSION", "").strip()
    if env:
        return sanitize_actor(env)
    rc, out = run_git(["config", "user.name"], Path.cwd())
    if rc == 0 and out:
        return sanitize_actor(out)
    return "unknown"


def make_ctx(args, mutating: bool = False) -> Ctx:
    ledger_dir = find_ledger_dir()
    if ledger_dir is None:
        raise LedgerError(
            "not-initialized",
            "no .ledger/ directory found here or in any parent directory",
            fix_hint="run: python ledger.py init  (from the repo root)")
    if mutating:
        # serialize BEFORE any task state is read (see lock rationale above)
        _acquire_mutation_lock(ledger_dir)
    config = dict(DEFAULT_CONFIG)
    cfg_path = ledger_dir / "config.json"
    if cfg_path.exists():
        try:
            config.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            raise LedgerError("config", f"cannot read {cfg_path}: {e}",
                              fix_hint="fix or delete .ledger/config.json")
    return Ctx(ledger_dir=ledger_dir, config=config,
               actor=resolve_actor(args), json_mode=getattr(args, "json", False))


def task_path(ctx: Ctx, tid: str) -> Path:
    return ctx.tasks_dir / f"{tid}.md"


def load_task_file(path: Path) -> tuple[Task | None, list[dict]]:
    try:
        raw = path.read_bytes()
    except OSError as e:
        return None, [err("parse", f"cannot read {path.name}: {e}")]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        return None, [err("encoding", f"{path.name} is not valid UTF-8: {e}",
                          fix_hint="re-save the file as UTF-8")]
    task, problems = parse_task(text)
    if task is not None:
        task.path = path
    return task, problems


def load_all_tasks(ctx: Ctx) -> tuple[list[Task], list[dict]]:
    tasks, problems = [], []
    if not ctx.tasks_dir.is_dir():
        return tasks, problems
    for path in sorted(ctx.tasks_dir.glob("*.md")):
        task, probs = load_task_file(path)
        for p in probs:
            p["task"] = p.get("task") or path.stem
        problems.extend(probs)
        if task is not None:
            tasks.append(task)
    return tasks, problems


def save_task(task: Task) -> None:
    """Serialize and write — but only if the result survives a parse
    round-trip identically. The tool must never author a file whose content
    would be reinterpreted (e.g. an unfenced '## ' line inside a section
    would split it, silently relocating or shadowing content)."""
    assert task.path is not None
    text = serialize_task(task)
    reparsed, problems = parse_task(text)
    ok = reparsed is not None and not problems
    if ok:
        # serialization keeps only the first copy of a duplicated known
        # section — never write a task that still carries duplicates
        names = [n for n, _ in task.sections if n in KNOWN_SECTIONS]
        ok = len(names) == len(set(names))
    if ok:
        want = {k: str(v) for k, v in task.header.items()
                if v is not None and str(v).strip() != ""}
        ok = want == reparsed.header
    if ok:
        def first_by_name(sections):
            out: dict = {}
            for name, content in sections:
                out.setdefault(name, content)
            return out
        a, b = first_by_name(task.sections), first_by_name(reparsed.sections)
        ok = all(a.get(n, "") == b.get(n, "") for n in set(a) | set(b))
    if not ok:
        raise LedgerError(
            "would-corrupt",
            f"refusing to write {task.path.name}: content would not survive a "
            "parse round-trip identically (an unfenced '## ' heading inside a "
            "section body, or a duplicated section)",
            task=task.header.get("id"),
            fix_hint="use ### or deeper headings inside sections, wrap "
                     "examples in ``` code fences, and merge duplicate "
                     "sections by hand")
    atomic_write(task.path, text)


def structural_problem_stems(problems: list[dict]) -> set[str]:
    # encoding damage (CRLF/BOM) is NOT structural: normalization is lossless
    # and CLI writes are the documented repair path. Parse problems are — a
    # rewrite would silently canonicalize away bad-merge evidence.
    return {p.get("task") for p in problems
            if p.get("code") == "parse" and p.get("task")}


def load_task_or_die(ctx: Ctx, fragment: str, for_write: bool = False) -> Task:
    """Resolve an id fragment to exactly one task, or raise LedgerError.

    With for_write=True, refuse a task whose file has parse problems:
    rewriting such a file would silently canonicalize it — dropping duplicate
    header values, duplicate sections, or preamble left by a bad merge
    resolution, destroying the other side's data and the very evidence
    `validate` exists to surface. (Encoding damage is NOT gated: CRLF/BOM
    normalization is lossless and CLI writes are the documented repair path.)
    """
    tasks, problems = load_all_tasks(ctx)
    frag = fragment.strip().lower()
    exact = [t for t in tasks if t.id.lower() == frag]
    matches = exact if len(exact) == 1 else \
        [t for t in tasks if frag in t.id.lower()]
    if len(matches) == 1:
        task = matches[0]
        if for_write:
            stems = structural_problem_stems(problems)
            stem = task.path.stem if task.path else task.id
            if task.id in stems or stem in stems:
                first = next(p for p in problems if p.get("task") in
                             (task.id, stem))
                raise LedgerError(
                    "corrupt-file",
                    f"{stem}.md has structural problems and will not be "
                    f"modified: {first['message']}",
                    task=task.id,
                    fix_hint="run ledger validate --json and repair the file "
                             "(or restore it from git history) first")
        return task
    if not matches:
        raise LedgerError("no-such-task", f"no task id matches '{fragment}'",
                          fix_hint="ledger list shows all ids")
    raise LedgerError(
        "ambiguous-id",
        f"'{fragment}' matches multiple tasks: "
        + ", ".join(f"{t.id} ({t.title})" for t in matches),
        fix_hint="use more characters of the id")


# ---------------------------------------------------------------------------
# Output envelope
# ---------------------------------------------------------------------------


def emit(args, ok: bool, data: dict, errors: list[dict] | None = None,
         human: list[str] | None = None) -> None:
    errors = errors or []
    if getattr(args, "json", False):
        print(json.dumps({"ok": ok, "data": data, "errors": errors}, indent=2))
    else:
        for line in (human or []):
            print(line)
        for e in errors:
            sev = (e.get("severity") or "error").upper()
            task = f" {e['task']}" if e.get("task") else ""
            hint = f"  (fix: {e['fix_hint']})" if e.get("fix_hint") else ""
            print(f"{sev} {e['code']}{task}: {e['message']}{hint}")


def task_brief(task: Task) -> dict:
    return {
        **{k: task.header.get(k) for k in HEADER_ORDER if k in task.header},
        "open_steps": sum(1 for s in task.steps() if not s["done"]),
        "open_questions": sum(1 for q in task.questions() if not q["answered"]),
        "commits": len(task.commits()),
        "closed_relation": task.closed_relation(),
        "resources": task.resources,
    }


def dependents_of(task: Task, all_tasks: list) -> list[str]:
    """Every task (any status) whose depends_on names this one — the reverse
    edge, computed on read, never stored. A wave is a task whose depends_on
    lists its members, so this answers "which wave was T-x in"."""
    return [t.id for t in sorted(all_tasks, key=sort_key)
            if task.id in t.depends_on]


def task_full(ctx: Ctx, task: Task, trailer_map: dict | None = None,
              all_tasks: list | None = None) -> dict:
    section_shas = [c["sha"] for c in task.commits()]
    trailer_shas = (trailer_map or {}).get(task.id, [])
    effective = list(dict.fromkeys(
        section_shas + [s[:7] for s in trailer_shas]))
    if all_tasks is None:
        all_tasks, _ = load_all_tasks(ctx)
    return {
        "header": {k: task.header.get(k) for k in HEADER_ORDER
                   if k in task.header},
        "spec": task.get_section("Spec"),
        "next_steps": task.steps(),
        "open_questions": task.questions(),
        "commits": task.commits(),
        "log": task.log(),
        "effective_commits": effective,
        "closed_relation": task.closed_relation(),
        "dependents": dependents_of(task, all_tasks),
        "resources": task.resources,
        "last_activity": task.last_activity(),
        "path": str(task.path) if task.path else None,
    }


def task_digest(ctx: Ctx, task: Task, last: int = 10,
                trailer_map: dict | None = None,
                all_tasks: list | None = None) -> dict:
    """The bounded derived view (DESIGN §5): everything an agent needs to
    resume WITHOUT the unbounded parts. Only `recent_log` is capped; the
    Spec body is deliberately excluded (line count only) so the one file
    read stays the authority on what to build."""
    steps = task.steps()
    questions = task.questions()
    log = sorted(task.log(), key=lambda e: e["ts"])  # stable: ties keep file order
    answers = [e for e in log if e["verb"] == "answer"]
    human_gated = []
    for q in questions:
        if not q["human"]:
            continue
        prefix = f"'HUMAN: {q['text']}' ->"
        by = [e for e in answers if e["text"].startswith(prefix)]
        human_gated.append({"n": q["n"], "text": q["text"],
                            "answered": q["answered"], "answer": q["answer"],
                            "answered_by": by[-1]["actor"] if by else None})
    section_shas = [c["sha"] for c in task.commits()]
    trailer_shas = (trailer_map or {}).get(task.id, [])
    effective = list(dict.fromkeys(section_shas + [s[:7] for s in trailer_shas]))
    if all_tasks is None:
        all_tasks, _ = load_all_tasks(ctx)
    spec = task.get_section("Spec")
    return {
        "header": {k: task.header.get(k) for k in HEADER_ORDER
                   if k in task.header},
        "path": str(task.path) if task.path else None,
        "steps_open": [s for s in steps if not s["done"]],
        "steps_total": len(steps),
        "steps_done": sum(1 for s in steps if s["done"]),
        "human_gated_questions": human_gated,
        "open_questions": sum(1 for q in questions if not q["answered"]),
        "recent_log": log[-last:] if last > 0 else [],
        "log_total": len(log),
        "dead_ends": [e for e in log if e["verb"] == "note(dead-end)"],
        "commits": task.commits(),
        "effective_commits": effective,
        "closed_relation": task.closed_relation(),
        "dependents": dependents_of(task, all_tasks),
        "last_activity": task.last_activity(),
        "spec_lines": len(spec.split("\n")) if spec else 0,
    }


def digest_human(d: dict) -> list[str]:
    h = d["header"]
    out = [f"{h.get('id')} [{h.get('priority')}/{h.get('size')}] "
           f"{h.get('title')} — {h.get('status')}"
           + (f", claimed by {h['claimed_by']}" if h.get("claimed_by") else "")
           + (f", blocked on {h['blocked_on']}" if h.get("blocked_on") else ""),
           f"  spec: {d['spec_lines']} line(s) in {d['path']}",
           f"  steps: {d['steps_done']}/{d['steps_total']} done"]
    for s in d["steps_open"]:
        out.append(f"    [ ] {s['n']}. {s['text']}")
    for q in d["human_gated_questions"]:
        mark = "answered" if q["answered"] else "OPEN"
        out.append(f"  human ({mark}): {q['text']}"
                   + (f" -> {q['answer']}" if q["answer"] else ""))
    for e in d["dead_ends"]:
        out.append(f"  dead end: {e['text']}")
    out.append(f"  recent log ({len(d['recent_log'])} of {d['log_total']}):")
    for e in d["recent_log"]:
        out.append(f"    {e['ts']} {e['verb']}: {e['text']}")
    out.append(f"  commits: {', '.join(d['effective_commits']) or '(none)'}"
               f"; dependents: {', '.join(d['dependents']) or '(none)'}"
               f"; last activity {d['last_activity']}")
    return out


def _brief_args_ok(args, digest: bool) -> None:
    """--last / --no-git only make sense for the digest shape."""
    if not digest and (getattr(args, "last", None) is not None
                       or getattr(args, "no_git", False)):
        raise LedgerError("usage", "--last / --no-git apply to the digest "
                          "shape only (show --brief; next without --full)",
                          exit_code=3)


def absorbed_by(task: Task, all_tasks: list[Task]) -> list[dict]:
    """Every task whose closed relation targets this one — the reverse view,
    derived on read so the survivor's file is never written."""
    out = []
    for other in sorted(all_tasks, key=sort_key):
        rel = other.closed_relation()
        if rel and rel["target"] == task.id:
            out.append({"id": other.id, "kind": rel["kind"]})
    return out


def trailer_links(ctx: Ctx) -> dict[str, list[str]]:
    """task id -> full shas claimed via Ledger-Task trailers (best effort)."""
    repo = ctx.repo
    if repo is None:
        return {}
    commits, error = walk_commits(repo, ctx.config.get("baseline"))
    if commits is None or error:
        return {}
    out: dict[str, list[str]] = {}
    for c in commits:
        for tid in c.task_ids:
            out.setdefault(tid, []).append(c.sha)
    return out


# ---------------------------------------------------------------------------
# Eligibility (`next`)
# ---------------------------------------------------------------------------


def sort_key(task: Task):
    prio = PRIORITIES.index(task.priority) if task.priority in PRIORITIES else 9
    return (prio, task.header.get("created", ""), task.id)


def claim_is_stale_at(task: Task, stale_days: int, ref_ts: str | None) -> bool:
    """Staleness relative to ref_ts (a UTC Z stamp) instead of now — the
    report asks "was this claim stranded at the end of the window?"."""
    last = task.last_activity()
    dt = parse_ts(last)
    if dt is None:
        return True
    ref = parse_ts(ref_ts) if ref_ts else None
    now = ref or datetime.now(timezone.utc)
    return now - dt > timedelta(days=stale_days)


def claim_is_stale(task: Task, stale_days: int) -> bool:
    return claim_is_stale_at(task, stale_days, None)


# ---------------------------------------------------------------------------
# Title similarity (advisory: `add` warns, never refuses; never in validate)
# ---------------------------------------------------------------------------

TITLE_STOPWORDS = frozenset(
    "the and for with from into when that this add fix use make support "
    "handle".split())
SIMILAR_MIN_SHARED = 2      # shared tokens needed before a pair is a candidate
SIMILAR_MIN_OVERLAP = 0.6   # |A∩B| / min(|A|,|B|)
SIMILAR_CAP = 5


def title_tokens(title: str) -> set[str]:
    """Deterministic token set for title comparison: lowercase, split on
    non-alphanumerics, drop tokens shorter than 3 chars and stopwords."""
    return {tok for tok in re.split(r"[^a-z0-9]+", title.lower())
            if len(tok) >= 3 and tok not in TITLE_STOPWORDS}


def title_similarity(a: set[str], b: set[str], closed: bool) -> float | None:
    """Score in (0, 1] when the pair is a duplicate candidate, else None.
    An empty side is never a candidate (also guards the division). A CLOSED
    task only matches on an identical token set — re-filing finished or
    dropped work is the classic duplicate; loose matches on history would
    be noise. No raw-string containment: it has no word boundaries."""
    if not a or not b:
        return None
    if closed:
        return 1.0 if a == b else None
    shared = a & b
    if len(shared) < SIMILAR_MIN_SHARED:
        return None
    overlap = len(shared) / min(len(a), len(b))
    return overlap if overlap >= SIMILAR_MIN_OVERLAP else None


def similar_tasks(title: str, tasks: list, exclude: str | None = None
                  ) -> list[tuple[Task, float]]:
    mine = title_tokens(title)
    out = []
    for t in tasks:
        if t.id == exclude:
            continue
        score = title_similarity(mine, title_tokens(t.title),
                                 closed=t.status in ("done", "dropped"))
        if score is not None:
            out.append((t, score))
    out.sort(key=lambda x: (-x[1], sort_key(x[0])))
    return out[:SIMILAR_CAP]


def _similar_task_warning(new_id: str, old: Task, score: float) -> dict:
    if old.status in ("done", "dropped"):
        hint = (f"{old.id} closed on {(old.header.get('closed') or '?')[:10]}; "
                f"if this is a regression or redo, keep {new_id} and "
                f"ledger note {new_id} 'follows {old.id}'; if you re-filed "
                f"finished work, ledger drop {new_id} --duplicate-of {old.id}")
    else:
        hint = (f"if it is the same work: ledger drop {new_id} --duplicate-of "
                f"{old.id} and carry any new evidence into {old.id} with "
                "ledger note/step; otherwise ignore")
    return err("similar-task",
               f"{new_id} looks similar to {old.id} ({old.status}) "
               f"'{old.title}'", task=new_id, severity="warning",
               fix_hint=hint)


def _dep_status_text(dep: str, by_id: dict[str, Task]) -> str:
    """`T-x (todo)`; a dropped dependency also names where its work went:
    `T-x (dropped, duplicate-of T-y)` so the re-point is one read away."""
    if dep not in by_id:
        return f"{dep} (missing)"
    task = by_id[dep]
    rel = task.closed_relation() if task.status == "dropped" else None
    if rel:
        return (f"{dep} ({task.status}, "
                f"{CLOSED_RELATION_TOKEN[rel['kind']]} {rel['target']})")
    return f"{dep} ({task.status})"


def held_resources(tasks: list, stale_days: int) -> dict[str, Task]:
    """resource slug -> the task whose FRESH in_progress claim leases it.
    A lease is a pure function of claim fields already in the file: status
    in_progress (a blocked task may retain claimed_by but does not hold),
    not stale (any Log activity keeps it alive), tag `resource:<slug>`.
    First holder in sort_key order wins the map; contention is reported
    separately by validate."""
    held: dict[str, Task] = {}
    for t in sorted(tasks, key=sort_key):
        if t.status != "in_progress" or claim_is_stale(t, stale_days):
            continue
        for r in t.resources:
            held.setdefault(r, t)
    return held


def resource_clash(task: Task, held: dict[str, Task]) -> tuple[str, Task] | None:
    """(resource, holder) when another task's fresh claim leases one of
    this task's resources; the task's own claim never blocks itself."""
    for r in task.resources:
        holder = held.get(r)
        if holder is not None and holder.id != task.id:
            return r, holder
    return None


def compute_eligible(tasks: list[Task], config: dict):
    """Returns (eligible, why, blocked_on_human, stale_blocks, resources_held).

    eligible: [(task, flag)] sorted; flag is None or 'stale_claim'.
    why: machine-readable near-miss explanations for every open task skipped.
    """
    done_ids = {t.id for t in tasks if t.status == "done"}
    by_id = {t.id: t for t in tasks}
    stale_days = int(config.get("stale_claim_days", 7))
    held = held_resources(tasks, stale_days)
    eligible, why, human, stale_blocks = [], [], [], []
    for task in sorted(tasks, key=sort_key):
        if task.status not in OPEN_STATUSES:
            continue
        if task.status == "blocked":
            reason = task.header.get("blocked_on", "?")
            text = f"blocked_on {reason}"
            # a task-targeted block never auto-clears: once the target has
            # closed, say so instead of leaving a silent dead end
            target = by_id.get(reason)
            if target is not None and target.status in ("done", "dropped"):
                stale_blocks.append({"id": task.id, "blocked_on": reason,
                                     "target_status": target.status})
                if target.status == "done":
                    text += f" (done — ledger unblock {task.id})"
                else:
                    text += (f" (dropped — it will never close; ledger "
                             f"unblock {task.id}, then block --on the real "
                             "reason)")
            why.append({"id": task.id, "ineligible_because": text})
            if reason == "human":
                human.append({"id": task.id, "title": task.title})
            continue
        flag = None
        if task.status == "in_progress":
            if not claim_is_stale(task, stale_days):
                why.append({"id": task.id, "ineligible_because":
                            f"claimed by {task.header.get('claimed_by', '?')} "
                            f"at {task.header.get('claimed_at', '?')}"})
                continue
            flag = "stale_claim"  # still subject to the gates below
        missing = [d for d in task.depends_on if d not in done_ids]
        if missing:
            details = ", ".join(_dep_status_text(d, by_id) for d in missing)
            why.append({"id": task.id,
                        "ineligible_because": f"depends_on {details}"})
            continue
        if task.size == "xl":
            why.append({"id": task.id, "ineligible_because":
                        "size xl — split it into smaller tasks first"})
            continue
        clash = resource_clash(task, held)
        if clash:
            r, holder = clash
            why.append({"id": task.id, "ineligible_because":
                        f"resource {r} held by {holder.id} (claimed by "
                        f"{holder.header.get('claimed_by', '?')} at "
                        f"{holder.header.get('claimed_at', '?')})"})
            continue
        eligible.append((task, flag))
    return (eligible, why, human, stale_blocks,
            {r: t.id for r, t in held.items()})


def blocked_on_closed_warnings(closed: Task, all_tasks: list) -> list[dict]:
    """Open tasks blocked on a task that just closed. Blocks never
    auto-clear (the --why may name more than the target finishing), so the
    closing verb names each one with its unblock hint instead."""
    out = []
    for t in sorted(all_tasks, key=sort_key):
        if t.status in OPEN_STATUSES and t.header.get("blocked_on") == closed.id:
            hint = f"ledger unblock {t.id}"
            if closed.status == "dropped":
                hint += " (then block --on the real reason, if one remains)"
            out.append(err(
                "refs",
                f"{t.id} is blocked_on {closed.id}, which is now "
                f"{closed.status} — blocks never auto-clear",
                task=t.id, severity="warning", fix_hint=hint))
    return out


def apply_claim(task: Task, actor: str, takeover_from: str | None,
                extra: str = "") -> None:
    task.header["status"] = "in_progress"
    task.header["claimed_by"] = actor
    task.header["claimed_at"] = now_ts()
    task.header.pop("blocked_on", None)
    if takeover_from:
        text = f"taking over claim from {takeover_from}"
    else:
        text = "claimed"
    task.append_log(actor, "claim", text + extra)


def _resource_guard(task: Task, all_tasks: list, stale_days: int,
                    force: bool, verb: str) -> str:
    """Refuse to lease a resource another fresh claim holds unless --force;
    returns the Log suffix to record a forced double-hold."""
    clash = resource_clash(task, held_resources(all_tasks, stale_days))
    if clash is None:
        return ""
    r, holder = clash
    if not force:
        raise LedgerError(
            "resource-held",
            f"resource {r} is held by {holder.id} (claimed by "
            f"{holder.header.get('claimed_by', '?')} at "
            f"{holder.header.get('claimed_at', '?')})", task=task.id,
            fix_hint=f"wait for {holder.id} to release, pick another task, "
                     f"or {verb} --force if you will serialize the resource "
                     "yourself")
    return f" (resource {r} also held by {holder.id})"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:
    script = Path(__file__).resolve()
    root = git_toplevel(Path.cwd()) or Path.cwd()
    ledger_dir = (root / ".ledger").resolve()
    created = not (ledger_dir / "config.json").exists()
    ledger_dir.mkdir(parents=True, exist_ok=True)
    _acquire_mutation_lock(ledger_dir)
    (ledger_dir / "tasks").mkdir(exist_ok=True)

    dest_script = ledger_dir / "ledger.py"
    if dest_script.resolve() != script:
        atomic_write(dest_script, script.read_text(encoding="utf-8"))

    cfg_path = ledger_dir / "config.json"
    if created:
        config = dict(DEFAULT_CONFIG)
        if args.prefix:
            config["prefix"] = args.prefix
        repo = git_toplevel(ledger_dir.parent)
        config["baseline"] = git_head(repo) if repo else None
        config["exempt_allowed_paths"] = list(DEFAULT_EXEMPT_ALLOWED_PATHS)
        atomic_write(cfg_path, json.dumps(config, indent=2))
    else:
        config = dict(DEFAULT_CONFIG)
        config.update(json.loads(cfg_path.read_text(encoding="utf-8")))

    atomic_write(ledger_dir / "PROTOCOL.md", PROTOCOL_TEXT)

    repo = git_toplevel(ledger_dir.parent)
    root = repo if repo else ledger_dir.parent

    ga_path = root / ".gitattributes"
    ga_text = ga_path.read_text(encoding="utf-8") if ga_path.exists() else ""
    if GITATTRIBUTES_LINE not in ga_text:
        sep = "" if (not ga_text or ga_text.endswith("\n")) else "\n"
        atomic_write(ga_path, ga_text + sep + GITATTRIBUTES_LINE + "\n")

    gi_path = root / ".gitignore"
    gi_text = gi_path.read_text(encoding="utf-8") if gi_path.exists() else ""
    if GITIGNORE_LINE not in gi_text:
        sep = "" if (not gi_text or gi_text.endswith("\n")) else "\n"
        atomic_write(gi_path, gi_text + sep + GITIGNORE_LINE + "\n")

    claude_path = root / "CLAUDE.md"
    block = f"{CLAUDE_BEGIN}\n\n{PROTOCOL_TEXT}\n{CLAUDE_END}\n"
    if claude_path.exists():
        text = claude_path.read_text(encoding="utf-8")
        if CLAUDE_BEGIN in text and CLAUDE_END in text:
            pre, rest = text.split(CLAUDE_BEGIN, 1)
            _, post = rest.split(CLAUDE_END, 1)
            atomic_write(claude_path, pre + block + post)
        else:
            sep = "" if text.endswith("\n") else "\n"
            atomic_write(claude_path, text + sep + "\n" + block)
    else:
        atomic_write(claude_path, block)

    baseline_note = config.get("baseline") or (
        "(none — no git history yet; ALL future commits are in "
        "coverage scope)")
    human = [
        f"ledger initialized at {ledger_dir}",
        f"baseline: {baseline_note}",
        "",
        "Commit the bootstrap with:  git add -A && git commit -m 'Add task ledger' "
        "-m 'Ledger-Exempt: ledger bootstrap'",
        "",
        "Add this test to your project's CI suite (e.g. tests/test_ledger.py):",
        "",
        CI_SNIPPET,
        "Optional shell alias:  alias ledger='python .ledger/ledger.py'",
    ]
    emit(args, True, {"ledger_dir": str(ledger_dir),
                      "baseline": config.get("baseline"),
                      "created": created, "ci_snippet": CI_SNIPPET},
         human=human)
    return 0


def _require_title(raw: str) -> str:
    title = sanitize_inline(raw)
    if not title:
        raise LedgerError("usage", "title must be non-empty", exit_code=3)
    return title


def _clean_tag(raw: str) -> str:
    tag = sanitize_inline(raw)
    if not tag or "," in tag:
        raise LedgerError("usage",
                          f"invalid tag {raw!r}: tags are non-empty and "
                          "cannot contain commas (the list separator)",
                          exit_code=3)
    return tag


def _check_section_body(text: str, what: str) -> str:
    """Multiline section input must not smuggle in '## ' headings — outside
    code fences they would split the task file into new sections."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    in_fence = False
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence and SECTION_RE.match(line):
            raise LedgerError(
                "usage",
                f"{what} contains an unfenced '## ' heading "
                f"({line.strip()[:40]!r}), which would split the task file",
                fix_hint="use ### or deeper headings, or wrap examples in "
                         "``` code fences",
                exit_code=3)
    if in_fence:
        raise LedgerError(
            "usage", f"{what} has an unclosed ``` code fence",
            fix_hint="close every fence you open", exit_code=3)
    return text


def cmd_add(args) -> int:
    ctx = make_ctx(args, mutating=True)
    tasks, _ = load_all_tasks(ctx)
    existing = {t.id for t in tasks}
    title = _require_title(args.title)
    task = new_task(ctx.prefix, existing, title, args.priority, args.size)

    spec = args.spec
    if spec == "-":
        spec = sys.stdin.read()
    if spec:
        task.set_section("Spec", _check_section_body(spec, "--spec text"))

    deps = []
    for frag in (args.after or []):
        deps.append(load_task_or_die(ctx, frag).id)
    if deps:
        task.header["depends_on"] = ", ".join(dict.fromkeys(deps))
    if args.tag:
        task.header["tags"] = ", ".join(dict.fromkeys(
            _clean_tag(t) for t in args.tag))

    # journal the initial selection: the `created:` prefix stays so old and
    # new corpora read uniformly; the suffixes make the add line the durable
    # record of a wave's selected members and tags
    created = f"created: {task.title} [{task.priority}/{task.size}]"
    if deps:
        created += f" (after: {task.header['depends_on']})"
    if task.header.get("tags"):
        created += f" (tags: {task.header['tags']})"
    task.append_log(ctx.actor, "add", created)
    task.path = task_path(ctx, task.id)
    save_task(task)
    # duplicates are cheapest to catch at filing time, and `add` is the one
    # command an agent cannot skip: warn (never refuse — a refusal makes
    # --force reflexive), persist nothing, never in validate
    similar = similar_tasks(title, tasks)
    warnings = [_similar_task_warning(task.id, old, score)
                for old, score in similar]
    emit(args, True,
         {"id": task.id, "path": str(task.path),
          "similar": [{"id": old.id, "status": old.status, "title": old.title,
                       "score": round(score, 3)} for old, score in similar]},
         errors=warnings, human=[f"added {task.id}: {task.title}"])
    return 0


def cmd_list(args) -> int:
    ctx = make_ctx(args)
    mine = getattr(args, "mine", False)
    if mine and args.unclaimed:
        raise LedgerError("usage", "--mine and --unclaimed are mutually "
                          "exclusive", exit_code=3)
    if mine and ctx.actor == "unknown":
        raise LedgerError("usage", "--mine needs a session identity",
                          exit_code=3,
                          fix_hint="set LEDGER_SESSION or pass --session")
    tasks, problems = load_all_tasks(ctx)
    depends_on = None
    if getattr(args, "depends_on", None):
        depends_on = load_task_or_die(ctx, args.depends_on).id
    rows = []
    for task in sorted(tasks, key=sort_key):
        # no status gate on --mine: a coherence violation stays visible
        if mine and task.header.get("claimed_by") != ctx.actor:
            continue
        if args.status and task.status not in args.status:
            continue
        if args.priority and task.priority not in args.priority:
            continue
        if args.tag and args.tag not in task.tags:
            continue
        if getattr(args, "resource", None) and \
                args.resource not in task.resources:
            continue
        if depends_on and depends_on not in task.depends_on:
            continue
        if args.claimed and not task.header.get("claimed_by"):
            continue
        if args.unclaimed and task.header.get("claimed_by"):
            continue
        rows.append(task)
    briefs = [task_brief(t) for t in rows]
    human = []
    if rows:
        widths = [max(len(str(t.id)) for t in rows),
                  max(len(t.status) for t in rows),
                  max((len(t.header.get("claimed_by", "")) for t in rows),
                      default=0)]
        for t in rows:
            human.append(
                f"{t.id:<{widths[0]}}  {t.status:<{widths[1]}}  {t.priority}  "
                f"{t.size:<2}  {t.header.get('claimed_by', ''):<{widths[2]}}  "
                f"{t.title}")
    else:
        human.append("no tasks match")
    emit(args, True, {"tasks": briefs}, errors=problems, human=human)
    return 0


def cmd_show(args) -> int:
    ctx = make_ctx(args)
    _brief_args_ok(args, digest=getattr(args, "brief", False))
    task = load_task_or_die(ctx, args.id, for_write=False)
    all_tasks, _ = load_all_tasks(ctx)
    if getattr(args, "brief", False):
        trailer_map = {} if args.no_git else trailer_links(ctx)
        data = task_digest(ctx, task, args.last or 10, trailer_map, all_tasks)
        data["absorbed"] = absorbed_by(task, all_tasks)
        emit(args, True, data, human=digest_human(data))
        return 0
    data = task_full(ctx, task, trailer_links(ctx), all_tasks)
    data["absorbed"] = absorbed_by(task, all_tasks)
    human = [serialize_task(task).rstrip("\n"), "",
             f"# last_activity: {data['last_activity']}",
             f"# effective_commits: {', '.join(data['effective_commits']) or '(none)'}",
             f"# dependents: {', '.join(data['dependents']) or '(none)'}"]
    if data["absorbed"]:
        human.append("# absorbed: " + ", ".join(
            f"{a['id']} ({a['kind']})" for a in data["absorbed"]))
    emit(args, True, data, human=human)
    return 0


def cmd_brief(args) -> int:
    ctx = make_ctx(args)  # read-only, lock-free
    task = load_task_or_die(ctx, args.id, for_write=False)
    all_tasks, _ = load_all_tasks(ctx)
    trailer_map = {} if args.no_git else trailer_links(ctx)
    last = 10 if args.last is None else args.last
    data = task_digest(ctx, task, last, trailer_map, all_tasks)
    emit(args, True, data, human=digest_human(data))
    return 0


def cmd_next(args) -> int:
    _brief_args_ok(args, digest=not getattr(args, "full", False))
    ctx = make_ctx(args, mutating=args.claim)
    tasks, problems = load_all_tasks(ctx)
    bad = structural_problem_stems(problems)
    pool = [t for t in tasks
            if t.id not in bad and (t.path is None or t.path.stem not in bad)]
    eligible, why, human_blocked, stale_blocks, resources_held = \
        compute_eligible(pool, ctx.config)
    for stem in sorted(bad):
        why.append({"id": stem, "ineligible_because":
                    "file has structural problems — run ledger validate and "
                    "repair it first"})
    # files that could not even be decoded produce no Task at all; still
    # surface them instead of leaving them silently invisible
    parsed_stems = {t.path.stem for t in tasks if t.path}
    unreadable = {p.get("task") for p in problems
                  if p.get("code") == "encoding" and p.get("task")}
    for stem in sorted(unreadable - parsed_stems - bad):
        why.append({"id": stem, "ineligible_because":
                    "file is not readable as UTF-8 — repair it"})
    stale_days = int(ctx.config.get("stale_claim_days", 7))

    def held_by_me(exclude: str | None) -> list[dict]:
        # advisory view keyed on the resolved actor: what this session
        # already holds, so a multi-claim session can release everything
        # at session end and resume its own work before taking more
        return [{"id": t.id, "title": t.title, "status": t.status,
                 "claimed_at": t.header.get("claimed_at"),
                 "blocked_on": t.header.get("blocked_on"),
                 "stale": claim_is_stale(t, stale_days)}
                for t in sorted(pool, key=sort_key)
                if t.id != exclude and t.header.get("claimed_by") == ctx.actor
                and t.status in ("in_progress", "blocked")]

    def held_lines(held: list[dict]) -> list[str]:
        return [f"  also holding: {h['id']} [{h['status']}"
                + (f", stale" if h["stale"] else "")
                + f"] {h['title']}" for h in held]

    if not eligible:
        held = held_by_me(None)
        emit(args, True, {"task": None, "claimed": False, "why": why,
                          "blocked_on_human": human_blocked,
                          "stale_blocks": stale_blocks, "held": held,
                          "resources_held": resources_held},
             errors=problems,
             human=["nothing eligible"] +
                   [f"  {w['id']}: {w['ineligible_because']}" for w in why]
                   + held_lines(held))
        return 0
    top, flag = eligible[0]
    claimed = False
    if args.claim:
        holder = top.header.get("claimed_by")
        # refreshing one's own stale claim is not a takeover
        takeover = (holder if flag == "stale_claim" and holder != ctx.actor
                    else None)
        apply_claim(top, ctx.actor, takeover)
        save_task(top)
        claimed = True
    held = held_by_me(top.id)
    # the digest is the DEFAULT here: this is the one command every session
    # runs, and the protocol already requires reading the task file, so the
    # full Log would enter context twice. --full restores task_full; the
    # shape depends only on the flag, never on data.
    if getattr(args, "full", False):
        payload = task_full(ctx, top, trailer_links(ctx), tasks)
    else:
        trailer_map = {} if args.no_git else trailer_links(ctx)
        last = 10 if args.last is None else args.last
        payload = task_digest(ctx, top, last, trailer_map, tasks)
    data = {"task": payload,
            "claimed": claimed,
            "stale_takeover": flag == "stale_claim",
            "why": why, "blocked_on_human": human_blocked,
            "stale_blocks": stale_blocks, "held": held,
            "resources_held": resources_held}
    if args.n > 1:
        data["tasks"] = [task_brief(t) for t, _ in eligible[:args.n]]
    verb = "claimed" if claimed else "next"
    emit(args, True, data, errors=problems,
         human=[f"{verb}: {top.id} [{top.priority}/{top.size}] {top.title}"]
               + ([f"  (took over stale claim)"] if flag == "stale_claim" else [])
               + [f"  {top.path}"]
               + [f"  stale block: {s['id']} blocked_on {s['blocked_on']} "
                  f"({s['target_status']}) — ledger unblock {s['id']}"
                  for s in stale_blocks]
               + held_lines(held))
    return 0


def cmd_claim(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    stale_days = int(ctx.config.get("stale_claim_days", 7))
    if task.status in ("done", "dropped"):
        raise LedgerError("bad-state", f"{task.id} is {task.status}",
                          task=task.id, fix_hint="closed tasks cannot be claimed")
    if task.status == "blocked":
        raise LedgerError(
            "bad-state",
            f"{task.id} is blocked on {task.header.get('blocked_on', '?')}",
            task=task.id, fix_hint="ledger unblock <id> first")
    takeover = None
    if task.status == "in_progress":
        holder = task.header.get("claimed_by", "?")
        stale = claim_is_stale(task, stale_days)
        if holder == ctx.actor and not stale and not args.force:
            emit(args, True, {"id": task.id, "already": True},
                 human=[f"{task.id} already claimed by you"])
            return 0
        if holder != ctx.actor and not stale and not args.force:
            raise LedgerError(
                "claim-held",
                f"{task.id} is claimed by {holder} "
                f"(fresh, at {task.header.get('claimed_at', '?')})",
                task=task.id,
                fix_hint="pick another task, or --force to take over")
        # stale (or forced) claim: refresh/takeover through apply_claim so
        # claimed_at advances and the Log records it
        takeover = holder if holder != ctx.actor else None
    all_tasks, _ = load_all_tasks(ctx)
    extra = _resource_guard(task, all_tasks, stale_days, args.force, "claim")
    apply_claim(task, ctx.actor, takeover, extra)
    save_task(task)
    emit(args, True, {"id": task.id, "claimed_by": ctx.actor},
         human=[f"claimed {task.id}: {task.title}" + extra])
    return 0


def _refuse_if_closed(task: Task, verb: str) -> None:
    """Closed is terminal (decision #12): after done/drop only the
    append-only or repair-only verbs (note, link, step check, question
    resolve) are allowed; everything else is a new task."""
    if task.status in ("done", "dropped"):
        raise LedgerError(
            "bad-state", f"{task.id} is {task.status} — closed is terminal, "
            f"{verb} is not allowed after close", task=task.id,
            fix_hint="a regression or redo is a new task (ledger search "
                     "first, then ledger add); note/link/step check/question "
                     "resolve remain allowed on closed tasks")


def _guard_foreign_claim(ctx: Ctx, task: Task, force: bool, verb: str) -> None:
    """Refuse to strip another session's FRESH claim without --force."""
    holder = task.header.get("claimed_by")
    stale_days = int(ctx.config.get("stale_claim_days", 7))
    if (holder and holder != ctx.actor
            and not claim_is_stale(task, stale_days) and not force):
        raise LedgerError(
            "claim-held",
            f"{task.id} is claimed by {holder} (fresh) — {verb} someone "
            "else's active claim needs --force",
            task=task.id, fix_hint="--force if their session is really gone")


def cmd_release(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    if task.status in ("done", "dropped"):
        raise LedgerError("bad-state", f"{task.id} is {task.status}",
                          task=task.id)
    _guard_foreign_claim(ctx, task, args.force, "releasing")
    task.header.pop("claimed_by", None)
    task.header.pop("claimed_at", None)
    if args.blocked:
        if not args.on:
            raise LedgerError("usage", "--blocked requires --on <human|task-id|"
                              "external: note>", exit_code=3)
        task.header["status"] = "blocked"
        task.header["blocked_on"] = normalize_blocked_on(ctx, args.on, task.id)
        # the blocker reaches the Log, not just the header, so the handoff
        # reason survives a later unblock/drop (mirrors block's Log text)
        text = f"blocked on {task.header['blocked_on']}"
        if args.note:
            text += f" — {sanitize_inline(args.note)}"
        human = f"released {task.id} -> blocked on {task.header['blocked_on']}"
    else:
        task.header["status"] = "todo"
        task.header.pop("blocked_on", None)
        text = args.note or "released"
        human = f"released {task.id} -> todo"
    task.append_log(ctx.actor, "release", text)
    save_task(task)
    emit(args, True, {"id": task.id, "status": task.status,
                      "blocked_on": task.header.get("blocked_on")},
         human=[human])
    return 0


def normalize_blocked_on(ctx: Ctx, value: str, self_id: str) -> str:
    value = sanitize_inline(value)
    if value == "human" or value.startswith("external:"):
        return value
    resolved = load_task_or_die(ctx, value).id
    if resolved == self_id:
        raise LedgerError("refs", f"{self_id} cannot be blocked on itself",
                          task=self_id,
                          fix_hint="block --on human, another task id, or "
                                   "'external: <note>'")
    return resolved


def _would_cycle(ctx: Ctx, task_id: str, new_deps: list[str]) -> bool:
    tasks, _ = load_all_tasks(ctx)
    graph = {t.id: t.depends_on for t in tasks}
    graph[task_id] = new_deps
    seen, stack = set(), list(new_deps)
    while stack:
        cur = stack.pop()
        if cur == task_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, []))
    return False


def cmd_set(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    _refuse_if_closed(task, "set")
    changes = []
    if args.title is not None:
        new_title = _require_title(args.title)
        changes.append(("title", task.title, new_title))
        task.header["title"] = new_title
    if args.priority is not None:
        changes.append(("priority", task.priority, args.priority))
        task.header["priority"] = args.priority
    if args.size is not None:
        changes.append(("size", task.size, args.size))
        task.header["size"] = args.size
    deps = task.depends_on
    for frag in (args.add_depends or []):
        dep = load_task_or_die(ctx, frag).id
        if dep == task.id:
            raise LedgerError("refs", f"{task.id} cannot depend on itself",
                              task=task.id)
        if dep not in deps:
            if _would_cycle(ctx, task.id, deps + [dep]):
                raise LedgerError(
                    "refs",
                    f"adding depends_on {dep} would create a dependency cycle",
                    task=task.id,
                    fix_hint="invert or drop one edge of the cycle")
            deps.append(dep)
            changes.append(("depends_on", "+", dep))
    for frag in (args.remove_depends or []):
        dep = load_task_or_die(ctx, frag).id
        if dep in deps:
            deps.remove(dep)
            changes.append(("depends_on", "-", dep))
    if args.add_depends or args.remove_depends:
        task.header["depends_on"] = ", ".join(deps)
        if not deps:
            task.header.pop("depends_on", None)
    tags = task.tags
    for tag in (args.add_tag or []):
        tag = _clean_tag(tag)
        if tag not in tags:
            tags.append(tag)
            changes.append(("tags", "+", tag))
    for tag in (args.remove_tag or []):
        if tag in tags:
            tags.remove(tag)
            changes.append(("tags", "-", tag))
    if args.add_tag or args.remove_tag:
        task.header["tags"] = ", ".join(tags)
        if not tags:
            task.header.pop("tags", None)
    if not changes:
        raise LedgerError("usage", "nothing to change", exit_code=3,
                          fix_hint="pass at least one --title/--priority/--size/"
                                   "--add-depends/--remove-depends/--add-tag/"
                                   "--remove-tag")
    for field, old, new in changes:
        task.append_log(ctx.actor, "set", f"{field} {old} -> {new}")
    save_task(task)
    emit(args, True, {"id": task.id,
                      "changes": [{"field": f, "old": o, "new": n}
                                  for f, o, n in changes]},
         human=[f"set {task.id}: " + "; ".join(f"{f} {o} -> {n}"
                                               for f, o, n in changes)])
    return 0


def cmd_note(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    # note(dead-end) mirrors done(no-code): a flag-generated verb sub-type so
    # views can select negative knowledge; carries no validation semantics
    verb = "note(dead-end)" if getattr(args, "dead_end", False) else "note"
    task.append_log(ctx.actor, verb, args.text)
    save_task(task)
    emit(args, True, {"id": task.id, "verb": verb},
         human=[f"noted on {task.id}" + (" (dead end)" if verb != "note"
                                          else "")])
    return 0


def _resolve_checkbox_line(content: str, selector: str,
                           want_unchecked: bool | None = None
                           ) -> tuple[int, str] | None:
    """Resolve selector (1-based index over checkbox lines, or unique
    substring) to (line_index, line). Returns None if no match; raises
    LedgerError if ambiguous."""
    lines = content.split("\n")
    boxes = [(i, line) for i, line in enumerate(lines) if CHECKBOX_RE.match(line)]
    try:
        n = int(selector)
        if 1 <= n <= len(boxes):
            return boxes[n - 1]
        return None
    except ValueError:
        pass
    pool = boxes
    if want_unchecked is True:
        pool = [(i, l) for i, l in boxes
                if CHECKBOX_RE.match(l).group(1) == " "]
    matches = [(i, l) for i, l in pool if selector.lower() in l.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    raise LedgerError(
        "ambiguous-selector",
        f"'{selector}' matches {len(matches)} items: "
        + "; ".join(l.strip("- ") for _, l in matches[:5]),
        fix_hint="use a longer substring or the 1-based index from show")


def cmd_step(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    content = task.get_section("Next Steps")
    if args.action != "check":  # check repairs a closed task; add/uncheck reopen work
        _refuse_if_closed(task, f"step {args.action}")
    if args.action == "add":
        line = f"- [ ] {sanitize_inline(args.value)}"
        task.set_section("Next Steps", (content + "\n" + line) if content else line)
        task.append_log(ctx.actor, "step", f"added '{sanitize_inline(args.value)}'")
    else:
        hit = _resolve_checkbox_line(content, args.value)
        if hit is None:
            raise LedgerError("no-such-step",
                              f"no step matches '{args.value}' on {task.id}",
                              task=task.id,
                              fix_hint="ledger show <id> lists steps with indexes")
        idx, line = hit
        mark = "x" if args.action == "check" else " "
        m = CHECKBOX_RE.match(line)
        new_line = f"- [{mark}] {m.group(2)}"
        lines = content.split("\n")
        lines[idx] = new_line
        task.set_section("Next Steps", "\n".join(lines))
        task.append_log(ctx.actor, "step", f"{args.action}ed '{m.group(2)}'")
    save_task(task)
    emit(args, True, {"id": task.id, "next_steps": task.steps()},
         human=[f"step {args.action} on {task.id}"])
    return 0


def cmd_question(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    content = task.get_section("Open Questions")
    if args.action == "add":
        _refuse_if_closed(task, "question add")  # resolve repairs; add reopens
        text = sanitize_inline(args.value)
        prefix = "HUMAN: " if args.human else ""
        line = f"- [ ] {prefix}{text}"
        task.set_section("Open Questions",
                         (content + "\n" + line) if content else line)
        task.append_log(ctx.actor, "question",
                        f"added{' (HUMAN)' if args.human else ''}: {text}")
    else:  # resolve
        if not args.answer:
            raise LedgerError("usage", "resolve requires --answer", exit_code=3)
        hit = _resolve_checkbox_line(content, args.value, want_unchecked=True)
        if hit is None:
            raise LedgerError(
                "no-such-question",
                f"no unanswered question matches '{args.value}' on {task.id}",
                task=task.id,
                fix_hint="ledger show <id> lists questions with indexes")
        _answer_question(task, hit[0], args.answer, ctx.actor)
    save_task(task)
    emit(args, True, {"id": task.id, "open_questions": task.questions()},
         human=[f"question {args.action} on {task.id}"])
    return 0


def _answer_question(task: Task, idx: int, answer: str, actor: str) -> str:
    """Rewrite the checkbox at line index idx of Open Questions as answered
    and journal it. Shared by `question resolve` and `answers apply` so the
    two can never drift. Returns the raw checkbox text (incl. HUMAN:)."""
    lines = task.get_section("Open Questions").split("\n")
    m = CHECKBOX_RE.match(lines[idx])
    if m is None or m.group(1) == "x":
        raise LedgerError("bad-state", "that question is already answered",
                          task=task.id)
    date = now_ts()[:10]
    text = sanitize_inline(answer)
    lines[idx] = f"- [x] {m.group(2)} -- ANSWERED ({date}): {text}"
    task.set_section("Open Questions", "\n".join(lines))
    task.append_log(actor, "answer", f"'{m.group(2)}' -> {text}")
    return m.group(2)


def _question_contexts(task: Task) -> list[list[str]]:
    """Per question: the non-empty, non-checkbox, non-heading lines between
    that checkbox and the next (the same line-level parse as
    Task.questions()). Prose before the first checkbox belongs to no row.
    Opportunistic — agents write options/recommendations there; the CLI
    never authors it."""
    out: list[list[str]] = []
    for line in task.get_section("Open Questions").split("\n"):
        if CHECKBOX_RE.match(line):
            out.append([])
        elif out and line.strip() and not line.lstrip().startswith("#"):
            out[-1].append(line.strip())
    return out


def question_key(text: str) -> str:
    """Grouping HINT for consumers (equal keys = candidate duplicates), never
    a selector: `question resolve` addresses by index or raw substring."""
    return re.sub(r"\s+", " ", text.casefold()).strip().rstrip("?.!").strip()


def blocked_reason(task: Task) -> tuple[str, str | None]:
    """The reason behind a human block, from the NEWEST block/release Log
    line only — an older block line is a stale reason after block / unblock
    / release --blocked. The header blocked_on stays the authoritative fact;
    this is the operator-facing why."""
    newest = None
    for e in task.log():
        if e["verb"] in ("block", "release") and (
                newest is None or e["ts"] >= newest["ts"]):
            newest = e
    if newest is None:
        return "", None
    text = newest["text"]
    target = task.header.get("blocked_on", "")
    if newest["verb"] == "block":
        prefix = f"on {target}"
        if not text.startswith(prefix):
            return "", "block"
        rest = text[len(prefix):]
    elif text.startswith("blocked on "):
        prefix = f"blocked on {target}"
        rest = text[len(prefix):] if text.startswith(prefix) else ""
    else:
        return ("" if text == "released" else text), "release"
    return (rest[3:] if rest.startswith(" — ") else rest.strip()), newest["verb"]


def _resolve_fragment(tasks: list, fragment: str) -> Task:
    """load_task_or_die's exact-then-substring rule against an already
    loaded list (no second directory scan)."""
    frag = fragment.strip().lower()
    exact = [t for t in tasks if t.id.lower() == frag]
    matches = exact if len(exact) == 1 else \
        [t for t in tasks if frag in t.id.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LedgerError("no-such-task", f"no task id matches '{fragment}'",
                          fix_hint="ledger list shows all ids")
    raise LedgerError("ambiguous-id", f"'{fragment}' matches multiple tasks: "
                      + ", ".join(t.id for t in matches),
                      fix_hint="use more characters of the id")


def cmd_questions(args) -> int:
    ctx = make_ctx(args)
    tasks, problems = load_all_tasks(ctx)
    scope = None
    if getattr(args, "task", None):
        scope = {_resolve_fragment(tasks, frag).id for frag in args.task}
    out, blocked = [], []
    for task in sorted(tasks, key=sort_key):
        if task.status not in OPEN_STATUSES:
            continue
        if scope is not None and task.id not in scope:
            continue
        meta = {"priority": task.priority, "status": task.status,
                "size": task.size, "claimed_by": task.header.get("claimed_by")}
        contexts = _question_contexts(task)
        for q in task.questions():
            if q["answered"]:
                continue
            if args.human and not q["human"]:
                continue
            out.append({"task": task.id, "title": task.title, "n": q["n"],
                        "human": q["human"], "text": q["text"],
                        "kind": "question", **meta,
                        "context": contexts[q["n"] - 1]
                        if q["n"] - 1 < len(contexts) else [],
                        "key": question_key(q["text"])})
        if task.status == "blocked" and task.header.get("blocked_on") == "human":
            reason, source = blocked_reason(task)
            blocked.append({"id": task.id, "title": task.title, **meta,
                            "reason": reason, "reason_source": source})
    human = []
    for q in out:
        who = f" by {q['claimed_by']}" if q["claimed_by"] else ""
        human.append(f"{q['task']} #{q['n']}{' [HUMAN]' if q['human'] else ''} "
                     f"({q['priority']}, {q['status']}{who}): {q['text']}")
        human.extend(f"    {line}" for line in q["context"])
    for b in blocked:
        who = f" by {b['claimed_by']}" if b["claimed_by"] else ""
        human.append(f"{b['id']} [BLOCKED on human] ({b['priority']}, "
                     f"blocked{who}): {b['reason'] or '(no reason recorded)'}")
    emit(args, True, {"questions": out, "blocked_on_human": blocked},
         errors=problems, human=human or ["no open questions"])
    return 0


def _locate_answer_target(task: Task, row: dict) -> tuple[int, str] | None:
    """Selector rule for `answers apply`: `n` is honoured only when the
    display text at that index equals the row's text; otherwise the text
    is the merge-safe substring address (decision #21); `n` alone behaves
    like `question resolve <n>`."""
    content = task.get_section("Open Questions")
    n, text = row.get("n"), row.get("text")
    if isinstance(n, int) and text is not None:
        qs = task.questions()
        if 1 <= n <= len(qs) and qs[n - 1]["text"] == text:
            return _resolve_checkbox_line(content, str(n))
    if text:
        hit = _resolve_checkbox_line(content, text, want_unchecked=True)
        return hit if hit is not None else _resolve_checkbox_line(content, text)
    if isinstance(n, int):
        return _resolve_checkbox_line(content, str(n))
    return None


def cmd_answers(args) -> int:
    # parse the input BEFORE taking the lock: a malformed file must never
    # hold up other agents
    try:
        raw = (sys.stdin.read() if args.file == "-"
               else Path(args.file).read_text(encoding="utf-8"))
    except OSError as e:
        raise LedgerError("usage", f"cannot read {args.file}: {e}", exit_code=3)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LedgerError("usage", f"answers input is not valid JSON: {e}",
                          exit_code=3,
                          fix_hint="pass the `questions --json` envelope, its "
                                   "data.questions list, or a bare list of "
                                   "{task, n?, text?, answer} rows")
    rows = payload
    if isinstance(payload, dict):
        rows = (payload.get("data", {}).get("questions")
                if isinstance(payload.get("data"), dict)
                else payload.get("questions"))
    if not isinstance(rows, list):
        raise LedgerError("usage", "answers input must be a list of rows",
                          exit_code=3)
    ctx = make_ctx(args, mutating=True)
    tasks, problems = load_all_tasks(ctx)
    by_id = {t.id: t for t in tasks}
    bad_stems = structural_problem_stems(problems)
    plan: dict[str, list] = {}
    targets: set[tuple[str, int]] = set()
    skipped, errors = [], []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not row.get("task"):
            errors.append(err("bad-row", f"row {i} has no task", fix_hint=
                              "rows are {task, n?, text?, answer}"))
            continue
        label = {"task": row["task"], "n": row.get("n"), "text": row.get("text")}
        if row.get("kind") == "block":
            skipped.append({**label, "reason": "block row (unblock by hand)"})
            continue
        if not row.get("answer"):
            skipped.append({**label, "reason": "no answer"})
            continue
        try:
            task = _resolve_fragment(tasks, row["task"])
            if task.id in bad_stems or (task.path and task.path.stem in bad_stems):
                raise LedgerError("corrupt-file", f"{task.id} has structural "
                                  "problems and will not be modified",
                                  task=task.id,
                                  fix_hint="run ledger validate and repair it")
            hit = _locate_answer_target(task, row)
        except LedgerError as e:
            errors.append(e.violation)
            continue
        if hit is None:
            errors.append(err("no-such-question",
                              f"{task.id}: no question matches row {i}",
                              task=task.id,
                              fix_hint="ledger show <id> lists questions"))
            continue
        idx, line = hit
        m = CHECKBOX_RE.match(line)
        if m.group(1) == "x":
            am = ANSWERED_RE.match(m.group(2))
            existing = am.group(3) if am else None
            if existing == sanitize_inline(row["answer"]):
                skipped.append({**label, "task": task.id,
                                "reason": "already-answered"})
            else:
                errors.append(err("bad-state", f"{task.id}: question already "
                                  f"answered differently: {existing!r}",
                                  task=task.id))
            continue
        if (task.id, idx) in targets:
            errors.append(err("duplicate-target", f"{task.id}: two rows "
                              "resolve to the same question", task=task.id))
            continue
        targets.add((task.id, idx))
        plan.setdefault(task.id, []).append((idx, row["answer"]))
    if errors:
        # every row is resolved before any write: a refusal changes no file
        emit(args, False, {"applied": [], "skipped": skipped}, errors=errors)
        return 2
    applied = []
    for tid, items in plan.items():
        task = by_id[tid]
        lines = task.get_section("Open Questions").split("\n")
        for idx, answer in items:
            n = sum(1 for l in lines[:idx + 1] if CHECKBOX_RE.match(l))
            raw_text = _answer_question(task, idx, answer, ctx.actor)
            applied.append({"task": tid, "n": n, "text": raw_text,
                            "answer": sanitize_inline(answer)})
        save_task(task)  # one write per file
    human = [f"applied {len(applied)} answer(s), skipped {len(skipped)}"]
    human += [f"  {a['task']} #{a['n']}: {a['answer']}" for a in applied]
    emit(args, True, {"applied": applied, "skipped": skipped}, human=human)
    return 0


def cmd_block(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    if task.status in ("done", "dropped"):
        raise LedgerError("bad-state", f"{task.id} is {task.status}",
                          task=task.id)
    task.header["status"] = "blocked"
    task.header["blocked_on"] = normalize_blocked_on(ctx, args.on, task.id)
    task.append_log(ctx.actor, "block",
                    f"on {task.header['blocked_on']}"
                    + (f" — {sanitize_inline(args.why)}" if args.why else ""))
    save_task(task)
    emit(args, True, {"id": task.id, "blocked_on": task.header["blocked_on"]},
         human=[f"blocked {task.id} on {task.header['blocked_on']}"])
    return 0


def cmd_unblock(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    if task.status != "blocked":
        raise LedgerError("bad-state", f"{task.id} is not blocked",
                          task=task.id)
    extra = ""
    if task.header.get("claimed_by"):
        # restoring in_progress re-acquires the task's resource leases
        all_tasks, _ = load_all_tasks(ctx)
        stale_days = int(ctx.config.get("stale_claim_days", 7))
        extra = _resource_guard(task, all_tasks, stale_days,
                                getattr(args, "force", False), "unblock")
    task.header.pop("blocked_on", None)
    if task.header.get("claimed_by"):
        task.header["status"] = "in_progress"
    else:
        task.header["status"] = "todo"
    task.append_log(ctx.actor, "unblock", f"-> {task.header['status']}" + extra)
    save_task(task)
    emit(args, True, {"id": task.id, "status": task.status},
         human=[f"unblocked {task.id} -> {task.status}"])
    return 0


def _link_commits(ctx: Ctx, task: Task, refs: list[str]) -> list[dict]:
    repo = ctx.repo
    if repo is None:
        raise LedgerError("no-git", "not inside a git repository",
                          fix_hint="commit linking needs git")
    linked = []
    for ref in refs:
        info = git_resolve_commit(repo, ref)
        if info is None:
            raise LedgerError("no-such-commit",
                              f"'{ref}' does not resolve to a commit",
                              task=task.id)
        if task.append_commit_line(info["sha7"], info["date"], info["subject"]):
            task.append_log(ctx.actor, "link",
                            f"{info['sha7']} {info['subject']}")
            linked.append(info)
    return linked


def cmd_link(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    linked = _link_commits(ctx, task, args.sha)
    save_task(task)
    emit(args, True,
         {"id": task.id, "linked": linked, "commits": task.commits()},
         human=[f"linked {len(linked)} commit(s) to {task.id}"])
    return 0


def _backfill_from_trailers(ctx: Ctx, tasks: list[Task],
                            commits: list[Commit],
                            skip_ids: set[str] | None = None) -> list[dict]:
    # skip_ids holds file STEMS from structural problems; a broken file's
    # header id may differ from its stem, so match on both
    by_id = {t.id: t for t in tasks
             if not skip_ids or (t.id not in skip_ids
                                 and (t.path is None
                                      or t.path.stem not in skip_ids))}
    backfilled = []
    touched = set()
    for c in commits:
        for tid in c.task_ids:
            task = by_id.get(tid)
            if task is None:
                continue
            if task.append_commit_line(c.sha7, c.date, c.subject):
                task.append_log(ctx.actor, "link",
                                f"{c.sha7} (backfilled from trailer)")
                touched.add(tid)
                backfilled.append({"sha": c.sha7, "task": tid})
    for tid in touched:
        save_task(by_id[tid])
    return backfilled


def cmd_scan(args) -> int:
    ctx = make_ctx(args, mutating=args.write)
    repo = ctx.repo
    if repo is None:
        raise LedgerError("no-git", "not inside a git repository")
    tasks, problems = load_all_tasks(ctx)
    known = {t.id for t in tasks}
    commits, error = walk_commits(repo, ctx.config.get("baseline"), args.since)
    if commits is None:
        raise LedgerError("coverage", error or "git walk failed")
    exempt_res = compile_exempt_patterns(ctx.config)
    policy = exempt_policy_globs(ctx.config)
    explicit = explicit_links(tasks)
    id_token_re = id_token_pattern(ctx.prefix)
    linked, exempt, unlinked, dangling, policy_violations = [], [], [], [], []
    for c in commits:
        bucket, bad_ids = classify_commit(c, repo, known, exempt_res, explicit)
        for raw in bad_ids:
            dangling.append({"sha": c.sha7, "id": raw,
                             "hint": _dangling_kind(raw, id_token_re)})
        if bucket == "linked":
            for tid in c.task_ids:
                if tid in known:
                    linked.append({"sha": c.sha7, "task": tid,
                                   "via": "trailer"})
            for tid in explicit_link_tasks(c, explicit):
                if not any(x["sha"] == c.sha7 and x["task"] == tid
                           for x in linked):
                    linked.append({"sha": c.sha7, "task": tid, "via": "link"})
        elif bucket == "exempt":
            exempt.append(c.sha7)
            bad = (exempt_policy_offenders(c, repo, policy, exempt_res)
                   if policy is not None else None)
            if bad:
                policy_violations.append({"sha": c.sha7, "paths": bad})
        else:
            unlinked.append({"sha": c.sha7, "subject": c.subject})
    backfilled = []
    if args.write:
        backfilled = _backfill_from_trailers(
            ctx, tasks, commits, skip_ids=structural_problem_stems(problems))
    # post-merge duplicate check: concurrent branches are exactly where
    # cross-branch duplicates are minted, and scan is the non-gating ritual
    # command that already walks the corpus (a fuzzy score never fails CI)
    open_tasks = sorted((t for t in tasks if t.status in OPEN_STATUSES),
                        key=sort_key)
    tokens = {t.id: title_tokens(t.title) for t in open_tasks}
    similar_pairs = []
    for i, a in enumerate(open_tasks):
        for b in open_tasks[i + 1:]:
            score = title_similarity(tokens[a.id], tokens[b.id], closed=False)
            if score is not None:
                similar_pairs.append({"a": a.id, "b": b.id,
                                      "score": round(score, 3)})
    similar_pairs.sort(key=lambda x: -x["score"])
    data = {"linked": linked, "exempt": exempt, "unlinked": unlinked,
            "dangling": dangling, "backfilled": backfilled,
            "commits_scanned": len(commits),
            "exempt_policy_violations": policy_violations,
            "similar_open_pairs": similar_pairs[:20]}
    human = [f"scanned {len(commits)} commit(s): {len(linked)} linked, "
             f"{len(exempt)} exempt, {len(unlinked)} unlinked, "
             f"{len(dangling)} dangling"]
    for v in policy_violations:
        human.append(f"  exempt-policy {v['sha']}: touches "
                     + ", ".join(v["paths"][:3]))
    for s in similar_pairs[:20]:
        human.append(f"  similar open titles: {s['a']} ~ {s['b']} "
                     f"({s['score']}) — ledger drop <dup> --duplicate-of "
                     "<survivor> if they are the same work")
    for u in unlinked:
        human.append(f"  unlinked {u['sha']}: {u['subject']}")
    for d in dangling:
        human.append(f"  dangling {d['sha']}: trailer names unknown id "
                     f"{d['id']} ({d['hint']})")
    if backfilled:
        human.append(f"  backfilled {len(backfilled)} commit line(s)")
    emit(args, True, data, errors=problems, human=human)
    return 0


def cmd_done(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    if task.status in ("done", "dropped"):
        raise LedgerError("bad-state", f"{task.id} is already {task.status}",
                          task=task.id)
    _guard_foreign_claim(ctx, task, args.force, "closing")
    repo = ctx.repo

    linked_any = False
    if args.commit:
        linked_any = bool(_link_commits(ctx, task, args.commit)) or linked_any
    if repo is not None:
        commits, _error = walk_commits(repo, ctx.config.get("baseline"))
        if commits:
            for c in commits:
                if task.id in c.task_ids:
                    if task.append_commit_line(c.sha7, c.date, c.subject):
                        task.append_log(ctx.actor, "link",
                                        f"{c.sha7} (backfilled from trailer)")
                        linked_any = True
    if linked_any:
        save_task(task)  # keep evidence links even if the close is refused

    refusals = []
    if not task.commits() and not args.no_code:
        refusals.append(err(
            "done-evidence",
            f"{task.id} has no linked commits",
            task=task.id,
            fix_hint="link evidence: ledger done <id> --commit HEAD, or explain "
                     "with --no-code \"reason\" if the task needed no commits"))
    # closed is terminal: done refuses EVERY state strict CI would reject,
    # so a closed task can never be born red. --force never bypasses these
    # (a moot HUMAN question is answered "moot: ..."; a moot step is checked
    # with a `-- MOOT: reason` suffix or deleted).
    open_human = [q for q in task.questions() if q["human"] and not q["answered"]]
    for q in open_human:
        refusals.append(err(
            "done-human-questions",
            f"unanswered HUMAN question: {q['text']}",
            task=task.id,
            fix_hint=f"ledger question {task.id} resolve <n> --answer \"...\" "
                     "once the human answers (\"moot: <why>\" if it no "
                     "longer applies)"))
    open_steps = [s for s in task.steps() if not s["done"]]
    if open_steps:
        refusals.append(err(
            "done-loose-ends",
            f"{len(open_steps)} unchecked next step(s): "
            + "; ".join(f"#{s['n']} {s['text'][:40]}" for s in open_steps[:3]),
            task=task.id,
            fix_hint=f"ledger step {task.id} check <n> (append `-- MOOT: "
                     "reason` to the line if it was overtaken), or delete "
                     "the stale line — Next Steps must reflect reality"))
    open_q = [q for q in task.questions() if not q["answered"] and not q["human"]]
    if open_q:
        refusals.append(err(
            "done-loose-ends",
            f"{len(open_q)} unanswered question(s): "
            + "; ".join(q["text"][:40] for q in open_q[:3]),
            task=task.id,
            fix_hint=f"ledger question {task.id} resolve <n> --answer "
                     "\"...\", or delete the line if it no longer matters"))
    if refusals:
        emit(args, False, {"id": task.id}, errors=refusals)
        return 2

    warnings = []
    if task.depends_on:
        # CLI-time only (never in validate): closing over open prerequisites
        # is the same coherence smell as closing with unchecked steps. A
        # dropped dependency counts as open — one reading of depends_on
        # tool-wide (next and drop treat it as unmet too).
        all_tasks, _ = load_all_tasks(ctx)
        by_id = {t.id: t for t in all_tasks}
        open_deps = [d for d in task.depends_on
                     if d not in by_id or by_id[d].status != "done"]
        if open_deps:
            details = ", ".join(_dep_status_text(d, by_id) for d in open_deps)
            warnings.append(err(
                "done-loose-ends",
                f"{len(open_deps)} depends_on task(s) still open: {details}",
                task=task.id, severity="warning",
                fix_hint="close or drop them first, or ledger set "
                         f"{task.id} --remove-depends <dep> if the "
                         "dependency no longer holds"))

    task.header["status"] = "done"
    task.header["closed"] = now_ts()
    task.header.pop("claimed_by", None)
    task.header.pop("claimed_at", None)
    task.header.pop("blocked_on", None)
    if args.no_code:
        task.append_log(ctx.actor, "done(no-code)", args.no_code)
    else:
        shas = ", ".join(c["sha"] for c in task.commits())
        task.append_log(ctx.actor, "done", f"evidence: {shas}")
    save_task(task)
    all_tasks, _ = load_all_tasks(ctx)
    warnings.extend(blocked_on_closed_warnings(task, all_tasks))
    emit(args, True, {"id": task.id, "commits": task.commits()},
         errors=warnings, human=[f"done: {task.id} {task.title}"])
    return 0


def cmd_drop(args) -> int:
    ctx = make_ctx(args, mutating=True)
    # every refusal below is evaluated BEFORE the first save: a refused drop
    # leaves no file changed
    if args.duplicate_of and args.superseded_by:
        raise LedgerError("usage", "--duplicate-of and --superseded-by are "
                          "mutually exclusive", exit_code=3,
                          fix_hint="a task is either a duplicate of a live "
                                   "task or replaced by a new one")
    why = sanitize_inline(args.why) if args.why else ""
    kind = ("duplicate" if args.duplicate_of
            else "superseded" if args.superseded_by else None)
    if kind is None and not why:
        raise LedgerError("usage", "drop needs --why, --duplicate-of <id> "
                          "or --superseded-by <id>", exit_code=3)
    task = load_task_or_die(ctx, args.id, for_write=True)
    if task.status in ("done", "dropped"):
        raise LedgerError("bad-state", f"{task.id} is already {task.status}",
                          task=task.id)
    _guard_foreign_claim(ctx, task, args.force, "closing")
    if kind is None and CLOSED_RELATION_RE.match(why):
        raise LedgerError(
            "refs", "--why carries the drop-relation grammar "
            f"({why.split(' ')[0]} ...) without the flag", task=task.id,
            fix_hint="use --duplicate-of <id> / --superseded-by <id> so the "
                     "target is resolved and validated")
    target = None
    if kind is not None:
        target = load_task_or_die(ctx, args.duplicate_of or args.superseded_by,
                                  for_write=False)
        if target.id == task.id:
            raise LedgerError("refs", f"{task.id} cannot be a {kind} of "
                              "itself", task=task.id)
        if target.status == "dropped":
            raise LedgerError(
                "bad-state", f"{target.id} is itself dropped", task=task.id,
                fix_hint="point at the live survivor (follow "
                         f"{target.id}'s closed_relation)")
    task.header["status"] = "dropped"
    task.header["closed"] = now_ts()
    task.header.pop("claimed_by", None)
    task.header.pop("claimed_at", None)
    task.header.pop("blocked_on", None)
    if target is not None:
        text = f"{CLOSED_RELATION_TOKEN[kind]} {target.id}"
        if why:
            text += f" — {why}"
    else:
        text = why
    task.append_log(ctx.actor, "drop", text)
    save_task(task)
    all_tasks, _ = load_all_tasks(ctx)
    warnings = []
    for t in all_tasks:
        if task.id not in t.depends_on or t.status not in OPEN_STATUSES:
            continue
        hint = f"ledger set {t.id} --remove-depends {task.id}"
        if target is not None and t.id != target.id:
            hint += f" --add-depends {target.id}"
        warnings.append(err(
            "refs",
            f"{t.id} depends_on {task.id}, which is now dropped — it will "
            "never become eligible", task=t.id, severity="warning",
            fix_hint=hint))
    warnings.extend(blocked_on_closed_warnings(task, all_tasks))
    if target is not None:
        relation = ("duplicate of" if kind == "duplicate" else "superseded by")
        human = f"dropped {task.id} as {relation} {target.id}"
        if why:
            human += f": {why}"
    else:
        human = f"dropped {task.id}: {why}"
    emit(args, True, {"id": task.id, "closed_relation": task.closed_relation()},
         errors=warnings, human=[human])
    return 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _enum_hint(allowed: tuple) -> str:
    # An old vendored copy will never have `doctor`, so the "corpus newer than
    # tool" signal must ride on the one command every CI runs.
    return (f"one of: {', '.join(allowed)}; if this file was written by a "
            "newer ledger.py, update the vendored copy (python "
            "<newer>/ledger.py init from the repo root) instead of editing "
            "the value, and do not run mutating commands from this copy "
            "against this corpus")


def validate_offline(ctx: Ctx) -> list[dict]:
    violations: list[dict] = []
    id_re = ctx.id_pattern()
    seen_ids: dict[str, str] = {}
    tasks: list[Task] = []

    paths = sorted(ctx.tasks_dir.glob("*.md")) if ctx.tasks_dir.is_dir() else []
    for path in paths:
        stem = path.stem
        try:
            raw = path.read_bytes()
        except OSError as e:
            violations.append(err("parse", f"cannot read {path.name}: {e}",
                                  task=stem))
            continue
        if raw.startswith(b"\xef\xbb\xbf"):
            violations.append(err("encoding", f"{path.name} has a UTF-8 BOM",
                                  task=stem,
                                  fix_hint="any ledger CLI write repairs this"))
        if b"\r" in raw:
            violations.append(err("encoding",
                                  f"{path.name} contains CR bytes (must be LF-only)",
                                  task=stem,
                                  fix_hint="any ledger CLI write repairs this"))
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            violations.append(err("encoding",
                                  f"{path.name} is not valid UTF-8: {e}",
                                  task=stem))
            continue

        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if CONFLICT_RE.match(line):
                violations.append(err(
                    "conflict-markers",
                    f"{path.name} contains an unresolved merge conflict marker: "
                    f"{line[:30]!r}",
                    task=stem,
                    fix_hint="resolve the merge; for Log sections keep both "
                             "sides' lines"))
                break

        task, problems = parse_task(text)
        for p in problems:
            p["task"] = p.get("task") or stem
        violations.extend(problems)
        if task is None:
            continue
        task.path = path
        tasks.append(task)

        tid = task.id
        if tid != stem or not id_re.match(tid):
            violations.append(err(
                "id-filename",
                f"{path.name}: header id '{tid}' must equal the filename stem "
                f"and match {ctx.prefix}-[a-z0-9]{{6}}",
                task=stem,
                fix_hint="rename the file to <id>.md or fix the id line"))
        if tid in seen_ids:
            violations.append(err(
                "id-unique",
                f"id '{tid}' appears in both {seen_ids[tid]} and {path.name}",
                task=tid,
                fix_hint="give the younger file a fresh id from ledger add and "
                         "update depends_on references"))
        else:
            seen_ids[tid] = path.name

        for key in task.header:
            if key not in HEADER_ORDER:
                violations.append(err("unknown-key",
                                      f"unknown header key '{key}'",
                                      task=tid, severity="warning",
                                      fix_hint="probably a typo; known keys: "
                                               + ", ".join(HEADER_ORDER)))

        status = task.status
        if status not in STATUSES:
            violations.append(err("enums", f"invalid status '{status}'",
                                  task=tid,
                                  fix_hint=_enum_hint(STATUSES)))
        if task.priority not in PRIORITIES:
            violations.append(err("enums", f"invalid priority '{task.priority}'",
                                  task=tid,
                                  fix_hint=_enum_hint(PRIORITIES)))
        if task.size not in SIZES:
            violations.append(err("enums", f"invalid size '{task.size}'",
                                  task=tid,
                                  fix_hint=_enum_hint(SIZES)))
        for key in ("created", "closed", "claimed_at"):
            val = task.header.get(key)
            if val is not None and not TS_RE.match(val):
                violations.append(err(
                    "enums", f"{key} '{val}' is not UTC ISO-8601 Z "
                    "(YYYY-MM-DDTHH:MM:SSZ)", task=tid))
        created, closed = task.header.get("created"), task.header.get("closed")
        if (created and closed and TS_RE.match(created) and TS_RE.match(closed)
                and closed < created):
            violations.append(err("enums", f"closed {closed} predates created "
                                  f"{created}", task=tid))

    # cross-file checks
    all_ids = {t.id for t in tasks}
    by_id = {t.id: t for t in tasks}
    for task in tasks:
        for dep in task.depends_on:
            if dep not in all_ids:
                violations.append(err(
                    "refs", f"depends_on references unknown task '{dep}'",
                    task=task.id,
                    fix_hint="remove it: ledger set <id> --remove-depends "
                             + dep))
        blocked_on = task.header.get("blocked_on")
        if blocked_on is not None:
            if blocked_on != "human" and not blocked_on.startswith("external:"):
                if not ctx.id_pattern().match(blocked_on):
                    violations.append(err(
                        "refs",
                        f"blocked_on '{blocked_on}' is not 'human', "
                        "'external: <note>', or a task id", task=task.id))
                elif blocked_on == task.id:
                    violations.append(err(
                        "refs", "task is blocked_on itself — it can never "
                        "become eligible", task=task.id,
                        fix_hint="ledger unblock <id>, then block --on the "
                                 "real reason"))
                elif blocked_on not in all_ids:
                    violations.append(err(
                        "refs",
                        f"blocked_on references unknown task '{blocked_on}'",
                        task=task.id))

    # dependency cycles
    color: dict[str, int] = {}

    def dfs(tid: str, stack: list[str]) -> list[str] | None:
        color[tid] = 1
        for dep in by_id[tid].depends_on if tid in by_id else []:
            if dep not in by_id:
                continue
            if color.get(dep, 0) == 1:
                return stack + [tid, dep]
            if color.get(dep, 0) == 0:
                cycle = dfs(dep, stack + [tid])
                if cycle:
                    return cycle
        color[tid] = 2
        return None

    for task in tasks:
        if color.get(task.id, 0) == 0:
            cycle = dfs(task.id, [])
            if cycle:
                violations.append(err(
                    "refs", "depends_on cycle: " + " -> ".join(cycle),
                    task=cycle[0],
                    fix_hint="break the cycle with ledger set --remove-depends"))
                break

    # per-task state coherence + evidence
    stale_days = int(ctx.config.get("stale_claim_days", 7))
    for task in tasks:
        tid, status = task.id, task.status
        claimed_by = task.header.get("claimed_by")
        claimed_at = task.header.get("claimed_at")
        if (claimed_by is None) != (claimed_at is None):
            violations.append(err(
                "state-coherence",
                "claimed_by and claimed_at must appear together", task=tid))
        if status == "in_progress" and not claimed_by:
            violations.append(err(
                "state-coherence", "in_progress task has no claimed_by/claimed_at",
                task=tid, fix_hint="ledger claim <id>, or ledger release <id>"))
        if status not in ("in_progress", "blocked") and claimed_by:
            violations.append(err(
                "state-coherence", f"{status} task carries claim fields",
                task=tid))
        if status == "blocked" and not task.header.get("blocked_on"):
            violations.append(err("state-coherence",
                                  "blocked task has no blocked_on", task=tid,
                                  fix_hint="ledger block <id> --on <reason>"))
        if status != "blocked" and task.header.get("blocked_on"):
            violations.append(err("state-coherence",
                                  f"{status} task carries blocked_on", task=tid))
        if status in ("done", "dropped"):
            if not task.header.get("closed"):
                violations.append(err("state-coherence",
                                      f"{status} task has no closed timestamp",
                                      task=tid))
            closing_verbs = {"done", "done(no-code)", "drop"}
            if not any(e["verb"] in closing_verbs for e in task.log()):
                violations.append(err(
                    "state-coherence",
                    f"{status} task has no closing Log line", task=tid,
                    fix_hint="close tasks only via ledger done / ledger drop"))
        if status not in ("done", "dropped") and task.header.get("closed"):
            violations.append(err("state-coherence",
                                  f"{status} task carries a closed timestamp",
                                  task=tid))
        if status == "done":
            has_commits = bool(task.commits())
            has_nocode = any(e["verb"] == "done(no-code)" for e in task.log())
            if not has_commits and not has_nocode:
                violations.append(err(
                    "done-evidence",
                    "done task has neither linked commits nor a "
                    "done(no-code) reason", task=tid,
                    fix_hint="ledger link <id> <sha>, or reopen and close "
                             "properly with ledger done"))
            unanswered_human = [q for q in task.questions()
                                if q["human"] and not q["answered"]]
            if unanswered_human:
                violations.append(err(
                    "done-human-questions",
                    f"done task has {len(unanswered_human)} unanswered HUMAN "
                    "question(s)", task=tid,
                    fix_hint="resolve them or reopen the discussion"))
            if any(not s["done"] for s in task.steps()) or \
               any(not q["answered"] and not q["human"] for q in task.questions()):
                violations.append(err(
                    "done-loose-ends",
                    "done task has unchecked steps or unanswered questions",
                    task=tid, severity="warning"))
        # a blocked task that RETAINED its claim (block keeps claimed_by)
        # ages exactly like an in_progress one: a vanished worker must not
        # hold a claim forever behind a block
        if status in ("in_progress", "blocked") and claimed_at:
            if claim_is_stale(task, stale_days):
                violations.append(err(
                    "stale-claim",
                    f"claim by {claimed_by} has been inactive more than "
                    f"{stale_days} day(s)", task=tid, severity="warning",
                    fix_hint="ledger release <id>, or ledger claim <id> --force "
                             "to take over"))
        # stranded handoff: a `release --blocked --on "external: ready ..."`
        # task carries no claim, so only its Log activity can age it. Scoped
        # to the `external: ready` prefix so deliberately parked blocks
        # (`external: wave open`) are never caught; a `note` refreshes it.
        blocked_on = task.header.get("blocked_on") or ""
        if (status == "blocked" and blocked_on.startswith("external: ready")
                and claim_is_stale(task, stale_days)):
            violations.append(err(
                "stale-block",
                f"handoff '{blocked_on}' has seen no Log activity for more "
                f"than {stale_days} day(s) — nobody picked it up",
                task=tid, severity="warning",
                fix_hint="integrator: ledger done <id> --commit <sha> or "
                         "ledger release <id> --note \"...\" to send it "
                         "back; still waiting on purpose: ledger note <id>"))
        if status in ("todo", "in_progress") and task.size == "xl":
            violations.append(err(
                "xl-open", "open task is size xl — split it", task=tid,
                severity="warning",
                fix_hint="ledger add the parts, then ledger set <id> "
                         "--add-depends <parts>; or drop this and re-add smaller"))
        # near-miss checkbox lines silently escape the steps/questions
        # machinery — and with it the HUMAN-question done gate
        for section_name in ("Next Steps", "Open Questions"):
            for line in task.get_section(section_name).split("\n"):
                if LOOSE_BOX_RE.match(line) and not CHECKBOX_RE.match(line):
                    violations.append(err(
                        "checkbox-grammar",
                        f"{section_name} line is not exact checkbox grammar "
                        f"and is invisible to the CLI: {line.strip()[:50]!r}",
                        task=tid, severity="warning",
                        fix_hint="use exactly '- [ ] text' / '- [x] text' "
                                 "(single spaces, lowercase x)"))

    # resource-contention (info, never promoted): two FRESH in_progress
    # claims lease the same resource — reachable via claim/unblock --force,
    # a cross-branch merge, a hand edit, or an older copy without the gate.
    # A header-derived hygiene signal in the stale-claim family, not an
    # enforced guarantee: the tool cannot verify a resource is in use.
    holders: dict[str, list[Task]] = {}
    for task in tasks:
        if task.status == "in_progress" and not claim_is_stale(task, stale_days):
            for r in task.resources:
                holders.setdefault(r, []).append(task)
    for r, ts in sorted(holders.items()):
        if len(ts) > 1:
            names = ", ".join(
                f"{t.id} ({t.header.get('claimed_by', '?')})"
                for t in sorted(ts, key=sort_key))
            violations.append(err(
                "resource-contention",
                f"resource {r} is leased by {len(ts)} fresh claims: {names}",
                severity="info",
                fix_hint="serialize the work: release one holder, or "
                         "release --blocked --on 'external: waiting for "
                         f"resource {r}'"))
    return violations


def _tamper_violations(patch: str, where: str, violations: list[dict]) -> None:
    """Collect log-tamper violations from one unified diff."""
    removed: dict[str, list[str]] = {}
    added: dict[str, set[str]] = {}
    deleted_files: list[str] = []
    current_new: str | None = None
    current_old: str | None = None
    for line in patch.split("\n"):
        if line.startswith("diff --git"):
            current_new = current_old = None
        elif line.startswith("--- a/"):
            current_old = line[6:]
        elif line.startswith("--- "):
            current_old = None  # /dev/null: file created in this diff
        elif line.startswith("+++ b/"):
            current_new = line[6:]
        elif line.startswith("+++ "):
            current_new = None  # /dev/null: file deleted in this diff
            if current_old and current_old.endswith(".md"):
                deleted_files.append(current_old)
        elif line.startswith("-") and not line.startswith("---"):
            content = line[1:]
            if LOG_LINE_RE.match(content):
                target = current_new or current_old
                if target:
                    removed.setdefault(target, []).append(content)
        elif line.startswith("+") and current_new:
            added.setdefault(current_new, set()).add(line[1:])
    deleted_set = set(deleted_files)
    for fname in deleted_files:
        violations.append(err(
            "log-tamper", f"task file {Path(fname).name} deleted {where}",
            task=Path(fname).stem, severity="warning",
            fix_hint="task files are never deleted (use ledger drop); "
                     "restore it from git history"))
    for fname, lines in removed.items():
        if fname in deleted_set:
            continue  # already reported as a whole-file deletion
        gone = [x for x in lines if x not in added.get(fname, set())]
        if gone:
            violations.append(err(
                "log-tamper",
                f"{Path(fname).name}: {len(gone)} Log line(s) deleted {where}",
                task=Path(fname).stem, severity="warning",
                fix_hint="Log is append-only; restore the lines from git "
                         "history"))


def id_token_pattern(prefix: str) -> re.Pattern:
    """Unanchored id matcher for prose / trailer text (ctx.id_pattern() is
    ^$-anchored and unusable there). Tokens found this way are NEVER used
    for linkage — one canonical trailer syntax (decision #10)."""
    return re.compile(rf"{re.escape(prefix)}-[a-z0-9]{{6}}(?![a-z0-9])")


PUSHED_LINK_GUIDANCE = (
    "if pushed, `ledger link <id> {sha7}` — an explicit, sha-verified link "
    "counts as coverage")


def coverage_fix_hint(sha7: str) -> str:
    """Ordered remedies: trailer first, link if pushed, add a task if none
    owns the work, exempt last and only for non-product commits."""
    return (
        "1) unpushed: add `Ledger-Task: <id>` to the message's LAST paragraph "
        "(git commit --amend / rebase; a blank line before Co-Authored-By "
        "puts it out of scope); 2) " + PUSHED_LINK_GUIDANCE.format(sha7=sha7)
        + "; 3) no task owns this work: `ledger add` one first, then link; "
        "`Ledger-Exempt: <reason>` is only for commits with no product-work "
        "obligation (merge/revert mechanics, ledger bookkeeping, generated "
        "artifacts, docs, CI metadata) — never for code without a task")


def _dangling_kind(raw: str, id_token_re: re.Pattern) -> str:
    tokens = id_token_re.findall(raw)
    if len(tokens) >= 2:
        return "multi-id-line"
    if len(tokens) == 1 and raw.strip() != tokens[0]:
        return "extra-text"
    return "unknown-id"  # well-formed but unknown, or not id-shaped at all


def _dangling_diagnostic(c: Commit, raw: str,
                         id_token_re: re.Pattern) -> tuple[str, str]:
    kind = _dangling_kind(raw, id_token_re)
    pushed = PUSHED_LINK_GUIDANCE.format(sha7=c.sha7) + \
        " and supersedes the dangling id"
    if kind == "multi-id-line":
        return (f"commit {c.sha7} trailer names several task ids on one "
                f"line: '{raw}'",
                "one 'Ledger-Task: <id>' line per task — rewrite the message "
                "if unpushed; " + pushed)
    if kind == "extra-text":
        tok = id_token_re.findall(raw)[0]
        return (f"commit {c.sha7} trailer carries extra text after the id: "
                f"'{raw}'",
                f"the line must be exactly 'Ledger-Task: {tok}' — rewrite "
                "the message if unpushed; " + pushed)
    return (f"commit {c.sha7} trailer names unknown task id '{raw}'",
            "fix the id in the message if unpushed (git commit --amend / "
            "rebase); " + pushed + " (if the task file was deleted, restore "
            "it from git history instead — log-tamper names it)")


def validate_git(ctx: Ctx, coverage: bool) -> list[dict]:
    violations: list[dict] = []
    repo = ctx.repo
    if repo is None:
        if coverage:
            violations.append(err(
                "coverage", "not a git repository — coverage cannot be checked",
                fix_hint="run inside the repo, or pass --no-git for exported "
                         "trees"))
        return violations
    if git_head(repo) is None:
        return violations  # empty repo: nothing to check yet

    tasks, _ = load_all_tasks(ctx)
    known = {t.id for t in tasks}
    by_id = {t.id: t for t in tasks}

    if coverage and git_is_shallow(repo):
        violations.append(err(
            "coverage",
            "shallow clone — coverage would pass vacuously, refusing",
            fix_hint="fetch full history (fetch-depth: 0 in CI)"))
        return violations

    # sha-unreachable: commit-cache lines that no longer resolve
    # (independent of the history walk, so it runs even if the walk fails)
    for task in tasks:
        for c in task.commits():
            if not git_sha_exists(repo, c["sha"]):
                violations.append(err(
                    "sha-unreachable",
                    f"commit {c['sha']} in ## Commits does not resolve locally",
                    task=task.id, severity="warning",
                    fix_hint="normal after rebase/shallow clone; "
                             "ledger scan --write re-materializes live links"))

    commits, walk_error = walk_commits(repo, ctx.config.get("baseline"))
    if commits is None:
        if coverage:
            violations.append(err("coverage",
                                  walk_error or "git walk failed"))
        # without --coverage an unreachable baseline is not an error;
        # the walk-dependent warnings are simply skipped
        return violations

    # linked-never-claimed: trailer points at a task that has NO claim
    # evidence at all. Current status "todo" is not enough — the protocol's
    # own claim -> commit -> release handoff legitimately ends in todo.
    # Flags OPEN tasks only: a closed task cannot be claimed retroactively,
    # so flagging it would be a permanent, unrepairable strict-CI failure;
    # its closing Log line already records engagement.
    flagged_never_claimed = set()
    for c in commits:
        for tid in c.task_ids:
            t = by_id.get(tid)
            if (t is not None and tid not in flagged_never_claimed
                    and t.status in ("todo", "blocked")
                    and not any(e["verb"] == "claim" for e in t.log())):
                flagged_never_claimed.add(tid)
                violations.append(err(
                    "linked-never-claimed",
                    f"commit {c.sha7} claims {tid}, which was never claimed",
                    task=tid, severity="warning",
                    fix_hint="claim tasks before committing against them"))

    if not coverage:
        return violations

    exempt_res = compile_exempt_patterns(ctx.config)
    policy = exempt_policy_globs(ctx.config)
    explicit = explicit_links(tasks)
    id_token_re = id_token_pattern(ctx.prefix)
    exempt_count = 0
    for c in commits:
        bucket, dangling = classify_commit(c, repo, known, exempt_res, explicit)
        # an explicit link is the corrected claim: the typo'd id stays in the
        # immutable message, so flagging it would be unrepairable
        if dangling and not explicit_link_tasks(c, explicit):
            for raw in dangling:
                msg, hint = _dangling_diagnostic(c, raw, id_token_re)
                violations.append(err("trailer-dangling", msg, fix_hint=hint))
        if bucket == "exempt":
            exempt_count += 1
            # the commit stays exempt (so exempt-ratio is unchanged and
            # coverage never fires alongside): the abuse gets its own code
            bad = (exempt_policy_offenders(c, repo, policy, exempt_res)
                   if policy is not None else None)
            if bad:
                violations.append(err(
                    "exempt-policy",
                    f"commit {c.sha7} ('{c.subject}') is exempt but touches "
                    f"{len(bad)} path(s) outside exempt_allowed_paths: "
                    + ", ".join(bad[:3]),
                    fix_hint=EXEMPT_POLICY_HINT))
        elif bucket == "unlinked":
            violations.append(err(
                "coverage",
                f"commit {c.sha7} ('{c.subject}') has no Ledger-Task/"
                "Ledger-Exempt trailer",
                fix_hint=coverage_fix_hint(c.sha7)))
    if commits:
        violations.append(err(
            "exempt-ratio",
            f"{exempt_count}/{len(commits)} commit(s) in scope are exempt",
            severity="info"))

    # ---- log-tamper: append-only Log, verified HISTORICALLY ---------------
    # A net baseline->now diff cannot see a Log line that was added after
    # baseline and deleted later (it nets out). Instead:
    #   (1) HEAD -> working tree: uncommitted tampering, caught BEFORE the
    #       session's final commit (line deletions AND file deletions);
    #   (2) every commit in scope, parent -> commit (one `git log -p` pass):
    #       once a Log event enters repository history, no later state may
    #       remove or alter it;
    #   (3) merge commits diffed against EACH parent (`log -p` omits merge
    #       diffs): any parent's Log line missing from the merge result was
    #       dropped by the resolution — the keep-both-sides rule makes this
    #       exact.
    # The -c overrides pin the output format against user git config
    # (diff.noprefix, diff.mnemonicPrefix, diff.external, core.quotePath).
    try:
        tasks_rel = ctx.tasks_dir.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return violations  # ledger dir outside the repo: skip log-tamper
    diff_cfg = ["-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
                "-c", "core.quotePath=false"]
    rc, out = run_git([*diff_cfg, "diff", "--no-ext-diff", "--no-renames",
                       "HEAD", "--", tasks_rel], repo)
    if rc == 0 and out:
        _tamper_violations(out, "(uncommitted)", violations)
    baseline = ctx.config.get("baseline")
    range_spec = f"{baseline}..HEAD" if baseline else "HEAD"
    rc, out = run_git([*diff_cfg, "log", "--no-show-signature", "--no-renames",
                       "--format=%x01%H", "-p", range_spec, "--", tasks_rel],
                      repo)
    if rc == 0 and out:
        for record in out.split("\x01"):
            if not record.strip():
                continue
            sha, _, patch = record.partition("\n")
            _tamper_violations(patch, f"in commit {sha.strip()[:7]}",
                               violations)
    for c in commits:
        if len(c.parents) > 1:
            for parent in c.parents:
                rc, out = run_git([*diff_cfg, "diff", "--no-ext-diff",
                                   "--no-renames", parent, c.sha, "--",
                                   tasks_rel], repo)
                if rc == 0 and out:
                    _tamper_violations(
                        out, f"in merge {c.sha7} (vs parent {parent[:7]})",
                        violations)
    return violations


def cmd_validate(args) -> int:
    ctx = make_ctx(args)
    violations = validate_offline(ctx)
    if not args.no_git:
        violations.extend(validate_git(ctx, coverage=args.coverage))
    if args.strict:
        for v in violations:
            if v["severity"] == "warning":
                v["severity"] = "error"
    errors = [v for v in violations if v["severity"] == "error"]
    warnings = [v for v in violations if v["severity"] != "error"]
    ok = not errors
    summary = (f"validate: {len(errors)} error(s), {len(warnings)} "
               f"warning/info — {'OK' if ok else 'FAIL'}")
    emit(args, ok, {"error_count": len(errors), "warning_count": len(warnings),
                    "checked_coverage": args.coverage and not args.no_git},
         errors=violations, human=[summary])
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# search: ranked text retrieval across task files (read-only, no index)
# ---------------------------------------------------------------------------

SEARCH_FIELDS = ("title", "id", "tags", "spec", "steps", "questions",
                 "commits", "log")
# code constants, not config keys, never stored (this is not the stored
# rank cut by decision #16)
SEARCH_WEIGHTS = {"title": 8, "id": 6, "tags": 6, "spec": 4, "steps": 3,
                  "questions": 3, "commits": 2, "log": 1}
SNIPPET_WIDTH = 160


def _search_texts(task: Task) -> dict[str, str]:
    """Fields over RAW section text so nothing in a task file is
    unreachable (the structured views drop prose, HUMAN: markers, verbs)."""
    return {"id": task.id, "title": task.title, "tags": ", ".join(task.tags),
            "spec": task.get_section("Spec"),
            "steps": task.get_section("Next Steps"),
            "questions": task.get_section("Open Questions"),
            "commits": task.get_section("Commits"),
            "log": task.get_section("Log")}


def _snippet(text: str, pattern: re.Pattern) -> str | None:
    for line in text.split("\n"):
        if not pattern.search(line):
            continue
        line = re.sub(r"\s+", " ", line).strip()
        m = pattern.search(line)
        centre = m.start() if m else 0
        start = max(0, centre - SNIPPET_WIDTH // 2)
        end = start + SNIPPET_WIDTH
        out = line[start:end]
        if start > 0:
            out = "…" + out[1:]
        if end < len(line):
            out = out[:-1] + "…"
        return out
    return None


def cmd_search(args) -> int:
    ctx = make_ctx(args)  # read-only: no mutation lock
    fields = list(SEARCH_FIELDS)
    if args.in_fields:
        fields = [f.strip() for f in args.in_fields.split(",") if f.strip()]
        unknown = [f for f in fields if f not in SEARCH_FIELDS]
        if unknown or not fields:
            raise LedgerError(
                "usage", f"unknown --in field(s): {', '.join(unknown) or '(none)'}",
                exit_code=3, fix_hint="fields: " + ", ".join(SEARCH_FIELDS))
    patterns = []
    for term in args.terms:
        try:
            patterns.append(re.compile(term if args.regex else re.escape(term),
                                       re.I))
        except re.error as e:
            raise LedgerError("usage", f"invalid regex {term!r}: {e}",
                              exit_code=3,
                              fix_hint="fix the pattern, or drop --regex for "
                                       "a literal substring match")
    tasks, problems = load_all_tasks(ctx)
    rows = []
    for task in tasks:
        if args.open and task.status not in OPEN_STATUSES:
            continue
        if args.status and task.status not in args.status:
            continue
        texts = _search_texts(task)
        score, hits, matched, snippets = 0, 0, set(), {}
        for pat in patterns:
            best = None
            for field in fields:
                if pat.search(texts[field]):
                    matched.add(field)
                    snippets.setdefault(field, _snippet(texts[field], pat))
                    weight = SEARCH_WEIGHTS[field]
                    best = weight if best is None else max(best, weight)
            if best is not None:
                hits += 1
                score += best
        if not (hits > 0 if args.any else hits == len(patterns)):
            continue
        if task.status in OPEN_STATUSES:
            score += 1
        rows.append((score, task,
                     sorted(matched, key=lambda f: -SEARCH_WEIGHTS[f]),
                     snippets))
    rows.sort(key=lambda r: (-r[0], sort_key(r[1])))
    count = len(rows)
    rows = rows[:max(args.n, 0)]
    out = []
    human = []
    for score, task, matched, snippets in rows:
        out.append({**task_brief(task), "score": score, "matched_in": matched,
                    "snippets": snippets})
        human.append(f"{task.id}  {task.status}  {task.priority}  "
                     f"{task.size:<2}  {task.title}  [{','.join(matched)}]")
        for field in matched:
            if snippets.get(field):
                human.append(f"    {field}: {snippets[field]}")
    if not rows:
        human.append(f"no task matches ({count} hit(s))")
    data = {"query": {"terms": list(args.terms),
                      "mode": "any" if args.any else "all",
                      "regex": bool(args.regex), "fields": fields},
            "count": count, "tasks": out}
    emit(args, True, data, errors=problems, human=human)
    return 0


# ---------------------------------------------------------------------------
# report: derived, never-stored wave / backlog metrics (operator diagnostics)
#
# Every figure is recomputed from headers, Log lines and the trailer walk on
# each call — nothing is stored, so nothing rots (DESIGN §11's first
# objection). Log-derived figures inherit §3's honest-agent trust level and
# are labeled in `sources`; only the `commits` block comes from git history.
# Never feeds next / done / validate; kept out of PROTOCOL_TEXT so the
# metric stays off the agent's lazy path (core bet 1).
# ---------------------------------------------------------------------------

SET_LINE_RE = re.compile(r"^(\w+) (.+?) -> (.+)$")  # cmd_set's `{field} {old} -> {new}`


def _window_bound(ctx: Ctx, value: str | None, use_git: bool) -> str | None:
    """A UTC Z stamp from `YYYY-MM-DD`, a Z timestamp, or (with git) a ref
    resolved to its committer time."""
    if not value:
        return None
    if TS_RE.match(value):
        return value
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value + "T00:00:00Z"
    if use_git and ctx.repo is not None:
        rc, out = run_git(["show", "-s", "--format=%cI", value + "^{commit}"],
                          ctx.repo)
        if rc == 0 and out:
            stamp = iso_to_utc_z(out.splitlines()[0])
            if stamp:
                return stamp
    raise LedgerError("usage", f"cannot interpret '{value}' as a timestamp "
                      "or git ref", exit_code=3,
                      fix_hint="use YYYY-MM-DD, YYYY-MM-DDTHH:MM:SSZ, or a "
                               "git ref (needs a repo and no --no-git)")


def _hours(a: str, b: str) -> float | None:
    da, db = parse_ts(a), parse_ts(b)
    if da is None or db is None:
        return None
    return round((db - da).total_seconds() / 3600, 1)


def _stats(values: list[float]) -> dict:
    import statistics
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0, "median": None, "p90": None, "max": None}
    return {"n": len(vals), "median": round(statistics.median(vals), 1),
            "p90": vals[int(0.9 * (len(vals) - 1))], "max": vals[-1]}


def _priority_at_creation(task: Task) -> str:
    """Replay the oldest `set: priority X -> Y` line: X was the value before
    the first change, i.e. the priority at creation."""
    sets = sorted((e for e in task.log() if e["verb"] == "set"),
                  key=lambda e: e["ts"])
    for e in sets:
        m = SET_LINE_RE.match(e["text"])
        if m and m.group(1) == "priority":
            return m.group(2)
    return task.priority


def cmd_report(args) -> int:
    ctx = make_ctx(args)  # read-only, lock-free
    use_git = not args.no_git and ctx.repo is not None
    since = _window_bound(ctx, args.since, use_git)
    until = _window_bound(ctx, args.until, use_git)
    tasks, problems = load_all_tasks(ctx)
    by_id = {t.id: t for t in tasks}

    def in_window(ts: str | None) -> bool:
        return bool(ts) and (since is None or ts >= since) and \
            (until is None or ts <= until)

    # ---- population ---------------------------------------------------
    population = list(tasks)
    scope: dict = {}
    if args.tag:
        population = [t for t in tasks if args.tag in t.tags]
        scope["tag"] = args.tag
    parent = None
    if args.task:
        parent = _resolve_fragment(tasks, args.task)
        members = list(parent.depends_on)
        for e in parent.log():  # members removed later are still members
            m = SET_LINE_RE.match(e["text"]) if e["verb"] == "set" else None
            if m and m.group(1) == "depends_on" and m.group(2) == "-":
                members.append(m.group(3).strip())
        wanted = [parent.id] + list(dict.fromkeys(members))
        population = [by_id[i] for i in wanted if i in by_id]
        scope["task"] = parent.id
        scope["members_missing"] = [i for i in wanted if i not in by_id]
    if args.actor:
        scope["actor"] = args.actor

    def events(task: Task) -> list[dict]:
        return [e for e in task.log() if in_window(e["ts"])
                and (not args.actor or e["actor"] == args.actor)]

    # ---- work -----------------------------------------------------------
    def by_prio() -> dict:
        return {p: 0 for p in PRIORITIES}
    work = {"opened": by_prio(), "closed_done": by_prio(),
            "closed_dropped": by_prio()}
    dropped_dups, prose_dups = 0, 0
    for t in population:
        if in_window(t.header.get("created")):
            work["opened"][_priority_at_creation(t)] = \
                work["opened"].get(_priority_at_creation(t), 0) + 1
        if t.status in ("done", "dropped") and in_window(t.header.get("closed")):
            key = "closed_done" if t.status == "done" else "closed_dropped"
            work[key][t.priority] = work[key].get(t.priority, 0) + 1
            if t.status == "dropped":
                rel = t.closed_relation()
                if rel and rel["kind"] == "duplicate":
                    dropped_dups += 1
                elif rel is None and any(
                        e["verb"] == "drop" and "duplicate" in e["text"].lower()
                        for e in t.log()):
                    prose_dups += 1
    opened = sum(work["opened"].values())
    closed_done = sum(work["closed_done"].values())
    ratios = {"reproduction": round(opened / closed_done, 2) if closed_done else None,
              "duplicate_rate": round(dropped_dups / opened, 2) if opened else None}

    # ---- Log-derived counters --------------------------------------------
    blockers = {"new": 0, "cleared": 0}
    questions = {"human_created": 0, "answered": 0, "human_open_end": 0}
    dependencies = {"added": 0, "removed": 0}
    priority = {"raised": 0, "lowered": 0}
    by_actor: dict[str, dict] = {}
    workers: set[str] = set()
    for t in population:
        if t.status in OPEN_STATUSES:
            questions["human_open_end"] += sum(
                1 for q in t.questions() if q["human"] and not q["answered"])
        for e in events(t):
            verb, text, actor = e["verb"], e["text"], e["actor"]
            row = by_actor.setdefault(actor, {
                "claims": 0, "takeovers": 0, "releases": 0, "done": 0,
                "notes": 0, "dead_ends": 0})
            if verb == "claim":
                workers.add(actor)
                row["claims"] += 1
                if text.startswith("taking over"):
                    row["takeovers"] += 1
            elif verb == "release":
                row["releases"] += 1
                if text.startswith("blocked on "):
                    blockers["new"] += 1
            elif verb in ("done", "done(no-code)"):
                row["done"] += 1
            elif verb == "note":
                row["notes"] += 1
            elif verb == "note(dead-end)":
                row["notes"] += 1
                row["dead_ends"] += 1
            elif verb == "block":
                blockers["new"] += 1
            elif verb == "unblock":
                blockers["cleared"] += 1
            elif verb == "question" and text.startswith("added (HUMAN)"):
                questions["human_created"] += 1
            elif verb == "answer":
                questions["answered"] += 1
            elif verb == "add" and "(after: " in text:
                dependencies["added"] += len(
                    id_token_pattern(ctx.prefix).findall(
                        text.split("(after: ", 1)[1].split(")", 1)[0]))
            elif verb == "set":
                m = SET_LINE_RE.match(text)
                if not m:
                    continue
                field, old, new = m.group(1), m.group(2), m.group(3)
                if field == "depends_on":
                    dependencies["added" if old == "+" else "removed"] += 1
                elif field == "priority" and old in PRIORITIES and new in PRIORITIES:
                    if PRIORITIES.index(new) < PRIORITIES.index(old):
                        priority["raised"] += 1
                    elif PRIORITIES.index(new) > PRIORITIES.index(old):
                        priority["lowered"] += 1

    # ---- claims at the end of the window ---------------------------------
    stale_days = int(ctx.config.get("stale_claim_days", 7))
    active, stranded = [], []
    for t in population:
        if not t.header.get("claimed_by"):
            continue
        row = {"id": t.id, "status": t.status,
               "claimed_by": t.header.get("claimed_by"),
               "claimed_at": t.header.get("claimed_at")}
        if claim_is_stale_at(t, stale_days, until) or (
                parent is not None and parent.status in ("done", "dropped")
                and t.id != parent.id):
            stranded.append(row)
        else:
            active.append(row)

    # ---- durations -----------------------------------------------------
    c2c, fc2c, c2fc = [], [], []
    for t in population:
        created, closed = t.header.get("created"), t.header.get("closed")
        claims = sorted(e["ts"] for e in t.log() if e["verb"] == "claim")
        first_claim = claims[0] if claims else None
        if closed and in_window(closed):
            c2c.append(_hours(created, closed))
            if first_claim:
                fc2c.append(_hours(first_claim, closed))
        if first_claim and in_window(first_claim):
            c2fc.append(_hours(created, first_claim))
    durations = {"unit": "hours",
                 "created_to_closed": _stats(c2c),
                 "first_claim_to_closed": _stats(fc2c),
                 "created_to_first_claim": _stats(c2fc)}

    # ---- commits (git history only; null when it cannot be computed) -----
    commits_block = None
    if use_git:
        commits, walk_error = walk_commits(ctx.repo, ctx.config.get("baseline"))
        if commits is not None and not walk_error:
            known = {t.id for t in tasks}
            pop_ids = {t.id for t in population}
            exempt_res = compile_exempt_patterns(ctx.config)
            explicit = explicit_links(tasks)
            in_scope = [c for c in commits if in_window(c.ctime)]
            counts = {"linked": 0, "exempt": 0, "unlinked": 0, "dangling": 0}
            linked_tasks_total, linked_n = 0, 0
            per_task: dict[str, int] = {}
            for c in in_scope:
                bucket, dangling = classify_commit(c, ctx.repo, known,
                                                   exempt_res, explicit)
                counts[bucket] += 1
                counts["dangling"] += len(dangling)
                if bucket == "linked":
                    ids = {t for t in c.task_ids if t in known}
                    ids |= set(explicit_link_tasks(c, explicit))
                    linked_n += 1
                    linked_tasks_total += len(ids)
                    for tid in ids:
                        if tid in pop_ids:
                            per_task[tid] = per_task.get(tid, 0) + 1
            done_in_pop = [t for t in population if t.status == "done"]
            final_commit = None
            if parent is not None:
                cands = list(dict.fromkeys(
                    [c["sha"] for c in parent.commits()]
                    + [c.sha7 for c in commits if parent.id in c.task_ids
                       or parent.id in explicit_link_tasks(c, explicit)]))
                cands = [s for s in cands if git_sha_exists(ctx.repo, s)]
                tips = []
                for s in cands:
                    ancestor_of_other = any(
                        o != s and run_git(["merge-base", "--is-ancestor",
                                            s, o], ctx.repo)[0] == 0
                        for o in cands)
                    if not ancestor_of_other:
                        tips.append(s)
                final_commit = tips[0] if tips else None
            commits_block = {
                **counts, "in_window": len(in_scope),
                "tasks_per_linked_commit":
                    round(linked_tasks_total / linked_n, 2) if linked_n else None,
                "linked_commits_per_done_task":
                    round(sum(per_task.get(t.id, 0) for t in done_in_pop)
                          / len(done_in_pop), 2) if done_in_pop else None,
                "final_commit": final_commit,
            }

    data = {
        "window": {"since": since, "until": until},
        "population": {"tasks": len(population), "scope": scope},
        "work": work,
        "dropped_duplicates": {"relation": dropped_dups,
                               "prose_heuristic": prose_dups},
        "ratios": ratios,
        "blockers": blockers,
        "questions": questions,
        "dependencies": dependencies,
        "priority": priority,
        "agents": {"workers": sorted(workers), "by_actor": by_actor,
                   "active_claims": active, "stranded_claims": stranded},
        "durations": durations,
        "commits": commits_block,
        "sources": {
            "log_derived": ["work", "dropped_duplicates", "blockers",
                            "questions", "dependencies", "priority",
                            "agents", "durations"],
            "git_derived": ["commits"] if commits_block is not None else [],
            "lower_bounds": [
                "dependencies.added counts add-line (after: ...) ids only "
                "for tasks filed by a copy >= 1.2.0",
                "work.opened priorities are replayed from set: lines",
                "dropped_duplicates.prose_heuristic is a text match"],
            "out_of_scope": ["validation duration", "integration failures",
                             "resource waits", "regressions/hotfixes — "
                             "orchestrator facts that live in wave notes"],
        },
    }
    p = ", ".join(f"{k}:{v}" for k, v in work["opened"].items() if v)
    human = [
        f"report  window {since or '-'} .. {until or '-'}  "
        f"population {len(population)} task(s) {scope or ''}",
        f"  opened {opened} ({p or '0'})  done {closed_done}  dropped "
        f"{sum(work['closed_dropped'].values())}  dup {dropped_dups}"
        f"(+{prose_dups} prose)  reproduction {ratios['reproduction']}",
        f"  blockers new {blockers['new']} cleared {blockers['cleared']}  "
        f"human q created {questions['human_created']} answered "
        f"{questions['answered']} open {questions['human_open_end']}",
        f"  deps +{dependencies['added']} -{dependencies['removed']}  "
        f"priority up {priority['raised']} down {priority['lowered']}",
        f"  workers {len(workers)}  active claims {len(active)}  stranded "
        f"{len(stranded)}" + (": " + ", ".join(
            f"{s['id']} ({s['claimed_by']})" for s in stranded)
            if stranded else ""),
    ]
    for actor, row in sorted(by_actor.items()):
        human.append(f"    {actor}: " + ", ".join(
            f"{k} {v}" for k, v in row.items() if v))
    d = durations
    human.append(
        f"  hours created->closed median {d['created_to_closed']['median']} "
        f"p90 {d['created_to_closed']['p90']} (n={d['created_to_closed']['n']})"
        f"; claim->closed median {d['first_claim_to_closed']['median']}")
    if commits_block is None:
        human.append("  commits: n/a (no git walk)")
    else:
        c = commits_block
        human.append(
            f"  commits {c['in_window']}: linked {c['linked']} exempt "
            f"{c['exempt']} unlinked {c['unlinked']} dangling {c['dangling']}"
            + (f"  final {c['final_commit']}" if c["final_commit"] else ""))
    emit(args, True, data, errors=problems, human=human)
    return 0


# ---------------------------------------------------------------------------
# doctor: offline version / compatibility report
# ---------------------------------------------------------------------------

VENDORED_VERSION_RE = re.compile(r'^TOOL_VERSION = "([^"]+)"', re.M)


def _read_text_if_exists(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None


def cmd_doctor(args) -> int:
    """Answer "is this vendored copy stale, and does the task corpus match
    the schema this copy expects?" from files alone — no git history, no
    network (the only subprocess is make_ctx's actor lookup, which
    --session / LEDGER_SESSION bypass)."""
    ctx = make_ctx(args)
    tasks, problems = load_all_tasks(ctx)
    unknown_keys, unknown_statuses = [], []
    for t in tasks:
        label = t.id or (t.path.stem if t.path else "?")
        for key in t.header:
            if key not in HEADER_ORDER:
                unknown_keys.append({"task": label, "key": key})
        if t.status not in STATUSES:
            unknown_statuses.append({"task": label, "status": t.status})
    declared = ctx.config.get("version")
    config_newer = isinstance(declared, int) and declared > SCHEMA_VERSION
    corpus_newer = bool(unknown_keys or unknown_statuses)
    compatible = not (config_newer or corpus_newer)

    vendored_path = ctx.ledger_dir / "ledger.py"
    vendored_text = _read_text_if_exists(vendored_path)
    m = VENDORED_VERSION_RE.search(vendored_text or "")
    vendored_version = m.group(1) if m else None
    running_is_vendored = False
    try:
        running_is_vendored = Path(__file__).resolve() == vendored_path.resolve()
    except OSError:
        pass

    root = ctx.ledger_dir.parent
    protocol_md = _read_text_if_exists(ctx.ledger_dir / "PROTOCOL.md")
    claude_md = _read_text_if_exists(root / "CLAUDE.md")
    block = f"{CLAUDE_BEGIN}\n\n{PROTOCOL_TEXT}\n{CLAUDE_END}"
    in_sync = {"PROTOCOL.md": protocol_md == PROTOCOL_TEXT,
               "CLAUDE.md": claude_md is not None and block in claude_md}

    errors: list[dict] = []
    if not compatible:
        what = []
        if config_newer:
            what.append(f"config.json declares schema {declared} > "
                        f"{SCHEMA_VERSION}")
        if unknown_statuses:
            what.append("unknown status " + ", ".join(
                f"'{u['status']}' ({u['task']})" for u in unknown_statuses[:3]))
        if unknown_keys:
            what.append("unknown header key " + ", ".join(
                f"'{u['key']}' ({u['task']})" for u in unknown_keys[:3]))
        errors.append(err(
            "schema-mismatch",
            "the task corpus looks newer than this ledger.py: "
            + "; ".join(what),
            fix_hint="run `python <newer>/ledger.py init` from the repo root "
                     "(init copies itself into .ledger/ and refreshes "
                     "PROTOCOL.md/CLAUDE.md); do not run mutating commands "
                     "from this copy against this corpus. If a key is really "
                     "a typo, ledger validate names it (unknown-key)"))
    if vendored_version is not None and vendored_version != TOOL_VERSION:
        errors.append(err(
            "vendored-stale",
            f"running ledger.py {TOOL_VERSION} but {vendored_path} is "
            f"{vendored_version}", severity="warning",
            fix_hint="run `python <this>/ledger.py init` from the repo root "
                     "to re-vendor, or run the vendored copy"))
    for name, ok in in_sync.items():
        if not ok:
            errors.append(err(
                "protocol-stale",
                f"{name} does not carry this copy's PROTOCOL_TEXT "
                f"(protocol version {PROTOCOL_VERSION})", severity="warning",
                fix_hint="run `python .ledger/ledger.py init` from the repo "
                         "root to regenerate it"))
    data = {
        "tool_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "config_schema_version": declared,
        "corpus_schema_version": SCHEMA_VERSION if not corpus_newer else None,
        "repo_compatible": compatible,
        "vendored_tool_version": vendored_version,
        "running_is_vendored_copy": running_is_vendored,
        "protocol_files_in_sync": in_sync,
        "task_count": len(tasks),
        "corpus_signals": {"unknown_keys": unknown_keys,
                           "unknown_statuses": unknown_statuses},
        "ledger_dir": str(ctx.ledger_dir),
        "python": ".".join(str(x) for x in sys.version_info[:3]),
        "canonical_source": CANONICAL_SOURCE,
    }
    human = [
        f"ledger {TOOL_VERSION} (schema {SCHEMA_VERSION}, protocol "
        f"{PROTOCOL_VERSION}) — {CANONICAL_SOURCE}",
        f"repo: config schema {declared}, {len(tasks)} task(s), "
        f"{'compatible' if compatible else 'NOT compatible'}",
        f"vendored copy: {vendored_version or '(missing)'}"
        + (" (running it)" if running_is_vendored else ""),
        "protocol files: " + ", ".join(
            f"{k} {'in sync' if v else 'STALE'}" for k, v in in_sync.items()),
    ]
    emit(args, compatible, data, errors=errors + problems, human=human)
    return 0 if compatible else 1


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class Parser(argparse.ArgumentParser):
    def error(self, message):  # exit 3 on usage errors per the exit-code table
        self.print_usage(sys.stderr)
        self.exit(3, f"{self.prog}: usage error: {message}\n")


def build_parser() -> Parser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="machine-readable {ok, data, errors} envelope")
    common.add_argument("--session",
                        help="actor id (else LEDGER_SESSION env, else git "
                             "user.name)")

    ap = Parser(prog="ledger", description=__doc__,
                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version",
                    version=f"ledger {TOOL_VERSION} (schema {SCHEMA_VERSION}, "
                            f"protocol {PROTOCOL_VERSION})")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)

    p = sub.add_parser("init", parents=[common], help="scaffold .ledger/")
    p.add_argument("--prefix", default=None, help="task id prefix (default T)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("add", parents=[common], help="create a task")
    p.add_argument("title")
    p.add_argument("-p", "--priority", choices=PRIORITIES, default="p2")
    p.add_argument("-s", "--size", choices=SIZES, default="m")
    p.add_argument("--spec", help="Spec body text, or '-' to read stdin")
    p.add_argument("--after", action="append",
                   help="task id this depends on (repeatable)")
    p.add_argument("--tag", action="append", help="tag (repeatable)")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("list", parents=[common], help="list tasks")
    p.add_argument("--status", action="append", choices=STATUSES)
    p.add_argument("--priority", action="append", choices=PRIORITIES)
    p.add_argument("--tag")
    p.add_argument("--resource", metavar="SLUG",
                   help="sugar for --tag resource:<slug> (ANDed with --tag)")
    p.add_argument("--depends-on", metavar="ID",
                   help="only tasks whose depends_on names this task "
                        "(reverse lookup: which wave was T-x in?)")
    p.add_argument("--claimed", action="store_true")
    p.add_argument("--unclaimed", action="store_true")
    p.add_argument("--mine", action="store_true",
                   help="only tasks claimed by this session (in_progress or "
                        "blocked) — the session-end release list")
    p.set_defaults(fn=cmd_list)

    brief_opts = argparse.ArgumentParser(add_help=False)
    brief_opts.add_argument("--last", type=int, default=None, metavar="N",
                            help="recent Log entries to include (default 10)")
    brief_opts.add_argument("--no-git", action="store_true",
                            help="skip the trailer walk (effective_commits = "
                                 "## Commits)")

    p = sub.add_parser("show", parents=[common, brief_opts],
                       help="show one task in full")
    p.add_argument("id")
    p.add_argument("--brief", action="store_true",
                   help="the bounded digest instead of everything")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("brief", parents=[common, brief_opts],
                       help="bounded derived view of one task (open steps, "
                            "human questions, dead ends, recent Log)")
    p.add_argument("id")
    # NOT set_defaults(last=10): parent-parser actions are shared objects,
    # so that would change --last's default for show/next as well
    p.set_defaults(fn=cmd_brief)

    p = sub.add_parser("next", parents=[common, brief_opts],
                       help="the highest-priority eligible task")
    p.add_argument("--claim", action="store_true",
                   help="claim the top pick atomically")
    p.add_argument("-n", type=int, default=1, help="also list top N")
    p.add_argument("--full", action="store_true",
                   help="return data.task in show's full shape instead of "
                        "the bounded digest")
    p.set_defaults(fn=cmd_next)

    p = sub.add_parser("claim", parents=[common], help="claim a task")
    p.add_argument("id")
    p.add_argument("--force", action="store_true",
                   help="take over a fresh claim held by someone else")
    p.set_defaults(fn=cmd_claim)

    p = sub.add_parser("release", parents=[common],
                       help="end-of-session handoff: unclaim")
    p.add_argument("id")
    p.add_argument("--note", help="where you stopped and why")
    p.add_argument("--blocked", action="store_true",
                   help="release into blocked state")
    p.add_argument("--on", help="with --blocked: human | task-id | "
                                "'external: note'")
    p.add_argument("--force", action="store_true",
                   help="release another session's fresh claim")
    p.set_defaults(fn=cmd_release)

    p = sub.add_parser("set", parents=[common], help="edit header fields")
    p.add_argument("id")
    p.add_argument("--title")
    p.add_argument("--priority", choices=PRIORITIES)
    p.add_argument("--size", choices=SIZES)
    p.add_argument("--add-depends", action="append")
    p.add_argument("--remove-depends", action="append")
    p.add_argument("--add-tag", action="append")
    p.add_argument("--remove-tag", action="append")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("note", parents=[common],
                       help="append a Log breadcrumb")
    p.add_argument("id")
    p.add_argument("text")
    p.add_argument("--dead-end", action="store_true",
                   help="mark as negative knowledge (verb note(dead-end)) so "
                        "brief/next can surface it")
    p.set_defaults(fn=cmd_note)

    p = sub.add_parser("step", parents=[common], help="manage Next Steps")
    p.add_argument("id")
    p.add_argument("action", choices=("add", "check", "uncheck"))
    p.add_argument("value", help="text for add; 1-based index or unique "
                                 "substring for check/uncheck")
    p.set_defaults(fn=cmd_step)

    p = sub.add_parser("question", parents=[common],
                       help="manage Open Questions")
    p.add_argument("id")
    p.add_argument("action", choices=("add", "resolve"))
    p.add_argument("value", help="text for add; index or substring for resolve")
    p.add_argument("--human", action="store_true",
                   help="mark as operator-gated (blocks done)")
    p.add_argument("--answer", help="answer text (resolve)")
    p.set_defaults(fn=cmd_question)

    p = sub.add_parser("questions", parents=[common],
                       help="the operator decision view: open questions "
                            "with context, plus tasks blocked on human")
    p.add_argument("--human", action="store_true",
                   help="only operator-gated questions")
    p.add_argument("--task", action="append", metavar="ID",
                   help="scope to these tasks (repeatable)")
    p.set_defaults(fn=cmd_questions)

    p = sub.add_parser("answers", parents=[common],
                       help="record operator answers in batch")
    p.add_argument("action", choices=("apply",))
    p.add_argument("file", help="`questions --json` output (or a bare list "
                                "of {task, n?, text?, answer}); - for stdin")
    p.set_defaults(fn=cmd_answers)

    p = sub.add_parser("block", parents=[common], help="mark a task blocked")
    p.add_argument("id")
    p.add_argument("--on", required=True,
                   help="human | task-id | 'external: note'")
    p.add_argument("--why")
    p.set_defaults(fn=cmd_block)

    p = sub.add_parser("unblock", parents=[common], help="clear a block")
    p.add_argument("id")
    p.add_argument("--force", action="store_true",
                   help="restore the claim even if its resource is now held "
                        "by another fresh claim")
    p.set_defaults(fn=cmd_unblock)

    p = sub.add_parser("link", parents=[common],
                       help="link commit(s) to a task")
    p.add_argument("id")
    p.add_argument("sha", nargs="+", help="commit sha or ref (e.g. HEAD)")
    p.set_defaults(fn=cmd_link)

    p = sub.add_parser("scan", parents=[common],
                       help="reconcile git history against the ledger")
    p.add_argument("--since", help="scan <since>..HEAD instead of baseline")
    p.add_argument("--write", action="store_true",
                   help="backfill ## Commits lines from trailers")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("done", parents=[common],
                       help="close a task with evidence")
    p.add_argument("id")
    p.add_argument("--commit", action="append", help="link this sha/ref first")
    p.add_argument("--no-code", metavar="REASON",
                   help="close without commits, with a reason")
    p.add_argument("--force", action="store_true",
                   help="override the foreign-fresh-claim guard only (never "
                        "the evidence, question or step gates)")
    p.set_defaults(fn=cmd_done)

    p = sub.add_parser("drop", parents=[common],
                       help="close a task as won't-do")
    p.add_argument("id")
    p.add_argument("--why", help="reason (required unless a relation flag "
                                 "is given)")
    p.add_argument("--duplicate-of", metavar="ID",
                   help="the live task that already covers this work")
    p.add_argument("--superseded-by", metavar="ID",
                   help="the task that replaces this one 1:1")
    p.add_argument("--force", action="store_true",
                   help="drop despite another session's fresh claim")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("validate", parents=[common],
                       help="check every ledger invariant")
    p.add_argument("--coverage", action="store_true",
                   help="also enforce commit->task traceability from git "
                        "history")
    p.add_argument("--strict", action="store_true",
                   help="promote warnings to errors")
    p.add_argument("--no-git", action="store_true",
                   help="skip git-backed checks (exported trees)")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("search", parents=[common],
                       help="ranked text search across task files")
    p.add_argument("terms", nargs="+", metavar="TERM",
                   help="case-insensitive substring (all terms must hit)")
    p.add_argument("--any", action="store_true", help="OR the terms")
    p.add_argument("--regex", action="store_true",
                   help="treat every term as a regular expression")
    p.add_argument("--in", dest="in_fields", metavar="FIELD[,FIELD]",
                   help="restrict to: " + ", ".join(SEARCH_FIELDS))
    p.add_argument("--status", action="append", choices=STATUSES)
    p.add_argument("--open", action="store_true",
                   help="open statuses only (default: every status)")
    p.add_argument("-n", type=int, default=20, help="max rows (default 20)")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("report", parents=[common],
                       help="operator diagnostics: derived wave / backlog "
                            "metrics (never stored, never fed to next/done/"
                            "validate)")
    p.add_argument("--since", metavar="TS|REF",
                   help="YYYY-MM-DD, UTC Z timestamp, or git ref (committer "
                        "time)")
    p.add_argument("--until", metavar="TS|REF")
    p.add_argument("--tag", help="population = tasks carrying TAG")
    p.add_argument("--task", metavar="ID",
                   help="population = the task and its depends_on members "
                        "(including members removed later)")
    p.add_argument("--actor", help="count only this actor's Log events")
    p.add_argument("--no-git", action="store_true",
                   help="skip the commit walk (commits: null)")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("doctor", parents=[common],
                       help="offline version/compatibility report (exit 1 "
                            "if the corpus is newer than this copy)")
    p.set_defaults(fn=cmd_doctor)

    return ap


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    if hasattr(sys.stdin, "reconfigure"):
        try:
            # piped stdin on Windows defaults to the ANSI code page, which
            # silently mojibakes UTF-8 spec text (--spec -)
            sys.stdin.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except LedgerError as e:
        emit(args, False, {}, errors=[e.violation])
        return e.exit_code


if __name__ == "__main__":
    sys.exit(main())
