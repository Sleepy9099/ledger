from ledger_ui import graphlayout as gl


def row(tid, status="todo", deps=""):
    return {"id": tid, "title": tid, "status": status, "priority": "p2",
            "size": "m", "created": "2026-01-01T00:00:00Z",
            "depends_on": deps}


ROWS = [
    row("A", "done"), row("B", "done", "A"), row("C", "todo", "B"),
    row("D", "todo", "C"), row("E", "in_progress", "C"),
    row("F", "todo"), row("G", "done"),
]


def test_open_scope_widens_one_closed_layer_at_a_time():
    s = gl.Scope("open", layers=0)
    assert gl.select(ROWS, s) == {"C", "D", "E", "F"}
    assert gl.more_available(ROWS, s) == 1
    assert gl.select(ROWS, gl.Scope("open", layers=1)) == {"B", "C", "D",
                                                           "E", "F"}
    assert gl.select(ROWS, gl.Scope("open", layers=5)) == {"A", "B", "C",
                                                           "D", "E", "F"}
    assert gl.more_available(ROWS, gl.Scope("open", layers=5)) == 0
    assert gl.select(ROWS, gl.Scope("all")) == {r["id"] for r in ROWS}


def test_focus_is_ancestors_plus_descendants():
    assert gl.select(ROWS, gl.Scope("focus", focus="C")) == {"A", "B", "C",
                                                             "D", "E"}


def test_layers_put_dependencies_left_and_isolate_loners():
    lay = gl.layout(ROWS, {r["id"] for r in ROWS})
    x = {t: p[0] for t, p in lay.positions.items()}
    for dep, task in lay.edges:
        assert x[dep] < x[task]
    assert set(lay.isolated) == {"F", "G"} and lay.layers == 4
    hidden = gl.layout(ROWS, {r["id"] for r in ROWS},
                       include_isolated=False)
    assert "F" not in hidden.positions


def test_sources_sit_next_to_their_first_dependent():
    rows = [row("R"), row("X", deps="R"), row("Y", deps="X"),
            row("Z", deps="Y"), row("S"), row("Z2", deps="Z,S")]
    lay = gl.layout(rows, {r["id"] for r in rows})
    x = {t: p[0] / gl.DX for t, p in lay.positions.items()}
    assert x["S"] == x["Z2"] - 1  # not stranded in column 0


def test_cycle_does_not_hang():
    rows = [row("P", deps="Q"), row("Q", deps="P")]
    lay = gl.layout(rows, {"P", "Q"})
    assert set(lay.positions) == {"P", "Q"}
