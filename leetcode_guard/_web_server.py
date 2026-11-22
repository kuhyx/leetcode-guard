"""Read-only localhost HTTP server publishing "was a problem solved today".

The single consumer is ``steam-backlog-enforcer``, which adds an hour to the
daily gaming budget on a day with a solve. It reads
``~/.local/share/leetcode_guard/ledger.json`` directly as its primary source
and falls back to this endpoint, so a dead server costs gaming time rather than
silently handing it back.

Read-only by construction, exactly like the MCP server beside it: there is no
route that mints a credit, settles a day or unlocks anything. A local web page
that could mint a credit would be a hole straight through the gate.

This publishes a *fact*, never a number of hours. steam-backlog-enforcer owns
every hour value, the same split screen-locker uses for the workout flag, so
the two repos cannot disagree about what an earned day is.

The 8771 API stays GET-only. The same process also hosts the browser
extension's heartbeat listener (``_attempt_server``, its own port, display-only
data that nothing deciding may read); losing that port never affects this API.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlsplit

from leetcode_guard._attempt_server import AttemptServer
from leetcode_guard._daycost import local_today
from leetcode_guard._gate_today import gate_off
from leetcode_guard._logging_setup import configure_logging
from leetcode_guard._web_theory import build_theory_payload
from leetcode_guard.solved_today import solved_today

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
# 8000 is steam-backlog-enforcer's own web UI; 8770 is screen-locker's.
DEFAULT_PORT = 8771

_API_STATUS = "/api/status"
_API_HEALTH = "/api/health"
_API_THEORY = "/api/theory"


def build_status_payload() -> dict[str, Any]:
    """The solved-today fact, in the shape the enforcer consumes.

    Returns:
        A payload whose ``leetcode`` block mirrors screen-locker's ``gaming``
        block: the fact the budget decision turns on, and nothing else.
    """
    answer = solved_today()
    return {
        "leetcode": {
            "solved_today": answer.solved,
            "solves_today": answer.count,
            "checked": answer.checked,
            "settled_by_credit": answer.settled_by_credit,
            # Live, never ledger state: on a stood-down day one solve earns.
            "gate_off": gate_off(local_today()),
            "reason": answer.reason,
        },
    }


def build_health_payload(*, attempts_up: bool = False) -> dict[str, Any]:
    """A liveness probe that does not touch the ledger.

    Args:
        attempts_up: Whether the heartbeat listener on its own port is bound.
            Additive: the deploy probe only looks for ``"ok": true``.

    Returns:
        A minimal ok payload.
    """
    return {
        "ok": True,
        "service": "leetcode-guard-web",
        "attempts_listener": attempts_up,
    }


class _Handler(BaseHTTPRequestHandler):
    """Serves the three read-only JSON routes."""

    server_version = "leetcode-guard-web"
    attempts: ClassVar[AttemptServer | None] = None

    def log_message(self, fmt: str, /, *args: object) -> None:
        """Send request logging to the journal at debug, not to stderr.

        Args:
            fmt: printf-style format string from BaseHTTPRequestHandler.
            args: Its arguments.
        """
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        """Dispatch a GET to one of the three APIs, or 404."""
        split = urlsplit(self.path)
        if split.path == _API_STATUS:
            self._serve_json("status", build_status_payload)
        elif split.path == _API_THEORY:
            self._serve_json("theory", build_theory_payload)
        elif split.path == _API_HEALTH:
            attempts = type(self).attempts
            up = attempts is not None and attempts.up
            self._serve_json("health", lambda: build_health_payload(attempts_up=up))
        else:
            self._send(
                HTTPStatus.NOT_FOUND,
                b"not found - this server serves /api/status, /api/health "
                b"and /api/theory",
                "text/plain",
            )

    def _serve_json(self, name: str, build: Callable[[], dict[str, Any]]) -> None:
        """Build a payload and send it as JSON, or a 500 naming the failure.

        Args:
            name: Payload name, used in the error message and the log.
            build: Zero-argument callable returning the payload.
        """
        try:
            body = json.dumps(build()).encode("utf-8")
        except OSError, ValueError, TypeError:
            # Never a bare swallow: the reason has to reach the journal, or a
            # broken endpoint looks identical to one with nothing to say.
            logger.exception("Failed to build the %s payload", name)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"{name} error - see the journal for leetcode-guard-web".encode(),
                "text/plain",
            )
            return
        self._send(HTTPStatus.OK, body, "application/json")

    def _send(self, status: HTTPStatus, body: bytes, ctype: str) -> None:
        """Write a complete response.

        Args:
            status: HTTP status to send.
            body: Response body.
            ctype: Content type. Every route here serves JSON or plain text, so
                the charset is unconditional -- unlike screen-locker's server,
                which also serves a static bundle and has to decide.
        """
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    attempts: AttemptServer | None = None,
) -> ThreadingHTTPServer:
    """Create (but do not start) the threading HTTP server.

    Args:
        host: Address to bind. Must stay on loopback: the API is
            unauthenticated.
        port: Port to bind.
        attempts: The heartbeat listener, only so ``/api/health`` can say
            whether it is up.

    Returns:
        The unstarted server.

    Raises:
        ValueError: If asked to bind anywhere but loopback.
    """
    if not host.startswith("127.") and host != "localhost":
        msg = f"Refusing to bind {host}: the status API is loopback-only"
        raise ValueError(msg)
    handler = type("WebHandler", (_Handler,), {"attempts": attempts})
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Run the web server until interrupted.

    Args:
        host: Address to bind.
        port: Port to bind.
    """
    # Display-only and fail-open: a taken attempt port is a warning inside start().
    attempts = AttemptServer()
    attempts.start()
    server = create_server(host, port, attempts)
    logger.info("leetcode-guard status API listening on http://%s:%d", host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        attempts.stop()


def main() -> int:
    """Entry point for ``python3 -m leetcode_guard._web_server``.

    Returns:
        Process exit code.
    """
    configure_logging()
    try:
        serve()
    except KeyboardInterrupt:
        # Warning rather than info, and not only to satisfy the no-silent-
        # failures gate: while this is down steam-backlog-enforcer falls back
        # to reading the ledger, and if that also fails the day quietly loses
        # an hour. A stop belongs in the journal at a level people read.
        logger.warning("leetcode-guard status API stopped by interrupt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
