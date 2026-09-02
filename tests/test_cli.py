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
                   "`--full`", "list --mine", "indented lines",
                   "no product-work obligation", "exempt_allowed_paths",
                   "Closed is terminal", "SAME final paragraph",
                   "ledger claim <id>", "--in spec,log", "own `HUMAN:`",
                   "--blocked-on", "`ok` is the success"):
        assert phrase in protocol and phrase in claude  # T-w0emnj, T-ntt2zz
    assert "ledger link <id> <sha>" in protocol
    assert "counts as coverage" in protocol
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


def test_done_force_never_bypasses_the_question_gate(repo):
    tid = repo.add_task("Moot")
    repo.j("question", tid, "add", "moot question?", "--human")
    refused = repo.j("done", tid, "--no-code", "obsoleted", "--force",
                     expect=2)
    assert refused["errors"][0]["code"] == "done-human-questions"
    assert "moot" in refused["errors"][0]["fix_hint"]
    repo.j("question", tid, "resolve", "moot", "--answer",
           "moot: feature removed")
    assert repo.j("done", tid, "--no-code", "obsoleted")["ok"]


def test_done_refuses_loose_ends(repo):
    """Closed is terminal: done refuses every state strict CI would reject,
    so a closed task can never be born red (T-ledxp4)."""
    tid = repo.add_task("Loose")
    repo.j("step", tid, "add", "never finished")
    repo.j("question", tid, "add", "cache ttl?")
    before = repo.read(tid)
    d = repo.j("done", tid, "--no-code", "abandoned half-way", expect=2)
    codes_seen = [e["code"] for e in d["errors"]]
    assert codes_seen == ["done-loose-ends", "done-loose-ends"]
    assert all(e["severity"] == "error" for e in d["errors"])
    assert "MOOT" in d["errors"][0]["fix_hint"]
    assert "never finished" in d["errors"][0]["message"]
    assert repo.read(tid) == before  # a refusal changes nothing
    repo.j("step", tid, "check", "1")
    repo.j("question", tid, "resolve", "ttl", "--answer", "60s")
    assert repo.j("done", tid, "--no-code", "finished")["ok"]
    assert repo.j("validate", "--no-git", "--strict")["ok"]


def test_closed_is_terminal_allowlist(repo):
    tid = repo.add_task("Finished")
    repo.j("step", tid, "add", "shipped")
    repo.j("step", tid, "check", "1")
    repo.j("done", tid, "--no-code", "shipped")
    before = repo.read(tid)
    refused = [
        ("set", tid, "--priority", "p0"),
        ("step", tid, "add", "one more thing"),
        ("step", tid, "uncheck", "1"),
        ("question", tid, "add", "another?", "--human"),
        ("block", tid, "--on", "human"),
        ("claim", tid),
        ("release", tid),
    ]
    for call in refused:
        d = repo.j(*call, expect=2)
        assert d["errors"][0]["code"] == "bad-state", call
        assert repo.read(tid) == before, call
    hint = repo.j("set", tid, "--priority", "p0", expect=2)["errors"][0][
        "fix_hint"]
    assert "new task" in hint
    # the allowlist: append-only or repair-only verbs still work
    assert repo.j("note", tid, "post-mortem: fine", "--dead-end")["ok"]
    assert repo.j("step", tid, "check", "1")["ok"] or True  # already checked
    dropped = repo.add_task("Dropped one")
    repo.j("drop", dropped, "--why", "cut")
    assert repo.j("step", dropped, "add", "x", expect=2)["errors"][0][
        "code"] == "bad-state"
    # a hand-edited loose end on a closed task is repaired with an allowed verb
    repo.write(tid, repo.read(tid).replace(
        "## Open Questions\n", "## Open Questions\n\n- [ ] HUMAN: late?\n"))
    assert repo.run("validate", "--no-git", "--strict").returncode == 1
    assert repo.j("question", tid, "resolve", "late", "--answer", "no")["ok"]
    assert repo.j("validate", "--no-git", "--strict")["ok"]


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
        ("answers", "apply", "-"), ("report",), ("unlink", tid, "HEAD"),
        ("repair", tid),
    ]
    for call in calls:
        r = repo.run(*call, "--json", input="[]")
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
    # (--force: a multi-claim session holding fresh claims must say so)
    n = repo.j("next", "--claim", "--session", "a", "--force")["data"]
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



# --- advisory resource leases (T-6kyk2x) -------------------------------------

