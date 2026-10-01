"""Projects: every registered ledger at a glance, plus a global inbox count.
Editing this list touches only the UI's own registry file."""
from __future__ import annotations

import asyncio

from nicegui import ui

from .. import model, theme
from ..projects import Registry
from ..shell import checkouts_for, header, page_url
from ..store import Store


async def page(store: Store) -> None:
    theme.apply()
    registry = Registry.load()
    header(None, registry)

    with ui.row().classes("w-full items-end justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Projects").classes("lg-h1")
            ui.label(f"{len(registry.projects)} ledger"
                     f"{'s' if len(registry.projects) != 1 else ''} · "
                     f"registry: {registry.path}").classes("lg-muted text-sm")
        ui.button("Add project", icon="add",
                  on_click=lambda: add_dialog(registry)).props(
            "unelevated no-caps")

    if not registry.projects:
        with ui.column().classes("lg-card w-full items-center p-12 gap-2"):
            ui.icon("folder_open").style("font-size:44px;color:var(--lg-muted)")
            ui.label("No projects yet").classes("lg-h2")
            ui.label("Add a repository that contains .ledger/ledger.py "
                     "(or run `ledger-ui add <path>`).").classes(
                "lg-muted text-sm")
        return

    summary = ui.row().classes("w-full gap-3")
    grid = ui.element("div").classes("w-full grid gap-4").style(
        "grid-template-columns: repeat(auto-fill, minmax(360px, 1fr))")
    slots = {}
    with grid:
        for p in registry.projects:
            slots[p.slug] = ui.column().classes("lg-card p-4 gap-3")
            with slots[p.slug]:
                ui.label(p.name).classes("lg-h2")
                ui.skeleton().classes("w-full h-24")

    async def load(p):
        checkouts = await asyncio.to_thread(checkouts_for, p)
        main = checkouts[0]
        snap = await store.snapshot(main.path) if main.has_ledger else None
        return p, checkouts, snap

    await ui.context.client.connected()
    results = await asyncio.gather(*(load(p) for p in registry.projects))
    totals = {"open": 0, "active": 0, "human": 0, "attention": 0}
    for p, checkouts, snap in results:
        slot = slots[p.slug]
        slot.clear()
        with slot:
            project_card(registry, p, checkouts, snap, totals)
    with summary:
        for label, key, colour in (
                ("Open tasks", "open", "#64748b"),
                ("Active", "active", theme.STATUS["in_progress"][1]),
                ("Waiting on you", "human", theme.HUMAN),
                ("Attention items", "attention", "#f97316")):
            with ui.element("div").classes("lg-card lg-kpi").style(
                    f"--c:{colour}"):
                ui.label(str(totals[key])).classes("value")
                ui.label(f"{label} · all projects").classes("label")


def project_card(registry, p, checkouts, snap, totals) -> None:
    with ui.row().classes("w-full items-start justify-between no-wrap"):
        with ui.column().classes("gap-0 min-w-0"):
            ui.link(p.name, page_url(p, "main", "overview")).classes(
                "lg-h2 no-underline").style("color: var(--lg-text)")
            ui.label(str(p.root)).classes("lg-muted lg-small break-all")
        with ui.button(icon="more_vert").props("flat round dense "
                                               "color=grey-7"):
            with ui.menu():
                ui.menu_item("Remove from list",
                             on_click=lambda: remove_dialog(registry, p))
    if snap is None:
        theme.chip("no .ledger/ledger.py in the main checkout", "#ef4444",
                   "error")
        return
    rows = snap.task_rows
    counts = model.status_counts(rows)
    q = snap.questions.data
    human = len(q.get("questions", [])) + len(q.get("blocked_on_human", []))
    att = model.attention(snap)
    serious = [a for a in att if a.severity in ("critical", "high",
                                                 "medium")]
    totals["open"] += counts["todo"] + counts["in_progress"] + counts[
        "blocked"]
    totals["active"] += counts["in_progress"]
    totals["human"] += human
    totals["attention"] += len(serious)

    with ui.row().classes("items-center gap-2"):
        if not snap.caps.supported or not snap.caps.compatible:
            theme.chip("needs attention", "#ef4444", "warning")
        else:
            theme.chip(f"ledger {snap.doctor.data.get('tool_version')}",
                       "#10b981", "verified")
        theme.chip(f"{len(rows)} tasks", "#64748b")
        if serious:
            theme.chip(f"{len(serious)} to look at", "#f97316", "flag")
    with ui.element("div").classes("w-full grid gap-2").style(
            "grid-template-columns: repeat(4, 1fr)"):
        for label, n, colour in (
                ("To do", counts["todo"], theme.STATUS["todo"][1]),
                ("Active", counts["in_progress"],
                 theme.STATUS["in_progress"][1]),
                ("Blocked", counts["blocked"], theme.STATUS["blocked"][1]),
                ("Human", human, theme.HUMAN)):
            with ui.column().classes("gap-0"):
                ui.label(str(n)).style(
                    f"font-size:22px;font-weight:750;color:{colour}")
                ui.label(label).classes("lg-muted lg-small")
    ui.separator()
    with ui.column().classes("w-full gap-1"):
        for c in checkouts:
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("home" if c.is_main else "call_split").classes(
                    "lg-muted").style("font-size:16px")
                if c.has_ledger:
                    ui.link(c.branch or "detached", page_url(
                        p, c, "overview")).classes("text-sm truncate")
                else:
                    ui.label(c.branch or "detached").classes(
                        "text-sm lg-muted truncate")
                    ui.label("no ledger").classes("lg-tag")
                ui.space()
                if not c.is_main:
                    ui.label(c.path.name).classes("lg-muted lg-small truncate")


def add_dialog(registry: Registry) -> None:
    with ui.dialog() as dialog, ui.card().classes("lg-card w-[560px] p-5 "
                                                  "gap-3"):
        ui.label("Add a project").classes("lg-h2")
        ui.label("A repository root (or its .ledger folder) containing "
                 ".ledger/ledger.py.").classes("lg-muted text-sm")
        path = ui.input("Path").props("outlined dense autofocus").classes(
            "w-full")
        name = ui.input("Display name (optional)").props(
            "outlined dense").classes("w-full")
        error = ui.label().classes("text-negative text-sm")

        def save() -> None:
            try:
                registry.add(path.value.strip().strip('"'),
                             name.value.strip() or None)
                registry.save()
            except (ValueError, OSError) as e:
                error.text = str(e)
                return
            dialog.close()
            ui.navigate.reload()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Add", on_click=save).props("unelevated no-caps")
    dialog.open()


def remove_dialog(registry: Registry, p) -> None:
    with ui.dialog() as dialog, ui.card().classes("lg-card p-5 gap-3"):
        ui.label(f"Remove {p.name} from the list?").classes("lg-h2")
        ui.label("Only the UI's registry entry is removed; the repository "
                 "and its ledger are untouched.").classes("lg-muted text-sm")

        def go() -> None:
            registry.remove(p.slug)
            registry.save()
            dialog.close()
            ui.navigate.reload()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Remove", on_click=go).props(
                "unelevated no-caps color=negative")
    dialog.open()
