"""`ledger log`: the corpus-wide, read-only Log event stream."""
import re


def events(payload):
    return payload["data"]["events"]


def stamp(repo, tid, old, new):
    """Rewrite one Log timestamp so ordering is testable without sleeping."""
    text = repo.read(tid)
    assert old in text
    repo.write(tid, text.replace(old, new, 1))


def test_rows_carry_task_context_newest_first(repo):
    a = repo.add_task("Alpha", "--tag", "core")
    b = repo.add_task("Beta")
    repo.j("note", a, "first note")
    repo.j("note", b, "second note")
    # pin distinct timestamps: a's add oldest, b's note newest
    for tid, verb, ts in ((a, "add", "2026-01-01T00:00:00Z"),
                          (b, "add", "2026-01-02T00:00:00Z"),
                          (a, "note", "2026-01-03T00:00:00Z"),
                          (b, "note", "2026-01-04T00:00:00Z")):
        line = next(l for l in repo.read(tid).splitlines()
                    if re.match(rf"^- \S+ \[[^\]]+\] {verb}: ", l))
        stamp(repo, tid, line, re.sub(r"^- \S+", f"- {ts}", line))
    d = repo.j("log")
    assert d["ok"] and d["data"]["count"] == 4
    rows = events(d)
    assert [(r["task"], r["verb"]) for r in rows] == [
        (b, "note"), (a, "note"), (b, "add"), (a, "add")]
    top = rows[0]
    assert top["title"] == "Beta" and top["status"] == "todo"
    assert top["actor"] == "test-session" and top["text"] == "second note"
    assert set(top) == {"ts", "actor", "verb", "text", "task", "title",
                        "status"}


def test_filters(repo):
    a = repo.add_task("Alpha", "--tag", "core")
    b = repo.add_task("Beta")
    repo.j("note", a, "plain")
    repo.j("note", b, "nope", "--dead-end")
    repo.j("note", b, "by someone else", "--session", "other-agent")
    d = repo.j("log", "--task", a)
    assert {r["task"] for r in events(d)} == {a}
    assert d["data"]["scope"] == {"task": a}
    d = repo.j("log", "--tag", "core")
    assert {r["task"] for r in events(d)} == {a}
    d = repo.j("log", "--actor", "other-agent")
    assert [r["text"] for r in events(d)] == ["by someone else"]
    d = repo.j("log", "--verb", "note(dead-end)")
    assert [r["text"] for r in events(d)] == ["nope"]
    d = repo.j("log", "--verb", "note", "--verb", "add")
    assert {r["verb"] for r in events(d)} == {"note", "add"}
    assert d["data"]["verbs"] == ["add", "note"]
    assert events(repo.j("log", "--since", "2999-01-01")) == []
    assert events(repo.j("log", "--until", "2000-01-01")) == []
    assert repo.j("log", "--since", "2000-01-01")["data"]["count"] == 5
    bad = repo.j("log", "--task", "T-nope", expect=2)
    assert bad["errors"][0]["code"] == "no-such-task"


def test_cap_and_truncation(repo):
    for i in range(4):
        repo.add_task(f"Task {i}")
    d = repo.j("log", "-n", "2")
    assert len(events(d)) == 2 and d["data"]["count"] == 4
    cut = d["data"]["truncated"]["events"]
    assert cut["total"] == 4 and cut["omitted"] == 2
    assert "-n 0" in cut["retrieve_with"]
    d = repo.j("log", "-n", "0")
    assert len(events(d)) == 4 and "truncated" not in d["data"]


def test_broken_file_reported_and_nothing_written(repo):
    good = repo.add_task("Readable")
    bad = repo.add_task("Broken")
    repo.write(bad, repo.read(bad).replace("status: todo",
                                           "status: todo\nstatus: done"))
    before = repo.task_file(good).read_bytes()
    d = repo.j("log", expect=1)  # data, but ok is false
    assert d["ok"] is False and good in {r["task"] for r in events(d)}
    assert any(e["code"] == "parse" and e["task"] == bad for e in d["errors"])
    assert repo.task_file(good).read_bytes() == before
    r = repo.run("log", "--task", good)  # human mode: one row per event
    assert good in r.stdout and "add: created" in r.stdout
