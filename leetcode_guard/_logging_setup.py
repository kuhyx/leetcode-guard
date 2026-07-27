"""Logging configuration.

Everything goes to **stderr**, never stdout. The MCP server speaks JSON-RPC on
stdout, so a single stream-to-stdout handler corrupts the protocol and the
server fails in a way that looks like a hang rather than an error.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_STATE: Final[dict[str, bool]] = {"configured": False}
"""A dict rather than a module-level bool so the once-only guard can be flipped
without a ``global`` statement, which the lint profile rejects."""


def configure_logging(*, verbose: bool = False) -> None:
    """Install a stderr handler once.

    Idempotent: repeated calls (the CLI, then the lock it starts) must not
    stack handlers and print every line twice.

    Args:
        verbose: Emit DEBUG rather than the default WARNING.
    """
    if _STATE["configured"]:
        return
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if verbose else logging.WARNING,
        format=_FORMAT,
    )
    _STATE["configured"] = True


def reset_logging_for_tests() -> None:
    """Clear the once-only guard.

    Exists so a test can exercise the configuration path itself, which is
    otherwise unreachable after the first call in a process.
    """
    _STATE["configured"] = False
