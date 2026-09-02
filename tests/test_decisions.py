"""The operator decision loop: `questions` as a decision view and
`answers apply` recording answers in batch (T-z1dkju)."""
import json
import os
import subprocess
import sys

from test_concurrency import _drop_lock, _hold_lock


def test_questions_rows_carry_context_key_and_task_state(repo):
    tid = repo.add_task("Needs decisions", "-p", "p1")
    repo.j("claim", tid)
    repo.j("question", tid, "add", "Which vendor?", "--human")
    repo.j("question", tid, "add", "cache ttl?")
    text = repo.read(tid).replace(
        "- [ ] HUMAN: Which vendor?\n",
        "- [ ] HUMAN: Which vendor?\n  (a) Acme — cheaper\n"
        "  (b) Globex — recommended\n### not context\n")
    repo.write(tid, text)
    rows = repo.j("questions")["data"]["questions"]
    assert [r["n"] for r in rows] == [1, 2]
    first, second = rows
    assert first["kind"] == "question" and first["priority"] == "p1"
    assert first["status"] == "in_progress"
    assert first["claimed_by"] == "test-session" and first["size"] == "m"
    assert first["context"] == ["(a) Acme — cheaper", "(b) Globex — recommended"]
    assert second["context"] == []
    assert first["key"] == "which vendor"
    other = repo.add_task("Duplicate question")
    repo.j("question", other, "add", "which  vendor", "--human")
    keys = {(r["task"], r["key"]) for r in
            repo.j("questions", "--human")["data"]["questions"]}
    assert keys == {(tid, "which vendor"), (other, "which vendor")}
    scoped = repo.j("questions", "--task", other)["data"]["questions"]
    assert [r["task"] for r in scoped] == [other]
    assert repo.j("questions", "--task", "zzzzzz", expect=2)["errors"][0][
        "code"] == "no-such-task"
    # show/list shapes are unchanged by the richer dashboard
    assert "context" not in repo.j("show", tid)["data"]["open_questions"][0]
    r = repo.run("questions")
    assert "    (b) Globex" in r.stdout  # context rendered indented


def test_blocked_on_human_rows_and_reason_sources(repo):
    a = repo.add_task("Blocked with why")
    repo.j("block", a, "--on", "human", "--why", "budget approval")
    b = repo.add_task("Handed off blocked")
    repo.j("claim", b)
    repo.j("release", b, "--blocked", "--on", "human", "--note", "pick a db")
    c = repo.add_task("Blocked on a task")
    repo.j("block", c, "--on", a)
    d = repo.j("questions")["data"]
    rows = {r["id"]: r for r in d["blocked_on_human"]}
    assert set(rows) == {a, b}  # --on T-y never appears
    assert rows[a]["reason"] == "budget approval"
    assert rows[a]["reason_source"] == "block"
    assert rows[b]["reason"] == "pick a db" and rows[b]["reason_source"] == "release"
    assert rows[b]["claimed_by"] is None and rows[a]["status"] == "blocked"
    # a stale reason never resurfaces: block -> unblock -> release --blocked
    repo.j("unblock", a)
    assert a not in {r["id"] for r in repo.j("questions")["data"][
        "blocked_on_human"]}
    repo.j("claim", a)
    repo.j("release", a, "--blocked", "--on", "human")
    rows = {r["id"]: r for r in repo.j("questions")["data"]["blocked_on_human"]}
    assert rows[a]["reason"] == "" and rows[a]["reason_source"] == "release"
    r = repo.run("questions")
    assert f"{b} [BLOCKED on human]" in r.stdout and "pick a db" in r.stdout


def _write_answers(repo, name, rows):
    path = repo.root.parent / name
    path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


def test_answers_apply_batch_across_tasks(repo):
    a = repo.add_task("Alpha decisions")
    b = repo.add_task("Beta decisions")
    repo.j("question", a, "add", "ship behind a flag?", "--human")
    repo.j("question", a, "add", "cache ttl?")
    repo.j("question", b, "add", "which vendor?", "--human")
    env = repo.j("questions", "--json")
    for row in env["data"]["questions"]:
        row["answer"] = {"ship behind a flag?": "yes", "cache ttl?": "60s",
                         "which vendor?": "Globex"}[row["text"]]
    path = _write_answers(repo, "answers.json", env)  # the whole envelope
    d = repo.j("answers", "apply", path)
    assert d["ok"] and len(d["data"]["applied"]) == 3
    assert d["data"]["skipped"] == []
    for tid in (a, b):
        show = repo.j("show", tid)["data"]
        assert all(q["answered"] for q in show["open_questions"])
    log_a = [e for e in repo.j("show", a)["data"]["log"] if e["verb"] == "answer"]
    assert len(log_a) == 2 and log_a[0]["text"].startswith("'HUMAN: ship")
    assert repo.j("done", a, "--no-code", "decided")["ok"]  # gate cleared
    # re-running the same file is safe: everything is already-answered
    d = repo.j("answers", "apply", path)
    assert d["data"]["applied"] == []
    assert {s["reason"] for s in d["data"]["skipped"]} == {"already-answered"}
    assert repo.j("validate", "--no-git", "--strict")["ok"]


