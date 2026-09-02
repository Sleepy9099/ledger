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
    # the repo fixture carries init's exempt_allowed_paths default, so the
    # explicit exemption must touch an allowed path (*.md)
    (repo.root / "notes.md").write_text("a\n", encoding="utf-8")
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
    hint = [e for e in payload["errors"]
            if e["code"] == "linked-never-claimed"][0]["fix_hint"]
    # the commit has landed: the hint must name the remedy for THAT state
    assert f"ledger claim {tid}" in hint and "release" in hint
    repo.j("claim", tid)
    repo.j("release", tid, "--note", "recorded after the fact")
    rc, payload = validate(repo, "--strict")
    assert rc == 0 and "linked-never-claimed" not in codes(payload)


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
    assert rc == 1 and tamper[0]["severity"] == "error"  # git-verified fact


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



def test_wave_as_task_end_to_end(repo):
    """The wave convention (DESIGN §8): members + a wave task, orchestrator
    claim, trailered member commits, an integration merge carrying the wave
    trailer, done --commit HEAD, strict validate clean, scan links the
    merge, and both reverse lookups answer."""
    m1 = repo.add_task("Member one", "--tag", "wave:w1")
    m2 = repo.add_task("Member two", "--tag", "wave:w1")
    w = repo.j("add", "Wave 1: ship the parser", "-p", "p1", "-s", "s",
               "--tag", "wave", "--tag", "wave:w1", "--after", m1,
               "--after", m2)["data"]["id"]
    repo.j("claim", w, "--session", "orchestrator")  # wave open
    for m, name in ((m1, "one"), (m2, "two")):
        repo.j("claim", m, "--session", f"worker-{name}")
        (repo.root / f"{name}.py").write_text("x\n", encoding="utf-8")
        repo.commit_all(f"Implement member {name}", (f"Ledger-Task: {m}",))
        repo.j("done", m, "--session", f"worker-{name}")
    # a worker's next never sees the open wave: the orchestrator holds it
    n = repo.j("next", "--session", "worker-three")["data"]
    assert n["task"] is None
    assert any(x["id"] == w and "claimed by orchestrator" in
               x["ineligible_because"] for x in n["why"])
    repo.git("checkout", "-q", "-b", "integration")
    (repo.root / "glue.py").write_text("g\n", encoding="utf-8")
    repo.commit_all("Wire members together", (f"Ledger-Task: {w}",))
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "--no-ff", "--no-commit", "integration")
    repo.git("commit", "-q", "-m", "Integrate wave 1", "-m",
             f"Ledger-Task: {w}")
    merge_sha = repo.git("rev-parse", "HEAD").stdout.strip()
    d = repo.j("done", w, "--commit", "HEAD", "--session", "orchestrator")
    assert d["ok"]
    assert not any("depends_on" in e["message"] for e in d["errors"])
    repo.j("note", w, "suite: green; workers: 2; anomalies: none",
           "--session", "orchestrator")  # the wave record, after close
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    scan = repo.j("scan")["data"]
    assert any(x["sha"] == merge_sha[:7] and x["task"] == w
               for x in scan["linked"])
    assert repo.j("show", m1)["data"]["dependents"] == [w]
    rows = repo.j("list", "--depends-on", m1, "--tag", "wave")["data"]["tasks"]
    assert [t["id"] for t in rows] == [w]
    population = {t["id"] for t in repo.j("list", "--tag", "wave:w1")[
        "data"]["tasks"]}
    assert population == {m1, m2, w}



# --- exempt path policy (T-zl7jh5) -------------------------------------------

def _set_policy(repo, globs):
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if globs is None:
        cfg.pop("exempt_allowed_paths", None)
    else:
        cfg["exempt_allowed_paths"] = globs
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def test_init_default_policy_and_bootstrap_stay_clean(repo):
    cfg = json.loads((repo.root / ".ledger" / "config.json").read_text(
        encoding="utf-8"))
    assert "docs/**" in cfg["exempt_allowed_paths"]
    assert "tests/test_ledger.py" in cfg["exempt_allowed_paths"]
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]  # the bootstrap commit passes


