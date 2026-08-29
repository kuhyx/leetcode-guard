"""Reading and writing the ledger file.

The load path follows ``gatelock.EscapeTracker.load()``'s structure -- missing
file is empty, corrupt file is empty plus a loud warning, every entry verified
and every problem reported -- with one rule inherited exactly:

**An entry that fails verification is kept in the file, never dropped.**

Whether it is *counted* is a separate decision, and the one place the two
designs diverge. See :mod:`leetcode_guard._balance`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Final

from leetcode_guard._ledger import (
    CREDIT,
    SEEN,
    LedgerEntry,
    from_json,
    key_available,
    to_json,
    verify,
)

_logger: Final = logging.getLogger(__name__)

_VERSION: Final = 1


@dataclass
class Ledger:
    """Every entry, plus what could be established about their integrity."""

    entries: dict[str, LedgerEntry] = field(default_factory=dict)
    tampered: int = 0
    """Entries whose signature failed against a **readable** key. Real
    evidence of editing, not an infrastructure problem."""

    integrity_ok: bool = True
    """Whether the HMAC key could be read at all. ``False`` means every
    signature check was meaningless, so verdicts based on them must not be
    trusted in either direction."""

    unparsable: int = 0
    """Rows that could not be read as entries. Reported, never silently zero."""

    def has(self, entry_id: str) -> bool:
        """Whether an entry with this id is already recorded."""
        return entry_id in self.entries

    def of_kind(self, kind: str) -> list[LedgerEntry]:
        """Every entry of one kind."""
        return [entry for entry in self.entries.values() if entry.kind == kind]


def solved_slugs(ledger: Ledger) -> frozenset[str]:
    """Every problem this device has recorded as solved, from the ledger alone.

    Independent of the LeetCode session, which is the whole point: cookies
    expire about every two weeks with no refresh flow, and the pool query is
    public, so an expired session yields a full problem list whose ``status``
    is uniformly ``null``. That silently disables LeetCode's own solved-filter
    while the surface still claims to be filtering. The ledger needs no
    cookies and no network, so it keeps working across that failure.

    Both ``CREDIT`` and ``SEEN`` carry a ``title_slug`` and both mean solved:
    ``SEEN`` is a submission that predates the gate, not one that failed. Keyed
    on ``kind`` rather than an ``ac:`` id prefix so the id format stays free to
    change. This is a filtering judgement only -- ``SEEN`` is still worth zero
    credits, and nothing here touches the balance.

    Returns:
        The slugs, as a **lower bound**: the ledger only ever saw the handful
        of submissions the recent-AC feed returns, so this means "solved and
        recorded here", never "everything you have ever solved".
    """
    slugs = set()
    for entry in ledger.entries.values():
        if entry.kind not in {CREDIT, SEEN}:
            # charge/bootstrap entries carry no title_slug at all.
            continue
        slug = entry.detail.get("title_slug")
        if slug:
            slugs.add(slug)
    return frozenset(slugs)


def load_ledger(path: Path, *, key_file: Path | None = None) -> Ledger:
    """Read the ledger, verifying every entry.

    Never raises. An unreadable ledger has to degrade to an empty one rather
    than abort, but note what that costs: an empty ledger is a zero balance, so
    a corrupt file locks rather than unlocks. That is the correct direction to
    fail, and it is why every corruption path here logs loudly enough to
    diagnose from the journal.
    """
    ledger = Ledger(integrity_ok=key_available(key_file=key_file))
    if not ledger.integrity_ok:
        _logger.warning(
            "HMAC key at %s is unreadable -- ledger integrity checking is OFF",
            key_file,
        )

    if not path.exists():
        return ledger

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        # .exception() already attaches the traceback, so the exception object
        # must not also be interpolated into the message.
        _logger.exception("ledger at %s is unreadable -- treating it as empty", path)
        return ledger

    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        _logger.error("ledger at %s has no entries array -- treating it as empty", path)
        return ledger

    for row in rows:
        entry = from_json(row)
        if entry is None:
            ledger.unparsable += 1
            _logger.error("ledger at %s holds an unreadable entry: %r", path, row)
            continue
        checked = _with_verification(entry, ledger=ledger, key_file=key_file)
        ledger.entries[checked.entry_id] = checked

    if ledger.tampered:
        _logger.error(
            "%d ledger entries failed their signature check -- they are kept on "
            "disk and reported, and forged credits will not be counted",
            ledger.tampered,
        )
    return ledger


def _with_verification(
    entry: LedgerEntry, *, ledger: Ledger, key_file: Path | None
) -> LedgerEntry:
    """Attach a verification verdict, counting genuine tampering."""
    if not ledger.integrity_ok:
        return entry
    verified = verify(entry, key_file=key_file)
    if not verified:
        ledger.tampered += 1
    return LedgerEntry(
        entry_id=entry.entry_id,
        kind=entry.kind,
        day=entry.day,
        created_at=entry.created_at,
        amount=entry.amount,
        device=entry.device,
        detail=dict(entry.detail),
        signature=entry.signature,
        verified=verified,
    )


def save_ledger(path: Path, ledger: Ledger) -> bool:
    """Persist the ledger atomically.

    Returns:
        Whether the write succeeded. Reported rather than raised, because the
        caller is usually a lock window mid-unlock.
    """
    payload = {
        "version": _VERSION,
        "entries": [to_json(entry) for entry in ledger.entries.values()],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name,
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        Path(temp_name).replace(path)
    except OSError:
        _logger.exception("could not write the ledger to %s", path)
        return False
    return True


def append(ledger: Ledger, entries: list[LedgerEntry]) -> int:
    """Add entries that are not already present.

    Returns:
        How many were actually new. Existing ids are left untouched -- the
        ledger is append-only, and re-writing an entry would let a later run
        change the ``day`` a credit was earned on.
    """
    added = 0
    for entry in entries:
        if ledger.has(entry.entry_id):
            continue
        ledger.entries[entry.entry_id] = entry
        added += 1
    return added
