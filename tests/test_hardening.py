"""Regression tests for the adversarial-review findings."""
import json
import subprocess
import sys

import pytest

from test_format import CANONICAL


def validate(repo, *flags):
    r = repo.run("validate", *flags, "--json")
    return r.returncode, json.loads(r.stdout)


def codes(payload):
    return {e["code"] for e in payload["errors"]}


# --- fence-aware parsing & the round-trip write guard ----------------------

def test_fenced_h2_is_section_content(ledger_mod):
    task, _ = ledger_mod.parse_task(CANONICAL)
    fenced = ("Example task file:\n\n```markdown\n## Log\n- fake entry\n```\n\n"
              "end of spec")
    task.set_section("Spec", fenced)
    once = ledger_mod.serialize_task(task)
    reparsed, problems = ledger_mod.parse_task(once)
    assert problems == []
    assert "## Log\n- fake entry" in reparsed.get_section("Spec")
    # the REAL audit Log is intact, not shadowed by the fenced fake
    assert [e["verb"] for e in reparsed.log()] == [
        "add", "claim", "link", "release", "claim"]
    assert ledger_mod.serialize_task(reparsed) == once  # stable


def test_save_guard_refuses_reinterpreted_content(ledger_mod, tmp_path):
    task, _ = ledger_mod.parse_task(CANONICAL)
    task.path = tmp_path / "T-a3f9c2.md"
    task.set_section("Spec", "intro\n\n## Sneaky unfenced heading\n\nmore")
    with pytest.raises(ledger_mod.LedgerError) as exc:
        ledger_mod.save_task(task)
    assert exc.value.violation["code"] == "would-corrupt"
    assert not task.path.exists()


def test_add_refuses_unfenced_h2_spec(repo):
    r = repo.run("add", "Heading smuggler", "--spec",
                 "Real spec\n\n## Log\n- forged", "--json")
    assert r.returncode == 3
    payload = json.loads(r.stdout)
    assert payload["ok"] is False


def test_add_allows_fenced_example_and_log_survives(repo):
    d = repo.j("add", "Fenced example", "--spec", "-",
               input="Quote a task file:\n\n```\n## Log\n- fake\n```\n")
    tid = d["data"]["id"]
    repo.j("claim", tid)
    repo.j("note", tid, "still here")
    show = repo.j("show", tid)["data"]
    assert "## Log" in show["spec"]  # the fenced example survived
    verbs = [e["verb"] for e in show["log"]]
    assert verbs == ["add", "claim", "note"]  # the real Log was never shadowed
    rc, payload = validate(repo, "--no-git")
    assert rc == 0


# --- corrupt files are read-only -------------------------------------------

def test_mutation_refused_on_bad_merge_file(repo):
    tid = repo.add_task("Merge casualty")
    text = repo.read(tid)
    text = text.replace("status: todo", "status: todo\nstatus: in_progress")
    text = text + "\n## Log\n\n- 2026-01-01T00:00:00Z [other] note: theirs\n"
    repo.write(tid, text)
    before = repo.task_file(tid).read_bytes()

    refused = repo.j("note", tid, "launder attempt", expect=2)
    assert refused["errors"][0]["code"] == "corrupt-file"
    assert repo.task_file(tid).read_bytes() == before  # byte-identical

    assert repo.j("show", tid)["data"]["header"]["id"] == tid  # reads still work
    d = repo.j("next")["data"]  # and next refuses to hand it out
    assert d["task"] is None or d["task"]["header"]["id"] != tid
    assert any(w["id"] == tid and "structural" in w["ineligible_because"]
               for w in d["why"])


# --- input hardening -------------------------------------------------------

def test_add_refuses_empty_title_and_bad_tags(repo):
    assert repo.run("add", "   ").returncode == 3
    assert repo.run("add", "ok title", "--tag", "a,b").returncode == 3
    tid = repo.add_task("Titled")
    assert repo.run("set", tid, "--title", " ").returncode == 3
    assert repo.run("set", tid, "--add-tag", "x,y").returncode == 3


def test_stdin_spec_is_utf8_even_when_piped(repo):
    text = "Réglages: café — backoff ± 20%\n"
    r = subprocess.run(
        [sys.executable, str(repo.script), "add", "utf8 spec", "--spec", "-",
         "--json"],
        cwd=str(repo.root), env=repo.env, capture_output=True,
        input=text.encode("utf-8"))
    assert r.returncode == 0, r.stderr
    tid = json.loads(r.stdout.decode("utf-8"))["data"]["id"]
    spec = repo.j("show", tid)["data"]["spec"]
    assert "Réglages: café — backoff ± 20%" in spec
    assert "Ã" not in spec  # the mojibake signature


