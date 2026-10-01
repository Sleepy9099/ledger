"""The task inspector body: `show <id> --json` rendered section by section,
mirroring the task file (header, Spec, Next Steps, Open Questions, Commits,
Log). Read-only."""
from __future__ import annotations

from nicegui import ui

from .. import model, theme
from ..client import Envelope
from ..shell import Page

# code-friendly: agent specs are full of snake_case paths; `_x_` must not
# become italics
MD_EXTRAS = ["fenced-code-blocks", "tables", "code-friendly",
             "cuddled-lists"]


def render_task(page: Page, env: Envelope, on_close) -> None:
    if not env.ok and not env.data:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Task unavailable").classes("lg-h2")
            ui.button(icon="close", on_click=on_close).props(
                "flat round dense")
        for e in env.errors:
            ui.label(e.get("message", "")).classes("lg-banner").style(
                "--c:#ef4444")
        return
    d = env.data
    h = d.get("header", {})
    rows_by_id = {r["id"]: r for r in (page.snap.task_rows if page.snap
                                       else [])}
    tid = h.get("id", "")

    # -- title block -----------------------------------------------------------
    with ui.row().classes("w-full items-center gap-2 no-wrap"):
        ui.label(tid).classes("lg-id text-sm")
        ui.button(icon="content_copy", on_click=lambda: (
            ui.clipboard.write(tid), ui.notify(f"Copied {tid}"))).props(
            "flat round dense size=sm color=grey-6").tooltip("Copy id")
        ui.space()
        ui.button(icon="close", on_click=on_close).props(
            "flat round dense color=grey-7")
    ui.label(h.get("title", "")).classes("lg-h1").style("font-size:20px")
    with ui.row().classes("items-center gap-2"):
        theme.status_chip(h.get("status", ""))
        theme.chip(h.get("priority", "").upper(),
                   theme.PRIORITY.get(h.get("priority", ""), "#94a3b8"))
        theme.chip(f"size {h.get('size', '')}", "#64748b")
        rel = d.get("closed_relation")
        if rel:
            theme.chip(f"{rel.get('kind')} of {rel.get('target')}",
                       "#94a3b8", "merge")
    theme.tag_list(model.split_list(h.get("tags")))

    with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1 lg-small"):
        def fact(label: str, value: str) -> None:
            ui.label(label).classes("lg-muted")
            ui.label(value or "—")
        fact("Created", f"{model.local_time(h.get('created'))} "
                        f"({model.ago(h.get('created'))})")
        if h.get("claimed_by"):
            fact("Claimed by", f"{h['claimed_by']} · "
                               f"{model.ago(h.get('claimed_at'))}")
        if h.get("closed"):
            fact("Closed", f"{model.local_time(h.get('closed'))} "
                           f"({model.ago(h.get('closed'))})")
        fact("Last activity", model.ago(d.get("last_activity")))
        if d.get("resources"):
            fact("Leases", ", ".join(d["resources"]))

    if h.get("blocked_on"):
        kind = model.blocked_kind(h["blocked_on"])
        colour = theme.HUMAN if kind == "human" else "#f59e0b"
        with ui.row().classes("lg-banner w-full items-center gap-2 no-wrap"
                              ).style(f"--c:{colour}"):
            ui.icon("pause_circle").style(f"color:{colour}")
            ui.label("Blocked on").classes("font-semibold")
            target = h["blocked_on"]
            if kind == "task":
                page.task_link(target)
            else:
                ui.label(target)

    # -- dependencies ----------------------------------------------------------
    depends = model.split_list(h.get("depends_on"))
    dependents = d.get("dependents", [])
    absorbed = d.get("absorbed", [])
    if depends or dependents or absorbed:
        _section("Dependencies")
        with ui.column().classes("w-full gap-1"):
            for dep in depends:
                _dep_row(page, dep, rows_by_id, "Depends on")
            for dep in dependents:
                _dep_row(page, dep, rows_by_id, "Needed by")
            for a in absorbed:
                _dep_row(page, a.get("id"), rows_by_id,
                         f"Absorbed ({a.get('kind')})")

    # -- spec ------------------------------------------------------------------
    _section("Spec")
    spec = d.get("spec") or ""
    if spec.strip():
        ui.markdown(spec, extras=MD_EXTRAS).classes("lg-md w-full")
    else:
        ui.label("No spec").classes("lg-muted lg-small")

    # -- steps -----------------------------------------------------------------
    steps = d.get("next_steps", [])
    if steps:
        done = sum(1 for s in steps if s.get("done"))
        _section(f"Next steps · {done}/{len(steps)}")
        ui.linear_progress(value=done / len(steps), show_value=False).props(
            "rounded color=positive track-color=grey-3").classes("h-1.5")
        with ui.column().classes("w-full gap-1"):
            for s in steps:
                with ui.row().classes("items-start gap-2 no-wrap"):
                    ui.icon("check_box" if s.get("done")
                            else "check_box_outline_blank").style(
                        f"color:{'#10b981' if s.get('done') else '#94a3b8'};"
                        "font-size:18px")
                    ui.label(s.get("text", "")).classes(
                        "text-sm" + (" lg-muted line-through"
                                     if s.get("done") else ""))

    # -- questions -------------------------------------------------------------
    questions = d.get("open_questions", [])
    if questions:
        _section("Questions")
        with ui.column().classes("w-full gap-2"):
            for q in questions:
                human = q.get("human")
                with ui.column().classes(
                        "lg-question w-full p-3 gap-1"
                        + (" human" if human else "")):
                    with ui.row().classes("items-center gap-2"):
                        if human:
                            theme.chip("HUMAN", theme.HUMAN,
                                       "record_voice_over", solid=True)
                        theme.chip("answered" if q.get("answered")
                                   else "open",
                                   "#10b981" if q.get("answered")
                                   else "#f59e0b")
                        ui.label(f"#{q.get('n')}").classes("lg-id")
                    ui.label(q.get("text", "").replace(";     ", "\n")
                             ).classes("text-sm whitespace-pre-wrap")
                    if q.get("answer"):
                        with ui.row().classes("items-start gap-2 no-wrap"):
                            ui.icon("subdirectory_arrow_right").classes(
                                "lg-muted")
                            ui.label(q["answer"]).classes(
                                "text-sm font-medium")

    # -- commits ---------------------------------------------------------------
    commits = d.get("commits", [])
    extra = [s for s in d.get("effective_commits", [])
             if not any(c["sha"].startswith(s) or s.startswith(c["sha"])
                        for c in commits)]
    if commits or extra:
        _section(f"Commits · {len(commits) + len(extra)}")
        with ui.column().classes("w-full gap-1"):
            for c in commits:
                with ui.row().classes("items-center gap-3 no-wrap"):
                    ui.label(c["sha"][:8]).classes("lg-id")
                    ui.label(c.get("date", "")).classes("lg-muted lg-small")
                    ui.label(c.get("subject", "")).classes("text-sm truncate")
            for s in extra:
                with ui.row().classes("items-center gap-3 no-wrap"):
                    ui.label(s[:8]).classes("lg-id")
                    ui.label("via trailer").classes("lg-muted lg-small")

    # -- log -------------------------------------------------------------------
    log = list(reversed(d.get("log", [])))
    _section(f"Activity · {len(log)}")
    with ui.column().classes("w-full gap-0"):
        for e in log:
            log_item(e)

    if d.get("path"):
        ui.label(d["path"]).classes("lg-id break-all mt-2").style(
            "white-space: normal")


