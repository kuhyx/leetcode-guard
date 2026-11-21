"""The status process also hosts the attempt listener, and survives losing it.

Display-only, so the one rule is fail-open: a taken port 8782 must never cost
the solved-today API on 8771, which steam-backlog-enforcer reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from leetcode_guard import _attempt_server, _web_server
from leetcode_guard._attempt_server import AttemptServer
from leetcode_guard._web_server import build_health_payload, create_server, serve
from leetcode_guard.tests.test_web_server import _get

if TYPE_CHECKING:
    from collections.abc import Iterator

_PKG = "leetcode_guard._web_server"


def test_the_health_payload_reports_the_listener_additively() -> None:
    """The old keys are untouched; one boolean is added."""
    down = build_health_payload()
    up = build_health_payload(attempts_up=True)

    assert down["ok"] is True
    assert down["service"] == "leetcode-guard-web"
    assert down["attempts_listener"] is False
    assert up["attempts_listener"] is True


@pytest.fixture(name="attempts")
def fixture_attempts() -> Iterator[AttemptServer]:
    """An unstarted listener on an ephemeral port."""
    server = AttemptServer(port=0)
    yield server
    server.stop()


@pytest.mark.parametrize("started", [False, True])
def test_the_served_health_follows_the_listener(
    attempts: AttemptServer, started: bool
) -> None:
    """``/api/health`` over HTTP says whether 8782 is up."""
    if started:
        assert attempts.start()
    server = create_server("127.0.0.1", 0, attempts)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = _get(int(server.server_address[1]), "/api/health")
    finally:
        server.shutdown()
        server.server_close()

    assert status == 200
    assert json.loads(body)["attempts_listener"] is started


def test_serve_starts_the_listener_before_serving_and_stops_it_after() -> None:
    """Order matters: the extension must find the port as soon as the API is up."""
    manager = MagicMock()
    manager.attempts.start.return_value = True
    with (
        patch(f"{_PKG}.AttemptServer", return_value=manager.attempts),
        patch(f"{_PKG}.create_server", return_value=manager.server),
    ):
        serve()

    names = [call[0] for call in manager.mock_calls]
    assert names.index("attempts.start") < names.index("server.serve_forever")
    assert names.index("server.serve_forever") < names.index("attempts.stop")


def test_a_failed_bind_does_not_stop_the_status_api() -> None:
    """``start()`` returning False (port taken) leaves 8771 serving."""
    manager = MagicMock()
    manager.attempts.start.return_value = False
    with (
        patch(f"{_PKG}.AttemptServer", return_value=manager.attempts),
        patch(f"{_PKG}.create_server", return_value=manager.server),
    ):
        serve()

    assert manager.server.serve_forever.called


def test_the_listener_is_stopped_even_when_serving_crashes() -> None:
    """A crash in the API must not leak the second port."""
    manager = MagicMock()
    manager.server.serve_forever.side_effect = RuntimeError("boom")
    with (
        patch(f"{_PKG}.AttemptServer", return_value=manager.attempts),
        patch(f"{_PKG}.create_server", return_value=manager.server),
        pytest.raises(RuntimeError),
    ):
        serve()

    assert manager.attempts.stop.called


def test_the_web_module_names_the_shipped_port_through_the_listener() -> None:
    """No second copy of the number lives in the web module."""
    assert _attempt_server.PORT == 8782
    assert "8782" not in Path(_web_server.__file__).read_text(encoding="utf-8")
