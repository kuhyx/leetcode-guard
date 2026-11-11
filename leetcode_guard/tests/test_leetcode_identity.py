"""The LeetCode identity probe: a real GraphQL answer, not a portal or a 403.

Split from :mod:`leetcode_guard.tests.test_leetcode` for the file-length cap.
"""

from __future__ import annotations

from typing import Any

import requests

from leetcode_guard._leetcode import looks_like_leetcode
from leetcode_guard.tests.test_leetcode import FakeResponse, FakeSession


def identity_session(body: Any) -> FakeSession:
    """A session whose GraphQL POST returns ``body``."""
    return FakeSession(FakeResponse(body=body))


def test_the_identity_probe_accepts_a_real_graphql_response():
    """A well-formed allQuestionsCount reply identifies LeetCode."""
    session = identity_session({"data": {"allQuestionsCount": [{"count": 4003}]}})

    assert looks_like_leetcode(session)


def test_the_identity_probe_rejects_a_captive_portal():
    """A portal answers HTTP 200 from a genuinely public IP, but with HTML --
    which is not a well-formed GraphQL response."""
    session = FakeSession(FakeResponse(raises=True))

    assert not looks_like_leetcode(session)


def test_the_identity_probe_rejects_a_response_without_the_expected_field():
    """A GraphQL reply without allQuestionsCount is not LeetCode."""
    session = identity_session({"data": {"somethingElse": 1}})

    assert not looks_like_leetcode(session)


def test_the_identity_probe_rejects_a_null_payload():
    """A null data payload is not LeetCode."""
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
