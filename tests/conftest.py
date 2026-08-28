"""Shared fixtures: isolated git environments and a CLI driver."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".ledger" / "ledger.py"


@pytest.fixture(scope="session")
def ledger_mod():
    spec = importlib.util.spec_from_file_location("ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ledger"] = mod  # dataclasses needs it for string annotations
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def base_env(tmp_path_factory):
    cfg = tmp_path_factory.mktemp("gitcfg") / "gitconfig"
    cfg.write_text(
        "[user]\n\tname = tester\n\temail = tester@example.com\n"
        "[init]\n\tdefaultBranch = main\n"
        "[commit]\n\tgpgsign = false\n"
        "[core]\n\tautocrlf = false\n",
        encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_GLOBAL": str(cfg),
        "GIT_CONFIG_NOSYSTEM": "1",
        "LEDGER_SESSION": "test-session",
    })
    return env


class LedgerRepo:
    """Drives the ledger CLI and git inside one temp project."""

    def __init__(self, root: Path, env: dict):
        self.root = root
        self.env = env

    @property
    def script(self) -> Path:
        deployed = self.root / ".ledger" / "ledger.py"
        return deployed if deployed.exists() else SCRIPT

    def run(self, *args: str, input: str | None = None):
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            cwd=str(self.root), env=self.env,
            capture_output=True, text=True, input=input)

    def j(self, *args: str, expect: int = 0, input: str | None = None) -> dict:
        r = self.run(*args, "--json", input=input)
        assert r.returncode == expect, (
            f"rc={r.returncode} (wanted {expect})\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        return json.loads(r.stdout)

    def git(self, *args: str, check: bool = True):
        r = subprocess.run(["git", *args], cwd=str(self.root), env=self.env,
                           capture_output=True, text=True)
        if check:
            assert r.returncode == 0, f"git {args}: {r.stdout}\n{r.stderr}"
        return r

    def commit_all(self, subject: str, trailers: tuple[str, ...] = ()) -> str:
        self.git("add", "-A")
        cmd = ["commit", "-q", "--allow-empty", "-m", subject]
        for t in trailers:
            cmd += ["-m", t]
        self.git(*cmd)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def add_task(self, title: str, *extra: str) -> str:
        return self.j("add", title, *extra)["data"]["id"]

    def task_file(self, tid: str) -> Path:
        return self.root / ".ledger" / "tasks" / f"{tid}.md"

    def read(self, tid: str) -> str:
        return self.task_file(tid).read_text(encoding="utf-8")

    def write(self, tid: str, text: str) -> None:
        with open(self.task_file(tid), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def _isolated_env(base_env: dict, tmp_path: Path) -> dict:
    env = dict(base_env)
    # stop git from discovering repos above the test sandbox
    env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)
    return env


@pytest.fixture
def repo(tmp_path, base_env) -> LedgerRepo:
    """A git repo with an initialized ledger and a clean coverage state."""
    lr = LedgerRepo(tmp_path / "repo", _isolated_env(base_env, tmp_path))
    lr.root.mkdir()
    lr.git("init", "-q")
    (lr.root / "README.txt").write_text("hello\n", encoding="utf-8")
    lr.commit_all("initial")  # pre-baseline: exempt from coverage by range
    r = lr.run("init")
    assert r.returncode == 0, r.stdout + r.stderr
    lr.commit_all("Add task ledger", ("Ledger-Exempt: ledger bootstrap",))
    return lr


@pytest.fixture
def plain(tmp_path, base_env) -> LedgerRepo:
    """An initialized ledger in a directory with no git repo."""
    lr = LedgerRepo(tmp_path / "plain", _isolated_env(base_env, tmp_path))
    lr.root.mkdir()
    r = lr.run("init")
    assert r.returncode == 0, r.stdout + r.stderr
    return lr