# --- eligibility & claim lifecycle -----------------------------------------

def set_stale_days(repo, days):
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["stale_claim_days"] = days
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def test_stale_claims_still_respect_eligibility_gates(repo):
    set_stale_days(repo, -1)  # every claim is instantly stale
    xl = repo.add_task("Stale whale", "-p", "p0", "-s", "xl")
    repo.j("claim", xl)
    dep = repo.add_task("Unmet dep", "-p", "p3")
    gated = repo.j("add", "Stale gated", "-p", "p0", "--after", dep)["data"]["id"]
    repo.j("claim", gated)
    fallback = repo.add_task("Fallback", "-p", "p3")

    d = repo.j("next")["data"]
    picked = d["task"]["header"]["id"]
    assert picked in (dep, fallback)  # never the xl or the dep-gated one
    why = {w["id"]: w["ineligible_because"] for w in d["why"]}
    assert "xl" in why[xl]
    assert dep in why[gated]


def test_self_stale_claim_refresh(repo):
    set_stale_days(repo, -1)
    tid = repo.add_task("Refresh me")
    repo.j("claim", tid)
    first = repo.j("show", tid)["data"]["header"]["claimed_at"]
    d = repo.j("claim", tid)  # self re-claim of a stale claim must refresh
    assert "already" not in d["data"]
    show = repo.j("show", tid)["data"]
    assert show["header"]["claimed_at"] >= first
    assert sum(1 for e in show["log"] if e["verb"] == "claim") == 2
    rc, payload = validate(repo, "--no-git", "--strict")
    assert "stale-claim" not in codes(payload) or rc == 1  # -1 keeps it stale
    set_stale_days(repo, 7)
    rc, payload = validate(repo, "--no-git", "--strict")
    assert rc == 0, payload  # refreshed claim is no longer stale


def test_release_foreign_fresh_claim_refused(repo):
    tid = repo.add_task("Guarded claim")
    repo.j("claim", tid)
    refused = repo.j("release", tid, "--session", "other", expect=2)
    assert refused["errors"][0]["code"] == "claim-held"
    repo.j("release", tid, "--session", "other", "--force")
    assert repo.j("show", tid)["data"]["header"]["status"] == "todo"


# --- git-layer hardening ----------------------------------------------------

def test_release_flow_passes_strict_validate(repo):
    """The protocol's own claim -> trailered commit -> release handoff must
    not trip linked-never-claimed in strict CI."""
    tid = repo.add_task("Handoff work")
    repo.j("claim", tid)
    (repo.root / "work.py").write_text("wip\n", encoding="utf-8")
    repo.commit_all("Advance the work", (f"Ledger-Task: {tid}",))
    repo.j("release", tid, "--note", "out of budget")
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]


def test_root_commit_without_trailer_fails_coverage(tmp_path, base_env):
    from conftest import LedgerRepo, _isolated_env
    lr = LedgerRepo(tmp_path / "root", _isolated_env(base_env, tmp_path))
    lr.root.mkdir()
    lr.git("init", "-q")
    lr.run("init")
    (lr.root / "app.py").write_text("x\n", encoding="utf-8")
    lr.commit_all("Initial import of the whole codebase")  # root commit, no trailer
    rc, payload = validate(lr, "--coverage")
    assert rc == 1
    assert "coverage" in codes(payload)


def test_deleted_task_file_detected(repo):
    tid = repo.add_task("Deletable")
    repo.commit_all("Track deletable")
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["baseline"] = repo.git("rev-parse", "HEAD").stdout.strip()
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    repo.task_file(tid).unlink()
    rc, payload = validate(repo, "--coverage")
    tamper = [e for e in payload["errors"] if e["code"] == "log-tamper"]
    assert any(e["task"] == tid and "deleted" in e["message"] for e in tamper)


def test_midbody_trailer_examples_are_not_claims(repo):
    (repo.root / "docs.md").write_text("how to\n", encoding="utf-8")
    repo.commit_all("Document the trailer convention",
                    ("Example:\nLedger-Task: T-abc123",
                     "Ledger-Exempt: docs about the ledger itself"))
    rc, payload = validate(repo, "--coverage")
    assert rc == 0, payload["errors"]
    assert "trailer-dangling" not in codes(payload)


