#!/usr/bin/env python3
"""The real lock for ``verify_review_first``: ``[demo]``, under a scratch world.

Started by the parent with ``-m`` (never imported) and a scratch ``$HOME``,
``$E2E_KEY`` and ``$E2E_OBS`` (``leetcode_guard/tests/_review_e2e.py``). On the
first run it writes what a seeded, settled install has: the pool cache, a
bootstrap ledger and the tutor's signed "theory done" row for the unit, so the
lock arms on SOLVE. Then it runs ``_cli.main`` (``--production``, or the demo)
with the outside world stubbed: LeetCode, sync, push, nudge port, free/sick
days and the morning/evening deferrals. The production 30 s poll is kept: the
1 s file watch is what has to bring the swap forward. An observer appends what
the widgets show to ``$E2E_OBS`` every 50 ms, when it changes.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import TYPE_CHECKING, Final
from unittest.mock import patch

import earned_time
from gatelock import log_integrity

from leetcode_guard import (
    _attempt_line,
    _cli,
    _constants,
    _harvest_run,
    _ledger_io,
    _phone_errors_sync,
    _review_due,
    _settings,
    _snapshot_push,
    _tutor_signed,
    solved_today,
)
from leetcode_guard._auth import AuthState
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_entries import bootstrap_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard._settings import Client
from leetcode_guard._snapshot_push import PushResult
from leetcode_guard.tests._e2e_fakes import fake_leetcode, ordinary_day, quiet_cli
from leetcode_guard.tests._net_fixtures import problem_row

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)
KEY: Final = Path(os.environ["E2E_KEY"])
OBS: Final = Path(os.environ["E2E_OBS"])
ALGO: Final = "leetcode-easy-algorithms-in-typescript"
MODULE: Final = "prefix-sums"
SLUGS: Final = ("ps-one", "ps-two", "ps-three", "ps-four", "ps-five")
STEP_MS: Final = 50
reads = [0]


def _rows() -> list[dict[str, object]]:
    """The scratch pool: the unit's Easy problems plus one Medium."""
    rows = [
        problem_row(s, frontend_id=str(i), topics=["prefix-sum"])
        for i, s in enumerate(SLUGS, 1)
    ]
    return [*rows, problem_row("ps-medium", difficulty="Medium", topics=["prefix-sum"])]


def _prepare() -> None:
    """Pool cache, bootstrap ledger, "theory done" for the unit; once per world."""
    if _constants.LEDGER_FILE.exists():
        return
    problems = tuple(p for p in map(parse_problem, _rows()) if p is not None)
    stamp = datetime.now(tz=UTC).timestamp()
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=problems, fetched_at=stamp, complete=True),
    )
    now = datetime.now(tz=UTC).astimezone()
    ledger = Ledger()
    append(ledger, [bootstrap_entry(day=local_today(), now=now, seeded=0)])
    save_ledger(_constants.LEDGER_FILE, ledger)
    at = now - timedelta(minutes=180)
    row: dict[str, object] = {
        "kind": "module_state",
        "entry_id": f"state:{ALGO}:{MODULE}:180",
        "day": at.date().isoformat(),
        "detail": {
            "subject": ALGO,
            "module": MODULE,
            "done": not os.environ.get("E2E_THEORY"),
            "at": at.timestamp(),
        },
    }
    row["hmac"] = earned_time.entry_signature(row, KEY.read_bytes().strip())
    path = _tutor_signed.TUTOR_DIR / "module_state.json"
    path.write_text(json.dumps({"version": 1, "entries": [row]}), encoding="utf-8")


def _counted(real: Callable[..., object]) -> Callable[..., object]:
    """``signed_rows`` that counts reads of ``review_due.json``."""

    def counted(name: str, *args: object, **kwargs: object) -> object:
        if name == "review_due.json":
            reads[0] += 1
        return real(name, *args, **kwargs)

    return counted


