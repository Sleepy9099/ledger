"""Cross-process mutation-lock behavior (T-q59p4n)."""
import json
import os
import subprocess
import sys


def test_concurrent_claims_have_exactly_one_winner(plain):
    tid = plain.add_task("Contested claim target")
    procs = []
    for i in range(12):
        procs.append(subprocess.Popen(
            [sys.executable, str(plain.script), "next", "--claim", "--json",
             "--session", f"racer-{i}"],
            cwd=str(plain.root), env=plain.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    payloads = []
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err
        payloads.append(json.loads(out))

    winners = [p for p in payloads if p["data"]["claimed"]]
    assert len(winners) == 1, f"{len(winners)} processes believe they claimed"
    winner_session = winners[0]["data"]["task"]["header"]["claimed_by"]

    show = plain.j("show", tid)["data"]
    assert show["header"]["claimed_by"] == winner_session
    claim_lines = [e for e in show["log"] if e["verb"] == "claim"]
    assert len(claim_lines) == 1  # no lost-update double claim in the Log
    assert claim_lines[0]["actor"] == winner_session
    # every loser was told the truth: nothing eligible, task held by winner
    for p in payloads:
        if not p["data"]["claimed"]:
            assert p["data"]["task"] is None
            assert any(w["id"] == tid for w in p["data"]["why"])


def _hold_lock(lock_path):
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    if sys.platform == "win32":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def _drop_lock(fd):
    if sys.platform == "win32":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    os.close(fd)


def test_lock_timeout_is_a_clean_refusal(plain):
    tid = plain.add_task("Locked out")
    fd = _hold_lock(plain.root / ".ledger" / ".lock")
    try:
        env = dict(plain.env)
        env["LEDGER_LOCK_TIMEOUT"] = "0.3"
        r = subprocess.run(
            [sys.executable, str(plain.script), "note", tid, "blocked",
             "--json"],
            cwd=str(plain.root), env=env, capture_output=True, text=True)
        assert r.returncode == 2, r.stdout + r.stderr
        payload = json.loads(r.stdout)
        assert payload["errors"][0]["code"] == "lock-timeout"
        assert payload["errors"][0]["fix_hint"]
    finally:
        _drop_lock(fd)
    assert plain.run("note", tid, "lock released, back to work").returncode == 0


def test_read_only_commands_ignore_the_lock(plain):
    tid = plain.add_task("Readable while locked")
    fd = _hold_lock(plain.root / ".ledger" / ".lock")
    try:
        env = dict(plain.env)
        env["LEDGER_LOCK_TIMEOUT"] = "0.3"
        for call in (("list",), ("show", tid), ("next",), ("questions",),
                     ("validate", "--no-git"), ("doctor",),
                     ("search", "x"), ("brief", tid)):
            r = subprocess.run(
                [sys.executable, str(plain.script), *call, "--json"],
                cwd=str(plain.root), env=env, capture_output=True, text=True)
            assert r.returncode == 0, (call, r.stdout, r.stderr)
    finally:
        _drop_lock(fd)


def test_lock_file_never_tracked(repo):
    repo.add_task("Make the lock file exist")
    assert (repo.root / ".ledger" / ".lock").exists()
    gi = (repo.root / ".gitignore").read_text(encoding="utf-8")
    assert ".ledger/.lock" in gi
    status = repo.git("status", "--porcelain").stdout
    assert ".lock" not in status
