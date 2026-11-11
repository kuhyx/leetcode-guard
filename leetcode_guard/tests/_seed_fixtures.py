"""First-run seeding shortcut shared by the scenario test modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._harvest import SeedStamp, seed_ledger
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._submissions import SolveProbe


def seed_monday(ledger: Ledger, probe: SolveProbe, path: Path, key_file: Path) -> int:
    """Seed *ledger* from *probe* as a first run on Monday at ``NOW``.

    Args:
        ledger: The ledger to seed in place.
        probe: What LeetCode reported on the first run.
        path: Where the seeded ledger is saved.
        key_file: The HMAC key to sign with.

    Returns:
        Whatever ``seed_ledger`` returns (markers written, or -1 when blind).
    """
    return seed_ledger(
        ledger,
        probe,
        stamp=SeedStamp(day=MONDAY, now=NOW, key_file=key_file),
        path=path,
    )
