"""Colours, icons and the shared stylesheet. One place to retune the look."""
from __future__ import annotations

from nicegui import ui

STATUS = {
    # status: (label, colour, icon)
    "todo": ("To do", "#64748b", "radio_button_unchecked"),
    "in_progress": ("Active", "#3b82f6", "play_circle"),
    "blocked": ("Blocked", "#f59e0b", "pause_circle"),
    "done": ("Done", "#10b981", "check_circle"),
    "dropped": ("Dropped", "#94a3b8", "cancel"),
}
PRIORITY = {"p0": "#ef4444", "p1": "#f97316", "p2": "#6366f1",
            "p3": "#94a3b8"}
HUMAN = "#a855f7"
ACCENT = "#4f46e5"

ATTENTION = {
    # kind: (icon, colour, label)
    "human": ("record_voice_over", HUMAN, "Decision"),
    "human-block": ("front_hand", HUMAN, "Blocked on you"),
    "corrupt": ("report", "#ef4444", "Corrupt"),
    "health": ("monitor_heart", "#ef4444", "Health"),
    "stale-claim": ("hourglass_bottom", "#f97316", "Stale claim"),
    "stale-block": ("link_off", "#f59e0b", "Stale block"),
    "handoff": ("move_to_inbox", "#0ea5e9", "Integration"),
    "bottleneck": ("account_tree", "#6366f1", "Bottleneck"),
}
SEVERITY_COLOUR = {"critical": "#ef4444", "high": HUMAN, "medium": "#f97316",
                   "low": "#64748b"}

VERB = {
    # Log verb: (icon, colour)
    "add": ("add_circle", "#64748b"),
    "claim": ("pan_tool_alt", "#3b82f6"),
    "release": ("logout", "#64748b"),
    "done": ("check_circle", "#10b981"),
    "drop": ("cancel", "#94a3b8"),
    "block": ("pause_circle", "#f59e0b"),
    "unblock": ("play_circle", "#10b981"),
    "note": ("sticky_note_2", "#64748b"),
    "note(dead-end)": ("dangerous", "#ef4444"),
    "question": ("help", HUMAN),
    "answer": ("question_answer", HUMAN),
    "step": ("checklist", "#0ea5e9"),
    "set": ("tune", "#64748b"),
    "link": ("commit", "#6366f1"),
    "unlink": ("link_off", "#6366f1"),
    "repair": ("build", "#f97316"),
    "takeover": ("swap_horiz", "#f97316"),
}


def verb_style(verb: str) -> tuple[str, str]:
    return VERB.get(verb) or VERB.get(verb.split("(")[0]) or \
        ("fiber_manual_record", "#94a3b8")


