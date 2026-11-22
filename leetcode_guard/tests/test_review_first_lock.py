"""Review first on the lock window: the first screen, the polls, Open, credit.

The view rules are ``test_review_first.py``; here the lock reads the tutor's
signed file once per poll, fails open on "cannot check" with one warning per
run, and keeps the credit path exactly as it was.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _glyphs as g
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._guard_factories import guard_with_fresh_solves, probe_of
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests._phase_fixtures import PREFIX, SOLVE, unit_pool
from leetcode_guard.tests._review_first_fixtures import (
    ROUTE,
    SOLVE_R,
    T_MS,
    install_tutor,
    slugs_of,
    write_module_due,
)
from leetcode_guard.tests._review_first_fixtures import (
    review_guard as _guard,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="tutor", autouse=True)
def _tutor(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_tutor(monkeypatch)


def test_the_first_screen_is_review_when_a_card_is_due(tmp_path: Path, hmac_key: Path):
    """Read before the window: due at t=0 means one row at t=0."""
    write_module_due(hmac_key, [T_MS - 1, T_MS, T_MS + 60_000])

    guard = _guard(tmp_path, hmac_key)

    assert [line.url for line in guard.model.problems] == [ROUTE]
    assert guard.model.problems[0].label == f"{g.REVIEW}  2"


def test_the_row_swaps_with_the_tutors_file_on_each_poll(
    tmp_path: Path, hmac_key: Path
):
    """Reviewed (nothing due) -> SOLVE rows; a card falls due again -> REVIEW."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)
    view = next(iter(guard.frames.views.values()))
    assert len(guard.model.problems) == 1

    write_module_due(hmac_key, [T_MS + 3_600_000])
    guard.on_poll_result(probe_of("old-1"))
    assert slugs_of(guard.model) == list(PREFIX)
    assert view.phase.painted.review is None

    write_module_due(hmac_key, [T_MS + 3_600_000, T_MS - 1])
    guard.on_poll_result(probe_of("old-1"))
    assert [line.url for line in guard.model.problems] == [ROUTE]
    assert view.phase.painted.review is not None


def test_a_card_falling_due_between_ticks_swaps_without_a_new_file(
    tmp_path: Path, hmac_key: Path
):
    """T is the lock's clock on every tick, so an unchanged file turns due."""
    write_module_due(hmac_key, [T_MS + 45_000])
    guard = _guard(tmp_path, hmac_key)
    assert slugs_of(guard.model) == list(PREFIX)

    guard.deps.seams.now = lambda: NOW.replace(second=59)
    guard.on_poll_result(probe_of("old-1"))

    assert [line.url for line in guard.model.problems] == [ROUTE]


def test_cannot_check_shows_the_solve_rows_and_warns_once_per_run(
    tmp_path: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """No file: SOLVE rows, one warning over startup plus three polls."""
    with caplog.at_level(logging.WARNING):
        guard = _guard(tmp_path, hmac_key)
        for _ in range(3):
            guard.on_poll_result(probe_of("old-1"))

    assert slugs_of(guard.model) == list(PREFIX)
    mentions = [r for r in caplog.records if "review_due.json" in r.getMessage()]
    assert len(mentions) == 1
    assert "review due" in mentions[0].getMessage()


def test_nothing_due_is_silent(tmp_path: Path, hmac_key: Path, caplog):
    """A clean "nothing due" read leaves no log line behind."""
    write_module_due(hmac_key, [])

    with caplog.at_level(logging.INFO):
        guard = _guard(tmp_path, hmac_key)
        guard.on_poll_result(probe_of("old-1"))

    assert slugs_of(guard.model) == list(PREFIX)
    assert not [r for r in caplog.records if "review" in r.getMessage()]


def test_no_tutor_launcher_keeps_the_solve_rows(
    tmp_path: Path, hmac_key: Path, monkeypatch, caplog
):
    """Never a REVIEW row whose Open cannot open (the 2026-08-05 rule)."""
    monkeypatch.setattr("leetcode_guard._lock_phase.find_tutor", lambda: None)
    write_module_due(hmac_key, [T_MS - 1])

    with caplog.at_level(logging.WARNING):
        guard = _guard(tmp_path, hmac_key)
        guard.on_poll_result(probe_of("old-1"))

    assert slugs_of(guard.model) == list(PREFIX)
    assert len([r for r in caplog.records if "tutor" in r.getMessage()]) == 1


def test_the_review_open_is_the_learn_path_not_the_browser(
    tmp_path: Path, hmac_key: Path, tutor: list[str]
):
    """Study mode, the grab released, the tutor on the route, strip up."""
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)

    guard.open_problem(guard.model.problems[0].url)

    guard.lock.root.grab_release.assert_called_once()
    assert tutor == [ROUTE]
    assert guard.session().active
    assert guard.strip is not None


def test_a_solve_credited_while_review_shows_clears_the_lock_as_ever(
    tmp_path: Path, hmac_key: Path
):
    """The rule is a view rule: the credit, the charge and the unlock are today's."""
    write_module_due(hmac_key, [T_MS - 1])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    reviewed = guard_with_fresh_solves(
        tmp_path / "a",
        hmac_key,
        pool=unit_pool(),
        phase=lambda: SOLVE_R,
        demo_mode=False,
    )
    control = guard_with_fresh_solves(
        tmp_path / "b", hmac_key, pool=unit_pool(), phase=lambda: SOLVE, demo_mode=False
    )
    assert [line.url for line in reviewed.model.problems] == [ROUTE]

    reviewed.on_poll_result(reviewed.check())
    control.on_poll_result(control.check())

    after = load_ledger(tmp_path / "a" / "ledger.json", key_file=hmac_key)
    ref = load_ledger(tmp_path / "b" / "ledger.json", key_file=hmac_key)
    assert after.entries["ac:brand-new"].kind == "credit"
    assert sorted(after.entries) == sorted(ref.entries)
    assert not reviewed.decision().locked
    assert reviewed.decision().state == control.decision().state


def test_leaving_review_verifies_the_solve_rows_it_brings_back(
    tmp_path: Path, hmac_key: Path, monkeypatch
):
    """Rows hidden since t=0 were never checked against LeetCode: ask now."""
    asked: list[int] = []
    write_module_due(hmac_key, [T_MS - 1])
    guard = _guard(tmp_path, hmac_key)
    monkeypatch.setattr(guard, "on_reveal", asked.append)

    write_module_due(hmac_key, [])
    guard.on_poll_result(probe_of("old-1"))

    assert asked == [len(PREFIX)]


def test_review_offers_open_the_hatch_and_break_glass_at_t0(
    tmp_path: Path, hmac_key: Path, tk_mock
):
    """The 2026-08-05 rule: the one row has its Open, the way out stays."""
    write_module_due(hmac_key, [T_MS - 1])

    guard = _guard(tmp_path, hmac_key)

    opens = [
        call
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == g.OPEN
    ]
    assert len(guard.model.problems) == len(opens) == 1
    assert guard.should_offer_escape()
    surface = next(iter(guard.frames.views.values()))
    assert surface.decor.escape_button is not None
    assert surface.decor.breakglass is not None
