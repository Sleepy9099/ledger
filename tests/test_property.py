"""Anti-corruption property: CLI mutations can never author an invalid ledger."""
import json
import random


def test_random_cli_sequences_never_corrupt(plain):
    rng = random.Random(20260827)
    ids: list[str] = []

    def any_id():
        return rng.choice(ids)

    def op_add():
        extra = []
        if ids and rng.random() < 0.3:
            extra += ["--after", any_id()]
        if rng.random() < 0.3:
            extra += ["--tag", rng.choice(["wave", "wave:w1", "resource:gpu"])]
        tid = plain.add_task(
            f"Task {rng.randrange(10_000)}",
            "-p", rng.choice(["p0", "p1", "p2", "p3"]),
            "-s", rng.choice(["xs", "s", "m", "l", "xl"]), *extra)
        ids.append(tid)

    def op_brief():
        assert plain.run("brief", any_id()).returncode == 0

    def op_note():
        extra = ["--dead-end"] if rng.random() < 0.3 else []
        plain.run("note", any_id(), f"breadcrumb {rng.randrange(999)}",
                  *extra)

    def op_step():
        tid = any_id()
        plain.run("step", tid, "add", f"do thing {rng.randrange(999)}")
        plain.run("step", tid, "check", "1")

    def op_question():
        tid = any_id()
        plain.run("question", tid, "add", f"q {rng.randrange(999)}?")
        if rng.random() < 0.5:
            plain.run("question", tid, "resolve", "1", "--answer", "resolved")
        else:
            plain.run("answers", "apply", "-", input=json.dumps(
                [{"task": tid, "n": 1, "answer": "applied"}]))

    def op_claim_release():
        tid = any_id()
        plain.run("claim", tid)
        if rng.random() < 0.5:
            plain.run("release", tid, "--note", "handing off")

    def op_block_unblock():
        tid = any_id()
        plain.run("block", tid, "--on", "human")
        if rng.random() < 0.5:
            plain.run("unblock", tid)

    def op_set():
        plain.run("set", any_id(), "--priority", rng.choice(["p0", "p3"]))

    def op_depends():
        a, b = any_id(), any_id()
        plain.run("set", a, "--add-depends", b)  # self/cycle may be refused

    def op_done():
        plain.run("done", any_id(), "--no-code", "synthetic completion",
                  "--force")

    def op_drop():
        if rng.random() < 0.5:  # self / dropped target may be refused: fine
            plain.run("drop", any_id(), "--duplicate-of", any_id())
        else:
            plain.run("drop", any_id(), "--why", "synthetic drop")

    ops = [op_add, op_note, op_step, op_question, op_claim_release,
           op_block_unblock, op_set, op_depends, op_done, op_drop, op_brief]
    op_add()
    for i in range(70):
        rng.choice(ops)()
        if i % 10 == 9:
            r = plain.run("validate", "--no-git", "--json")
            payload = json.loads(r.stdout)
            hard = [e for e in payload["errors"] if e["severity"] == "error"]
            assert r.returncode == 0, (
                f"CLI ops corrupted the ledger at step {i}:\n"
                + json.dumps(hard, indent=2))


def test_every_op_refusal_leaves_files_untouched(plain):
    tid = plain.add_task("Refusal target")
    before = plain.read(tid)
    assert plain.run("done", tid).returncode == 2       # no evidence
    assert plain.run("unblock", tid).returncode == 2    # not blocked
    assert plain.run("step", tid, "check", "1").returncode == 2  # no steps
    assert plain.read(tid) == before
