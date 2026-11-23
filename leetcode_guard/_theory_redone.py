"""The re-pass credit: a unit passed again after its post-mortem pays +1 per revision.

The tutor's post-mortem (``tutor/postmortem``, ``DOCS-contract-postmortem.md``)
adds or un-teaches cards of a finished unit, which signs ``done: false`` and
sends the unit back to THEORY. Each applied revision is one signed C7 row in
``postmortems/revisions.json``. Passing the unit again pays the usual minute
credits plus ``theory-redone:<subject>:<unit>:<rev>`` (``amount: 1``,
``detail.source: "tutor-theory"``): never a minute credit (no ``theory:<day>:``
prefix) and never a second ``theory-done`` (that id has no revision).

Rules (kuhy, 2026-11-23), all in one poll:

* The C7 row verifies. A missing file is no revision (silent: the normal state
  until the first post-mortem); a forged row is dropped and can only pay less.
* The unit is current when the poll starts or ends (the poll that finishes the
  re-pass usually moves the machine past the unit).
* Every module of the unit was signed ``done: false`` after the revision's
  ``at`` (a re-pass really happened: a ``done: true`` re-signed by a backfill
  or reconcile alone is not one), and its latest row is ``done: true``, later
  than that, signed TODAY. C2 is read strictly, as for the finish credit.
* The id is not in the ledger yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

from leetcode_guard import _tutor_signed
from leetcode_guard._daycost import day_key
from leetcode_guard._phase_inputs import MODULE_STATE
from leetcode_guard._theory_finish import theory_row
from leetcode_guard._tutor_signed import detail_of, signed_rows

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

    from leetcode_guard._ledger import LedgerEntry
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase import PhaseState
    from leetcode_guard._tutor_signed import Row

REDONE_PREFIX: Final = "theory-redone:"
REVISIONS: Final = "postmortems/revisions.json"
REV_KIND: Final = "postmortem_rev"


class Revision(NamedTuple):
    """One verified C7 row."""

    unit: str
    subject: str
    modules: tuple[str, ...]
    rev: int
    at: float

    @property
    def entry_id(self) -> str:
        """The credit's ledger id."""
        return f"{REDONE_PREFIX}{self.subject}:{self.unit}:{self.rev}"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _parse(row: Row) -> Revision | None:
    d = detail_of(row)
    unit, subject, mods, rev = (
        d.get("unit"),
        d.get("subject"),
        d.get("modules"),
        d.get("rev"),
    )
    at = _number(d.get("at"))
    if row.get("kind") != REV_KIND or at is None or not isinstance(rev, int):
        return None
    if not isinstance(unit, str) or not isinstance(subject, str):
        return None
    if not isinstance(mods, list) or not mods or isinstance(rev, bool):
        return None
    return Revision(unit, subject, tuple(str(m) for m in mods), rev, at)


def revisions(key_file: Path | None) -> list[Revision]:
    """Every verified C7 row; none when the file does not exist yet."""
    if not (_tutor_signed.TUTOR_DIR / REVISIONS).is_file():
        return []
    rows = signed_rows(REVISIONS, key_file=key_file) or []
    return [found for found in map(_parse, rows) if found is not None]


def _history(
    rows: list[Row], subject: str, module: str
) -> list[tuple[float, bool, str]]:
    """(``at``, ``done``, ``day``) of the module's C2 rows, oldest first."""
    out = []
    for row in rows:
        d = detail_of(row)
        at, done = _number(d.get("at")), d.get("done")
        if (
            row.get("kind") != "module_state"
            or at is None
            or not isinstance(done, bool)
        ):
            continue
        if d.get("subject") == subject and d.get("module") == module:
            out.append((at, done, str(row.get("day"))))
    return sorted(out, key=lambda item: item[0])


def repassed(rows: list[Row], found: Revision, today: str) -> bool:
    """Whether every module of ``found`` was undone after it and is done again today."""
    for module in found.modules:
        history = _history(rows, found.subject, module)
        undone = [at for at, done, _ in history if not done and at > found.at]
        if not undone or not history:
            return False
        at, done, day = history[-1]
        if not done or day != today or at <= undone[0]:
            return False
    return True


def redone_entry(
    found: Revision, stamp: tuple[date, datetime], key_file: Path | None
) -> LedgerEntry:
    """The signed ``theory-redone`` credit; ``stamp`` is (day, now)."""
    detail = {
        "unit": found.unit,
        "subject": found.subject,
        "rev": str(found.rev),
        "redone": "1",
    }
    return theory_row(found.entry_id, stamp, detail, key_file)


def due_redone(
    ledger: Ledger,
    state: PhaseState,
    before: PhaseState | None,
    *,
    stamp: tuple[date, datetime],
    key_file: Path | None = None,
) -> list[LedgerEntry]:
    """The re-pass credits not minted yet; ``before`` is the phase the poll began in."""
    units = {state.unit} | ({before.unit} if before is not None else set())
    wanted = {
        found.entry_id: found
        for found in revisions(key_file)
        if found.unit in units - {""} and not ledger.has(found.entry_id)
    }
    # C2 is read only when a revision could pay, and strictly: "cannot check" pays none.
    rows = signed_rows(MODULE_STATE, key_file=key_file, strict=True) if wanted else None
    return [
        redone_entry(found, stamp, key_file)
        for found in wanted.values()
        if rows is not None and repassed(rows, found, day_key(stamp[0]))
    ]
