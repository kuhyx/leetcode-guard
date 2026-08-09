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
from leetcode_guard._daycost import day_cost, day_key

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._submissions import AcSubmission

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


def _iso(now: datetime) -> str:
    """Serialise a timestamp for storage."""
    return now.isoformat()


def credit_entry(
    submission: AcSubmission,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> LedgerEntry:
    """A signed +1 credit for one accepted submission."""
    return sign(
        LedgerEntry(
            entry_id=f"ac:{submission.submission_id}",
            kind=CREDIT,
            day=day_key(day),
            created_at=_iso(now),
            amount=1,
            detail={
                "title_slug": submission.title_slug,
                "lang": submission.lang,
                "source": SOURCE_LEETCODE,
                "submitted_at": str(submission.timestamp),
            },
        ),
        key_file=key_file,
    )


def seen_entry(
    submission: AcSubmission,
    *,
    day: date,
    now: datetime,
    key_file: Path | None = None,
) -> LedgerEntry:
    """A zero-value marker: this submission predates the gate.

    Written during first-run seeding so the same submission can never later be
    harvested as a credit.
    """
    return sign(
        LedgerEntry(
            entry_id=f"ac:{submission.submission_id}",
            kind=SEEN,
            day=day_key(day),
            created_at=_iso(now),
            amount=0,
            detail={"title_slug": submission.title_slug, "source": SOURCE_SEED},
        ),
        key_file=key_file,
    )


def bootstrap_entry(
    *, day: date, now: datetime, seeded: int, key_file: Path | None = None
) -> LedgerEntry:
    """The marker proving seeding has happened.

    Seeding keys off this rather than off the file's absence, so an
    empty-but-present ledger still gets seeded instead of handing out every
    recent submission as a credit.
    """
    return sign(
        LedgerEntry(
            entry_id=f"bootstrap:{day_key(day)}",
            kind=BOOTSTRAP,
            day=day_key(day),
            created_at=_iso(now),
            amount=0,
            detail={"seeded": str(seeded), "source": SOURCE_SEED},
        ),
        key_file=key_file,
    )


def charge_entry(
    day: date,
    *,
    now: datetime,
    source: str = SOURCE_LEETCODE,
    key_file: Path | None = None,
) -> LedgerEntry:
    """A signed debit for one gated day.

    ``source`` records *why* the day was satisfied: normally credits, but also
    an escape hatch or a classified LeetCode outage. Those still write a charge
    -- the day is settled -- and can push the balance negative, which is
    intended: the debt carries and the next day still costs full price.
    """
    return sign(
        LedgerEntry(
            entry_id=f"charge:{day_key(day)}",
            kind=CHARGE,
            day=day_key(day),
            created_at=_iso(now),
            amount=day_cost(day),
            detail={"source": source},
        ),
        key_file=key_file,
    )


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
