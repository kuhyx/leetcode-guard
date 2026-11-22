"""The theory-first screens as data: which screen, the card, the unit list."""

from __future__ import annotations

from leetcode_guard import _glyphs as g
from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT
from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._viewmodel import build_problem_lines, build_viewmodel
from leetcode_guard._viewmodel_phase import (
    NONE_SCREEN,
    PHASE_ROWS,
    build_phase_screen,
)
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW
from leetcode_guard.tests._phase_fixtures import (
    NONE,
    PREFIX,
    SOLVE,
    STACK,
    SUBJECT,
    THEORY,
    phase,
    unit_pool,
)
from leetcode_guard.tests.test_viewmodel import CHECKED_AT, OK_PROBE, SIGNED_OUT


def _slugs(unit: str, *, blocks: bool = True) -> list[str]:
    lines, _ = build_problem_lines(unit_pool(blocks=blocks), limit=99, unit=unit)
    return [line.slug for line in lines]


def test_theory_leads_with_a_card_for_the_unit():
    """Pencil, unit name, taught / total, the 12 -> 1 price (no running minutes), a learn route."""
    screen = build_phase_screen(THEORY)

    assert screen.phase == "theory"
    assert screen.card is not None
    assert screen.card.title == f"{g.THEORY_PENDING}  prefix-sums"
    assert screen.card.counts == "3 / 12"
    assert screen.card.fraction == 3 / 12
    assert screen.card.rate == f"12{g.MINUTES} {g.RATE} 1{g.CREDIT}"
    assert screen.card.ready_mark == ""
    assert screen.card.button == g.LEARN
    assert screen.card.route == f"/learn/{SUBJECT}/prefix-sums"
    assert screen.unit_bar == ""
    assert screen.rows == PHASE_ROWS == 5


def test_lessons_not_ready_mark_the_card_and_route_to_the_plan():
    """No lessons yet: a not-ready glyph and the subject's plan screen."""
    card = build_phase_screen(phase(lessons_ready=False)).card

    assert card is not None
    assert card.ready_mark == g.NOT_READY
    assert card.button == g.PLAN
    assert card.route == f"/plan/{SUBJECT}"


def test_unreadable_tutor_files_read_unknown_never_zero():
    """``cards_*`` None means the tutor could not be read: say so, not 0 / 0."""
    card = build_phase_screen(phase(cards_taught=None, cards_total=None)).card

    assert card is not None
    assert card.counts == f"{g.UNKNOWN} / {g.UNKNOWN}"
    assert card.fraction is None


def test_an_empty_module_has_no_fraction_and_a_full_one_caps_at_one():
    """0 / 0 draws an empty bar; a count past the total never overfills it."""
    empty = build_phase_screen(phase(cards_taught=0, cards_total=0)).card
    over = build_phase_screen(phase(cards_taught=13, cards_total=12)).card

    assert empty is not None
    assert empty.fraction is None
    assert over is not None
    assert over.fraction == 1.0


def test_theory_without_a_target_offers_no_learn_route():
    """Nothing to open: the card stays, the button has no route."""
    card = build_phase_screen(phase(learn_target=None)).card

    assert card is not None
    assert card.route is None


def test_solve_is_a_slim_bar_and_offers_no_theory():
    """Check glyph, unit, solved / total; no card, so no learn button."""
    screen = build_phase_screen(SOLVE)

    assert screen.card is None
    assert screen.unit_bar == "prefix-sums  1 / 3"
    assert screen.rows == PHASE_ROWS


def test_none_and_a_missing_phase_are_todays_list():
    """Every unit finished, or no phase at all: the screen as it was."""
    assert build_phase_screen(None) == NONE_SCREEN
    none = build_phase_screen(NONE)
    assert none.card is None
    assert none.unit_bar == ""
    assert none.rows == PROBLEM_DISPLAY_LIMIT
    assert not none.unit_list


def test_a_unit_screen_lists_only_that_units_problems_in_pool_order():
    """No wall of problems: u's rows, in the order the rules side ranked."""
    assert _slugs("prefix-sums") == list(PREFIX)
    assert _slugs("stack-queue") == list(STACK)


def test_no_unit_or_no_curriculum_keeps_the_whole_list():
    """``none`` and an unranked pool fall back to every problem."""
    assert len(_slugs("")) == len(unit_pool().problems)
    assert len(_slugs("prefix-sums", blocks=False)) == len(unit_pool().problems)


def test_a_unit_with_nothing_left_falls_back_to_the_whole_list():
    """A filter that empties the list would hide every Open button (08-05)."""
    lines, _ = build_problem_lines(
        unit_pool(), limit=99, unit="prefix-sums", solved_slugs=frozenset(PREFIX)
    )

    assert [line.slug for line in lines] == [
        p.title_slug for p in unit_pool().problems if p.title_slug not in PREFIX
    ]
    assert _slugs("no-such-unit") == [p.title_slug for p in unit_pool().problems]


def test_unit_rows_carry_no_pencil_the_card_already_says_it():
    """In THEORY every row would carry the pencil; the card carries it once."""
    lines, _ = build_problem_lines(unit_pool(), limit=99, unit="prefix-sums")
    whole, _ = build_problem_lines(unit_pool(), limit=99)

    assert not any(line.mark.startswith(g.THEORY_PENDING) for line in lines)
    assert all(line.mark.startswith(g.THEORY_PENDING) for line in whole[:2])


def test_the_view_model_carries_the_screen_and_the_unit_rows():
    """``ViewSource.phase`` reaches the model: the screen plus u's rows."""
    decision = decide(Ledger(), day=MONDAY, now=NOW)
    model = build_viewmodel(
        decision,
        ViewSource(unit_pool(), SIGNED_OUT, limit=99, phase=THEORY),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )
    plain = build_viewmodel(
        decision,
        ViewSource(unit_pool(), SIGNED_OUT, limit=99),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert model.screen == build_phase_screen(THEORY)
    assert [line.slug for line in model.problems] == list(PREFIX)
    assert model.problems[0].label == "1  Range Sum"
    assert plain.screen == NONE_SCREEN
    assert len(plain.problems) == len(unit_pool().problems)
