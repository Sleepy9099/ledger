"""`ledger doctor`: offline version separation and corpus compatibility."""
import json
import re


def test_version_constants_are_separate_and_reported(ledger_mod, plain):
    assert re.fullmatch(r"\d+\.\d+\.\d+", ledger_mod.TOOL_VERSION)
    assert isinstance(ledger_mod.SCHEMA_VERSION, int)
    assert isinstance(ledger_mod.PROTOCOL_VERSION, int)
    assert ledger_mod.DEFAULT_CONFIG["version"] == ledger_mod.SCHEMA_VERSION
    d = plain.j("doctor")
    assert d["ok"] and d["errors"] == []
    data = d["data"]
    assert data["tool_version"] == ledger_mod.TOOL_VERSION
    assert data["schema_version"] == ledger_mod.SCHEMA_VERSION
    assert data["protocol_version"] == ledger_mod.PROTOCOL_VERSION
    assert data["config_schema_version"] == ledger_mod.SCHEMA_VERSION
    assert data["corpus_schema_version"] == ledger_mod.SCHEMA_VERSION
    assert data["repo_compatible"] is True
    assert data["canonical_source"] == "github.com/Sleepy9099/ledger"
    # the fixture runs the vendored copy that init wrote
    assert data["vendored_tool_version"] == ledger_mod.TOOL_VERSION
    assert data["running_is_vendored_copy"] is True
    assert data["protocol_files_in_sync"] == {"PROTOCOL.md": True,
                                              "CLAUDE.md": True}
    r = plain.run("--version")
    assert r.returncode == 0 and ledger_mod.TOOL_VERSION in r.stdout


def test_doctor_flags_a_corpus_newer_than_the_tool(plain):
    tid = plain.add_task("From the future")
    plain.write(tid, plain.read(tid).replace("status: todo", "status: ready"))
    d = plain.j("doctor", expect=1)
    assert d["ok"] is False
    assert d["data"]["repo_compatible"] is False
    assert d["data"]["corpus_schema_version"] is None
    mismatch = [e for e in d["errors"] if e["code"] == "schema-mismatch"]
    assert len(mismatch) == 1
    assert "init" in mismatch[0]["fix_hint"]
    assert "mutating" in mismatch[0]["fix_hint"]
    assert d["data"]["corpus_signals"]["unknown_statuses"] == [
        {"task": tid, "status": "ready"}]
    # the same signal rides on validate's enums hint, which old copies DO have
    v = json.loads(plain.run("validate", "--no-git", "--json").stdout)
    enums = [e for e in v["errors"] if e["code"] == "enums"]
    assert enums and "newer ledger.py" in enums[0]["fix_hint"]
    assert "do not run mutating commands" in enums[0]["fix_hint"]

    plain.write(tid, plain.read(tid).replace("status: ready", "status: todo")
                .replace(f"id: {tid}", f"id: {tid}\nlease: x"))
    d = plain.j("doctor", expect=1)
    assert d["data"]["corpus_signals"]["unknown_keys"] == [
        {"task": tid, "key": "lease"}]


def test_doctor_flags_a_newer_config_schema(plain):
    cfg_path = plain.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["version"] = 99
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    d = plain.j("doctor", expect=1)
    assert d["data"]["config_schema_version"] == 99
    assert d["data"]["repo_compatible"] is False
    assert any(e["code"] == "schema-mismatch" for e in d["errors"])


def test_doctor_detects_stale_protocol_files_and_stale_vendored_copy(plain):
    protocol = plain.root / ".ledger" / "PROTOCOL.md"
    protocol.write_text("# an older protocol\n", encoding="utf-8")
    d = plain.j("doctor")  # warnings only: still exit 0
    assert d["ok"]
    assert d["data"]["protocol_files_in_sync"]["PROTOCOL.md"] is False
    stale = [e for e in d["errors"] if e["code"] == "protocol-stale"]
    assert stale and stale[0]["severity"] == "warning"
    assert "init" in stale[0]["fix_hint"]
    plain.j("init")  # the documented repair
    assert plain.j("doctor")["data"]["protocol_files_in_sync"]["PROTOCOL.md"]

    vendored = plain.root / ".ledger" / "ledger.py"
    text = vendored.read_text(encoding="utf-8")
    vendored.write_text(re.sub(r'^TOOL_VERSION = "[^"]+"',
                               'TOOL_VERSION = "0.0.1"', text, count=1,
                               flags=re.M), encoding="utf-8", newline="\n")
    d = plain.j("doctor")  # the fixture now runs the (older) vendored copy...
    assert d["data"]["tool_version"] == "0.0.1"
    assert d["data"]["vendored_tool_version"] == "0.0.1"  # ...so no warning


def test_doctor_in_process_tool_newer_than_corpus_is_compatible(
        ledger_mod, plain, monkeypatch, capsys):
    """The reverse case: a newer tool over an older bootstrap is fine — a
    lower declared config schema is reported, not refused."""
    cfg_path = plain.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["version"] = 0
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    monkeypatch.chdir(plain.root)
    monkeypatch.setattr(ledger_mod, "SCHEMA_VERSION", 1)
    args = ledger_mod.build_parser().parse_args(
        ["doctor", "--json", "--session", "in-process"])
    rc = args.fn(args)
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["ok"]
    assert payload["data"]["config_schema_version"] == 0
    assert payload["data"]["repo_compatible"] is True


