"""Violation completeness: every validate code has a trigger and a clean pass."""
import json


def codes(payload, severity=None):
    out = set()
    for e in payload["errors"]:
        if severity is None or e["severity"] == severity:
            out.add(e["code"])
    return out


def validate(repo, *flags, expect=None):
    r = repo.run("validate", *flags, "--json")
    payload = json.loads(r.stdout)
    if expect is not None:
        assert r.returncode == expect, r.stdout
    return r.returncode, payload


def test_clean_ledger_validates(repo):
    repo.add_task("Innocent")
    rc, payload = validate(repo, expect=0)
    assert payload["ok"] and payload["data"]["error_count"] == 0


def test_encoding_crlf_and_bom_detected_then_repaired(repo):
    tid = repo.add_task("Enc")
    raw = repo.task_file(tid).read_bytes()
    repo.task_file(tid).write_bytes(b"\xef\xbb\xbf" + raw.replace(b"\n", b"\r\n"))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "encoding" in codes(payload)
    repo.j("note", tid, "any CLI write repairs encoding")
    validate(repo, "--no-git", expect=0)


def test_parse_duplicate_key(repo):
    tid = repo.add_task("Dup")
    repo.write(tid, repo.read(tid).replace(
        "priority: p2\n", "priority: p2\npriority: p0\n"))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "parse" in codes(payload)


def test_conflict_markers(repo):
    tid = repo.add_task("Conflicted")
    repo.write(tid, repo.read(tid).replace(
        "## Log", "<<<<<<< HEAD\n## Log"))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "conflict-markers" in codes(payload)


def test_id_filename_mismatch(repo):
    tid = repo.add_task("Renamed")
    target = repo.task_file(tid).with_name("T-zzz999.md")
    repo.task_file(tid).rename(target)
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "id-filename" in codes(payload)


def test_id_unique(repo):
    tid = repo.add_task("Original")
    clone = repo.task_file(tid).with_name("T-aaa111.md")
    clone.write_text(repo.read(tid), encoding="utf-8", newline="\n")
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "id-unique" in codes(payload)


def test_enums_and_timestamps(repo):
    tid = repo.add_task("Enums")
    repo.write(tid, repo.read(tid).replace("status: todo", "status: doing")
               .replace("priority: p2", "priority: P1")
               .replace("size: m", "size: huge"))
    rc, payload = validate(repo, "--no-git", expect=1)
    msgs = [e["message"] for e in payload["errors"] if e["code"] == "enums"]
    assert len(msgs) >= 3

    tid2 = repo.add_task("Times")
    repo.write(tid2, repo.read(tid2).replace(
        "created: 20", "created: not-a-timestamp\nclosed: 20", 1))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "enums" in codes(payload)


def test_refs_dangling_and_cycle(repo):
    a = repo.add_task("A")
    repo.write(a, repo.read(a).replace(
        f"id: {a}", f"id: {a}\ndepends_on: T-nope42"
    ).replace("depends_on: T-nope42", "depends_on: T-nope42", 1))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "refs" in codes(payload)
    repo.write(a, repo.read(a).replace("depends_on: T-nope42\n", ""))

    b = repo.add_task("B")
    repo.j("set", a, "--add-depends", b)
    refused = repo.j("set", b, "--add-depends", a, expect=2)  # CLI refuses cycles
    assert refused["errors"][0]["code"] == "refs"
    # a cycle can still arrive via merge: simulate with a hand edit
    repo.write(b, repo.read(b).replace(f"id: {b}", f"id: {b}\ndepends_on: {a}"))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert any(e["code"] == "refs" and "cycle" in e["message"]
               for e in payload["errors"])
    repo.write(b, repo.read(b).replace(f"\ndepends_on: {a}", ""))
    repo.j("set", a, "--remove-depends", b)

    c = repo.add_task("C")
    repo.write(c, repo.read(c).replace("status: todo", "status: blocked\n"
                                       "blocked_on: nonsense value"))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert any(e["code"] == "refs" and "blocked_on" in e["message"]
               for e in payload["errors"])


