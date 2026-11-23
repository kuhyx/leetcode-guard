"""``GET /api/postmortems``: the tutor's post-mortem reports, for display.

Read-only like every route on this server: it never writes a file, mints a
credit or settles a day. It mirrors :func:`_postmortem_view.read_postmortems`
(no size cap; the snapshot applies its own). ``null`` means reading raised
(logged at warning), ``[]`` means no post-mortem yet.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from leetcode_guard._postmortem_view import read_postmortems

_logger: Final = logging.getLogger(__name__)


def build_postmortems_payload() -> dict[str, Any]:
    """The ``{"postmortems": [...]}`` payload. Never raises (``Exception``)."""
    try:
        rows: list[dict[str, Any]] | None = read_postmortems()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _logger.warning(
            "post-mortem route failed, answering null: %s",
            type(exc).__name__,
            exc_info=True,
        )
        rows = None
    return {"postmortems": rows}
