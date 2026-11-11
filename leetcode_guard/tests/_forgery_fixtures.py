"""An on-disk ledger with one forged credit beside one genuine one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    forged_credit,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger


def reload_with_forgery(tmp_path: Path, key_file: Path) -> Ledger:
    """Save a genuine Monday credit plus ``ac:forged``, then load it back.

    Args:
        tmp_path: Where ``ledger.json`` is written.
        key_file: The HMAC key that signs the genuine credit and verifies both.

    Returns:
        The ledger as read back from disk.
    """
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=key_file)
    append(ledger, [forged_credit()])
    save_ledger(path, ledger)
    return load_ledger(path, key_file=key_file)
