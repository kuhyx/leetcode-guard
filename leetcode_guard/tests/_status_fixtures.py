"""Snapshot builder shared by the ``test_status*`` modules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from leetcode_guard._status import PoolFiles, gather_status

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._status_model import StatusSnapshot

MONDAY_NOON = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def status_at(
    tmp_path: Path,
    key_file: Path,
    *,
    ledger_path: Path | None = None,
    now: datetime = MONDAY_NOON,
) -> StatusSnapshot:
    """Gather a status snapshot whose pool cache and cookies live in *tmp_path*.

    Args:
        tmp_path: Directory for the pool cache, the cookies and, by default,
            the ledger.
        key_file: The HMAC key to verify the ledger with.
        ledger_path: The ledger to read; ``tmp_path / "ledger.json"`` if omitted.
        now: The moment the snapshot is taken.

    Returns:
        The snapshot.
    """
    return gather_status(
        now=now,
        ledger_path=tmp_path / "ledger.json" if ledger_path is None else ledger_path,
        pool_files=PoolFiles(
            cache=tmp_path / "pool.json", cookies=tmp_path / "cookies.json"
        ),
        key_file=key_file,
    )