def test_reinit_never_rewrites_config_json(repo):
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["version"] = 0  # an older bootstrap; init must not "upgrade" it
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    before = cfg_path.read_bytes()
    repo.j("init")
    assert cfg_path.read_bytes() == before
    # task-mutating commands never touch it either
    tid = repo.add_task("Config must stay put")
    repo.j("claim", tid)
    repo.j("done", tid, "--no-code", "n/a")
    assert cfg_path.read_bytes() == before


def test_doctor_never_touches_git_history(plain):
    """`plain` has no repository at all — doctor must still answer fully."""
    d = plain.j("doctor")
    assert d["ok"] and d["data"]["task_count"] == 0



def test_protocol_adapters_are_maintained_and_verified(repo):
    d = repo.j("init", "--adapter", "AGENTS.md")
    assert d["data"]["adapters"] == ["CLAUDE.md", "AGENTS.md"]
    cfg = json.loads((repo.root / ".ledger" / "config.json").read_text(
        encoding="utf-8"))
    assert cfg["protocol_adapters"] == ["CLAUDE.md", "AGENTS.md"]
    agents = (repo.root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("<!-- LEDGER:BEGIN -->") == 1
    assert "ledger next --claim --json" in agents
    repo.j("init")  # re-init keeps exactly one block per adapter
    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (repo.root / name).read_text(encoding="utf-8")
        assert text.count("<!-- LEDGER:BEGIN -->") == 1, name
    d = repo.j("doctor")
    assert d["data"]["protocol_files_in_sync"] == {
        "PROTOCOL.md": True, "CLAUDE.md": True, "AGENTS.md": True}
    (repo.root / "AGENTS.md").write_text("# stale\n", encoding="utf-8")
    d = repo.j("doctor")
    assert d["data"]["protocol_files_in_sync"]["AGENTS.md"] is False
    assert any(e["code"] == "protocol-stale" and "AGENTS.md" in e["message"]
               for e in d["errors"])
    # an existing AGENTS.md with other content keeps that content
    (repo.root / "AGENTS.md").write_text("# House rules\n\nBe kind.\n",
                                         encoding="utf-8")
    repo.j("init")
    agents = (repo.root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# House rules") and "Be kind." in agents
    assert agents.count("<!-- LEDGER:BEGIN -->") == 1
    # the protocol no longer assumes one vendor for the session id
    assert "<agent>-<YYYY-MM-DD>" in (repo.root / ".ledger" / "PROTOCOL.md"
                                      ).read_text(encoding="utf-8")



def test_malformed_config_types_are_config_errors_not_tracebacks(plain):
    cfg_path = plain.root / ".ledger" / "config.json"
    good = json.loads(cfg_path.read_text(encoding="utf-8"))
    bad_values = {
        "stale_claim_days": "x", "exempt_patterns": "^Merge ", "prefix": 5,
        "baseline": 3, "exempt_allowed_paths": "docs/**",
        "exempt_policy_since": 12, "protocol_adapters": "CLAUDE.md",
        "version": "1",
    }
    for key, value in bad_values.items():
        cfg = dict(good)
        cfg[key] = value
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        r = plain.run("list", "--json")
        assert r.returncode == 2, (key, r.stdout, r.stderr)
        payload = json.loads(r.stdout)  # an envelope, never a traceback
        assert payload["errors"][0]["code"] == "config", key
        assert key in payload["errors"][0]["message"], key
        assert payload["errors"][0]["fix_hint"], key
    cfg_path.write_text(json.dumps(good, indent=2), encoding="utf-8")
    assert plain.j("list")["ok"]



def test_init_reports_whether_the_tool_was_copied(repo):
    import re as _re
    import subprocess as _sp
    import sys as _sys
    from conftest import SCRIPT
    d = repo.j("init")  # the fixture runs the vendored copy on itself
    assert d["data"]["tool_copied"] is False
    r = repo.run("init")
    assert "running the vendored copy" in r.stdout
    vendored = repo.root / ".ledger" / "ledger.py"
    vendored.write_text(_re.sub(r'^TOOL_VERSION = "[^"]+"',
                                'TOOL_VERSION = "0.0.1"',
                                vendored.read_text(encoding="utf-8"),
                                count=1, flags=_re.M),
                        encoding="utf-8", newline="\n")
    r = _sp.run([_sys.executable, str(SCRIPT), "init", "--json"],
                cwd=str(repo.root), env=repo.env, capture_output=True,
                text=True)
    payload = json.loads(r.stdout)
    assert payload["ok"] and payload["data"]["tool_copied"] is True
    assert 'TOOL_VERSION = "0.0.1"' not in vendored.read_text(encoding="utf-8")
    assert repo.j("doctor")["data"]["vendored_tool_version"] != "0.0.1"
