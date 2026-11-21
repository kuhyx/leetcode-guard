"""Loopback listener for the browser extension's problem-tab heartbeat.

The extension POSTs ``{"slug": ..., "tab": ...}`` to ``/beat`` once a minute
while a LeetCode problem tab is visible; each beat lands in ``attempts.json``
via :mod:`leetcode_guard._attempt_store`. **Display-only**: nothing that
decides, charges or credits may read what this writes, and a forged beat buys
nothing -- which is also why there is no authentication beyond the checks below.

Hardening, because a web page can reach any loopback port:

* only ``POST /beat``; every other method is 405, every other path 404;
* a request whose ``Origin`` is present and is not ``chrome-extension://...``
  is 403, and **no CORS header is ever sent**, so a page cannot read a reply
  and a preflight is never granted;
* the body is capped at 256 bytes by ``Content-Length``, which is required;
* the slug must be in the cached problem pool (never a network call), so
  arbitrary strings cannot grow the file.

Hosted by the always-on status process (``_web_server``) on a daemon thread. A
taken port is a warning, not a crash: the status API on 8771 keeps running.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import json
import logging
import re
import time
from typing import TYPE_CHECKING, ClassVar, Final

from leetcode_guard import _attempt_store
from leetcode_guard._attempt_model import TABS
from leetcode_guard._attempt_slugs import SlugIndex
from leetcode_guard._loopback_listener import LoopbackListener

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

HOST: Final = "127.0.0.1"
PORT: Final = 8782
"""8770 screen-locker, 8771 our status API, 8772 the lock's nudge bell."""
BEAT_PATH: Final = "/beat"
MAX_BODY: Final = 256
EXTENSION_ORIGIN: Final = "chrome-extension://"
_SLUG: Final = re.compile(r"[a-z0-9-]{1,100}")
_LENGTH: Final = re.compile(r"[0-9]{1,10}")
"""ASCII digits only: ``str.isdigit`` accepts superscripts ``int`` rejects."""
_POLL_SECONDS: Final = 0.05
_REFUSED_METHODS: Final = ("GET", "HEAD", "PUT", "DELETE", "PATCH", "OPTIONS")


class _Handler(BaseHTTPRequestHandler):
    """Accept ``POST /beat``; refuse everything else without granting CORS."""

    server_version = "leetcode-guard-attempts"
    timeout = 5
    """A client that stalls mid-body must not hold a thread for ever."""
    slugs: ClassVar[SlugIndex]
    clock: ClassVar[Callable[[], float]]

    def do_POST(self) -> None:
        """Validate, then record one heartbeat."""
        self._reply(self._handle())

    def _handle(self) -> HTTPStatus:
        """The status for this request; every refusal precedes any store write."""
        refused = self._refusal()
        if isinstance(refused, HTTPStatus):
            return refused
        slug, tab = refused
        known = type(self).slugs.current()
        if known is None:
            return HTTPStatus.SERVICE_UNAVAILABLE
        if slug not in known:
            return HTTPStatus.NOT_FOUND
        outcome = _attempt_store.add_beat(slug, tab, now=type(self).clock())
        if outcome is _attempt_store.Outcome.FAILED:
            return HTTPStatus.SERVICE_UNAVAILABLE
        return HTTPStatus.NO_CONTENT

    def _refusal(self) -> HTTPStatus | tuple[str, str]:
        """The refusal for path, origin, length or body; else ``(slug, tab)``."""
        if self.path != BEAT_PATH:
            return HTTPStatus.NOT_FOUND
        origin = self.headers.get("Origin")
        if origin is not None and not origin.startswith(EXTENSION_ORIGIN):
            return HTTPStatus.FORBIDDEN
        body = self._read_body()
        if isinstance(body, HTTPStatus):
            return body
        return _parse_beat(body) or HTTPStatus.BAD_REQUEST

    def _read_body(self) -> bytes | HTTPStatus:
        """The body, or the refusal. Never reads more than :data:`MAX_BODY`."""
        header = self.headers.get("Content-Length")
        if header is None:
            return HTTPStatus.LENGTH_REQUIRED
        if _LENGTH.fullmatch(header) is None:
            return HTTPStatus.BAD_REQUEST
        length = int(header)
        if length > MAX_BODY:
            return HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        return self.rfile.read(length)

    def reply_refused(self) -> None:
        """405 for any method but POST; ``Allow`` is the only extra header."""
        self._reply(HTTPStatus.METHOD_NOT_ALLOWED)

    def _reply(self, status: HTTPStatus) -> None:
        self.send_response(status)
        if status is HTTPStatus.METHOD_NOT_ALLOWED:
            self.send_header("Allow", "POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, /, *args: object) -> None:
        """Route the access log to debug instead of stderr."""
        _logger.debug("beat %s", fmt % args)


def _parse_beat(body: bytes) -> tuple[str, str] | None:
    """``(slug, tab)`` from a request body, or ``None`` if it is not exactly that."""
    try:
        payload = json.loads(body)
    except ValueError:
        _logger.warning("heartbeat refused: the body is not valid JSON")
        return None
    if not isinstance(payload, dict):
        return None
    slug, tab = payload.get("slug"), payload.get("tab")
    if not (isinstance(slug, str) and _SLUG.fullmatch(slug) and tab in TABS):
        return None
    return slug, str(tab)


def _install_method_guards(handler: type[_Handler]) -> None:
    """Make every non-POST verb a 405 (stdlib would answer 501)."""
    for verb in _REFUSED_METHODS:
        setattr(handler, f"do_{verb}", _Handler.reply_refused)


_install_method_guards(_Handler)


class AttemptServer:
    """The ``/beat`` listener on a daemon thread."""

    def __init__(
        self,
        *,
        host: str = HOST,
        port: int | None = None,
        slugs: SlugIndex | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Prepare, without binding.

        Args:
            host: Bind address. Loopback only, never a public interface.
            port: Bind port; ``None`` reads :data:`PORT` now, ``0`` picks a free
                one (tests).
            slugs: The slug validator; defaults to the real pool cache.
            clock: The server's clock; the timestamp is never client data.
        """
        self._slugs = SlugIndex() if slugs is None else slugs
        self._clock = clock
        self._listener = LoopbackListener(
            (host, PORT if port is None else port),
            thread_name="attempt-server",
            failure="cannot listen for attempt heartbeats on %s:%d; "
            "problem-tab time will not be measured",
            # The default 0.5 s poll makes every ``stop()`` wait that long.
            poll_seconds=_POLL_SECONDS,
        )

    @property
    def up(self) -> bool:
        """Whether the port is bound."""
        return self._listener.port is not None

    @property
    def port(self) -> int | None:
        """The bound port, or ``None`` when not listening."""
        return self._listener.port

    def start(self) -> bool:
        """Bind and serve in the background.

        Returns:
            Whether it is listening. A taken port is logged at warning and
            survived: the heartbeat is display-only, the status API goes on.
        """
        handler = type(
            "AttemptHandler",
            (_Handler,),
            {"slugs": self._slugs, "clock": staticmethod(self._clock)},
        )
        return self._listener.start(handler)

    def stop(self) -> None:
        """Close the port. Idempotent."""
        self._listener.stop()
