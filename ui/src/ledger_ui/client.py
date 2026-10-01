"""The one door into a ledger: run the target checkout's own vendored CLI.

The UI never parses or writes task Markdown. Every fact it shows comes from
`<checkout>/.ledger/ledger.py <cmd> --json`, run with that checkout as the
working directory, so the copy that governs a repo is the copy that answers
for it (DESIGN decision #27). Only read verbs are reachable from here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

OPERATOR = "HUMAN"
MIN_VERSION = (1, 5, 0)
TIMEOUT_S = 180

# The read-only surface. A verb missing here cannot be issued by the UI —
# v1 is read-only by decision, so mutation verbs are absent, not hidden.
READ_VERBS = frozenset({
    "doctor", "list", "show", "brief", "questions", "next", "report",
    "validate", "search", "log",
})
# `next` is read-only only without --claim
FORBIDDEN_FLAGS = frozenset({"--claim", "--write", "--prune"})

# Features keyed on the target copy's tool_version.
FEATURES = {
    "log": (1, 6, 0),
}


def parse_version(text: str | None) -> tuple[int, ...] | None:
    if not text:
        return None
    try:
        return tuple(int(p) for p in text.split(".")[:3])
    except ValueError:
        return None


def version_text(v: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in v)


@dataclass
class Envelope:
    """A decoded `{ok, data, errors}` reply, plus how the call went."""
    ok: bool
    data: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    exit_code: int = 0
    stderr: str = ""
    elapsed_ms: int = 0

    def by_severity(self, severity: str) -> list[dict]:
        return [e for e in self.errors
                if (e.get("severity") or "error") == severity]

    @property
    def error_rows(self) -> list[dict]:
        return self.by_severity("error")


class ReadOnlyViolation(ValueError):
    """Raised before any subprocess when a caller asks for a write."""


def ledger_script(checkout: Path) -> Path | None:
    script = Path(checkout) / ".ledger" / "ledger.py"
    return script if script.is_file() else None


class LedgerClient:
    """Runs one checkout's vendored ledger.py. Stateless and thread-safe."""

    def __init__(self, checkout: Path, python: str | None = None):
        self.checkout = Path(checkout)
        self.python = python or sys.executable

    @property
    def script(self) -> Path | None:
        return ledger_script(self.checkout)

    def run(self, verb: str, *args: str) -> Envelope:
        if verb not in READ_VERBS:
            raise ReadOnlyViolation(f"'{verb}' is not a read verb")
        bad = FORBIDDEN_FLAGS.intersection(args)
        if bad:
            raise ReadOnlyViolation(f"flag(s) {sorted(bad)} write")
        script = self.script
        if script is None:
            return Envelope(ok=False, exit_code=-1, errors=[{
                "code": "ui-no-ledger", "severity": "error", "task": None,
                "message": f"no .ledger/ledger.py in {self.checkout}",
                "fix_hint": "this checkout has no vendored ledger (a branch "
                            "that predates it?)"}])
        env = dict(os.environ)
        env.pop("LEDGER_SESSION", None)  # --session below is the identity
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.python, str(script), verb, *args, "--json",
               "--session", OPERATOR]
        import time
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd, cwd=str(self.checkout), env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return Envelope(ok=False, exit_code=-1, errors=[{
                "code": "ui-timeout", "severity": "error", "task": None,
                "message": f"`ledger {verb}` took longer than {TIMEOUT_S}s",
                "fix_hint": None}])
        elapsed = int((time.perf_counter() - t0) * 1000)
        return decode(proc.stdout, proc.returncode, proc.stderr, verb,
                      elapsed)


def decode(stdout: str, exit_code: int, stderr: str, verb: str,
           elapsed_ms: int = 0) -> Envelope:
    """Turn CLI output into an Envelope. A copy too old for a verb answers
    with argparse's exit 3 and no JSON — reported, never raised."""
    try:
        payload = json.loads(stdout)
        if not isinstance(payload, dict) or "ok" not in payload:
            raise ValueError("not an envelope")
    except ValueError:
        tail = (stderr or stdout or "").strip().splitlines()[-1:] or [""]
        return Envelope(ok=False, exit_code=exit_code, stderr=stderr,
                        elapsed_ms=elapsed_ms, errors=[{
                            "code": "ui-decode", "severity": "error",
                            "task": None,
                            "message": f"`ledger {verb}` returned no JSON "
                                       f"envelope (exit {exit_code}): "
                                       f"{tail[0]}",
                            "fix_hint": "the vendored copy may predate this "
                                        "command; `doctor` shows its version"}])
    return Envelope(ok=bool(payload.get("ok")),
                    data=payload.get("data") or {},
                    errors=list(payload.get("errors") or []),
                    exit_code=exit_code, stderr=stderr,
                    elapsed_ms=elapsed_ms)


@dataclass
class Capabilities:
    tool_version: tuple[int, ...] | None
    protocol_version: int | None
    compatible: bool

    @classmethod
    def from_doctor(cls, env: Envelope) -> "Capabilities":
        data = env.data or {}
        return cls(tool_version=parse_version(data.get("tool_version")),
                   protocol_version=data.get("protocol_version"),
                   compatible=bool(data.get("repo_compatible", env.ok)))

    @property
    def supported(self) -> bool:
        return self.tool_version is not None and \
            self.tool_version >= MIN_VERSION

    def has(self, feature: str) -> bool:
        need = FEATURES[feature]
        return self.tool_version is not None and self.tool_version >= need

    def missing_reason(self, feature: str) -> str:
        have = version_text(self.tool_version) if self.tool_version else "?"
        return (f"needs ledger {version_text(FEATURES[feature])}+ "
                f"(this checkout vendors {have})")
