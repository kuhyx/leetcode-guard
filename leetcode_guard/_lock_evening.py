"""The evening-chain lock window (``--evening``, see ``_evening``).

A subclass rather than a flag threaded through the ordinary lock, so the
morning gate's code path is untouched. Three differences:

* ``gatelock.watch_credit`` watches the ledger and takes the window down the
  moment the leetcode ``charge`` row lands, whichever process wrote it (this
  lock's own poll, the one-minute harvest, a phone sync).
* The only other way out is the end-evening control: exit code
  :data:`~leetcode_guard._evening.EXIT_END_EVENING`.
* Nothing else may lift it. The ordinary stand-downs (``decide`` calls an
  escaped day settled; an outage forgives the day) do not pay the rung, and
  closing on them would exit 0 with the rung unpaid, so the orchestrator would
  relaunch the gate in a loop. They are held, and the escape hatch -- which
  settles with exactly such a charge -- is not offered.

No morning-session carrot poll either: the contract ignores it. The rank stays
:data:`~leetcode_guard._constants.RANK_LEETCODE_GUARD` (150, below
screen-locker's 200), which is what the contract asks of evening gates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from gatelock import watch_credit

from leetcode_guard._breakglass import breakglass_lines
from leetcode_guard._constants import EXIT_OK
from leetcode_guard._evening import EXIT_END_EVENING, STOP_COMMAND, evening_paid
from leetcode_guard._lock import LeetcodeGuard
from leetcode_guard._view_evening import install_end_evening_button

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import SurfaceInfo

    from leetcode_guard._lock_deps import GuardDeps
    from leetcode_guard._submissions import SolveProbe

_logger: Final = logging.getLogger(__name__)

CREDIT_POLL_MS: Final = 3_000
"""Well inside the 10 s an open window may take to notice a credit."""


class EveningGuard(LeetcodeGuard):
    """A production lock that ends when the rung is paid or kuhy ends the evening."""

    exit_code: int = EXIT_OK

    def __init__(self, *, demo_mode: bool = False, deps: GuardDeps) -> None:
        """Arm the lock, then the credit watch (the Tk loop is not running yet)."""
        super().__init__(demo_mode=demo_mode, deps=deps)
        watch_credit(
            self.root,
            [deps.ledger_path],
            self.rung_paid,
            self.on_evening_credit,
            poll_ms=CREDIT_POLL_MS,
        )

    def rung_paid(self) -> bool:
        """Whether today's leetcode rung is verifiably paid (unreadable: no)."""
        return evening_paid(
            self.deps.ledger_path,
            key_file=self.deps.key_file,
            now=self.deps.moment(),
        )

    def on_evening_credit(self) -> None:
        """The charge landed: the normal unlocked stand-down."""
        self._release(self._last_probe)

    def _release(self, probe: SolveProbe) -> None:
        """Let go only for a paid rung."""
        if not self.rung_paid():
            _logger.warning("evening: stand-down held; the leetcode rung is unpaid")
            return
        super()._release(probe)

    def should_offer_escape(self) -> bool:
        """Never: the hatch's charge pays nothing; the end control is the exit."""
        return False

    def _start_carrot_watch(self) -> None:
        """No morning-session poll in an evening run."""

    def build_surface(self, parent: tk.Misc, surface: SurfaceInfo) -> None:
        """The ordinary surface plus the end-evening control, from t=0."""
        super().build_surface(parent, surface)
        config = self.run_state.config
        install_end_evening_button(parent, config, self.end_evening)
        # The ordinary line stops leetcode-guard.service, which does not own
        # this process; a dead break-glass command is worse than none.
        view = self.frames.views[surface.output_name]
        lines = breakglass_lines(config, STOP_COMMAND)
        view.decor.breakglass.configure(text="\n".join(lines))

    def end_evening(self) -> None:
        """Kuhy ends the evening: close, exit 10, the chain stops."""
        _logger.warning("evening: ended from the lock window; the chain stops")
        self.exit_code = EXIT_END_EVENING
        self.close()
