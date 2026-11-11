"""Tests for ``solved_slugs``: which ledger entries count as a solved problem."""

from __future__ import annotations

from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, solved_slugs


def test_solved_slugs_collects_credits_and_seen_alike():
    """A `seen` entry is a solve that predates the gate, not a failure.

    It is worth zero credits on purpose, but for *suggestions* it means solved
    exactly as much as a credit does -- and on a freshly seeded ledger it is
    where nearly every known slug comes from, so dropping it would gut the
    filter.
    """
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry(
                "ac:1", "credit", "2026-08-12", "", 1, detail={"title_slug": "a"}
            ),
            LedgerEntry(
                "ac:2", "seen", "2026-08-05", "", 0, detail={"title_slug": "b"}
            ),
        ],
    )

    assert solved_slugs(ledger) == frozenset({"a", "b"})


def test_solved_slugs_ignores_entries_that_name_no_problem():
    """Charge and bootstrap entries carry no `title_slug` at all."""
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry("charge:2026-08-12", "charge", "2026-08-12", "", 1),
            LedgerEntry("bootstrap:2026-08-05", "bootstrap", "2026-08-05", "", 0),
            LedgerEntry(
                "ac:3", "credit", "2026-08-12", "", 1, detail={"title_slug": ""}
            ),
        ],
    )

    assert solved_slugs(ledger) == frozenset()


def test_solved_slugs_of_an_empty_ledger_is_empty():
    """An empty ledger has no solved slugs."""
    assert solved_slugs(Ledger()) == frozenset()


def test_solved_slugs_deduplicates_repeated_solves():
    """Re-solving mints a fresh credit under a new submission id; the
    suggestion filter cares about the problem, not the attempt count."""
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry(
                "ac:1", "credit", "2026-08-12", "", 1, detail={"title_slug": "a"}
            ),
            LedgerEntry(
                "ac:2", "credit", "2026-08-13", "", 1, detail={"title_slug": "a"}
            ),
        ],
    )

    assert solved_slugs(ledger) == frozenset({"a"})
