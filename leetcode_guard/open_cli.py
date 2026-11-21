"""Open the first suggested problem: ``python3 -m leetcode_guard.open_cli``.

The lock's ``Open`` button for a surface that is not a lock. The daily-limits
popup starts this when its LeetCode row is clicked (2026-11-21: the row named
the bonus and offered no way to the work). It holds no grab and knows nothing
about locks; under a production lock that popup cannot be clicked at all.

Display-only, like the MCP's ``get_suggested_problems``: the row comes from
the on-disk pool cache through ``gather_status``, so a click never fetches,
never counts against LeetCode's rate limit and writes nothing. The cached
order is not verified live, so the first row can be a problem solved a minute
ago; the lock's own list stays the verified one.

The exit status is the whole contract, because the caller discards stdio: 0
once a browser was started, 1 when there was nothing to open or no launcher.
"""

from __future__ import annotations

import logging
import sys
from typing import Final

from leetcode_guard import _browser
from leetcode_guard._status import gather_status

_logger: Final = logging.getLogger(__name__)

EXIT_OPENED: Final = 0
EXIT_NOTHING: Final = 1


def main() -> int:
    """Open the first cached suggestion in the browser.

    Returns:
        ``EXIT_OPENED`` once a browser was started, else ``EXIT_NOTHING``
        (the reason is logged at warning level, here or by the launcher).
    """
    suggestions = gather_status(limit=1).pool.suggestions
    if not suggestions:
        _logger.warning("no suggested problem in the cached pool: nothing to open")
        return EXIT_NOTHING
    opened = _browser.launch(suggestions[0].url)
    return EXIT_OPENED if opened.ok else EXIT_NOTHING


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    sys.exit(main())
