"""Parser/serializer unit tests against the module itself."""

CANONICAL = """---
id: T-a3f9c2
title: Add retry with exponential backoff to the sync client
status: in_progress
priority: p1
size: m
created: 2026-08-25T09:12:40Z
claimed_by: claude-2026-08-27-a
claimed_at: 2026-08-27T14:03:22Z
depends_on: T-77be04
tags: sync, reliability
---

## Spec

Retries apply to idempotent GET/PUT calls in sync/client.py only.
Backoff: base 250ms, factor 2, jitter +-20%, max 5 attempts, cap 30s.

## Next Steps

- [x] Extract request path into _send() seam for retry wrapper
- [ ] Implement backoff loop with jitter (see spec constants)
- [ ] Unit tests: 429 then success; 500 x5 exhausts; 400 no retry

## Open Questions

- [x] Retry budget shared across calls? -- ANSWERED (2026-08-26): No, per-call budget only.
- [ ] HUMAN: Should POST /bulk be retried with an idempotency key, or excluded?

## Commits

- 4f2c9ab 2026-08-26 Extract _send() seam in sync client
- b91d3e0 2026-08-27 Add SyncRetryError and config plumbing

## Log

- 2026-08-25T09:12:40Z [ej] add: created from incident #211 follow-up
- 2026-08-26T18:40:02Z [claude-2026-08-26-b] claim: starting seam extraction
- 2026-08-26T19:55:31Z [claude-2026-08-26-b] link: 4f2c9ab seam extracted, tests green
- 2026-08-26T19:56:10Z [claude-2026-08-26-b] release: out of context budget; next steps updated
- 2026-08-27T14:03:22Z [claude-2026-08-27-a] claim: resuming, picking up backoff loop
"""


def test_canonical_roundtrip_identity(ledger_mod):
    task, problems = ledger_mod.parse_task(CANONICAL)
    assert problems == []
    assert ledger_mod.serialize_task(task) == CANONICAL


def test_parse_serialize_fixed_point(ledger_mod):
    task, _ = ledger_mod.parse_task(CANONICAL)
    once = ledger_mod.serialize_task(task)
    task2, problems = ledger_mod.parse_task(once)
    assert problems == []
    assert ledger_mod.serialize_task(task2) == once
    assert task2.header == task.header
    assert task2.sections == task.sections


def test_structured_views(ledger_mod):
    task, _ = ledger_mod.parse_task(CANONICAL)
    steps = task.steps()
    assert [s["done"] for s in steps] == [True, False, False]
    assert steps[1]["text"].startswith("Implement backoff loop")

    questions = task.questions()
    assert questions[0]["answered"] and questions[0]["answer"] == "No, per-call budget only."
    assert not questions[0]["human"]
    assert questions[1]["human"] and not questions[1]["answered"]
    assert questions[1]["text"].startswith("Should POST /bulk")

    commits = task.commits()
    assert [c["sha"] for c in commits] == ["4f2c9ab", "b91d3e0"]

    log = task.log()
    assert [e["verb"] for e in log] == ["add", "claim", "link", "release", "claim"]
    assert log[0]["actor"] == "ej"

    assert task.depends_on == ["T-77be04"]
    assert task.tags == ["sync", "reliability"]
    assert task.last_activity() == "2026-08-27T14:03:22Z"


def test_unknown_keys_and_sections_preserved(ledger_mod):
    text = CANONICAL.replace(
        "tags: sync, reliability\n", "tags: sync, reliability\nmystery: kept\n"
    ).replace(
        "## Log", "## Scratch Notes\n\nfree-form agent notes survive\n\n## Log")
    task, _ = ledger_mod.parse_task(text)
    out = ledger_mod.serialize_task(task)
    assert "mystery: kept" in out
    assert "## Scratch Notes" in out
    assert "free-form agent notes survive" in out
    assert out.rstrip().split("\n")[-1].startswith("- 2026-08-27")  # Log still last


def test_log_stays_last_and_sections_canonical(ledger_mod):
    task, _ = ledger_mod.parse_task(CANONICAL)
    task.append_log("actor", "note", "something")
    out = ledger_mod.serialize_task(task)
    order = [line[3:] for line in out.split("\n") if line.startswith("## ")]
    assert order == ["Spec", "Next Steps", "Open Questions", "Commits", "Log"]
    assert out.index("## Log") > out.index("## Commits")


