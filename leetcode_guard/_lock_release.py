"""Every way the lock lets go other than actually solving something.

Split out of ``_lock.py`` to stay under the repo's 400-line-per-file cap, and
it turns out to be the right seam anyway: this is the whole "what if they
cannot solve one today" surface in one place, which is the part most worth
reading before changing.

Two exits, and they cost differently on purpose:

* **A LeetCode outage** settles the day for free. Not the user's fault and not
  something they can fix, so charging them for it would be punishing downtime.
* **The escape hatch** settles the day too, but at the price of a written
  justification against a real budget.

Both write a full-cost charge, so the balance goes negative and the debt
carries: a forgiven day is not a free one, and tomorrow still costs full price.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Final

from leetcode_guard._constants import UNVERIFIABLE_HATCH_SECONDS
from leetcode_guard._daycost import local_today
from leetcode_guard._gate import settle_day
from leetcode_guard._ledger import SOURCE_ESCAPE, SOURCE_NETWORK_INCIDENT, SOURCE_OUTAGE
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._netcheck import classify
from leetcode_guard._network_incident import decide_policy

if TYPE_CHECKING:
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._lock_state import EscapeKit, OutageState, RunState
    from leetcode_guard._netcheck import NetworkDiagnosis
    from leetcode_guard._poller import SolvePoller
    from leetcode_guard._submissions import SolveProbe
    from leetcode_guard._view_group import FrameGroup

_logger: Final = logging.getLogger(__name__)


class ReleaseMixin:
    """Outage classification and the escape hatch, mixed into the lock.

    Reads ``_poller``, ``_deps``, ``_ledger``, ``_run``, ``_escape``,
    ``_outage`` and ``_frames`` from the class it is mixed into, and calls
    ``_release``.

    Those collaborators are declared below rather than left implicit. A mixin
    that silently assumes attributes exist is the kind that breaks when the
    host class is refactored and says nothing until runtime; declaring them
    makes the contract checkable.
    """

    _poller: SolvePoller[SolveProbe]
    _run: RunState
    _deps: GuardDeps
    _ledger: Ledger
    _escape: EscapeKit
    _outage: OutageState
    _frames: FrameGroup

    def _release(self, probe: SolveProbe) -> None:
        """Provided by the host class."""
        raise NotImplementedError

    def _blind_seconds(self) -> float:
        """How long every check in a row has failed."""
        return (
            self._poller.state.consecutive_unverifiable * self._run.poll_interval / 1000
        )

    def _blind_for_long_enough(self) -> bool:
        """Whether it is time to work out *why* we are blind."""
        return self._blind_seconds() >= UNVERIFIABLE_HATCH_SECONDS

    def _handle_outage(self) -> None:
        """Classify the failure once, then apply the matching policy.

        Classified once and remembered. Re-probing three anchors and a DNS
        lookup on every tick would be noise, and the answer does not change
        between ticks -- a network that is down stays down.
        """
        if self._outage.diagnosis is not None:
            return
        seam = self._deps.seams.diagnose
        diagnose = seam if seam is not None else classify
        diagnosis: NetworkDiagnosis = diagnose()
        self._outage.diagnosis = diagnosis
        policy = decide_policy(diagnosis, self._escape.incidents)
        self._outage.note = policy.message

        if policy.unlock_now:
            self._settle_and_release(SOURCE_OUTAGE)
            return
        if policy.require_form:
            # The screen promises "write down what happened and it unlocks".
            # Recording the policy is what makes that promise true -- without
            # it the offline path had no exit at all once the ordinary escape
            # budget was spent, which is a trapped keyboard.
            self._outage.policy = policy
            self._outage.since = time.monotonic()

    def clear_outage(self) -> None:
        """Forget the diagnosis once LeetCode answers again.

        Without this the banner outlives the outage and keeps telling the user
        they have no internet long after they reconnected.
        """
        if self._outage.diagnosis is None:
            return
        _logger.info("LeetCode is reachable again -- clearing the outage banner")
        self._outage.diagnosis = None
        self._outage.note = None
        self._outage.policy = None
        self._outage.since = None

    def _incident_form_due(self) -> bool:
        """Whether the mandatory network-incident form may be submitted yet."""
        policy = self._outage.policy
        if policy is None or self._outage.since is None:
            return False
        return time.monotonic() - self._outage.since >= policy.wait_seconds

    def _on_incident_recorded(self, reason: str) -> None:
        """Settle the day once the written network account is accepted."""
        _logger.warning("unlocking via a recorded network incident: %s", reason)
        self._settle_and_release(SOURCE_NETWORK_INCIDENT)

    def _open_escape(self) -> None:
        """Show whichever form applies on the primary surface.

        The network-incident form takes precedence: when the gate is blind
        because *this machine* is offline, that is the sanctioned way out and
        it must not consume the ordinary escape budget.
        """
        hatch = (
            self._escape.incident_hatch
            if self._incident_form_due()
            else self._escape.hatch
        )
        if hatch.open or self._escape.hatch.open or self._escape.incident_hatch.open:
            return
        first = next(iter(self._frames), None)
        if first is None:
            # Legitimate: with zero live outputs the lock still holds the grab
            # and has nowhere to draw. Say so rather than crash the lock.
            _logger.warning("no surface available to show the escape form on")
            return
        hatch.show(first)

    def _on_escape_granted(self, reason: str) -> None:
        """Settle today without spending credits, then unlock."""
        _logger.warning("unlocking via the escape hatch: %s", reason)
        self._settle_and_release(SOURCE_ESCAPE)

    def _settle_and_release(self, source: str) -> None:
        """Mark today paid for by ``source`` and let the lock go."""
        if self._deps.write_ledger:
            moment = self._deps.moment()
            entry = charge_entry(
                local_today(now=moment),
                now=moment,
                source=source,
                key_file=self._deps.key_file,
            )
            settle_day(self._ledger, entry, self._deps.ledger_path)
        self._release(self._deps.probe)
