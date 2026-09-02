"""Git-backed behavior: coverage, scan, trailers, merges, tamper detection."""
import json

import pytest


def validate(repo, *flags):
    r = repo.run("validate", *flags, "--json")
    return r.returncode, json.loads(r.stdout)


def codes(payload):
    return {e["code"] for e in payload["errors"]}


def test_coverage_clean_then_catches_unlinked(repo):
    tid = repo.add_task("Tracked work")
    repo.j("claim", tid)
    (repo.root / "feature.py").write_text("code\n", encoding="utf-8")
    repo.commit_all("Implement feature", (f"Ledger-Task: {tid}",))
    rc, payload = validate(repo, "--coverage")
    assert rc == 0, payload

    (repo.root / "rogue.py").write_text("rogue\n", encoding="utf-8")
    sha = repo.commit_all("Rogue commit with no trailer")
    rc, payload = validate(repo, "--coverage")
    assert rc == 1
    cov = [e for e in payload["errors"] if e["code"] == "coverage"]
    assert any(sha[:7] in e["message"] for e in cov)
    assert all(e["fix_hint"] for e in cov)


def test_exemption_channels(repo):
    (repo.root / "a.txt").write_text("a\n", encoding="utf-8")
    repo.commit_all("Chore work", ("Ledger-Exempt: tooling chore",))
    (repo.root / "b.txt").write_text("b\n", encoding="utf-8")
    repo.commit_all("Merge branch 'feature' into main")  # exempt_patterns
    repo.j("add", "Ledger-only change")  # commit touching only .ledger/
    repo.commit_all("Record new task in ledger")
    rc, payload = validate(repo, "--coverage")
    assert rc == 0, payload
    info = [e for e in payload["errors"] if e["code"] == "exempt-ratio"]
    assert info and info[0]["severity"] == "info"


def test_trailer_dangling(repo):
    (repo.root / "c.txt").write_text("c\n", encoding="utf-8")
    repo.commit_all("Work against ghost", ("Ledger-Task: T-gh0st1",))
    rc, payload = validate(repo, "--coverage")
    assert rc == 1
    assert "trailer-dangling" in codes(payload)


def test_linked_never_claimed_warning(repo):
    tid = repo.add_task("Never claimed")
    (repo.root / "d.txt").write_text("d\n", encoding="utf-8")
    repo.commit_all("Drive-by work", (f"Ledger-Task: {tid}",))
    rc, payload = validate(repo)
    assert rc == 0  # warning tier
    assert "linked-never-claimed" in codes(payload)


def test_sha_unreachable_warning(repo):
    tid = repo.add_task("Ghost sha")
    text = repo.read(tid).replace(
        "## Commits", "## Commits\n\n- abc1234 2026-01-01 ghost commit")
    repo.write(tid, text)
    rc, payload = validate(repo)
    assert rc == 0
    assert "sha-unreachable" in codes(payload)


def test_scan_buckets_and_write_backfill(repo):
    tid = repo.add_task("Scanned")
    repo.j("claim", tid)
    (repo.root / "e.txt").write_text("e\n", encoding="utf-8")
    linked_sha = repo.commit_all("Advance task", (f"Ledger-Task: {tid}",))
    (repo.root / "f.txt").write_text("f\n", encoding="utf-8")
    repo.commit_all("Exempt thing", ("Ledger-Exempt: unrelated",))
    (repo.root / "g.txt").write_text("g\n", encoding="utf-8")
    unlinked_sha = repo.commit_all("Untracked thing")
    (repo.root / "h.txt").write_text("h\n", encoding="utf-8")
    repo.commit_all("Ghost ref", ("Ledger-Task: T-gh0st2",))

    d = repo.j("scan")["data"]
    assert any(x["task"] == tid and x["sha"] == linked_sha[:7]
               for x in d["linked"])
    assert len(d["exempt"]) >= 1
    assert any(x["sha"] == unlinked_sha[:7] for x in d["unlinked"])
    assert any(x["id"] == "T-gh0st2" for x in d["dangling"])
    assert d["backfilled"] == []

    d = repo.j("scan", "--write")["data"]
    assert {"sha": linked_sha[:7], "task": tid} in [
        {"sha": b["sha"], "task": b["task"]} for b in d["backfilled"]]
    assert linked_sha[:7] in repo.read(tid)
    # idempotent: second --write backfills nothing new
    d = repo.j("scan", "--write")["data"]
    assert d["backfilled"] == []


