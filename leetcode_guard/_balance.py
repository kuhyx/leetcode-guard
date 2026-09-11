"""Which ledger entries count, and what the balance therefore is.

The balance is always ``sum(counted credits) - sum(charges)``, recomputed from
the entries every time. There is no stored total, because a stored total is one
number someone can edit.

The counting table -- implement it exactly, the asymmetry is the point:

===============  =============  ========  ========
Key readable     Signature      Kind      Counted
===============  =============  ========  ========
yes              valid          credit    **yes**
yes              invalid        credit    **no**
yes              any            charge    yes
no               n/a            credit    yes, if this device wrote it
no               n/a            credit    no, if another device did
no               n/a            charge    yes
any              any            charge    surcharge repays debt only if trusted
===============  =============  ========  ========

**Why credits invert gatelock's rule.** ``EscapeTracker.load()`` keeps entries
it cannot verify, because there an entry is a *usage counted against you* and
keeping it is the conservative direction. Here a credit is the resource that
*grants* unlock, so keeping an unverified one is precisely the bypass the rule
exists to prevent: appending ``{"kind": "credit", "amount": 1}`` with no
signature would buy a day. Charges keep the literal rule, for the same
underlying reason -- discarding one would refund a day.

**Why a charge's surcharge is the exception to the charge rule.** A charge
written while debt was outstanding is one credit dearer than the day itself,
and that extra credit is what repays the debt (see ``_debt``). Repayment
*relieves* the user the way a credit does, so it follows the credit rule: the
whole ``amount`` still counts as spent whatever the signature says -- never a
refund -- but only a trusted entry's surcharge counts as repaid. Inflating the
amount of a forged charge therefore costs balance and buys nothing.

**Why the key-readable column exists.** ``verify_entry_hmac`` returns ``False``
both for a forgery and for a key file that merely cannot be read. Without the
distinction, a single ``chmod`` on the key would make every credit uncountable
and brick the machine. With it, an unreadable key degrades to trusting this
device's own entries -- announced loudly -- while still refusing entries that
arrived over sync from somewhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import DEVICE_ID
from leetcode_guard._ledger import CHARGE, CREDIT, LedgerEntry

if TYPE_CHECKING:
    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class Balance:
    """The derived credit position."""

    credits: int
    charged: int
    available: int
    """``credits - charged``. **May be negative**: an escape hatch or a
    classified outage settles a day without spending credits, so the debt
    carries forward and the next day still costs full price."""

    discounted: int
    """Credits present in the file but refused -- forged, or foreign while the
    key is unreadable. Surfaced on the lock so a refusal is never silent."""

    tampered: int
    integrity_ok: bool
    unparsable: int


def is_trusted(entry: LedgerEntry, *, integrity_ok: bool) -> bool:
    """The credit rule, applied to credits and to the surcharge on charges.

    A valid signature, or this device's own entry when the key cannot be read.
    """
    if integrity_ok:
        return entry.verified
    return entry.device == DEVICE_ID


def counts_toward_balance(entry: LedgerEntry, *, integrity_ok: bool) -> bool:
    """Whether one entry contributes, per the table in the module docstring."""
    if entry.kind == CHARGE:
        return True
    if entry.kind != CREDIT:
        return False
    return is_trusted(entry, integrity_ok=integrity_ok)


def compute_balance(ledger: Ledger) -> Balance:
    """Derive the balance from the entries.

    Args:
        ledger: A loaded ledger, with verification already attached.

    Returns:
        The position, including how much was refused and why.
    """
    # `earned`, not `credits`: the latter is a Python builtin.
    earned = 0
    charged = 0
    discounted = 0
    for entry in ledger.entries.values():
        if entry.kind == CHARGE:
            charged += entry.amount
            continue
        if entry.kind != CREDIT:
            continue
        if counts_toward_balance(entry, integrity_ok=ledger.integrity_ok):
            earned += entry.amount
        else:
            discounted += entry.amount

    if discounted:
        _logger.error(
            "%d ledger credits were refused (forged signature, or written by "
            "another device while the HMAC key is unreadable)",
            discounted,
        )

    return Balance(
        credits=earned,
        charged=charged,
        available=earned - charged,
        discounted=discounted,
        tampered=ledger.tampered,
        integrity_ok=ledger.integrity_ok,
        unparsable=ledger.unparsable,
    )
