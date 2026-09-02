"""CLI contract tests: envelope shape, exit codes, lifecycle verbs."""
import json
import re


def test_init_idempotent_and_bootstrap_files(repo):
    d = repo.j("init")
    assert d["ok"] and d["data"]["created"] is False  # second run: no reset
    ledger = repo.root / ".ledger"
    assert (ledger / "ledger.py").exists()
    assert (ledger / "PROTOCOL.md").exists()
    assert (ledger / "tasks").is_dir()
    cfg = json.loads((ledger / "config.json").read_text(encoding="utf-8"))
    assert cfg["prefix"] == "T" and cfg["baseline"]
    ga = (repo.root / ".gitattributes").read_text(encoding="utf-8")
    assert ".ledger/** text eol=lf" in ga
    claude = (repo.root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- LEDGER:BEGIN -->" in claude and "<!-- LEDGER:END -->" in claude
    assert "Ledger protocol" in claude
    # re-init must not duplicate the protocol block or gitattributes line
    repo.j("init")
    claude2 = (repo.root / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude2.count("<!-- LEDGER:BEGIN -->") == 1
    ga2 = (repo.root / ".gitattributes").read_text(encoding="utf-8")
    assert ga2.count(".ledger/** text eol=lf") == 1


def test_add_show_shapes(repo):
    d = repo.j("add", "First task", "-p", "p1", "-s", "s", "--tag", "alpha")
    tid = d["data"]["id"]
    assert re.fullmatch(r"T-[a-z0-9]{6}", tid)
    assert repo.task_file(tid).exists()
    assert set(d.keys()) == {"ok", "data", "errors"}

    show = repo.j("show", tid)["data"]
    for key in ("header", "spec", "next_steps", "open_questions", "commits",
                "log", "effective_commits", "last_activity", "path"):
        assert key in show
    assert show["header"]["status"] == "todo"
    assert show["header"]["priority"] == "p1"
    assert show["header"]["tags"] == "alpha"
    assert show["log"][0]["verb"] == "add"
    assert show["log"][0]["actor"] == "test-session"


def test_add_spec_from_stdin_and_after(repo):
    dep = repo.add_task("Dependency")
    d = repo.j("add", "Child", "--spec", "-", "--after", dep,
               input="Line one.\nLine two.\n")
    child = d["data"]["id"]
    show = repo.j("show", child)["data"]
    assert show["spec"] == "Line one.\nLine two."
    assert show["header"]["depends_on"] == dep


def test_list_filters_and_sort(repo):
    low = repo.add_task("Low priority", "-p", "p3")
    high = repo.add_task("High priority", "-p", "p0")
    mid = repo.add_task("Mid priority", "-p", "p2")
    tasks = repo.j("list")["data"]["tasks"]
    assert [t["id"] for t in tasks] == [high, mid, low]
    only_p0 = repo.j("list", "--priority", "p0")["data"]["tasks"]
    assert [t["id"] for t in only_p0] == [high]
    repo.j("claim", high)
    assert [t["id"] for t in repo.j("list", "--claimed")["data"]["tasks"]] == [high]
    unclaimed = {t["id"] for t in repo.j("list", "--unclaimed")["data"]["tasks"]}
    assert unclaimed == {low, mid}
    assert repo.j("list", "--status", "in_progress")["data"]["tasks"][0]["id"] == high


def test_next_prioritizes_and_explains(repo):
    xl = repo.add_task("Huge refactor", "-p", "p0", "-s", "xl")
    dep = repo.add_task("Foundation", "-p", "p1")
    child = repo.j("add", "Dependent work", "-p", "p0", "--after", dep)["data"]["id"]
    d = repo.j("next")["data"]
    # xl is skipped, child is dep-gated, so the p1 foundation wins
    assert d["task"]["header"]["id"] == dep
    why = {w["id"]: w["ineligible_because"] for w in d["why"]}
    assert "split" in why[xl]
    assert dep in why[child] and "depends_on" in why[child]


def test_next_claim_and_exhaustion(repo):
    tid = repo.add_task("Only task")
    d = repo.j("next", "--claim")["data"]
    assert d["claimed"] and d["task"]["header"]["claimed_by"] == "test-session"
    d2 = repo.j("next")["data"]
    assert d2["task"] is None
    assert any(w["id"] == tid and "claimed by" in w["ineligible_because"]
               for w in d2["why"])


def test_next_reports_human_blockage(repo):
    tid = repo.add_task("Needs a decision")
    repo.j("block", tid, "--on", "human", "--why", "which vendor?")
    d = repo.j("next")["data"]
    assert d["task"] is None
    assert d["blocked_on_human"][0]["id"] == tid


def test_claim_contention_and_force(repo):
    tid = repo.add_task("Contested")
    repo.j("claim", tid)
    other = repo.j("claim", tid, "--session", "other-session", expect=2)
    assert other["errors"][0]["code"] == "claim-held"
    forced = repo.j("claim", tid, "--session", "other-session", "--force")
    assert forced["ok"]
    show = repo.j("show", tid)["data"]
    assert show["header"]["claimed_by"] == "other-session"
    assert any("taking over" in e["text"] for e in show["log"])


def test_release_handoff(repo):
    tid = repo.add_task("Handoff")
    repo.j("claim", tid)
    repo.j("release", tid, "--note", "stopped at parser")
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "todo"
    assert "claimed_by" not in show["header"]
    assert any(e["verb"] == "release" and "stopped at parser" in e["text"]
               for e in show["log"])
    repo.j("claim", tid)
    repo.j("release", tid, "--blocked", "--on", "human")
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "blocked"
    assert show["header"]["blocked_on"] == "human"


def test_block_unblock_preserves_claim(repo):
    tid = repo.add_task("Blocky")
    repo.j("claim", tid)
    repo.j("block", tid, "--on", "external: waiting on API key")
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "blocked"
    assert show["header"]["blocked_on"] == "external: waiting on API key"
    repo.j("unblock", tid)
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "in_progress"  # claim was kept


def test_set_fields_and_log_trail(repo):
    a = repo.add_task("Alpha")
    b = repo.add_task("Beta")
    d = repo.j("set", a, "--priority", "p0", "--size", "l",
               "--add-depends", b, "--add-tag", "core")
    assert len(d["data"]["changes"]) == 4
    show = repo.j("show", a)["data"]
    assert show["header"]["priority"] == "p0"
    assert show["header"]["depends_on"] == b
    set_logs = [e for e in show["log"] if e["verb"] == "set"]
    assert any("priority p2 -> p0" in e["text"] for e in set_logs)
    repo.j("set", a, "--remove-depends", b, "--remove-tag", "core")
    show = repo.j("show", a)["data"]
    assert "depends_on" not in show["header"] and "tags" not in show["header"]
    assert repo.j("set", a, "--add-depends", a, expect=2)["errors"][0]["code"] == "refs"
    assert repo.run("set", a).returncode == 3  # nothing to change


def test_steps_by_index_and_substring(repo):
    tid = repo.add_task("Steppy")
    repo.j("step", tid, "add", "write the parser")
    repo.j("step", tid, "add", "write the serializer")
    repo.j("step", tid, "check", "1")
    steps = repo.j("show", tid)["data"]["next_steps"]
    assert steps[0]["done"] and not steps[1]["done"]
    repo.j("step", tid, "check", "serializer")
    steps = repo.j("show", tid)["data"]["next_steps"]
    assert steps[1]["done"]
    repo.j("step", tid, "uncheck", "parser")
    steps = repo.j("show", tid)["data"]["next_steps"]
    assert not steps[0]["done"]
    amb = repo.j("step", tid, "check", "write the", expect=2)
    assert amb["errors"][0]["code"] == "ambiguous-selector"
    missing = repo.j("step", tid, "check", "no such step text", expect=2)
    assert missing["errors"][0]["code"] == "no-such-step"


def test_questions_lifecycle_and_dashboard(repo):
    a = repo.add_task("Ask things")
    repo.j("question", a, "add", "cache TTL value?")
    repo.j("question", a, "add", "which vendor do we pick?", "--human")
    qs = repo.j("questions")["data"]["questions"]
    assert len(qs) == 2
    human_only = repo.j("questions", "--human")["data"]["questions"]
    assert len(human_only) == 1 and human_only[0]["human"]
    assert human_only[0]["text"] == "which vendor do we pick?"

    repo.j("question", a, "resolve", "TTL", "--answer", "60 seconds")
    qs = repo.j("show", a)["data"]["open_questions"]
    assert qs[0]["answered"] and qs[0]["answer"] == "60 seconds"
    assert repo.run("question", a, "resolve", "vendor").returncode == 3  # no --answer
    # answered questions never resurface on the dashboard
    assert len(repo.j("questions")["data"]["questions"]) == 1


def test_done_requires_evidence(repo):
    tid = repo.add_task("Evidenceless")
    repo.j("claim", tid)
    refused = repo.j("done", tid, expect=2)
    assert refused["ok"] is False
    assert refused["errors"][0]["code"] == "done-evidence"
    assert refused["errors"][0]["fix_hint"]
    ok = repo.j("done", tid, "--no-code", "config-only change, no commit needed")
    assert ok["ok"]
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "done"
    assert "closed" in show["header"] and "claimed_by" not in show["header"]
    assert any(e["verb"] == "done(no-code)" for e in show["log"])


def test_done_blocked_by_human_question(repo):
    tid = repo.add_task("Questionable")
    repo.j("claim", tid)
    repo.j("question", tid, "add", "ship behind a flag?", "--human")
    refused = repo.j("done", tid, "--no-code", "n/a", expect=2)
    assert any(e["code"] == "done-human-questions" for e in refused["errors"])
    repo.j("question", tid, "resolve", "flag", "--answer", "yes, flag it")
    assert repo.j("done", tid, "--no-code", "n/a")["ok"]


def test_done_force_overrides_human_question(repo):
    tid = repo.add_task("Moot")
    repo.j("question", tid, "add", "moot question?", "--human")
    ok = repo.j("done", tid, "--no-code", "obsoleted", "--force")
    assert ok["ok"]


def test_done_warns_on_loose_ends(repo):
    tid = repo.add_task("Loose")
    repo.j("step", tid, "add", "never finished")
    d = repo.j("done", tid, "--no-code", "abandoned half-way on purpose")
    assert d["ok"]
    assert any(e["code"] == "done-loose-ends" and e["severity"] == "warning"
               for e in d["errors"])


def test_drop_and_closed_states_refuse_verbs(repo):
    tid = repo.add_task("Droppable")
    assert repo.run("drop", tid).returncode == 3  # --why is required
    repo.j("drop", tid, "--why", "superseded by new design")
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "dropped" and "closed" in show["header"]
    assert repo.j("claim", tid, expect=2)["errors"][0]["code"] == "bad-state"
    assert repo.j("drop", tid, "--why", "again", expect=2)["errors"][0]["code"] == "bad-state"
    assert repo.j("done", tid, expect=2)["errors"][0]["code"] == "bad-state"


def test_id_fragment_resolution(repo):
    tid = repo.add_task("Fragment target")
    other = repo.add_task("Decoy")
    frag = tid.split("-")[1]
    assert repo.j("show", frag)["data"]["header"]["id"] == tid
    assert repo.j("show", tid.upper())["data"]["header"]["id"] == tid
    missing = repo.j("show", "zzzzzz9", expect=2)
    assert missing["errors"][0]["code"] == "no-such-task"
    amb = repo.j("show", "T-", expect=2)  # matches both tasks
    assert amb["errors"][0]["code"] == "ambiguous-id"
    assert tid in amb["errors"][0]["message"] and other in amb["errors"][0]["message"]


def test_usage_errors_exit_3(repo):
    assert repo.run("add", "Bad prio", "-p", "p9").returncode == 3
    assert repo.run("frobnicate").returncode == 3
    assert repo.run("add").returncode == 3


def test_not_initialized_is_a_refusal(tmp_path, base_env):
    from conftest import LedgerRepo, _isolated_env
    lr = LedgerRepo(tmp_path / "bare", _isolated_env(base_env, tmp_path))
    lr.root.mkdir()
    d = lr.j("list", expect=2)
    assert d["errors"][0]["code"] == "not-initialized"


def test_files_are_lf_only_utf8(repo):
    tid = repo.add_task("Unicode naïve — check")
    repo.j("note", tid, "line one\r\nline two")
    raw = repo.task_file(tid).read_bytes()
    assert b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    text = repo.read(tid)
    assert "line one; line two" in text  # newlines sanitized in log lines


def test_every_command_emits_envelope(repo):
    tid = repo.add_task("Envelope")
    calls = [
        ("list",), ("show", tid), ("next",), ("questions",),
        ("note", tid, "x"), ("step", tid, "add", "s"),
        ("question", tid, "add", "q?"), ("claim", tid), ("release", tid),
        ("block", tid, "--on", "human"), ("unblock", tid),
        ("set", tid, "--priority", "p1"), ("scan",), ("validate",),
        ("doctor",),
    ]
    for call in calls:
        r = repo.run(*call, "--json")
        payload = json.loads(r.stdout)
        assert set(payload.keys()) == {"ok", "data", "errors"}, call


# --- drop relations (T-71aehi) ----------------------------------------------

def test_drop_duplicate_of_records_machine_visible_relation(repo):
    survivor = repo.add_task("Canonical work")
    dupe = repo.add_task("Same work filed twice")
    d = repo.j("drop", dupe, "--duplicate-of", survivor, "--why", "same thing")
    assert d["ok"]
    assert d["data"]["closed_relation"] == {"kind": "duplicate",
                                            "target": survivor}
    text = repo.read(dupe)
    assert f"drop: duplicate-of {survivor} — same thing" in text
    show = repo.j("show", dupe)["data"]
    assert show["header"]["status"] == "dropped"
    assert show["closed_relation"] == {"kind": "duplicate", "target": survivor}
    # the reverse view is derived on read; the survivor's file was not written
    assert repo.j("show", survivor)["data"]["absorbed"] == [
        {"id": dupe, "kind": "duplicate"}]
    assert "drop" not in repo.read(survivor)
    rows = repo.j("list", "--status", "dropped")["data"]["tasks"]
    assert rows[0]["closed_relation"]["target"] == survivor
    assert repo.j("validate", "--no-git", "--strict")["ok"]


def test_drop_superseded_by_without_why(repo):
    old = repo.add_task("Old approach")
    new = repo.add_task("New approach")
    d = repo.j("drop", old, "--superseded-by", new)
    assert d["data"]["closed_relation"] == {"kind": "superseded", "target": new}
    assert f"drop: superseded-by {new}\n" in repo.read(old)
    r = repo.run("drop", repo.add_task("Human readable"), "--superseded-by",
                 new)
    assert "as superseded by" in r.stdout


def test_drop_relation_refusals_leave_files_untouched(repo):
    a = repo.add_task("Alpha")
    b = repo.add_task("Beta")
    gone = repo.add_task("Already dropped")
    repo.j("drop", gone, "--why", "gone")
    before = repo.read(a)
    both = repo.j("drop", a, "--duplicate-of", b, "--superseded-by", b,
                  expect=3)
    assert both["errors"][0]["code"] == "usage"
    assert repo.run("drop", a).returncode == 3  # neither --why nor a relation
    assert repo.j("drop", a, "--duplicate-of", a, expect=2)["errors"][0][
        "code"] == "refs"
    dropped_target = repo.j("drop", a, "--duplicate-of", gone, expect=2)
    assert dropped_target["errors"][0]["code"] == "bad-state"
    assert "survivor" in dropped_target["errors"][0]["fix_hint"]
    assert repo.j("drop", a, "--duplicate-of", "zzzzzz", expect=2)["errors"][
        0]["code"] == "no-such-task"
    assert repo.j("drop", a, "--duplicate-of", "T-", expect=2)["errors"][0][
        "code"] == "ambiguous-id"
    hand_typed = repo.j("drop", a, "--why", f"duplicate-of {b} — typed",
                        expect=2)
    assert hand_typed["errors"][0]["code"] == "refs"
    assert repo.read(a) == before  # every refusal happened before any write
    # a done target is a legitimate survivor
    repo.j("done", b, "--no-code", "finished")
    assert repo.j("drop", a, "--duplicate-of", b)["ok"]


def test_drop_why_with_newlines_still_parses_relation(repo):
    survivor = repo.add_task("Survivor")
    dupe = repo.add_task("Dupe")
    repo.j("drop", dupe, "--duplicate-of", survivor, "--why",
           "line one\nline two")
    rel = repo.j("show", dupe)["data"]["closed_relation"]
    assert rel == {"kind": "duplicate", "target": survivor}
    assert "line one; line two" in repo.read(dupe)