CSS = r"""
:root {
  --lg-bg: #f6f7fb; --lg-surface: #ffffff; --lg-surface-2: #f1f3f9;
  --lg-border: #e3e6ef; --lg-text: #0f172a; --lg-muted: #64748b;
  --lg-accent: #4f46e5; --lg-human: #a855f7;
}
body.body--dark {
  --lg-bg: #0b0e14; --lg-surface: #121722; --lg-surface-2: #182030;
  --lg-border: #232c3d; --lg-text: #e5e9f2; --lg-muted: #8b95a8;
  --lg-accent: #818cf8;
}
body, .q-page-container { background: var(--lg-bg) !important;
  color: var(--lg-text); }
body { font-family: Inter, "Segoe UI", system-ui, -apple-system, sans-serif;
  font-feature-settings: "cv11", "ss01"; -webkit-font-smoothing: antialiased; }
.nicegui-content { padding: 20px 24px 40px; gap: 16px; }

.lg-header { background: var(--lg-surface) !important; color: var(--lg-text) !important;
  border-bottom: 1px solid var(--lg-border); }
.lg-brand { font-weight: 700; letter-spacing: -0.02em; font-size: 17px; }
.lg-brand .dot { width: 10px; height: 10px; border-radius: 3px;
  background: linear-gradient(135deg, #6366f1, #a855f7); display: inline-block; }
.lg-drawer { background: var(--lg-surface) !important; }
.lg-nav-item { border-radius: 8px; margin: 1px 8px; padding: 7px 10px;
  color: var(--lg-text); text-decoration: none; display: flex; align-items: center;
  gap: 10px; font-size: 13.5px; font-weight: 500; }
.lg-nav-item:hover { background: var(--lg-surface-2); }
.lg-nav-item.active { background: color-mix(in srgb, var(--lg-accent) 14%, transparent);
  color: var(--lg-accent); }
.lg-nav-item .q-icon { font-size: 19px; opacity: .85; }
.lg-nav-count { margin-left: auto; font-size: 11px; font-weight: 700; padding: 0 7px;
  border-radius: 999px; background: var(--lg-surface-2); color: var(--lg-muted); }
.lg-nav-count.hot { background: var(--lg-human); color: white; }
.lg-section-label { font-size: 11px; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--lg-muted); padding: 14px 18px 6px; }

.lg-card { background: var(--lg-surface); border: 1px solid var(--lg-border);
  border-radius: 14px; box-shadow: 0 1px 2px rgba(15,23,42,.04); }
.lg-card-title { font-size: 13px; font-weight: 700; letter-spacing: .02em;
  color: var(--lg-muted); text-transform: uppercase; }
.lg-h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.2; }
.lg-h2 { font-size: 16px; font-weight: 650; letter-spacing: -0.01em; }
.lg-muted { color: var(--lg-muted); }
.lg-small { font-size: 12px; }
.lg-id { font-family: "Cascadia Code", "JetBrains Mono", ui-monospace, Consolas, monospace;
  font-size: 12px; color: var(--lg-muted); white-space: nowrap; }
a.lg-id:hover, .lg-link:hover { color: var(--lg-accent); cursor: pointer; }
.lg-link { cursor: pointer; }
.lg-link:hover { text-decoration: underline; }

.lg-chip { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px;
  border-radius: 999px; font-size: 11.5px; font-weight: 650; line-height: 18px;
  white-space: nowrap; color: var(--c);
  background: color-mix(in srgb, var(--c) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--c) 28%, transparent); }
.lg-chip.solid { background: var(--c); color: white; border-color: var(--c); }
.lg-tag { display: inline-block; padding: 0 7px; border-radius: 6px; font-size: 11px;
  background: var(--lg-surface-2); color: var(--lg-muted); border: 1px solid var(--lg-border);
  white-space: nowrap; }
.lg-prio { font-weight: 800; font-size: 11.5px; color: var(--c); }

.lg-kpi { padding: 16px 18px; min-width: 150px; flex: 1; position: relative; overflow: hidden; }
.lg-kpi .value { font-size: 30px; font-weight: 750; letter-spacing: -0.03em; line-height: 1.1; }
.lg-kpi .label { font-size: 12.5px; color: var(--lg-muted); font-weight: 600; }
.lg-kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: var(--c); }

.lg-row { padding: 10px 14px; border-top: 1px solid var(--lg-border); }
.lg-row:first-child { border-top: none; }
.lg-row.clickable:hover { background: var(--lg-surface-2); cursor: pointer; }
.lg-att-icon { width: 34px; height: 34px; border-radius: 10px; display: flex;
  align-items: center; justify-content: center; flex-shrink: 0;
  background: color-mix(in srgb, var(--c) 14%, transparent); color: var(--c); }

.lg-table { background: var(--lg-surface) !important; border-radius: 14px;
  border: 1px solid var(--lg-border); box-shadow: none !important; }
.lg-table thead tr th { font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--lg-muted); background: var(--lg-surface); }
.lg-table tbody tr { cursor: pointer; }
.lg-table tbody td { font-size: 13px; }
.lg-table .q-table__bottom { border-top: 1px solid var(--lg-border); }

.lg-inspector { background: var(--lg-surface) !important; border-left: 1px solid var(--lg-border); }
.lg-md { font-size: 13.5px; line-height: 1.55; }
.lg-md h1, .lg-md h2, .lg-md h3 { font-size: 14px; font-weight: 700; margin: 14px 0 4px; }
.lg-md p { margin: 0 0 8px; }
.lg-md code { font-size: 12px; padding: 1px 4px; border-radius: 4px; background: var(--lg-surface-2); }
.lg-md pre { background: var(--lg-surface-2); padding: 10px; border-radius: 8px; overflow-x: auto; }
.lg-md ul { padding-left: 20px; margin: 0 0 8px; }
.lg-md table { border-collapse: collapse; } .lg-md td, .lg-md th { border: 1px solid var(--lg-border); padding: 3px 6px; }

.lg-timeline-item { display: grid; grid-template-columns: 22px 1fr; gap: 10px; padding: 6px 0; }
.lg-timeline-dot { width: 22px; height: 22px; border-radius: 7px; display: flex;
  align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--c) 14%, transparent); color: var(--c); }
.lg-dead-end { border-left: 3px solid #ef4444; padding-left: 8px;
  background: color-mix(in srgb, #ef4444 6%, transparent); border-radius: 4px; }
.lg-banner { border-radius: 10px; padding: 10px 12px; font-size: 13px;
  background: color-mix(in srgb, var(--c) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--c) 30%, transparent); }
.lg-question { border-radius: 12px; border: 1px solid var(--lg-border); }
.lg-question.human { border-color: color-mix(in srgb, var(--lg-human) 45%, var(--lg-border)); }
.lg-context { font-size: 13px; line-height: 1.5; white-space: pre-wrap; color: var(--lg-text);
  background: var(--lg-surface-2); border-radius: 8px; padding: 8px 10px; }
.lg-code { font-family: "Cascadia Code", ui-monospace, Consolas, monospace; font-size: 12px;
  background: var(--lg-surface-2); border: 1px solid var(--lg-border); border-radius: 8px;
  padding: 8px 10px; white-space: pre-wrap; word-break: break-all; }
.lg-live { width: 8px; height: 8px; border-radius: 50%; background: #10b981;
  box-shadow: 0 0 0 3px color-mix(in srgb, #10b981 25%, transparent); }
.lg-live.busy { background: #f59e0b; box-shadow: 0 0 0 3px color-mix(in srgb, #f59e0b 25%, transparent); }
.lg-empty { padding: 28px; text-align: center; color: var(--lg-muted); font-size: 13px; }
.lg-filter .q-field__control { min-height: 36px; }
.lg-day { font-size: 12px; font-weight: 700; color: var(--lg-muted); text-transform: uppercase;
  letter-spacing: .06em; padding: 14px 0 6px; position: sticky; top: 0;
  background: var(--lg-bg); z-index: 1; }
"""


