"""Everything the lock needs, in one injectable record.

Split out of ``_lock.py`` for the 250-line cap. It sits in its own module
because both the guard and the mixins it is passed to reference it, and a
module that only holds a value can be imported by any of them without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor
    from pathlib import Path

    from leetcode_guard._auth import AuthState
    from leetcode_guard._leetcode import PostFn
    from leetcode_guard._netcheck import NetworkDiagnosis
    from leetcode_guard._pool_resolve import PoolResolution
    from leetcode_guard._submissions import SolveProbe


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
