"""Has the tutor taught a unit's theory yet? A read-only look at its files.

kuhy's rule (2026-11-21): theory first, then the block's problems. A block whose
theory is not taught stays on the suggestion list -- the lock must always offer
something to solve -- but is marked and sorted under the taught ones.

**"Done" is every live card of the unit's modules taught once**, not the
tutor's own "mastered" (a Good review of every card, days later). That is a
second copy of a tutor rule and kuhy chose it knowingly; it is why this module
reads the event log rather than the stored module status.

File shapes, measured against ``~/.local/share/tutor`` on 2026-11-21 and
re-checked live by ``scripts/verify_theory_shape.py``:

* ``subjects/<subject>/cards.json`` -- ``{card_id: {"module": str,
  "suspended": bool, ...}}``. Cards exist only for modules the tutor has
  unlocked, so a locked module has none and reads as pending.
* ``log.jsonl`` -- one JSON object per line, appended while this reads; a
  taught card is ``{"k": "taught", "s": <subject>, "c": <card_id>, ...}``.

**Display-only**, like ``_curriculum``: nothing that decides, charges or
credits may import this. Every failure reads as :attr:`Theory.UNKNOWN` (shown
as pending, logged at WARNING) -- cannot check is never "taught". Files are
opened only through :mod:`leetcode_guard._tutor_read` (regular, size-capped);
the one exception to "UNKNOWN" is a torn or undecodable log *line*, which is
skipped and the other lines still count.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from leetcode_guard._curriculum import Blocks, Theory, load_curriculum
from leetcode_guard._read_json import MISSING
from leetcode_guard._tutor_read import read_tutor_bytes, read_tutor_json

if TYPE_CHECKING:
    from leetcode_guard._curriculum import Curriculum, Unit

_logger: Final = logging.getLogger(__name__)

TUTOR_DATA_DIR = Path.home() / ".local" / "share" / "tutor"
"""Read at call time so the test suite can point it away from the real tutor."""

_TAUGHT: Final = "taught"


def _events(data: bytes, path: Path) -> list[object]:
    """Every parseable log line; the rest are skipped with ONE warning.

    A line cut mid-append (a multibyte character split in two included) is the
    normal state of a log a live server writes, so it costs only itself.
    """
    events: list[object] = []
    warned = False
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw.decode("utf-8")))
        except (ValueError, RecursionError) as exc:
            if not warned:
                _logger.warning(
                    "skipping torn line(s) in tutor log %s, first: %s", path, exc
                )
                warned = True
    return events


def _taught(root: Path) -> frozenset[tuple[str, str]] | None:
    """Every ``(subject, card)`` the log says was taught; ``None`` if unreadable."""
    path = root / "log.jsonl"
    data = read_tutor_bytes(path, _logger)
    if data is None:
        return None
    return frozenset(
        (event["s"], event["c"])
        for event in _events(data, path)
        if isinstance(event, dict)
        and event.get("k") == _TAUGHT
        and isinstance(event.get("s"), str)
        and isinstance(event.get("c"), str)
    )


def _module_cards(root: Path, subject: str) -> dict[str, set[str]] | None:
    """Live card ids per module of ``subject``; ``None`` (warned) if unusable."""
    path = root / "subjects" / subject / "cards.json"
    document = read_tutor_json(path, _logger)
    if document is MISSING:
        return None
    if not isinstance(document, dict):
        _logger.warning("tutor cards %s are not an object, theory unknown", path)
        return None
    cards: dict[str, set[str]] = {}
    for card_id, row in document.items():
        module = row.get("module") if isinstance(row, dict) else None
        if not isinstance(module, str):
            _logger.warning("tutor cards %s: %s has no module", path, card_id)
            return None
        if row.get("suspended") is not True:
            cards.setdefault(module, set()).add(card_id)
    return cards


def _state(
    unit: Unit,
    taught: frozenset[tuple[str, str]] | None,
    cards: dict[str, set[str]] | None,
) -> Theory:
    """One mapped unit's state from the two files' contents."""
    if taught is None or cards is None:
        return Theory.UNKNOWN
    done = all(
        cards.get(module)
        and all((unit.subject, card) in taught for card in cards[module])
        for module in unit.modules
    )
    return Theory.DONE if done else Theory.PENDING


def unit_theory(curriculum: Curriculum, root: Path | None = None) -> tuple[Theory, ...]:
    """Each unit's theory state, in unit order.

    Args:
        curriculum: The units and the tutor modules they map to.
        root: The tutor data dir; ``None`` means :data:`TUTOR_DATA_DIR` now.

    Returns:
        One state per unit. No tutor file is opened when no unit maps a module.
    """
    units = curriculum.units
    if not any(unit.subject for unit in units):
        return (Theory.NONE,) * len(units)
    root = TUTOR_DATA_DIR if root is None else root
    taught = _taught(root)
    cards: dict[str, dict[str, set[str]] | None] = {}
    states: list[Theory] = []
    for unit in units:
        if not unit.subject:
            states.append(Theory.NONE)
            continue
        if taught is not None and unit.subject not in cards:
            cards[unit.subject] = _module_cards(root, unit.subject)
        states.append(_state(unit, taught, cards.get(unit.subject)))
    return tuple(states)


def load_blocks() -> Blocks | None:
    """The curriculum with its theory states, or ``None`` when there is none."""
    curriculum = load_curriculum()
    if curriculum is None:
        return None
    return Blocks(curriculum=curriculum, theory=unit_theory(curriculum))
