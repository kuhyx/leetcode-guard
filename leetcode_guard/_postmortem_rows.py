"""One post-mortem revision, shaped into the rows the status app draws.

Tolerant by design: a wrong-typed field reads as ``None`` (unknown) or an
empty string, a non-object row is dropped, and nothing here raises on a
report's content. Display-only, like :mod:`leetcode_guard._postmortem_view`.
"""

from __future__ import annotations

from typing import Any, Final

FINDING_CAP: Final = 400
"""Characters of a finding kept; the snapshot is pushed every minute."""

FRONT_CAP: Final = 200
"""Characters of a card front kept."""

_ELLIPSIS: Final = "…"
_PAIR: Final = 2

Row = dict[str, Any]


def clip(value: object, cap: int) -> str:
    """``value`` as text no longer than ``cap``; a cut ends in an ellipsis."""
    if not isinstance(value, str):
        return ""
    if len(value) <= cap:
        return value
    return value[: cap - len(_ELLIPSIS)] + _ELLIPSIS


def count(value: object) -> int | None:
    """A non-negative int (not a bool), else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def pair(value: object) -> list[int] | None:
    """A ``[k, n]`` rate, else ``None``."""
    if not isinstance(value, list) or len(value) != _PAIR:
        return None
    k, n = (count(item) for item in value)
    if k is None or n is None:
        return None
    return [k, n]


def objects(value: object) -> list[Row]:
    """The object entries of a list; anything else is empty."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def strings(value: object) -> list[str]:
    """The string entries of a list; anything else is empty."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def problem_row(row: Row) -> Row:
    """One grid row: tries, minutes, one-shot, phase and the finding."""
    phase = row.get("phase")
    return {
        "slug": clip(row.get("slug"), FRONT_CAP),
        "tries": count(row.get("tries")),
        "minutes": count(row.get("minutes")),
        "one_shot": row.get("one_shot") is True,
        "phase": phase if phase in {"pre", "post"} else None,
        "finding": clip(row.get("finding"), FINDING_CAP),
    }


def _chip(kind: str, front: object, finding: object, used_by: object = None) -> Row:
    return {
        "kind": kind,
        "front": clip(front, FRONT_CAP),
        "finding": clip(finding, FINDING_CAP),
        "used_by": strings(used_by),
    }


def _reasons(applied: object) -> dict[str, object]:
    """Suspension reasons by card id, from the applied block."""
    if not isinstance(applied, dict):
        return {}
    return {
        str(item.get("id")): item.get("reason")
        for item in objects(applied.get("suspended"))
    }


def card_chips(revision: Row) -> list[Row]:
    """New, edited, suspended, then kept cards; unchanged cards are not chips."""
    cards = objects(revision.get("cards"))
    reasons = _reasons(revision.get("applied"))
    chips = [
        _chip("new", card.get("front"), card.get("why"))
        for card in objects(revision.get("new_cards"))
    ]
    chips += [
        _chip("edited", card.get("new_front") or card.get("front"), card.get("finding"))
        for card in cards
        if card.get("change") == "edit"
    ]
    chips += [
        _chip(
            "suspended",
            card.get("front"),
            reasons.get(str(card.get("id"))) or card.get("finding"),
        )
        for card in cards
        if card.get("change") == "suspend"
    ]
    chips += [
        _chip("kept", card.get("front"), card.get("finding"), card.get("used_by"))
        for card in cards
        if card.get("change") == "kept"
    ]
    return chips
