"""The background fetch: delivered on the Tk thread, never after close."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from leetcode_guard import _status_fetch
from leetcode_guard._status_fetch import POLL_MS, BackgroundFetch
from leetcode_guard.tests.test_projection import progress


def wait_for_worker(fetch: BackgroundFetch) -> None:
    """Join the daemon thread so ``poll`` sees it finished."""
    thread = fetch._thread
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_a_finished_fetch_is_delivered_by_the_poll():
    root, done = MagicMock(), MagicMock()
    fetch = BackgroundFetch(root, done, fetch=progress)

    assert fetch.start()
    root.after.assert_called_once_with(POLL_MS, fetch.poll)
    wait_for_worker(fetch)
    fetch.poll()

    done.assert_called_once_with(progress())


def test_a_running_fetch_reschedules_the_poll_and_refuses_a_second_start():
    hold = threading.Event()
    root, done = MagicMock(), MagicMock()

    def slow() -> None:
        hold.wait(timeout=5)

    fetch = BackgroundFetch(root, done, fetch=slow)
    assert fetch.start()
    assert fetch.running
    assert not fetch.start()

    fetch.poll()

    assert root.after.call_count == 2
    done.assert_not_called()
    hold.set()
    wait_for_worker(fetch)


def test_a_cancelled_fetch_delivers_nothing():
    root, done = MagicMock(), MagicMock()
    fetch = BackgroundFetch(root, done, fetch=progress)
    fetch.start()
    wait_for_worker(fetch)

    fetch.cancel()
    fetch.poll()

    done.assert_not_called()
    root.after.assert_called_once()


def test_a_worker_exception_is_logged_and_delivered_as_none(caplog):
    def explode() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    root, done = MagicMock(), MagicMock()
    fetch = BackgroundFetch(root, done, fetch=explode)
    with caplog.at_level("ERROR"):
        fetch.start()
        wait_for_worker(fetch)
        fetch.poll()

    done.assert_called_once_with(None)
    assert "the progress fetch failed" in caplog.text


def test_the_default_fetch_is_the_live_one_resolved_at_construction(monkeypatch):
    live = MagicMock(return_value=None)
    monkeypatch.setattr(_status_fetch, "fetch_live_progress", live)
    fetch = BackgroundFetch(MagicMock(), MagicMock())

    fetch.start()
    wait_for_worker(fetch)

    live.assert_called_once_with()
