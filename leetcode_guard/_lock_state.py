"""The lock's mutable state, grouped by who changes it.

``LeetcodeGuard`` once held twenty-odd loose attributes. These records keep the
same fields under three names -- the run itself, the escape machinery and the
current outage -- so the guard stays within the lint profile's attribute limit
and each mixin can say which group it touches. A module that only holds values
imports no tkinter and can be reached from any mixin without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gatelock import EscapeTracker, LockConfig

    from leetcode_guard._escape_flow import EscapeHatch
    from leetcode_guard._netcheck import NetworkDiagnosis
    from leetcode_guard._network_incident import IncidentPolicy


@dataclass
class RunState:
    """What one run of the lock is, and whether it is still running."""

    demo: bool
    started: float
    poll_interval: int
    config: LockConfig
    closed: bool = False


@dataclass
class EscapeKit:
    """The two escape paths: the plain hatch and the network-incident one."""

    tracker: EscapeTracker
    incidents: EscapeTracker
    hatch: EscapeHatch
    incident_hatch: EscapeHatch


@dataclass
class OutageState:
    """The classified network outage the lock is currently riding out."""

    diagnosis: NetworkDiagnosis | None = None
    note: str | None = None
    policy: IncidentPolicy | None = None
    since: float | None = None
