"""The lock window.

Almost no window code lives here. gatelock owns the per-output surfaces, the X
grab, VT switching, hotplug recovery and cross-app arbitration; this module
supplies the five hooks and the business logic that decides when to let go.

Arming order follows gatelock's rule -- **arm first, render second** -- and one
addition of our own: the network work that produces the suggestion list and the
first probe happens *before* the window is built, off the Tk thread. Fetching
inside a surface builder would mean no window at all when the network is down,
and no window is itself the bypass.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import logging
import time
import tkinter as tk
from typing import TYPE_CHECKING, Any, Final

from gatelock import (
    Arbiter,
    GateRoot,
    LockConfig,
    LockWindow,
    assert_not_under_pytest,
)

from leetcode_guard._constants import (
    POLL_INTERVAL_MS_DEMO,
    POLL_INTERVAL_MS_PRODUCTION,
    RANK_LEETCODE_GUARD,
    SUGGESTION_COUNT,
)
from leetcode_guard._daycost import local_today
from leetcode_guard._escape_flow import EscapeHatch, build_tracker, is_offerable
from leetcode_guard._gate import GateDecision, apply_decision, decide
from leetcode_guard._harvest import commit_harvest, harvest, needs_seeding, seed_ledger
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._lock_release import ReleaseMixin
from leetcode_guard._network_incident import (
    build_tracker as build_incident_tracker,
)
from leetcode_guard._poller import SolvePoller
from leetcode_guard._queue import wait_for_turn
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac
from leetcode_guard._sync import sync_quietly
from leetcode_guard._view import build_guard_view
from leetcode_guard._view_group import FrameGroup
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import ViewModel, build_viewmodel

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor
    from pathlib import Path

    from gatelock import SurfaceInfo

    from leetcode_guard._auth import AuthState
    from leetcode_guard._leetcode import PostFn
    from leetcode_guard._netcheck import NetworkDiagnosis
    from leetcode_guard._network_incident import IncidentPolicy
    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._submissions import SolveProbe

_logger: Final = logging.getLogger(__name__)

_UNLOCK_LINGER_MS = 3000
"""How long the "unlocked" screen stays up. Long enough to read, short enough
not to feel like the lock is stuck."""


@dataclass
class GuardDeps:
    """Everything the lock needs, injected so tests never patch globals."""

    ledger_path: Path
    escape_path: Path
    post: PostFn
    username: str
    auth: AuthState
    pool: PoolResolution
    probe: SolveProbe
    incident_path: Path | None = None
    key_file: Path | None = None
    write_ledger: bool = True
    executor: Executor | None = None
    now: Any = None
    sync_on_close: bool = False
    """Push the ledger to the sync repo when the lock lets go.

    Off by default so tests and demos never touch the network on teardown;
    production turns it on."""

    wait_turn: bool = True
    """Whether to queue behind higher-ranked lockers before arming.

    Off in tests, which would otherwise consult a real arbiter directory."""

    diagnose: Callable[[], NetworkDiagnosis] | None = None
    """Network classifier. ``None`` means use the real one."""

    def moment(self) -> datetime:
        """Current time, injectable."""
        return self.now() if self.now is not None else datetime.now().astimezone()


class LeetcodeGuard(ReleaseMixin):
    """A gatelock consumer that releases when a LeetCode problem is solved."""

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
        )
        self._views[surface.output_name] = view
        self._frames.add(surface.output_name, parent)
        if self._demo:
            self._install_demo_close_button(parent)

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
        self._poller.stop()
        if self._deps.write_ledger and self._deps.sync_on_close:
            # Best-effort and last: a sync failure must never abort teardown
            # and leave the screen grabbed.
            sync_quietly(self._deps.ledger_path, key_file=self._deps.key_file)

    # -- internals --------------------------------------------------------

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
            limit=SUGGESTION_COUNT,
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
        """Fold one probe into the ledger and repaint."""
        if probe is None:
            return
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
        """Show the unlocked screen briefly, then let go."""
        self._model = self._build_model(probe)
        apply_viewmodel(self._views.values(), self._model)
        self.root.after(_UNLOCK_LINGER_MS, self.close)

    def _install_demo_close_button(self, parent: tk.Misc) -> None:
        """The escape that makes a demo safe to run.

        Installed on the **surface**, not on the root. With
        ``overrideredirect=True`` the root is a full-screen backdrop and
        gatelock's per-output Toplevels sit on top of it, so a button placed on
        the root is drawn behind them and is invisible and unclickable. Caught
        by screenshotting the demo rather than by any test -- which is exactly
        why the demo gets screenshotted.
        """
        button = tk.Button(
            parent,
            text="X Close Demo",
            fg=self._config.on_fill,
            bg=self._config.danger,
            command=self.close,
            relief="flat",
        )
        button.place(x=10, y=10)

    def close(self) -> None:
        """Release the lock. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._lock.close()

    def run(self) -> None:
        """Hand control to Tk until the lock releases."""
        self._lock.run()