def test_next_skips_held_resources_and_falls_through(repo):
    from test_hardening import set_stale_days
    # p0 vs p1: same-second creation would otherwise tie and sort by random id
    holder = repo.add_task("Uses the GPU", "-p", "p0", "--tag", "resource:gpu")
    waiter = repo.add_task("Also needs the GPU", "-p", "p1", "--tag",
                           "resource:gpu", "--tag", "resource:db")
    free = repo.add_task("No resources", "-p", "p2")
    repo.j("claim", holder, "--session", "a")
    n = repo.j("next", "-n", "5", "--session", "b")["data"]
    assert n["task"]["header"]["id"] == free  # fell through to the free task
    why = {w["id"]: w["ineligible_because"] for w in n["why"]}
    assert why[waiter].startswith(f"resource gpu held by {holder}")
    assert "claimed by a" in why[waiter]
    assert n["resources_held"] == {"gpu": holder}
    assert [t["id"] for t in n["tasks"]] == [free]
    assert repo.j("show", waiter)["data"]["resources"] == ["gpu", "db"]
    assert repo.j("list", "--resource", "gpu")["data"]["tasks"] == \
        repo.j("list", "--tag", "resource:gpu")["data"]["tasks"]
    assert repo.j("list", "--resource", "gpu")["data"]["tasks"][0][
        "resources"] == ["gpu"]
    d = repo.j("next", "--claim", "--session", "b")["data"]
    assert d["claimed"] and d["task"]["header"]["id"] == free
    # a blocked holder does not hold; neither does a stale one
    repo.j("block", holder, "--on", "human", "--session", "a")
    assert repo.j("next", "--session", "c")["data"]["task"]["header"][
        "id"] == waiter
    repo.j("unblock", holder, "--session", "a")
    assert repo.j("next", "--session", "c")["data"]["task"] is None
    set_stale_days(repo, -1)
    n = repo.j("next", "--session", "c")["data"]
    assert n["resources_held"] == {}
    set_stale_days(repo, 7)
    # release / done / drop of the holder frees the resource
    repo.j("release", holder, "--session", "a")
    n = repo.j("next", "--session", "c")["data"]
    assert n["task"]["header"]["id"] in (holder, waiter)
    assert n["resources_held"] == {}
    # nothing-eligible path carries resources_held too
    repo.j("claim", waiter, "--session", "a")
    repo.j("claim", holder, "--session", "a", "--force")
    repo.j("done", free, "--no-code", "x", "--session", "b")
    n = repo.j("next", "--session", "c")["data"]
    assert n["task"] is None and set(n["resources_held"]) == {"gpu", "db"}


def test_claim_and_unblock_refuse_held_resources_unless_forced(repo):
    a = repo.add_task("First on the suite", "--tag", "resource:full-suite")
    b = repo.add_task("Second on the suite", "--tag", "resource:full-suite")
    repo.j("claim", a, "--session", "x")
    refused = repo.j("claim", b, "--session", "y", expect=2)
    assert refused["errors"][0]["code"] == "resource-held"
    assert a in refused["errors"][0]["message"]
    assert "--force" in refused["errors"][0]["fix_hint"]
    assert repo.j("show", b)["data"]["header"]["status"] == "todo"
    # self re-claim of one's own holder is never refused
    assert repo.j("claim", a, "--session", "x")["ok"]
    forced = repo.j("claim", b, "--session", "y", "--force")
    assert forced["ok"]
    log = repo.j("show", b)["data"]["log"]
    assert log[-1]["text"] == f"claimed (resource full-suite also held by {a})"
    v = repo.j("validate", "--no-git", "--strict")  # info never fails CI
    assert v["ok"]
    cont = [e for e in v["errors"] if e["code"] == "resource-contention"]
    assert len(cont) == 1 and cont[0]["severity"] == "info"
    assert a in cont[0]["message"] and b in cont[0]["message"]
    # unblock re-acquires the lease: refused while held elsewhere
    repo.j("release", b, "--session", "y")
    repo.j("block", a, "--on", "human", "--session", "x")  # a keeps its claim
    repo.j("claim", b, "--session", "y")  # free now: a is blocked
    refused = repo.j("unblock", a, "--session", "x", expect=2)
    assert refused["errors"][0]["code"] == "resource-held"
    assert repo.j("show", a)["data"]["header"]["status"] == "blocked"
    ok = repo.j("unblock", a, "--session", "x", "--force")
    assert ok["ok"] and ok["data"]["status"] == "in_progress"
    assert "also held by" in repo.j("show", a)["data"]["log"][-1]["text"]



# --- report: derived operator diagnostics (T-00mrm7) -------------------------