def test_link_and_done_with_head(repo):
    tid = repo.add_task("Linkable")
    repo.j("claim", tid)
    (repo.root / "i.txt").write_text("i\n", encoding="utf-8")
    sha = repo.commit_all("Do the work", ("Ledger-Exempt: linked manually below",))
    bad = repo.j("link", tid, "0000000000000000000000000000000000000000",
                 expect=2)
    assert bad["errors"][0]["code"] == "no-such-commit"
    repo.j("link", tid, "HEAD")
    show = repo.j("show", tid)["data"]
    assert show["commits"][0]["sha"] == sha[:7]
    assert any(e["verb"] == "link" for e in show["log"])
    d = repo.j("done", tid)
    assert d["ok"]
    assert any(e["verb"] == "done" and sha[:7] in e["text"]
               for e in repo.j("show", tid)["data"]["log"])


def test_done_autolinks_trailer_commits(repo):
    tid = repo.add_task("Auto")
    repo.j("claim", tid)
    (repo.root / "j.txt").write_text("j\n", encoding="utf-8")
    sha = repo.commit_all("Advance auto task", (f"Ledger-Task: {tid}",))
    d = repo.j("done", tid)  # no --commit needed: trailer is the claim
    assert d["ok"]
    assert d["data"]["commits"][0]["sha"] == sha[:7]


def test_merge_parallel_adds_do_not_conflict(repo):
    repo.git("checkout", "-q", "-b", "feature-a")
    a = repo.add_task("From branch A")
    repo.commit_all("Track task A")  # ledger-only: exempt
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "feature-b")
    b = repo.add_task("From branch B")
    repo.commit_all("Track task B")
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "feature-a")
    r = repo.git("merge", "feature-b", check=False)
    assert r.returncode == 0, "parallel adds must merge without conflict"
    assert repo.task_file(a).exists() and repo.task_file(b).exists()
    rc, payload = validate(repo, "--coverage")
    assert rc == 0, payload


def test_merge_dual_log_appends_keep_both_resolution(repo):
    tid = repo.add_task("Shared")
    repo.commit_all("Track shared task")
    repo.git("checkout", "-q", "-b", "left")
    repo.j("note", tid, "left-side breadcrumb")
    repo.commit_all("Left note")
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "right")
    repo.j("note", tid, "right-side breadcrumb")
    repo.commit_all("Right note")
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "left")
    r = repo.git("merge", "right", check=False)
    if r.returncode != 0:
        # documented resolution: keep both sides' lines, drop the markers
        text = repo.read(tid)
        resolved = "\n".join(
            line for line in text.split("\n")
            if not line.startswith(("<<<<<<<", "=======", ">>>>>>>")))
        repo.write(tid, resolved)
        repo.git("add", "-A")
        repo.git("commit", "-q", "--no-edit")
    log_text = repo.read(tid)
    assert "left-side breadcrumb" in log_text
    assert "right-side breadcrumb" in log_text
    rc, payload = validate(repo, "--coverage")
    assert rc == 0, payload


def test_merge_header_conflict_bad_resolution_is_caught(repo):
    tid = repo.add_task("Header fight")
    repo.commit_all("Track header task")
    repo.git("checkout", "-q", "-b", "p0-side")
    repo.j("set", tid, "--priority", "p0")
    repo.commit_all("Escalate")
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "p3-side")
    repo.j("set", tid, "--priority", "p3")
    repo.commit_all("Deprioritize")
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "p0-side")
    r = repo.git("merge", "p3-side", check=False)
    assert r.returncode != 0, "same-line header edit should conflict visibly"
    # a lazy union-style resolution that keeps BOTH priority lines:
    text = repo.read(tid)
    resolved = "\n".join(
        line for line in text.split("\n")
        if not line.startswith(("<<<<<<<", "=======", ">>>>>>>")))
    repo.write(tid, resolved)
    rc, payload = validate(repo, "--no-git")
    assert rc == 1
    assert any(e["code"] == "parse" and "duplicate header key" in e["message"]
               for e in payload["errors"])


