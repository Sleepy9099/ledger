"""Human Inbox: every open HUMAN question and every task blocked on a human.

Read-only by decision (2026-10-01): the UI shows the exact CLI command that
records an answer; it never runs it.
"""
from __future__ import annotations

from nicegui import ui

from .. import model, theme
from ..client import OPERATOR
from ..shell import Page
from .task import MD_EXTRAS


def resolve_command(task: str, n: int) -> str:
    return (f'python .ledger/ledger.py question {task} resolve {n} '
            f'--answer "..." --session {OPERATOR}')


async def render(page: Page, _container) -> None:
    snap = page.snap
    data = snap.questions.data
    questions = data.get("questions", [])
    blocked = data.get("blocked_on_human", [])
    rows = snap.task_rows
    dmap = model.dependents_map(rows)

    with ui.row().classes("w-full items-end justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Human Inbox").classes("lg-h1")
            ui.label(f"{len(questions)} open decision"
                     f"{'s' if len(questions) != 1 else ''} · "
                     f"{len(blocked)} task{'s' if len(blocked) != 1 else ''}"
                     f" blocked on a human").classes("lg-muted text-sm")
        theme.chip("read-only — answer with the CLI", "#64748b", "lock")

    if not questions and not blocked:
        with ui.column().classes("lg-card w-full items-center p-10 gap-2"):
            ui.icon("mark_email_read").style("font-size:42px;color:#10b981")
            ui.label("Inbox zero").classes("lg-h2")
            ui.label("No agent is waiting on a human decision.").classes(
                "lg-muted text-sm")
        return

    # group questions by task, most-blocking task first
    by_task: dict[str, list[dict]] = {}
    for q in questions:
        by_task.setdefault(q["task"], []).append(q)
    order = sorted(by_task, key=lambda t: (
        -len(model.open_downstream(rows, t, dmap)),
        by_task[t][0].get("priority", "p9")))

    for tid in order:
        qs = by_task[tid]
        first = qs[0]
        waiting = model.open_downstream(rows, tid, dmap)
        with ui.column().classes("lg-card w-full gap-3 p-4"):
            with ui.row().classes("w-full items-center gap-2"):
                theme.priority_label(first.get("priority", ""))
                page.task_link(tid)
                theme.status_chip(first.get("status", ""))
                if first.get("claimed_by"):
                    theme.chip(first["claimed_by"], "#3b82f6", "smart_toy")
                if waiting:
                    theme.chip(f"{len(waiting)} task"
                               f"{'s' if len(waiting) != 1 else ''} waiting",
                               "#6366f1", "account_tree")
                ui.space()
                theme.chip(f"{len(qs)} question{'s' if len(qs) != 1 else ''}",
                           theme.HUMAN, "record_voice_over")
            ui.label(first.get("title", "")).classes("lg-h2 lg-link").on(
                "click", lambda _=None, t=tid: page.open_task(t))
            for q in qs:
                with ui.column().classes("lg-question human w-full p-3 gap-2"):
                    with ui.row().classes("items-start gap-2 no-wrap w-full"):
                        ui.label(f"#{q.get('n')}").classes("lg-id pt-0.5")
                        ui.label(q.get("text", "")).classes(
                            "text-[14.5px] font-medium grow")
                    ctx = q.get("context") or []
                    if ctx:
                        # one thought per line: keep the breaks ("  \n")
                        ui.markdown("  \n".join(c.strip() for c in ctx),
                                    extras=MD_EXTRAS).classes(
                            "lg-context lg-md w-full")
                    cmd = resolve_command(tid, q.get("n", 1))
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        ui.label(cmd).classes("lg-code grow")
                        ui.button(icon="content_copy", on_click=lambda c=cmd: (
                            ui.clipboard.write(c),
                            ui.notify("Command copied — run it in the "
                                      "checkout, then commit the task file"))
                                  ).props("flat round dense color=grey-7"
                                          ).tooltip("Copy command")

    if blocked:
        ui.label("Blocked on a human").classes("lg-card-title mt-2")
        with ui.column().classes("lg-card w-full gap-0"):
            for b in blocked:
                with ui.column().classes("lg-row clickable w-full gap-1").on(
                        "click", lambda _=None, t=b["id"]: page.open_task(t)):
                    with ui.row().classes("items-center gap-2"):
                        theme.priority_label(b.get("priority", ""))
                        ui.label(b["id"]).classes("lg-id")
                        ui.label(b.get("title", "")).classes(
                            "text-sm font-medium")
                    if b.get("reason"):
                        ui.label(b["reason"]).classes(
                            "lg-small lg-muted whitespace-pre-wrap")
                    ui.label(f"python .ledger/ledger.py unblock {b['id']} "
                             f"--session {OPERATOR}").classes(
                        "lg-code lg-small")

    ui.label("Batch alternative: `python .ledger/ledger.py questions --human "
             "--json > q.json`, add an \"answer\" to each row, then "
             "`python .ledger/ledger.py answers apply q.json --session "
             f"{OPERATOR}`.").classes("lg-muted lg-small mt-2")

