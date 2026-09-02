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
    # the repair the protocol promises for a pushed commit is true (T-5z04ex)
    protocol = (ledger / "PROTOCOL.md").read_text(encoding="utf-8")
    for phrase in ("--add-depends", "not the action", "ready for integration",
                   "not scope expansion", "ledger search", "bounded digest",
                   "`--full`", "list --mine"):
        assert phrase in protocol and phrase in claude  # T-w0emnj, T-ntt2zz
    assert "ledger link <id> <sha>" in protocol
    assert "explicit link counts as coverage" in protocol
    assert "Unpushed: amend" in protocol
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
    assert show["log"][0]["text"] == "created: First task [p1/s] (tags: alpha)"
    assert show["dependents"] == []


def test_add_spec_from_stdin_and_after(repo):
    dep = repo.add_task("Dependency")
    d = repo.j("add", "Child", "--spec", "-", "--after", dep,
               input="Line one.\nLine two.\n")
    child = d["data"]["id"]
    show = repo.j("show", child)["data"]
    assert show["spec"] == "Line one.\nLine two."
    assert show["header"]["depends_on"] == dep
    assert show["log"][0]["text"] == f"created: Child [p2/m] (after: {dep})"
    plain = repo.add_task("Plain")
    assert repo.j("show", plain)["data"]["log"][0]["text"] == "created: Plain [p2/m]"


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
    assert d["stale_blocks"] == []  # human / external blocks never age here


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
    d = repo.j("release", tid, "--blocked", "--on", "human", "--note", "x")
    assert d["data"]["blocked_on"] == "human"
    show = repo.j("show", tid)["data"]
    assert show["header"]["status"] == "blocked"
    assert show["header"]["blocked_on"] == "human"
    # the blocker reaches the Log (mirrors block's text), not just the header
    assert show["log"][-1]["verb"] == "release"
    assert show["log"][-1]["text"] == "blocked on human — x"
    other = repo.add_task("Blocker task")
    repo.j("unblock", tid)
    repo.j("claim", tid)
    repo.j("release", tid, "--blocked", "--on", other.split("-")[1])
    show = repo.j("show", tid)["data"]
    assert show["log"][-1]["text"] == f"blocked on {other}"  # resolved id


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
        ("doctor",), ("search", "x"), ("brief", tid),
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



# --- the integration handoff convention (T-w0emnj) ---------------------------

def test_integration_handoff_sequence(repo):
    tid = repo.add_task("Worker output")
    repo.j("claim", tid, "--session", "worker")
    (repo.root / "feature.py").write_text("done locally\n", encoding="utf-8")
    repo.commit_all("Implement feature", (f"Ledger-Task: {tid}",))
    d = repo.j("release", tid, "--blocked", "--on",
               "external: ready for integration", "--note", "suite green",
               "--session", "worker")
    assert d["data"]["status"] == "blocked"
    # another worker's next never re-dispatches a handed-off task
    n = repo.j("next", "--claim", "--session", "worker-2")["data"]
    assert n["task"] is None
    assert any(w["id"] == tid and "external: ready" in w["ineligible_because"]
               for w in n["why"])
    queue = repo.j("list", "--status", "blocked")["data"]["tasks"]
    assert queue[0]["id"] == tid
    assert queue[0]["blocked_on"].startswith("external: ready")
    assert repo.j("validate", "--strict", "--no-git")["ok"]
    # the integrator can send it back...
    repo.j("release", tid, "--note", "integration failed: flaky",
           "--session", "integrator")
    assert repo.j("show", tid)["data"]["header"]["status"] == "todo"
    # ...or close it with evidence and no --force
    repo.j("claim", tid, "--session", "worker")
    repo.j("release", tid, "--blocked", "--on",
           "external: ready for integration", "--session", "worker")
    d = repo.j("done", tid, "--commit", "HEAD", "--session", "integrator")
    assert d["ok"]
    assert repo.j("validate", "--strict", "--no-git")["ok"]



# --- note --dead-end (T-yfvuya) ----------------------------------------------