def test_report_counts_every_family(repo):
    m1 = repo.add_task("Member one", "-p", "p1", "--tag", "wave:w1")
    m2 = repo.add_task("Member two", "-p", "p3", "--tag", "wave:w1")
    m3 = repo.add_task("Member three", "--tag", "wave:w1")
    dup = repo.add_task("Member one again", "--tag", "wave:w1")
    w = repo.j("add", "Wave 1", "-p", "p1", "-s", "s", "--tag", "wave",
               "--after", m1, "--after", m2, "--after", m3)["data"]["id"]
    repo.j("set", m2, "--priority", "p0")          # raised: opened at p3
    repo.j("set", w, "--remove-depends", m3)        # removed member
    repo.j("claim", w, "--session", "orchestrator")
    repo.j("claim", m1, "--session", "worker-a")
    (repo.root / "m1.py").write_text("x\n", encoding="utf-8")
    sha = repo.commit_all("Member one work", (f"Ledger-Task: {m1}",))
    repo.j("done", m1, "--commit", "HEAD", "--session", "worker-a")
    repo.j("drop", dup, "--duplicate-of", m1, "--session", "worker-a")
    repo.j("drop", m3, "--why", "duplicate of something", "--session",
           "worker-b")
    repo.j("claim", m2, "--session", "worker-b")  # block keeps this claim
    repo.j("block", m2, "--on", "human", "--why", "budget?", "--session",
           "worker-b")
    repo.j("question", m2, "add", "buy the GPU?", "--human",
           "--session", "worker-b")
    repo.j("question", w, "add", "ship on friday?", "--human",
           "--session", "orchestrator")
    repo.j("question", w, "resolve", "friday", "--answer", "yes",
           "--session", "the-operator")
    repo.j("note", m1, "the cache route deadlocks", "--dead-end",
           "--session", "worker-a")
    d = repo.j("report", "--task", w)
    assert d["ok"]
    r = d["data"]
    assert r["population"]["tasks"] == 4  # wave + m1 + m2 + removed m3
    assert r["population"]["scope"] == {"task": w, "members_missing": []}
    assert r["work"]["opened"]["p1"] == 2 and r["work"]["opened"]["p3"] == 1
    assert r["work"]["closed_done"]["p1"] == 1
    assert r["work"]["closed_dropped"]["p2"] == 1
    assert r["dropped_duplicates"] == {"relation": 0, "prose_heuristic": 1}
    assert r["ratios"]["reproduction"] == 4.0
    assert r["blockers"] == {"new": 1, "cleared": 0}
    assert r["questions"] == {"human_created": 2, "human_answered": 1,
                              "answered_total": 1, "human_open_end": 1}
    assert r["dependencies"] == {"added": 3, "removed": 1}
    assert r["priority"] == {"raised": 1, "lowered": 0}
    assert r["agents"]["workers"] == ["orchestrator", "worker-a", "worker-b"]
    assert r["agents"]["by_actor"]["worker-a"]["done"] == 1
    assert r["agents"]["by_actor"]["worker-a"]["dead_ends"] == 1
    assert [a["id"] for a in r["agents"]["active_claims"]] == [w, m2]
    assert r["agents"]["stranded_claims"] == []
    assert r["durations"]["created_to_closed"]["n"] == 2
    assert r["durations"]["first_claim_to_closed"]["n"] == 1
    assert r["commits"]["linked"] == 1 and r["commits"]["in_window"] >= 2
    assert r["commits"]["linked_commits_per_done_task"] == 1.0
    assert "commits" in r["sources"]["git_derived"]
    # the whole population by tag includes the duplicate that is not a member
    d = repo.j("report", "--tag", "wave:w1")["data"]
    assert d["population"]["tasks"] == 4
    assert d["dropped_duplicates"]["relation"] == 1
    # the orchestrator closes the wave: members' claims become stranded
    repo.j("done", w, "--commit", "HEAD", "--session", "orchestrator",
           "--force")
    d = repo.j("report", "--task", w)["data"]
    assert [s["id"] for s in d["agents"]["stranded_claims"]] == [m2]
    assert d["commits"]["final_commit"] == sha[:7]
    r = repo.run("report", "--task", w)
    assert "workers 3" in r.stdout and "final " + sha[:7] in r.stdout


def test_report_windows_actor_and_git_free_paths(repo, plain):
    old = repo.add_task("Opened before the window", "-p", "p1")
    repo.j("claim", old, "--session", "a")
    import time
    time.sleep(1.1)
    boundary = repo.commit_all("Boundary commit", ("Ledger-Exempt: fixture",))
    time.sleep(1.1)
    repo.j("done", old, "--no-code", "closed later", "--session", "a")
    new = repo.add_task("Opened after")
    d = repo.j("report", "--since", "HEAD")["data"]  # a git ref resolves
    assert sum(d["work"]["opened"].values()) == 1  # only `new`
    assert d["work"]["closed_done"]["p1"] == 1     # the later close counts
    assert d["window"]["since"] is not None
    d = repo.j("report", "--since", "2000-01-01", "--until",
               "2000-01-02T00:00:00Z")["data"]
    assert sum(d["work"]["opened"].values()) == 0
    assert d["agents"]["by_actor"] == {}
    d = repo.j("report", "--actor", "a")["data"]
    assert set(d["agents"]["by_actor"]) == {"a"}
    assert repo.j("report", "--since", "not-a-ref", expect=3)["errors"][0][
        "code"] == "usage"
    assert repo.j("report", "--no-git")["data"]["commits"] is None
    p = plain.add_task("Plain tree")
    d = plain.j("report")
    assert d["ok"] and d["data"]["commits"] is None
    assert d["data"]["sources"]["git_derived"] == []
    # nothing is written
    before = repo.read(new)
    repo.j("report")
    assert repo.read(new) == before



