"""What the guard does with each probe: seed, decide, paint, release.

Split out of ``_lock.py`` for the 250-line cap, along the seam ``ReleaseMixin``
and ``StudyMixin`` already use. ``_lock.py`` keeps construction, the surface
callbacks and the Tk lifecycle; this is the tick.
"""

from __future__ import annotations

from dataclasses import replace
import logging
import time
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT
from leetcode_guard._daycost import local_today
from leetcode_guard._escape_flow import is_offerable
from leetcode_guard._gate import apply_decision, decide
from leetcode_guard._harvest import commit_harvest, harvest, needs_seeding, seed_ledger
from leetcode_guard._submissions import ProbeStatus, SolveProbe, fetch_recent_ac
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import build_viewmodel

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import EscapeTracker

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._poller import SolvePoller
    from leetcode_guard._viewmodel import ViewModel

_logger: Final = logging.getLogger(__name__)

_UNLOCK_LINGER_MS = 3000
"""How long the "unlocked" screen stays up. Long enough to read, short enough
not to feel like the lock is stuck."""


class PollMixin:
    """The tick half of :class:`~leetcode_guard._lock.LeetcodeGuard`.

    Reads ``_deps``, ``_ledger``, ``_tracker``, ``_started``, ``_outage_note``,
    ``_poller``, ``_views``, ``_model``, ``_closed`` and ``root`` from the
    class it is mixed into, and calls back into the release and study halves.
    Declared rather than assumed, as the other two mixins do: a mixin that
    silently expects attributes is one that breaks on a refactor and says
    nothing until runtime.
    """

    _deps: GuardDeps
    _ledger: Ledger
    _tracker: EscapeTracker
    _started: float
    _outage_note: str | None
    _poller: SolvePoller
    _views: dict[str, Any]
    _model: ViewModel
    _closed: bool
    root: Any
    _blind_seconds: Callable[[], float]
    _blind_for_long_enough: Callable[[], bool]
    _incident_form_due: Callable[[], bool]
    _handle_outage: Callable[[], None]
    _end_study: Callable[[], None]
    clear_outage: Callable[[], None]
    close: Callable[[], None]

    def _maybe_seed(self) -> None:
        """Initialise a brand-new ledger so the first run still gates."""
        if not needs_seeding(self._ledger) and self._deps.write_ledger:
            return
        if not self._deps.write_ledger:
            return
        seed_ledger(
            self._ledger,
            self._deps.probe,
            day=local_today(now=self._deps.moment()),
            now=self._deps.moment(),
            path=self._deps.ledger_path,
            key_file=self._deps.key_file,
        )

    def _decision(self) -> GateDecision:
        """Today's verdict against the current ledger."""
        moment = self._deps.moment()
        return decide(
            self._ledger,
            day=local_today(now=moment),
            now=moment,
            key_file=self._deps.key_file,
        )

    def _build_model(self, probe: SolveProbe) -> ViewModel:
        """Render the current state."""
        model = build_viewmodel(
            self._decision(),
            self._deps.pool,
            self._deps.auth,
            probe,
            checked_at=self._deps.moment(),
            limit=PROBLEM_DISPLAY_LIMIT,
            show_escape=self._should_offer_escape(),
        )
        if self._outage_note is None:
            return model
        return replace(model, notes=(*model.notes, self._outage_note))

    def _should_offer_escape(self) -> bool:
        """Whether the hatch is currently visible."""
        if self._incident_form_due():
            # Not subject to the ordinary budget: this is the offline path's
            # only exit, and refusing it is what made the lock a trap.
            return True
        return is_offerable(
            self._tracker,
            elapsed_seconds=time.monotonic() - self._started,
            # hasattr because the first model is built before the poller
            # exists; treating that as "not blind yet" is correct.
            unverifiable_seconds=self._blind_seconds()
            if hasattr(self, "_poller")
            else 0.0,
        )

    def _check(self) -> SolveProbe:
        """The blocking network call. Runs on the executor, never on Tk."""
        return fetch_recent_ac(self._deps.post, self._deps.username)

    def _on_poll_result(self, probe: SolveProbe | None) -> None:
        """Fold one probe into the ledger and repaint.

        ``None`` means :meth:`_check` *raised*, and it used to return here. That
        skipped both ``state.record`` and the repaint, so a probe that raised
        every tick -- a bad cookie jar, an SSL failure, a resolver exception --
        left ``consecutive_unverifiable`` at zero for ever. The blind-time route
        to the hatch could then never fire and the status line froze at whatever
        it said on startup: a lock with no exit that looked exactly like a
        healthy one. Treating the crash as the unverifiable probe it is costs
        nothing, and a crash is the case that most needs a way out.
        """
        if probe is None:
            _logger.warning(
                "the solve check crashed; counting it as an unverifiable probe "
                "so blind time still accrues and the hatch can still appear"
            )
            probe = SolveProbe(
                status=ProbeStatus.UNVERIFIABLE,
                submissions=(),
                reason="the solve check crashed -- see the log",
            )
        self._poller.state.record(usable=probe.status is ProbeStatus.OK)
        if probe.status is ProbeStatus.OK:
            self.clear_outage()
        elif self._blind_for_long_enough():
            self._handle_outage()
            if self._closed:
                return

        if self._deps.write_ledger:
            moment = self._deps.moment()
            result = harvest(
                self._ledger,
                probe,
                day=local_today(now=moment),
                now=moment,
                key_file=self._deps.key_file,
            )
            commit_harvest(self._ledger, result, self._deps.ledger_path)

        decision = self._decision()
        if not decision.locked:
            if decision.charge is not None and self._deps.write_ledger:
                apply_decision(self._ledger, decision, self._deps.ledger_path)
            self._release(probe)
            return

        self._model = self._build_model(probe)
        apply_viewmodel(self._views.values(), self._model)

    def _release(self, probe: SolveProbe) -> None:
        """Show the unlocked screen briefly, then let go.

        A solve landing mid-study is the *primary* way study mode ends, so the
        lock is put back first: the unlocked screen has to be on a surface that
        is actually mapped, or the good news flashes onto a hidden window and
        the user never sees why the machine came back.
        """
        self._end_study()
        self._model = self._build_model(probe)
        apply_viewmodel(self._views.values(), self._model)
        self.root.after(_UNLOCK_LINGER_MS, self.close)
