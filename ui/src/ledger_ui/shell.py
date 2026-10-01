"""The frame around every checkout page: header, navigation, live refresh,
the task inspector drawer and the Ctrl+K jump-to-task palette."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import quote

from nicegui import background_tasks, ui

from . import model, theme
from .projects import Checkout, Project, Registry, discover_checkouts
from .store import Snapshot, Store

VIEWS = [
    # key, label, icon
    ("overview", "Overview", "space_dashboard"),
    ("work", "Work", "view_list"),
    ("inbox", "Human Inbox", "inbox"),
    ("graph", "Dependencies", "account_tree"),
    ("activity", "Activity", "timeline"),
    ("validation", "Validation", "verified"),
]

_CHECKOUT_CACHE: dict[str, tuple[float, list[Checkout]]] = {}
CHECKOUT_TTL_S = 30


def checkouts_for(project: Project) -> list[Checkout]:
    key = str(project.root)
    hit = _CHECKOUT_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CHECKOUT_TTL_S:
        return hit[1]
    found = discover_checkouts(project.root)
    _CHECKOUT_CACHE[key] = (time.monotonic(), found)
    return found


def page_url(project: Project, checkout: Checkout | str, view: str,
             task: str | None = None) -> str:
    key = checkout if isinstance(checkout, str) else checkout.key
    url = f"/p/{quote(project.slug)}/{quote(key)}/{view}"
    return url + (f"?task={quote(task)}" if task else "")


@dataclass
class Page:
    store: Store
    registry: Registry
    project: Project
    checkouts: list[Checkout]
    checkout: Checkout
    view: str
    snap: Snapshot | None = None
    state: dict = field(default_factory=dict)  # per-view UI state
    inspector: "Inspector | None" = None
    _refreshers: list[Callable[[], Awaitable[None]]] = field(
        default_factory=list)

    @property
    def path(self) -> Path:
        return self.checkout.path

    def url(self, view: str, task: str | None = None) -> str:
        return page_url(self.project, self.checkout, view, task)

    def open_task(self, task_id: str) -> None:
        if self.inspector:
            self.inspector.open(task_id)

    def task_link(self, task_id: str, label: str | None = None):
        """A clickable id that opens the inspector in place."""
        el = ui.label(label or task_id).classes("lg-id lg-link")
        el.on("click", lambda _=None, t=task_id: self.open_task(t))
        return el


def header(page: Page | None, registry: Registry, drawer=None) -> None:
    with ui.header().classes("lg-header items-center gap-3 px-4 py-2"):
        if drawer is not None:
            ui.button(icon="menu", on_click=drawer.toggle).props(
                "flat round dense color=grey-7")
        with ui.link(target="/").classes("no-underline text-inherit"):
            with ui.row().classes("items-center gap-2 lg-brand"):
                ui.html('<span class="dot"></span>', sanitize=False)
                ui.label("Ledger")
        if page is not None:
            projects = {p.slug: p.name for p in registry.projects}
            ui.select(projects, value=page.project.slug,
                      on_change=lambda e: ui.navigate.to(
                          f"/p/{quote(e.value)}/main/{page.view}")
                      ).props("dense outlined options-dense").classes(
                "lg-filter w-44")
            checkouts = {c.key: c.label for c in page.checkouts}
            ui.select(checkouts, value=page.checkout.key,
                      on_change=lambda e: ui.navigate.to(
                          page_url(page.project, e.value, page.view))
                      ).props("dense outlined options-dense").classes(
                "lg-filter w-72")
        ui.space()
        if page is not None:
            ui.button("Jump to task", icon="search",
                      on_click=lambda: open_palette(page)).props(
                "flat no-caps dense color=grey-7").tooltip("Ctrl+K")
            live = ui.html('<span class="lg-live"></span>',
                           sanitize=False).tooltip(
                "Live: refreshes when task files change")
            page.state["_live"] = live
        dark = ui.dark_mode(None)
        ui.button(icon="contrast", on_click=lambda: dark.set_value(
            not bool(dark.value))).props("flat round dense color=grey-7"
                                         ).tooltip("Toggle dark mode")


def nav(page: Page) -> ui.left_drawer:
    drawer = ui.left_drawer(value=True, bordered=False).classes(
        "lg-drawer").props("width=236 breakpoint=900")
    with drawer:
        ui.label(page.project.name).classes("lg-section-label")
        counts = page.state.get("_nav_counts", {})
        for key, label, icon in VIEWS:
            active = " active" if key == page.view else ""
            with ui.link(target=page.url(key)).classes(
                    f"lg-nav-item{active}"):
                ui.icon(icon)
                ui.label(label)
                n = counts.get(key)
                if n:
                    hot = " hot" if key == "inbox" else ""
                    ui.label(str(n)).classes(f"lg-nav-count{hot}")
        ui.label("Checkout").classes("lg-section-label")
        with ui.column().classes("px-5 gap-1 lg-small lg-muted"):
            ui.label(page.checkout.branch or "detached HEAD").classes(
                "font-medium").style("color: var(--lg-text)")
            ui.label(str(page.checkout.path)).classes("break-all")
            ver = page.state.get("_version")
            if ver:
                ui.label(f"ledger {ver}")
        ui.label("Projects").classes("lg-section-label")
        with ui.link(target="/").classes("lg-nav-item"):
            ui.icon("apps")
            ui.label("All projects")
    return drawer


async def frame(page: Page,
                render: Callable[[Page, ui.column], Awaitable[None]]) -> None:
    """Build the chrome, then render the view once the client is connected
    and again whenever the checkout's task files change."""
    theme.apply()
    container_holder: dict = {}
    # snapshot first (usually cached) so the nav can show counts
    page.snap = await page.store.snapshot(page.path)
    _nav_state(page)
    drawer = nav(page)
    header(page, page.registry, drawer)
    page.inspector = Inspector(page)
    container = ui.column().classes("w-full gap-4")
    container_holder["c"] = container
    stamp = {"value": await page.store.stamp(page.path)}

    async def draw() -> None:
        container.clear()
        with container:
            await render(page, container)

    async def tick() -> None:
        new = await page.store.stamp(page.path)
        if new == stamp["value"]:
            return
        stamp["value"] = new
        live = page.state.get("_live")
        if live:
            live.content = '<span class="lg-live busy"></span>'
        page.snap = await page.store.snapshot(page.path)
        await draw()
        if page.inspector and page.inspector.current:
            await page.inspector.load(page.inspector.current)
        if live:
            live.content = '<span class="lg-live"></span>'

    await draw()
    ui.timer(3.0, tick)
    ui.keyboard(on_key=lambda e: _palette_key(e, page))
    initial = page.state.get("_initial_task")
    if initial:
        page.open_task(initial)


