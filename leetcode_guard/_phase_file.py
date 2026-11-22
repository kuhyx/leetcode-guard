"""Contract C3: the signed ``theory_phase.json`` the tutor reads.

One signed row, rewritten only when the unit, the phase or ``teachable``
changes (the ``at`` stamp alone never rewrites it)::

    {
        "kind": "theory_phase",
        "entry_id": "phase",
        "day": "YYYY-MM-DD",
        "detail": {
            "unit": "...",
            "phase": "theory" | "solve" | "none",
            "teachable": [["<subject>", "<module>"], ...],
            "at": 1.0,
        },
        "hmac": "...",
    }

Signed like every row in the fleet (``gatelock.log_integrity``: HMAC-SHA256
over the row without ``hmac``). The tutor fails closed on a missing or bad
file, so a write that cannot be signed is skipped, logged, and the old file
stays. The same file is this guard's "last signed phase": when the inputs
cannot be read, the display holds it (:func:`read_phase`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from leetcode_guard._atomic_json import write_json
from leetcode_guard._constants import DATA_DIR
from leetcode_guard._phase import PhaseState
from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._phase_view import Phase

_logger: Final = logging.getLogger(__name__)

PHASE_FILE = DATA_DIR / "theory_phase.json"
"""Read at call time, so the test suite can point it at a scratch dir."""

_PAIR: Final = 2
_PHASES: Final[dict[object, Phase]] = {
    "theory": "theory",
    "solve": "solve",
    "none": "none",
}


def _content(state: PhaseState) -> dict[str, object]:
    """What a rewrite is decided on: unit, phase and the teachable list."""
    return {
        "unit": state.unit,
        "phase": state.phase,
        "teachable": [list(pair) for pair in state.teachable],
    }


def _stored(key_file: Path | None) -> dict[str, object] | None:
    """The file's ``detail`` when its signature verifies, else ``None``."""
    row = read_json(PHASE_FILE, _logger, "phase file %s unreadable: %s", PHASE_FILE)
    if row is MISSING or not isinstance(row, dict):
        return None
    detail = row.get("detail")
    if not verify_entry_hmac(row, key_file=key_file) or not isinstance(detail, dict):
        _logger.warning("phase file %s fails its signature, ignored", PHASE_FILE)
        return None
    return detail


def write_phase(
    state: PhaseState, *, day: date, now: datetime, key_file: Path | None = None
) -> bool:
    """Rewrite the file when the content changed. Returns whether it was written."""
    content = _content(state)
    stored = _stored(key_file)
    if stored is not None and {k: stored.get(k) for k in content} == content:
        return False
    row: dict[str, object] = {
        "kind": "theory_phase",
        "entry_id": "phase",
        "day": day.isoformat(),
        "detail": {**content, "at": now.timestamp()},
    }
    signature = compute_entry_hmac(row, key_file=key_file)
    if signature is None:
        _logger.warning("HMAC key unreadable: %s not rewritten", PHASE_FILE)
        return False
    try:
        write_json(PHASE_FILE, {**row, "hmac": signature})
    except OSError as exc:
        _logger.warning("cannot write %s: %s", PHASE_FILE, exc)
        return False
    return True


def read_phase(key_file: Path | None = None) -> PhaseState | None:
    """The last signed phase, or ``None`` when there is none to trust."""
    stored = _stored(key_file)
    if stored is None:
        return None
    unit, phase, teachable = (stored.get(k) for k in ("unit", "phase", "teachable"))
    pairs = teachable if isinstance(teachable, list) else []
    valid = all(
        isinstance(pair, list)
        and len(pair) == _PAIR
        and all(isinstance(x, str) for x in pair)
        for pair in pairs
    )
    if not isinstance(unit, str) or phase not in _PHASES or not valid:
        _logger.warning("phase file %s has a bad shape, ignored", PHASE_FILE)
        return None
    return PhaseState(
        unit=unit,
        phase=_PHASES[phase],
        subject=pairs[0][0] if pairs else "",
        modules=tuple(pair[1] for pair in pairs),
    )
