"""Ledger entries in, CRDT records out -- and back again.

Split out of ``_sync.py`` for the 250-line cap. That module owns the transport
and the tick; this one owns the shape conversion, which is where the ordering
rules actually live.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING, Final

from crdt_sync import (
    Hlc,
    Log,
    Record,
    dump_log,
    load_log,
)

from leetcode_guard._constants import (
    DEVICE_ID,
)
from leetcode_guard._ledger import LedgerEntry, from_json, to_json

if TYPE_CHECKING:
    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)


_PAYLOAD_FIELD: Final = "entry"


def _hlc_for(entry: LedgerEntry) -> Hlc:
    """A deterministic clock stamp for one entry.

    Derived from the entry's own ``created_at`` so that syncing an unchanged
    ledger is a no-op at the byte level. Using the wall clock here would
    rewrite every record on every push and fill the sync repo with noise.
    """
    try:
        moment = datetime.fromisoformat(entry.created_at)
    except ValueError:
        _logger.warning(
            "ledger entry %s has an unparsable created_at %r -- stamping it at "
            "the epoch so the merge order stays deterministic",
            entry.entry_id,
            entry.created_at,
        )
        return Hlc(wall_time_ms=0, counter=0, node_id=entry.device or DEVICE_ID)
    return Hlc(
        wall_time_ms=int(moment.timestamp() * 1000),
        counter=0,
        node_id=entry.device or DEVICE_ID,
    )


def records_from_ledger(ledger: Ledger) -> Log:
    """Project the ledger into CRDT records, one per entry."""
    return {
        entry_id: Record(
            id=entry_id,
            fields={_PAYLOAD_FIELD: (to_json(entry), _hlc_for(entry))},
        )
        for entry_id, entry in ledger.entries.items()
    }


def entries_from_records(log: Log) -> list[LedgerEntry]:
    """Read ledger entries back out of merged records."""
    entries = []
    for record in log.values():
        if record.deleted:
            # Ledger entries are never deleted locally, so a tombstone means
            # another device removed one. Honour it by simply not importing it.
            continue
        field = record.fields.get(_PAYLOAD_FIELD)
        if field is None:
            _logger.warning("sync record %s has no %s field", record.id, _PAYLOAD_FIELD)
            continue
        entry = from_json(field[0])
        if entry is None:
            _logger.warning(
                "sync record %s does not parse as a ledger entry", record.id
            )
            continue
        entries.append(entry)
    return entries


def encode_log(log: Log) -> str:
    """Serialise for the sync repo."""
    return dump_log(log)


def decode_log(text: str) -> Log:
    """Parse a device file from the sync repo."""
    return load_log(text)
