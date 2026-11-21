"""Tests for the loopback ``/beat`` listener, over real sockets on port 0.

What matters is what crosses HTTP: which requests reach the store, which are
refused and with what status, and that no CORS permission is ever granted.
"""

from __future__ import annotations

from http import HTTPStatus
import logging
import socket
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from leetcode_guard import _attempt_server, _attempt_store
from leetcode_guard._attempt_server import AttemptServer
from leetcode_guard._attempt_store import Outcome, load
from leetcode_guard.tests._attempt_server_helpers import GOOD, post, serving

if TYPE_CHECKING:
    from collections.abc import Iterator

JSON = {"Content-Type": "application/json"}


@pytest.fixture(name="port")
def fixture_port() -> Iterator[int]:
    """A started listener on a free loopback port; the pool knows two-sum."""
    with serving(["two-sum", "add-two-numbers"]) as bound:
        yield bound


def test_the_shipped_port_is_8782() -> None:
    """The extension is built against this number."""
    assert _attempt_server.PORT == 8782
    assert _attempt_server.HOST == "127.0.0.1"


def test_a_valid_beat_is_stored_and_answered_204_with_no_body(port: int) -> None:
    """The happy path, including that nothing CORS-like is ever sent."""
    response = post(port, GOOD, JSON)

    assert response.status == HTTPStatus.NO_CONTENT
    assert [
        h for h, _ in response.getheaders() if h.lower().startswith("access-")
    ] == []
    records = load()
    assert [(r.slug, r.beats[0].tab) for r in records.values()] == [
        ("two-sum", "description")
    ]


def test_a_duplicate_beat_is_still_204_and_stored_once(port: int) -> None:
    """Skipping is the store's business; the client sees success."""
    assert post(port, GOOD).status == HTTPStatus.NO_CONTENT
    assert post(port, GOOD).status == HTTPStatus.NO_CONTENT

    (record,) = load().values()
    assert len(record.beats) == 1


def test_a_store_failure_is_503(port: int) -> None:
    """Fail-open for the browser, but honest about the miss."""
    with patch.object(_attempt_store, "add_beat", return_value=Outcome.FAILED):
        assert post(port, GOOD).status == HTTPStatus.SERVICE_UNAVAILABLE


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS"])
@pytest.mark.parametrize("path", ["/beat", "/other"])
def test_other_methods_are_405_and_grant_nothing(
    port: int, method: str, path: str
) -> None:
    """GET and a preflight OPTIONS alike: no permission, no CORS headers."""
    response = post(port, b"", path=path, method=method)

    assert response.status == HTTPStatus.METHOD_NOT_ALLOWED
    assert not any(h.lower().startswith("access-") for h, _ in response.getheaders())


def test_another_path_is_404_and_stores_nothing(port: int) -> None:
    """Only ``/beat`` exists."""
    assert post(port, GOOD, path="/nudge").status == HTTPStatus.NOT_FOUND
    assert load() == {}


@pytest.mark.parametrize(
    "origin", ["chrome-extension://abcdefghijklmnop", "chrome-extension://x/y"]
)
def test_an_extension_origin_is_allowed(port: int, origin: str) -> None:
    """The extension's own origin passes."""
    assert post(port, GOOD, {"Origin": origin}).status == HTTPStatus.NO_CONTENT


@pytest.mark.parametrize(
    "origin",
    [
        "https://leetcode.com",
        "http://localhost:8771",
        "null",
        "",
        "chrome-extension:/x",
        "moz-extension://abc",
    ],
)
def test_a_web_page_origin_is_403_and_stores_nothing(port: int, origin: str) -> None:
    """A page cannot forge a heartbeat; ``null`` and empty count as pages."""
    response = post(port, GOOD, {"Origin": origin})

    assert response.status == HTTPStatus.FORBIDDEN
    assert not any(h.lower().startswith("access-") for h, _ in response.getheaders())
    assert load() == {}


def test_a_taken_port_is_survived_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fail-open: the status API must keep running without this listener."""
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        server = AttemptServer(port=squatter.getsockname()[1])

        with caplog.at_level(logging.WARNING):
            assert not server.start()

    assert server.port is None
    assert not server.up
    assert "heartbeat" in caplog.text


def test_the_default_port_is_read_from_the_module_constant() -> None:
    """``mod.PORT`` is read at construction, so tests can redirect it."""
    with patch.object(_attempt_server, "PORT", 0):
        server = AttemptServer()
        assert server.start()
        try:
            assert server.up
            assert server.port not in (None, 8782)
        finally:
            server.stop()


def test_stop_is_idempotent_and_closes_the_port() -> None:
    """A second stop is a no-op; the port is gone after the first."""
    server = AttemptServer(port=0)
    assert server.start()
    bound = server.port
    assert bound is not None

    server.stop()
    server.stop()

    assert server.port is None
    with (
        pytest.raises(ConnectionRefusedError),
        socket.create_connection(("127.0.0.1", bound), 1),
    ):
        pass


def test_request_logging_stays_out_of_stderr(
    port: int, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    """The access log goes to debug, like the nudge bell."""
    with caplog.at_level(logging.DEBUG):
        post(port, GOOD)

    assert capfd.readouterr().err == ""
    assert any(
        r.levelno == logging.DEBUG and "beat" in r.getMessage() for r in caplog.records
    )