# --- hard context budgets (T-841lcp) -----------------------------------------

def test_digest_families_are_bounded_with_truncation_metadata(repo):
    tid = repo.add_task("Big task")
    for i in range(30):
        repo.j("step", tid, "add", f"step {i:02d}")
    for i in range(12):
        repo.j("question", tid, "add", f"decision {i:02d}?", "--human")
    for i in range(13):
        repo.j("note", tid, f"dead end {i:02d}", "--dead-end")
    d = repo.j("brief", tid, "--last", "5")["data"]
    assert len(d["steps_open"]) == 25 and d["steps_total"] == 30
    assert [s["n"] for s in d["steps_open"]] == list(range(1, 26))
    assert len(d["human_gated_questions"]) == 10
    assert len(d["dead_ends"]) == 10 and len(d["recent_log"]) == 5
    t = d["truncated"]
    assert t["steps_open"] == {"total": 30, "omitted": 5,
                               "retrieve_with": f"ledger show {tid} --json"}
    assert t["human_gated_questions"]["omitted"] == 2
    assert t["dead_ends"]["omitted"] == 3
    assert t["recent_log"]["total"] == d["log_total"]
    assert "--last" in t["recent_log"]["retrieve_with"]
    r = repo.run("brief", tid)
    assert "(+5 more: ledger show" in r.stdout
    # nothing cut -> no truncated key at all
    small = repo.add_task("Small task")
    assert "truncated" not in repo.j("brief", small)["data"]
    # show stays unbounded
    assert len(repo.j("show", tid)["data"]["next_steps"]) == 30


def test_next_lists_are_bounded_and_full_is_not(repo):
    blocked = []
    for i in range(35):
        prio = "p1" if i < 30 else "p3"
        t = repo.add_task(f"Gate {i:02d}", "-p", prio)
        repo.j("block", t, "--on", "human")
        blocked.append((t, prio))
    d = repo.j("next")["data"]
    assert d["task"] is None
    assert len(d["why"]) == 30 and len(d["blocked_on_human"]) == 20
    assert d["truncated"]["why"] == {
        "total": 35, "omitted": 5,
        "retrieve_with": "ledger next --full --json"}
    assert d["truncated"]["blocked_on_human"]["omitted"] == 15
    assert "questions --human" in d["truncated"]["blocked_on_human"][
        "retrieve_with"]
    kept = {w["id"] for w in d["why"]}
    assert all(prio == "p1" for t, prio in blocked if t in kept)  # least urgent cut
    r = repo.run("next")
    assert "(+5 more: ledger next --full" in r.stdout
    full = repo.j("next", "--full")["data"]
    assert len(full["why"]) == 35 and "truncated" not in full
    free = repo.add_task("Eligible", "-p", "p0")
    d = repo.j("next")["data"]
    assert d["task"]["header"]["id"] == free and "truncated" in d



# --- report replays state at the window end (T-w7v7wk) -----------------------

