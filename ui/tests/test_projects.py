import pytest

from ledger_ui.projects import (Registry, discover_checkouts, normalize_root,
                                parse_worktrees, registry_path)


def test_registry_round_trip_lives_in_the_ui_home(ledger, ui_home):
    reg = Registry.load()
    assert reg.projects == [] and registry_path() == ui_home / "projects.json"
    p = reg.add(ledger.root / ".ledger", name="Demo")  # .ledger accepted
    assert p.root == ledger.root.resolve() and p.slug == "Demo"
    reg.save()
    again = Registry.load()
    assert [(x.name, x.root) for x in again.projects] == [
        ("Demo", ledger.root.resolve())]
    # nothing was written into the repo
    assert not (ledger.root / ".ledger" / "projects.json").exists()
    assert again.remove("Demo") and not again.remove("Demo")


def test_registry_refuses_non_ledgers_and_duplicates(ledger, ui_home,
                                                     tmp_path):
    reg = Registry.load()
    with pytest.raises(ValueError, match="no .ledger/ledger.py"):
        reg.add(tmp_path)
    reg.add(ledger.root)
    with pytest.raises(ValueError, match="already registered"):
        reg.add(ledger.root / ".ledger" / "ledger.py")


def test_normalize_root(tmp_path):
    assert normalize_root(tmp_path / ".ledger") == tmp_path.resolve()
    assert normalize_root(tmp_path) == tmp_path.resolve()


def test_parse_worktrees():
    rows = parse_worktrees(
        "worktree C:/r\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree C:/r/.wt/x\nHEAD def\ndetached\n\n"
        "worktree C:/bare\nbare\n")
    assert rows[0] == {"worktree": "C:/r", "HEAD": "abc",
                       "branch": "refs/heads/main"}
    assert rows[1]["detached"] is True and rows[2]["bare"] is True


def test_discover_checkouts_includes_worktrees(ledger, tmp_path):
    ledger.git("branch", "feature")
    wt = tmp_path / "wt-feature"
    ledger.git("worktree", "add", "-q", str(wt), "feature")
    found = discover_checkouts(ledger.root)
    assert [c.key for c in found] == ["main", "wt-feature"]
    assert found[0].is_main and found[0].branch == "main"
    assert found[1].branch == "feature" and found[1].has_ledger


def test_discover_without_git_falls_back_to_root(tmp_path):
    found = discover_checkouts(tmp_path)
    assert len(found) == 1 and found[0].path == tmp_path
