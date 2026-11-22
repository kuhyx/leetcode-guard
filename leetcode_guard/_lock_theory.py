"""The lock's own theory poll: teaching minutes pay while the window is up.

The one-minute harvester stands aside while a lock holds the instance lock, so
without this a day paid by signed tutor minutes alone would stay locked. Called
from ``PollMixin.on_poll_result`` after the solve harvest and before the day is
decided, so a theory credit clears the lock exactly as a solve does.

Split out of ``_lock_poll.py`` for the 250-line cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._daycost import local_today
from leetcode_guard._theory_credit import poll_theory

if TYPE_CHECKING:
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._lock_deps import GuardDeps


def mint_theory(ledger: Ledger, deps: GuardDeps, *, demo: bool) -> None:
    """Mint today's due theory credits into ``ledger`` and save it.

    Never in the demo: its ledger is deleted every run, so polling there would
    mint from kuhy's real minutes and rewrite the live ``theory_phase.json``
    from a phase the demo ledger decided, changing what the tutor may teach.
    ``poll_theory`` never raises, so a theory bug costs the credit, never the
    lock.
    """
    if demo:
        return
    moment = deps.moment()
    poll_theory(
        ledger,
        deps.ledger_path,
        day=local_today(now=moment),
        now=moment,
        key_file=deps.key_file,
    )