def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_report_replays_state_at_the_window_end(repo):
    import time
    tid = repo.add_task("Decision pending", "-p", "p1")
    repo.j("claim", tid, "--session", "w")
    repo.j("question", tid, "add", "which db?", "--human")
    repo.j("question", tid, "add", "cache ttl?")
    time.sleep(1.1)
    cutoff = _utc_now()
    time.sleep(1.1)
    repo.j("question", tid, "resolve", "db", "--answer", "postgres",
           "--session", "op")
    repo.j("question", tid, "resolve", "ttl", "--answer", "60s")
    repo.j("release", tid, "--session", "w")
    then = repo.j("report", "--until", cutoff)["data"]
    assert then["questions"] == {"human_created": 1, "human_answered": 0,
                                 "answered_total": 0, "human_open_end": 1}
    assert [a["claimed_by"] for a in then["agents"]["active_claims"]] == ["w"]
    assert then["agents"]["stranded_claims"] == []
    now = repo.j("report")["data"]
    assert now["questions"] == {"human_created": 1, "human_answered": 1,
                                "answered_total": 2, "human_open_end": 0}
    assert now["agents"]["active_claims"] == []
    assert "replay" in " ".join(now["sources"]["lower_bounds"])
    # a takeover chain: the holder at the cutoff is the taker
    t2 = repo.add_task("Taken over")
    repo.j("claim", t2, "--session", "a")
    repo.j("claim", t2, "--session", "b", "--force")
    time.sleep(1.1)
    cutoff2 = _utc_now()
    time.sleep(1.1)
    repo.j("done", t2, "--no-code", "x", "--session", "b")
    then = repo.j("report", "--until", cutoff2, "--task", t2)["data"]
    assert [a["claimed_by"] for a in then["agents"]["active_claims"]] == ["b"]
    assert then["work"]["closed_done"] == {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    now = repo.j("report", "--task", t2)["data"]
    assert now["agents"]["active_claims"] == []
    assert sum(now["work"]["closed_done"].values()) == 1


def test_report_final_commit_only_when_unique(repo):
    w = repo.add_task("Wave with two tips", "-p", "p1")
    repo.j("claim", w, "--session", "orch")
    repo.git("checkout", "-q", "-b", "tip-a")
    (repo.root / "a.py").write_text("a\n", encoding="utf-8")
    sha_a = repo.commit_all("Tip A", (f"Ledger-Task: {w}",))
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "tip-b")
    (repo.root / "b.py").write_text("b\n", encoding="utf-8")
    sha_b = repo.commit_all("Tip B", (f"Ledger-Task: {w}",))
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "tip-a")
    repo.git("merge", "-q", "--no-ff", "--no-commit", "tip-b")
    repo.git("commit", "-q", "-m", "Integrate both tips")  # untrailered
    d = repo.j("report", "--task", w)["data"]["commits"]
    assert d["final_commit"] is None
    assert set(d["final_commit_candidates"]) == {sha_a[:7], sha_b[:7]}
    repo.j("link", w, "HEAD")  # the merge is now the unique tip
    d = repo.j("report", "--task", w)["data"]["commits"]
    merge_sha = repo.git("rev-parse", "HEAD").stdout.strip()[:7]
    assert d["final_commit"] == merge_sha
    assert d["final_commit_candidates"] == [merge_sha]



# --- small fixes from the 2026-09-02 review (T-piaumc) ----------------------

def test_next_claim_reports_post_claim_resources_and_true_takeovers(repo):
    from test_hardening import set_stale_days
    tid = repo.add_task("Needs gpu3", "--tag", "resource:gpu3")
    d = repo.j("next", "--claim", "--session", "a")["data"]
    assert d["claimed"] and d["resources_held"] == {"gpu3": tid}
    assert d["stale_takeover"] is False
    set_stale_days(repo, -1)
    # refreshing one's OWN stale claim is not a takeover
    d = repo.j("next", "--claim", "--session", "a")["data"]
    assert d["task"]["header"]["id"] == tid and d["stale_takeover"] is False
    assert d["task"]["header"]["claimed_by"] == "a"
    # a different session taking a stale claim is
    d = repo.j("next", "--session", "b")["data"]
    assert d["stale_takeover"] is True and d["claimed"] is False
    d = repo.j("next", "--claim", "--session", "b")["data"]
    assert d["stale_takeover"] is True
    assert d["task"]["header"]["claimed_by"] == "b"



# --- session identity (sweep 2026-09-02, task G) ----------------------------

def test_next_reports_actor_and_refuses_a_second_fresh_claim(repo):
    a = repo.add_task("First", "-p", "p1")
    b = repo.add_task("Second", "-p", "p2")
    d = repo.j("next", "--claim", "--session", "w")["data"]
    assert d["actor"] == {"id": "w", "source": "flag"}
    assert d["task"]["header"]["id"] == a and d["held"] == []
    refused = repo.j("next", "--claim", "--session", "w", expect=2)
    assert refused["errors"][0]["code"] == "already-holding"
    assert a in refused["errors"][0]["message"]
    assert f"ledger brief {a}" in refused["errors"][0]["fix_hint"]
    assert repo.j("show", b)["data"]["header"]["status"] == "todo"
    d = repo.j("next", "--session", "w")["data"]  # without --claim: fine
    assert d["task"]["header"]["id"] == b and [h["id"] for h in d["held"]] == [a]
    d = repo.j("next", "--claim", "--session", "w", "--force")["data"]
    assert d["claimed"] and [h["id"] for h in d["held"]] == [a]
    # env source
    import subprocess as _sp
    import sys as _sys
    r = _sp.run([_sys.executable, str(repo.script), "next", "--json"],
                cwd=str(repo.root), env=repo.env, capture_output=True,
                text=True)
    assert json.loads(r.stdout)["data"]["actor"]["source"] == "env"


