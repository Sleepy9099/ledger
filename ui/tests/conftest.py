"""A real temp ledger driven by this repo's ledger.py, so every UI test reads
what the CLI actually emits."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".ledger" / "ledger.py"
sys.path.insert(0, str(ROOT / "ui" / "src"))


class TempLedger:
    def __init__(self, root: Path, env: dict):
        self.root = root
        self.env = env

    def cli(self, *args: str) -> dict:
        r = subprocess.run(
            [sys.executable, ".ledger/ledger.py", *args, "--json"],
            cwd=self.root, env=self.env, capture_output=True, text=True,
            encoding="utf-8")
        return json.loads(r.stdout)

    def add(self, title: str, *extra: str) -> str:
        return self.cli("add", title, *extra)["data"]["id"]

    def git(self, *args: str) -> str:
        r = subprocess.run(["git", *args], cwd=self.root, env=self.env,
                           capture_output=True, text=True, check=True)
        return r.stdout


@pytest.fixture
def env(tmp_path):
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = tester\n\temail = t@example.com\n"
                   "[init]\n\tdefaultBranch = main\n"
                   "[commit]\n\tgpgsign = false\n", encoding="utf-8")
    e = dict(os.environ)
    e.update(GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_NOSYSTEM="1",
             LEDGER_SESSION="test-agent")
    return e


@pytest.fixture
def ledger(tmp_path, env) -> TempLedger:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".ledger").mkdir()
    shutil.copyfile(SCRIPT, root / ".ledger" / "ledger.py")
    led = TempLedger(root, env)
    led.git("init", "-q")
    led.cli("init")
    led.git("add", "-A")
    led.git("commit", "-q", "-m", "bootstrap", "-m",
            "Ledger-Exempt: ledger bootstrap")
    return led


@pytest.fixture
def ui_home(tmp_path, monkeypatch):
    home = tmp_path / "ui-home"
    monkeypatch.setenv("LEDGER_UI_HOME", str(home))
    return home
