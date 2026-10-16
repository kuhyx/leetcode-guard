"""Which sick days switch this gate off (the ``sickdays`` 0.2.0 keep set).

A sick day may keep some lockers active. This gate stands down only when the
day is sick **and** ``leetcode`` is not kept; a kept day is an ordinary day in
every respect -- price, debt, workday penalty. Every caller that used to ask
"is it a sick day?" for this gate asks :func:`leetcode_stands_down` instead,
past days included, so a kept past day with no charge is owed like any other.

Both helpers look ``sickdays.stands_down`` up at call time, never import it by
name: the test suite and the ``scripts/`` harnesses replace it on the module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sickdays

if TYPE_CHECKING:
    from datetime import date


def leetcode_stands_down(day: date) -> bool:
    """Whether this gate is off on ``day``: sick, and leetcode not kept."""
    return sickdays.stands_down(sickdays.LOCKER_LEETCODE, day)


def alarm_stands_down(day: date) -> bool:
    """Whether the wake-alarm switch is off on ``day``.

    A missed ring on such a day is not a miss, so its workday penalty is void.
    """
    return sickdays.stands_down(sickdays.LOCKER_ALARM, day)