def test_state_coherence(repo):
    a = repo.add_task("NoClaim")
    repo.write(a, repo.read(a).replace("status: todo", "status: in_progress"))
    b = repo.add_task("HalfClaim")
    repo.write(b, repo.read(b).replace(
        f"id: {b}", f"id: {b}\nclaimed_by: ghost"))
    c = repo.add_task("BareBlocked")
    repo.write(c, repo.read(c).replace("status: todo", "status: blocked"))
    d = repo.add_task("FakeDone")
    repo.write(d, repo.read(d).replace("status: todo", "status: done"))
    e = repo.add_task("ClosedTodo")
    repo.write(e, repo.read(e).replace(
        f"id: {e}", f"id: {e}\nclosed: 2026-01-01T00:00:00Z").replace(
        "status: todo", "status: todo"))
    rc, payload = validate(repo, "--no-git", expect=1)
    sc = [x for x in payload["errors"] if x["code"] == "state-coherence"]
    tasks_flagged = {x["task"] for x in sc}
    assert {a, b, c, d, e} <= tasks_flagged


def test_done_evidence_and_human_questions(repo):
    tid = repo.add_task("Sneaky done")
    repo.j("question", tid, "add", "unanswered gate?", "--human")
    text = repo.read(tid).replace("status: todo", "status: done")
    text = text.replace("## Commits", "## Commits").replace(
        "## Log\n", "## Log\n\n- 2026-01-01T00:00:00Z [x] done: evidence: none\n")
    text = text.replace(f"id: {tid}", f"id: {tid}").replace(
        "created: ", "closed: 2027-01-01T00:00:00Z\ncreated: ")
    repo.write(tid, text)
    rc, payload = validate(repo, "--no-git", expect=1)
    assert "done-evidence" in codes(payload)
    assert "done-human-questions" in codes(payload)


def test_warning_tier_and_strict_promotion(repo):
    # stale claim: rewrite claim + log timestamps into the distant past
    tid = repo.add_task("Stale")
    repo.j("claim", tid)
    text = repo.read(tid)
    for ts_fragment in ("2026-", "2027-", "2028-"):
        text = text.replace(ts_fragment, "2020-")
    repo.write(tid, text)
    xl = repo.add_task("Whale", "-s", "xl")
    loose = repo.add_task("Loose done")
    repo.j("done", loose, "--no-code", "meh")
    repo.write(loose, repo.read(loose).replace(  # done refuses this: hand-edit
        "## Next Steps\n", "## Next Steps\n\n- [ ] left unchecked\n"))
    unknown = repo.add_task("Typo")
    repo.write(unknown, repo.read(unknown).replace(
        f"id: {unknown}", f"id: {unknown}\npriorty: p1"))

    rc, payload = validate(repo, "--no-git", expect=0)  # warnings only
    warns = codes(payload, "warning")
    assert {"stale-claim", "xl-open", "done-loose-ends", "unknown-key"} <= warns

    rc, payload = validate(repo, "--no-git", "--strict", expect=1)
    assert {"stale-claim", "xl-open", "done-loose-ends", "unknown-key"} <= codes(
        payload, "error")


def test_validate_no_git_in_plain_tree(plain):
    plain.add_task("Offline")
    rc, payload = validate(plain, "--no-git", expect=0)
    assert payload["ok"]
    # coverage without git must refuse loudly rather than pass vacuously
    rc, payload = validate(plain, "--coverage", expect=1)
    assert "coverage" in codes(payload)


def test_validation_code_table_is_stable(ledger_mod):
    assert set(ledger_mod.VALIDATION_CODES) == {
        "encoding", "parse", "conflict-markers", "id-filename", "id-unique",
        "enums", "refs", "state-coherence", "done-evidence",
        "done-human-questions", "coverage", "trailer-dangling",
        "exempt-policy", "stale-claim", "stale-block",
        "xl-open", "checkbox-grammar", "done-loose-ends", "unknown-key",
        "sha-unreachable", "linked-never-claimed", "log-tamper",
        "unknown-section",
        "exempt-ratio", "resource-contention",
    }
    assert ledger_mod.VALIDATION_CODES["exempt-ratio"] == "info"
    assert ledger_mod.VALIDATION_CODES["resource-contention"] == "info"



def test_dead_end_notes_never_affect_closing(repo):
    tid = repo.add_task("Closed with lessons")
    repo.j("note", tid, "approach A failed", "--dead-end")
    repo.j("done", tid, "--no-code", "documented the dead end instead")
    repo.j("note", tid, "approach B also failed", "--dead-end")
    rc, payload = validate(repo, "--no-git", "--strict", expect=0)
    assert payload["ok"]



def _age_task(repo, tid):
    """Rewrite every timestamp on a task into the distant past."""
    text = repo.read(tid)
    for ts_fragment in ("2026-", "2027-", "2028-"):
        text = text.replace(ts_fragment, "2020-")
    repo.write(tid, text)


