"""Dependencies: the depends_on graph, laid out left (dependencies) to right
(what they unblock). Starts with every open task plus the closed tasks they
depend on directly; "load more" pulls in one more closed layer at a time and
"everything" renders the whole corpus."""
from __future__ import annotations

from nicegui import ui

from .. import graphlayout as gl
from .. import model, theme
from ..shell import Page

SIZE_PX = {"xs": 9, "s": 12, "m": 15, "l": 19, "xl": 23}

TOOLTIP = r'''p => {
  if (p.dataType !== 'node') return '';
  const d = p.data;
  return `<div style="max-width:340px;white-space:normal">
    <b style="font-family:monospace">${d.name}</b> · ${d.statusLabel} · ${d.priority.toUpperCase()} · ${d.size}<br/>
    <span style="font-weight:600">${d.title}</span>
    ${d.owner ? `<br/><span style="opacity:.75">claimed by ${d.owner}</span>` : ''}
    ${d.blocked ? `<br/><span style="color:#d97706">blocked on ${d.blocked}</span>` : ''}
  </div>`;
}'''
LABEL = r'''p => p.data.short'''


async def render(page: Page, container) -> None:
    rows = page.snap.task_rows
    scope: gl.Scope = page.state.setdefault("graph_scope", gl.Scope())
    stale = {c["id"] for c in page.snap.report.data.get("agents", {}).get(
        "stranded_claims", [])}

    async def rerender() -> None:
        container.clear()
        with container:
            await render(page, container)

    ids = gl.select(rows, scope)
    lay = gl.layout(rows, ids, include_isolated=scope.isolated)
    more = gl.more_available(rows, scope)

    with ui.row().classes("w-full items-end justify-between"):
        with ui.column().classes("gap-0"):
            ui.label("Dependencies").classes("lg-h1")
            ui.label(f"{len(lay.positions)} of {len(rows)} tasks · "
                     f"{len(lay.edges)} edges · {lay.layers} layers"
                     + (f" · {len(lay.isolated)} without edges"
                        if lay.isolated else "")).classes("lg-muted text-sm")
        with ui.row().classes("items-center gap-2"):
            mode = ui.toggle({"open": "Open work", "all": "Everything",
                              "focus": "Focus"}, value=scope.mode).props(
                "dense no-caps unelevated toggle-color=primary")
            iso = ui.switch("Tasks without edges", value=scope.isolated
                            ).props("dense")

    async def set_mode(e) -> None:
        scope.mode = e.value
        if scope.mode == "focus" and not scope.focus:
            scope.focus = next((r["id"] for r in rows
                                if r.get("status") == "in_progress"), None) \
                or (rows[0]["id"] if rows else None)
        await rerender()
    mode.on_value_change(set_mode)

    async def set_iso(e) -> None:
        scope.isolated = bool(e.value)
        await rerender()
    iso.on_value_change(set_iso)

    with ui.row().classes("w-full items-center gap-2"):
        if scope.mode == "open":
            ui.label(f"Closed dependency layers: {scope.layers}").classes(
                "lg-small lg-muted")
            async def widen(step: int) -> None:
                scope.layers = max(scope.layers + step, 0)
                await rerender()
            if more:
                ui.button(f"Load more (+{more})", icon="unfold_more",
                          on_click=lambda: widen(1)).props(
                    "outline dense no-caps")
            if scope.layers > 0:
                ui.button("Fewer", icon="unfold_less",
                          on_click=lambda: widen(-1)).props(
                    "flat dense no-caps color=grey-7")
        if scope.mode == "focus":
            opts = {r["id"]: f"{r['id']} · {r.get('title', '')[:60]}"
                    for r in rows}
            sel = ui.select(opts, value=scope.focus, with_input=True,
                            label="Focus task").props(
                "dense outlined options-dense").classes("lg-filter w-[480px]")

            async def set_focus(e) -> None:
                scope.focus = e.value
                await rerender()
            sel.on_value_change(set_focus)
        ui.space()
        legend()

    if not lay.positions:
        ui.label("Nothing to draw in this scope.").classes(
            "lg-card lg-empty w-full")
        return

    by_id = {r["id"]: r for r in rows}
    nodes = []
    for tid, (x, y) in lay.positions.items():
        r = by_id[tid]
        status = r.get("status", "")
        label, colour, _ = theme.STATUS.get(status, (status, "#94a3b8", ""))
        border, width, btype = "rgba(0,0,0,0)", 0, "solid"
        if model.blocked_kind(r.get("blocked_on")) == "human":
            border, width = theme.HUMAN, 3
        elif r.get("priority") in ("p0", "p1") and status in model.OPEN:
            border, width = theme.PRIORITY[r["priority"]], 2
        if tid in stale:
            border, width, btype = "#f97316", 3, "dashed"
        title = r.get("title", "")
        nodes.append({
            "name": tid, "x": x, "y": y,
            "symbolSize": SIZE_PX.get(r.get("size"), 14),
            "itemStyle": {"color": colour, "borderColor": border,
                          "borderWidth": width, "borderType": btype,
                          "opacity": 0.55 if status in ("done", "dropped")
                          else 1},
            "title": theme.esc(title), "statusLabel": label,
            "priority": r.get("priority", ""), "size": r.get("size", ""),
            "owner": theme.esc(r.get("claimed_by") or ""),
            "blocked": theme.esc(r.get("blocked_on") or ""),
            "short": f"{tid}  {title[:34]}{'…' if len(title) > 34 else ''}",
        })
    focus = scope.focus if scope.mode == "focus" else None
    if focus in lay.positions:
        for n in nodes:
            if n["name"] == focus:
                n["symbolSize"] += 8
                n["itemStyle"].update(borderColor="#4f46e5", borderWidth=4)
    links = [{"source": d, "target": t} for d, t in lay.edges]

    options = {
        "animation": len(nodes) < 400,
        "tooltip": {"trigger": "item", ":formatter": TOOLTIP,
                    "confine": True},
        "series": [{
            "type": "graph", "layout": "none", "roam": True,
            "scaleLimit": {"min": 0.05, "max": 6},
            "data": nodes, "links": links,
            "edgeSymbol": ["none", "arrow"], "edgeSymbolSize": 6,
            "lineStyle": {"color": "#94a3b8", "opacity": 0.3, "width": 1,
                          "curveness": 0.08},
            "label": {"show": True, "position": "right", "fontSize": 11,
                      ":formatter": LABEL, "color": "inherit"},
            "labelLayout": {"hideOverlap": True},
            "emphasis": {"focus": "adjacency",
                         "lineStyle": {"width": 2, "opacity": 1}},
        }],
    }
    chart = ui.echart(options).classes("lg-card w-full").style(
        "height: calc(100vh - 230px); min-height: 520px")
    chart.on_point_click(lambda e: page.open_task(e.name)
                         if e.data_type == "node" else None)
    # the canvas is sized before the page layout settles; resize once it has
    ui.timer(0.3, lambda: chart.run_chart_method("resize"), once=True)
    ui.label("Scroll to zoom, drag to pan, hover to trace a task's "
             "neighbours, click to inspect.").classes("lg-muted lg-small")


def legend() -> None:
    with ui.row().classes("items-center gap-3 lg-small lg-muted"):
        for s in ("todo", "in_progress", "blocked", "done"):
            label, colour, _ = theme.STATUS[s]
            ui.html(f'<span style="display:inline-flex;align-items:center;'
                    f'gap:5px"><span style="width:10px;height:10px;'
                    f'border-radius:50%;background:{colour}"></span>'
                    f'{label}</span>', sanitize=False)
        ui.html(f'<span style="display:inline-flex;align-items:center;gap:5px">'
                f'<span style="width:10px;height:10px;border-radius:50%;'
                f'border:3px solid {theme.HUMAN}"></span>blocked on human'
                f'</span>', sanitize=False)
        ui.html('<span style="display:inline-flex;align-items:center;gap:5px">'
                '<span style="width:10px;height:10px;border-radius:50%;'
                'border:2px dashed #f97316"></span>stale claim</span>',
                sanitize=False)