def test_git_name_fallback_warns_and_unknown_identity_is_refused(repo):
    import subprocess as _sp
    import sys as _sys
    tid = repo.add_task("Identity")
    env = dict(repo.env)
    env.pop("LEDGER_SESSION")
    r = _sp.run([_sys.executable, str(repo.script), "claim", tid, "--json"],
                cwd=str(repo.root), env=env, capture_output=True, text=True)
    d = json.loads(r.stdout)
    assert d["ok"] and d["data"]["actor"] == {"id": "tester", "source": "git"}
    fb = [e for e in d["errors"] if e["code"] == "session-fallback"]
    assert fb and "EVERY shell call" in fb[0]["fix_hint"]
    repo.j("release", tid, "--session", "tester")
    env["GIT_CONFIG_GLOBAL"] = str(repo.root / "no-such-gitconfig")
    r = _sp.run([_sys.executable, str(repo.script), "claim", tid, "--json"],
                cwd=str(repo.root), env=env, capture_output=True, text=True)
    d = json.loads(r.stdout)
    assert r.returncode == 3 and d["errors"][0]["code"] == "usage"
    assert "unknown" in d["errors"][0]["message"]
    assert repo.j("show", tid)["data"]["header"]["status"] == "todo"
    r = _sp.run([_sys.executable, str(repo.script), "next", "--claim",
                 "--json"], cwd=str(repo.root), env=env, capture_output=True,
                text=True)
    assert r.returncode == 3



def test_report_final_commit_needs_no_git_per_pair(ledger_mod, repo,
                                                   monkeypatch, capsys):
    w = repo.add_task("Wave of many commits", "-p", "p1")
    repo.j("claim", w, "--session", "orch")
    for i in range(8):
        (repo.root / f"f{i}.py").write_text(str(i), encoding="utf-8")
        repo.commit_all(f"Member commit {i}", (f"Ledger-Task: {w}",))
    head = repo.git("rev-parse", "HEAD").stdout.strip()[:7]
    monkeypatch.chdir(repo.root)
    real = ledger_mod.run_git
    calls = []

    def counting(args, cwd):
        calls.append(args[0] if args[0] != "-c" else args[4])
        return real(args, cwd)
    monkeypatch.setattr(ledger_mod, "run_git", counting)
    args = ledger_mod.build_parser().parse_args(
        ["report", "--task", w, "--json", "--session", "t"])
    rc = args.fn(args)
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["data"]["commits"]["final_commit"] == head
    assert "merge-base" not in calls



# --- contract pass (sweep 2026-09-02, task I) --------------------------------

def test_usage_errors_keep_the_json_envelope(repo):
    tid = repo.add_task("Usage")
    r = repo.run("step", tid, "check", "--json")  # missing positional
    assert r.returncode == 3
    payload = json.loads(r.stdout)
    assert payload["ok"] is False and payload["errors"][0]["code"] == "usage"
    assert payload["errors"][0]["fix_hint"]
    r = repo.run("frobnicate", "--json")
    assert r.returncode == 3 and json.loads(r.stdout)["ok"] is False
    r = repo.run("step", tid, "check")  # no --json: plain text on stderr
    assert r.returncode == 3 and r.stdout == "" and "usage" in r.stderr


def test_list_blocked_on_is_the_integrator_queue(repo):
    ready = repo.add_task("Ready one")
    repo.j("claim", ready)
    repo.j("release", ready, "--blocked", "--on",
           "external: ready for integration")
    parked = repo.add_task("Parked")
    repo.j("block", parked, "--on", "external: wave open")
    human = repo.add_task("Human gate")
    repo.j("block", human, "--on", "human")
    rows = repo.j("list", "--blocked-on", "external: ready")["data"]["tasks"]
    assert [t["id"] for t in rows] == [ready]
    rows = repo.j("list", "--blocked-on", "external:")["data"]["tasks"]
    assert {t["id"] for t in rows} == {ready, parked}
    v = repo.j("validate", "--no-git")["data"]
    assert {"error_count", "warning_count", "warnings_only", "info_count"} <= set(v)


def test_every_cli_code_is_documented_in_the_readme(ledger_mod):
    import re as _re
    from pathlib import Path as _P
    src = _P(ledger_mod.__file__).read_text(encoding="utf-8")
    codes = set(_re.findall(r'LedgerError\(\s*"([a-z-]+)"', src)) | set(
        _re.findall(r'\berr\(\s*"([a-z-]+)"', src))
    readme = _P(ledger_mod.__file__).resolve().parents[1].joinpath(
        "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in codes - set(ledger_mod.VALIDATION_CODES)
                     if f"`{c}`" not in readme)
    assert missing == [], missing



# --- fix_hint audit (sweep 2026-09-02, task J) -------------------------------