def _nav_state(page: Page) -> None:
    snap = page.snap
    if snap is None:
        return
    rows = snap.task_rows
    counts = model.status_counts(rows)
    q = snap.questions.data
    page.state["_nav_counts"] = {
        "work": counts["todo"] + counts["in_progress"] + counts["blocked"],
        "inbox": len(q.get("questions", [])) + len(
            q.get("blocked_on_human", [])),
    }
    tv = snap.doctor.data.get("tool_version")
    page.state["_version"] = tv


def _palette_key(e, page: Page) -> None:
    if e.action.keydown and e.key == "k" and (e.modifiers.ctrl or
                                              e.modifiers.meta):
        open_palette(page)


def open_palette(page: Page) -> None:
    rows = page.snap.task_rows if page.snap else []
    with ui.dialog() as dialog, ui.card().classes(
            "lg-card w-[680px] max-w-full p-0 gap-0"):
        search = ui.input(placeholder="Jump to a task — id, title, tag, "
                                      "owner…").props(
            "autofocus borderless dense").classes("w-full px-4 py-2 text-base")
        ui.separator()
        results = ui.column().classes("w-full gap-0 max-h-[60vh] "
                                      "overflow-y-auto")

        def choose(tid: str) -> None:
            dialog.close()
            page.open_task(tid)

        def update() -> None:
            results.clear()
            f = model.Filters(text=search.value or "", statuses=())
            hits = [r for r in rows if f.matches(r)][:40]
            with results:
                if not hits:
                    ui.label("No matching task").classes("lg-empty w-full")
                for r in hits:
                    with ui.row().classes(
                            "lg-row clickable w-full items-center gap-3 "
                            "no-wrap").on("click",
                                          lambda _=None, t=r["id"]: choose(t)):
                        theme.status_chip(r.get("status", ""))
                        theme.priority_label(r.get("priority", ""))
                        ui.label(r["id"]).classes("lg-id")
                        ui.label(r.get("title", "")).classes(
                            "truncate text-sm")

        def first() -> None:
            f = model.Filters(text=search.value or "", statuses=())
            hit = next((r for r in rows if f.matches(r)), None)
            if hit:
                choose(hit["id"])

        search.on("update:model-value", lambda _: update())
        search.on("keydown.enter", lambda _: first())
        update()
    dialog.open()


# -- inspector -------------------------------------------------------------------

class Inspector:
    """Right-hand drawer rendering `show <id>` without leaving the view."""

    def __init__(self, page: Page):
        self.page = page
        self.current: str | None = None
        self.drawer = ui.right_drawer(value=False, bordered=False).props(
            "width=620 overlay elevated behavior=desktop").classes(
            "lg-inspector")
        with self.drawer:
            self.body = ui.column().classes("w-full gap-3 p-1")

    def open(self, task_id: str) -> None:
        self.current = task_id
        self.drawer.show()
        # keep the URL shareable: ?task= reopens this inspector
        ui.navigate.history.replace(self.page.url(self.page.view, task_id))
        background_tasks.create(self.load(task_id),
                                name=f"inspect {task_id}")

    def close(self) -> None:
        self.current = None
        self.drawer.hide()
        ui.navigate.history.replace(self.page.url(self.page.view))

    async def load(self, task_id: str) -> None:
        from .views.task import render_task  # late: views import shell
        self.body.clear()
        with self.body:
            with ui.row().classes("w-full justify-center p-8"):
                ui.spinner(size="lg")
        env = await self.page.store.call(self.page.path, "show", task_id)
        if self.current != task_id:
            return
        self.body.clear()
        with self.body:
            render_task(self.page, env, on_close=self.close)
