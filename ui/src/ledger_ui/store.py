"""Cached, concurrent reads over many checkouts.

A cached envelope is reused until the checkout's task directory changes
(file count, newest mtime, total size, config mtime) — and, for verbs that
consult git, until HEAD moves. Nothing here is authoritative: dropping the
cache only costs subprocess time.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .client import Capabilities, Envelope, LedgerClient

# verbs whose answer depends on git history as well as the task files
GIT_VERBS = frozenset({"show", "validate", "report", "log"})


def tasks_stamp(checkout: Path) -> tuple:
    ledger = Path(checkout) / ".ledger"
    count = newest = total = 0
    try:
        with os.scandir(ledger / "tasks") as it:
            for entry in it:
                if entry.name.endswith(".md"):
                    st = entry.stat()
                    count += 1
                    total += st.st_size
                    newest = max(newest, st.st_mtime_ns)
    except FileNotFoundError:
        pass
    try:
        cfg = (ledger / "config.json").stat().st_mtime_ns
    except FileNotFoundError:
        cfg = 0
    try:
        tool = (ledger / "ledger.py").stat().st_mtime_ns
    except FileNotFoundError:
        tool = 0
    return (count, newest, total, cfg, tool)


def git_head(checkout: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(checkout),
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


@dataclass
class Snapshot:
    """The bundle most screens start from: one coherent-enough read."""
    checkout: Path
    doctor: Envelope
    tasks: Envelope
    questions: Envelope
    next: Envelope
    report: Envelope
    caps: Capabilities = field(init=False)

    def __post_init__(self) -> None:
        self.caps = Capabilities.from_doctor(self.doctor)

    @property
    def task_rows(self) -> list[dict]:
        return list(self.tasks.data.get("tasks", []))

    @property
    def envelopes(self) -> list[Envelope]:
        return [self.doctor, self.tasks, self.questions, self.next,
                self.report]


class Store:
    def __init__(self, client_factory=LedgerClient):
        self._client_factory = client_factory
        self._cache: dict[tuple, tuple[tuple, Envelope]] = {}
        self._lock = threading.Lock()
        self._validating: dict[str, asyncio.Task] = {}

    # -- sync core (runs in worker threads) -------------------------------
    def _key_stamp(self, checkout: Path, verb: str) -> tuple:
        stamp = tasks_stamp(checkout)
        if verb in GIT_VERBS:
            stamp += (git_head(checkout),)
        return stamp

    def get(self, checkout: Path, verb: str, *args: str) -> Envelope:
        key = (str(checkout), verb, args)
        stamp = self._key_stamp(checkout, verb)
        with self._lock:
            hit = self._cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
        env = self._client_factory(checkout).run(verb, *args)
        with self._lock:
            self._cache[key] = (stamp, env)
        return env

    def peek(self, checkout: Path, verb: str, *args: str) -> Envelope | None:
        """A cached envelope that is still fresh, without running anything."""
        key = (str(checkout), verb, args)
        with self._lock:
            hit = self._cache.get(key)
        if hit and hit[0] == self._key_stamp(checkout, verb):
            return hit[1]
        return None

    def stale_peek(self, checkout: Path, verb: str,
                   *args: str) -> Envelope | None:
        """The last envelope even if outdated (for showing while re-running)."""
        with self._lock:
            hit = self._cache.get((str(checkout), verb, args))
        return hit[1] if hit else None

    # -- async API --------------------------------------------------------
    async def call(self, checkout: Path, verb: str, *args: str) -> Envelope:
        return await asyncio.to_thread(self.get, checkout, verb, *args)

    async def many(self, checkout: Path,
                   calls: list[tuple[str, ...]]) -> list[Envelope]:
        return list(await asyncio.gather(
            *(self.call(checkout, *c) for c in calls)))

    async def snapshot(self, checkout: Path) -> Snapshot:
        doctor, tasks, questions, nxt, report = await self.many(checkout, [
            ("doctor",), ("list",), ("questions", "--human"), ("next",),
            ("report", "--no-git")])
        return Snapshot(Path(checkout), doctor, tasks, questions, nxt, report)

    async def stamp(self, checkout: Path) -> tuple:
        return await asyncio.to_thread(tasks_stamp, checkout)

    # -- validation: slow (20s on a large repo), so explicit + shared -----
    VALIDATE_ARGS = ("--coverage",)

    def validation_running(self, checkout: Path) -> bool:
        task = self._validating.get(str(checkout))
        return task is not None and not task.done()

    async def validate(self, checkout: Path) -> Envelope:
        """Run (or join an already running) `validate --coverage`."""
        key = str(checkout)
        task = self._validating.get(key)
        if task is None or task.done():
            task = asyncio.ensure_future(
                self.call(checkout, "validate", *self.VALIDATE_ARGS))
            self._validating[key] = task
        return await asyncio.shield(task)

    def cached_validation(self, checkout: Path) -> tuple[Envelope | None,
                                                         bool]:
        """(last result, whether it is still fresh)."""
        fresh = self.peek(checkout, "validate", *self.VALIDATE_ARGS)
        if fresh is not None:
            return fresh, True
        return self.stale_peek(checkout, "validate", *self.VALIDATE_ARGS), \
            False
