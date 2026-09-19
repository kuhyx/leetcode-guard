"""Run the one network call the status window makes without blocking it.

Tk is single-threaded: a widget touched from a worker thread corrupts the
interpreter, and a fetch run *on* the Tk thread freezes the window for as long
as LeetCode takes to answer -- up to the network timeout, during which Escape
does nothing. This window's whole promise is that it goes away when asked, so
the fetch runs on a daemon thread and the result is collected by a Tk timer
that polls ``is_alive`` from the main thread. No widget is ever touched off
the Tk thread, and nothing here is a callback the worker invokes.

``cancel`` exists for the close path: a root destroyed while the fetch is in
flight must not have its repaint scheduled afterwards.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
import threading
from typing import TYPE_CHECKING, Final

from leetcode_guard._status_projection import fetch_live_progress

if TYPE_CHECKING:
    import tkinter as tk

    from leetcode_guard._progress import Progress

_logger: Final = logging.getLogger(__name__)

POLL_MS: Final = 150
"""How often the Tk thread checks whether the worker has finished. Cheap: one
``is_alive`` per tick."""

FetchFn = Callable[[], "Progress | None"]


class BackgroundFetch:
    """One fetch at a time, started from and delivered to the Tk thread."""

    def __init__(
        self,
        root: tk.Misc,
        on_done: Callable[[Progress | None], None],
        *,
        fetch: FetchFn | None = None,
    ) -> None:
        """Bind to ``root`` for scheduling; ``on_done`` runs on the Tk thread.

        ``fetch`` defaults to the live one, resolved here rather than in the
        signature so the suite can rebind the module attribute.
        """
        self._root = root
        self._on_done = on_done
        self._fetch: FetchFn = fetch if fetch is not None else fetch_live_progress
        self._thread: threading.Thread | None = None
        self._result: Progress | None = None
        self._cancelled = False

    @property
    def running(self) -> bool:
        """Whether a fetch is in flight."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Begin a fetch. ``False`` (and no second thread) if one is running."""
        if self.running:
            return False
        self._cancelled = False
        self._result = None
        self._thread = threading.Thread(
            target=self._work, name="leetcode-guard-progress", daemon=True
        )
        self._thread.start()
        self._root.after(POLL_MS, self.poll)
        return True

    def cancel(self) -> None:
        """Forget the result: the window is closing."""
        self._cancelled = True

    def _work(self) -> None:
        """The worker body. Touches no widget."""
        try:
            self._result = self._fetch()
        except Exception:
            # Logged rather than raised: an exception on a daemon thread is
            # printed to stderr and lost, and the window would wait forever
            # for a result that is never coming. The poll delivers None.
            _logger.exception("the progress fetch failed")
            self._result = None

    def poll(self) -> None:
        """Deliver the result once the worker is done; otherwise check later."""
        if self._cancelled:
            return
        if self.running:
            self._root.after(POLL_MS, self.poll)
            return
        self._on_done(self._result)
