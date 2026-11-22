"""Everything the lock needs, in one injectable record.

Split out of ``_lock.py`` for the 250-line cap. It sits in its own module
because both the guard and the mixins it is passed to reference it, and a
module that only holds a value can be imported by any of them without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor
    from pathlib import Path

    from leetcode_guard._auth import AuthState
    from leetcode_guard._leetcode import PostFn
    from leetcode_guard._netcheck import NetworkDiagnosis
    from leetcode_guard._phase_view import PhaseView
    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._submissions import SolveProbe


@dataclass
class GuardSeams:
    """The lock's optional behaviour and test seams, grouped off ``GuardDeps``.

    Every field defaults to the production behaviour, so the CLI sets only
    what differs and a test sets only the seam it drives.
    """

    incident_path: Path | None = None
    executor: Executor | None = None
    now: Any = None
    sync_on_close: bool = False
    """Push the ledger to the sync repo when the lock lets go.

    Off by default so tests and demos never touch the network on teardown;
    production turns it on."""

    nudge_port: int | None = None
    """Where to listen for the browser's "Accepted" doorbell (``_nudge_server``).

    ``None`` opens no port, so tests never bind a real socket; the CLI sets it.
    """

    wait_turn: bool = True
    """Whether to queue behind higher-ranked lockers before arming.

    Off in tests, which would otherwise consult a real arbiter directory."""

    resume_study: bool = False
    """Arm without taking the grab: a restart that resumes study mode.

    The caller must then enter study (``_study_restart.resume_study``), which
    arms the grab itself if that fails."""

    diagnose: Callable[[], NetworkDiagnosis] | None = None
    """Network classifier. ``None`` means use the real one."""

    phase: Callable[[], PhaseView] | None = None
    """The current unit and screen (SPEC C5), read once per poll (``_lock_phase``).

    Set by the CLI to the rules side's read-only getter; ``None`` paints today's
    list. It may raise: the lock keeps the last screen it read."""


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
    key_file: Path | None = None
    write_ledger: bool = True
    seams: GuardSeams = field(default_factory=GuardSeams)

    def moment(self) -> datetime:
        """Current time, injectable."""
        now = self.seams.now
        return now() if now is not None else datetime.now().astimezone()
