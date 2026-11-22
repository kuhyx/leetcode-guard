"""The THEORY and SOLVE screens paint no words either (textgate, SPEC Lock screens).

The collector is ``test_text_free``'s. One extra allowance: the unit id is data,
like a problem title (SPEC: "unit names and titles are data"), so it may appear
on the card and the bar. Built through the real ``build_viewmodel``, so a word
the phase view model generates fails here even though no widget code names it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._view import build_guard_view
from leetcode_guard._view_phase import mark_learn_unavailable
from leetcode_guard._view_types import ViewHooks
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests._phase_fixtures import NEXT, SOLVE, THEORY, phase, unit_pool
from leetcode_guard.tests.test_text_free import painted, words_in
from leetcode_guard.tests.test_viewmodel import CHECKED_AT, OK_PROBE, SIGNED_OUT

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._phase_view import PhaseView

SCREENS = (
    THEORY,
    phase(lessons_ready=False),
    phase(cards_taught=None, cards_total=None),
    SOLVE,
    NEXT,
)
"""THEORY, THEORY with no lessons yet, THEORY unreadable, SOLVE, the next unit."""


def _model(key: Path, view: PhaseView):
    decision = decide(Ledger(), day=MONDAY, now=NOW, key_file=key)
    pool = unit_pool()
    source = ViewSource(pool, SIGNED_OUT, limit=len(pool.problems), phase=view)
    return build_viewmodel(decision, source, OK_PROBE, checked_at=CHECKED_AT)


def _allowed() -> tuple[str, ...]:
    """Unit ids and the fixture pool's titles: data, never ours to word."""
    units = {screen.unit for screen in SCREENS}
    titles = {problem.title for problem in unit_pool().problems}
    # Longest first, so a title is never half-removed by a shorter one inside it.
    return tuple(sorted(units | titles, key=len, reverse=True))


def _words(text: str) -> list[str]:
    for allowed in _allowed():
        text = text.replace(allowed, " ")
    return words_in(text)


def test_no_phase_screen_paints_a_word(tk_mock, hmac_key: Path):
    """Card, rate, counts, unit bar and the cannot-open mark carry no prose."""
    config = LockConfig()
    hooks = ViewHooks(
        on_escape=lambda: None, on_open=lambda _url: None, on_learn=lambda _r: None
    )
    models = [_model(hmac_key, screen) for screen in SCREENS]
    view = build_guard_view(
        MagicMock(), config, models[0], output_name="DP-0", hooks=hooks
    )
    for model in models:
        apply_viewmodel([view], model)
    apply_viewmodel([view], models[0])
    mark_learn_unavailable([view], config)

    texts = painted(tk_mock)
    # Not vacuous: both screens' unit labels really were painted.
    assert any(THEORY.unit in text for text in texts)
    assert any(NEXT.unit in text for text in texts)
    offenders = {text: _words(text) for text in texts if _words(text)}
    assert offenders == {}
