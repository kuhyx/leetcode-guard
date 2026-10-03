"""Check solved-state live for rows the user scrolls to, a batch at a time.

The pool is resolved before the window opens and only its top
``SUGGESTION_COUNT`` are confirmed against LeetCode then; that bound exists
because one request per problem across ~4000 would trip the rate limit, which
LeetCode answers with the same null payload as an expired session. Scrolling
reveals rows past that depth, so they are checked as they appear -- one
``ROW_BATCH`` at a time, never more than one batch in flight, on an executor so
the Tk thread never waits on the network.

A confirmed solve is removed from the pool itself rather than added to the
solved set the status line acknowledges: "Accepted: X" means a solve landed
*during this lock*, and an old solve found by scrolling is not that.
"""

from __future__ import annotations

from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import replace
import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._constants import POLL_DRAIN_MS, SUGGESTION_COUNT
from leetcode_guard._live_solved import LiveSolved, check_solved
from leetcode_guard._view_problems import ROW_BATCH
from leetcode_guard._view_update import apply_viewmodel

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._submissions import SolveProbe
    from leetcode_guard._viewmodel import ViewModel

_logger: Final = logging.getLogger(__name__)


class RevealMixin:
    """Owns the reveal depth, the checked set and the one in-flight batch."""

    root: Any
    _deps: GuardDeps
    _views: dict[str, Any]
    _model: ViewModel
    _closed: bool
    _build_model: Callable[[SolveProbe], ViewModel]

    def _start_reveal(self) -> None:
        """Record what the pool resolution already verified."""
        self._checked = {
            p.title_slug for p in self._deps.pool.problems[:SUGGESTION_COUNT]
        }
        self._reveal_depth = 0
        self._reveal_blind = False
        self._reveal_future: Future[LiveSolved] | None = None
        self._reveal_slugs: list[str] = []
        self._last_probe = self._deps.probe
        self._reveal_executor: Executor = (
            self._deps.executor
            if self._deps.executor is not None
            else ThreadPoolExecutor(max_workers=1)
        )

    def _stop_reveal(self) -> None:
        """Release the executor if it is ours."""
        if self._deps.executor is None:
            self._reveal_executor.shutdown(wait=False)

    def _on_reveal(self, depth: int) -> None:
        """A surface now has ``depth`` rows; make sure they are checked."""
        self._reveal_depth = max(self._reveal_depth, depth)
        self._request_reveal_check()

    def _request_reveal_check(self) -> None:
        """Submit the next unchecked batch, if any and if nothing is in flight."""
        if self._closed or self._reveal_blind or self._reveal_future is not None:
            return
        unchecked = [
            line.slug
            for line in self._model.problems[: self._reveal_depth]
            if line.slug and line.slug not in self._checked
        ]
        slugs = unchecked[:ROW_BATCH]
        if not slugs:
            return
        post = self._deps.post
        self._reveal_slugs = slugs
        self._reveal_future = self._reveal_executor.submit(
            lambda: check_solved(post, slugs)
        )
        self.root.after(POLL_DRAIN_MS, self._drain_reveal)

    def _drain_reveal(self) -> None:
        """On the Tk thread: fold a finished batch in and ask for the next."""
        future = self._reveal_future
        if self._closed or future is None:
            return
        if not future.done():
            self.root.after(POLL_DRAIN_MS, self._drain_reveal)
            return
        self._reveal_future = None
        try:
            evidence = future.result()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.exception("the scrolled-row solved-check raised; stopping it")
            self._reveal_blind = True
            return
        self._checked.update(self._reveal_slugs)
        if not evidence.signed_in:
            # Nothing answered, so further batches would be just as blind --
            # the same rule ``verify_live`` stops on. Rows stay as ranked.
            self._reveal_blind = True
            return
        if evidence.solved:
            pool = self._deps.pool
            self._deps.pool = replace(
                pool,
                problems=tuple(
                    p for p in pool.problems if p.title_slug not in evidence.solved
                ),
            )
            self._model = self._build_model(self._last_probe)
            apply_viewmodel(self._views.values(), self._model)
        self._request_reveal_check()