def test_answers_apply_selector_rules_and_refusals(repo):
    a = repo.add_task("Selector rules")
    repo.j("question", a, "add", "first?", "--human")
    repo.j("question", a, "add", "second?", "--human")
    # stale n with matching text: text wins
    d = repo.j("answers", "apply", _write_answers(repo, "s1.json", [
        {"task": a, "n": 1, "text": "second?", "answer": "by text"}]))
    assert d["data"]["applied"][0]["n"] == 2
    qs = repo.j("show", a)["data"]["open_questions"]
    assert qs[1]["answered"] and not qs[0]["answered"]
    # one bad row refuses the whole batch and changes no file
    b = repo.add_task("Untouched")
    repo.j("question", b, "add", "fine?", "--human")
    before_a, before_b = repo.read(a), repo.read(b)
    d = repo.j("answers", "apply", _write_answers(repo, "s2.json", [
        {"task": b, "text": "fine?", "answer": "yes"},
        {"task": a, "text": "second?", "answer": "different"},  # answered
    ]), expect=2)
    assert d["ok"] is False
    assert any(e["code"] == "bad-state" and e["task"] == a for e in d["errors"])
    assert repo.read(a) == before_a and repo.read(b) == before_b
    # rows without an answer, block rows and n-only rows
    d = repo.j("answers", "apply", _write_answers(repo, "s3.json", [
        {"task": b, "text": "fine?"},
        {"task": b, "kind": "block", "answer": "x"},
        {"task": a, "n": 1, "answer": "n-only"},
    ]))
    assert [s["reason"] for s in d["data"]["skipped"]] == [
        "no answer", "block row (unblock by hand)"]
    assert d["data"]["applied"][0]["text"] == "HUMAN: first?"
    # duplicate targets, unknown task, ambiguous fragment
    c = repo.add_task("Dupes")
    repo.j("question", c, "add", "one?", "--human")
    d = repo.j("answers", "apply", _write_answers(repo, "s4.json", [
        {"task": c, "text": "one?", "answer": "a"},
        {"task": c, "n": 1, "answer": "b"},
        {"task": "zzzzzz", "text": "x", "answer": "y"},
        {"task": "T-", "text": "x", "answer": "y"},
    ]), expect=2)
    codes = {e["code"] for e in d["errors"]}
    assert {"duplicate-target", "no-such-task", "ambiguous-id"} <= codes
    assert repo.j("show", c)["data"]["open_questions"][0]["answered"] is False
    # stdin, malformed JSON (exit 3, before any lock), bare list
    r = repo.run("answers", "apply", "-", "--json",
                 input=json.dumps([{"task": c, "text": "one?", "answer": "a"}]))
    assert r.returncode == 0
    r = repo.run("answers", "apply", "-", "--json", input="{not json")
    assert r.returncode == 3 and json.loads(r.stdout)["errors"][0]["code"] == "usage"


def test_answers_apply_equals_resolve_modulo_time(repo):
    a = repo.add_task("Via resolve")
    b = repo.add_task("Via apply")
    for t in (a, b):
        repo.j("question", t, "add", "HUMAN-free question?")
    repo.j("question", a, "resolve", "question", "--answer", "same")
    repo.j("answers", "apply", _write_answers(repo, "eq.json", [
        {"task": b, "text": "question", "answer": "same"}]))
    section = lambda tid: repo.read(tid).split("## Open Questions")[1].split(
        "## Commits")[0]
    assert section(a) == section(b)
    verbs = lambda tid: [e["verb"] for e in repo.j("show", tid)["data"]["log"]]
    assert verbs(a) == verbs(b) == ["add", "question", "answer"]


def test_answers_apply_respects_the_mutation_lock(plain):
    tid = plain.add_task("Locked ledger")
    plain.j("question", tid, "add", "q?", "--human")
    path = plain.root.parent / "lock.json"
    path.write_text(json.dumps([{"task": tid, "text": "q?", "answer": "a"}]),
                    encoding="utf-8")
    fd = _hold_lock(plain.root / ".ledger" / ".lock")
    try:
        env = dict(plain.env)
        env["LEDGER_LOCK_TIMEOUT"] = "0.3"
        r = subprocess.run([sys.executable, str(plain.script), "answers",
                            "apply", str(path), "--json"],
                           cwd=str(plain.root), env=env, capture_output=True,
                           text=True)
        assert r.returncode == 2
        assert json.loads(r.stdout)["errors"][0]["code"] == "lock-timeout"
    finally:
        _drop_lock(fd)
    assert plain.j("answers", "apply", str(path))["ok"]