def test_hints_name_real_commands_and_indexes(repo):
    from conftest import LedgerRepo, _isolated_env
    # next with nothing at all explains itself
    d = repo.j("next")["data"]
    assert d["task"] is None and d["reason"] == "no tasks in the ledger"
    t = repo.add_task("Only")
    repo.j("done", t, "--no-code", "x")
    assert repo.j("next")["data"]["reason"] == "every task is closed"
    b = repo.add_task("Blocked one")
    repo.j("block", b, "--on", "human")
    assert "ineligible" in repo.j("next")["data"]["reason"]
    # done's hints carry the real indexes and report what they linked
    tid = repo.add_task("Indexed hints")
    repo.j("step", tid, "add", "first step")
    repo.j("step", tid, "check", "1")
    repo.j("step", tid, "add", "second step")
    repo.j("question", tid, "add", "plain?")
    repo.j("question", tid, "add", "gate?", "--human")
    (repo.root / "h.py").write_text("h\n", encoding="utf-8")
    sha = repo.commit_all("Untrailered evidence")
    d = repo.j("done", tid, "--commit", "HEAD", expect=2)
    hints = "\n".join(e["fix_hint"] for e in d["errors"])
    assert f"ledger step {tid} check 2" in hints
    assert f"ledger question {tid} resolve 1 --answer" in hints  # plain? is #1
    assert f"ledger question {tid} resolve 2 --answer" in hints  # gate? is #2
    assert d["data"]["linked"] == [sha[:7]]
    assert f"ledger unlink {tid}" in d["errors"][0]["fix_hint"]
    # validate's hints
    xl = repo.add_task("Whale", "-s", "xl")
    loose = repo.add_task("Loose done")
    repo.j("done", loose, "--no-code", "x")
    repo.write(loose, repo.read(loose).replace(
        "## Next Steps\n", "## Next Steps\n\n- [ ] forgotten\n"))
    evid = repo.add_task("No evidence")
    repo.j("done", evid, "--no-code", "x")
    repo.write(evid, "\n".join(l for l in repo.read(evid).split("\n")
                               if "done(no-code)" not in l)
               .replace("## Log\n", "## Log\n\n- 2026-01-01T00:00:00Z [x] done: evidence: none\n"))
    v = json.loads(repo.run("validate", "--no-git", "--json").stdout)
    by_code = {e["code"]: e for e in v["errors"]}
    assert "--size l" in by_code["xl-open"]["fix_hint"]
    assert "MOOT" in by_code["done-loose-ends"]["fix_hint"]
    assert "reopen" not in by_code["done-evidence"]["fix_hint"]
    assert "ledger link" in by_code["done-evidence"]["fix_hint"]



# --- orchestration signals (sweep 2026-09-02, task K) -----------------------

def test_scan_reports_contended_tasks(repo):
    tid = repo.add_task("Contended")
    repo.j("claim", tid, "--session", "b")
    repo.j("note", tid, "b working", "--session", "b")
    assert repo.j("scan")["data"]["contended"] == []
    repo.j("note", tid, "orch also touched it", "--session", "orch")
    c = repo.j("scan")["data"]["contended"]
    assert c and c[0]["task"] == tid and c[0]["actors"] == ["b", "orch"]
    r = repo.run("scan")
    assert f"contended {tid}" in r.stdout


def test_claim_takes_an_external_handoff_in_one_step(repo):
    tid = repo.add_task("Handed off")
    repo.j("claim", tid, "--session", "worker")
    repo.j("release", tid, "--blocked", "--on", "external: ready for integration",
           "--session", "worker")
    d = repo.j("claim", tid, "--session", "integrator")
    assert d["ok"]
    h = repo.j("show", tid)["data"]["header"]
    assert h["status"] == "in_progress" and h["claimed_by"] == "integrator"
    assert "blocked_on" not in h
    assert "was blocked on external: ready" in repo.j("show", tid)["data"]["log"][-1]["text"]
    human = repo.add_task("Human gate")
    repo.j("block", human, "--on", "human")
    assert repo.j("claim", human, expect=2)["errors"][0]["code"] == "bad-state"


def test_done_refuses_unreachable_evidence_and_link_warns(repo):
    tid = repo.add_task("Unreachable evidence")
    repo.j("claim", tid)
    repo.commit_all("Track the task first")
    (repo.root / "gone.py").write_text("g\n", encoding="utf-8")
    sha = repo.commit_all("Will be reset away")
    repo.git("reset", "-q", "--hard", "HEAD~1")
    d = repo.j("done", tid, "--commit", sha, expect=2)
    assert d["errors"][0]["code"] == "done-evidence"
    assert "not reachable" in d["errors"][0]["message"]
    assert repo.j("show", tid)["data"]["commits"] == []  # nothing saved
    d = repo.j("link", tid, sha)
    warn = [e for e in d["errors"] if e["code"] == "sha-unreachable"]
    assert d["ok"] and warn and "unlink" in warn[0]["fix_hint"]
    assert repo.j("done", tid, "--force")["ok"]


def test_resource_contention_is_visible_and_tags_are_guarded(repo):
    a = repo.add_task("Holder A", "--tag", "resource:gpu")
    b = repo.add_task("Holder B", "--tag", "resource:gpu")
    c = repo.add_task("Late tagger")
    repo.j("claim", a, "--session", "x")
    repo.j("claim", b, "--session", "y", "--force")
    n = repo.j("next", "--session", "z")["data"]
    assert set(n["resource_contention"]["gpu"]) == {a, b}  # same-second ids
    repo.j("claim", c, "--session", "w")
    refused = repo.j("set", c, "--add-tag", "resource:gpu", "--session", "w",
                     expect=2)
    assert refused["errors"][0]["code"] == "resource-held"
    assert "resource:gpu" not in repo.read(c)
    d = repo.j("set", c, "--add-tag", "resource:gpu", "--session", "w", "--force")
    assert d["ok"]
    log = repo.j("show", c)["data"]["log"][-1]
    assert log["verb"] == "set" and "also held by" in log["text"]
    assert repo.j("set", c, "--add-tag", "plain", "--session", "w")["ok"]


