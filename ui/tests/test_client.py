import pytest

from ledger_ui.client import (Capabilities, Envelope, LedgerClient,
                              ReadOnlyViolation, decode, parse_version)


def test_reads_go_through_the_target_copy(ledger):
    tid = ledger.add("Readable task")
    env = LedgerClient(ledger.root).run("list")
    assert env.ok and [t["id"] for t in env.data["tasks"]] == [tid]
    show = LedgerClient(ledger.root).run("show", tid)
    assert show.ok and show.data["header"]["title"] == "Readable task"


def test_identity_is_the_operator(ledger):
    env = LedgerClient(ledger.root).run("next")
    assert env.data["actor"] == {"id": "HUMAN", "source": "flag"}


@pytest.mark.parametrize("verb,args", [
    ("claim", ("T-x",)), ("done", ("T-x",)), ("question", ()),
    ("answers", ()), ("note", ()), ("init", ()),
    ("next", ("--claim",)), ("scan", ("--write",)), ("scan", ("--prune",)),
])
def test_write_surface_is_unreachable(ledger, verb, args):
    with pytest.raises(ReadOnlyViolation):
        LedgerClient(ledger.root).run(verb, *args)


def test_nothing_written_by_a_full_read_pass(ledger):
    tid = ledger.add("Untouched")
    path = ledger.root / ".ledger" / "tasks" / f"{tid}.md"
    before = path.read_bytes()
    c = LedgerClient(ledger.root)
    for verb, args in (("doctor", ()), ("list", ()), ("show", (tid,)),
                       ("questions", ("--human",)), ("next", ()),
                       ("report", ("--no-git",)), ("log", ()),
                       ("validate", ("--coverage",)), ("search", ("x",))):
        c.run(verb, *args)
    assert path.read_bytes() == before


def test_missing_ledger_is_an_envelope_not_an_exception(tmp_path):
    env = LedgerClient(tmp_path).run("list")
    assert not env.ok and env.errors[0]["code"] == "ui-no-ledger"


def test_non_json_output_decodes_to_an_error_row():
    env = decode("usage: ledger ...\n", 3, "invalid choice: 'log'", "log")
    assert not env.ok and env.exit_code == 3
    assert env.errors[0]["code"] == "ui-decode"
    assert "log" in env.errors[0]["message"]


def test_capabilities_gate_on_tool_version():
    def caps(v):
        return Capabilities.from_doctor(Envelope(ok=True, data={
            "tool_version": v, "protocol_version": 17,
            "repo_compatible": True}))
    assert not caps("1.5.0").has("log") and caps("1.5.0").supported
    assert caps("1.6.0").has("log")
    assert not caps("1.4.2").supported
    assert "1.6.0" in caps("1.5.0").missing_reason("log")
    assert parse_version("1.10.3") > parse_version("1.9.9")
    assert parse_version("garbage") is None
