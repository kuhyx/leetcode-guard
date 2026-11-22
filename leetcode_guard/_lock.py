"""The lock window.

Almost no window code lives here. gatelock owns the per-output surfaces, the X
grab, VT switching, hotplug recovery and cross-app arbitration; this module
supplies the five hooks and the business logic that decides when to let go.

Arming order follows gatelock's rule -- **arm first, render second** -- and one
addition of our own: the network work that produces the suggestion list and the
first probe happens *before* the window is built, off the Tk thread. Fetching
inside a surface builder would mean no window at all when the network is down,
and no window is itself the bypass.

That invariant has one stated exception. **No window is the bypass while the
lock is asserted** -- but :mod:`leetcode_guard._lock_study` stands the assertion
down on request (Open, learn, a SOLVE row's ``?``), releasing the grab: until
2026-08-05 the lock demanded a solve its grabbed browser could not type. Study
mode is explicit, no timeout; both transitions log at warning with elapsed time.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Final

from gatelock import (
    Arbiter,
    GateRoot,
    GrabPolicy,
    LockConfig,
    LockWindow,
    assert_not_under_pytest,
    wait_for_turn,
)
from gatelock.error_report import watch_stalls

from leetcode_guard import _errors
from leetcode_guard import _glyphs as g
from leetcode_guard._constants import (
    POLL_INTERVAL_MS_DEMO,
    POLL_INTERVAL_MS_PRODUCTION,
    RANK_LEETCODE_GUARD,
)
from leetcode_guard._escape_flow import EscapeHatch, build_tracker
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._lock_carrot import CarrotMixin
from leetcode_guard._lock_nudge import NudgeMixin
from leetcode_guard._lock_phase import PhaseReader, unit_rows
from leetcode_guard._lock_poll import PollMixin
from leetcode_guard._lock_release import ReleaseMixin
from leetcode_guard._lock_reveal import RevealMixin
from leetcode_guard._lock_state import EscapeKit, OutageState, RunState
from leetcode_guard._lock_study import StudyMixin
from leetcode_guard._network_incident import build_tracker as build_incident_tracker
from leetcode_guard._poller import PollerSettings, SolvePoller
from leetcode_guard._study_restart import arm_input, wind_down_study
from leetcode_guard._sync import sync_quietly
from leetcode_guard._view import build_guard_view
from leetcode_guard._view_evening import install_demo_close_button
from leetcode_guard._view_group import FrameGroup
from leetcode_guard._view_types import ViewHooks

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import SurfaceInfo

    from leetcode_guard._lock_deps import GuardDeps

_logger: Final = logging.getLogger(__name__)


class LeetcodeGuard(
    PollMixin, CarrotMixin, ReleaseMixin, StudyMixin, NudgeMixin, RevealMixin
):
    """A gatelock consumer that releases when a LeetCode problem is solved.

    ``PollMixin`` comes first and the order is load-bearing. ``StudyMixin``
    declares ``_decision`` and ``ReleaseMixin`` declares ``_release`` as stubs
    that raise, so that they can call them; listing PollMixin last put those
    stubs ahead of the real implementations in the MRO and every construction
    of the guard died on ``NotImplementedError``.
    """

    def __init__(self, *, demo_mode: bool = True, deps: GuardDeps) -> None:
        """Arm the lock.

        Args:
            demo_mode: The default. Uses a local grab, leaves VT switching
                alone and shows a close button, so a demo can never trap the
                developer. ``--production`` opts out.
            deps: Injected collaborators.
        """
        assert_not_under_pytest("the leetcode-guard lock")
        self.deps = deps
        self.frames = FrameGroup()
        config = LockConfig(
            mode="hard",
            # Per-output placement is impossible without it, in demo too.
            overrideredirect=True,
            grab=GrabPolicy(
                kind="local" if demo_mode else "global",
                disable_vt=not demo_mode,
            ),
            app_name="leetcode_guard",
            rank=RANK_LEETCODE_GUARD,
        )
        self.run_state = RunState(
            demo=demo_mode,
            started=time.monotonic(),
            poll_interval=(
                POLL_INTERVAL_MS_DEMO if demo_mode else POLL_INTERVAL_MS_PRODUCTION
            ),
            config=config,
            phases=PhaseReader(deps, demo=demo_mode),
        )

        self.ledger = load_ledger(deps.ledger_path, key_file=deps.key_file)
        self._maybe_seed()

        tracker = build_tracker(deps.escape_path, key_file=deps.key_file)
        incidents = build_incident_tracker(
            deps.seams.incident_path
            if deps.seams.incident_path is not None
            else deps.escape_path.with_name("network_incidents.json"),
            key_file=deps.key_file,
        )
        self.escape = EscapeKit(
            tracker=tracker,
            incidents=incidents,
            hatch=EscapeHatch(tracker, config, on_granted=self.on_escape_granted),
            incident_hatch=EscapeHatch(
                incidents, config, on_granted=self.on_incident_recorded
            ),
        )
        self.outage = OutageState()

        self.root = GateRoot()
        self.root.title("LeetCode Guard" + (" [DEMO]" if demo_mode else ""))

        self.run_state.phases.refresh()  # the first screen is the phase's
        self.model = self.build_model(deps.probe)
        self.start_reveal()
        self.on_reveal(unit_rows(self.model, changed=True))
        # StudyMixin builds ``_study``/``_strip`` lazily: they need the LockWindow.

        arbiter = Arbiter(
            "leetcode_guard",
            RANK_LEETCODE_GUARD,
            grab=self.run_state.config.resolved_grab(),
            disable_vt=self.run_state.config.resolved_disable_vt(),
        )
        arbiter.publish()
        if deps.seams.wait_turn:
            # Published first so lower-ranked lockers queue behind us, then wait
            # with nothing on screen. Never exits: higher rank is "later", not "skip".
            wait_for_turn(arbiter)
        arbiter.acquire_holder()

        self.lock = LockWindow(
            self.root, self.run_state.config, hooks=self, arbiter=arbiter
        )
        self.lock.setup()

        self.poller = SolvePoller(
            self.root,
            PollerSettings(
                interval_ms=self.run_state.poll_interval,
                work=self.check,
                on_result=self.on_poll_result,
                executor=deps.seams.executor,
                on_watch=self.run_state.phases.file_watch,
            ),
        )
        self.poller.start()
        self.start_nudges(deps.seams.nudge_port)
        self._start_carrot_watch()
        arm_input(self.lock, grab=not deps.seams.resume_study)

    # -- gatelock hooks ---------------------------------------------------

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Paint one output. Pure rendering; nothing is fetched or decided."""
        view = build_guard_view(
            parent,
            self.run_state.config,
            self.model,
            output_name=surface.output_name,
            hooks=ViewHooks(
                on_escape=self.open_escape,
                on_open=self.open_problem,
                on_reveal=self.on_reveal,
                on_learn=self.open_learn,
                on_rework=self.open_rework,
            ),
        )
        self.frames.views[surface.output_name] = view
        self.frames.add(surface.output_name, parent)
        if self.run_state.demo:
            install_demo_close_button(parent, self.run_state.config, self.close)

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Drop a monitor that has gone away."""
        self.frames.views.pop(surface.output_name, None)
        self.frames.discard(surface.output_name)

    def on_focus_ready(self, surface: SurfaceInfo | None) -> None:
        """No input field until the hatch opens; ``None``: zero live outputs."""

    def on_callback_error(self) -> None:
        """A Tk callback raised. Say so on screen and keep polling."""
        _logger.exception("a Tk callback raised inside the lock")
        for view in self.frames.views.values():
            # A warning mark in the danger colour; the poller keeps watching.
            view.status_line.configure(
                text=g.BLIND, fg=self.run_state.config.palette.danger
            )

    def on_close(self) -> None:
        """Runs on every exit path, including SIGTERM."""
        # First: study mode restored VT switching directly and cleared
        # gatelock's own ``_vt_disabled`` flag to match. Resuming here puts both
        # back, so ``LockWindow.close``'s restore is not skipped and the
        # machine does not exit with VT switching still disabled.
        wind_down_study(self)  # not _end_study: a restart resumes study
        self._stop_carrot_watch()
        self.stop_nudges()
        self.stop_reveal()
        self.poller.stop()
        if self.deps.write_ledger and self.deps.seams.sync_on_close:
            # Best-effort and last: a sync failure must never abort teardown
            # and leave the screen grabbed.
            sync_quietly(self.deps.ledger_path, key_file=self.deps.key_file)

    def close(self) -> None:
        """Release the lock. Idempotent."""
        if self.run_state.closed:
            return
        self.run_state.closed = True
        self.lock.close()

    def run(self) -> None:
        """Hand control to Tk until the lock releases.

        The stall watch starts here, not at ``GateRoot()``: construction blocks
        Tk on purpose (``wait_for_turn``, the surface build), filed as c890f31a.
        """
        if _errors.SLOT.reporter is not None:
            watch_stalls(self.root, _errors.SLOT.reporter)
        self.lock.run()
