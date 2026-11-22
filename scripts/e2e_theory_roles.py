#!/usr/bin/env python3
"""The roles ``e2e_theory`` spawns, each under its scratch ``$HOME``.

``lock`` / ``harvest`` / ``status``: the real ``--production`` lock run, the
one-minute harvester and ``--status``, with the outside world faked (LeetCode
network, HMAC key, snapshot push, Firebase sync, nudge port, RTDB lines).
``pool``: a fresh scratch pool cache. ``teach`` / ``flip``: append signed
tutor rows (C1 / C2) exactly as the tutor signs them (``earned_time``).
``needed``: today's decision, one line. Run only by ``e2e_theory``, which sets
``$HOME``, ``$E2E_KEY`` and ``$E2E_ROOT`` first; never by hand.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import faulthandler
import json
import os
from pathlib import Path
import signal
import sys
from typing import TYPE_CHECKING, Any

import earned_time
from gatelock import log_integrity

import leetcode_guard
from leetcode_guard import (
    _attempt_line,
    _cli,
    _constants,
    _harvest_run,
    _ledger_io,
    _lock,
    _morning_session,
    _phone_errors_sync,
    _settings,
    _snapshot_push,
    _tutor_signed,
    solved_today,
)
from leetcode_guard._auth import AuthState
from leetcode_guard._daycost import local_today
from leetcode_guard._gate_today import decide_today
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard._settings import Client
from leetcode_guard._snapshot_push import PushResult
from leetcode_guard.tests._net_fixtures import (
    null_data_result,
    pool_result,
    problem_row,
    recent_ac_result,
    status_result,
    submission_row,
)

if TYPE_CHECKING:
    from leetcode_guard._submissions import SolveProbe

KEY = Path(os.environ["E2E_KEY"])
ALGO = "leetcode-easy-algorithms-in-typescript"
EASY = {
    "prefix-sums": ("ps-one", "ps-two", "ps-three", "ps-four", "ps-five"),
    "stack-queue": ("sq-one", "sq-two"),
}
TAGS = {"prefix-sums": "prefix-sum", "stack-queue": "stack"}
FAST_POLL_MS = 3_000
"""The production poll is 30 s; the e2e only shortens the wait, not the path."""


def _rows() -> list[dict[str, object]]:
    """The scratch pool: each unit's Easy problems, plus one Medium."""
    rows = [
        problem_row(slug, frontend_id=str(i), topics=[TAGS[unit]])
        for i, (unit, slugs) in enumerate(EASY.items(), 1)
        for slug in slugs
    ]
    return [*rows, problem_row("ps-medium", difficulty="Medium", topics=["prefix-sum"])]


def _post(query: str, variables: object) -> object:
    """LeetCode, faked: the pool, ``$E2E_AC`` as accepted, never attempted."""
    if "recentAcSubmissions" in query:
        stamp = int(datetime.now(tz=UTC).timestamp()) - 60
        ac = [s for s in os.environ.get("E2E_AC", "").split(",") if s]
        return recent_ac_result(
            [
                submission_row(f"9{i}", slug, timestamp=stamp)
                for i, slug in enumerate(ac)
            ]
        )
    if "problemsetQuestionList" in query:
        return pool_result(_rows(), total=len(_rows()))
    if "questionStatus" in query and isinstance(variables, dict):
        return status_result(str(variables.get("titleSlug")), None)
    return null_data_result()


def _no_push(**_k: object) -> PushResult:
    """The snapshot push, faked: nothing leaves the machine."""
    return PushResult(pushed=False, reason="e2e: no push", size=0)


def _fake_world() -> None:
    """Scratch key, fake network; no push, sync, nudge port or RTDB line."""
    faulthandler.register(signal.SIGUSR1)  # a stalled role says where it is
    here = Path(leetcode_guard.__file__).resolve()
    if not here.is_relative_to(Path(os.environ["E2E_ROOT"]).resolve()):
        sys.exit(f"wrong tree: {here}")
    if os.environ.get("DISPLAY", "").split(".")[0] in {":0", ""}:
        os.environ["DISPLAY"] = ":99999"
    log_integrity.DEFAULT_HMAC_KEY_FILE = KEY
    solved_today.DEFAULT_HMAC_KEY_FILE = KEY

    def client() -> Client:
        return Client(
            post=_post, auth=AuthState(cookies=None, note="e2e"), username="e2e"
        )

    _cli.build_client = _harvest_run.build_client = _settings.build_client = client
    _ledger_io.request_push = lambda _path: False
    _lock.sync_quietly = lambda *_a, **_k: None
    lock: Any = _lock  # a Final constant, shortened for the e2e only
    lock.POLL_INTERVAL_MS_PRODUCTION = FAST_POLL_MS
    # 05:00-11:00 an arming run waits 180 s for the phone's morning session.
    _morning_session.MORNING_RETRY_SECONDS = 0.0
    _cli.NUDGE_PORT = None
    _snapshot_push.push_quietly = _no_push
    _phone_errors_sync.sync_quietly = lambda: "e2e: none"
    _attempt_line.attempts_line = lambda **_k: "e2e: none"


