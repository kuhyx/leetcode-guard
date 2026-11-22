"""Fakes shared by the real-lock harnesses in ``scripts/`` (child processes).

``scripts/`` is not a package, so one script cannot import another without
breaking mypy in CI (CLAUDE.md); what several harnesses need lives here.
Each patch list is ``(target, attribute, value)`` for ``patch.object``.
"""

from __future__ import annotations

from datetime import date
import sys
from typing import TYPE_CHECKING, Any

import freedays
import sickdays

from leetcode_guard import _cli, _focus
from leetcode_guard import _lock as lock_module
from leetcode_guard.tests._net_fixtures import (
    null_data_result,
    pool_result,
    recent_ac_result,
    status_result,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._leetcode import GraphQLResult
    from leetcode_guard._settings import Client

Patch = tuple[object, str, object]
Rows = list[dict[str, Any]]


def fake_leetcode(
    pool: Callable[[], Rows], accepted: Callable[[], Rows]
) -> Callable[[str, object], GraphQLResult]:
    """LeetCode, faked: ``pool`` rows, ``accepted`` submissions, never attempted."""

    def post(query: str, variables: object) -> GraphQLResult:
        if "recentAcSubmissions" in query:
            return recent_ac_result(accepted())
        if "problemsetQuestionList" in query:
            rows = pool()
            return pool_result(rows, total=len(rows))
        if "questionStatus" in query and isinstance(variables, dict):
            return status_result(str(variables.get("titleSlug")), None)
        return null_data_result()

    return post


def _no(*_args: object, **_kwargs: object) -> bool:
    """Stands in for every "is today special?" probe."""
    return False


def ordinary_day() -> list[Patch]:
    """Today is an ordinary gating day (a free or sick day would unlock)."""
    patches: list[Patch] = [
        (freedays, "is_free_day", _no),
        (_focus, "stands_down", _no),
        (sickdays, "is_sick_day", _no),
        (sickdays, "stands_down", _no),
        (sickdays, "kept_lockers", lambda *_a, **_k: frozenset()),
    ]
    patches.extend(
        (module, "GATE_START_DATE", date(2000, 1, 1))
        for name, module in list(sys.modules.items())
        if name.startswith("leetcode_guard.") and hasattr(module, "GATE_START_DATE")
    )
    return patches


def quiet_cli(client: Client) -> list[Patch]:
    """``cmd_lock`` with ``client``: no deferral, progress fetch, nudge port or sync."""
    return [
        (_cli, "build_client", lambda: client),
        (_cli, "defer_for_morning_session", lambda *_a, **_k: None),
        (_cli, "defer_for_evening_lockdown", lambda _now: None),
        (_cli, "refresh_progress", lambda *_a, **_k: None),
        (_cli, "NUDGE_PORT", None),
        (lock_module, "sync_quietly", lambda *_a, **_k: None),
    ]