def test_log_tamper_detected(repo):
    tid = repo.add_task("Tamperproof")
    repo.j("note", tid, "load-bearing history line")
    repo.commit_all("Record history")
    # move the baseline so the tamper crosses baseline..HEAD
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["baseline"] = repo.git("rev-parse", "HEAD").stdout.strip()
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    repo.commit_all("Pin baseline", ("Ledger-Exempt: test setup",))

    text = "\n".join(line for line in repo.read(tid).split("\n")
                     if "load-bearing" not in line)
    repo.write(tid, text)
    repo.commit_all("Rewrite history quietly", ("Ledger-Exempt: cover-up",))
    rc, payload = validate(repo, "--coverage")
    tamper = [e for e in payload["errors"] if e["code"] == "log-tamper"]
    assert tamper and tamper[0]["task"] == tid


def test_empty_repo_init_and_first_commits(tmp_path, base_env):
    from conftest import LedgerRepo, _isolated_env
    lr = LedgerRepo(tmp_path / "fresh", _isolated_env(base_env, tmp_path))
    lr.root.mkdir()
    lr.git("init", "-q")
    d = lr.j("init")
    assert d["data"]["baseline"] is None
    tid = lr.add_task("Greenfield")
    rc, payload = validate(lr, "--coverage")
    assert rc == 0  # nothing committed yet: nothing to cover
    lr.commit_all("Bootstrap everything", ("Ledger-Exempt: ledger bootstrap",))
    (lr.root / "code.py").write_text("x\n", encoding="utf-8")
    lr.commit_all("First real work with no trailer")
    rc, payload = validate(lr, "--coverage")
    assert rc == 1 and "coverage" in codes(payload)


def test_shallow_clone_refused(repo, tmp_path):
    from conftest import LedgerRepo
    (repo.root / "k.txt").write_text("k\n", encoding="utf-8")
    repo.commit_all("More history", ("Ledger-Exempt: filler",))
    dest = tmp_path / "shallow"
    r = repo.git("clone", "-q", "--depth", "1",
                 repo.root.as_uri(), str(dest), check=False)
    if r.returncode != 0:
        pytest.skip("local shallow clone unsupported here")
    lr = LedgerRepo(dest, repo.env)
    rc, payload = validate(lr, "--coverage")
    assert rc == 1
    assert any(e["code"] == "coverage" and "shallow" in e["message"]
               for e in payload["errors"])


# --- coverage repair: explicit links count, multi-id trailers (T-5z04ex) ---

def test_link_repairs_a_pushed_untrailered_commit(repo):
    tid = repo.add_task("Forgot the trailer")
    repo.j("claim", tid)
    (repo.root / "oops.py").write_text("x\n", encoding="utf-8")
    sha = repo.commit_all("Work without a trailer")
    rc, payload = validate(repo, "--coverage")
    cov = [e for e in payload["errors"] if e["code"] == "coverage"]
    assert rc == 1 and cov
    hint = cov[0]["fix_hint"]
    assert "amend" in hint and f"ledger link <id> {sha[:7]}" in hint
    assert "ledger add" in hint and "never for code without a task" in hint
    repo.j("link", tid, sha)  # the repair the protocol promises
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    d = repo.j("scan")["data"]
    assert {"sha": sha[:7], "task": tid, "via": "link"} in d["linked"]
    assert d["unlinked"] == []
    # a ## Commits line alone (hand-edited cache, no link: Log line) is NOT
    # coverage — both halves of the explicit link are required
    other = repo.add_task("Hand-edited commits cache")
    (repo.root / "oops2.py").write_text("y\n", encoding="utf-8")
    sha2 = repo.commit_all("Second untrailered")
    repo.write(other, repo.read(other).replace(
        "## Commits", f"## Commits\n\n- {sha2[:7]} 2026-01-01 forged"))
    rc, payload = validate(repo, "--coverage")
    assert any(e["code"] == "coverage" and sha2[:7] in e["message"]
               for e in payload["errors"])


