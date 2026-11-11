"""Tests for checking rows the user scrolls to.

Only the top of the pool is verified before the window opens; these pin that
deeper rows are checked a batch at a time as they are revealed, that a solve
found that way disappears silently (it is not "accepted during this lock"),
and that a blind or crashing check stops further requests.
"""

from __future__ import annotations

from concurrent.futures import Future
from typing import TYPE_CHECKING, Any
from unittest.mock import ANY, MagicMock, call

from leetcode_guard._constants import SUGGESTION_COUNT
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._view_problems import ROW_BATCH
from leetcode_guard.tests._guard_factories import create_guard, pool_of

if TYPE_CHECKING:
    from pathlib import Path

SLUGS = tuple(f"problem-{i}" for i in range(40))


def _guard(
    tmp_path: Path, solved: frozenset[str] = frozenset()
) -> tuple[Any, list[str]]:
    """Build a guard over SLUGS whose status lookups are recorded."""
    guard, _calls = create_guard(tmp_path, seeded=True, pool=pool_of(*SLUGS))
    asked: list[str] = []

    def post(_query: str, variables: dict[str, Any]) -> GraphQLResult:
        """Record the asked slug and report it solved when listed."""
        slug = variables["titleSlug"]
        asked.append(slug)
        return GraphQLResult(
            data={"question": {"status": "ac" if slug in solved else None}}
        )

    guard.deps.post = post
    return guard, asked


def test_rows_past_the_verified_depth_are_checked_once_revealed(tmp_path: Path) -> None:
    """Revealing rows past the verified depth checks exactly the new batch."""
    guard, asked = _guard(tmp_path)

    guard.on_reveal(SUGGESTION_COUNT + ROW_BATCH)
    guard.drain_reveal()

    assert asked == list(SLUGS[SUGGESTION_COUNT : SUGGESTION_COUNT + ROW_BATCH])


def test_a_scrolled_to_solve_drops_out_without_an_accepted_note(
    tmp_path: Path,
) -> None:
    """A solve found by scrolling leaves the list without an Accepted note."""
    gone = SLUGS[SUGGESTION_COUNT + 1]
    guard, _asked = _guard(tmp_path, solved=frozenset({gone}))

    guard.on_reveal(SUGGESTION_COUNT + ROW_BATCH)
    guard.drain_reveal()

    assert gone not in {line.slug for line in guard.model.problems}
    assert "Accepted" not in guard.model.status_line


def test_rows_already_verified_are_not_asked_again(tmp_path: Path) -> None:
    """Revealing only verified rows asks nothing and starts no check."""
    guard, asked = _guard(tmp_path)

    guard.on_reveal(SUGGESTION_COUNT)

    assert asked == []
    assert guard.reveal_future is None


def test_a_signed_out_answer_stops_further_batches(tmp_path: Path) -> None:
    """A signed-out answer marks reveal blind and stops later batches."""
    guard, asked = _guard(tmp_path)
    guard.deps.post = lambda _q, _v: GraphQLResult(data=None)

    guard.on_reveal(len(SLUGS))
    guard.drain_reveal()
    guard.on_reveal(len(SLUGS))

    assert asked == []
    assert guard.reveal_blind
    assert guard.reveal_future is None


def test_a_crashing_check_stops_further_batches(tmp_path: Path) -> None:
    """A batch that raised marks reveal blind."""
    guard, _asked = _guard(tmp_path)
    failed: Future[Any] = Future()
    failed.set_exception(RuntimeError("boom"))
    guard.reveal_future = failed

    guard.drain_reveal()

    assert guard.reveal_blind


def test_an_unfinished_batch_is_drained_again_later(tmp_path: Path) -> None:
    """A batch still running books another drain."""
    guard, _asked = _guard(tmp_path)
    guard.reveal_future = Future()
    MagicMock.reset_mock(guard.root.after)

    guard.drain_reveal()

    assert guard.root.after.call_args == call(ANY, guard.drain_reveal)


def test_nothing_happens_after_close(tmp_path: Path) -> None:
    """A closed lock asks nothing on reveal or drain."""
    guard, asked = _guard(tmp_path)
    guard.run_state.closed = True

    guard.on_reveal(len(SLUGS))
    guard.reveal_future = Future()
    guard.drain_reveal()

    assert asked == []


def test_its_own_executor_is_shut_down_and_an_injected_one_is_not(
    tmp_path: Path,
) -> None:
    """Stopping shuts down only an executor the guard created itself."""
    guard, _asked = _guard(tmp_path)
    injected = guard.reveal_executor
    guard.stop_reveal()

    guard.deps.seams.executor = None
    guard.start_reveal()
    own = guard.reveal_executor
    assert own is not injected
    guard.reveal_executor = MagicMock()
    guard.stop_reveal()

    guard.reveal_executor.shutdown.assert_called_once_with(wait=False)
    own.shutdown(wait=False)