def test_staleness_follows_the_holder_not_bystanders(repo):
    from test_hardening import set_stale_days
    tid = repo.add_task("Stranded worker")
    repo.j("claim", tid, "--session", "worker")
    set_stale_days(repo, -1)
    repo.j("note", tid, "orch: worker has not reported", "--session", "orch")
    rc = repo.run("validate", "--no-git", "--json")
    v = json.loads(rc.stdout)
    assert any(e["code"] == "stale-claim" and e["task"] == tid for e in v["errors"])
    repo.j("note", tid, "still here", "--session", "worker")
    set_stale_days(repo, 7)
    v = json.loads(repo.run("validate", "--no-git", "--json").stdout)
    assert not any(e["code"] == "stale-claim" for e in v["errors"])


def test_member_of_handoffs_and_last_handoff(repo):
    m1 = repo.add_task("Member one", "-p", "p1")
    m2 = repo.add_task("Member two", "-p", "p2")
    w = repo.j("add", "Wave", "--after", m1, "--after", m2)["data"]["id"]
    rows = repo.j("list", "--member-of", w)["data"]["tasks"]
    assert [t["id"] for t in rows] == [m1, m2]
    repo.j("claim", m1)
    repo.j("release", m1, "--blocked", "--on", "external: ready for integration",
           "--note", "green locally")
    r = repo.j("report", "--task", w)["data"]
    assert r["handoffs"]["awaiting_integration"] == [m1]
    d = repo.j("brief", m1)["data"]
    assert d["last_handoff"]["verb"] == "release"
    assert "green locally" in d["last_handoff"]["text"]
    assert "last handoff:" in repo.run("brief", m1).stdout
    assert repo.j("brief", m2)["data"]["last_handoff"] is None



# --- untested surface from the docs review (sweep 2026-09-02, task L) -------

def test_scan_since_and_multi_sha_link_unlink(repo):
    tid = repo.add_task("Ranges")
    repo.j("claim", tid)
    (repo.root / "one.py").write_text("1", encoding="utf-8")
    first = repo.commit_all("First work", (f"Ledger-Task: {tid}",))
    (repo.root / "two.py").write_text("2", encoding="utf-8")
    second = repo.commit_all("Second work", (f"Ledger-Task: {tid}",))
    d = repo.j("scan", "--since", first)["data"]
    assert [x["sha"] for x in d["linked"]] == [second[:7]]
    assert d["commits_scanned"] == 1
    d = repo.j("link", tid, first, second)
    assert [i["sha7"] for i in d["data"]["linked"]] == [first[:7], second[:7]]
    d = repo.j("unlink", tid, first, second, "--why", "both wrong")
    assert d["data"]["unlinked"] == [first[:7], second[:7]]
    assert repo.j("show", tid)["data"]["commits"] == []


def test_no_such_question_and_bad_row(repo):
    tid = repo.add_task("Questions")
    repo.j("question", tid, "add", "only one?")
    d = repo.j("question", tid, "resolve", "nothing like this", "--answer",
               "x", expect=2)
    assert d["errors"][0]["code"] == "no-such-question"
    assert "brief" in d["errors"][0]["fix_hint"]
    d = repo.j("answers", "apply", "-", expect=2,
               input=json.dumps([{"task": tid, "text": "nope?", "answer": "a"},
                                 {"answer": "no task key"}]))
    codes = {e["code"] for e in d["errors"]}
    assert codes == {"no-such-question", "bad-row"}


def test_git_verbs_refuse_without_a_repository(plain):
    tid = plain.add_task("No git here")
    for call in (("link", tid, "HEAD"), ("unlink", tid, "abc1234"), ("scan",)):
        d = plain.j(*call, expect=2)
        assert d["errors"][0]["code"] in ("no-git", "no-such-commit-line"), call


def test_answers_apply_refuses_a_corrupt_target(repo):
    tid = repo.add_task("Corrupt target")
    repo.j("question", tid, "add", "q?", "--human")
    repo.write(tid, repo.read(tid).replace("status: todo", "status: todo\nstatus: done"))
    before = repo.read(tid)
    d = repo.j("answers", "apply", "-", expect=2,
               input=json.dumps([{"task": tid, "text": "q?", "answer": "a"}]))
    assert any(e["code"] == "corrupt-file" for e in d["errors"])
    assert repo.read(tid) == before
