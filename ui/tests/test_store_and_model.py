import asyncio

from ledger_ui import model
from ledger_ui.client import LedgerClient
from ledger_ui.store import Store


class CountingClient(LedgerClient):
    calls: list = []

    def run(self, verb, *args):
        CountingClient.calls.append(verb)
        return super().run(verb, *args)


def test_cache_reuses_until_task_files_change(ledger):
    CountingClient.calls = []
    store = Store(client_factory=CountingClient)
    store.get(ledger.root, "list")
    store.get(ledger.root, "list")
    assert CountingClient.calls == ["list"]
    ledger.add("A new task")
    env = store.get(ledger.root, "list")
    assert CountingClient.calls == ["list", "list"]
    assert len(env.data["tasks"]) == 1


def test_snapshot_and_attention(ledger):
    gate = ledger.add("Pick a storage engine")
    downstream = ledger.add("Build on the engine", "--after", gate)
    ledger.add("Build more on it", "--after", downstream)
    ledger.cli("question", gate, "add", "SQLite or Postgres?", "--human")
    blocked = ledger.add("Needs a person")
    ledger.cli("block", blocked, "--on", "human", "--why", "sign-off")
    snap = asyncio.run(Store().snapshot(ledger.root))
    assert snap.caps.supported and snap.caps.has("log")
    items = model.attention(snap)
    kinds = [a.kind for a in items]
    assert kinds[:2] == ["human", "human-block"]
    human = items[0]
    assert human.task == gate and human.waiting == 2
    assert "SQLite or Postgres?" in human.title
    assert items[1].task == blocked


def test_model_helpers():
    assert model.actor_family("w-apfs-2026-09-25-e") == "w-apfs"
    assert model.actor_kind("w-apfs-2026-09-25-e") == "w"
    assert model.actor_family("claude-2026-10-01-a") == "claude"
    assert model.actor_family("HUMAN") == "HUMAN"
    assert model.blocked_kind("human") == "human"
    assert model.blocked_kind("T-abc123") == "task"
    assert model.blocked_kind("external: ready for integration") == "handoff"
    assert model.blocked_kind("external: vendor reply") == "external"
    rows = [{"id": "T-1", "title": "Parser", "status": "todo",
             "priority": "p1", "size": "s", "tags": "core, io"},
            {"id": "T-2", "title": "Writer", "status": "done",
             "priority": "p2", "size": "m", "tags": ""}]
    f = model.Filters()
    assert [r["id"] for r in rows if f.matches(r)] == ["T-1"]
    f = model.Filters(text="writ", statuses=())
    assert [r["id"] for r in rows if f.matches(r)] == ["T-2"]
    assert model.Filters(tag="io", statuses=()).matches(rows[0])
    assert model.all_tags(rows) == ["core", "io"]
