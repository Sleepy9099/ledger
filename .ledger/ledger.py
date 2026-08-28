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
TRAILER_RE = re.compile(r"^(Ledger-Task|Ledger-Exempt):[ \t]*(.+?)[ \t]*$", re.M)
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7}|\|{7})( |$)")
ID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"

GITATTRIBUTES_LINE = ".ledger/** text eol=lf"
GITIGNORE_LINE = ".ledger/.lock"
CLAUDE_BEGIN = "<!-- LEDGER:BEGIN -->"
CLAUDE_END = "<!-- LEDGER:END -->"

DEFAULT_CONFIG = {
    "version": 1,
    "prefix": "T",
    "baseline": None,
    "stale_claim_days": 7,
    "exempt_patterns": ["^Merge ", "^Revert "],
}

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
    "stale-claim": "warning",
    "xl-open": "warning",
    "checkbox-grammar": "warning",
    "done-loose-ends": "warning",
    "unknown-key": "warning",
    "sha-unreachable": "warning",   # git
    "linked-never-claimed": "warning",  # git
    "log-tamper": "warning",        # git, --coverage only
    "exempt-ratio": "info",         # git, --coverage only; never promoted
}

PROTOCOL_TEXT = """# Ledger protocol (required workflow for agents)

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
    fmt = "%H%x00%h%x00%as%x00%s%x00%P%x00%B%x00%x1e"
    rc, out = run_git(["log", "--no-show-signature", f"--format={fmt}",
                       range_spec], repo)
    if rc != 0:
        return None, f"git log {range_spec} failed"
    commits = []
    for record in out.split("\x00\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x00", 5)
        if len(parts) != 6:
            continue
        sha, sha7, date, subject, parents, body = parts
        task_ids, exempt = _parse_trailers(body)
        commits.append(Commit(sha=sha.strip(), sha7=sha7, date=date,
                              subject=subject, body=body,
                              parents=parents.split(), task_ids=task_ids,
                              exempt_reason=exempt))
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
    rc, out = run_git(args, repo)
    if rc != 0:
        return None
    return [line for line in out.split("\n")
            if line.strip() and not re.fullmatch(r"[0-9a-f]{40}", line.strip())]


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


def classify_commit(commit: Commit, repo: Path, known_ids: set[str],
                    exempt_res: list[re.Pattern]) -> tuple[str, list[str]]:
    """Returns (bucket, dangling_ids). Buckets: linked | exempt | unlinked."""
    dangling = [t for t in commit.task_ids if t not in known_ids]
    if any(t in known_ids for t in commit.task_ids):
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
    }


def task_full(ctx: Ctx, task: Task, trailer_map: dict | None = None) -> dict:
    section_shas = [c["sha"] for c in task.commits()]
    trailer_shas = (trailer_map or {}).get(task.id, [])
    effective = list(dict.fromkeys(
        section_shas + [s[:7] for s in trailer_shas]))
    return {
        "header": {k: task.header.get(k) for k in HEADER_ORDER
                   if k in task.header},
        "spec": task.get_section("Spec"),
        "next_steps": task.steps(),
        "open_questions": task.questions(),
        "commits": task.commits(),
        "log": task.log(),
        "effective_commits": effective,
        "last_activity": task.last_activity(),
        "path": str(task.path) if task.path else None,
    }


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


def claim_is_stale(task: Task, stale_days: int) -> bool:
    last = task.last_activity()
    dt = parse_ts(last)
    if dt is None:
        return True
    return datetime.now(timezone.utc) - dt > timedelta(days=stale_days)


def compute_eligible(tasks: list[Task], config: dict):
    """Returns (eligible, why, blocked_on_human).

    eligible: [(task, flag)] sorted; flag is None or 'stale_claim'.
    why: machine-readable near-miss explanations for every open task skipped.
    """
    done_ids = {t.id for t in tasks if t.status == "done"}
    by_id = {t.id: t for t in tasks}
    stale_days = int(config.get("stale_claim_days", 7))
    eligible, why, human = [], [], []
    for task in sorted(tasks, key=sort_key):
        if task.status not in OPEN_STATUSES:
            continue
        if task.status == "blocked":
            reason = task.header.get("blocked_on", "?")
            why.append({"id": task.id, "ineligible_because": f"blocked_on {reason}"})
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
            details = ", ".join(
                f"{d} ({by_id[d].status if d in by_id else 'missing'})"
                for d in missing)
            why.append({"id": task.id,
                        "ineligible_because": f"depends_on {details}"})
            continue
        if task.size == "xl":
            why.append({"id": task.id, "ineligible_because":
                        "size xl — split it into smaller tasks first"})
            continue
        eligible.append((task, flag))
    return eligible, why, human


def apply_claim(task: Task, actor: str, takeover_from: str | None) -> None:
    task.header["status"] = "in_progress"
    task.header["claimed_by"] = actor
    task.header["claimed_at"] = now_ts()
    task.header.pop("blocked_on", None)
    if takeover_from:
        task.append_log(actor, "claim",
                        f"taking over claim from {takeover_from}")
    else:
        task.append_log(actor, "claim", "claimed")


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

    task.append_log(ctx.actor, "add", f"created: {task.title}")
    task.path = task_path(ctx, task.id)
    save_task(task)
    emit(args, True, {"id": task.id, "path": str(task.path)},
         human=[f"added {task.id}: {task.title}"])
    return 0


def cmd_list(args) -> int:
    ctx = make_ctx(args)
    tasks, problems = load_all_tasks(ctx)
    rows = []
    for task in sorted(tasks, key=sort_key):
        if args.status and task.status not in args.status:
            continue
        if args.priority and task.priority not in args.priority:
            continue
        if args.tag and args.tag not in task.tags:
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
    task = load_task_or_die(ctx, args.id, for_write=False)
    data = task_full(ctx, task, trailer_links(ctx))
    human = [serialize_task(task).rstrip("\n"), "",
             f"# last_activity: {data['last_activity']}",
             f"# effective_commits: {', '.join(data['effective_commits']) or '(none)'}"]
    emit(args, True, data, human=human)
    return 0


def cmd_next(args) -> int:
    ctx = make_ctx(args, mutating=args.claim)
    tasks, problems = load_all_tasks(ctx)
    bad = structural_problem_stems(problems)
    pool = [t for t in tasks
            if t.id not in bad and (t.path is None or t.path.stem not in bad)]
    eligible, why, human_blocked = compute_eligible(pool, ctx.config)
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
    if not eligible:
        emit(args, True, {"task": None, "claimed": False, "why": why,
                          "blocked_on_human": human_blocked},
             errors=problems,
             human=["nothing eligible"] +
                   [f"  {w['id']}: {w['ineligible_because']}" for w in why])
        return 0
    top, flag = eligible[0]
    claimed = False
    if args.claim:
        takeover = top.header.get("claimed_by") if flag == "stale_claim" else None
        apply_claim(top, ctx.actor, takeover)
        save_task(top)
        claimed = True
    data = {"task": task_full(ctx, top, trailer_links(ctx)), "claimed": claimed,
            "stale_takeover": flag == "stale_claim",
            "why": why, "blocked_on_human": human_blocked}
    if args.n > 1:
        data["tasks"] = [task_brief(t) for t, _ in eligible[:args.n]]
    verb = "claimed" if claimed else "next"
    emit(args, True, data, errors=problems,
         human=[f"{verb}: {top.id} [{top.priority}/{top.size}] {top.title}"]
               + ([f"  (took over stale claim)"] if flag == "stale_claim" else [])
               + [f"  {top.path}"])
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
    apply_claim(task, ctx.actor, takeover)
    save_task(task)
    emit(args, True, {"id": task.id, "claimed_by": ctx.actor},
         human=[f"claimed {task.id}: {task.title}"])
    return 0


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
    else:
        task.header["status"] = "todo"
        task.header.pop("blocked_on", None)
    task.append_log(ctx.actor, "release", args.note or "released")
    save_task(task)
    emit(args, True, {"id": task.id, "status": task.status},
         human=[f"released {task.id} -> {task.status}"])
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
    task.append_log(ctx.actor, "note", args.text)
    save_task(task)
    emit(args, True, {"id": task.id}, human=[f"noted on {task.id}"])
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
        idx, line = hit
        m = CHECKBOX_RE.match(line)
        if m.group(1) == "x":
            raise LedgerError("bad-state", "that question is already answered",
                              task=task.id)
        date = now_ts()[:10]
        answer = sanitize_inline(args.answer)
        new_line = f"- [x] {m.group(2)} -- ANSWERED ({date}): {answer}"
        lines = content.split("\n")
        lines[idx] = new_line
        task.set_section("Open Questions", "\n".join(lines))
        task.append_log(ctx.actor, "answer", f"'{m.group(2)}' -> {answer}")
    save_task(task)
    emit(args, True, {"id": task.id, "open_questions": task.questions()},
         human=[f"question {args.action} on {task.id}"])
    return 0


def cmd_questions(args) -> int:
    ctx = make_ctx(args)
    tasks, problems = load_all_tasks(ctx)
    out = []
    for task in sorted(tasks, key=sort_key):
        if task.status not in OPEN_STATUSES:
            continue
        for q in task.questions():
            if q["answered"]:
                continue
            if args.human and not q["human"]:
                continue
            out.append({"task": task.id, "title": task.title, "n": q["n"],
                        "human": q["human"], "text": q["text"]})
    human = [f"{q['task']} #{q['n']}{' [HUMAN]' if q['human'] else ''}: "
             f"{q['text']}" for q in out] or ["no open questions"]
    emit(args, True, {"questions": out}, errors=problems, human=human)
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
    task.header.pop("blocked_on", None)
    if task.header.get("claimed_by"):
        task.header["status"] = "in_progress"
    else:
        task.header["status"] = "todo"
    task.append_log(ctx.actor, "unblock", f"-> {task.header['status']}")
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
    linked, exempt, unlinked, dangling = [], [], [], []
    for c in commits:
        bucket, bad_ids = classify_commit(c, repo, known, exempt_res)
        for tid in bad_ids:
            dangling.append({"sha": c.sha7, "id": tid})
        if bucket == "linked":
            for tid in c.task_ids:
                if tid in known:
                    linked.append({"sha": c.sha7, "task": tid})
        elif bucket == "exempt":
            exempt.append(c.sha7)
        else:
            unlinked.append({"sha": c.sha7, "subject": c.subject})
    backfilled = []
    if args.write:
        backfilled = _backfill_from_trailers(
            ctx, tasks, commits, skip_ids=structural_problem_stems(problems))
    data = {"linked": linked, "exempt": exempt, "unlinked": unlinked,
            "dangling": dangling, "backfilled": backfilled,
            "commits_scanned": len(commits)}
    human = [f"scanned {len(commits)} commit(s): {len(linked)} linked, "
             f"{len(exempt)} exempt, {len(unlinked)} unlinked, "
             f"{len(dangling)} dangling"]
    for u in unlinked:
        human.append(f"  unlinked {u['sha']}: {u['subject']}")
    for d in dangling:
        human.append(f"  dangling {d['sha']}: trailer names unknown id {d['id']}")
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
    open_human = [q for q in task.questions() if q["human"] and not q["answered"]]
    if open_human and not args.force:
        for q in open_human:
            refusals.append(err(
                "done-human-questions",
                f"unanswered HUMAN question: {q['text']}",
                task=task.id,
                fix_hint="ledger question <id> resolve <n> --answer \"...\" after "
                         "the human answers, or --force if truly moot"))
    if refusals:
        emit(args, False, {"id": task.id}, errors=refusals)
        return 2

    warnings = []
    open_steps = [s for s in task.steps() if not s["done"]]
    if open_steps:
        warnings.append(err("done-loose-ends",
                            f"{len(open_steps)} unchecked next step(s)",
                            task=task.id, severity="warning",
                            fix_hint="check them or delete stale ones"))
    open_q = [q for q in task.questions() if not q["answered"] and not q["human"]]
    if open_q:
        warnings.append(err("done-loose-ends",
                            f"{len(open_q)} unanswered question(s)",
                            task=task.id, severity="warning"))

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
    emit(args, True, {"id": task.id, "commits": task.commits()},
         errors=warnings, human=[f"done: {task.id} {task.title}"])
    return 0


def cmd_drop(args) -> int:
    ctx = make_ctx(args, mutating=True)
    task = load_task_or_die(ctx, args.id, for_write=True)
    if task.status in ("done", "dropped"):
        raise LedgerError("bad-state", f"{task.id} is already {task.status}",
                          task=task.id)
    _guard_foreign_claim(ctx, task, args.force, "closing")
    task.header["status"] = "dropped"
    task.header["closed"] = now_ts()
    task.header.pop("claimed_by", None)
    task.header.pop("claimed_at", None)
    task.header.pop("blocked_on", None)
    task.append_log(ctx.actor, "drop", args.why)
    save_task(task)
    all_tasks, _ = load_all_tasks(ctx)
    warnings = [
        err("refs",
            f"{t.id} depends_on {task.id}, which is now dropped — it will "
            "never become eligible", task=t.id, severity="warning",
            fix_hint=f"ledger set {t.id} --remove-depends {task.id}")
        for t in all_tasks
        if task.id in t.depends_on and t.status in OPEN_STATUSES]
    emit(args, True, {"id": task.id}, errors=warnings,
         human=[f"dropped {task.id}: {args.why}"])
    return 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


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
                                  fix_hint=f"one of: {', '.join(STATUSES)}"))
        if task.priority not in PRIORITIES:
            violations.append(err("enums", f"invalid priority '{task.priority}'",
                                  task=tid,
                                  fix_hint=f"one of: {', '.join(PRIORITIES)}"))
        if task.size not in SIZES:
            violations.append(err("enums", f"invalid size '{task.size}'",
                                  task=tid,
                                  fix_hint=f"one of: {', '.join(SIZES)}"))
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
        if status == "in_progress" and claimed_at:
            if claim_is_stale(task, stale_days):
                violations.append(err(
                    "stale-claim",
                    f"claim by {claimed_by} has been inactive more than "
                    f"{stale_days} day(s)", task=tid, severity="warning",
                    fix_hint="ledger release <id>, or ledger claim <id> --force "
                             "to take over"))
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
    return violations


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
    exempt_count = 0
    for c in commits:
        bucket, dangling = classify_commit(c, repo, known, exempt_res)
        for tid in dangling:
            violations.append(err(
                "trailer-dangling",
                f"commit {c.sha7} trailer names unknown task id '{tid}'",
                fix_hint="fix the id with ledger link, or add the missing task"))
        if bucket == "exempt":
            exempt_count += 1
        elif bucket == "unlinked":
            violations.append(err(
                "coverage",
                f"commit {c.sha7} ('{c.subject}') has no Ledger-Task/"
                "Ledger-Exempt trailer",
                fix_hint="repair with: ledger link <task-id> " + c.sha7
                         + " — and use trailers going forward"))
    if commits:
        violations.append(err(
            "exempt-ratio",
            f"{exempt_count}/{len(commits)} commit(s) in scope are exempt",
            severity="info"))

    # log-tamper: Log bullet lines deleted across baseline..HEAD (best effort)
    baseline = ctx.config.get("baseline")
    try:
        tasks_rel = ctx.tasks_dir.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        tasks_rel = None  # ledger dir outside the repo: skip log-tamper
    if baseline and tasks_rel and git_sha_exists(repo, baseline):
        # whole-file deletion is the bluntest tamper: compare the task files
        # recorded at baseline against what exists on disk now
        # (core.quotePath=false: octal-escaped non-ASCII paths would silently
        # dodge the .md-suffix matching below)
        rc, out = run_git(["-c", "core.quotePath=false", "ls-tree", "-r",
                           "--name-only", baseline, "--", tasks_rel], repo)
        if rc == 0:
            on_disk = ({p.name for p in ctx.tasks_dir.glob("*.md")}
                       if ctx.tasks_dir.is_dir() else set())
            for line in out.split("\n"):
                name = Path(line.strip()).name
                if line.strip().endswith(".md") and name not in on_disk:
                    violations.append(err(
                        "log-tamper",
                        f"task file {name} present at baseline has been "
                        "deleted", task=Path(name).stem, severity="warning",
                        fix_hint="task files are never deleted (use ledger "
                                 "drop); restore it from git history"))
        # -c overrides + --no-ext-diff: user git config (diff.noprefix,
        # diff.mnemonicPrefix, diff.external, core.quotePath) must not
        # silently change the output format this parser depends on.
        # Diffing baseline against the WORKING TREE (no HEAD arg) means the
        # protocol's pre-commit session-end validate sees uncommitted
        # Log-line deletions too, matching the file-deletion check above.
        rc, out = run_git(["-c", "diff.noprefix=false",
                           "-c", "diff.mnemonicPrefix=false",
                           "-c", "core.quotePath=false",
                           "diff", "--no-ext-diff", baseline, "--",
                           tasks_rel], repo)
        if rc == 0 and out:
            current_file = None
            removed: dict[str, list[str]] = {}
            added: dict[str, set[str]] = {}
            for line in out.split("\n"):
                if line.startswith("diff --git"):
                    current_file = None  # reset until the +++ header
                elif line.startswith("+++ b/"):
                    current_file = line[6:]
                elif line.startswith("+++ "):
                    current_file = None  # e.g. '+++ /dev/null' (deletion)
                elif line.startswith("-") and not line.startswith("---") \
                        and current_file:
                    content = line[1:]
                    if LOG_LINE_RE.match(content):
                        removed.setdefault(current_file, []).append(content)
                elif line.startswith("+") and current_file:
                    added.setdefault(current_file, set()).add(line[1:])
            for fname, lines in removed.items():
                gone = [x for x in lines if x not in added.get(fname, set())]
                if gone:
                    violations.append(err(
                        "log-tamper",
                        f"{Path(fname).name}: {len(gone)} Log line(s) present at "
                        "baseline were deleted", task=Path(fname).stem,
                        severity="warning",
                        fix_hint="Log is append-only; restore the lines from "
                                 "git history"))
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
    p.add_argument("--claimed", action="store_true")
    p.add_argument("--unclaimed", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show", parents=[common], help="show one task in full")
    p.add_argument("id")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("next", parents=[common],
                       help="the highest-priority eligible task")
    p.add_argument("--claim", action="store_true",
                   help="claim the top pick atomically")
    p.add_argument("-n", type=int, default=1, help="also list top N")
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
                       help="all open questions across tasks")
    p.add_argument("--human", action="store_true",
                   help="only operator-gated questions")
    p.set_defaults(fn=cmd_questions)

    p = sub.add_parser("block", parents=[common], help="mark a task blocked")
    p.add_argument("id")
    p.add_argument("--on", required=True,
                   help="human | task-id | 'external: note'")
    p.add_argument("--why")
    p.set_defaults(fn=cmd_block)

    p = sub.add_parser("unblock", parents=[common], help="clear a block")
    p.add_argument("id")
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
                   help="override the unanswered-HUMAN-question refusal and "
                        "the foreign-fresh-claim guard")
    p.set_defaults(fn=cmd_done)

    p = sub.add_parser("drop", parents=[common],
                       help="close a task as won't-do")
    p.add_argument("id")
    p.add_argument("--why", required=True)
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
