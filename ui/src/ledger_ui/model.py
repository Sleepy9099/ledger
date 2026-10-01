"""Pure view-model derivations over CLI envelopes (no NiceGUI imports).

Everything here re-shapes what the CLI already decided; nothing re-derives
ledger semantics such as eligibility or validity. Kept free of UI code so it
is unit-testable against a real temp ledger.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

STATUSES = ("todo", "in_progress", "blocked", "done", "dropped")
OPEN = ("todo", "in_progress", "blocked")
PRIORITIES = ("p0", "p1", "p2", "p3")
SIZES = ("xs", "s", "m", "l", "xl")


# -- time --------------------------------------------------------------------

def parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def ago(ts: str | None, now: datetime | None = None) -> str:
    dt = parse_ts(ts)
    if dt is None:
        return ""
    secs = int(((now or datetime.now(timezone.utc)) - dt).total_seconds())
    if secs < 60:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit} ago"
    return ""


def local_time(ts: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    dt = parse_ts(ts)
    return dt.astimezone().strftime(fmt) if dt else ""


def local_day(ts: str | None) -> str:
    return local_time(ts, "%A %d %B %Y")


# -- task rows ----------------------------------------------------------------

def split_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def deps(row: dict) -> list[str]:
    return split_list(row.get("depends_on"))


def tags(row: dict) -> list[str]:
    return split_list(row.get("tags"))


def status_counts(rows: list[dict]) -> dict[str, int]:
    c = Counter(r.get("status") for r in rows)
    return {s: c.get(s, 0) for s in STATUSES}


def blocked_kind(blocked_on: str | None) -> str | None:
    if not blocked_on:
        return None
    if blocked_on == "human":
        return "human"
    if blocked_on.startswith("external:"):
        if blocked_on.startswith("external: ready"):
            return "handoff"
        return "external"
    return "task"


def actor_family(actor: str) -> str:
    """`w-apfs-2026-09-25-e` -> `w-apfs`; `claude-2026-10-01-a` -> `claude`.
    Purely a display grouping for long actor lists."""
    m = re.match(r"^(.*?)-\d{4}-\d{2}-\d{2}(?:-|$)", actor)
    return m.group(1) if m else actor


def actor_kind(actor: str) -> str:
    """The family's first token: `w`, `claude`, `orch`, `HUMAN`..."""
    return actor_family(actor).split("-")[0]


# -- dependency structure ----------------------------------------------------

