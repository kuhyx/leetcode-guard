"""Guards that cannot verify a solve, plus the network diagnoses that explain why.

Shared by the outage and network-incident lock tests (``test_lock_part3`` to
``test_lock_part5``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, create_guard, probe_of

if TYPE_CHECKING:
    from pathlib import Path


def remote_outage() -> NetworkDiagnosis:
    """Build a diagnosis where the machine is online but LeetCode is down."""
    return NetworkDiagnosis(
        verdict=NetworkVerdict.REMOTE_OUTAGE,
        reason="LeetCode is down",
        anchors_reachable=3,
        addresses=("1.2.3.4",),
    )


def local_offline() -> NetworkDiagnosis:
    """Build a diagnosis where this machine has no internet at all."""
    return NetworkDiagnosis(
        verdict=NetworkVerdict.LOCAL_OFFLINE,
        reason="no internet on this machine",
        anchors_reachable=0,
        addresses=(),
    )


def blind_guard(tmp_path: Path, hmac_key: Path, diagnose):
    """Build a seeded guard whose polls are unverifiable and classifier is due."""
    guard, _ = create_guard(
        tmp_path,
        probe=probe_of(),
        poll_probe=UNVERIFIABLE,
        key_file=hmac_key,
        # An ordinary gating day: seeding settles the day it runs on, so a
        # self-seeding guard is unlocked and none of these outage paths apply.
        seeded=True,
    )
    guard.deps.seams = replace(guard.deps.seams, diagnose=diagnose)
    # Enough consecutive failures that the classifier is due to run.
    guard.poller.state.consecutive_unverifiable = 999
    return guard


def blind_offline(tmp_path: Path, hmac_key: Path):
    """A guard that has been blind long enough, with LOCAL_OFFLINE diagnosed."""
    guard = blind_guard(tmp_path, hmac_key, local_offline)
    guard.on_poll_result(UNVERIFIABLE)
    return guard
