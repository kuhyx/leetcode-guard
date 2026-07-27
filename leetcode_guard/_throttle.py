"""Minimum-interval limiter for the LeetCode endpoint.

LeetCode publishes no ``x-ratelimit-*`` or ``retry-after`` headers, so there is
no signal before a block -- pacing has to be defensive rather than reactive.
This enforces a floor on the gap between consecutive requests.

``now``/``sleep`` are injected so tests can assert the arithmetic without
spending wall-clock time.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable


class Throttle:
    """Block until at least ``min_interval`` has passed since the last call."""

    def __init__(
        self,
        min_interval: float,
        *,
        now: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Create a limiter.

        Args:
            min_interval: Minimum seconds between successive ``wait`` returns.
            now: Monotonic clock. Defaults to :func:`time.monotonic` -- not
                :func:`time.time`, so an NTP step cannot make the limiter
                wait for hours or stop limiting altogether.
            sleep: Blocking sleep. Defaults to :func:`time.sleep`.
        """
        self._min_interval: Final = min_interval
        self._now: Final = now if now is not None else time.monotonic
        self._sleep: Final = sleep if sleep is not None else time.sleep
        self._last: float | None = None

    def wait(self) -> float:
        """Sleep as long as needed, then record this call.

        Returns:
            The number of seconds actually slept. Zero on the first call and
            whenever enough time has already passed.
        """
        current = self._now()
        slept = 0.0
        if self._last is not None:
            remaining = self._min_interval - (current - self._last)
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
                current = self._now()
        self._last = current
        return slept