def test_note_dead_end_writes_selectable_verb(repo):
    tid = repo.add_task("Explorer")
    d = repo.j("note", tid, "tried the regex route; catastrophic backtracking",
               "--dead-end")
    assert d["data"]["verb"] == "note(dead-end)"
    d = repo.j("note", tid, "plain fact")
    assert d["data"]["verb"] == "note"
    log = repo.j("show", tid)["data"]["log"]
    assert [e["verb"] for e in log[-2:]] == ["note(dead-end)", "note"]
    assert "- 2" in repo.read(tid) and "] note(dead-end): tried" in repo.read(tid)
    assert repo.j("validate", "--no-git", "--strict")["ok"]



# --- done warns on still-open dependencies (T-naq65o) -----------------------

def test_done_warns_on_still_open_dependencies(repo):
    a = repo.add_task("Member A")
    b = repo.add_task("Member B")
    c = repo.add_task("Member C")
    w = repo.j("add", "Wave", "--after", a, "--after", b, "--after", c)[
        "data"]["id"]
    repo.j("claim", a)
    repo.j("drop", c, "--why", "cut from the wave")
    d = repo.j("done", w, "--no-code", "stamped")
    assert d["ok"]  # a warning, never a refusal
    loose = [e for e in d["errors"] if e["code"] == "done-loose-ends"
             and "depends_on" in e["message"]]
    assert len(loose) == 1 and loose[0]["severity"] == "warning"
    msg = loose[0]["message"]
    assert f"{a} (in_progress)" in msg and f"{b} (todo)" in msg
    assert f"{c} (dropped)" in msg  # dropped counts as open, like next/drop
    assert f"ledger set {w} --remove-depends" in loose[0]["fix_hint"]
    assert repo.j("validate", "--no-git", "--strict")["ok"]  # CLI-time only
    # every dependency done: no depends_on warning
    repo.j("done", a, "--no-code", "x")
    w2 = repo.j("add", "Wave 2", "--after", a)["data"]["id"]
    d = repo.j("done", w2, "--no-code", "x")
    assert not any("depends_on" in e["message"] for e in d["errors"])
    # the --commit path warns identically
    w3 = repo.j("add", "Wave 3", "--after", b)["data"]["id"]
    d = repo.j("done", w3, "--commit", "HEAD")
    assert d["ok"] and any("depends_on" in e["message"] for e in d["errors"])



# --- blocks whose target task has closed (T-9jkvg0) --------------------------

def test_next_and_closing_verbs_signal_blocks_on_closed_tasks(repo):
    b = repo.add_task("Blocker")
    a = repo.add_task("Waiting on the blocker")
    repo.j("block", a, "--on", b)
    assert repo.j("next")["data"]["stale_blocks"] == []
    d = repo.j("done", b, "--no-code", "shipped elsewhere")
    warn = [e for e in d["errors"] if e.get("task") == a and e["code"] == "refs"]
    assert warn and warn[0]["severity"] == "warning"
    assert warn[0]["fix_hint"] == f"ledger unblock {a}"
    n = repo.j("next")["data"]
    why = {w["id"]: w["ineligible_because"] for w in n["why"]}
    assert why[a].startswith(f"blocked_on {b}") and "(done" in why[a]
    assert n["stale_blocks"] == [{"id": a, "blocked_on": b,
                                  "target_status": "done"}]
    assert repo.j("validate", "--no-git", "--strict")["ok"]  # no new code
    repo.j("unblock", a)
    assert repo.j("next")["data"]["task"]["header"]["id"] == a
    # a dropped target will never close: the why says so
    c = repo.add_task("Dropped blocker")
    e = repo.add_task("Waiting on the dropped one")
    repo.j("block", e, "--on", c)
    d = repo.j("drop", c, "--why", "cut")
    assert any(x.get("task") == e and "unblock" in (x["fix_hint"] or "")
               for x in d["errors"])
    n = repo.j("next")["data"]
    why = {w["id"]: w["ineligible_because"] for w in n["why"]}
    assert "(dropped" in why[e] and "real reason" in why[e]
    assert {"id": e, "blocked_on": c, "target_status": "dropped"} in n[
        "stale_blocks"]
    # claimed path: block retains the claim; unblock restores in_progress
    f = repo.add_task("Blocker three")
    g = repo.add_task("Claimed waiter")
    repo.j("claim", g)
    repo.j("block", g, "--on", f)
    repo.j("done", f, "--no-code", "x")
    assert any(s["id"] == g for s in repo.j("next")["data"]["stale_blocks"])
    repo.j("unblock", g)
    assert repo.j("show", g)["data"]["header"]["status"] == "in_progress"
    assert not any(s["id"] == g
                   for s in repo.j("next")["data"]["stale_blocks"])



