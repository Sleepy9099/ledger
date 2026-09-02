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



def test_protocol_files_mirror_protocol_text(ledger_mod):
    """init maintains PROTOCOL.md and the CLAUDE.md block; this repo must
    never drift from the literal it ships."""
    protocol = (ROOT / ".ledger" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert protocol.replace("\r\n", "\n") == ledger_mod.PROTOCOL_TEXT
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    block = (f"{ledger_mod.CLAUDE_BEGIN}\n\n{ledger_mod.PROTOCOL_TEXT}\n"
             f"{ledger_mod.CLAUDE_END}")
    assert block in claude.replace("\r\n", "\n")


def test_protocol_text_stays_within_its_budget(ledger_mod):
    """The protocol block is loaded into every agent session (review §22):
    the ceiling below already accounts for the search, brief, dead-end,
    list --mine, options-under-questions and exemption-taxonomy clauses.
    A later edit must REPLACE wording, not append."""
    text = ledger_mod.PROTOCOL_TEXT
    assert text.count("\n") <= 110, text.count("\n")
    assert len(text.encode("utf-8")) <= 6000, len(text.encode("utf-8"))
