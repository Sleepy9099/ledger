"""Every page renders against a real temp ledger (NiceGUI's simulated user,
no browser)."""
import asyncio
from pathlib import Path

from nicegui.testing.user_simulation import user_simulation

from ledger_ui.projects import Registry

MAIN = Path(__file__).with_name("smoke_main.py")


def test_every_view_renders(ledger, ui_home):
    gate = ledger.add("Pick a storage engine", "--spec",
                      "Compare `sqlite_store` and the postgres_store path.")
    ledger.add("Build on the engine", "--after", gate)
    ledger.cli("question", gate, "add", "SQLite or Postgres?", "--human")
    ledger.cli("note", gate, "tried an in-memory store", "--dead-end")
    reg = Registry.load()
    reg.add(ledger.root, name="Demo")
    reg.save()

    async def go() -> None:
        async with user_simulation(main_file=MAIN) as user:
            await user.open("/")
            await user.should_see("Demo")
            for view, marker in (
                    ("overview", "Needs your attention"),
                    ("work", "2 of 2 tasks"),
                    ("inbox", "SQLite or Postgres?"),
                    ("graph", "Dependencies"),
                    ("activity", "tried an in-memory store"),
                    ("validation", "Run validation")):
                await user.open(f"/p/Demo/main/{view}")
                await user.should_see(marker, retries=50)
            await user.open(f"/p/Demo/main/work?task={gate}")
            # inspector: the spec (a real `show` subprocess, so allow time)
            await user.should_see("postgres_store", retries=100)
            await user.open("/p/Nope/main/overview")
            await user.should_see("No project 'Nope' is registered.")

    asyncio.run(go())