def test_exempt_commit_outside_policy_is_flagged_not_uncovered(repo):
    (repo.root / "src").mkdir()
    (repo.root / "src" / "app.py").write_text("x\n", encoding="utf-8")
    (repo.root / "docs").mkdir()
    (repo.root / "docs" / "guide.md").write_text("g\n", encoding="utf-8")
    sha = repo.commit_all("Sneak code in", ("Ledger-Exempt: misc",))
    rc, payload = validate(repo, "--coverage")
    assert rc == 1
    pol = [e for e in payload["errors"] if e["code"] == "exempt-policy"]
    assert len(pol) == 1 and sha[:7] in pol[0]["message"]
    assert "src/app.py" in pol[0]["message"]
    assert "docs/guide.md" not in pol[0]["message"]
    assert "ledger add" in pol[0]["fix_hint"] and "HUMAN" in pol[0]["fix_hint"]
    assert "coverage" not in codes(payload)  # never both for one commit
    d = repo.j("scan")["data"]
    assert sha[:7] in d["exempt"]  # still in the exempt bucket
    assert d["exempt_policy_violations"] == [{"sha": sha[:7],
                                              "paths": ["src/app.py"]}]
    # docs-only exemption passes; without the key the policy is off
    (repo.root / "docs" / "more.md").write_text("m\n", encoding="utf-8")
    repo.commit_all("Docs only", ("Ledger-Exempt: docs",))
    rc, payload = validate(repo, "--coverage")
    assert [e for e in payload["errors"] if e["code"] == "exempt-policy"
            and "more.md" in e["message"]] == []
    _set_policy(repo, None)
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]


def test_glob_semantics_and_config_validation(repo):
    (repo.root / "deep" / "er").mkdir(parents=True)
    (repo.root / "deep" / "er" / "README.md").write_text("r\n", encoding="utf-8")
    (repo.root / "deep" / "er" / "LICENSE.txt").write_text("l\n", encoding="utf-8")
    (repo.root / "gen").mkdir()
    (repo.root / "gen" / "out.lock").write_text("o\n", encoding="utf-8")
    repo.commit_all("Basename globs at any depth", ("Ledger-Exempt: meta",))
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    _set_policy(repo, ["build/*.js"])
    (repo.root / "build").mkdir()
    (repo.root / "build" / "a.js").write_text("a\n", encoding="utf-8")
    (repo.root / "build" / "sub").mkdir()
    (repo.root / "build" / "sub" / "b.js").write_text("b\n", encoding="utf-8")
    sha = repo.commit_all("Path glob is exact", ("Ledger-Exempt: build",))
    rc, payload = validate(repo, "--coverage")
    pol = [e for e in payload["errors"] if e["code"] == "exempt-policy"]
    assert any(sha[:7] in e["message"] and "build/sub/b.js" in e["message"]
               and "build/a.js" not in e["message"] for e in pol)
    _set_policy(repo, ["docs/**", 7])
    for call in (("validate", "--coverage"), ("scan",)):
        r = repo.run(*call, "--json")
        assert r.returncode == 2
        assert json.loads(r.stdout)["errors"][0]["code"] == "config"


def test_pattern_exempt_true_merge_is_path_checked_squash_is_not(repo):
    # clean merge: --cc lists nothing -> exempt, no violation
    repo.git("checkout", "-q", "-b", "clean")
    (repo.root / "docs").mkdir()
    (repo.root / "docs" / "c.md").write_text("c\n", encoding="utf-8")
    repo.commit_all("Docs on a branch", ("Ledger-Exempt: docs",))
    repo.git("checkout", "-q", "main")
    (repo.root / "docs").mkdir(exist_ok=True)  # only existed on the branch
    (repo.root / "docs" / "m.md").write_text("m\n", encoding="utf-8")
    repo.commit_all("Docs on main", ("Ledger-Exempt: docs",))
    repo.git("merge", "-q", "--no-ff", "clean", "-m", "Merge branch 'clean'")
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    # evil merge under the ^Merge pattern: the resolution content is checked
    repo.git("checkout", "-q", "-b", "side")
    (repo.root / "conflict.py").write_text("side\n", encoding="utf-8")
    repo.commit_all("Side change", ("Ledger-Exempt: docs",))  # (also flagged)
    repo.git("checkout", "-q", "main")
    (repo.root / "conflict.py").write_text("main\n", encoding="utf-8")
    repo.commit_all("Main change", ("Ledger-Exempt: docs",))
    r = repo.git("merge", "side", check=False)
    assert r.returncode != 0
    (repo.root / "conflict.py").write_text("evil\n", encoding="utf-8")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "Merge branch 'side' into main")
    merge_sha = repo.git("rev-parse", "HEAD").stdout.strip()
    rc, payload = validate(repo, "--coverage")
    pol = [e for e in payload["errors"] if e["code"] == "exempt-policy"]
    assert any(merge_sha[:7] in e["message"] and "conflict.py" in e["message"]
               for e in pol)
    assert not any(e["code"] == "coverage" and merge_sha[:7] in e["message"]
                   for e in payload["errors"])
    # a single-parent commit whose subject matches ^Merge (squash) stays
    # exempt and unchecked: the documented gap
    (repo.root / "squashed.py").write_text("s\n", encoding="utf-8")
    squash = repo.commit_all("Merge pull request #7 from feature")
    rc, payload = validate(repo, "--coverage")
    assert not any(squash[:7] in e["message"] for e in payload["errors"])


