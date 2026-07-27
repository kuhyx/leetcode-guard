"""User-configurable settings and the wired-up network client.

Small on purpose: the only genuinely configurable thing is the LeetCode
username, and the only thing worth assembling in one place is the
authenticated-or-not client the rest of the app talks through.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._auth import AuthState, load_cookies
from leetcode_guard._constants import (
    COOKIES_FILE,
    DEFAULT_USERNAME,
    NETWORK_TIMEOUT_SECONDS,
    THROTTLE_MIN_INTERVAL_SECONDS,
    USERNAME_FILE,
)
from leetcode_guard._leetcode import LeetCodeClient, PostFn, build_session
from leetcode_guard._throttle import Throttle

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


def load_username(path: Path | None = None) -> str:
    """Read the configured LeetCode handle, falling back to the default.

    A blank or unreadable file falls back rather than failing: the wrong
    username produces a loud, specific GraphQL error later ("That user does not
    exist."), which is a far better diagnostic than a crash at startup.

    ``None`` rather than ``USERNAME_FILE`` as the default: a default argument is
    evaluated once at import, so baking the path in would make the constant
    unpatchable and every test would read the real config directory.
    """
    if path is None:
        path = USERNAME_FILE
    if not path.exists():
        # The normal state, not a fault: the default is correct for this
        # machine and the file only exists if someone overrode it. Warning here
        # would print on every single run.
        _logger.debug("no username file at %s -- using %r", path, DEFAULT_USERNAME)
        return DEFAULT_USERNAME
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _logger.warning(
            "cannot read the username from %s (%s) -- using %r",
            path,
            exc,
            DEFAULT_USERNAME,
        )
        return DEFAULT_USERNAME
    if not text:
        _logger.warning("%s is empty -- using the default username", path)
        return DEFAULT_USERNAME
    return text.splitlines()[0].strip()


@dataclass(frozen=True)
class Client:
    """Everything needed to talk to LeetCode for one run."""

    post: PostFn
    auth: AuthState
    username: str


def build_client(
    *,
    username_file: Path | None = None,
    cookies_file: Path | None = None,
    timeout: float = NETWORK_TIMEOUT_SECONDS,
) -> Client:
    """Assemble the network client for this run.

    Cookies are loaded here and, if present, attached to the session. Their
    absence is not an error and is never propagated as one -- it only changes
    whether already-solved problems can be hidden from the suggestion list.

    The path defaults are resolved at call time, for the reason spelled out in
    :func:`load_username`.
    """
    auth = load_cookies(COOKIES_FILE if cookies_file is None else cookies_file)
    session = build_session(auth.cookies)
    client = LeetCodeClient(
        session=session,
        throttle=Throttle(THROTTLE_MIN_INTERVAL_SECONDS),
        timeout=timeout,
    )
    return Client(
        post=client.post,
        auth=auth,
        username=load_username(
            USERNAME_FILE if username_file is None else username_file
        ),
    )
