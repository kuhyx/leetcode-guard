"""Keep a local copy of the snapshot for the desktop app.

The desktop build of the status app reads this file instead of Firebase, so
it works with no sign-in and no network. :func:`push_snapshot` writes it on
every attempt, *before* the network is touched: an offline minute still
refreshes it, and its own ``generated_at`` is the desktop's freshness signal
(there is no local heartbeat).

**Display-only, like ``progress_cache.json``.** Nothing that decides, charges
or credits may read it; ``test_push_trigger`` searches every deciding module
for its name. Deleting it costs the desktop one minute of "unknown".
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._atomic_json import write_json
from leetcode_guard._constants import DATA_DIR

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

LOCAL_SNAPSHOT_FILE: Final = DATA_DIR / "snapshot.json"
"""Here rather than in ``_constants``, which is at the line cap."""


def write_local_snapshot(snapshot: dict[str, Any], path: Path | None = None) -> bool:
    """Atomically replace the local copy with ``snapshot``. Never raises."""
    target = LOCAL_SNAPSHOT_FILE if path is None else path
    try:
        write_json(target, snapshot)
    except OSError as exc:
        _logger.warning("could not write the local snapshot at %s: %s", target, exc)
        return False
    return True
