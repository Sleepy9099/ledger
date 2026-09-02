"""The optional packaging shim must stay a thin wrapper around the one file."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_wraps_the_single_file_without_dependencies(ledger_mod):
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # stdlib-only: no tomllib on 3.10, so pin the load-bearing lines by text
    version = re.search(r'^version = "([^"]+)"', text, re.M).group(1)
    assert version == ledger_mod.TOOL_VERSION  # one version line for both
    assert 'ledger = "ledger:main"' in text          # console entry point
    assert 'package-dir = {"" = ".ledger"}' in text  # the module IS the file
    assert 'py-modules = ["ledger"]' in text
    assert "dependencies = []" in text               # never a runtime dep
    assert 'requires-python = ">=3.10"' in text
    # the entry point target exists (console_scripts calls sys.exit(main()))
    assert callable(ledger_mod.main)


def test_single_file_bootstrap_is_unchanged_by_packaging(repo):
    """The copy-one-file bootstrap must not need pyproject at all."""
    assert not (repo.root / "pyproject.toml").exists()
    d = repo.j("doctor")
    assert d["ok"] and d["data"]["running_is_vendored_copy"] is True
