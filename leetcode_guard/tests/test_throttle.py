"""Tests for the minimum-interval limiter."""

from __future__ import annotations

from leetcode_guard._throttle import Throttle


class FakeClock:
    """A monotonic clock that only moves when told, or when slept on."""

    def __init__(self) -> None:
        self.value = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        """Return the current fake time."""
        return self.value

    def sleep(self, seconds: float) -> None:
        """Record the sleep and advance the clock by it."""
        self.slept.append(seconds)
        self.value += seconds


def test_first_call_never_waits():
    """The first wait returns at once without sleeping."""
    clock = FakeClock()
    throttle = Throttle(0.5, now=clock.now, sleep=clock.sleep)

    assert throttle.wait() == 0.0
    assert clock.slept == []


def test_second_call_waits_the_remainder():
    """A second call sleeps only the rest of the interval."""
    clock = FakeClock()
    throttle = Throttle(0.5, now=clock.now, sleep=clock.sleep)
    throttle.wait()

    clock.value = 0.2
    slept = throttle.wait()

    assert slept == 0.3
    assert clock.slept == [0.3]


def test_no_wait_when_enough_time_already_passed():
    """A call after the interval has elapsed does not sleep."""
    clock = FakeClock()
    throttle = Throttle(0.5, now=clock.now, sleep=clock.sleep)
    throttle.wait()

    clock.value = 10.0

    assert throttle.wait() == 0.0
    assert clock.slept == []


def test_exactly_at_the_interval_does_not_wait():
    """A call exactly one interval later does not sleep."""
    clock = FakeClock()
    throttle = Throttle(0.5, now=clock.now, sleep=clock.sleep)
    throttle.wait()

    clock.value = 0.5

    assert throttle.wait() == 0.0


def test_last_call_time_is_taken_after_sleeping():
    """Otherwise every subsequent call would inherit the pre-sleep timestamp
    and the limiter would drift by one full interval."""
    clock = FakeClock()
    throttle = Throttle(1.0, now=clock.now, sleep=clock.sleep)
    throttle.wait()

    clock.value = 0.0
    throttle.wait()

    # The sleep advanced the clock to 1.0, so a call at 1.5 needs 0.5 more.
    clock.value = 1.5
    assert throttle.wait() == 0.5


def test_defaults_use_the_real_clock():
    """A zero interval on the real clock never waits."""
    throttle = Throttle(0.0)

    assert throttle.wait() == 0.0
    assert throttle.wait() == 0.0