def test_unreachable_baseline_plain_validate_ok(repo):
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["baseline"] = "0" * 40
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    rc, payload = validate(repo)
    assert rc == 0, payload["errors"]  # plain validate: no coverage error
    rc, payload = validate(repo, "--coverage")
    assert rc == 1 and "coverage" in codes(payload)


def test_merge_introducing_code_needs_trailer(repo):
    repo.git("checkout", "-q", "-b", "side")
    (repo.root / "conflict.txt").write_text("side\n", encoding="utf-8")
    repo.commit_all("Side change", ("Ledger-Exempt: fixture",))
    repo.git("checkout", "-q", "main")
    (repo.root / "conflict.txt").write_text("main\n", encoding="utf-8")
    repo.commit_all("Main change", ("Ledger-Exempt: fixture",))
    r = repo.git("merge", "side", check=False)
    assert r.returncode != 0
    (repo.root / "conflict.txt").write_text("resolved differently\n",
                                            encoding="utf-8")
    repo.git("add", "-A")
    # amend the merge subject so the ^Merge exempt pattern does not apply
    repo.git("commit", "-q", "-m", "Combine both sides with new content")
    rc, payload = validate(repo, "--coverage")
    assert rc == 1  # the evil-merge content is in coverage scope
    assert "coverage" in codes(payload)


# --- checkbox grammar net ---------------------------------------------------

def test_checkbox_lookalike_warned(repo):
    tid = repo.add_task("Gate me")
    text = repo.read(tid).replace(
        "## Open Questions\n",
        "## Open Questions\n\n- [] HUMAN: do not ship without signoff\n")
    repo.write(tid, text)
    rc, payload = validate(repo, "--no-git")
    assert rc == 0
    assert "checkbox-grammar" in codes(payload)
    rc, payload = validate(repo, "--no-git", "--strict")
    assert rc == 1


def test_drop_warns_about_open_dependents(repo):
    base = repo.add_task("Foundation")
    child = repo.j("add", "Child", "--after", base)["data"]["id"]
    d = repo.j("drop", base, "--why", "obsolete")
    warn = [e for e in d["errors"] if e["severity"] == "warning"]
    assert any(child in (e.get("task") or "") for e in warn)


# --- second verification round ----------------------------------------------

def test_scan_write_skips_corrupt_file_with_mismatched_stem(repo):
    """A broken file whose header id differs from its filename stem must not
    slip past scan --write's corruption skip."""
    victim = repo.root / ".ledger" / "tasks" / "T-aaaaaa.md"
    victim.write_text(
        "---\nid: T-bbbbbb\ntitle: Broken merge artifact\nstatus: todo\n"
        "priority: p2\nsize: m\ncreated: 2026-01-01T00:00:00Z\n---\n\n"
        "## Spec\n\n## Next Steps\n\n## Open Questions\n\n## Commits\n\n"
        "## Log\n\n- 2026-01-01T00:00:00Z [a] add: created\n\n## Log\n\n"
        "- 2026-01-02T00:00:00Z [b] note: PRECIOUS BREADCRUMB\n",
        encoding="utf-8", newline="\n")
    before = victim.read_bytes()
    repo.commit_all("Introduce broken file", ("Ledger-Task: T-bbbbbb",))
    repo.j("scan", "--write")
    assert victim.read_bytes() == before  # never rewritten


def test_save_guard_refuses_duplicate_known_sections(ledger_mod, tmp_path):
    task, _ = ledger_mod.parse_task(CANONICAL)
    task.path = tmp_path / "T-a3f9c2.md"
    task.sections.append(["Log", "- 2026-01-01T00:00:00Z [x] note: dupe"])
    with pytest.raises(ledger_mod.LedgerError) as exc:
        ledger_mod.save_task(task)
    assert exc.value.violation["code"] == "would-corrupt"


def test_done_and_drop_respect_foreign_fresh_claims(repo):
    tid = repo.add_task("Held tight")
    repo.j("claim", tid, "--session", "mallory")
    refused = repo.j("done", tid, "--no-code", "hijack", expect=2)
    assert any(e["code"] == "claim-held" for e in refused["errors"])
    refused = repo.j("drop", tid, "--why", "hijack", expect=2)
    assert any(e["code"] == "claim-held" for e in refused["errors"])
    assert repo.j("show", tid)["data"]["header"]["claimed_by"] == "mallory"
    d = repo.j("drop", tid, "--why", "authorized takeover", "--force")
    assert d["ok"]


