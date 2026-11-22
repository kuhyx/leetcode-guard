#!/usr/bin/env python3
"""One real production lock for ``verify_restart_study``: ``<role> <status-file>``.

Runs the real ``_cli.cmd_lock`` (so the restart marker is read exactly where
production reads it) with every outward effect stubbed: no network, no sync, no
nudge port, no morning-session or lockdown deferral, a scratch ledger seeded
for today. A probe reports gatelock's public ``holds_grab()`` to the status file
at start and again after a recovery tick. Roles: ``enter`` presses Open,
``back`` presses "Back to lock" after the tick, anything else only observes.
The parent ends the process with SIGTERM.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Final
from unittest.mock import patch

from leetcode_guard import _cli, _lock_study
from leetcode_guard._auth import AuthState
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_entries import bootstrap_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._settings import Client
from leetcode_guard.tests._e2e_fakes import ordinary_day, quiet_cli

SETTLE_MS: Final = 2500
"""Real time before "STAYS": 2.5 ``recovery_tick_ms`` (1 s) ticks."""
START_PROBE_MS: Final = 700
URL: Final = "https://example.invalid/problems/two-sum/"
ARGC: Final = 3  # module, role, status file


def _stubs() -> list[tuple[object, str, object]]:
    """Everything that would leave the scratch directory."""
    client = Client(
        post=lambda _q, _v: GraphQLResult(data={"recentAcSubmissionList": []}),
        auth=AuthState(cookies=None, note="Not signed in."),
        username="kuchy",
    )
    empty_pool = PoolResolution(problems=(), source="cache", notes=())
    return [
        *quiet_cli(client),
        (_cli, "wait_for_x_server", lambda **_k: None),
        (_cli, "resolve_pool", lambda *_a, **_k: empty_pool),
        (_lock_study, "find_opener", lambda: "/bin/true"),
        (
            _lock_study,
            "launch",
            lambda _url: SimpleNamespace(ok=True, reason="", command=()),
        ),
    ]


def _probed(role: str, status: Path) -> type[LeetcodeGuard]:
    """The production lock plus a probe that reports to the parent."""
    stages: list[dict[str, Any]] = []

    class Probed(LeetcodeGuard):
        """The production lock, observed."""

        def run(self) -> None:
            """Schedule the probes, then hand control to Tk as usual."""
            self.root.after(START_PROBE_MS, self._start_probe)
            super().run()

        def _record(self, stage: str, *, final: bool = False) -> None:
            stages.append(
                {
                    "stage": stage,
                    "held": bool(self.lock.recovery.holds_grab()),
                    "studying": self.session().active,
                    "strip": self.strip is not None,
                    "final": final,
                }
            )
            tmp = status.with_suffix(".tmp")
            tmp.write_text(json.dumps(stages), encoding="utf-8")
            tmp.replace(status)

        def _start_probe(self) -> None:
            self._record("start")
            if role == "enter":
                self.open_problem(URL)
                self._record("after-open")
            self.root.after(SETTLE_MS, self._settled_probe)

        def _settled_probe(self) -> None:
            self._record("settled", final=role != "back")
            if role == "back":
                self.back_to_lock()
                self._record("back", final=True)

    return Probed


def main(role: str, status: Path) -> int:
    """Seed a scratch ledger for today, then run the lock until SIGTERM."""
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
    if not _cli.LEDGER_FILE.exists():
        ledger = Ledger()
        now = datetime.now(tz=UTC).astimezone()
        append(ledger, [bootstrap_entry(day=local_today(), now=now, seeded=0)])
        save_ledger(_cli.LEDGER_FILE, ledger)
    patches = [
        *ordinary_day(),
        *_stubs(),
        (_cli, "LeetcodeGuard", _probed(role, status)),
    ]
    with ExitStack() as stack:
        for target, name, value in patches:
            stack.enter_context(patch.object(target, name, value))
        return int(_cli.cmd_lock(demo_mode=False))


if __name__ == "__main__":
    if len(sys.argv) != ARGC:
        sys.exit("usage: verify_restart_study_child <role> <status-file>")
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