def _spy_models() -> None:
    """Record every model the lock builds, with the phase it read."""
    out = Path(os.environ["E2E_MODEL"])
    build = LeetcodeGuard.build_model

    def spy(self: LeetcodeGuard, probe: SolveProbe) -> object:
        model = build(self, probe)
        view = self.run_state.phases.view
        out.write_text(
            json.dumps(
                {
                    "screen": asdict(model.screen),
                    "view": None if view is None else asdict(view),
                    "rows": [line.slug for line in model.problems],
                    "unlocked": model.unlocked,
                },
                default=str,
            ),
            encoding="utf-8",
        )
        return model

    guard: Any = LeetcodeGuard
    guard.build_model = spy


def _signed(row: dict[str, object]) -> dict[str, object]:
    """``row`` signed the way the tutor signs (``earned_time``)."""
    return {**row, "hmac": earned_time.entry_signature(row, KEY.read_bytes().strip())}


def _append(name: str, rows: list[dict[str, object]]) -> None:
    """Append rows to a scratch tutor file, creating it as the tutor would."""
    path = _tutor_signed.TUTOR_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if name == "module_state.json":
        doc["version"] = 1
    doc["entries"] = [*doc.get("entries", []), *rows]
    path.write_text(json.dumps(doc), encoding="utf-8")


def teach(spec: str) -> None:
    """``<subject>/<module>/<minutes>/<minutes ago>``: one C1 teaching row."""
    subject, module, minutes, ago = spec.split("/")
    ended = datetime.now().astimezone() - timedelta(minutes=int(ago))
    detail: dict[str, object] = {
        "session_id": f"e2e-{module}-{ago}",
        "block": int(minutes),
        "minutes": int(minutes),
        "active_seconds": int(minutes) * 60.0,
        "ended_at": ended.timestamp(),
        "checks_passed": 0,
        "checks_total": 0,
    }
    if module != "-":
        detail |= {"subject": subject, "module": module}
    entry = f"e2e-{module}-{ago}-m{minutes}"
    row = {"kind": "credit", "entry_id": entry, "day": ended.date().isoformat()}
    _append(
        "ledger.json",
        [_signed({**row, "created_at": ended.timestamp(), "detail": detail})],
    )


def flip(spec: str) -> None:
    """``<module>/<0|1>/<minutes ago>``: one C2 row of the algorithm subject."""
    module, done, ago = spec.split("/")
    at = (datetime.now().astimezone() - timedelta(minutes=int(ago))).timestamp()
    detail = {"subject": ALGO, "module": module, "done": done == "1", "at": at}
    row = {"kind": "module_state", "entry_id": f"state:{ALGO}:{module}:{ago}"}
    day = datetime.fromtimestamp(at).astimezone().date().isoformat()
    _append("module_state.json", [_signed({**row, "day": day, "detail": detail})])


def needed() -> int:
    """Print today's decision: ``locked=<bool> needed=<n> cost=<n> <reason>``."""
    now = datetime.now().astimezone()
    ledger = load_ledger(_constants.LEDGER_FILE, key_file=KEY)
    decision = decide_today(ledger, day=local_today(now=now), now=now, key_file=KEY)
    print(
        f"locked={decision.locked} needed={decision.needed} "
        f"cost={decision.cost} {decision.reason}"
    )
    return 0


def main(role: str, args: list[str]) -> int:
    """Dispatch one role."""
    _fake_world()
    if role == "pool":
        problems = tuple(p for p in map(parse_problem, _rows()) if p is not None)
        stamp = datetime.now(tz=UTC).timestamp()
        pool = CachedPool(problems=problems, fetched_at=stamp, complete=True)
        return 0 if write_cache(_constants.POOL_CACHE_FILE, pool) else 1
    if role in {"teach", "flip"}:
        for spec in args:
            (teach if role == "teach" else flip)(spec)
        return 0
    if role == "needed":
        return needed()
    if role == "harvest":
        return _harvest_run.main()
    _spy_models()
    return _cli.main(["--status"] if role == "status" else ["--production"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
