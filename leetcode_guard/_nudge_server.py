"""Loopback doorbell: "the browser just showed an Accepted verdict".

The lock polls LeetCode every 30 seconds, so a solve used to take anything up
to half a minute to register. The browser extension in ``extension/`` sees the
verdict the moment LeetCode's own page does and rings this bell.

**A ring is never evidence.** It carries no body worth reading -- the handler
does not even parse one -- and its only effect is to make the lock ask LeetCode
*now* instead of later. Credits still come from the recent-AC feed alone, so a
forged ring costs a few extra requests and buys nothing. That is also why it
needs no authentication: anything that could reach the port could already run
the same probe itself.

Lives in the lock process, not in ``_web_server``: that one is documented as
read-only and runs at all times, while this port should be closed whenever no
lock is up, so the extension's request fails silently on an unlocked machine.
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import logging
from typing import TYPE_CHECKING, ClassVar, Final

from leetcode_guard._loopback_listener import LoopbackListener

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

NUDGE_HOST: Final = "127.0.0.1"
NUDGE_PORT: Final = 8772
"""8000 is steam-backlog-enforcer, 8770 screen-locker, 8771 our status API."""

NUDGE_PATH: Final = "/nudge"


class _Handler(BaseHTTPRequestHandler):
    """Accept ``POST /nudge``; answer everything else 404."""

    on_nudge: ClassVar[Callable[[], None]]

    def do_POST(self) -> None:
        """Ring the bell. The body is deliberately ignored."""
        if self.path != NUDGE_PATH:
            self._reply(HTTPStatus.NOT_FOUND)
            return
        type(self).on_nudge()
        self._reply(HTTPStatus.NO_CONTENT)

    def do_OPTIONS(self) -> None:
        """CORS and Private Network Access preflight, for a page-side caller."""
        self._reply(HTTPStatus.NO_CONTENT)

    def _reply(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt: str, /, *args: object) -> None:
        """Route the access log to debug instead of stderr."""
        _logger.debug("nudge %s", fmt % args)


class NudgeServer:
    """A loopback listener running on a daemon thread."""

    def __init__(
        self,
        on_nudge: Callable[[], None],
        *,
        host: str = NUDGE_HOST,
        port: int = NUDGE_PORT,
    ) -> None:
        """Prepare, without binding.

        Args:
            on_nudge: Called on the *server* thread. It must be thread-safe and
                must never touch Tk -- in practice it sets an Event.
            host: Bind address. Loopback only, never a public interface.
            port: Bind port; ``0`` picks a free one (tests).
        """
        self._on_nudge = on_nudge
        self._listener = LoopbackListener(
            (host, port),
            thread_name="nudge-server",
            failure="cannot listen for browser nudges on %s:%d; solves will be "
            "noticed by the regular poll only",
        )

    @property
    def port(self) -> int | None:
        """The bound port, or ``None`` when not listening."""
        return self._listener.port

    def start(self) -> bool:
        """Bind and serve in the background.

        Returns:
            Whether it is listening. A taken port is logged and survived: the
            30-second poll still notices every solve, just later.
        """
        handler = type("NudgeHandler", (_Handler,), {"on_nudge": self._on_nudge})
        return self._listener.start(handler)

    def stop(self) -> None:
        """Close the port. Idempotent."""
        self._listener.stop()
