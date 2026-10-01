"""Activity: the corpus-wide Log timeline from `ledger log --json` (1.6.0+),
grouped by day, filterable by actor, verb, task and time window."""
from __future__ import annotations

from nicegui import ui

from .. import model
from ..shell import Page
from .task import log_item

PAGE = 200
VERBS = ["add", "claim", "release", "done", "drop", "block", "unblock",
         "note", "note(dead-end)", "question", "answer", "step", "set",
         "link", "unlink", "repair"]


async def render(page: Page, container) -> None:
    caps = page.snap.caps
    ui.label("Activity").classes("lg-h1")
    if not caps.has("log"):
        with ui.column().classes("lg-card w-full items-center p-10 gap-2"):
            ui.icon("history_toggle_off").style(
                "font-size:42px;color:var(--lg-muted)")
            ui.label("Activity needs `ledger log`").classes("lg-h2")
            ui.label(caps.missing_reason("log") + ". Re-vendor "
                     ".ledger/ledger.py to enable this view.").classes(
                "lg-muted text-sm")
        return

    st = page.state.setdefault("activity", {
        "limit": PAGE, "actor": "", "verbs": [], "since": "", "text": ""})
    workers = page.snap.report.data.get("agents", {}).get("workers", [])
    actors = sorted(set(workers) | {r["claimed_by"] for r in
                                    page.snap.task_rows
                                    if r.get("claimed_by")})

    with ui.row().classes("w-full gap-2 items-center"):
        text = ui.input(placeholder="Filter loaded events…",
                        value=st["text"]).props(
            "dense outlined clearable").classes("lg-filter w-64")
        with text.add_slot("prepend"):
            ui.icon("search")
        actor = ui.select([""] + actors, value=st["actor"], label="Actor",
                          with_input=True).props(
            "dense outlined clearable options-dense").classes(
            "lg-filter w-64")
        verbs = ui.select(VERBS, multiple=True, value=st["verbs"],
                          label="Event").props(
            "dense outlined use-chips options-dense").classes(
            "lg-filter min-w-[200px]")
        since = ui.select({"": "Any time", "1": "Last 24 hours",
                           "7": "Last 7 days", "30": "Last 30 days"},
                          value=st["since"], label="Window").props(
            "dense outlined options-dense").classes("lg-filter w-40")

    body = ui.column().classes("w-full gap-0")

    async def load() -> None:
        args = ["-n", str(st["limit"])]
        if st["actor"]:
            args += ["--actor", st["actor"]]
        for v in st["verbs"]:
            args += ["--verb", v]
        if st["since"]:
            from datetime import datetime, timedelta, timezone
            stamp = (datetime.now(timezone.utc)
                     - timedelta(days=int(st["since"]))).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            args += ["--since", stamp]
        env = await page.store.call(page.path, "log", *args)
        body.clear()
        with body:
            draw(page, env, st, load)

    async def changed(_=None) -> None:
        st.update(actor=actor.value or "", verbs=list(verbs.value or []),
                  since=since.value or "", limit=PAGE)
        await load()

    async def text_changed(_=None) -> None:
        st["text"] = text.value or ""
        await load()

    for el in (actor, verbs, since):
        el.on_value_change(changed)
    text.on_value_change(text_changed)
    await load()


def draw(page: Page, env, st: dict, reload) -> None:
    if not env.ok and not env.data:
        for e in env.errors:
            ui.label(e.get("message", "")).classes("lg-banner").style(
                "--c:#ef4444")
        return
    events = env.data.get("events", [])
    total = env.data.get("count", len(events))
    needle = st["text"].lower().split()
    if needle:
        events = [e for e in events if all(
            n in " ".join((e.get("task", ""), e.get("title", ""),
                           e.get("text", ""), e.get("actor", ""))).lower()
            for n in needle)]
    actors = {e.get("actor") for e in events}
    with ui.row().classes("w-full items-center gap-2 pb-1"):
        ui.label(f"{len(events)} shown · {total} matching in the ledger · "
                 f"{len(actors)} actor{'s' if len(actors) != 1 else ''}"
                 ).classes("lg-muted text-sm")
    if not events:
        ui.label("No activity matches").classes("lg-card lg-empty w-full")
        return
    with ui.column().classes("lg-card w-full gap-0 px-4 pb-3"):
        day = None
        for e in events:
            d = model.local_day(e.get("ts"))
            if d != day:
                day = d
                ui.label(d).classes("lg-day w-full")
            log_item(e, page, show_task=True)
    if total > st["limit"]:
        async def more() -> None:
            st["limit"] += PAGE
            await reload()
        with ui.row().classes("w-full justify-center pt-2"):
            ui.button(f"Load {min(PAGE, total - st['limit'])} more",
                      icon="expand_more", on_click=more).props(
                "outline no-caps")