def test_stale_block_flags_forgotten_handoffs_only(repo):
    handed = repo.add_task("Handed off and forgotten")
    repo.j("claim", handed)
    repo.j("release", handed, "--blocked", "--on",
           "external: ready for integration", "--note", "green")
    parked = repo.add_task("Parked wave")
    repo.j("claim", parked)
    repo.j("release", parked, "--blocked", "--on", "external: wave open")
    for tid in (handed, parked):
        _age_task(repo, tid)
    rc, payload = validate(repo, "--no-git", expect=0)
    stale = [e for e in payload["errors"] if e["code"] == "stale-block"]
    assert [e["task"] for e in stale] == [handed]
    assert "nobody picked it up" in stale[0]["message"]
    assert "ledger done" in stale[0]["fix_hint"]
    rc, payload = validate(repo, "--no-git", "--strict", expect=1)
    assert "stale-block" in codes(payload, "error")
    # a note refreshes it (still waiting on purpose); done repairs it
    repo.j("note", handed, "integrator queue is long; still waiting")
    rc, payload = validate(repo, "--no-git", "--strict", expect=0)
    assert "stale-block" not in codes(payload)
    _age_task(repo, handed)
    repo.j("done", handed, "--no-code", "integrated", "--session",
           "integrator")
    rc, payload = validate(repo, "--no-git", "--strict", expect=0)


def test_stale_claim_covers_claim_retaining_blocked_tasks(repo):
    tid = repo.add_task("Blocked with a claim")
    repo.j("claim", tid)
    repo.j("block", tid, "--on", "human", "--why", "vanished after this")
    _age_task(repo, tid)
    rc, payload = validate(repo, "--no-git", expect=0)
    stale = [e for e in payload["errors"] if e["code"] == "stale-claim"]
    assert [e["task"] for e in stale] == [tid]
    assert "stale-block" not in codes(payload)  # a human block is not a handoff
    repo.j("release", tid, "--blocked", "--on", "human", "--force")
    rc, payload = validate(repo, "--no-git", "--strict", expect=0)



def test_step_outcome_suffix_is_free_text_and_strict_clean(repo):
    """Phase-0 pin for T-w5pjd8: `- [x] text -- MOOT: reason` is the one
    grammar-compatible step annotation. Nobody may later tighten the
    checkbox grammar into rejecting it; marker characters DO fail."""
    tid = repo.add_task("Annotated steps")
    repo.j("step", tid, "add", "wire the cache")
    repo.j("step", tid, "add", "measure it")
    text = repo.read(tid).replace(
        "- [ ] wire the cache", "- [x] wire the cache -- MOOT: cache removed"
    ).replace("- [ ] measure it", "- [ ] measure it -- DELEGATED: T-abc123")
    repo.write(tid, text)
    steps = repo.j("show", tid)["data"]["next_steps"]
    assert steps[0]["done"] and steps[0]["text"].endswith("MOOT: cache removed")
    assert not steps[1]["done"]
    rc, payload = validate(repo, "--no-git", "--strict", expect=0)
    assert "checkbox-grammar" not in codes(payload)
    # round-trips byte-for-byte through uncheck / check
    before = repo.read(tid)
    repo.j("step", tid, "uncheck", "cache")
    repo.j("step", tid, "check", "cache")
    after = repo.read(tid)
    assert after.split("## Log")[0] == before.split("## Log")[0]
    assert repo.j("step", tid, "check", "T-abc123")["ok"]  # selector by id
    # the improvised marker characters are the thing that fails
    repo.write(tid, repo.read(tid).replace("- [x] measure it",
                                           "- [~] measure it"))
    rc, payload = validate(repo, "--no-git", "--strict", expect=1)
    assert "checkbox-grammar" in codes(payload, "error")



def test_closing_log_line_with_open_status_is_incoherent(repo):
    """The documented header-conflict rule can re-open a closed task; the
    file must not validate clean (sweep 2026-09-02, task C)."""
    tid = repo.add_task("Closed then merged open")
    repo.j("done", tid, "--no-code", "shipped")
    text = repo.read(tid).replace("status: done\n", "status: in_progress\n"
                                  ).replace("closed: ", "claimed_by: b\nclaimed_at: ")
    repo.write(tid, text)
    rc, payload = validate(repo, "--no-git", expect=1)
    sc = [e for e in payload["errors"] if e["code"] == "state-coherence"
          and "closing Log line" in e["message"]]
    assert sc and "ledger repair" in sc[0]["fix_hint"]


