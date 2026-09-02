---
id: T-a6qomg
title: Speed up the test suite: run it in parallel (pytest-xdist) in CI and locally
status: todo
priority: p3
size: xs
created: 2026-09-02T03:37:49Z
tags: infra
---

## Spec

### Motivation

The suite spawns one Python subprocess per CLI call, so 161 tests take about five minutes serially (measured 2026-09-01 on Windows). Every test uses its own tmp_path repo, so the tests are independent and parallelize cleanly; the concurrency tests already spawn their own racers.

### Design

- pyproject `[project.optional-dependencies] dev = ["pytest", "pytest-xdist"]`.
- CI installs the dev extras and runs `python -m pytest -n auto`.
- README "This repository" notes `pip install -e .[dev]` / `python -m pytest -n auto`; plain `python -m pytest` keeps working without xdist.
- Verify in an isolated venv before committing (the dogfood tests read the real repo read-only, which is safe under -n).

### Not in scope

An in-process CLI driver for the tests (would need to unwind the process-lifetime lock and stdout reconfiguration) — revisit only if xdist is insufficient.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T03:37:49Z [claude-2026-09-01-b] add: created: Speed up the test suite: run it in parallel (pytest-xdist) in CI and locally [p3/xs] (tags: infra)
