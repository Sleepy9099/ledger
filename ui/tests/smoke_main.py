"""Main file for the page smoke test: registers the real routes afresh
(user_simulation resets NiceGUI's globals between runs)."""
import sys

from nicegui import ui

for name in [m for m in sys.modules if m.startswith("ledger_ui.")
             and m not in ("ledger_ui.client", "ledger_ui.projects",
                           "ledger_ui.model", "ledger_ui.store",
                           "ledger_ui.graphlayout")]:
    del sys.modules[name]

import ledger_ui.routes  # noqa: E402,F401

ui.run(storage_secret="smoke")