def test_invalid_exempt_pattern_is_a_proper_error(repo):
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["exempt_patterns"] = ["("]
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    for call in (("scan",), ("validate", "--coverage")):
        r = repo.run(*call, "--json")
        assert r.returncode == 2, r.stdout + r.stderr
        payload = json.loads(r.stdout)  # envelope survives, no traceback
        assert payload["errors"][0]["code"] == "config"
        assert payload["errors"][0]["fix_hint"]


def test_uncommitted_log_line_deletion_detected(repo):
    tid = repo.add_task("Precommit tamper")
    repo.j("note", tid, "line that must survive")
    repo.commit_all("Track it")
    cfg_path = repo.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["baseline"] = repo.git("rev-parse", "HEAD").stdout.strip()
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    text = "\n".join(line for line in repo.read(tid).split("\n")
                     if "must survive" not in line)
    repo.write(tid, text)  # NOT committed
    rc, payload = validate(repo, "--coverage")
    assert any(e["code"] == "log-tamper" and e["task"] == tid
               for e in payload["errors"])


def test_blocked_on_self_refused_and_validated(repo):
    tid = repo.add_task("Self blocker")
    refused = repo.j("block", tid, "--on", tid, expect=2)
    assert refused["errors"][0]["code"] == "refs"
    # a self-block can still arrive via hand edit / merge: validate flags it
    repo.write(tid, repo.read(tid).replace(
        "status: todo", f"status: blocked\nblocked_on: {tid}"))
    rc, payload = validate(repo, "--no-git")
    assert rc == 1
    assert any(e["code"] == "refs" and "itself" in e["message"]
               for e in payload["errors"])


def test_closed_unclaimed_task_does_not_fail_strict_forever(repo):
    """Closing without ever claiming is a ceremony miss, not a permanent
    strict-CI failure — there is no retroactive claim to repair it with."""
    tid = repo.add_task("Quickie")
    (repo.root / "quick.py").write_text("q\n", encoding="utf-8")
    repo.commit_all("Quick fix", (f"Ledger-Task: {tid}",))
    rc, payload = validate(repo, "--coverage")
    assert "linked-never-claimed" in codes(payload)  # open: flagged
    repo.j("done", tid)
    rc, payload = validate(repo, "--coverage", "--strict")
    assert rc == 0, payload["errors"]  # closed: engagement recorded, repairable state


def test_add_then_delete_after_baseline_detected(repo):
    """The exact hole in net-diff detection: a Log line born after baseline
    and deleted in a later commit nets out of a baseline->now comparison.
    Commit-by-commit history verification must catch it."""
    tid = repo.add_task("Born after baseline")
    repo.j("note", tid, "ephemeral truth")
    repo.commit_all("Track task with note")
    text = "\n".join(line for line in repo.read(tid).split("\n")
                     if "ephemeral truth" not in line)
    repo.write(tid, text)
    repo.commit_all("Quietly drop the note", ("Ledger-Exempt: cover-up",))
    rc, payload = validate(repo, "--coverage")
    tamper = [e for e in payload["errors"] if e["code"] == "log-tamper"]
    assert any(e["task"] == tid and "in commit" in e["message"]
               for e in tamper), payload["errors"]


def test_committed_file_deletion_detected(repo):
    tid = repo.add_task("Doomed")
    repo.commit_all("Track doomed task")
    repo.git("rm", "-q", f".ledger/tasks/{tid}.md")
    repo.commit_all("Erase the task", ("Ledger-Exempt: cover-up",))
    rc, payload = validate(repo, "--coverage")
    tamper = [e for e in payload["errors"] if e["code"] == "log-tamper"]
    assert any(e["task"] == tid and "deleted in commit" in e["message"]
               for e in tamper), payload["errors"]


