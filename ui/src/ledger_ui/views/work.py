"""Work: the filterable task table. Rows come from `list --json`."""
from __future__ import annotations

from nicegui import ui

from .. import model, theme
from ..shell import Page

COLUMNS = [
    {"name": "status", "label": "Status", "field": "status_rank",
     "sortable": True, "align": "left"},
    {"name": "priority", "label": "P", "field": "priority", "sortable": True,
     "align": "left"},
    {"name": "id", "label": "Task", "field": "id", "sortable": True,
     "align": "left"},
    {"name": "title", "label": "Title", "field": "title", "sortable": True,
     "align": "left", "style": "white-space: normal; min-width: 320px"},
    {"name": "owner", "label": "Owner", "field": "owner", "sortable": True,
     "align": "left"},
    {"name": "size", "label": "Size", "field": "size_rank",
     "sortable": True, "align": "left"},
    {"name": "progress", "label": "Open", "field": "open_items",
     "sortable": True, "align": "right"},
    {"name": "created", "label": "Created", "field": "created",
     "sortable": True, "align": "right"},
]

STATUS_CELL = r'''
<q-td :props="props">
  <span class="lg-chip" :style="{'--c': props.row.status_color}">
    <i class="q-icon material-icons" style="font-size:13px">{{ props.row.status_icon }}</i>
    {{ props.row.status_label }}</span>
</q-td>'''
PRIORITY_CELL = r'''
<q-td :props="props"><span class="lg-prio" :style="{'--c': props.row.prio_color}">
  {{ props.row.priority.toUpperCase() }}</span></q-td>'''
ID_CELL = r'''<q-td :props="props"><span class="lg-id">{{ props.row.id }}</span></q-td>'''
TITLE_CELL = r'''
<q-td :props="props">
  <div style="font-weight:550; line-height:1.35">{{ props.row.title }}</div>
  <div v-if="props.row.blocked_on" class="lg-small" style="color:#d97706; margin-top:2px">
    ⏸ {{ props.row.blocked_on }}</div>
  <div v-if="props.row.tag_list.length" style="margin-top:3px; display:flex; gap:4px; flex-wrap:wrap">
    <span v-for="t in props.row.tag_list" :key="t" class="lg-tag">{{ t }}</span></div>
</q-td>'''
OWNER_CELL = r'''
<q-td :props="props">
  <div v-if="props.row.owner" class="lg-small" style="font-weight:600">{{ props.row.owner }}</div>
  <div v-if="props.row.claimed_ago" class="lg-small lg-muted">{{ props.row.claimed_ago }}</div>
</q-td>'''
PROGRESS_CELL = r'''
<q-td :props="props" class="lg-small">
  <span v-if="props.row.open_steps" title="open steps">☐ {{ props.row.open_steps }}</span>
  <span v-if="props.row.open_questions" title="open questions" style="margin-left:8px">? {{ props.row.open_questions }}</span>
  <span v-if="props.row.commits" title="commits" class="lg-muted" style="margin-left:8px">⎇ {{ props.row.commits }}</span>
</q-td>'''
SIZE_CELL = r'''<q-td :props="props"><span class="lg-tag">{{ props.row.size }}</span></q-td>'''
CREATED_CELL = r'''
<q-td :props="props" class="lg-small lg-muted" :title="props.row.created">{{ props.row.created_day }}</q-td>'''

STATUS_RANK = {s: i for i, s in enumerate(
    ("in_progress", "blocked", "todo", "done", "dropped"))}
SIZE_RANK = {s: i for i, s in enumerate(model.SIZES)}


def table_row(r: dict) -> dict:
    status = r.get("status", "")
    label, colour, icon = theme.STATUS.get(status, (status, "#94a3b8", "help"))
    tags = model.tags(r)
    return {
        "id": r["id"], "title": r.get("title", ""), "status": status,
        "status_rank": STATUS_RANK.get(status, 9), "status_label": label,
        "status_color": colour, "status_icon": icon,
        "priority": r.get("priority", ""),
        "prio_color": theme.PRIORITY.get(r.get("priority", ""), "#94a3b8"),
        "size": r.get("size", ""), "size_rank": SIZE_RANK.get(r.get("size"), 9),
        "owner": r.get("claimed_by") or "",
        "claimed_ago": model.ago(r.get("claimed_at")),
        "blocked_on": r.get("blocked_on") or "",
        "tag_list": tags,
        "open_steps": r.get("open_steps", 0),
        "open_questions": r.get("open_questions", 0),
        "commits": r.get("commits", 0),
        "open_items": r.get("open_steps", 0) + r.get("open_questions", 0),
        "created": r.get("created", ""),
        "created_day": (r.get("created") or "")[:10],
    }


