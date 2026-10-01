"""Overview: what needs the human's attention in this checkout, first."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nicegui import ui

from .. import model, theme
from ..shell import Page


async def render(page: Page, _container) -> None:
    snap = page.snap
    rows = snap.task_rows
    counts = model.status_counts(rows)
    q = snap.questions.data
    human_n = len(q.get("questions", [])) + len(q.get("blocked_on_human", []))
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    closed_7d = sum(1 for r in rows if r.get("status") == "done"
                    and (r.get("closed") or "") >= week_ago)

    with ui.row().classes("w-full items-end justify-between"):
        with ui.column().classes("gap-0"):
            ui.label(page.project.name).classes("lg-h1")
            ui.label(f"{page.checkout.label} · {len(rows)} tasks").classes(
                "lg-muted text-sm")
        health_chip(snap)

    with ui.row().classes("w-full gap-3"):
        kpi("To do", counts["todo"], theme.STATUS["todo"][1],
            page.url("work"))
        kpi("Active", counts["in_progress"], theme.STATUS["in_progress"][1],
            page.url("work"))
        kpi("Blocked", counts["blocked"], theme.STATUS["blocked"][1],
            page.url("work"))
        kpi("Waiting on you", human_n, theme.HUMAN, page.url("inbox"))
        kpi("Done · 7 days", closed_7d, theme.STATUS["done"][1],
            page.url("activity"))

    with ui.row().classes("w-full gap-4 items-start no-wrap max-lg:flex-wrap"):
        with ui.column().classes("gap-4 grow min-w-0").style("flex: 2 1 0"):
            attention_card(page)
            blocked_card(page)
        with ui.column().classes("gap-4 min-w-[300px]").style("flex: 1 1 0"):
            active_card(page)
            next_card(page)
            closed_card(page)


def health_chip(snap) -> None:
    caps = snap.caps
    if not snap.doctor.ok and not snap.doctor.data:
        theme.chip("ledger unreadable", "#ef4444", "error")
    elif not caps.supported or not caps.compatible:
        theme.chip("needs attention", "#ef4444", "warning")
    elif any(e.get("severity") == "error" for e in snap.tasks.errors):
        theme.chip("corrupt task file", "#ef4444", "report")
    else:
        theme.chip(f"healthy · ledger {snap.doctor.data.get('tool_version')}",
                   "#10b981", "verified")


def kpi(label: str, value: int, colour: str, target: str) -> None:
    with ui.link(target=target).classes("no-underline text-inherit flex-1"):
        with ui.element("div").classes("lg-card lg-kpi").style(
                f"--c:{colour}"):
            ui.label(str(value)).classes("value")
            ui.label(label).classes("label")


def card(title: str, subtitle: str = ""):
    c = ui.column().classes("lg-card w-full gap-0")
    with c:
        with ui.row().classes("w-full items-baseline gap-2 px-4 pt-3 pb-2"):
            ui.label(title).classes("lg-card-title")
            if subtitle:
                ui.label(subtitle).classes("lg-muted lg-small")
    return c


def attention_card(page: Page) -> None:
    items = model.attention(page.snap)
    with card("Needs your attention", f"{len(items)}" if items else ""):
        if not items:
            with ui.row().classes("lg-empty w-full justify-center gap-2"):
                ui.icon("task_alt").style("color:#10b981")
                ui.label("Nothing needs you right now")
            return
        for a in items[:40]:
            icon, colour, label = theme.ATTENTION.get(
                a.kind, ("info", "#64748b", a.kind))
            row = ui.row().classes("lg-row w-full items-start gap-3 no-wrap"
                                   + (" clickable" if a.task else ""))
            if a.task:
                row.on("click", lambda _=None, t=a.task: page.open_task(t))
            with row:
                ui.html(f'<div class="lg-att-icon" style="--c:{colour}">'
                        f'<i class="q-icon material-icons">{icon}</i></div>',
                        sanitize=False)
                with ui.column().classes("gap-0 grow min-w-0"):
                    with ui.row().classes("items-center gap-2"):
                        theme.chip(label, colour)
                        if a.task:
                            ui.label(a.task).classes("lg-id")
                        if a.waiting:
                            theme.chip(f"{a.waiting} waiting", "#6366f1",
                                       "account_tree")
                    ui.label(a.title).classes("text-sm font-medium").style(
                        "display:-webkit-box;-webkit-line-clamp:3;"
                        "-webkit-box-orient:vertical;overflow:hidden")
                    if a.detail:
                        ui.label(a.detail).classes("lg-muted lg-small").style(
                            "display:-webkit-box;-webkit-line-clamp:2;"
                            "-webkit-box-orient:vertical;overflow:hidden")


def blocked_card(page: Page) -> None:
    groups = model.blocked_groups(page.snap.task_rows)
    if not groups:
        return
    names = {"human": "On a human", "task": "On another task",
             "external": "On something external",
             "handoff": "Ready for integration", "other": "Other"}
    total = sum(len(v) for v in groups.values())
    with card("Blocked", str(total)):
        for kind in ("human", "task", "handoff", "external", "other"):
            rows = groups.get(kind)
            if not rows:
                continue
            with ui.expansion(f"{names[kind]} · {len(rows)}",
                              value=kind in ("human", "task")).classes(
                    "w-full lg-small").props("dense"):
                for r in rows:
                    with ui.row().classes(
                            "lg-row clickable w-full items-start gap-3 "
                            "no-wrap").on(
                            "click", lambda _=None, t=r["id"]:
                            page.open_task(t)):
                        theme.priority_label(r.get("priority", ""))
                        ui.label(r["id"]).classes("lg-id")
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(r.get("title", "")).classes(
                                "text-sm truncate")
                            ui.label(r.get("blocked_on", "")).classes(
                                "lg-muted lg-small truncate")


def active_card(page: Page) -> None:
    groups = model.active_by_actor(page.snap.task_rows)
    n = sum(len(v) for v in groups.values())
    with card("Active work", f"{n} claimed by {len(groups)} "
                             f"session{'s' if len(groups) != 1 else ''}"
              if n else ""):
        if not groups:
            ui.label("No task is claimed").classes("lg-empty w-full")
            return
        for actor, rows in groups.items():
            with ui.column().classes("lg-row w-full gap-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("smart_toy" if actor != "HUMAN" else "person"
                            ).classes("lg-muted")
                    ui.label(actor).classes("text-sm font-semibold")
                for r in rows:
                    with ui.row().classes("items-center gap-2 no-wrap w-full "
                                          "lg-link").on(
                            "click", lambda _=None, t=r["id"]:
                            page.open_task(t)):
                        ui.label(r["id"]).classes("lg-id")
                        ui.label(r.get("title", "")).classes(
                            "text-sm truncate grow")
                        ui.label(model.ago(r.get("claimed_at"))).classes(
                            "lg-muted lg-small whitespace-nowrap")


def next_card(page: Page) -> None:
    data = page.snap.next.data
    task = data.get("task")
    with card("Next up", "what `ledger next` would hand out"):
        if not task:
            ui.label(data.get("reason") or "Nothing eligible").classes(
                "lg-empty w-full")
        else:
            h = task.get("header", {})
            with ui.column().classes("lg-row clickable w-full gap-1").on(
                    "click", lambda _=None, t=h.get("id"): page.open_task(t)):
                with ui.row().classes("items-center gap-2"):
                    theme.priority_label(h.get("priority", ""))
                    ui.label(h.get("id", "")).classes("lg-id")
                    theme.chip(f"size {h.get('size', '')}", "#64748b")
                ui.label(h.get("title", "")).classes("text-sm font-medium")
                if task.get("steps_total"):
                    ui.label(f"{task.get('steps_done', 0)}/"
                             f"{task['steps_total']} steps").classes(
                        "lg-muted lg-small")
        why = data.get("why", [])
        if why:
            with ui.expansion(f"Not eligible · {len(why)}").classes(
                    "w-full lg-small").props("dense"):
                for w in why:
                    with ui.row().classes("items-start gap-2 no-wrap px-2 "
                                          "py-1"):
                        page.task_link(w.get("id", ""))
                        ui.label(w.get("ineligible_because", "")).classes(
                            "lg-small lg-muted")


def closed_card(page: Page) -> None:
    rows = model.recently_closed(page.snap.task_rows)
    if not rows:
        return
    with card("Recently closed"):
        for r in rows:
            with ui.row().classes("lg-row clickable w-full items-center "
                                  "gap-2 no-wrap").on(
                    "click", lambda _=None, t=r["id"]: page.open_task(t)):
                theme.status_chip(r.get("status", ""))
                ui.label(r["id"]).classes("lg-id")
                ui.label(r.get("title", "")).classes("text-sm truncate grow")
                ui.label(model.ago(r.get("closed"))).classes(
                    "lg-muted lg-small whitespace-nowrap")
