"""Tests for _web_server: the read-only solved-today endpoint.

Two invariants are pinned here rather than left to review. The server must
refuse to bind anywhere but loopback, because the payload is unauthenticated;
and it must serve only the two read routes, because a route that could write
would be a hole straight through the gate.

The routes are exercised over a real loopback server rather than by calling the
handler directly -- a mocked handler cannot catch a response that is malformed
at the HTTP level.
"""

from __future__ import annotations

import http.client
import json
from threading import Thread
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from leetcode_guard import _web_server
from leetcode_guard._web_server import (
    build_health_payload,
    build_status_payload,
    create_server,
    main,
    serve,
)
from leetcode_guard.solved_today import SolvedToday

if TYPE_CHECKING:
    from collections.abc import Iterator

_PKG = "leetcode_guard._web_server"


def _get(port: int, path: str) -> tuple[int, bytes]:
    """Fetch a path from the live server.

    Uses ``http.client`` rather than ``urlopen``: it takes a host and a path
    instead of a URL, so there is no scheme for the lint profile to flag.

    Args:
        port: The port the server is listening on.
        path: The request path.

    Returns:
        The status code and the body.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


@pytest.fixture
def live_server() -> Iterator[int]:
    """A real server on an ephemeral loopback port.

    Yields:
        The port it is listening on.
    """
    server = create_server("127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class TestPayloads:
    """What the endpoint publishes."""

    def test_the_status_payload_reports_the_fact(self) -> None:
        """A fact, never a number of hours: the enforcer owns those."""
        answer = SolvedToday(checked=True, solved=True, count=2, reason="2 today")
        with patch(f"{_PKG}.solved_today", return_value=answer):
            payload = build_status_payload()
        assert payload == {
            "leetcode": {
                "solved_today": True,
                "solves_today": 2,
                "checked": True,
                "reason": "2 today",
            }
        }

    def test_cannot_check_is_published_as_such(self) -> None:
        """The consumer must be able to tell "unknown" from "no"."""
        answer = SolvedToday(checked=False, solved=False, count=0, reason="no key")
        with patch(f"{_PKG}.solved_today", return_value=answer):
            payload = build_status_payload()
        assert payload["leetcode"]["checked"] is False

    def test_the_health_payload_does_not_touch_the_ledger(self) -> None:
        """A liveness probe must not depend on the thing it reports about."""
        with patch(f"{_PKG}.solved_today", side_effect=AssertionError) as solved:
            assert build_health_payload()["ok"] is True
        assert solved.call_count == 0


class TestRoutes:
    """Serving, over a real loopback server."""

    def test_status_is_served_as_json(self, live_server: int) -> None:
        """The happy path.

        Args:
            live_server: The running server's port.
        """
        answer = SolvedToday(checked=True, solved=True, count=1, reason="1 today")
        with patch(f"{_PKG}.solved_today", return_value=answer):
            status, body = _get(live_server, "/api/status")
        assert status == 200
        assert json.loads(body)["leetcode"]["solved_today"] is True

    def test_health_is_served(self, live_server: int) -> None:
        """The probe route answers without reading anything.

        Args:
            live_server: The running server's port.
        """
        status, body = _get(live_server, "/api/health")
        assert status == 200
        assert json.loads(body)["ok"] is True

    def test_an_unknown_route_is_404(self, live_server: int) -> None:
        """There is no static bundle here and no other API.

        Args:
            live_server: The running server's port.
        """
        status, _ = _get(live_server, "/api/unlock")
        assert status == 404

    def test_a_failing_payload_is_a_500_not_a_lie(self, live_server: int) -> None:
        """A broken endpoint must not look like one with nothing to say.

        Args:
            live_server: The running server's port.
        """
        with patch(f"{_PKG}.solved_today", side_effect=OSError("boom")):
            status, _ = _get(live_server, "/api/status")
        assert status == 500

    def test_request_logging_goes_to_the_journal(self, live_server: int) -> None:
        """BaseHTTPRequestHandler writes to stderr unless this is overridden.

        Args:
            live_server: The running server's port.
        """
        with patch(f"{_PKG}.logger") as logger:
            _get(live_server, "/api/health")
        assert logger.debug.called


class TestBinding:
    """The payload is unauthenticated, so it must never leave this machine."""

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::"])
    def test_a_non_loopback_bind_is_refused(self, host: str) -> None:
        """Refuse loudly rather than quietly publishing the payload.

        Args:
            host: An address that is not loopback.
        """
        with pytest.raises(ValueError, match="loopback-only"):
            create_server(host)

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
    def test_loopback_is_allowed(self, host: str) -> None:
        """Both spellings of loopback are accepted.

        Args:
            host: An accepted loopback address.
        """
        server = create_server(host, 0)
        server.server_close()


class TestEntryPoints:
    """serve() and main(), which systemd runs."""

    def test_serve_closes_the_server_on_exit(self) -> None:
        """A crash in serve_forever must not leak the listening socket."""
        server = MagicMock()
        with patch(f"{_PKG}.create_server", return_value=server):
            serve()
        assert server.serve_forever.called
        assert server.server_close.called

    def test_main_exits_cleanly_on_interrupt(self) -> None:
        """Ctrl-C and systemd's SIGINT are an ordinary stop, not a failure."""
        with (
            patch(f"{_PKG}.configure_logging"),
            patch(f"{_PKG}.serve", side_effect=KeyboardInterrupt),
        ):
            assert main() == 0

    def test_main_runs_the_server(self) -> None:
        """The ordinary path starts serving."""
        with (
            patch(f"{_PKG}.configure_logging"),
            patch(f"{_PKG}.serve") as served,
        ):
            assert main() == 0
        assert served.called

    def test_the_module_is_runnable(self) -> None:
        """``python3 -m leetcode_guard._web_server`` is what the unit runs."""
        assert hasattr(_web_server, "main")
