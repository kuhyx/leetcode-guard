"""The lock window.

Almost no window code lives here. gatelock owns the per-output surfaces, the X
grab, VT switching, hotplug recovery and cross-app arbitration; this module
supplies the five hooks and the business logic that decides when to let go.

Arming order follows gatelock's rule -- **arm first, render second** -- and one
addition of our own: the network work that produces the suggestion list and the
first probe happens *before* the window is built, off the Tk thread. Fetching
inside a surface builder would mean no window at all when the network is down,
and no window is itself the bypass.

That last invariant now has a stated exception, and it is worth reading before
changing anything here. **No window is the bypass while the lock is asserted**
-- but :mod:`leetcode_guard._lock_study` can stand the assertion down on
request, releasing the grab so the user can actually reach a problem. Until
2026-08-05 the rule was absolute, and the result was a lock demanding a solve it
had itself made impossible: the browser needed to produce one could not receive
a keystroke. Study mode is an explicit, user-initiated, logged release of
assertion, with no timeout, and both transitions log at warning with elapsed
time so the journal always says how long the machine was open.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Final

from gatelock import (
    Arbiter,
    GateRoot,
    LockConfig,
    LockWindow,
    assert_not_under_pytest,
    wait_for_turn,
)

from leetcode_guard._constants import (
    POLL_INTERVAL_MS_DEMO,
    POLL_INTERVAL_MS_PRODUCTION,
    RANK_LEETCODE_GUARD,
)
from leetcode_guard._escape_flow import EscapeHatch, build_tracker
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._lock_poll import PollMixin
from leetcode_guard._lock_release import ReleaseMixin
from leetcode_guard._lock_study import StudyMixin
from leetcode_guard._network_incident import (
    build_tracker as build_incident_tracker,
)
from leetcode_guard._poller import SolvePoller
from leetcode_guard._sync import sync_quietly
from leetcode_guard._view import build_guard_view, install_demo_close_button
from leetcode_guard._view_group import FrameGroup

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import SurfaceInfo

    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._netcheck import NetworkDiagnosis
    from leetcode_guard._network_incident import IncidentPolicy

_logger: Final = logging.getLogger(__name__)


class LeetcodeGuard(PollMixin, ReleaseMixin, StudyMixin):
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
        self._deps = deps
        self._demo = demo_mode
        self._views: dict[str, Any] = {}
        self._frames = FrameGroup()
        self._started = time.monotonic()
        self._poll_interval = (
            POLL_INTERVAL_MS_DEMO if demo_mode else POLL_INTERVAL_MS_PRODUCTION
        )

        self._ledger = load_ledger(deps.ledger_path, key_file=deps.key_file)
        self._maybe_seed()

        self._config = LockConfig(
            mode="hard",
            # Per-output placement is impossible without it, in demo too.
            overrideredirect=True,
            grab="local" if demo_mode else "global",
            disable_vt=not demo_mode,
            app_name="leetcode_guard",
            rank=RANK_LEETCODE_GUARD,
        )
        self._tracker = build_tracker(deps.escape_path, key_file=deps.key_file)
        self._incidents = build_incident_tracker(
            deps.incident_path
            if deps.incident_path is not None
            else deps.escape_path.with_name("network_incidents.json"),
            key_file=deps.key_file,
        )
        self._incident_hatch = EscapeHatch(
            self._incidents, self._config, on_granted=self._on_incident_recorded
        )
        self._diagnosis: NetworkDiagnosis | None = None
        self._outage_note: str | None = None
        self._incident_policy: IncidentPolicy | None = None
        self._outage_since: float | None = None
        self._hatch = EscapeHatch(
            self._tracker, self._config, on_granted=self._on_escape_granted
        )

        self.root = GateRoot()
        self.root.title("LeetCode Guard" + (" [DEMO]" if demo_mode else ""))

        self._model = self._build_model(deps.probe)
        self._closed = False
        # Built lazily by StudyMixin: the session needs the LockWindow, which
        # does not exist until further down this method.
        self._study = None
        self._strip = None

        arbiter = Arbiter(
            "leetcode_guard",
            RANK_LEETCODE_GUARD,
            grab=self._config.resolved_grab(),
            disable_vt=self._config.resolved_disable_vt(),
        )
        arbiter.publish()
        if deps.wait_turn:
            # Published first so anything lower-ranked queues behind us in
            # turn, then wait with nothing on screen. Never exits here: a
            # higher-ranked locker means "later", never "skip".
            wait_for_turn(arbiter)
        arbiter.acquire_holder()

        self._lock = LockWindow(self.root, self._config, hooks=self, arbiter=arbiter)
        self._lock.setup()

        self._poller = SolvePoller(
            self.root,
            interval_ms=self._poll_interval,
            work=self._check,
            on_result=self._on_poll_result,
            executor=deps.executor,
        )
        self._poller.start()
        self._lock.grab_input()

    # -- gatelock hooks ---------------------------------------------------

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """Paint one output. Pure rendering; nothing is fetched or decided."""
        view = build_guard_view(
            parent,
            self._config,
            self._model,
            output_name=surface.output_name,
            on_escape=self._open_escape,
            on_open=self._open_problem,
        )
        self._views[surface.output_name] = view
        self._frames.add(surface.output_name, parent)
        if self._demo:
            install_demo_close_button(parent, self._config, self.close)

    def teardown_surface(self, surface: SurfaceInfo) -> None:
        """Drop a monitor that has gone away."""
        self._views.pop(surface.output_name, None)
        self._frames.discard(surface.output_name)

    def on_focus_ready(self, surface: SurfaceInfo | None) -> None:
        """Nothing to focus: the lock has no input field until the hatch opens.

        ``surface`` may be ``None`` -- that is the zero-live-outputs case,
        where the lock correctly holds the grab and shows nothing.
        """

    def on_callback_error(self) -> None:
        """A Tk callback raised. Say so on screen and keep polling."""
        _logger.exception("a Tk callback raised inside the lock")
        for view in self._views.values():
            view.status_line.configure(text="Something went wrong -- still watching.")

    def on_close(self) -> None:
        """Runs on every exit path, including SIGTERM."""
        # First: study mode restored VT switching directly and cleared
        # gatelock's own ``_vt_disabled`` flag to match. Resuming here puts both
        # back, so ``LockWindow.close``'s restore is not skipped and the
        # machine does not exit with VT switching still disabled.
        self._end_study()
        self._poller.stop()
        if self._deps.write_ledger and self._deps.sync_on_close:
            # Best-effort and last: a sync failure must never abort teardown
            # and leave the screen grabbed.
            sync_quietly(self._deps.ledger_path, key_file=self._deps.key_file)

    # -- internals --------------------------------------------------------
    def close(self) -> None:
        """Release the lock. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._lock.close()

    def run(self) -> None:
        """Hand control to Tk until the lock releases."""
        self._lock.run()