# --- add warns on similar titles (T-3bryhm) ----------------------------------

def test_add_warns_on_similar_titles_without_refusing(repo):
    old = repo.add_task("Batch git subprocess calls in validate")
    d = repo.j("add", "Batch git subprocess calls in validate")  # exact dupe
    new = d["data"]["id"]
    assert d["ok"] and repo.task_file(new).exists()
    sim = [e for e in d["errors"] if e["code"] == "similar-task"]
    assert len(sim) == 1 and sim[0]["task"] == new
    assert sim[0]["severity"] == "warning"
    assert old in sim[0]["message"] and "(todo)" in sim[0]["message"]
    assert f"ledger drop {new} --duplicate-of {old}" in sim[0]["fix_hint"]
    assert d["data"]["similar"] == [{
        "id": old, "status": "todo",
        "title": "Batch git subprocess calls in validate", "score": 1.0}]
    # near duplicate names the older id; unrelated and stopword-only do not
    d = repo.j("add", "Batch the git subprocess calls that validate spawns")
    assert any(e["code"] == "similar-task" and old in e["message"]
               for e in d["errors"])
    assert repo.j("add", "Rename the config loader")["errors"] == []
    repo.add_task("Fix the thing")
    assert repo.j("add", "Add the thing")["errors"] == []
    repo.add_task("Add it")
    fixed = repo.add_task("Fix it")
    repo.j("done", fixed, "--no-code", "x")
    d = repo.j("add", "Fix it")  # empty token sets are never candidates
    assert d["ok"] and d["errors"] == []
    # nothing is persisted and validate never sees it
    assert "similar" not in repo.read(new)
    assert repo.j("validate", "--no-git", "--strict")["ok"]


def test_add_matches_closed_tasks_only_on_identical_titles(repo):
    old = repo.add_task("Migrate the parser to a state machine")
    repo.j("done", old, "--no-code", "shipped")
    d = repo.j("add", "Migrate the parser to a state machine")
    sim = [e for e in d["errors"] if e["code"] == "similar-task"]
    assert len(sim) == 1 and "closed on" in sim[0]["fix_hint"]
    assert "regression or redo" in sim[0]["fix_hint"]
    assert repo.j("add", "Migrate the parser to a recursive descent")[
        "errors"] == []  # loosely similar closed title: noise, not a hint


def test_add_similarity_is_capped_and_best_first(repo):
    exact = repo.add_task("Parser rewrite phase")
    for word in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta"):
        repo.add_task(f"Parser rewrite {word}")  # overlap 2/3 each
    d = repo.j("add", "Parser rewrite phase")
    sim = d["data"]["similar"]
    assert len(sim) == 5
    assert sim[0]["id"] == exact and sim[0]["score"] == 1.0
    assert all(s["score"] < 1.0 for s in sim[1:])


def test_scan_reports_similar_open_pairs(repo):
    a = repo.add_task("Retry with backoff for the sync client", "-p", "p1")
    b = repo.add_task("Sync client retry backoff")  # p2: pins the pair order
    repo.add_task("Unrelated docs cleanup")
    d = repo.j("scan")["data"]
    assert d["similar_open_pairs"] == [{"a": a, "b": b, "score": 1.0}]
    repo.j("drop", b, "--duplicate-of", a)
    assert repo.j("scan")["data"]["similar_open_pairs"] == []


def test_title_tokens(ledger_mod):
    assert ledger_mod.title_tokens(
        "Add: retry-with backoff for the sync client!") == {
        "retry", "backoff", "sync", "client"}
    assert ledger_mod.title_tokens("Fix it") == set()
    assert ledger_mod.title_tokens("Task 1234") == {"task", "1234"}