def test_done_commit_link_counts_as_coverage(repo):
    tid = repo.add_task("Closed via --commit")
    repo.j("claim", tid)
    (repo.root / "w.py").write_text("w\n", encoding="utf-8")
    repo.commit_all("Untrailered but closed with --commit HEAD")
    repo.j("done", tid, "--commit", "HEAD")
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]


def test_multi_id_trailer_line_is_diagnosed_never_linked(repo):
    a = repo.add_task("A side")
    b = repo.add_task("B side")
    (repo.root / "m.py").write_text("m\n", encoding="utf-8")
    sha = repo.commit_all("Two ids on one line", (f"Ledger-Task: {a}, {b}",))
    rc, payload = validate(repo, "--coverage")
    dang = [e for e in payload["errors"] if e["code"] == "trailer-dangling"]
    assert len(dang) == 1 and "several" in dang[0]["message"]
    assert "one 'Ledger-Task: <id>' line per task" in dang[0]["fix_hint"]
    assert "ledger link" in dang[0]["fix_hint"]
    d = repo.j("scan")["data"]
    assert d["linked"] == []  # tokens are diagnostics, never linkage
    assert d["dangling"] == [{"sha": sha[:7], "id": f"{a}, {b}",
                              "hint": "multi-id-line"}]
    refused = repo.j("done", a, expect=2)
    assert refused["errors"][0]["code"] == "done-evidence"
    # the repair: an explicit link supersedes the dangling line
    repo.j("link", a, sha)
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]


def test_trailer_with_extra_text_and_exempt_line_still_dangles(repo):
    a = repo.add_task("Partial")
    (repo.root / "p.py").write_text("p\n", encoding="utf-8")
    repo.commit_all("Extra text", (f"Ledger-Task: {a} (partial)",))
    rc, payload = validate(repo, "--coverage")
    dang = [e for e in payload["errors"] if e["code"] == "trailer-dangling"]
    assert len(dang) == 1 and "extra text" in dang[0]["message"]
    assert "several" not in dang[0]["message"]
    assert f"exactly 'Ledger-Task: {a}'" in dang[0]["fix_hint"]
    assert repo.j("scan")["data"]["dangling"][0]["hint"] == "extra-text"
    # Ledger-Exempt clears coverage for the commit but not the dangling id
    (repo.root / "q.py").write_text("q\n", encoding="utf-8")
    # both lines in ONE final paragraph (separate -m args would make only
    # the last paragraph count, per git trailer semantics)
    repo.commit_all("Exempt with a ghost",
                    ("Ledger-Task: T-gh0st9\nLedger-Exempt: fixture",))
    rc, payload = validate(repo, "--coverage")
    codes_seen = codes(payload)
    assert "trailer-dangling" in codes_seen
    assert not any(e["code"] == "coverage" and "ghost" in e["message"].lower()
                   for e in payload["errors"])
    unknown = [e for e in payload["errors"] if e["code"] == "trailer-dangling"
               and "T-gh0st9" in e["message"]]
    assert unknown and "restore it from git history" in unknown[0]["fix_hint"]



def test_deleting_a_dead_end_note_is_tampering(repo):
    tid = repo.add_task("Lessons")
    repo.j("note", tid, "the cache route deadlocks", "--dead-end")
    repo.commit_all("Track lessons")
    text = "\n".join(line for line in repo.read(tid).split("\n")
                     if "deadlocks" not in line)
    repo.write(tid, text)
    repo.commit_all("Forget the lesson", ("Ledger-Exempt: cover-up",))
    rc, payload = validate(repo, "--coverage")
    assert any(e["code"] == "log-tamper" and e["task"] == tid
               for e in payload["errors"]), payload["errors"]