def _patches() -> list[tuple[object, str, object]]:
    """Everything that would leave the scratch world, or unlock on a special day."""
    post = fake_leetcode(_rows, list)
    client = Client(post=post, auth=AuthState(cookies=None, note="e2e"), username="e2e")
    return [
        *ordinary_day(),
        *quiet_cli(client),
        (log_integrity, "DEFAULT_HMAC_KEY_FILE", KEY),
        (solved_today, "DEFAULT_HMAC_KEY_FILE", KEY),
        (_harvest_run, "build_client", lambda: client),
        (_settings, "build_client", lambda: client),
        (_ledger_io, "request_push", lambda _path: False),
        (
            _snapshot_push,
            "push_quietly",
            lambda **_k: PushResult(pushed=False, reason="e2e", size=0),
        ),
        (_phone_errors_sync, "sync_quietly", lambda: "e2e: none"),
        (_attempt_line, "attempts_line", lambda **_k: "e2e: none"),
        (_review_due, "signed_rows", _counted(_review_due.signed_rows)),
        (_cli, "LeetcodeGuard", _observed()),
    ]


def _snapshot(guard: LeetcodeGuard) -> dict[str, object]:
    """What the first surface shows: rows, the first Open, status, learn glyph."""
    views = list(guard.frames.views.values())
    rows: list[str] = []
    btn: list[int] | None = None
    learn: list[object] | None = None
    status = ""
    if views:
        view = views[0]
        rows = [
            str(lb.cget("text")) for lb in view.problems.labels if lb.winfo_ismapped()
        ]
        mapped = [b for b in view.problems.buttons if b.winfo_ismapped()]
        if mapped:
            b = mapped[0]
            btn = [b.winfo_rootx(), b.winfo_rooty(), b.winfo_width(), b.winfo_height()]
        status = str(view.status_line.cget("text"))
        if view.phase is not None and view.phase.learn.winfo_ismapped():
            w = view.phase.learn
            learn = [
                w.winfo_rootx(),
                w.winfo_rooty(),
                w.winfo_width(),
                w.winfo_height(),
                str(w.cget("text")),
            ]
    return {
        "rows": rows,
        "btn": btn,
        "learn": learn,
        "status": status,
        "grab": bool(guard.lock.recovery.holds_grab()),
        "study": bool(guard.session().active),
        "strip": guard.strip is not None,
        "reads": reads[0],
    }


def _observed() -> type[LeetcodeGuard]:
    """The production lock plus an observer that never ends it."""
    last: list[dict[str, object]] = [{}]

    class Observed(LeetcodeGuard):
        """The production lock, observed."""

        def run(self) -> None:
            """Schedule the observer, then hand control to Tk as usual."""
            self.root.after(STEP_MS, self._observe)
            super().run()

        def _observe(self) -> None:
            try:
                state = _snapshot(self)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("observer error: %r", exc)  # the parent fails on it
                state = {"error": repr(exc)}
            if state != last[0]:
                last[0] = state
                with OBS.open("a", encoding="utf-8") as sink:
                    sink.write(json.dumps({"t": time.time(), **state}) + "\n")
            self.root.after(STEP_MS, self._observe)

    return Observed


def main(argv: list[str]) -> int:
    """Prepare the world once, then run the real lock until SIGTERM."""
    if os.environ.get("DISPLAY", "") in {"", ":0"}:
        return 2
    home = os.environ["HOME"]
    for path in (
        _constants.LEDGER_FILE,
        _constants.POOL_CACHE_FILE,
        _tutor_signed.TUTOR_DIR,
    ):
        if not str(path).startswith(home):
            sys.exit(f"not scratch: {path}")
    demo = argv == ["demo"]
    with ExitStack() as stack:
        for target, name, value in _patches():
            stack.enter_context(patch.object(target, name, value))
        _prepare()
        return int(_cli.main([] if demo else ["--production"]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