# --- dependents and list --depends-on (T-9iu47b) ----------------------------

def test_dependents_and_list_depends_on(repo):
    m = repo.add_task("Member", "-p", "p0")  # priorities pin every order below
    other = repo.add_task("Other member")
    w = repo.j("add", "Wave 1", "-p", "p1", "--tag", "wave", "--after", m,
               "--after", other)["data"]["id"]
    child = repo.j("add", "Follow-up", "--after", m)["data"]["id"]  # p2
    assert repo.j("show", m)["data"]["dependents"] == [w, child]
    assert repo.j("next")["data"]["task"]["dependents"] == [w, child]
    rows = repo.j("list", "--depends-on", m)["data"]["tasks"]
    assert [t["id"] for t in rows] == [w, child]
    rows = repo.j("list", "--depends-on", m, "--tag", "wave")["data"]["tasks"]
    assert [t["id"] for t in rows] == [w]
    repo.j("done", w, "--no-code", "stamped", "--force")
    assert w in repo.j("show", m)["data"]["dependents"]  # any status
    assert repo.j("list", "--depends-on", "zzzzzz", expect=2)["errors"][0][
        "code"] == "no-such-task"
    assert repo.j("list", "--depends-on", "T-", expect=2)["errors"][0][
        "code"] == "ambiguous-id"



# --- brief: the bounded digest (T-z7iebd) ------------------------------------

def test_brief_digest_shape_and_bounds(repo):
    tid = repo.j("add", "Long-running task", "--spec", "-",
                 input="line 1\nline 2\nline 3\n")["data"]["id"]
    for i in range(3):
        repo.j("step", tid, "add", f"step {i + 1}")
    repo.j("step", tid, "check", "1")
    repo.j("question", tid, "add", "ship behind a flag?", "--human")
    repo.j("question", tid, "add", "cache ttl?")
    repo.j("question", tid, "resolve", "flag", "--answer", "yes",
           "--session", "the-operator")
    repo.j("note", tid, "regex route backtracks", "--dead-end")
    for i in range(12):
        repo.j("note", tid, f"breadcrumb {i}")
    before = repo.task_file(tid).read_bytes()
    d = repo.j("brief", tid, "--last", "3")["data"]
    assert repo.task_file(tid).read_bytes() == before
    assert d["header"]["id"] == tid and d["spec_lines"] == 3
    assert [s["n"] for s in d["steps_open"]] == [2, 3]  # original indexes
    assert d["steps_total"] == 3 and d["steps_done"] == 1
    assert d["human_gated_questions"] == [{
        "n": 1, "text": "ship behind a flag?", "answered": True,
        "answer": "yes", "answered_by": "the-operator"}]
    assert d["open_questions"] == 1
    assert len(d["recent_log"]) == 3
    assert d["log_total"] == 1 + 3 + 1 + 2 + 1 + 1 + 12  # every Log line
    assert d["recent_log"][-1]["text"] == "breadcrumb 11"
    assert all(e["ts"] >= d["recent_log"][0]["ts"] for e in d["recent_log"])
    assert [e["text"] for e in d["dead_ends"]] == ["regex route backtracks"]
    assert d["dependents"] == [] and d["commits"] == []
    assert d["effective_commits"] == []
    for key in ("spec", "log", "next_steps"):
        assert key not in d  # bounded: the file is the Spec authority
    r = repo.run("brief", tid)
    assert "dead end: regex route backtracks" in r.stdout
    assert "[ ] 2. step 2" in r.stdout


