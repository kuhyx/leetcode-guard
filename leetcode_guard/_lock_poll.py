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

from leetcode_guard._daycost import local_today
from leetcode_guard._difficulty_resolve import resolve_probe
from leetcode_guard._escape_flow import is_offerable
from leetcode_guard._gate import apply_decision
from leetcode_guard._gate_today import decide_today
from leetcode_guard._harvest import (
    SeedStamp,
    commit_harvest,
    harvest,
    needs_seeding,
    seed_ledger,
)
from leetcode_guard._ledger_io import solved_slugs
from leetcode_guard._submissions import ProbeStatus, SolveProbe, fetch_recent_ac
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource

if TYPE_CHECKING:
    from collections.abc import Callable

    from leetcode_guard._gate import GateDecision
    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._lock_state import EscapeKit, OutageState, RunState
    from leetcode_guard._poller import SolvePoller
    from leetcode_guard._view_group import FrameGroup
    from leetcode_guard._viewmodel import ViewModel

_logger: Final = logging.getLogger(__name__)

_UNLOCK_LINGER_MS = 3000
"""How long the "unlocked" screen stays up. Long enough to read, short enough
not to feel like the lock is stuck."""


class PollMixin:
    """The tick half of :class:`~leetcode_guard._lock.LeetcodeGuard`.

    Reads ``_deps``, ``_ledger``, ``_escape``, ``_outage``, ``_run``,
    ``_poller``, ``_frames``, ``_model`` and ``root`` from the
    class it is mixed into, and calls back into the release and study halves.
    Declared rather than assumed, as the other two mixins do: a mixin that
    silently expects attributes is one that breaks on a refactor and says
    nothing until runtime.
    """

    deps: GuardDeps
    ledger: Ledger
    escape: EscapeKit
    outage: OutageState
    run_state: RunState
    poller: SolvePoller
    frames: FrameGroup
    model: ViewModel
    root: Any
    _blind_seconds: Callable[[], float]
    _blind_for_long_enough: Callable[[], bool]
    incident_form_due: Callable[[], bool]
    _handle_outage: Callable[[], None]
    _end_study: Callable[[], None]
    _end_burst: Callable[[], None]
    refresh_strip: Callable[[], None]
    _last_probe: SolveProbe
    clear_outage: Callable[[], None]
    close: Callable[[], None]

    def _maybe_seed(self) -> None:
        """Initialise a brand-new ledger so the first run still gates."""
        if not needs_seeding(self.ledger) and self.deps.write_ledger:
            return
        if not self.deps.write_ledger:
            return
        seed_ledger(
            self.ledger,
            self.deps.probe,
            stamp=SeedStamp(
                day=local_today(now=self.deps.moment()),
                now=self.deps.moment(),
                key_file=self.deps.key_file,
            ),
            path=self.deps.ledger_path,
        )

    def decision(self) -> GateDecision:
        """Today's verdict against the current ledger."""
        moment = self.deps.moment()
        day = local_today(now=moment)
        return decide_today(
            self.ledger,
            day=day,
            now=moment,
            key_file=self.deps.key_file,
            demo=self.run_state.demo,
        )

    def _build_model(self, probe: SolveProbe) -> ViewModel:
        """Render the current state."""
        model = build_viewmodel(
            self.decision(),
            ViewSource(
                self.deps.pool,
                self.deps.auth,
                # Every unsolved problem: the surface scrolls (``_view_scroll``).
                limit=len(self.deps.pool.problems),
                solved_slugs=self._solved_slugs(probe),
            ),
            probe,
            checked_at=self.deps.moment(),
            show_escape=self.should_offer_escape(),
        )
        if self.outage.note is None:
            return model
        return replace(model, notes=(*model.notes, self.outage.note))

    def _solved_slugs(self, probe: SolveProbe) -> frozenset[str]:
        """Everything known to be solved right now, from both sources.

        The union, for the reason ``_cli`` already unions them when the pool is
        first resolved: the ledger survives an expired session but only ever
        saw what the recent-AC feed returned, and the demo deletes its ledger
        on every run. Probing alone would lose the seeded history; the ledger
        alone lags a solve by one harvest, and an unverifiable probe harvests
        nothing at all.
        """
        return solved_slugs(self.ledger) | frozenset(
            item.title_slug for item in probe.submissions
        )

    def should_offer_escape(self) -> bool:
        """Whether the hatch is currently visible."""
        if self.incident_form_due():
            # Not subject to the ordinary budget: this is the offline path's
            # only exit, and refusing it is what made the lock a trap.
            return True
        return is_offerable(
            self.escape.tracker,
            elapsed_seconds=time.monotonic() - self.run_state.started,
            # hasattr because the first model is built before the poller
            # exists; treating that as "not blind yet" is correct.
            unverifiable_seconds=self._blind_seconds()
            if hasattr(self, "poller")
            else 0.0,
        )

    def check(self) -> SolveProbe:
        """The blocking network call. Runs on the executor, never on Tk."""
        probe = fetch_recent_ac(self.deps.post, self.deps.username)
        if self.deps.write_ledger:
            # Executor thread, before the credit is harvested: a Medium solve
            # must already price as 2 when ``_decision`` runs on the Tk thread.
            moment = self.deps.moment()
            resolve_probe(
                probe,
                post=self.deps.post,
                now=moment,
                key_file=self.deps.key_file,
            )
        return probe

    def on_poll_result(self, probe: SolveProbe | None) -> None:
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
        usable = probe.status is ProbeStatus.OK
        if usable or not self.poller.last_was_poke:
            # A failed *extra* probe is not blind time: blind seconds are
            # counted in poll intervals, so letting a burst of nudges count
            # would buy the escape hatch in seconds.
            self.poller.state.record(usable=usable)
        if probe.status is ProbeStatus.OK:
            self.clear_outage()
        elif self._blind_for_long_enough():
            self._handle_outage()
            if self.run_state.closed:
                return

        if self.deps.write_ledger:
            moment = self.deps.moment()
            result = harvest(
                self.ledger,
                probe,
                day=local_today(now=moment),
                now=moment,
                key_file=self.deps.key_file,
            )
            commit_harvest(self.ledger, result, self.deps.ledger_path)
            if result.gained:
                self._end_burst()

        decision = self.decision()
        if not decision.locked:
            if decision.charge is not None and self.deps.write_ledger:
                apply_decision(self.ledger, decision, self.deps.ledger_path)
            self._release(probe)
            return

        self._last_probe = probe
        self.model = self._build_model(probe)
        apply_viewmodel(self.frames.views.values(), self.model)
        self.refresh_strip()

    def _release(self, probe: SolveProbe) -> None:
        """Show the unlocked screen briefly, then let go.

        A solve landing mid-study is the *primary* way study mode ends, so the
        lock is put back first: the unlocked screen has to be on a surface that
        is actually mapped, or the good news flashes onto a hidden window and
        the user never sees why the machine came back.
        """
        self._end_study()
        self.model = self._build_model(probe)
        apply_viewmodel(self.frames.views.values(), self.model)
        self.root.after(_UNLOCK_LINGER_MS, self.close)
