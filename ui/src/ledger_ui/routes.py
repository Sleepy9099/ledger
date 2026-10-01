"""URL → page. Importing this module registers every page with NiceGUI."""
from __future__ import annotations

from urllib.parse import quote

from nicegui import ui

from . import theme
from .projects import Registry
from .shell import Page, checkouts_for, frame, header
from .store import Store
from .views import (activity, graph, inbox, overview, projects, validation,
                    work)

STORE = Store()

RENDERERS = {
    "overview": overview.render,
    "work": work.render,
    "inbox": inbox.render,
    "graph": graph.render,
    "activity": activity.render,
    "validation": validation.render,
}


@ui.page("/")
async def index() -> None:
    await projects.page(STORE)


@ui.page("/p/{project}")
def project_root(project: str) -> None:
    ui.navigate.to(f"/p/{quote(project)}/main/overview")


@ui.page("/p/{project}/{checkout}")
def checkout_root(project: str, checkout: str) -> None:
    ui.navigate.to(f"/p/{quote(project)}/{quote(checkout)}/overview")


@ui.page("/p/{project}/{checkout}/{view}")
async def checkout_page(project: str, checkout: str, view: str,
                        task: str | None = None) -> None:
    registry = Registry.load()
    proj = registry.get(project)
    if proj is None:
        return not_found(registry, f"No project '{project}' is registered.")
    checkouts = checkouts_for(proj)
    co = next((c for c in checkouts if c.key == checkout), None)
    if co is None:
        return not_found(registry, f"{proj.name} has no checkout "
                                   f"'{checkout}'.")
    if not co.has_ledger:
        return not_found(registry, f"{co.path} has no .ledger/ledger.py "
                                   "(the branch may predate the ledger).")
    render = RENDERERS.get(view)
    if render is None:
        return not_found(registry, f"Unknown view '{view}'.")
    page = Page(STORE, registry, proj, checkouts, co, view)
    if task:
        page.state["_initial_task"] = task
    await frame(page, render)


def not_found(registry: Registry, message: str) -> None:
    theme.apply()
    header(None, registry)
    with ui.column().classes("lg-card w-full items-center p-12 gap-3"):
        ui.icon("travel_explore").style("font-size:44px;color:var(--lg-muted)")
        ui.label(message).classes("lg-h2")
        ui.link("Back to projects", "/")