def test_merge_dropping_one_sides_log_detected(repo):
    tid = repo.add_task("Contested history")
    repo.commit_all("Track contested task")
    repo.git("checkout", "-q", "-b", "ours")
    repo.j("note", tid, "ours breadcrumb")
    repo.commit_all("Ours note")
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "theirs")
    repo.j("note", tid, "theirs breadcrumb")
    repo.commit_all("Theirs note")
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "ours")
    r = repo.git("merge", "theirs", check=False)
    # BAD resolution: keep only our side's Log line, drop theirs
    text = repo.read(tid)
    lines = [line for line in text.split("\n")
             if not line.startswith(("<<<<<<<", "=======", ">>>>>>>"))
             and "theirs breadcrumb" not in line]
    repo.write(tid, "\n".join(lines))
    repo.git("add", "-A")
    if r.returncode != 0:
        repo.git("commit", "-q", "--no-edit")
    else:
        repo.git("commit", "-q", "-m", "Merge cleanup",
                 "-m", "Ledger-Exempt: fixture")
    rc, payload = validate(repo, "--coverage")
    tamper = [e for e in payload["errors"] if e["code"] == "log-tamper"]
    assert any(e["task"] == tid and
               ("in merge" in e["message"] or "in commit" in e["message"])
               for e in tamper), payload["errors"]


def test_keep_both_merge_resolution_stays_clean(repo):
    tid = repo.add_task("Peaceful history")
    repo.commit_all("Track peaceful task")
    repo.git("checkout", "-q", "-b", "left2")
    repo.j("note", tid, "left line")
    repo.commit_all("Left note")
    repo.git("checkout", "-q", "main")
    repo.git("checkout", "-q", "-b", "right2")
    repo.j("note", tid, "right line")
    repo.commit_all("Right note")
    repo.git("checkout", "-q", "main")
    repo.git("merge", "-q", "left2")
    r = repo.git("merge", "right2", check=False)
    if r.returncode != 0:
        text = "\n".join(
            line for line in repo.read(tid).split("\n")
            if not line.startswith(("<<<<<<<", "=======", ">>>>>>>")))
        repo.write(tid, text)
        repo.git("add", "-A")
        repo.git("commit", "-q", "--no-edit")
    rc, payload = validate(repo, "--coverage")
    assert rc == 0, payload["errors"]
    assert not [e for e in payload["errors"] if e["code"] == "log-tamper"]


def test_unicode_prefix_tamper_detection(tmp_path, base_env):
    """core.quotePath octal-escaping must not blind the tamper checks."""
    from conftest import LedgerRepo, _isolated_env
    lr = LedgerRepo(tmp_path / "uni", _isolated_env(base_env, tmp_path))
    lr.root.mkdir()
    lr.git("init", "-q")
    (lr.root / "seed.txt").write_text("s\n", encoding="utf-8")
    lr.commit_all("initial")
    r = lr.run("init", "--prefix", "日")
    assert r.returncode == 0, r.stdout + r.stderr
    d = lr.j("add", "unicode prefixed task")
    tid = d["data"]["id"]
    assert tid.startswith("日-")
    lr.commit_all("Track unicode task", ("Ledger-Exempt: fixture",))
    cfg_path = lr.root / ".ledger" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["baseline"] = lr.git("rev-parse", "HEAD").stdout.strip()
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    lr.task_file(tid).unlink()
    r = lr.run("validate", "--coverage", "--json")
    payload = json.loads(r.stdout)
    assert any(e["code"] == "log-tamper" and "deleted" in e["message"]
               for e in payload["errors"]), payload["errors"]


# --- drop relations downstream (T-71aehi) ----------------------------------

def test_drop_relation_repoints_dependents_and_next_why(repo):
    survivor = repo.add_task("Survivor")
    dupe = repo.add_task("Dupe")
    child = repo.j("add", "Child", "--after", dupe)["data"]["id"]
    d = repo.j("drop", dupe, "--duplicate-of", survivor)
    warn = [e for e in d["errors"] if e.get("task") == child]
    assert warn and warn[0]["fix_hint"] == (
        f"ledger set {child} --remove-depends {dupe} --add-depends {survivor}")
    why = {w["id"]: w["ineligible_because"]
           for w in repo.j("next")["data"]["why"]}
    assert f"{dupe} (dropped, duplicate-of {survivor})" in why[child]
    # the dependent IS the survivor: no self-dependency is suggested
    other = repo.add_task("Other")
    sl = repo.j("add", "Survivor-like", "--after", other)["data"]["id"]
    d = repo.j("drop", other, "--superseded-by", sl)
    warn = [e for e in d["errors"] if e.get("task") == sl]
    assert warn and warn[0]["fix_hint"] == (
        f"ledger set {sl} --remove-depends {other}")
