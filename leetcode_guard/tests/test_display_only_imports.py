"""The tutor's unsigned files and the attempt log order rows; they never decide.

``_theory`` reads the tutor's ``log.jsonl``/``cards.json``, which anyone can
edit. The moment the gate, the balance or the harvester consulted it, editing
JSON would steer a lock or a credit -- the ``progress_cache.json`` rule again.

Since stage 4 (2026-11-22) the curriculum's ORDER and MAPPING are decider
input: the theory-first phase machine (``_phase``) walks the units in order,
so ``_curriculum`` left this list. It ships inside the package; the unsigned
tutor files did not move. ``_tutor_read`` left it too: it is only a bounded
file reader, and the signed tutor files (``_tutor_signed``) go through it.
"""

from __future__ import annotations

import pytest

from leetcode_guard.tests.test_push_trigger import PACKAGE, _closure, _imports

DISPLAY_ONLY = {
    "_theory",
    # attempts.json: heartbeats and submissions measured for display. A decider
    # that read it would turn "open the editorial" into a bypass.
    "_attempt_paths",
    "_attempt_model",
    "_attempt_store",
    "_attempt_io",
    "_attempt_server",
    # The readers built on it: the solve measurement and the flagged report.
    "_attempts",
    "_attempt_report",
    # recentSubmissionList, every status: read by the harvester's attempts line
    # (``_attempt_line``, which is NOT listed: the orchestrator imports it on
    # purpose and must not import any module below directly).
    "_attempt_queries",
    # Per-problem submission history with code (phase 2): context for a
    # coaching Claude. ``_history_sync`` is NOT listed, like ``_attempt_line``.
    "_history_queries",
    "_history_store",
    # The coach log's finished reviews: they clear a flag, so a decider that read
    # them would let an edited JSONL line steer a lock or a credit.
    "_coach_reviews",
}
DISPLAY_PRODUCERS = {
    # The lock's unit view (SPEC C5): it reads the tutor's cards.json and
    # log.jsonl for the cards bar. Banned from every decider like the set
    # above, but the lock windows may import it: ``cmd_lock`` hands it to the
    # window as ``GuardSeams.phase``, fenced so it never raises into the lock.
    "_unit_view",
    # Credits earned today, for the study strip's filled dots. It reads the
    # verified ledger like the balance does, but a decider that came to depend
    # on it would let a display count steer a lock or a credit.
    "_earned_today",
}
DECIDER_PREFIXES = (
    "_balance",
    "_daycost",
    "_debt",
    "_difficulty",
    "_gate",
    "_harvest",
    "_ledger",
    "_phase",
    "_theory_credit",
    "_tutor_signed",
)
WINDOW_PREFIXES = ("_lock", "_cli", "_study")
WINDOWS = sorted(
    path.stem for path in PACKAGE.glob("_*.py") if path.stem.startswith(WINDOW_PREFIXES)
)
ORCHESTRATOR = "_harvest_run"
"""Mints through ``_harvest`` and then pushes the display snapshot, so its
import closure reaches the status code on purpose. It gets the direct ban."""
DECIDERS = sorted(
    path.stem
    for path in PACKAGE.glob("_*.py")
    if path.stem.startswith(DECIDER_PREFIXES) and path.stem != ORCHESTRATOR
)


def test_the_decider_list_is_not_empty():
    """A renamed package would otherwise make the ban below vacuous."""
    assert {"_gate", "_balance", "_harvest", "_debt"} <= set(DECIDERS)
    assert {"_phase", "_phase_inputs", "_tutor_signed"} <= set(DECIDERS)


def test_the_phase_machine_reads_the_order_but_not_the_unsigned_tutor_files():
    """Order and mapping decide now; ``log.jsonl``/``cards.json`` still never do."""
    reached = _closure(("_phase_inputs",))

    assert "_curriculum" in reached
    assert "_tutor_signed" in reached
    assert "_theory" not in reached


@pytest.mark.parametrize("name", DECIDERS)
def test_nothing_that_decides_can_reach_the_display_only_modules(name: str):
    """Transitively: not even through a helper two imports away."""
    assert not _closure((name,)) & (DISPLAY_ONLY | DISPLAY_PRODUCERS)


def test_the_harvester_never_reads_them_itself():
    """Its own code may hand the snapshot off, never consult the curriculum."""
    assert not _imports(ORCHESTRATOR) & (DISPLAY_ONLY | DISPLAY_PRODUCERS)


def test_the_unit_view_is_banned_because_it_reads_the_unsigned_files():
    """Why it is on the list: its closure reaches ``_theory``."""
    assert "_theory" in _closure(tuple(DISPLAY_PRODUCERS))


def test_the_window_list_is_not_empty():
    """A renamed prefix would otherwise make the ban below vacuous."""
    assert {"_lock", "_cli", "_study"} <= set(WINDOWS)


@pytest.mark.parametrize("name", WINDOWS)
def test_the_lock_and_study_windows_never_import_them_directly(name: str):
    """They reach the order through the display path on purpose (``resolve_pool``
    hands them ``blocks``); a direct import is a second reader of editable files
    inside the window that holds the grab."""
    assert not _imports(name) & DISPLAY_ONLY


def test_the_theory_route_reads_signed_inputs_only():
    """``/api/theory`` is a display mirror of signed data: its closure must not
    reach the unsigned tutor files, and it must not use ``_status_unit``."""
    reached = _closure(("_web_theory",))

    assert {"_phase_inputs", "_tutor_signed", "_theory_credit"} <= reached
    assert not reached & (DISPLAY_ONLY | DISPLAY_PRODUCERS | {"_status_unit"})