def test_non_ascii_paths_are_matched_unquoted(repo):
    (repo.root / "docs").mkdir()
    (repo.root / "docs" / "ä.md").write_text("ä\n", encoding="utf-8")
    repo.commit_all("Unicode docs", ("Ledger-Exempt: docs",))
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    (repo.root / "src").mkdir()
    (repo.root / "src" / "ä.py").write_text("ä\n", encoding="utf-8")
    repo.commit_all("Unicode code", ("Ledger-Exempt: nope",))
    rc, payload = validate(repo, "--coverage")
    pol = [e for e in payload["errors"] if e["code"] == "exempt-policy"]
    assert pol and "src/ä.py" in pol[-1]["message"]



# --- exemption-policy migration (T-6zi51x) -----------------------------------

def _set_policy_since(repo, sha):
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["exempt_policy_since"] = sha
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def test_policy_since_is_forward_only(repo):
    (repo.root / "src").mkdir()
    (repo.root / "src" / "old.py").write_text("o\n", encoding="utf-8")
    old = repo.commit_all("Old exempt code", ("Ledger-Exempt: legacy",))
    rc, payload = validate(repo, "--coverage")
    assert any(e["code"] == "exempt-policy" and old[:7] in e["message"]
               for e in payload["errors"])
    _set_policy_since(repo, old)  # adopt the policy from here on
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    (repo.root / "src" / "new.py").write_text("n\n", encoding="utf-8")
    new = repo.commit_all("New exempt code", ("Ledger-Exempt: still legacy",))
    rc, payload = validate(repo, "--coverage")
    pol = [e for e in payload["errors"] if e["code"] == "exempt-policy"]
    assert [new[:7] in e["message"] for e in pol] == [True]
    assert repo.j("scan")["data"]["exempt_policy_violations"][0]["sha"] == new[:7]


def test_doctor_reports_policy_and_init_enables_it_forward_only(repo):
    _set_policy(repo, None)
    d = repo.j("doctor")
    assert d["data"]["exempt_policy"] == {"active": False, "since": None,
                                          "globs": None}
    off = [e for e in d["errors"] if e["code"] == "exempt-policy-off"]
    assert off and off[0]["severity"] == "warning"
    assert "--enable-exempt-policy" in off[0]["fix_hint"]
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg_before = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg_before["stale_claim_days"] = 3  # an unrelated key must survive
    cfg_path.write_text(json.dumps(cfg_before, indent=2), encoding="utf-8")
    head = repo.git("rev-parse", "HEAD").stdout.strip()
    d = repo.j("init", "--enable-exempt-policy")
    assert d["data"]["exempt_policy"]["active"] is True
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["exempt_policy_since"] == head
    assert "docs/**" in cfg["exempt_allowed_paths"]
    assert cfg["stale_claim_days"] == 3
    after = cfg_path.read_bytes()
    repo.j("init", "--enable-exempt-policy")  # idempotent
    assert cfg_path.read_bytes() == after
    d = repo.j("doctor")
    assert d["data"]["exempt_policy"]["since"] == head
    assert not any(e["code"] == "exempt-policy-off" for e in d["errors"])
    # plain re-init never touches config.json
    repo.j("init")
    assert cfg_path.read_bytes() == after


