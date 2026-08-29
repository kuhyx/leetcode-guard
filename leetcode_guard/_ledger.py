"""Ledger entries and their signatures.

The ledger is append-only and every entry is HMAC-signed against a root-owned
key. Two kinds carry value:

* ``ac:<submission_id>`` -- a credit, worth 1. Keyed on LeetCode's own
  submission id, which is what makes re-polling idempotent and lets a solve
  from before the lock engaged count with no timestamp bookkeeping.
* ``charge:<YYYY-MM-DD>`` -- a debit, worth :func:`day_cost` for that day.

Two more carry none: ``seen:`` marks a submission that existed before the gate
did (first-run seeding) and ``bootstrap:`` records that seeding happened.

Honest scope: the key is world-readable, so this is tamper-*evident*, not
tamper-*proof*. It stops casual editing of a JSON file and leaves a loud record
when someone tries; it does not stop someone who reads the key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from leetcode_guard._constants import DEVICE_ID

if TYPE_CHECKING:
    from pathlib import Path


CREDIT: Final = "credit"
CHARGE: Final = "charge"
SEEN: Final = "seen"
BOOTSTRAP: Final = "bootstrap"

SOURCE_LEETCODE: Final = "leetcode"
SOURCE_SEED: Final = "seed"
SOURCE_ESCAPE: Final = "escape"
SOURCE_OUTAGE: Final = "leetcode-outage"
SOURCE_NETWORK_INCIDENT: Final = "network-incident"
_PROBE_PAYLOAD: Final[dict[str, object]] = {"probe": "1"}


@dataclass(frozen=True)
class LedgerEntry:
    """One immutable line in the ledger.

    Attributes:
        entry_id: Unique and meaningful -- ``ac:<id>`` or ``charge:<date>``. It
            is the dedupe key, so its construction is the whole idempotency
            story.
        kind: One of :data:`CREDIT`, :data:`CHARGE`, :data:`SEEN`,
            :data:`BOOTSTRAP`.
        day: Local ``YYYY-MM-DD`` the entry belongs to.
        created_at: UTC ISO timestamp. Forensics and HLC ordering only -- never
            day arithmetic, which is local.
        amount: Credits granted or consumed. Zero for the marker kinds.
        device: Which machine wrote it. Load-bearing when the HMAC key is
            unreadable; see :mod:`leetcode_guard._balance`.
        detail: Free-form context (``title_slug``, ``lang``, ``source``).
        signature: The HMAC, or ``None`` if signing was impossible.
        verified: Filled in at load time. **Never** used to decide whether to
            keep an entry -- only whether to count it.
    """

    entry_id: str
    kind: str
    day: str
    created_at: str
    amount: int
    device: str = DEVICE_ID
    detail: dict[str, str] = field(default_factory=dict)
    signature: str | None = None
    verified: bool = False


def entry_payload(entry: LedgerEntry) -> dict[str, object]:
    """The signed portion of an entry.

    Excludes ``signature`` (it is the output) and ``verified`` (it is derived
    at load time and not part of the record).
    """
    return {
        "entry_id": entry.entry_id,
        "kind": entry.kind,
        "day": entry.day,
        "created_at": entry.created_at,
        "amount": entry.amount,
        "device": entry.device,
        "detail": dict(entry.detail),
    }


def sign(entry: LedgerEntry, *, key_file: Path | None = None) -> LedgerEntry:
    """Return a copy carrying its HMAC.

    A ``None`` signature means the key was unreadable, not that the entry is
    fraudulent. The distinction is what :func:`key_available` exists for.
    """
    signature = compute_entry_hmac(entry_payload(entry), key_file=key_file)
    return LedgerEntry(
        entry_id=entry.entry_id,
        kind=entry.kind,
        day=entry.day,
        created_at=entry.created_at,
        amount=entry.amount,
        device=entry.device,
        detail=dict(entry.detail),
        signature=signature,
        verified=signature is not None,
    )


def verify(entry: LedgerEntry, *, key_file: Path | None = None) -> bool:
    """Whether ``entry``'s signature matches its contents."""
    if entry.signature is None:
        return False
    payload = entry_payload(entry)
    payload["hmac"] = entry.signature
    return verify_entry_hmac(payload, key_file=key_file)


def key_available(*, key_file: Path | None = None) -> bool:
    """Whether the HMAC key can be read at all.

    This is the discriminator the whole integrity policy rests on.
    ``verify_entry_hmac`` returns ``False`` both for a forged entry and for a
    key file that merely cannot be read, and those two cases must lead to
    opposite decisions: refuse to count a forgery, keep counting when the
    infrastructure is broken. Probing the key once separates them.
    """
    return compute_entry_hmac(_PROBE_PAYLOAD, key_file=key_file) is not None


def to_json(entry: LedgerEntry) -> dict[str, Any]:
    """Serialise an entry for the ledger file."""
    payload = entry_payload(entry)
    payload["hmac"] = entry.signature
    return payload


def from_json(raw: object) -> LedgerEntry | None:
    """Parse a stored entry, or ``None`` if it is unusable."""
    if not isinstance(raw, dict):
        return None
    entry_id = raw.get("entry_id")
    kind = raw.get("kind")
    day = raw.get("day")
    if (
        not isinstance(entry_id, str)
        or not isinstance(kind, str)
        or not isinstance(day, str)
    ):
        return None
    amount = raw.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int):
        return None
    detail = raw.get("detail")
    signature = raw.get("hmac")
    return LedgerEntry(
        entry_id=entry_id,
        kind=kind,
        day=day,
        created_at=str(raw.get("created_at", "")),
        amount=amount,
        device=str(raw.get("device", "")),
        detail={str(k): str(v) for k, v in detail.items()}
        if isinstance(detail, dict)
        else {},
        signature=signature if isinstance(signature, str) else None,
    )
