"""Which ledgers the UI knows about, and the checkouts each one has.

The registry is a user-level preference file (paths and display names),
never stored inside a repo and never holding task state.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .client import ledger_script


def config_dir() -> Path:
    override = os.environ.get("LEDGER_UI_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "ledger-ui"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ledger-ui"


def registry_path() -> Path:
    return config_dir() / "projects.json"


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return slug or "project"


def normalize_root(path: str | Path) -> Path:
    """Accept a repo root or its `.ledger` directory (or ledger.py)."""
    p = Path(path).expanduser()
    if p.name == "ledger.py":
        p = p.parent
    if p.name == ".ledger":
        p = p.parent
    return p.resolve()


@dataclass
class Project:
    name: str
    root: Path

    @property
    def slug(self) -> str:
        return slugify(self.name)


@dataclass
class Registry:
    projects: list[Project] = field(default_factory=list)
    path: Path | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> "Registry":
        path = path or registry_path()
        reg = cls(path=path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return reg
        for row in raw.get("projects", []):
            if row.get("name") and row.get("root"):
                reg.projects.append(Project(row["name"], Path(row["root"])))
        return reg

    def save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "projects": [
            {"name": p.name, "root": str(p.root)} for p in self.projects]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, slug: str) -> Project | None:
        return next((p for p in self.projects if p.slug == slug), None)

    def add(self, path: str | Path, name: str | None = None) -> Project:
        root = normalize_root(path)
        if ledger_script(root) is None:
            raise ValueError(f"no .ledger/ledger.py under {root}")
        name = name or root.name
        if any(p.root == root for p in self.projects):
            raise ValueError(f"{root} is already registered")
        if self.get(slugify(name)):
            raise ValueError(f"a project named '{name}' already exists")
        project = Project(name, root)
        self.projects.append(project)
        return project

    def remove(self, slug: str) -> bool:
        before = len(self.projects)
        self.projects = [p for p in self.projects if p.slug != slug]
        return len(self.projects) != before


@dataclass
class Checkout:
    """One working tree of a project: the main checkout or a worktree."""
    key: str
    path: Path
    branch: str | None
    head: str | None
    is_main: bool

    @property
    def has_ledger(self) -> bool:
        return ledger_script(self.path) is not None

    @property
    def label(self) -> str:
        where = "main checkout" if self.is_main else self.path.name
        return f"{self.branch or 'detached'} · {where}"


def parse_worktrees(porcelain: str) -> list[dict]:
    rows, cur = [], {}
    for line in porcelain.splitlines():
        if not line.strip():
            if cur:
                rows.append(cur)
            cur = {}
            continue
        key, _, value = line.partition(" ")
        cur[key] = value if value else True
    if cur:
        rows.append(cur)
    return rows


def discover_checkouts(root: Path) -> list[Checkout]:
    """The main checkout first, then every other worktree git knows of.
    Without git (an exported tree) the root alone is the one checkout."""
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"], cwd=str(root),
            capture_output=True, text=True, encoding="utf-8", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = parse_worktrees(out.stdout) if out.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        rows = []
    checkouts: list[Checkout] = []
    used: set[str] = set()
    for i, row in enumerate(rows):
        if row.get("bare") or "worktree" not in row:
            continue
        path = Path(row["worktree"])
        branch = row.get("branch")
        if isinstance(branch, str):
            branch = branch.removeprefix("refs/heads/")
        else:
            branch = None
        is_main = i == 0
        key = "main" if is_main else slugify(path.name)
        while key in used:
            key += "-"
        used.add(key)
        checkouts.append(Checkout(key, path, branch, row.get("HEAD"),
                                  is_main))
    if not checkouts:
        checkouts.append(Checkout("main", Path(root), None, None, True))
    return checkouts
