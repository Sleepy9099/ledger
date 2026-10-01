# ledger-ui

A read-only review UI for [Ledger](../README.md) task ledgers. It is for
the human operator: what needs your attention, what the agents are doing,
which decisions are waiting on you, how the work depends on itself, and
whether the ledger is valid. You can point it at any number of
repositories at once.

It lives in the Ledger repo but is **never vendored**: `ledger init` copies
only `.ledger/ledger.py`, and the root package stays dependency-free. This
package depends on [NiceGUI](https://nicegui.io).

## Install and run

```bash
pip install -e ui              # or: pipx install ./ui
ledger-ui add C:/path/to/repo  # a repo root or its .ledger folder
ledger-ui                      # opens http://127.0.0.1:8765
```

- `ledger-ui --native` opens a desktop window instead of a browser tab
  (`pip install -e "ui[native]"` for pywebview).
- `ledger-ui list` / `ledger-ui remove <name>` manage the project list,
  and so does the Projects page.
- The project list lives in `%APPDATA%\ledger-ui\projects.json` on Windows
  or `~/.config/ledger-ui/projects.json` elsewhere (`--home DIR` or
  `LEDGER_UI_HOME` overrides it). It holds paths and names only, never task
  state, and nothing is written inside any repository.

## Screens

- **Projects**: every registered ledger, with its health, counts and
  checkouts (the main checkout plus every `git worktree`). A worktree whose
  branch predates the ledger is listed but can't be opened.
- **Overview**: attention items first (HUMAN decisions and how many open
  tasks wait on them, tasks blocked on a human, stale claims, blocks on
  tasks that have closed, the integration queue, bottlenecks, health
  warnings). Also active work by session, what `ledger next` would hand
  out and why other tasks are ineligible, and recent closes.
- **Work**: a filterable, sortable table of tasks (status, priority, size,
  tag, owner, blocked kind, text). Click a row to open the inspector, which
  shows the task file section by section (header, Spec, Next Steps,
  Questions, Commits, Log) without leaving the page.
- **Human Inbox**: every open HUMAN question with the agent's context
  (options and a recommendation), grouped by task and sorted by how much
  work it blocks. Each has a copyable command that records your answer.
- **Dependencies**: the `depends_on` graph, laid out left to right. It
  starts with the open work plus the closed tasks it depends on directly.
  **Load more** pulls in one more closed layer at a time, **Everything**
  draws the whole corpus, and **Focus** shows one task's ancestors and
  descendants.
- **Activity**: the corpus-wide Log, newest first, grouped by day and
  filterable by actor, event and time window. Needs ledger 1.6.0+ (`ledger
  log`). Older copies get an explanation instead.
- **Validation**: `validate --coverage`, run on demand because it walks git
  history (about 20s on a large repo). Rows are grouped by code, with the
  CLI's own `fix_hint`.

Press Ctrl+K anywhere to jump to a task. Pages refresh by themselves when
the checkout's task files change.

## Design rules

- **One semantic implementation.** Every fact comes from
  `<checkout>/.ledger/ledger.py <verb> --json --session HUMAN`, run inside
  that checkout. The UI never parses or writes task Markdown, so it can't
  disagree with the copy that governs the repo. `client.py` lets through
  only read verbs (`READ_VERBS`) and refuses write flags (`--claim`,
  `--write`, `--prune`) before it starts any process.
- **Read-only (v1).** Decisions are recorded with the CLI, using the
  command the Inbox gives you. Then commit the task file like any other
  ledger change.
- **Gated on the target's version.** `doctor --json` says what each
  checkout's copy supports. The minimum is 1.5.0, and features such as
  Activity turn on per version (`client.FEATURES`).
- **Nothing is authoritative here.** Results are cached until the task
  directory or HEAD changes. Dropping the cache only costs subprocess time.

## Layout

```text
src/ledger_ui/
  client.py       read-only CLI adapter, envelopes, capability gate
  projects.py     project registry, worktree discovery
  store.py        stamp-keyed cache, concurrent reads, shared validation run
  model.py        pure view-model derivations (attention, filters, grouping)
  graphlayout.py  graph scoping and layered layout
  theme.py        colours, icons, stylesheet
  shell.py        header, navigation, live refresh, inspector, Ctrl+K
  routes.py       URL to page
  views/          one module per screen
tests/            client, registry, cache/model, layout, and a page smoke
                  test that renders every view through NiceGUI's simulated user
```

Run the tests with `python -m pytest ui/tests` after `pip install -e
"ui[dev]"`.
