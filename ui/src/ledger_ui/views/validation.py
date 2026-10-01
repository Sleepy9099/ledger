"""Validation: `validate --coverage --json`, run on demand (it walks git
history and can take ~20s on a large repo). Rows are rendered verbatim —
code, severity, message, fix_hint — the UI invents no recovery logic."""
from __future__ import annotations

import time

from nicegui import ui

from .. import theme
from ..shell import Page

SEVERITY = {"error": ("#ef4444", "error"), "warning": ("#f59e0b", "warning"),
            "info": ("#0ea5e9", "info")}


async def render(page: Page, container) -> None:
    store = page.store
    env, fresh = store.cached_validation(page.path)
    running = store.validation_running(page.path)

    with ui.row().classes("w-full items-end justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Validation").classes("lg-h1")
            ui.label("ledger validate --coverage — every invariant, plus "
                     "commit → task traceability").classes("lg-muted text-sm")
        btn = ui.button("Run validation" if env is None else "Re-run",
                        icon="play_arrow").props("unelevated no-caps")

    async def run() -> None:
        btn.props("loading")
        started = time.perf_counter()
        await store.validate(page.path)
        page.state["validated_in"] = time.perf_counter() - started
        container.clear()
        with container:
            await render(page, container)
    btn.on_click(run)

    if running:
        btn.props("loading")
        ui.timer(1.0, lambda: _poll(page, container), once=True)

    if env is None:
        with ui.column().classes("lg-card w-full items-center p-10 gap-2"):
            ui.icon("verified").style("font-size:42px;color:var(--lg-muted)")
            ui.label("Not run yet in this session").classes("lg-h2")
            ui.label("Large repos take a while: the coverage check walks git "
                     "history.").classes("lg-muted text-sm")
        return

    rows = env.errors
    counts = {s: sum(1 for e in rows if (e.get("severity") or "error") == s)
              for s in SEVERITY}
    with ui.row().classes("w-full items-center gap-2"):
        if env.ok and not counts["error"]:
            theme.chip("passing", "#10b981", "check_circle", solid=True)
        else:
            theme.chip("failing", "#ef4444", "cancel", solid=True)
        for sev, n in counts.items():
            if n:
                colour, icon = SEVERITY[sev]
                theme.chip(f"{n} {sev}{'s' if n != 1 else ''}", colour, icon)
        if not fresh:
            theme.chip("outdated — files or HEAD changed since", "#f59e0b",
                       "update")
        took = page.state.get("validated_in")
        ui.label(f"ran in {took:.1f}s" if took else
                 f"{env.elapsed_ms / 1000:.1f}s").classes("lg-muted lg-small")

    if not rows:
        with ui.column().classes("lg-card w-full items-center p-10 gap-2"):
            ui.icon("task_alt").style("font-size:42px;color:#10b981")
            ui.label("Every invariant holds").classes("lg-h2")
        return

    groups: dict[str, list[dict]] = {}
    for e in rows:
        groups.setdefault(e.get("code", "?"), []).append(e)
    order = sorted(groups, key=lambda c: (
        min(list(SEVERITY).index(e.get("severity") or "error")
            if (e.get("severity") or "error") in SEVERITY else 9
            for e in groups[c]), c))
    for code in order:
        items = groups[code]
        sev = items[0].get("severity") or "error"
        colour, icon = SEVERITY.get(sev, ("#64748b", "help"))
        with ui.column().classes("lg-card w-full gap-0"):
            with ui.row().classes("w-full items-center gap-2 px-4 pt-3 pb-2"):
                ui.icon(icon).style(f"color:{colour}")
                ui.label(code).classes("lg-h2")
                theme.chip(f"{len(items)}", colour)
            for e in items[:200]:
                with ui.column().classes("lg-row w-full gap-1"):
                    with ui.row().classes("items-start gap-2 no-wrap w-full"):
                        if e.get("task"):
                            page.task_link(e["task"])
                        ui.label(e.get("message", "")).classes(
                            "text-sm grow whitespace-pre-wrap")
                    if e.get("fix_hint"):
                        with ui.row().classes("items-start gap-2 no-wrap"):
                            ui.icon("build").classes("lg-muted").style(
                                "font-size:15px")
                            ui.label(e["fix_hint"]).classes(
                                "lg-small lg-muted whitespace-pre-wrap")
            if len(items) > 200:
                ui.label(f"… {len(items) - 200} more").classes(
                    "lg-muted lg-small px-4 py-2")


async def _poll(page: Page, container) -> None:
    if page.store.validation_running(page.path):
        await page.store.validate(page.path)
    container.clear()
    with container:
        await render(page, container)