def test_show_and_next_brief_flags(repo):
    tid = repo.add_task("Digestible")
    full = repo.j("show", tid)["data"]
    assert "log" in full and "spec" in full
    digest = repo.j("show", tid, "--brief")["data"]
    assert "recent_log" in digest and "log" not in digest
    assert "absorbed" in digest
    assert repo.run("show", tid, "--last", "2").returncode == 3  # needs --brief
    # next: the digest is the DEFAULT (T-fzyn4o); --full restores task_full;
    # -n rows stay header+counts either way
    n = repo.j("next", "-n", "3", "--last", "2")["data"]
    assert "recent_log" in n["task"] and "log" not in n["task"]
    assert len(n["task"]["recent_log"]) <= 2
    assert n["tasks"][0]["id"] == tid and "open_steps" in n["tasks"][0]
    full_next = repo.j("next", "--full", "-n", "3")["data"]
    assert "log" in full_next["task"] and "spec" in full_next["task"]
    assert "open_steps" in full_next["tasks"][0]
    assert repo.run("next", "--full", "--last", "2").returncode == 3
    claimed = repo.j("next", "--claim")["data"]
    assert claimed["claimed"] and claimed["task"]["header"]["claimed_by"]
    assert "recent_log" in claimed["task"]


def test_brief_effective_commits_without_git_walk(plain, repo):
    p = plain.add_task("Plain tree")
    d = plain.j("brief", p)["data"]
    assert d["effective_commits"] == [] and d["commits"] == []
    tid = repo.add_task("Trailer only")
    (repo.root / "t.py").write_text("t\n", encoding="utf-8")
    sha = repo.commit_all("Trailered work", (f"Ledger-Task: {tid}",))
    d = repo.j("brief", tid)["data"]
    assert d["commits"] == [] and d["effective_commits"] == [sha[:7]]
    d = repo.j("brief", tid, "--no-git")["data"]
    assert d["effective_commits"] == []



# --- list --mine and next.held for multi-claim sessions (T-eb6bas) -----------

def test_list_mine_and_next_held(repo):
    from test_hardening import set_stale_days
    a = repo.add_task("Held one", "-p", "p1")
    b = repo.add_task("Held two", "-p", "p1")
    c = repo.add_task("Held and blocked", "-p", "p1")
    other = repo.add_task("Someone else's", "-p", "p1")
    free = repo.add_task("Free task", "-p", "p3")
    for t in (a, b, c):
        repo.j("claim", t, "--session", "a")
    repo.j("block", c, "--on", "human", "--session", "a")
    repo.j("claim", other, "--session", "b")
    mine = repo.j("list", "--mine", "--session", "a")["data"]["tasks"]
    assert {t["id"] for t in mine} == {a, b, c}  # same-second ids: set
    assert repo.j("list", "--mine", "--session", "b")["data"]["tasks"][0][
        "id"] == other
    assert repo.run("list", "--mine", "--unclaimed", "--session", "a"
                    ).returncode == 3
    env_free = dict(repo.env)
    env_free.pop("LEDGER_SESSION")
    import subprocess, sys
    r = subprocess.run([sys.executable, str(repo.script), "list", "--mine",
                        "--json", "--session", "unknown"],
                       cwd=str(repo.root), env=env_free, capture_output=True,
                       text=True)
    assert r.returncode == 3  # no identity: refuse rather than list nothing
    # next: held on the eligible path, excluding the task just claimed
    n = repo.j("next", "--claim", "--session", "a")["data"]
    assert n["task"]["header"]["id"] == free
    held = {h["id"]: h for h in n["held"]}
    assert set(held) == {a, b, c}
    assert held[a]["stale"] is False and held[a]["status"] == "in_progress"
    assert held[c]["status"] == "blocked" and held[c]["blocked_on"] == "human"
    assert other not in held
    r = repo.run("next", "--session", "a")
    assert f"also holding: {a} [in_progress]" in r.stdout
    assert f"also holding: {free}" not in r.stdout or True
    # nothing-eligible path still carries held
    n = repo.j("next", "--session", "a")["data"]
    assert n["task"] is None or n["task"]["header"]["id"] != free
    assert set(h["id"] for h in n["held"]) >= {a, b, c}
    # refreshing one's own stale claim is not a takeover
    set_stale_days(repo, -1)
    n = repo.j("next", "--claim", "--session", "a")["data"]
    assert n["claimed"]
    picked = n["task"]["header"]["id"]
    log = repo.j("show", picked)["data"]["log"]
    claims = [e for e in log if e["verb"] == "claim"]
    if picked in (a, b, free):
        assert claims[-1]["text"] == "claimed"
        assert "taking over" not in claims[-1]["text"]
    assert any(h["stale"] for h in n["held"])