async def render(page: Page, _container) -> None:
    rows = page.snap.task_rows
    f: model.Filters = page.state.setdefault("work_filters", model.Filters())

    with ui.row().classes("w-full items-end justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Work").classes("lg-h1")
            shown = ui.label().classes("lg-muted text-sm")

    status_opts = {s: theme.STATUS[s][0] for s in model.STATUSES}
    with ui.row().classes("w-full gap-2 items-center"):
        search = ui.input(placeholder="Filter by id, title, tag, owner…",
                          value=f.text).props(
            "dense outlined clearable").classes("lg-filter w-72")
        with search.add_slot("prepend"):
            ui.icon("search")
        st = ui.select(status_opts, multiple=True, value=list(f.statuses),
                       label="Status").props(
            "dense outlined use-chips options-dense").classes(
            "lg-filter min-w-[220px]")
        pr = ui.select(list(model.PRIORITIES), multiple=True,
                       value=list(f.priorities), label="Priority").props(
            "dense outlined use-chips options-dense").classes(
            "lg-filter min-w-[120px]")
        sz = ui.select(list(model.SIZES), multiple=True, value=list(f.sizes),
                       label="Size").props(
            "dense outlined use-chips options-dense").classes(
            "lg-filter min-w-[110px]")
        tg = ui.select([""] + model.all_tags(rows), value=f.tag, label="Tag",
                       with_input=True).props(
            "dense outlined clearable options-dense").classes(
            "lg-filter w-44")
        ow = ui.select([""] + model.all_owners(rows), value=f.owner,
                       label="Owner", with_input=True).props(
            "dense outlined clearable options-dense").classes(
            "lg-filter w-52")
        bk = ui.select({"": "Any", "human": "On human", "task": "On a task",
                        "external": "External", "handoff": "Integration"},
                       value=f.blocked, label="Blocked").props(
            "dense outlined options-dense").classes("lg-filter w-36")

        def reset() -> None:
            page.state["work_filters"] = model.Filters()
            search.value, st.value, pr.value, sz.value = "", list(
                model.OPEN), [], []
            tg.value = ow.value = bk.value = ""
        ui.button("Reset", icon="restart_alt", on_click=reset).props(
            "flat dense no-caps color=grey-7")

    table = ui.table(columns=COLUMNS, rows=[], row_key="id",
                     pagination={"rowsPerPage": 50, "sortBy": None}).classes(
        "lg-table w-full").props("flat")
    for name, tpl in (("status", STATUS_CELL), ("priority", PRIORITY_CELL),
                      ("id", ID_CELL), ("title", TITLE_CELL),
                      ("owner", OWNER_CELL), ("size", SIZE_CELL),
                      ("progress", PROGRESS_CELL),
                      ("created", CREATED_CELL)):
        table.add_slot(f"body-cell-{name}", tpl)
    table.on("rowClick", lambda e: _row_click(page, e.args))

    def apply(_=None) -> None:
        nf = model.Filters(
            text=search.value or "", statuses=tuple(st.value or ()),
            priorities=tuple(pr.value or ()), sizes=tuple(sz.value or ()),
            tag=tg.value or "", owner=ow.value or "", blocked=bk.value or "")
        page.state["work_filters"] = nf
        hits = [table_row(r) for r in rows if nf.matches(r)]
        table.rows = hits
        table.update()
        shown.text = f"{len(hits)} of {len(rows)} tasks"

    for el in (search, st, pr, sz, tg, ow, bk):
        el.on_value_change(apply)
    apply()


def _row_click(page: Page, args) -> None:
    row = next((a for a in (args if isinstance(args, list) else [args])
                if isinstance(a, dict) and "id" in a), None)
    if row:
        page.open_task(row["id"])
