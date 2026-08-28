"""The host-CI contract, applied to this repository's own ledger.

This is the test every bootstrapped project gets: if a commit lands in this
repo's history without a Ledger-Task/Ledger-Exempt trailer, or a task is
closed without evidence, this test fails. Work tackled must appear in the
storage.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_this_repos_ledger_is_valid():
    r = subprocess.run(
        [sys.executable, str(ROOT / ".ledger" / "ledger.py"), "validate",
         "--coverage", "--strict", "--json"],
        cwd=str(ROOT), capture_output=True, text=True)
    payload = json.loads(r.stdout)
    assert r.returncode == 0, json.dumps(payload["errors"], indent=2)
