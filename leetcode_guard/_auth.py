"""Optional LeetCode cookies.

Auth is a pure enhancement here and the code must keep it that way. Cookies do
exactly one thing: populate ``status`` on the pool query so already-solved
problems can be hidden from the suggestion list. They are never consulted for
solve detection, so an absent, corrupt or expired session can only ever make
the suggestions worse -- never prevent an unlock.

``LEETCODE_SESSION`` is a JWT that expires in roughly two weeks with no refresh
flow, so expiry is the normal case rather than the exception.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

SESSION_KEY: Final = "LEETCODE_SESSION"
CSRF_KEY: Final = "csrftoken"


@dataclass(frozen=True)
class Cookies:
    """A usable LeetCode session."""

    session: str
    csrf: str


@dataclass(frozen=True)
class AuthState:
    """What the rest of the app is allowed to know about auth.

    Attributes:
        cookies: The credentials, if any were loadable.
        note: A user-facing sentence explaining the state, rendered on the lock
            surface. Never a bare flag: "already-solved problems are not being
            filtered" is actionable, ``authenticated=False`` is not.
    """

    cookies: Cookies | None
    note: str

    @property
    def present(self) -> bool:
        """Whether credentials were loaded."""
        return self.cookies is not None


_NO_FILE_NOTE: Final = (
    "Not signed in -- problems you have already solved are NOT filtered out "
    "of this list."
)


def load_cookies(path: Path) -> AuthState:
    """Read cookies from ``path``, degrading to unauthenticated on any problem.

    Every failure mode returns an :class:`AuthState` rather than raising: this
    runs on the lock's startup path, where an exception means no window.

    Args:
        path: JSON file holding ``LEETCODE_SESSION`` and ``csrftoken``.

    Returns:
        The loaded state, authenticated or not.
    """
    if not path.exists():
        return AuthState(cookies=None, note=_NO_FILE_NOTE)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("cannot read cookies from %s: %s", path, exc)
        return AuthState(
            cookies=None,
            note=f"Cookie file {path} is unreadable -- continuing signed out.",
        )
    if not isinstance(raw, dict):
        _logger.warning("cookie file %s is not a JSON object", path)
        return AuthState(
            cookies=None,
            note=f"Cookie file {path} is not a JSON object -- continuing signed out.",
        )
    session = raw.get(SESSION_KEY)
    csrf = raw.get(CSRF_KEY)
    if (
        not isinstance(session, str)
        or not isinstance(csrf, str)
        or not session
        or not csrf
    ):
        _logger.warning(
            "cookie file %s is missing %s and/or %s", path, SESSION_KEY, CSRF_KEY
        )
        return AuthState(
            cookies=None,
            note=(
                f"Cookie file {path} is missing {SESSION_KEY}/{CSRF_KEY} "
                "-- continuing signed out."
            ),
        )
    return AuthState(
        cookies=Cookies(session=session, csrf=csrf),
        note="Signed in -- already-solved problems are hidden from this list.",
    )


def rejected_state() -> AuthState:
    """The state to switch to once LeetCode has refused the stored cookies.

    Distinguished from "no cookies" because the fix differs: a missing file
    needs one created, an expired JWT needs the two values re-pasted.
    """
    return AuthState(
        cookies=None,
        note=(
            "LeetCode rejected the stored session (it expires about every two "
            "weeks) -- already-solved problems are NOT filtered out. Re-paste "
            f"{SESSION_KEY} and {CSRF_KEY} to fix."
        ),
    )