def test_shallow_detection_fails_closed(ledger_mod, repo, monkeypatch):
    monkeypatch.chdir(repo.root)
    real = ledger_mod.run_git

    def broken(args, cwd):
        if "--is-shallow-repository" in args or "--git-dir" in args:
            return 128, ""
        return real(args, cwd)
    monkeypatch.setattr(ledger_mod, "run_git", broken)
    args = ledger_mod.build_parser().parse_args(["validate", "--coverage",
                                                 "--json", "--session", "t"])
    ctx = ledger_mod.make_ctx(args)
    violations = ledger_mod.validate_git(ctx, coverage=True)
    assert any(e["code"] == "coverage" and "cannot determine" in e["message"]
               for e in violations)



def _header_of(repo, tid):
    return repo.j("show", tid)["data"]["header"]


def test_repair_derives_a_coherent_header_for_each_incoherent_state(repo):
    # (a) a done task that a merge re-opened / left with claim fields
    a = repo.add_task("Merged open")
    repo.j("claim", a, "--session", "x")
    repo.j("done", a, "--no-code", "shipped", "--session", "x")
    repo.write(a, repo.read(a).replace("status: done\n", "status: in_progress\n"
                                      ).replace("closed: ", "claimed_by: y\nclaimed_at: "))
    validate(repo, "--no-git", expect=1)
    d = repo.j("repair", a)
    assert d["ok"] and any("status=done" in c for c in d["data"]["changes"])
    h = _header_of(repo, a)
    assert h["status"] == "done" and "claimed_by" not in h and "closed" in h
    assert repo.j("show", a)["data"]["log"][-1]["verb"] == "repair"
    # (b) todo with stray claim fields and blocked_on
    b = repo.add_task("Stray fields")
    repo.write(b, repo.read(b).replace(f"id: {b}", f"id: {b}\nclaimed_by: z\n"
                                      f"claimed_at: 2026-01-01T00:00:00Z\n"
                                      "blocked_on: human"))
    repo.j("repair", b)
    h = _header_of(repo, b)
    assert h["status"] == "todo" and "claimed_by" not in h and "blocked_on" not in h
    # (c) in_progress missing claimed_at: paired from the newest claim line
    c = repo.add_task("Half claim")
    repo.j("claim", c, "--session", "holder")
    repo.write(c, repo.read(c).replace("claimed_at: ", "claimed_at_gone: "))
    repo.j("repair", c)
    h = _header_of(repo, c)
    assert h["claimed_by"] == "holder" and "claimed_at" in h
    assert "claimed_at_gone: " in repo.read(c)  # unknown keys are never touched
    # (d) blocked without blocked_on: derived from the block line
    e = repo.add_task("Blocked lost reason")
    repo.j("block", e, "--on", "human", "--why", "budget")
    repo.write(e, repo.read(e).replace("blocked_on: human\n", ""))
    repo.j("repair", e)
    assert _header_of(repo, e)["blocked_on"] == "human"
    # (e) done without closed
    f = repo.add_task("Lost closed")
    repo.j("done", f, "--no-code", "x")
    repo.write(f, repo.read(f).replace("closed: ", "closed_gone: "))
    repo.j("repair", f)
    assert "closed" in _header_of(repo, f)
    # the stray keys left above are unknown-key warnings (errors under
    # --strict) by design; drop them, then the whole ledger is strict-clean
    import re as _re
    for t in (c, f):
        repo.write(t, _re.sub(r"^(claimed_at_gone|closed_gone): .*\n", "",
                              repo.read(t), flags=_re.M))
    rc, payload = validate(repo, "--no-git", "--strict")
    assert rc == 0, [x for x in payload["errors"] if x["severity"] == "error"]
    # nothing to repair is a refusal, not a silent no-op
    d = repo.j("repair", f, expect=2)
    assert d["errors"][0]["code"] == "nothing-to-repair"
    # every state-coherence violation now carries a hint
    g = repo.add_task("Hints")
    repo.write(g, repo.read(g).replace(f"id: {g}", f"id: {g}\nclaimed_by: q"))
    rc, payload = validate(repo, "--no-git", expect=1)
    assert all(e["fix_hint"] for e in payload["errors"]
               if e["code"] == "state-coherence")
