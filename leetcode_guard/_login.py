"""Store LeetCode cookies, but only after LeetCode has accepted them.

The session JWT lasts about two weeks and there is no refresh flow, so it dies
routinely. What made that expensive was not the expiry -- it was that nothing
noticed. :func:`leetcode_guard._auth.load_cookies` reported "signed in" on the
strength of two non-empty strings existing in a file, and the surface repeated
that claim for five days while every solved-state check silently came back
``null``.

So the write is gated on evidence. A cookie pair is saved only if a live query
using it comes back with a non-null ``status`` -- the one observation that
distinguishes a working session from an expired one, since the public pool
query answers dead cookies with HTTP 200 and a complete payload full of nulls
rather than with an error.

The values are read from **stdin**, never from argv: a session token in
``~/.zsh_history`` is a credential leak that outlives the session itself.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import TYPE_CHECKING, Final

from leetcode_guard._auth import CSRF_KEY, SESSION_KEY, Cookies
from leetcode_guard._leetcode import build_session, post_graphql
from leetcode_guard._live_solved import parse_status
from leetcode_guard._queries import STATUS_QUERY, status_variables

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

_PROBE_SLUG: Final = "two-sum"
"""The problem the verification probe asks about.

Any free problem would do. This one is chosen because it is the oldest and
most-solved on the site, so it is the least likely ever to be withdrawn or
turned premium -- the probe must fail because the *cookies* are bad, never
because the problem went away.
"""

_OWNER_ONLY: Final = stat.S_IRUSR | stat.S_IWUSR


def verify_cookies(cookies: Cookies, *, timeout: float) -> tuple[bool, str]:
    """Ask LeetCode whether it recognises this session.

    Returns:
        Whether the cookies work, and a sentence explaining the verdict. A
        ``null`` status is the failure that matters: the request succeeded and
        the payload parsed, and LeetCode simply did not know who was asking.
    """
    session = build_session(cookies)
    result = post_graphql(
        session, STATUS_QUERY, status_variables(_PROBE_SLUG), timeout=timeout
    )
    if result.transport_error is not None:
        return False, f"could not reach LeetCode: {result.transport_error}"
    if result.errors:
        return False, f"LeetCode rejected the query: {'; '.join(result.errors)}"
    if parse_status(result.data) is None:
        return False, (
            "LeetCode answered but did not recognise the session -- status came "
            "back null, which is what an expired or mistyped cookie looks like"
        )
    return True, "LeetCode recognised the session"


def write_cookies(path: Path, cookies: Cookies) -> bool:
    """Persist the pair atomically, readable only by its owner.

    Returns:
        Whether the write succeeded. The file holds a live credential, so the
        0600 mode is set on the temporary file *before* any secret reaches the
        disk -- creating it world-readable and chmod-ing afterwards leaves a
        window where another local user can read the token.
    """
    payload = {SESSION_KEY: cookies.session, CSRF_KEY: cookies.csrf}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name,
            suffix=".tmp",
            delete=False,
        ) as handle:
            Path(handle.name).chmod(_OWNER_ONLY)
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        Path(temp_name).replace(path)
    except OSError as exc:
        _logger.warning("could not write cookies to %s: %s", path, exc)
        return False
    return True


def _prompt(reader: Callable[[], str], label: str) -> str:
    """Read one value, without echoing it into any command line."""
    print(f"Paste {label} (DevTools -> Application -> Cookies): ", end="")
    sys.stdout.flush()
    return reader().strip()


def login(
    path: Path,
    *,
    timeout: float,
    reader: Callable[[], str] = sys.stdin.readline,
) -> bool:
    """Prompt for cookies, verify them live, and save only if they work.

    Returns:
        Whether a verified pair was written.
    """
    session = _prompt(reader, SESSION_KEY)
    csrf = _prompt(reader, CSRF_KEY)
    if not session or not csrf:
        print("\nboth values are required -- nothing was written")
        return False

    cookies = Cookies(session=session, csrf=csrf)
    print("\nverifying with LeetCode...")
    ok, reason = verify_cookies(cookies, timeout=timeout)
    if not ok:
        print(f"REFUSED: {reason}")
        print("nothing was written -- any existing cookie file is untouched")
        return False

    if not write_cookies(path, cookies):
        print(f"verified, but could not write {path}")
        return False
    print(f"{reason}; saved to {path}")
    return True
