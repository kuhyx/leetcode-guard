"""What happens when the gate cannot see LeetCode *and* it is our own fault.

Your rule: if the network problem is on this machine, stay locked until it
comes back -- with an automatic release after about five minutes plus an
obligatory written account of what happened.

Built on ``gatelock``'s escape core, with two deliberate departures from how
the ordinary hatch is tuned:

**Budgets never exhaust.** A multi-day ISP outage must not brick the machine,
so the rolling limits are set far above any plausible real use. The deterrent
here is the wait and the written record, not running out of allowance.

**The escalating wait is capped.** Doubling from five minutes reaches about
2.7 hours by the sixth incident, which a genuinely dead connection would hit
inside a week. Past the cap it stops being a deterrent and becomes a
punishment schedule that outruns real outages, so it stops at thirty minutes.

This is separate from :mod:`leetcode_guard._escape_flow`, which keeps real
budgets and covers everything else. Mixing them would let a week of bad wifi
consume the allowance meant for "I genuinely cannot do this today".
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from gatelock import EscapeDraft, EscapePolicy, EscapeTracker

from leetcode_guard._constants import (
    HISTORY_REVIEW_COUNT,
    JUSTIFICATION_MIN_CHARS,
    NETWORK_INCIDENT_BUDGET,
    NETWORK_INCIDENT_LOCKOUT_CAP_SECONDS,
    NETWORK_INCIDENT_LOCKOUT_SECONDS,
)
from leetcode_guard._netcheck import NetworkDiagnosis, NetworkVerdict

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

NETWORK_INCIDENT_POLICY: Final = EscapePolicy(
    name="network-incident",
    label="Network incident",
    budget_per_7_days=NETWORK_INCIDENT_BUDGET,
    budget_per_30_days=NETWORK_INCIDENT_BUDGET,
    budget_per_90_days=NETWORK_INCIDENT_BUDGET,
    lockout_seconds=NETWORK_INCIDENT_LOCKOUT_SECONDS,
    justification_min_chars=JUSTIFICATION_MIN_CHARS,
    history_review_count=HISTORY_REVIEW_COUNT,
)


def build_tracker(path: Path, *, key_file: Path | None = None) -> EscapeTracker:
    """Build the incident tracker over its own history file."""
    tracker = EscapeTracker(NETWORK_INCIDENT_POLICY, path, key_file=key_file)
    tracker.load()
    return tracker


def lockout_seconds(tracker: EscapeTracker) -> int:
    """How long to wait before the form may be submitted.

    Capped, for the reason in the module docstring.
    """
    return min(tracker.compute_lockout_seconds(), NETWORK_INCIDENT_LOCKOUT_CAP_SECONDS)


@dataclass(frozen=True)
class IncidentPolicy:
    """What a diagnosis means for the lock right now."""

    unlock_now: bool
    """Release immediately, with no form. Only ever a remote outage."""

    require_form: bool
    """Hold until a written account is accepted."""

    wait_seconds: int
    """How long the form stays disabled."""

    message: str
    """Shown verbatim on the lock surface."""


def decide_policy(
    diagnosis: NetworkDiagnosis, tracker: EscapeTracker
) -> IncidentPolicy:
    """Turn a network diagnosis into what the lock should do.

    Args:
        diagnosis: From :func:`leetcode_guard._netcheck.classify`.
        tracker: The incident history, for the escalating wait.

    Returns:
        The policy. Note the asymmetry, which is the whole point: a problem
        LeetCode caused releases the day for free, and a problem *this machine*
        caused costs a wait and an explanation.
    """
    if diagnosis.verdict is NetworkVerdict.REMOTE_OUTAGE:
        _logger.error(
            "unlocking because LeetCode is unreachable while this machine is "
            "online: %s",
            diagnosis.reason,
        )
        return IncidentPolicy(
            unlock_now=True,
            require_form=False,
            wait_seconds=0,
            message=(
                f"{diagnosis.reason}\n"
                "Today has been settled automatically. This is recorded."
            ),
        )

    if diagnosis.verdict is NetworkVerdict.ONLINE:
        return IncidentPolicy(
            unlock_now=False,
            require_form=False,
            wait_seconds=0,
            message="LeetCode is reachable again -- still watching for a solve.",
        )

    wait = lockout_seconds(tracker)
    minutes = max(1, wait // 60)
    return IncidentPolicy(
        unlock_now=False,
        require_form=True,
        wait_seconds=wait,
        message=(
            f"{diagnosis.reason}\n"
            f"Reconnect and the gate carries on as normal. If you cannot, the "
            f"machine unlocks after {minutes} minute(s) -- but only once you "
            "have written down what happened to the network."
        ),
    )


def record_incident(
    tracker: EscapeTracker, draft: EscapeDraft, diagnosis: NetworkDiagnosis
) -> str | None:
    """Validate and store one incident.

    Returns:
        A user-facing complaint, or ``None`` when it was accepted.
    """
    complaint = tracker.validate(draft)
    if complaint is not None:
        return complaint
    if not tracker.record(draft):
        _logger.error("failed to record a network incident")
        return "Could not record the incident -- try again."
    _logger.warning(
        "network incident recorded (%s): %s", diagnosis.verdict.value, draft.reason
    )
    return None
