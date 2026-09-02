"""`ledger search`: ranked, read-only retrieval across task files."""
import json


def ids(payload):
    return [t["id"] for t in payload["data"]["tasks"]]


def test_field_ranking_and_open_bonus(repo):
    title_hit = repo.add_task("Tokenizer rewrite", "-p", "p3")
    spec_hit = repo.j("add", "Parser cleanup", "-p", "p3", "--spec",
                      "Touches the tokenizer boundary")["data"]["id"]
    log_hit = repo.add_task("Unrelated chore", "-p", "p3")
    repo.j("note", log_hit, "tokenizer note only in the log")
    closed_title = repo.add_task("Old tokenizer work", "-p", "p3")
    repo.j("done", closed_title, "--no-code", "shipped")
    d = repo.j("search", "tokenizer")
    assert d["ok"] and d["data"]["count"] == 4
    assert ids(d) == [title_hit, closed_title, spec_hit, log_hit]
    rows = {t["id"]: t for t in d["data"]["tasks"]}
    assert rows[title_hit]["score"] == 9      # title 8 + open 1
    assert rows[closed_title]["score"] == 8   # title 8, closed
    assert rows[spec_hit]["matched_in"] == ["spec"]
    assert rows[log_hit]["matched_in"] == ["log"]
    # equal scores fall back to priority order
    p1 = repo.add_task("Tokenizer p1", "-p", "p1")
    assert ids(repo.j("search", "tokenizer"))[0] == p1


def test_and_any_in_and_regex(repo):
    both = repo.j("add", "Retry client", "--spec", "backoff with jitter")[
        "data"]["id"]
    one = repo.add_task("Retry server")
    assert ids(repo.j("search", "retry", "jitter")) == [both]
    assert set(ids(repo.j("search", "retry", "jitter", "--any"))) == {both, one}
    assert ids(repo.j("search", "jitter", "--in", "title")) == []
    assert ids(repo.j("search", "jitter", "--in", "spec,title")) == [both]
    assert ids(repo.j("search", r"back(off|up)", "--regex")) == [both]
    bad = repo.j("search", "(", "--regex", expect=3)
    assert bad["errors"][0]["code"] == "usage" and bad["errors"][0]["fix_hint"]
    bad = repo.j("search", "x", "--in", "body", expect=3)
    assert bad["errors"][0]["code"] == "usage"


def test_status_filters_cap_and_count(repo):
    a = repo.add_task("Cache eviction")
    b = repo.add_task("Cache warmup")
    c = repo.add_task("Cache invalidation")
    repo.j("done", b, "--no-code", "x")
    repo.j("drop", c, "--why", "y")
    assert set(ids(repo.j("search", "cache"))) == {a, b, c}  # every status
    assert ids(repo.j("search", "cache", "--open")) == [a]
    assert ids(repo.j("search", "cache", "--status", "dropped")) == [c]
    d = repo.j("search", "cache", "-n", "1")
    assert len(d["data"]["tasks"]) == 1 and d["data"]["count"] == 3
    d = repo.j("search", "nothing-matches-this")
    assert d["ok"] and d["data"]["count"] == 0 and d["data"]["tasks"] == []


def test_snippets_and_id_hits(repo):
    tid = repo.j("add", "Long spec", "--spec",
                 ("filler " * 40) + "NEEDLE here " + ("filler " * 40))[
        "data"]["id"]
    d = repo.j("search", "needle")
    snip = d["data"]["tasks"][0]["snippets"]["spec"]
    assert "NEEDLE" in snip and len(snip) <= 160
    frag = tid.split("-")[1][:4]
    d = repo.j("search", frag, "--in", "id")
    assert ids(d) == [tid] and d["data"]["tasks"][0]["matched_in"] == ["id"]
    # raw-section fields: HUMAN markers and Log verbs are searchable
    repo.j("question", tid, "add", "which vendor?", "--human")
    assert ids(repo.j("search", "HUMAN:", "--in", "questions")) == [tid]
    assert tid in ids(repo.j("search", "question: added", "--in", "log"))


def test_broken_file_is_reported_not_fatal(repo):
    good = repo.add_task("Searchable")
    bad = repo.add_task("Broken")
    repo.write(bad, repo.read(bad).replace("status: todo",
                                           "status: todo\nstatus: done"))
    d = repo.j("search", "searchable", expect=1)  # data, but ok is false
    assert ids(d) == [good] and d["ok"] is False
    assert any(e["code"] == "parse" and e["task"] == bad for e in d["errors"])


def test_search_writes_nothing(repo):
    tid = repo.add_task("Immutable under search")
    before = repo.task_file(tid).read_bytes()
    repo.j("search", "immutable")
    assert repo.task_file(tid).read_bytes() == before
    r = repo.run("search", "immutable")  # human mode renders a row + snippet
    assert tid in r.stdout and "title" in r.stdout
