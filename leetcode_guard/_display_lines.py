"""The harvester's display-only lines, each fenced so it cannot stop a harvest.

Split out of ``_harvest_run`` (at the line cap). Every import is inside its
function on purpose: the harvest mints credits, these only display, and a
breakage in one of them -- a crdt_sync bump, a bug in a display module -- must
cost that line, never the process start (``test_harvest_isolation.py``).
Each ``except`` logs the exception TYPE only: an RTDB or LeetCode failure's
message can carry a request URL with a token in it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


def push_line() -> str:
    """Push the status snapshot; nothing it does can stop a harvest.

    Imported here, not at the top: the harvest mints credits, the snapshot is
    display-only, and a snapshot-only breakage -- a crdt_sync bump dropping a
    name only the push uses, a bug in a snapshot module -- must cost the push,
    never the process start (``test_harvest_isolation.py``).
    """
    try:
        from leetcode_guard._snapshot_push import (  # pylint: disable=import-outside-toplevel
            push_quietly,
        )

        return push_quietly().reason
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning("snapshot push unavailable: %s", exc, exc_info=True)
        return f"push unavailable: {exc}"


def phone_errors_line() -> str:
    """Notify about the status app's reported errors; isolated like the push.

    Display only, and the phone can write the node: whatever it holds or
    however this fails, the harvest above has already run.
    """
    try:
        from leetcode_guard._phone_errors_sync import (  # pylint: disable=import-outside-toplevel
            sync_quietly,
        )

        return sync_quietly()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # The type only, and no traceback: an RTDB failure's message can
        # carry the request URL, ``?auth=<token>`` and all.
        _logger.warning("phone errors unavailable: %s", type(exc).__name__)
        return f"unavailable ({type(exc).__name__})"


def attempts_line(key_file: Path | None) -> str:
    """Record theory snapshots and failed submissions; isolated like the push.

    Display only: it writes ``attempts.json`` and nothing else, and the harvest
    above has already run, so whatever it does wrong costs only this line.
    """
    try:
        from leetcode_guard._attempt_line import (  # pylint: disable=import-outside-toplevel
            attempts_line as line,
        )

        return line(key_file=key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # The type only, like the phone errors: a request URL can ride in a message.
        _logger.warning("attempts line unavailable: %s", type(exc).__name__)
        return f"unavailable ({type(exc).__name__})"


def history_line(key_file: Path | None) -> str:
    """Mirror one problem's submissions with code; isolated like the push.

    Display only: it writes ``history/<slug>.json`` and nothing else.
    """
    try:
        from leetcode_guard._history_sync import (  # pylint: disable=import-outside-toplevel
            history_line as line,
        )

        return line(key_file=key_file)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning("history line unavailable: %s", type(exc).__name__)
        return f"unavailable ({type(exc).__name__})"
