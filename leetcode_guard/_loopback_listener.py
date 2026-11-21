"""A loopback HTTP listener on a daemon thread, shared by the small servers.

The nudge bell (``_nudge_server``) and the heartbeat listener
(``_attempt_server``) both need the same lifecycle: bind without crashing the
host process, serve in the background, close idempotently. Only the handler,
the thread name, the poll interval and the log sentence differ.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import threading
from typing import Final

_logger: Final = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS: Final = 0.5
"""``serve_forever``'s own default; ``stop()`` waits up to one poll."""


class LoopbackListener:
    """Bind, serve on a daemon thread, stop; a taken port is logged, not raised."""

    def __init__(
        self,
        address: tuple[str, int],
        *,
        thread_name: str,
        failure: str,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        """Prepare, without binding.

        Args:
            address: ``(host, port)``; loopback only, ``0`` picks a free port.
            thread_name: Name of the serving thread.
            failure: Warning text for a failed bind, with ``%s:%d`` for the
                address.
            poll_seconds: ``serve_forever`` poll interval.
        """
        self._address = address
        self._thread_name = thread_name
        self._failure = failure
        self._poll_seconds = poll_seconds
        self._server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int | None:
        """The bound port, or ``None`` when not listening."""
        if self._server is None:
            return None
        return int(self._server.server_address[1])

    def start(self, handler: type[BaseHTTPRequestHandler]) -> bool:
        """Bind and serve in the background; ``False`` when the bind failed."""
        try:
            server = ThreadingHTTPServer(self._address, handler)
        except OSError:
            _logger.warning(self._failure, *self._address, exc_info=True)
            return False
        server.daemon_threads = True
        self._server = server
        threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": self._poll_seconds},
            name=self._thread_name,
            daemon=True,
        ).start()
        return True

    def stop(self) -> None:
        """Close the port. Idempotent."""
        server, self._server = self._server, None
        if server is None:
            return
        server.shutdown()
        server.server_close()
