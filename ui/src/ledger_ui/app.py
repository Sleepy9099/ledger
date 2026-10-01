"""`ledger-ui`: serve the review UI, or edit the project registry.

    ledger-ui [serve] [--port N] [--native] [--no-show]
    ledger-ui add <path> [--name NAME]
    ledger-ui remove <name>
    ledger-ui list
"""
from __future__ import annotations

import argparse
import os
import sys

from .projects import Registry, config_dir, slugify


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ledger-ui",
        description="Read-only review UI for Ledger task ledgers.")
    ap.add_argument("--home", metavar="DIR",
                    help="settings directory holding projects.json "
                         "(default: %%APPDATA%%/ledger-ui or "
                         "~/.config/ledger-ui; env LEDGER_UI_HOME)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="run the UI (default)")
    for p in (ap, s):
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--native", action="store_true",
                       help="open in a desktop window (needs pywebview: "
                            "pip install 'ledger-ui[native]')")
        p.add_argument("--no-show", action="store_true",
                       help="do not open a browser tab")
    a = sub.add_parser("add", help="register a repository")
    a.add_argument("path")
    a.add_argument("--name")
    r = sub.add_parser("remove", help="unregister a project")
    r.add_argument("name")
    sub.add_parser("list", help="show registered projects")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.home:
        os.environ["LEDGER_UI_HOME"] = args.home
    if args.cmd in (None, "serve"):
        serve(args)
        return 0
    reg = Registry.load()
    if args.cmd == "add":
        try:
            p = reg.add(args.path, args.name)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        reg.save()
        print(f"added {p.name}: {p.root}")
    elif args.cmd == "remove":
        if not reg.remove(slugify(args.name)):
            print(f"error: no project named '{args.name}'", file=sys.stderr)
            return 2
        reg.save()
        print(f"removed {args.name}")
    elif args.cmd == "list":
        print(f"registry: {reg.path}")
        for p in reg.projects:
            print(f"  {p.name:<24} {p.root}")
    return 0


def serve(args) -> None:
    # keep NiceGUI's storage out of whatever directory we were started from
    os.environ.setdefault("NICEGUI_STORAGE_PATH",
                          str(config_dir() / "nicegui-storage"))
    from nicegui import app, ui

    from . import routes  # noqa: F401  (registers the pages)

    app.on_startup(lambda: print(
        f"ledger-ui on http://{args.host}:{args.port}  (read-only)"))
    ui.run(host=args.host, port=args.port, title="Ledger",
           favicon="📒", native=args.native, reload=False,
           show=not args.no_show, dark=None, show_welcome_message=False,
           window_size=(1440, 920) if args.native else None)


if __name__ in {"__main__", "__mp_main__"}:
    sys.exit(main())