def test_parse_problems_detected(ledger_mod):
    # duplicate key
    _, probs = ledger_mod.parse_task(CANONICAL.replace(
        "priority: p1\n", "priority: p1\npriority: p0\n"))
    assert any("duplicate header key" in p["message"] for p in probs)
    # missing closing fence
    task, probs = ledger_mod.parse_task("---\nid: T-abcdef\n")
    assert task is None and probs[0]["code"] == "parse"
    # content before first section
    _, probs = ledger_mod.parse_task(CANONICAL.replace(
        "\n## Spec", "\nstray preamble\n\n## Spec"))
    assert any("before the first" in p["message"] for p in probs)
    # sections out of canonical order
    reordered = CANONICAL.replace("## Spec", "## ZZTMP").replace(
        "## Next Steps", "## Spec").replace("## ZZTMP", "## Next Steps")
    _, probs = ledger_mod.parse_task(reordered)
    assert any("canonical order" in p["message"] for p in probs)


def test_sanitize_inline_and_actor(ledger_mod):
    assert ledger_mod.sanitize_inline("a\r\nb\nc") == "a; b; c"
    assert ledger_mod.sanitize_actor("we[ird]\nname") == "we_ird__name"
    assert ledger_mod.sanitize_actor("  ") == "unknown"


def test_crlf_input_normalized_on_parse(ledger_mod):
    task, problems = ledger_mod.parse_task(CANONICAL.replace("\n", "\r\n"))
    assert problems == []
    assert ledger_mod.serialize_task(task) == CANONICAL


def test_closed_relation_grammar_roundtrip_and_prose_is_not_a_relation(ledger_mod):
    text = CANONICAL.replace(
        "status: in_progress\n", "status: dropped\n").replace(
        "claimed_by: claude-2026-08-27-a\nclaimed_at: 2026-08-27T14:03:22Z\n",
        "closed: 2026-08-28T10:00:00Z\n").replace(
        "- 2026-08-27T14:03:22Z [claude-2026-08-27-a] claim: resuming, "
        "picking up backoff loop\n",
        "- 2026-08-28T10:00:00Z [ej] drop: duplicate-of T-77be04 — same fix\n")
    task, problems = ledger_mod.parse_task(text)
    assert problems == []
    assert ledger_mod.serialize_task(task) == text
    assert task.closed_relation() == {"kind": "duplicate", "target": "T-77be04"}
    # the historical free-text phrasing is prose, not a machine relation
    prose = text.replace("drop: duplicate-of T-77be04 — same fix",
                         "drop: superseded by new design")
    task, _ = ledger_mod.parse_task(prose)
    assert task.closed_relation() is None
    # two drop lines sharing the newest timestamp that disagree -> None
    torn = text.replace(
        "- 2026-08-28T10:00:00Z [ej] drop: duplicate-of T-77be04 — same fix\n",
        "- 2026-08-28T10:00:00Z [ej] drop: duplicate-of T-77be04 — same fix\n"
        "- 2026-08-28T10:00:00Z [other] drop: superseded-by T-000000\n")
    task, _ = ledger_mod.parse_task(torn)
    assert task.closed_relation() is None



def test_dead_end_note_roundtrips_and_is_selectable(ledger_mod):
    text = CANONICAL.replace(
        "- 2026-08-26T19:55:31Z [claude-2026-08-26-b] link: 4f2c9ab seam "
        "extracted, tests green\n",
        "- 2026-08-26T19:55:31Z [claude-2026-08-26-b] link: 4f2c9ab seam "
        "extracted, tests green\n"
        "- 2026-08-26T19:56:00Z [claude-2026-08-26-b] note(dead-end): "
        "asyncio.timeout does not cover the DNS phase\n")
    task, problems = ledger_mod.parse_task(text)
    assert problems == []
    assert ledger_mod.serialize_task(task) == text
    dead = [e for e in task.log() if e["verb"] == "note(dead-end)"]
    assert len(dead) == 1 and "DNS phase" in dead[0]["text"]
    assert task.last_activity() == "2026-08-27T14:03:22Z"
