#!/usr/bin/env python3
"""Measure nudge -> credit -> repaint on a real Tk loop, with real threads.

The browser half is ``verify_nudge_extension``. This is the lock half: a demo
guard on Xvfb whose network seam answers like LeetCode after ``--rtt`` seconds
(0.3 s is what ``curl`` measured against leetcode.com/graphql on 2026-10-03).
The fake feed gains a new accepted submission, the doorbell is rung over real
HTTP, and the clock stops when the poll handler has minted the credit and
repainted -- the moment "still need N" changes on screen.

    xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_nudge_latency

Exit 0 when every trial is under ``--budget`` seconds.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
import http.client
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
from typing import TYPE_CHECKING, Any

from leetcode_guard import _gate, _lock_poll
from leetcode_guard._auth import AuthState
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._lock_deps import GuardDeps
from leetcode_guard._nudge_server import NUDGE_PATH, NUDGE_PORT
from leetcode_guard._pool_resolve import PoolResolution
from leetcode_guard._submissions import ProbeStatus, SolveProbe
from leetcode_guard._view_update import apply_viewmodel as paint

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leetcode_guard._viewmodel import ViewModel

NOW = datetime.now(tz=UTC).astimezone()
SETTLE_SECONDS = 1.5
"""Let the startup probe land before ringing, so the bell finds an idle poller."""


class FakeFeed:
    """recentAcSubmissionList after ``rtt`` seconds; ids are added on demand."""

    def __init__(self, rtt: float) -> None:
        """Start with an empty feed."""
        self.rtt = rtt
        self.rows: list[dict[str, Any]] = []

    def post(self, _query: str, _variables: dict[str, Any]) -> GraphQLResult:
        """Answer like LeetCode, slowly."""
        time.sleep(self.rtt)
        return GraphQLResult(data={"recentAcSubmissionList": list(self.rows)})

    def accept(self, submission_id: str) -> None:
        """A new submission appears in the feed."""
        self.rows.insert(
            0,
            {
                "id": submission_id,
                "title": "Two Sum",
                "titleSlug": "two-sum",
                "timestamp": str(int(time.time())),
                "lang": "python3",
            },
        )


def _ring(port: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", NUDGE_PATH, body=b"")
    conn.getresponse().read()
    conn.close()


def trial(rtt: float, workdir: Path) -> float:
    """One nudge; returns seconds from ring to credited repaint."""
    _gate.GATE_START_DATE = date(2000, 1, 1)
    feed = FakeFeed(rtt)
    guard = LeetcodeGuard(
        demo_mode=True,
        deps=GuardDeps(
            ledger_path=workdir / "ledger.json",
            escape_path=workdir / "escape.json",
            incident_path=workdir / "incidents.json",
            post=feed.post,
            username="kuchy",
            auth=AuthState(cookies=None, note="signed out"),
            pool=PoolResolution(problems=(), source="none", notes=()),
            probe=SolveProbe(status=ProbeStatus.OK, submissions=(), reason="seed"),
            wait_turn=False,
            now=lambda: NOW,
            nudge_port=NUDGE_PORT,
        ),
    )
    # Watch the repaint itself: the first model whose balance line differs
    # from the startup one is the credit landing on screen. Patched at module
    # level so the harness needs no private attribute of the guard.
    credited: list[float] = []
    painted: list[str] = []

    def watched(views: Iterable[Any], model: ViewModel) -> int:
        count = paint(views, model)
        painted.append(model.balance_line)
        if painted[0] != model.balance_line and not credited:
            credited.append(time.monotonic())
            guard.root.after(10, guard.root.quit)
        return count

    _lock_poll.apply_viewmodel = watched
    rung: list[float] = []

    def ring_later() -> None:
        time.sleep(SETTLE_SECONDS)
        feed.accept(f"sub-{time.monotonic_ns()}")
        rung.append(time.monotonic())
        _ring(NUDGE_PORT)

    threading.Thread(target=ring_later, daemon=True).start()
    guard.root.after(int((SETTLE_SECONDS + 10) * 1000), guard.root.quit)
    try:
        guard.root.mainloop()
    finally:
        _lock_poll.apply_viewmodel = paint
        guard.on_close()
        guard.root.destroy()
    if not credited:
        return float("inf")
    return credited[0] - rung[0]


def main() -> int:
    """Run the trials and report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtt", type=float, default=0.3)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--budget", type=float, default=1.0)
    args = parser.parse_args()
    results = []
    for index in range(args.trials):
        with tempfile.TemporaryDirectory(
            dir=Path.home() / "data" / "claude-scratch"
        ) as tmp:
            seconds = trial(args.rtt, Path(tmp))
        results.append(seconds)
        _say(f"trial {index + 1}: {1000 * seconds:.0f} ms")
    overhead = statistics.median(r - args.rtt for r in results)
    _say(
        f"median {1000 * statistics.median(results):.0f} ms, max "
        f"{1000 * max(results):.0f} ms (rtt {1000 * args.rtt:.0f} ms; lock "
        f"overhead median {1000 * overhead:.0f} ms)"
    )
    return 0 if max(results) < args.budget else 1


def _say(line: str) -> None:
    """Report one line.

    ``sys.stdout`` rather than print: ruff's T201 fixer deletes prints, and
    this output is the harness's whole interface.
    """
    sys.stdout.write(line + "\n")


if __name__ == "__main__":
    sys.exit(main())