def test_only_bookkeeping_paths_are_implicitly_exempt(repo):
    ledger_py = repo.root / ".ledger" / "ledger.py"
    ledger_py.write_text(ledger_py.read_text(encoding="utf-8")
                         + "\n# tweak\n", encoding="utf-8", newline="\n")
    sha = repo.commit_all("Tweak the vendored tool")  # untrailered
    rc, payload = validate(repo, "--coverage")
    assert any(e["code"] == "coverage" and sha[:7] in e["message"]
               for e in payload["errors"])
    d = repo.j("scan")["data"]
    assert any(u["sha"] == sha[:7] for u in d["unlinked"])
    repo.j("add", "Bookkeeping only")
    tasks_only = repo.commit_all("Record a task")
    d = repo.j("scan")["data"]
    assert tasks_only[:7] in d["exempt"]
    assert d["exempt_by_channel"]["bookkeeping"] >= 1
    rc, payload = validate(repo, "--coverage")
    ratio = [e for e in payload["errors"] if e["code"] == "exempt-ratio"][0]
    assert "bookkeeping" in ratio["message"] and "trailer" in ratio["message"]
    # re-vendoring under an exemption is NOT allowed by the policy: a
    # modified ledger.py or config.json is code / policy work (a task)
    ledger_py.write_text(ledger_py.read_text(encoding="utf-8")
                         + "# tweak 2\n", encoding="utf-8", newline="\n")
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["exempt_patterns"] = cfg["exempt_patterns"] + ["."]  # the attack
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    attack = repo.commit_all("Housekeeping", ("Ledger-Exempt: housekeeping",))
    rc, payload = validate(repo, "--coverage")
    pol = [e for e in payload["errors"] if e["code"] == "exempt-policy"
           and attack[:7] in e["message"]]
    assert pol and ".ledger/ledger.py" in pol[0]["message"]
    assert ".ledger/config.json" in pol[0]["message"]
    # ...while the fixture's bootstrap commit, which CREATED them, is clean
    cfg["exempt_patterns"] = cfg["exempt_patterns"][:-1]
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    task = repo.add_task("Re-vendor ledger.py")
    repo.commit_all("Re-vendor ledger.py under a task", (f"Ledger-Task: {task}",))
    rc, payload = validate(repo, "--coverage")
    assert not any(e["code"] == "exempt-policy" and "Re-vendor" in e["message"]
                   for e in payload["errors"])



def test_sha_unreachable_asks_head_reachability_not_local_existence(repo):
    """After a history rewrite the old commit still resolves on the machine
    that rewrote it (reflog) but in no clone; the gate must agree with the
    clone, not with the rewriter."""
    tid = repo.add_task("Rewritten history")
    (repo.root / "r.py").write_text("r\n", encoding="utf-8")
    old = repo.commit_all("Work", (f"Ledger-Task: {tid}",))
    repo.j("link", tid, "HEAD")
    rc, payload = validate(repo)
    assert "sha-unreachable" not in codes(payload)
    repo.git("commit", "-q", "--amend", "-m", "Work (amended)", "-m",
             f"Ledger-Task: {tid}")
    repo.git("cat-file", "-e", old)  # still in the local object store
    rc, payload = validate(repo)
    unreachable = [e for e in payload["errors"] if e["code"] == "sha-unreachable"]
    assert [e["task"] for e in unreachable] == [tid]
    assert "not reachable from any branch" in unreachable[0]["message"]
    assert "scan --prune" in unreachable[0]["fix_hint"]
    assert repo.j("show", tid)["data"]["commits"][0]["sha"] == old[:7]



# --- scan --prune and unlink (T-nxww2u) --------------------------------------

def test_scan_prune_drops_dead_pointers_and_journals_each(repo):
    a = repo.add_task("Rewritten A")
    b = repo.add_task("Rewritten B")
    repo.j("claim", a)
    repo.j("claim", b)
    base = repo.commit_all("Track tasks")  # bookkeeping
    (repo.root / "a.py").write_text("a", encoding="utf-8")
    old_a = repo.commit_all("Work A", (f"Ledger-Task: {a}",))
    (repo.root / "b.py").write_text("b", encoding="utf-8")
    old_b = repo.commit_all("Work B", (f"Ledger-Task: {b}",))
    repo.j("link", a, old_a)
    repo.j("link", b, old_b)
    # the rewrite: squash both work commits into one new commit (the old
    # shas survive only in the reflog; the task files still cite them)
    repo.git("reset", "-q", "--soft", base)
    squashed = repo.commit_all("Work A+B (rewritten)",
                               (f"Ledger-Task: {a}\nLedger-Task: {b}",))
    rc, payload = validate(repo)
    dead = {e["task"] for e in payload["errors"] if e["code"] == "sha-unreachable"}
    assert dead == {a, b}  # both cited shas died in the rewrite
    d = repo.j("scan", "--write")["data"]  # --write alone never removes
    assert d["pruned"] == [] and old_a[:7] in repo.read(a)
    d = repo.j("scan", "--prune")["data"]
    pruned = {(p["task"], p["sha"]) for p in d["pruned"]}
    assert pruned == {(a, old_a[:7]), (b, old_b[:7])}
    assert old_a[:7] not in repo.read(a).split("## Log")[0]
    log_a = repo.j("show", a)["data"]["log"]
    assert log_a[-1]["verb"] == "unlink" and old_a[:7] in log_a[-1]["text"]
    assert "history rewrite" in log_a[-1]["text"]
    # --prune implies --write: the live trailer link was re-materialized
    assert squashed[:7] in repo.read(a) and squashed[:7] in repo.read(b)
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]
    assert repo.j("scan", "--prune")["data"]["pruned"] == []  # idempotent


