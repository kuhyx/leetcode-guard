"""Write a JSON document to disk so readers see the old file or the new one.

Four caches and the ledger all need the same thing -- never a half-written
file, even if the process dies mid-write -- so the temp-file / fsync / rename
dance lives here once. Callers own the error policy: this raises ``OSError``
and they decide whether that is a warning or an exception.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def write_json(
    path: Path,
    payload: object,
    *,
    indent: int | None = None,
    before_write: Callable[[Path], None] | None = None,
) -> None:
    """Atomically replace ``path`` with ``payload`` serialised as JSON.

    Args:
        path: Destination. Its parent is created if missing.
        payload: Anything ``json.dump`` accepts.
        indent: Passed through to ``json.dump``.
        before_write: Called with the temporary file's path before any byte
            of ``payload`` reaches it -- e.g. to set 0600 on a credential
            file, which has to happen before the secret is written, not after.

    Raises:
        OSError: If any step of the write fails; ``path`` is untouched then.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name,
        suffix=".tmp",
        delete=False,
    ) as handle:
        if before_write is not None:
            before_write(Path(handle.name))
        json.dump(payload, handle, indent=indent)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    Path(temp_name).replace(path)
