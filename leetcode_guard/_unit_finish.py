"""Contract C6: ``unit_finish.json``, the signed trigger of the tutor's post-mortem.

A unit is finished when the phase machine has moved past it (its theory is
done and every free Easy problem is solved: ``_phase``). For each finished
unit with a tutor mapping this guard appends one signed row whenever the set
of solves the unit claims changes::

    {
        "version": 1,
        "entries": [
            {
                "kind": "unit_finish",
                "entry_id": "finish:<unit>:<n>",
                "day": "YYYY-MM-DD",
                "detail": {
                    "unit": "prefix-sums",
                    "subject": "...",
                    "modules": ["..."],
                    "at": 1795400000.0,
                    "solves": ["slug", ...],
                },
                "hmac": "...",
            }
        ],
    }

``solves`` is every problem the unit claims (``Curriculum.unit_index``, any
difficulty) that the ledger holds a trusted solve for. The tutor decides
whether to run (``tutor/postmortem/watch.py``: at least 3 solves the last
post-mortem did not see). Nothing here mints, charges or decides: deleting
the file re-writes the same rows on the next poll, and an edited row fails
its signature, so neither can start a post-mortem the solves do not warrant.

``postmortem_dry_run.json`` is the same row for any unit, finished or not
(``kind: unit_preview``), one per file: ``--postmortem-dry-run`` writes it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from leetcode_guard import _constants
from leetcode_guard._atomic_json import write_json
from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._phase_inputs import trusted_solved_slugs
from leetcode_guard._pool_cache import read_cache
from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from leetcode_guard._curriculum import Curriculum, Unit
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState

_logger: Final = logging.getLogger(__name__)

FINISH_FILE = _constants.DATA_DIR / "unit_finish.json"
PREVIEW_FILE = _constants.DATA_DIR / "postmortem_dry_run.json"
"""Both read at call time, so the test suite can point them at a scratch dir."""
FINISH: Final = "unit_finish"
PREVIEW: Final = "unit_preview"

Row = dict[str, object]


def _claims(
    curriculum: Curriculum, ledger: Ledger, key_file: Path | None
) -> list[set[str]] | None:
    """Per unit, the solved slugs it claims; ``None`` without a trusted pool."""
    pool = read_cache(_constants.POOL_CACHE_FILE, key_file=key_file)
    if pool is None or not pool.verified:
        _logger.warning("no signed problem pool: unit solves not recorded")
        return None
    solved = trusted_solved_slugs(ledger)
    found: list[set[str]] = [set() for _ in curriculum.units]
    for problem in pool.problems:
        if problem.title_slug in solved:
            index = curriculum.unit_index(problem.topics)
            if index < len(found):
                found[index].add(problem.title_slug)
    return found


def _row(kind: str, unit: Unit, solves: set[str], n: int, now: datetime) -> Row:
    return {
        "kind": kind,
        "entry_id": f"finish:{unit.unit_id}:{n}",
        "day": now.date().isoformat(),
        "detail": {
            "unit": unit.unit_id,
            "subject": unit.subject,
            "modules": list(unit.modules),
            "at": now.timestamp(),
            "solves": sorted(solves),
        },
    }


def _signed(row: Row, key_file: Path | None) -> Row | None:
    signature = compute_entry_hmac(row, key_file=key_file)
    if signature is None:
        _logger.warning("HMAC key unreadable: unit row not written")
        return None
    return {**row, "hmac": signature}


def _rows(path: Path, key_file: Path | None) -> list[Row]:
    """The file's verified rows; a forged or broken row is dropped (logged)."""
    raw = read_json(path, _logger, "unit file %s unreadable: %s", path)
    rows = raw.get("entries") if isinstance(raw, dict) else None
    if raw is MISSING or not isinstance(rows, list):
        return []
    kept = [r for r in rows if isinstance(r, dict) and _valid(r, key_file)]
    if len(kept) != len(rows):
        _logger.warning("%s: %d unverified rows dropped", path, len(rows) - len(kept))
    return kept


def _valid(row: Row, key_file: Path | None) -> bool:
    try:
        return verify_entry_hmac(row, key_file=key_file)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.exception("a unit row's signature check raised: dropped")
        return False


def _solves_of(row: Row) -> object:
    detail = row.get("detail")
    return detail.get("solves") if isinstance(detail, dict) else None


def _finished(curriculum: Curriculum, state: PhaseState) -> list[int]:
    """Indices of the mapped units the machine has moved past."""
    ids = [unit.unit_id for unit in curriculum.units]
    if state.unit and state.unit not in ids:
        return []
    stop = ids.index(state.unit) if state.unit else len(ids)
    return [i for i in range(stop) if curriculum.units[i].subject]


def record_finishes(
    ledger: Ledger, state: PhaseState, *, now: datetime, key_file: Path | None = None
) -> list[Row]:
    """Append a signed row per finished unit whose claimed solves changed."""
    curriculum = load_curriculum()
    finished = _finished(curriculum, state) if curriculum else []
    if curriculum is None or not finished:
        return []
    claims = _claims(curriculum, ledger, key_file)
    if claims is None:
        return []
    rows = _rows(FINISH_FILE, key_file)
    fresh: list[Row] = []
    for index in finished:
        unit = curriculum.units[index]
        prefix = f"finish:{unit.unit_id}:"
        mine = [r for r in rows if str(r.get("entry_id")).startswith(prefix)]
        if mine and _solves_of(mine[-1]) == sorted(claims[index]):
            continue
        made = _signed(_row(FINISH, unit, claims[index], len(mine) + 1, now), key_file)
        if made is None:
            return []
        fresh.append(made)
    if fresh:
        write_json(FINISH_FILE, {"version": 1, "entries": [*rows, *fresh]})
    return fresh


def write_preview(
    ledger: Ledger, unit_id: str, *, now: datetime, key_file: Path | None = None
) -> Row | None:
    """Sign the dry-run row for ``unit_id``; ``None`` (logged) when it cannot."""
    curriculum = load_curriculum()
    units = curriculum.units if curriculum else ()
    index = next((i for i, u in enumerate(units) if u.unit_id == unit_id), None)
    if curriculum is None or index is None or not units[index].subject:
        _logger.warning("%s is not a unit with tutor theory", unit_id)
        return None
    claims = _claims(curriculum, ledger, key_file)
    if claims is None:
        return None
    made = _signed(_row(PREVIEW, units[index], claims[index], 1, now), key_file)
    if made is not None:
        write_json(PREVIEW_FILE, {"version": 1, "entries": [made]})
    return made
