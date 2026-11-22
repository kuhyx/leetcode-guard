"""Open the lock's first action: ``python3 -m leetcode_guard.open_cli``.

The lock's first button for a surface that is not a lock. The daily-limits
popup starts this when its LeetCode row is clicked (2026-11-21: the row named
the bonus and offered no way to the work). It holds no grab and knows nothing
about locks; under a production lock that popup cannot be clicked at all.

What it opens follows the theory-first phase (stage 4), like the lock:

* THEORY(u): the tutor on u's learn route, through the same
  ``_viewmodel_phase.learn_route`` and ``_browser.launch_tutor`` the learn
  button uses (``tutor --route /learn/<subject>/<module>``, or the plan screen
  while the lessons are not made). Never ``xdg-open``: that is another browser.
* SOLVE(u) and ``none``: the first suggested problem, as before.
* A missing or failing tutor launcher is logged at warning and the first
  problem opens instead, so the row always does something.

Display-only, like the MCP's ``get_suggested_problems``: the unit and the row
come from disk through ``gather_status``, so a click never fetches, never
counts against LeetCode's rate limit, never mints and writes nothing. The
cached order is not verified live, so the first row can be a problem solved a
minute ago; the lock's own list stays the verified one.

The exit status is the whole contract, because the caller discards stdio: 0
once a browser or the tutor was started, 1 when there was nothing to open or
no launcher.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Final

from leetcode_guard import _browser
from leetcode_guard._status import gather_status
from leetcode_guard._viewmodel_phase import learn_route

if TYPE_CHECKING:
    from leetcode_guard._status_model import StatusSnapshot

_logger: Final = logging.getLogger(__name__)

EXIT_OPENED: Final = 0
EXIT_NOTHING: Final = 1


def main() -> int:
    """Open the lock's first action: the tutor in THEORY, else the first problem.

    Returns:
        ``EXIT_OPENED`` once a browser or the tutor was started, else
        ``EXIT_NOTHING`` (the reason is logged at warning level, here or by
        the launcher).
    """
    snapshot = gather_status(limit=1)
    route = learn_route(snapshot.unit.view)
    if route is not None:
        opened = _browser.launch_tutor(route)
        if opened.ok:
            return EXIT_OPENED
        _logger.warning(
            "the tutor did not open %s (%s): opening the first problem instead",
            route,
            opened.reason,
        )
    return _open_first_problem(snapshot)


def _open_first_problem(snapshot: StatusSnapshot) -> int:
    suggestions = snapshot.pool.suggestions
    if not suggestions:
        _logger.warning("no suggested problem in the cached pool: nothing to open")
        return EXIT_NOTHING
    opened = _browser.launch(suggestions[0].url)
    return EXIT_OPENED if opened.ok else EXIT_NOTHING


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    sys.exit(main())
