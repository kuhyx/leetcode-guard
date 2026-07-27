"""Tests for the network seam.

The only module in the suite that patches ``requests``. Every failure mode has
to become a field rather than an exception, because the caller is a lock window
where an escaping exception means no window at all.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from leetcode_guard._auth import Cookies
from leetcode_guard._leetcode import (
    GraphQLResult,
    LeetCodeClient,
    build_session,
    looks_like_leetcode,
    post_graphql,
)
from leetcode_guard._throttle import Throttle


class FakeResponse:
    """Minimal stand-in for :class:`requests.Response`."""

    def __init__(
        self, status_code: int = 200, body: Any = None, *, raises: bool = False
    ) -> None:
        self.status_code = status_code
        self._body = body
        self._raises = raises

    def json(self) -> Any:
        if self._raises:
            message = "no JSON"
            raise ValueError(message)
        return self._body


class FakeSession:
    """Records the request and returns a scripted response."""

    def __init__(self, response: Any = None, *, error: Exception | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: Any, timeout: float) -> Any:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._error is not None:
            raise self._error
        return self._response


def test_ok_result_carries_data():
    session = FakeSession(FakeResponse(body={"data": {"x": 1}}))

    result = post_graphql(session, "query", {"a": 1})

    assert result.ok
    assert result.data == {"x": 1}
    assert session.calls[0]["json"] == {"query": "query", "variables": {"a": 1}}


def test_network_exception_becomes_transport_error():
    session = FakeSession(error=requests.ConnectionError("boom"))

    result = post_graphql(session, "q", {})

    assert not result.ok
    assert result.transport_error is not None
    assert "boom" in result.transport_error


def test_non_200_becomes_transport_error():
    session = FakeSession(FakeResponse(status_code=503))

    result = post_graphql(session, "q", {})

    assert result.transport_error == "HTTP 503"


def test_non_json_body_becomes_transport_error():
    session = FakeSession(FakeResponse(raises=True))

    result = post_graphql(session, "q", {})

    assert result.transport_error == "LeetCode returned non-JSON"


def test_non_object_json_body_is_rejected():
    session = FakeSession(FakeResponse(body=["not", "an", "object"]))

    result = post_graphql(session, "q", {})

    assert result.transport_error == "LeetCode returned a non-object JSON body"


def test_graphql_errors_are_extracted():
    session = FakeSession(
        FakeResponse(body={"errors": [{"message": "That user does not exist."}]})
    )

    result = post_graphql(session, "q", {})

    assert result.errors == ("That user does not exist.",)
    assert not result.ok


def test_error_entries_without_a_message_are_stringified():
    session = FakeSession(FakeResponse(body={"errors": [{"code": 7}, "plain"]}))

    result = post_graphql(session, "q", {})

    assert len(result.errors) == 2
    assert "7" in result.errors[0]
    assert result.errors[1] == "plain"


def test_error_entry_with_null_message_falls_back_to_the_whole_entry():
    session = FakeSession(FakeResponse(body={"errors": [{"message": None}]}))

    result = post_graphql(session, "q", {})

    assert "message" in result.errors[0]


@pytest.mark.parametrize("errors", [[], "not-a-list", None])
def test_empty_or_malformed_errors_array_is_ignored(errors: Any):
    session = FakeSession(FakeResponse(body={"errors": errors, "data": {"x": 1}}))

    result = post_graphql(session, "q", {})

    assert result.ok


def test_null_data_is_not_an_error_and_not_a_negative():
    """The single most important behaviour in this module: an expired session
    replies HTTP 200 with a null payload, and callers must classify that as
    "unknown", never as "nothing solved"."""
    session = FakeSession(FakeResponse(body={"data": None}))

    result = post_graphql(session, "q", {})

    assert result.data is None
    assert result.errors == ()
    assert result.transport_error is None
    assert not result.ok


def test_build_session_sets_headers_without_cookies():
    session = build_session(None)

    assert session.headers["User-Agent"].startswith("Mozilla/5.0")
    assert "x-csrftoken" not in session.headers


def test_build_session_attaches_cookies_and_csrf_header():
    session = build_session(Cookies(session="sess", csrf="tok"))

    assert session.headers["x-csrftoken"] == "tok"


def test_client_throttles_then_posts():
    slept: list[float] = []
    clock = {"t": 0.0}

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["t"] = seconds

    throttle = Throttle(1.0, now=lambda: clock["t"], sleep=sleep)
    session = FakeSession(FakeResponse(body={"data": {"x": 1}}))
    client = LeetCodeClient(session=session, throttle=throttle, timeout=3.0)

    assert client.post("q", {}).data == {"x": 1}
    client.post("q", {})

    assert slept == [1.0]
    assert session.calls[0]["timeout"] == 3.0


def test_result_ok_requires_all_three_conditions():
    assert not GraphQLResult(data={"a": 1}, errors=("bad",)).ok
    assert not GraphQLResult(data={"a": 1}, transport_error="down").ok
    assert GraphQLResult(data={"a": 1}).ok


def identity_session(body):
    """A session whose GraphQL POST returns ``body``."""
    return FakeSession(FakeResponse(body=body))


def test_the_identity_probe_accepts_a_real_graphql_response():
    session = identity_session({"data": {"allQuestionsCount": [{"count": 4003}]}})

    assert looks_like_leetcode(session)


def test_the_identity_probe_rejects_a_captive_portal():
    """A portal answers HTTP 200 from a genuinely public IP, but with HTML --
    which is not a well-formed GraphQL response."""
    session = FakeSession(FakeResponse(raises=True))

    assert not looks_like_leetcode(session)


def test_the_identity_probe_rejects_a_response_without_the_expected_field():
    session = identity_session({"data": {"somethingElse": 1}})

    assert not looks_like_leetcode(session)


def test_the_identity_probe_rejects_a_null_payload():
    session = identity_session({"data": None})

    assert not looks_like_leetcode(session)


def test_the_identity_probe_reports_a_network_failure_as_not_leetcode():
    """Failing to the stricter policy is the safe direction."""
    session = FakeSession(error=requests.ConnectionError("down"))

    assert not looks_like_leetcode(session)


def test_the_identity_probe_does_not_fetch_the_homepage():
    """A plain GET of https://leetcode.com/ returns HTTP 403 (Cloudflare), so
    a homepage probe reports "not LeetCode" on a healthy connection -- which
    would blame the user for LeetCode's own downtime."""
    session = identity_session({"data": {"allQuestionsCount": []}})

    looks_like_leetcode(session)

    assert session.calls[0]["url"].endswith("/graphql/")