def test_unlink_is_explicit_journaled_and_loud(repo):
    tid = repo.add_task("Evidence removal")
    repo.j("claim", tid)
    (repo.root / "u.py").write_text("u\n", encoding="utf-8")
    sha = repo.commit_all("Untrailered work")
    repo.j("done", tid, "--commit", "HEAD")
    missing = repo.j("unlink", tid, "0000000", expect=2)
    assert missing["errors"][0]["code"] == "no-such-commit-line"
    d = repo.j("unlink", tid, sha, "--why", "linked the wrong task")
    assert d["data"]["unlinked"] == [sha[:7]] and d["data"]["commits"] == []
    log = repo.j("show", tid)["data"]["log"]
    assert log[-1]["verb"] == "unlink"
    assert log[-1]["text"] == f"{sha[:7]} linked the wrong task"
    rc, payload = validate(repo, "--coverage")  # loud on both sides
    assert "done-evidence" in codes(payload)
    assert any(e["code"] == "coverage" and sha[:7] in e["message"]
               for e in payload["errors"])



def test_exempt_policy_preview_is_a_dry_run(repo):
    (repo.root / "src").mkdir()
    (repo.root / "src" / "x.py").write_text("x\n", encoding="utf-8")
    (repo.root / "gen.lock").write_text("l\n", encoding="utf-8")
    sha = repo.commit_all("Exempt with code", ("Ledger-Exempt: misc",))
    (repo.root / "docs").mkdir()
    (repo.root / "docs" / "d.md").write_text("d\n", encoding="utf-8")
    repo.commit_all("Exempt docs", ("Ledger-Exempt: docs",))
    _set_policy(repo, None)  # policy off: the preview uses the defaults
    d = repo.j("scan", "--exempt-policy-preview")["data"]
    pv = d["exempt_policy_preview"]
    assert pv["policy_active"] is False and pv["would_violate"] == 1
    assert pv["commits"][0]["sha"] == sha[:7]
    assert pv["commits"][0]["paths"] == ["src/x.py"]  # gen.lock is allowed
    assert "forward-only" in pv["note"]
    assert "docs/**" in pv["globs"]
    r = repo.run("scan", "--exempt-policy-preview")
    assert "would violate" in r.stdout
    # the preview ignores exempt_policy_since: the switch is what it measures
    _set_policy(repo, ["docs/**", "*.md", ".gitignore", ".gitattributes"])
    _set_policy_since(repo, repo.git("rev-parse", "HEAD").stdout.strip())
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]  # forward-only: nothing checked yet
    pv = repo.j("scan", "--exempt-policy-preview")["data"]["exempt_policy_preview"]
    assert pv["policy_active"] is True and pv["would_violate"] == 1
    assert pv["globs"][0] == ".ledger/tasks/**" and "docs/**" in pv["globs"]
    assert "exempt_policy_preview" not in repo.j("scan")["data"]  # opt-in
    off = [e for e in repo.j("doctor")["errors"] if e["code"] == "exempt-policy-off"]
    assert off == []
    _set_policy(repo, None)
    off = [e for e in repo.j("doctor")["errors"] if e["code"] == "exempt-policy-off"]
    assert "--exempt-policy-preview" in off[0]["fix_hint"]



# --- prune safety (sweep 2026-09-02, task A) --------------------------------

