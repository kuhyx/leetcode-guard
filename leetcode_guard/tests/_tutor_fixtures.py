"""Signed tutor rows (contracts C1 and C2), signed by the TUTOR's library.

Shapes measured 2026-11-22 from the real ``~/.local/share/tutor/ledger.json``
(658 rows, e.g. ``20261121-172327-7e3a-m1``: ``kind``, ``entry_id``, ``day``,
``created_at`` float, ``detail`` with ``session_id``, ``block``, ``minutes``,
``active_seconds``, ``ended_at`` float, ``checks_passed``, ``checks_total``).
``detail.subject``/``detail.module`` (C1) and ``module_state.json`` (C2) were
measured the same day from the tutor's own writers in
``~/data/claude-scratch/lc-stage4/wt-tutor`` (commits 706dcb4: only teaching
rows carry the C1 keys; 65bf1be: signed C2 flips, ``entry_id``
``state:<subject>:<module>:<n>``, ``n`` counting that module's rows). The
untouched rows they wrote are ``tutor_measured_2026-11-22.json``, checked by
``test_tutor_measured.py``; these builders follow that shape.

Rows are signed with ``earned_time.entry_signature`` -- what the tutor itself
calls (``tutor/credit.py``) -- so the guard's gatelock-based verification is
checked against the other library, not against itself.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

import earned_time

from leetcode_guard import _tutor_signed

if TYPE_CHECKING:
    from pathlib import Path

ALGO = "leetcode-easy-algorithms-in-typescript"


def signed(row: dict[str, object], key_file: Path) -> dict[str, object]:
    """``row`` with the tutor's ``hmac``."""
    return {
        **row,
        "hmac": earned_time.entry_signature(row, key_file.read_bytes().strip()),
    }


def teaching_row(
    entry_id: str,
    minutes: int,
    *,
    ended: datetime,
    key_file: Path,
    where: tuple[str, str | None] = (ALGO, "prefix-sums"),
) -> dict[str, object]:
    """A signed C1 credit row for (subject, module); module ``None`` = a review row."""
    subject, module = where
    detail: dict[str, object] = {
        "session_id": entry_id.rsplit("-m", 1)[0],
        "block": 1,
        "minutes": minutes,
        "active_seconds": minutes * 60.0,
        "ended_at": ended.timestamp(),
        "checks_passed": 0,
        "checks_total": 0,
    }
    if module is not None:
        detail |= {"subject": subject, "module": module}
    row = {
        "kind": "credit",
        "entry_id": entry_id,
        "day": ended.date().isoformat(),
        "created_at": ended.timestamp(),
        "detail": detail,
    }
    return signed(row, key_file)


def review_row(
    entry_id: str,
    minutes: int,
    *,
    ended: datetime,
    key_file: Path,
    where: tuple[str, str] | None = (ALGO, "b1"),
) -> dict[str, object]:
    """A signed C1 review-minute row.

    Tagged (the tutor's new shape, 2026-11-22): ``detail.subject``,
    ``detail.module`` of the card whose review completed the minute, and
    ``detail.activity == "review"``. ``where=None`` is the old, untagged shape:
    none of the three.
    """
    row = teaching_row(
        entry_id, minutes, ended=ended, key_file=key_file, where=(ALGO, None)
    )
    row.pop("hmac")
    detail = row["detail"]
    assert isinstance(detail, dict)
    if where is not None:
        detail |= {"subject": where[0], "module": where[1], "activity": "review"}
    return signed(row, key_file)


def state_row(
    module: str, *, done: bool, at: float, key_file: Path, n: int = 1
) -> dict[str, object]:
    """A signed C2 ``module_state`` row, the module's ``n``-th."""
    row = {
        "kind": "module_state",
        "entry_id": f"state:{ALGO}:{module}:{n}",
        "day": datetime.fromtimestamp(at, tz=UTC).astimezone().date().isoformat(),
        "detail": {"subject": ALGO, "module": module, "done": done, "at": at},
    }
    return signed(row, key_file)


def write_tutor(name: str, rows: list[object]) -> Path:
    """Write ``{"entries": rows}`` (C1 has no ``version``; C2 has 1) to the scratch dir."""
    path = _tutor_signed.TUTOR_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    document: dict[str, object] = {"entries": rows}
    if name == "module_state.json":
        document = {"version": 1, **document}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
