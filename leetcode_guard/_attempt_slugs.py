"""The cached problem pool's slugs, for validating a heartbeat.

Read-only and offline: the pool cache is what the lock already offers when the
network is down. The parsed set is kept until the file's mtime changes, so a
heartbeat a minute costs one ``stat``. When the cache is missing or unreadable
the answer is ``None`` ("cannot validate"), warned once per outage, and the
caller refuses to write.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Final

from leetcode_guard import _constants
from leetcode_guard._pool_cache import read_cache

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)
_UNUSABLE: Final = (
    "pool cache %s is missing or unreadable; heartbeats cannot be validated, "
    "so none is recorded"
)


class SlugIndex:
    """Slugs of the cached pool, reloaded only when the cache file changes."""

    def __init__(self, path: Path | None = None) -> None:
        """Prepare, without reading.

        Args:
            path: The pool cache; ``None`` reads ``_constants.POOL_CACHE_FILE``
                at each call so the test redirect applies.
        """
        self._path = path
        self._lock = threading.Lock()
        self._stamp: int | None = None
        self._slugs: frozenset[str] | None = None
        self._warned = False

    def current(self) -> frozenset[str] | None:
        """The pool's slugs, or ``None`` when the cache cannot be used."""
        path = _constants.POOL_CACHE_FILE if self._path is None else self._path
        with self._lock:
            try:
                stamp = path.stat().st_mtime_ns
            except OSError:
                self._stamp = self._slugs = None
                if not self._warned:
                    self._warned = True
                    _logger.warning(_UNUSABLE, path, exc_info=True)
                return None
            if stamp != self._stamp:
                self._stamp = stamp
                pool = read_cache(path)
                self._slugs = (
                    None
                    if pool is None
                    else frozenset(problem.title_slug for problem in pool.problems)
                )
                if self._slugs is not None:
                    self._warned = False
            if self._slugs is None:
                self._warn_once(path)
            return self._slugs

    def _warn_once(self, path: Path) -> None:
        if not self._warned:
            self._warned = True
            _logger.warning(_UNUSABLE, path)
