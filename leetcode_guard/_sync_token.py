"""The GitHub token that backs cross-device sync.

Its own module so nothing else has to know how the secret is stored, and so
there is exactly one place that could ever leak it. Nothing here returns the
token in an error message, a log line or a repr.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


def read_sync_token(path: Path) -> str | None:
    """Read the GitHub token, or ``None`` if there isn't a usable one.

    Sync is entirely optional: the gate works fully without it, so every
    failure here is a warning and a ``None``, never an exception. Log lines
    name the *path* and never the contents.
    """
    if not path.exists():
        _logger.debug("no sync token at %s -- sync is disabled", path)
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _logger.warning("cannot read the sync token at %s: %s", path, exc)
        return None
    if not text:
        _logger.warning("the sync token at %s is empty -- sync is disabled", path)
        return None
    return text.splitlines()[0].strip()
