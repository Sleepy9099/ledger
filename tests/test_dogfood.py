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


def test_ci_workflow_keeps_the_cross_platform_claim_true():
    """The GitHub Actions matrix is what makes the README's cross-platform
    and full-history claims continuously true; pin the load-bearing parts
    so a casual edit cannot silently shrink them."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    assert "fetch-depth: 0" in workflow      # validate refuses shallow clones
    assert "python -m pytest" in workflow
    for runner in ("ubuntu-latest", "windows-latest"):
        assert runner in workflow
    for version in ('"3.10"', '"3.14"'):
        assert version in workflow