def apply() -> None:
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;'
        '500;600;700;800&display=swap" rel="stylesheet">')
    ui.add_css(CSS)
    ui.colors(primary=ACCENT, secondary="#a855f7", accent="#4f46e5",
              positive="#10b981", negative="#ef4444", warning="#f59e0b",
              info="#0ea5e9")


# -- small builders ------------------------------------------------------------

def chip(text: str, colour: str, icon: str | None = None,
         solid: bool = False):
    icon_html = (f'<i class="q-icon material-icons" style="font-size:13px">'
                 f'{icon}</i>') if icon else ""
    return ui.html(
        f'<span class="lg-chip{" solid" if solid else ""}" '
        f'style="--c:{colour}">{icon_html}{_esc(text)}</span>',
        sanitize=False)


def status_chip(status: str):
    label, colour, icon = STATUS.get(status, (status, "#94a3b8", "help"))
    return chip(label, colour, icon)


def priority_label(priority: str):
    colour = PRIORITY.get(priority, "#94a3b8")
    return ui.html(f'<span class="lg-prio" style="--c:{colour}">'
                   f'{_esc(priority.upper())}</span>', sanitize=False)


def tag_list(tags: list[str]):
    if not tags:
        return None
    return ui.html(" ".join(f'<span class="lg-tag">{_esc(t)}</span>'
                            for t in tags), sanitize=False)


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


esc = _esc
