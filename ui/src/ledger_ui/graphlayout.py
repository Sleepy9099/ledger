"""Dependency-graph scoping and a layered (left-to-right) layout.

Pure Python over `list --json` rows: edges are `depends_on`, drawn from the
dependency to the task that needs it, so work flows left to right.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from . import model

DX, DY = 200, 56
STATUS_RANK = {"in_progress": 0, "blocked": 1, "todo": 2, "done": 3,
               "dropped": 4}


@dataclass
class Scope:
    mode: str = "open"      # open | all | focus
    layers: int = 1         # open mode: closed dependency layers pulled in
    focus: str | None = None
    isolated: bool = True   # include tasks with no edges in the scope


def select(rows: list[dict], scope: Scope) -> set[str]:
    by_id = {r["id"]: r for r in rows}
    if scope.mode == "all":
        return set(by_id)
    if scope.mode == "focus" and scope.focus in by_id:
        return ancestors(rows, scope.focus) | descendants(rows, scope.focus) \
            | {scope.focus}
    chosen = {r["id"] for r in rows if r.get("status") in model.OPEN}
    frontier = set(chosen)
    for _ in range(max(scope.layers, 0)):
        nxt = {d for t in frontier for d in model.deps(by_id[t])
               if d in by_id and d not in chosen}
        if not nxt:
            break
        chosen |= nxt
        frontier = nxt
    return chosen


def more_available(rows: list[dict], scope: Scope) -> int:
    """How many nodes one more 'load more' step would add."""
    if scope.mode != "open":
        return 0
    now = select(rows, scope)
    bigger = select(rows, Scope("open", scope.layers + 1))
    return len(bigger - now)


def ancestors(rows: list[dict], tid: str) -> set[str]:
    by_id = {r["id"]: r for r in rows}
    seen: set[str] = set()
    stack = [tid]
    while stack:
        for d in model.deps(by_id.get(stack.pop(), {})):
            if d in by_id and d not in seen:
                seen.add(d)
                stack.append(d)
    return seen


def descendants(rows: list[dict], tid: str) -> set[str]:
    dmap = model.dependents_map(rows)
    seen: set[str] = set()
    stack = [tid]
    while stack:
        for c in dmap.get(stack.pop(), []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


@dataclass
class Layout:
    positions: dict[str, tuple[float, float]]
    edges: list[tuple[str, str]]          # (dependency, dependent)
    isolated: list[str]
    layers: int


def layout(rows: list[dict], ids: set[str], include_isolated: bool = True
           ) -> Layout:
    by_id = {r["id"]: r for r in rows if r["id"] in ids}
    edges = [(d, t) for t in by_id for d in model.deps(by_id[t])
             if d in by_id]
    linked = {x for e in edges for x in e}
    preds: dict[str, list[str]] = defaultdict(list)
    succs: dict[str, list[str]] = defaultdict(list)
    for d, t in edges:
        preds[t].append(d)
        succs[d].append(t)

    layer: dict[str, int] = {}

    def depth(t: str, trail: frozenset = frozenset()) -> int:
        if t in layer:
            return layer[t]
        if t in trail:  # a cycle (validate forbids it) — cut it here
            return 0
        trail = trail | {t}
        value = 1 + max((depth(p, trail) for p in preds[t]), default=-1)
        layer[t] = value
        return value

    import sys
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 10000))
    try:
        for t in linked:
            depth(t)
    finally:
        sys.setrecursionlimit(old)

    # sources (no dependency in scope) sit just left of their earliest
    # dependent instead of all piling into column 0 with long edges
    for t in linked:
        if not preds[t] and succs[t]:
            layer[t] = max(min(layer[s] for s in succs[t]) - 1, 0)

    def key(t: str):
        r = by_id[t]
        return (STATUS_RANK.get(r.get("status"), 9), r.get("priority", "p9"),
                r.get("created", ""), t)

    n_layers = max(layer.values(), default=-1) + 1
    columns: list[list[str]] = [[] for _ in range(n_layers)]
    for t in linked:
        columns[layer[t]].append(t)
    for col in columns:
        col.sort(key=key)

    # barycentre sweeps to reduce crossings
    for _ in range(4):
        for i in range(1, n_layers):
            pos = {t: k for k, t in enumerate(columns[i - 1])}
            columns[i].sort(key=lambda t: (_bary(preds[t], pos), key(t)))
        for i in range(n_layers - 2, -1, -1):
            pos = {t: k for k, t in enumerate(columns[i + 1])}
            columns[i].sort(key=lambda t: (_bary(succs[t], pos), key(t)))

    positions: dict[str, tuple[float, float]] = {}
    tallest = max((len(c) for c in columns), default=0)
    for i, col in enumerate(columns):
        offset = (tallest - len(col)) * DY / 2
        for k, t in enumerate(col):
            positions[t] = (i * DX, offset + k * DY)

    isolated = sorted((t for t in by_id if t not in linked), key=key)
    if include_isolated and isolated:
        top = (tallest + 2) * DY
        per_row = max(n_layers, 6)
        for k, t in enumerate(isolated):
            positions[t] = ((k % per_row) * DX, top + (k // per_row) * DY)
    return Layout(positions, edges, isolated, n_layers)


def _bary(neighbours: list[str], pos: dict[str, int]) -> float:
    vals = [pos[n] for n in neighbours if n in pos]
    return sum(vals) / len(vals) if vals else float("inf")