def log_item(e: dict, page: Page | None = None, show_task: bool = False,
             ) -> None:
    icon, colour = theme.verb_style(e.get("verb", ""))
    dead = e.get("verb") == "note(dead-end)"
    with ui.element("div").classes("lg-timeline-item w-full"):
        ui.html(f'<div class="lg-timeline-dot" style="--c:{colour}">'
                f'<i class="q-icon material-icons" style="font-size:14px">'
                f'{icon}</i></div>', sanitize=False)
        with ui.column().classes("gap-0 min-w-0" + (" lg-dead-end"
                                                     if dead else "")):
            with ui.row().classes("items-center gap-2 lg-small"):
                ui.label(e.get("verb", "")).classes("font-semibold").style(
                    f"color:{colour}")
                ui.label(e.get("actor", "")).classes("lg-muted")
                if show_task and page is not None and e.get("task"):
                    page.task_link(e["task"])
                ui.label(model.local_time(e.get("ts"), "%H:%M") if show_task
                         else f"{model.local_time(e.get('ts'))}").classes(
                    "lg-muted").tooltip(e.get("ts", ""))
            if show_task and e.get("title"):
                ui.label(e["title"]).classes("lg-small lg-muted truncate")
            ui.label(e.get("text", "")).classes(
                "text-sm whitespace-pre-wrap break-words")


def _section(title: str) -> None:
    ui.label(title).classes("lg-card-title mt-3")


def _dep_row(page: Page, tid: str, rows_by_id: dict, relation: str) -> None:
    r = rows_by_id.get(tid, {})
    with ui.row().classes("items-center gap-2 no-wrap w-full"):
        ui.label(relation).classes("lg-muted lg-small w-24 shrink-0")
        if r:
            theme.status_chip(r.get("status", ""))
        page.task_link(tid)
        ui.label(r.get("title", "(not in this checkout)")).classes(
            "text-sm truncate")
