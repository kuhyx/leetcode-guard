"""Ask LeetCode, right now, which of these problems are already solved.

The suggestion list used to be filtered entirely from stored data: the pool
cache's ``status`` column, written up to seven days earlier. That is wrong in
the one direction that matters -- a problem solved since the cache was written
still looks unsolved -- and on 2026-08-14 it put a problem solved two days
earlier at the top of the list.

So the displayed problems are verified live, on every run.

**Bounded on purpose.** Only the handful about to be shown are checked, not all
four thousand. Re-paging the whole authenticated pool costs 41 requests on the
path that runs *before* the lock window is built, and LeetCode answers a rate
limit with HTTP 200 and a null payload -- the same signature as the expired
session this check exists to catch. Hammering it to be thorough is a way to
manufacture the very bug being fixed. Checking the ten problems on screen
answers the actual question ("do not show me something I have solved") at a
tenth of the cost.

**Never a source of "not solved".** ``status`` is per-session: ``null`` when
signed out, and an expired session is indistinguishable from a signed-out one
except by that ``null``. So this module can only ever *add* to what is known
from the ledger. A failed check leaves the ledger's answer standing rather than
overriding it -- the same three-valued discipline as
:mod:`leetcode_guard._submissions`, for the same reason: "cannot check" is not
"not solved".
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._queries import STATUS_QUERY, status_variables

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leetcode_guard._leetcode import PostFn

_logger: Final = logging.getLogger(__name__)

_FIELD: Final = "question"
SOLVED_STATUS: Final = "ac"


@dataclass(frozen=True)
class LiveSolved:
    """What a live sweep established, and how much of it it managed."""

    solved: frozenset[str] = frozenset()
    """Slugs LeetCode confirmed as accepted. Positive evidence only."""

    checked: int = 0
    """Problems whose request completed and whose payload parsed."""

    recognised: int = 0
    """Problems that came back with a non-null status.

    Strictly fewer than ``checked``, and the gap is not an error: measured
    against a live session, LeetCode returns ``null`` for a problem the user has
    never *attempted*, and ``"notac"`` only once there is a failed submission on
    record. So a null is a real answer here, not silence -- it just happens to
    be the same token an expired session returns for everything.
    """

    attempted: int = 0
    """Problems the sweep tried to check."""

    @property
    def complete(self) -> bool:
        """Whether every attempted problem answered."""
        return self.checked == self.attempted

    @property
    def signed_in(self) -> bool:
        """Whether the sweep learned anything at all.

        Deliberately keyed on requests completing rather than on statuses being
        non-null. The tempting version -- "no non-null status means a dead
        cookie" -- is wrong against real data: a signed-in user browsing
        suggestions they have never opened gets an all-null sweep too, and
        treating that as a dead session made the lock announce "could not check
        solved-state" while holding a perfectly good cookie.

        A genuinely dead session is caught one layer up instead, by
        ``--login`` refusing to store cookies that cannot produce a non-null
        status for a problem chosen because it is not null.
        """
        return self.checked > 0


def usable_payload(data: object) -> bool:
    """Whether LeetCode returned a ``question`` envelope we could read.

    Separate from :func:`parse_status` because a ``null`` status inside a valid
    envelope is an *answer* ("never attempted"), while a missing envelope is
    silence. Collapsing the two made every sweep of never-opened problems look
    like an expired session.
    """
    return isinstance(data, dict) and isinstance(data.get(_FIELD), dict)


def parse_status(data: object) -> str | None:
    """Read one ``question`` payload's status, or ``None`` if unusable.

    ``None`` covers both "malformed" and "signed out", deliberately: neither is
    evidence about whether the problem is solved, so callers must not be able
    to tell them apart and act on it.
    """
    if not isinstance(data, dict):
        return None
    question = data.get(_FIELD)
    if not isinstance(question, dict):
        return None
    status = question.get("status")
    if not isinstance(status, str) or not status:
        return None
    return status


def check_solved(post: PostFn, slugs: Iterable[str]) -> LiveSolved:
    """Ask LeetCode which of ``slugs`` the current session has solved.

    One request per slug, so callers must pass only what they are about to
    display. Never raises: a slug that errors is left unchecked, which means
    the ledger's answer for it stands.

    Args:
        post: The network seam.
        slugs: Problems to verify, in display order.

    Returns:
        What was established. ``solved`` is positive evidence only.
    """
    wanted = list(slugs)
    solved: set[str] = set()
    checked = 0
    recognised = 0
    for slug in wanted:
        result = post(STATUS_QUERY, status_variables(slug))
        if result.transport_error is not None:
            _logger.warning(
                "live solved-check for %s failed: %s", slug, result.transport_error
            )
            continue
        if result.errors:
            _logger.warning(
                "live solved-check for %s rejected: %s", slug, "; ".join(result.errors)
            )
            continue
        if not usable_payload(result.data):
            # Malformed beyond recognition -- not even the envelope was there.
            continue
        checked += 1
        status = parse_status(result.data)
        if status is not None:
            recognised += 1
        if status == SOLVED_STATUS:
            solved.add(slug)
    if wanted and checked == 0:
        _logger.warning(
            "live solved-check learned nothing about %d problems -- LeetCode is "
            "unreachable or rate-limiting; falling back to the ledger",
            len(wanted),
        )
    return LiveSolved(
        solved=frozenset(solved),
        checked=checked,
        recognised=recognised,
        attempted=len(wanted),
    )
