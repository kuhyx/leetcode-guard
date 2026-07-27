"""The single network seam.

Every other module in this package takes a :data:`PostFn` and never touches
``requests`` itself. That is what makes 100% branch coverage reachable without
mocking HTTP in thirty places: the fakes are plain functions returning
:class:`GraphQLResult` values.

:func:`post_graphql` never raises. Every failure -- socket, HTTP status, JSON,
GraphQL -- becomes a field on the result, because the caller is a lock window
and an escaping exception there means no window at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Final

import requests

from leetcode_guard._auth import CSRF_KEY, SESSION_KEY, Cookies
from leetcode_guard._constants import (
    GRAPHQL_URL,
    NETWORK_TIMEOUT_SECONDS,
    REFERER,
    USER_AGENT,
)
from leetcode_guard._queries import IDENTITY_QUERY

if TYPE_CHECKING:
    from leetcode_guard._throttle import Throttle

_logger: Final = logging.getLogger(__name__)

_HTTP_OK: Final = 200

_IDENTITY_FIELD: Final = "allQuestionsCount"
"""The field a genuine LeetCode GraphQL response carries. See
:func:`looks_like_leetcode`."""


@dataclass(frozen=True)
class GraphQLResult:
    """One GraphQL response, with every failure mode made explicit.

    Attributes:
        data: The ``data`` object, or ``None``. **A** ``None`` **here is not an
            error and not a negative answer** -- LeetCode replies to an expired
            session with HTTP 200 and a null payload, so callers must classify
            it as "unknown", never as "no".
        errors: GraphQL-level messages, e.g. "That user does not exist.".
        transport_error: Socket, HTTP-status or JSON failure, in plain words.
    """

    data: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()
    transport_error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the response carried usable data."""
        return (
            self.transport_error is None and not self.errors and self.data is not None
        )


PostFn = Callable[[str, dict[str, Any]], GraphQLResult]
"""The seam: ``(query, variables) -> GraphQLResult``."""


@dataclass
class LeetCodeClient:
    """A reusable session plus its limiter, exposed as a :data:`PostFn`.

    One :class:`requests.Session` for the whole process on purpose. The
    endpoint hands out a ``csrftoken`` and a Cloudflare ``_cfuvid`` cookie on
    first contact; rotating identity per request is exactly the pattern bot
    detection scores badly.
    """

    session: requests.Session
    throttle: Throttle
    timeout: float = NETWORK_TIMEOUT_SECONDS

    def post(self, query: str, variables: dict[str, Any]) -> GraphQLResult:
        """Send one document. Signature matches :data:`PostFn`."""
        self.throttle.wait()
        return post_graphql(self.session, query, variables, timeout=self.timeout)


def build_session(cookies: Cookies | None) -> requests.Session:
    """Create the shared session, authenticated when cookies are available.

    Args:
        cookies: Optional credentials. Their only effect is populating
            ``status`` on the pool query.

    Returns:
        A configured session.
    """
    session = requests.Session()
    session.headers.update(
        {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": REFERER,
        }
    )
    if cookies is not None:
        session.cookies.set(SESSION_KEY, cookies.session, domain=".leetcode.com")
        session.cookies.set(CSRF_KEY, cookies.csrf, domain=".leetcode.com")
        session.headers["x-csrftoken"] = cookies.csrf
    return session


def post_graphql(
    session: requests.Session,
    query: str,
    variables: dict[str, Any],
    *,
    timeout: float = NETWORK_TIMEOUT_SECONDS,
) -> GraphQLResult:
    """POST one GraphQL document and classify whatever comes back.

    Args:
        session: The shared session from :func:`build_session`.
        query: A document from :mod:`leetcode_guard._queries`.
        variables: Its variables.
        timeout: Per-request timeout in seconds.

    Returns:
        A result whose fields say exactly what happened. Never raises.
    """
    payload = {"query": query, "variables": variables}
    try:
        response = session.post(GRAPHQL_URL, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        _logger.warning("LeetCode request failed: %s", exc)
        return GraphQLResult(transport_error=f"network error: {exc}")

    if response.status_code != _HTTP_OK:
        _logger.warning("LeetCode returned HTTP %d", response.status_code)
        return GraphQLResult(transport_error=f"HTTP {response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        _logger.warning("LeetCode returned non-JSON: %s", exc)
        return GraphQLResult(transport_error="LeetCode returned non-JSON")

    if not isinstance(body, dict):
        _logger.warning(
            "LeetCode returned a JSON %s, not an object", type(body).__name__
        )
        return GraphQLResult(transport_error="LeetCode returned a non-object JSON body")

    errors = _extract_errors(body)
    if errors:
        _logger.warning("LeetCode rejected the query: %s", "; ".join(errors))
        return GraphQLResult(errors=errors)

    data = body.get("data")
    if not isinstance(data, dict):
        # Not an error path: this is what an expired session looks like.
        return GraphQLResult()
    return GraphQLResult(data=data)


def looks_like_leetcode(
    session: requests.Session, *, timeout: float = NETWORK_TIMEOUT_SECONDS
) -> bool:
    """Whether we are really talking to LeetCode.

    The control probe behind :mod:`leetcode_guard._netcheck`'s tampering check.
    A captive portal or hijacking resolver answers with HTTP 200 from a
    genuinely public address, so only the *response* can tell them apart from
    the real site.

    Probes the GraphQL endpoint, not the homepage: a plain GET of
    ``https://leetcode.com/`` returns HTTP 403 (Cloudflare), so the homepage
    version of this check failed on healthy connections and would have blamed
    the user for LeetCode's own downtime.

    A portal returns HTML, which is not a well-formed GraphQL response, so it
    fails here as intended. Any failure reports "not LeetCode", routing to the
    stricter policy -- the safe direction.
    """
    result = post_graphql(session, IDENTITY_QUERY, {}, timeout=timeout)
    if result.data is None:
        _logger.warning(
            "identity probe got no GraphQL data (%s)",
            result.transport_error or "; ".join(result.errors) or "empty payload",
        )
        return False
    return _IDENTITY_FIELD in result.data


def _extract_errors(body: dict[str, Any]) -> tuple[str, ...]:
    """Pull human-readable messages out of a GraphQL ``errors`` array."""
    raw = body.get("errors")
    if not isinstance(raw, list) or not raw:
        return ()
    messages = []
    for item in raw:
        if isinstance(item, dict):
            message = item.get("message")
            messages.append(str(message) if message is not None else str(item))
        else:
            messages.append(str(item))
    return tuple(messages)