def dependents_map(rows: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        for d in deps(r):
            out[d].append(r["id"])
    return out


def open_downstream(rows: list[dict], task_id: str,
                    dmap: dict[str, list[str]] | None = None) -> set[str]:
    """Open tasks that (transitively) depend on task_id."""
    dmap = dmap if dmap is not None else dependents_map(rows)
    status = {r["id"]: r.get("status") for r in rows}
    seen: set[str] = set()
    stack = [task_id]
    while stack:
        for child in dmap.get(stack.pop(), []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return {t for t in seen if status.get(t) in OPEN}


# -- attention ---------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Attention:
    kind: str          # human | human-block | corrupt | health | stale-claim
    #                    | stale-block | handoff | bottleneck
    severity: str      # critical | high | medium | low
    title: str
    detail: str = ""
    task: str | None = None
    waiting: int = 0   # open tasks downstream of `task`


def attention(snap) -> list[Attention]:
    rows = snap.task_rows
    by_id = {r["id"]: r for r in rows}
    dmap = dependents_map(rows)
    items: list[Attention] = []

    if not snap.doctor.ok and not snap.doctor.data:
        items.append(Attention("health", "critical", "Ledger unreadable",
                               _first_message(snap.doctor)))
    elif not snap.caps.supported:
        items.append(Attention(
            "health", "critical", "Vendored ledger too old for this UI",
            "re-vendor ledger.py (1.5.0 or newer)"))
    elif not snap.caps.compatible:
        items.append(Attention(
            "health", "critical", "Corpus is newer than the vendored copy",
            _first_message(snap.doctor)))

    for e in snap.tasks.errors:
        if (e.get("severity") or "error") == "error":
            items.append(Attention("corrupt", "critical",
                                   f"Unreadable task file ({e.get('code')})",
                                   e.get("message", ""), e.get("task")))

    for q in snap.questions.data.get("questions", []):
        tid = q.get("task")
        waiting = len(open_downstream(rows, tid, dmap)) if tid else 0
        items.append(Attention("human", "high", q.get("text", ""),
                               q.get("title", ""), tid, waiting))

    for b in snap.questions.data.get("blocked_on_human", []):
        tid = b.get("id")
        items.append(Attention(
            "human-block", "high", f"Blocked on you: {b.get('title', '')}",
            b.get("reason") or "", tid,
            len(open_downstream(rows, tid, dmap)) if tid else 0))

    agents = snap.report.data.get("agents", {})
    for c in agents.get("stranded_claims", []):
        title = by_id.get(c["id"], {}).get("title", "")
        items.append(Attention(
            "stale-claim", "medium",
            f"{c.get('claimed_by')} holds a stale claim",
            f"{title} — claimed {ago(c.get('claimed_at'))}", c["id"]))

    for s in snap.next.data.get("stale_blocks", []):
        tid = s.get("id") if isinstance(s, dict) else s
        title = by_id.get(tid, {}).get("title", "")
        target = by_id.get(tid, {}).get("blocked_on", "")
        items.append(Attention(
            "stale-block", "medium", "Blocked on a task that has closed",
            f"{title} — blocked_on {target}", tid))

    handoffs = [r for r in rows if r.get("status") == "blocked"
                and blocked_kind(r.get("blocked_on")) == "handoff"]
    if handoffs:
        items.append(Attention(
            "handoff", "low",
            f"{len(handoffs)} task(s) ready for integration",
            ", ".join(r["id"] for r in handoffs[:6])
            + (" …" if len(handoffs) > 6 else "")))

    bottlenecks = sorted(
        ((len(open_downstream(rows, r["id"], dmap)), r) for r in rows
         if r.get("status") in OPEN), key=lambda x: -x[0])
    for n, r in bottlenecks[:3]:
        if n >= 3:
            items.append(Attention(
                "bottleneck", "low", f"{n} open tasks wait on {r['id']}",
                r.get("title", ""), r["id"], n))

    for e in snap.doctor.errors:
        if e.get("severity") == "warning":
            items.append(Attention("health", "low", e.get("code", ""),
                                   e.get("message", "")))

    items.sort(key=lambda a: (SEVERITY_ORDER[a.severity], -a.waiting))
    return items


def _first_message(env) -> str:
    return next((e.get("message", "") for e in env.errors), "")


# -- overview blocks ---------------------------------------------------------

def active_by_actor(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("status") == "in_progress" and r.get("claimed_by"):
            out[r["claimed_by"]].append(r)
    for v in out.values():
        v.sort(key=lambda r: r.get("claimed_at") or "", reverse=True)
    return dict(sorted(out.items(),
                       key=lambda kv: max(r.get("claimed_at") or ""
                                          for r in kv[1]), reverse=True))


def recently_closed(rows: list[dict], limit: int = 8) -> list[dict]:
    closed = [r for r in rows if r.get("closed")]
    closed.sort(key=lambda r: r["closed"], reverse=True)
    return closed[:limit]


def blocked_groups(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("status") == "blocked":
            out[blocked_kind(r.get("blocked_on")) or "other"].append(r)
    return dict(out)


# -- filtering (Work view) ---------------------------------------------------

@dataclass
class Filters:
    text: str = ""
    statuses: tuple[str, ...] = OPEN
    priorities: tuple[str, ...] = ()
    sizes: tuple[str, ...] = ()
    tag: str = ""
    owner: str = ""
    blocked: str = ""   # human | task | external | handoff

    def matches(self, r: dict) -> bool:
        if self.statuses and r.get("status") not in self.statuses:
            return False
        if self.priorities and r.get("priority") not in self.priorities:
            return False
        if self.sizes and r.get("size") not in self.sizes:
            return False
        if self.tag and self.tag not in tags(r):
            return False
        if self.owner and r.get("claimed_by") != self.owner:
            return False
        if self.blocked and blocked_kind(r.get("blocked_on")) != self.blocked:
            return False
        if self.text:
            hay = " ".join([r.get("id", ""), r.get("title", ""),
                            r.get("tags") or "", r.get("claimed_by") or "",
                            r.get("blocked_on") or ""]).lower()
            if not all(t in hay for t in self.text.lower().split()):
                return False
        return True


def all_tags(rows: list[dict]) -> list[str]:
    return sorted({t for r in rows for t in tags(r)})


def all_owners(rows: list[dict]) -> list[str]:
    return sorted({r["claimed_by"] for r in rows if r.get("claimed_by")})
