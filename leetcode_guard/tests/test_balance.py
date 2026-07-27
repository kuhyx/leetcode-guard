"""Tests for the integrity table.

This is the security-critical table from :mod:`leetcode_guard._balance`. Each
row below is one line of it, and each exists because getting it wrong is either
a bypass (counting a forged credit) or a brick (refusing every credit because a
key file lost its read bit).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._balance import compute_balance, counts_toward_balance
from leetcode_guard._ledger import LedgerEntry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    add_charge,
    foreign_credit,
    forged_credit,
    ledger_with_credits,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_valid_credits_count(hmac_key: Path):
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)

    balance = compute_balance(ledger)

    assert balance.credits == 3
    assert balance.available == 3
    assert balance.discounted == 0


def test_charges_are_subtracted(hmac_key: Path):
    ledger = ledger_with_credits(3, day=MONDAY, key_file=hmac_key)
    add_charge(ledger, MONDAY, key_file=hmac_key)

    balance = compute_balance(ledger)

    assert balance.charged == 1
    assert balance.available == 2


def test_a_forged_credit_is_refused_but_kept_on_disk(tmp_path: Path, hmac_key: Path):
    """The whole point of signing. Appending
    ``{"kind": "credit", "amount": 1}`` by hand must not buy a day -- and the
    evidence must survive in the file."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [forged_credit()])
    save_ledger(path, ledger)

    reloaded = load_ledger(path, key_file=hmac_key)
    balance = compute_balance(reloaded)

    assert balance.credits == 1
    assert balance.discounted == 1
    assert balance.tampered == 1
    assert reloaded.has("ac:forged")


def test_an_edited_credit_amount_is_refused(tmp_path: Path, hmac_key: Path):
    """Changing a signed entry's amount invalidates its signature."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    only = next(iter(ledger.entries.values()))
    ledger.entries[only.entry_id] = LedgerEntry(
        entry_id=only.entry_id,
        kind=only.kind,
        day=only.day,
        created_at=only.created_at,
        amount=99,
        device=only.device,
        detail=dict(only.detail),
        signature=only.signature,
    )
    save_ledger(path, ledger)

    balance = compute_balance(load_ledger(path, key_file=hmac_key))

    assert balance.credits == 0
    assert balance.discounted == 99


def test_charges_still_count_when_their_signature_fails(tmp_path: Path, hmac_key: Path):
    """Here the literal gatelock rule applies unchanged: discarding an
    unverifiable charge would refund a day."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    append(
        ledger,
        [
            LedgerEntry(
                entry_id="charge:2026-07-27",
                kind="charge",
                day="2026-08-10",
                created_at=NOW.isoformat(),
                amount=1,
                signature=None,
            )
        ],
    )
    save_ledger(path, ledger)

    balance = compute_balance(load_ledger(path, key_file=hmac_key))

    assert balance.charged == 1
    assert balance.available == 1


def test_an_unreadable_key_still_counts_this_devices_credits(
    tmp_path: Path, hmac_key: Path, missing_key: Path
):
    """A chmod on the key must not brick the machine."""
    path = tmp_path / "ledger.json"
    save_ledger(path, ledger_with_credits(3, day=MONDAY, key_file=hmac_key))

    reloaded = load_ledger(path, key_file=missing_key)
    balance = compute_balance(reloaded)

    assert not balance.integrity_ok
    assert balance.credits == 3
    assert balance.tampered == 0


def test_an_unreadable_key_refuses_credits_from_another_device(
    tmp_path: Path, hmac_key: Path, missing_key: Path
):
    """Sync is a user-writable channel into the ledger. With no way to check a
    signature, a foreign credit cannot be trusted."""
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [foreign_credit(key_file=hmac_key)])
    save_ledger(path, ledger)

    balance = compute_balance(load_ledger(path, key_file=missing_key))

    assert balance.credits == 1
    assert balance.discounted == 1


def test_a_verified_foreign_credit_counts_when_the_key_is_readable(
    tmp_path: Path, hmac_key: Path
):
    path = tmp_path / "ledger.json"
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    append(ledger, [foreign_credit(key_file=hmac_key)])
    save_ledger(path, ledger)

    balance = compute_balance(load_ledger(path, key_file=hmac_key))

    assert balance.credits == 2


def test_marker_kinds_contribute_nothing(hmac_key: Path):
    ledger = Ledger()
    append(
        ledger,
        [
            LedgerEntry(
                entry_id="ac:seen-1",
                kind="seen",
                day="2026-08-10",
                created_at=NOW.isoformat(),
                amount=0,
                verified=True,
            ),
            LedgerEntry(
                entry_id="bootstrap:2026-07-27",
                kind="bootstrap",
                day="2026-08-10",
                created_at=NOW.isoformat(),
                amount=0,
                verified=True,
            ),
        ],
    )

    balance = compute_balance(ledger)

    assert balance.credits == 0
    assert balance.discounted == 0


def test_available_goes_negative_when_a_day_is_settled_without_credits(hmac_key: Path):
    """An escaped or outage-forgiven day carries debt forward; the next day
    still costs full price."""
    ledger = Ledger()
    add_charge(ledger, MONDAY, key_file=hmac_key)

    assert compute_balance(ledger).available == -1


def test_counts_toward_balance_is_a_direct_reading_of_the_table():
    valid = LedgerEntry("ac:1", "credit", "2026-08-10", "", 1, verified=True)
    invalid = LedgerEntry("ac:2", "credit", "2026-08-10", "", 1, verified=False)
    foreign = LedgerEntry("ac:3", "credit", "2026-08-10", "", 1, device="phone")
    charge = LedgerEntry("charge:x", "charge", "2026-08-10", "", 1)
    marker = LedgerEntry("ac:4", "seen", "2026-08-10", "", 0)

    assert counts_toward_balance(valid, integrity_ok=True)
    assert not counts_toward_balance(invalid, integrity_ok=True)
    assert counts_toward_balance(invalid, integrity_ok=False)
    assert not counts_toward_balance(foreign, integrity_ok=False)
    assert counts_toward_balance(charge, integrity_ok=True)
    assert counts_toward_balance(charge, integrity_ok=False)
    assert not counts_toward_balance(marker, integrity_ok=True)