def test_prune_refuses_on_shallow_clones(repo, tmp_path):
    from conftest import LedgerRepo
    (repo.root / "k.py").write_text("k\n", encoding="utf-8")
    repo.commit_all("More history", ("Ledger-Exempt: filler",))
    dest = tmp_path / "shallow-prune"
    r = repo.git("clone", "-q", "--depth", "1", repo.root.as_uri(), str(dest),
                 check=False)
    if r.returncode != 0:
        pytest.skip("local shallow clone unsupported here")
    lr = LedgerRepo(dest, repo.env)
    cfg_path = dest / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["baseline"] = None
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    d = lr.j("scan", "--prune", expect=2)
    assert d["errors"][0]["code"] == "coverage"
    assert "shallow" in d["errors"][0]["message"]


def test_prune_keeps_evidence_that_lives_on_another_branch(repo):
    tid = repo.add_task("Worker task")
    repo.j("claim", tid, "--session", "worker")
    repo.commit_all("Track worker task")
    repo.git("checkout", "-q", "-b", "worker")
    (repo.root / "w.py").write_text("w\n", encoding="utf-8")
    sha = repo.commit_all("Worker work", (f"Ledger-Task: {tid}",))
    repo.j("link", tid, "HEAD")
    repo.commit_all("Record link")
    # carry only the task file to main (the way an orchestrator merges
    # bookkeeping before code lands)
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "worker", "--", f".ledger/tasks/{tid}.md")
    repo.commit_all("Sync task file")
    rc, payload = validate(repo)
    assert "sha-unreachable" not in codes(payload)  # the branch is a ref
    d = repo.j("scan", "--prune")["data"]
    assert d["pruned"] == [] and sha[:7] in repo.read(tid)


def test_prune_never_strips_a_done_tasks_last_evidence(repo):
    tid = repo.add_task("Squashed later")
    repo.j("claim", tid)
    base = repo.commit_all("Track task")
    (repo.root / "s.py").write_text("s\n", encoding="utf-8")
    old = repo.commit_all("Implement squashed feature", (f"Ledger-Task: {tid}",))
    repo.j("done", tid, "--commit", "HEAD")
    # a squash merge: the trailer ends up mid-body, the old sha disappears
    repo.git("reset", "-q", "--soft", base)
    squash = repo.commit_all("Implement squashed feature",
                             (f"* Implement squashed feature\n\nLedger-Task: {tid}",
                              "Reviewed-by: someone"))
    d = repo.j("scan", "--prune", expect=1)
    assert d["ok"] is False and d["data"]["pruned"] == []
    refused = d["data"]["prune_refused"]
    assert refused == [{"task": tid, "sha": old[:7],
                        "replacement_candidates": [squash[:7]]}]
    row = [e for e in d["errors"] if e["code"] == "prune-refused"][0]
    assert f"ledger link {tid}" in row["fix_hint"] and squash[:7] in row["fix_hint"]
    assert old[:7] in repo.read(tid)  # untouched
    # the agent confirms the candidate: then prune cleans up
    repo.j("link", tid, squash)
    d = repo.j("scan", "--prune")["data"]
    assert d["pruned"] == [{"task": tid, "sha": old[:7]}]
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]



def test_validate_scan_report_spawn_no_per_commit_diff_tree(ledger_mod, repo,
                                                            monkeypatch, capsys):
    """One name-status pass replaces one diff-tree per classified commit;
    Ctx.repo is memoized (T-jqulvk)."""
    for i in range(6):
        (repo.root / f"c{i}.md").write_text(str(i), encoding="utf-8")
        repo.commit_all(f"Chore {i}", ("Ledger-Exempt: docs",))
    repo.j("add", "Bookkeeping only")
    repo.commit_all("Track a task")
    monkeypatch.chdir(repo.root)
    real = ledger_mod.run_git
    for argv in (["validate", "--coverage"], ["scan"], ["report"]):
        calls = []

        def counting(args, cwd):
            calls.append(" ".join(args[:6]))
            return real(args, cwd)
        monkeypatch.setattr(ledger_mod, "run_git", counting)
        ledger_mod._FILE_STATUS_CACHE.clear()
        args = ledger_mod.build_parser().parse_args(argv + ["--json", "--session", "t"])
        args.fn(args)
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"], (argv, payload["errors"])
        assert not any("diff-tree" in c for c in calls), (argv, calls)
        assert sum("show-toplevel" in c for c in calls) <= 1, (argv, calls)
