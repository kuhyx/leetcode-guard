"""Read a JSON cache file, folding "absent" and "unreadable" into one answer.

The caches (pool, progress, profile, statements, unresolved difficulties) all
open the same way: no file means "nothing cached yet", an unreadable one means
the same plus a warning. Each caller still owns its schema check, its own
empty value and its warning text; only the open-and-parse step is shared.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import logging
    from pathlib import Path

MISSING: Final = object()
"""Returned when there is no usable document; compare with ``is``."""


def read_json(
    path: Path, logger: logging.Logger, message: str, *args: object
) -> object:
    """The parsed JSON at ``path``, or :data:`MISSING`.

    Args:
        path: The cache file.
        logger: The caller's logger, so the warning keeps the caller's name.
        message: The warning's %-format; its last ``%s`` receives the error.
        *args: The format's other arguments, before the error.

    Returns:
        Whatever ``json.loads`` produced, or :data:`MISSING` when the file is
        absent, or exists but cannot be read or parsed (warned via ``logger``).
    """
    if not path.exists():
        return MISSING
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(message, *args, exc)
        return MISSING
