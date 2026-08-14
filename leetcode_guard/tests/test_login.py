"""Tests for the verified cookie store.

The point of ``--login`` is that it fails closed. Every test here is really
asking one question: can an unverified credential reach the disk? It must not,
because the whole defect this command exists to fix was a cookie file that
looked authoritative and was not.
"""

from __future__ import annotations

import json
import stat
from typing import TYPE_CHECKING

from leetcode_guard._auth import CSRF_KEY, SESSION_KEY, Cookies, load_cookies
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._login import login, verify_cookies, write_cookies

if TYPE_CHECKING:
    from pathlib import Path

import leetcode_guard._login as login_module

GOOD = Cookies(session="sess", csrf="tok")


def reader_for(*values: str):
    """A stdin stand-in yielding each value once."""
    remaining = iter(values)
    return lambda: next(remaining)


def patch_post(monkeypatch, result: GraphQLResult) -> list[str]:
    """Make the module's one network call return ``result``."""
    seen: list[str] = []

    def fake_post(
        _session: object,
        _query: str,
        variables: dict[str, object],
        *,
        timeout: float,
    ) -> GraphQLResult:
        assert timeout > 0
        seen.append(str(variables["titleSlug"]))
        return result

    monkeypatch.setattr(login_module, "post_graphql", fake_post)
    monkeypatch.setattr(login_module, "build_session", lambda cookies: cookies)
    return seen


def test_a_recognised_session_verifies(monkeypatch):
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "notac"}}))

    ok, reason = verify_cookies(GOOD, timeout=1.0)

    assert ok
    assert "recognised" in reason


def test_a_null_status_is_refused(monkeypatch):
    """The exact shape of an expired session: HTTP 200, valid payload, null."""
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": None}}))

    ok, reason = verify_cookies(GOOD, timeout=1.0)

    assert not ok
    assert "null" in reason


def test_an_unreachable_endpoint_is_refused(monkeypatch):
    patch_post(monkeypatch, GraphQLResult(transport_error="down"))

    ok, reason = verify_cookies(GOOD, timeout=1.0)

    assert not ok
    assert "could not reach" in reason


def test_a_rejected_query_is_refused(monkeypatch):
    patch_post(monkeypatch, GraphQLResult(errors=("bad token",)))

    ok, reason = verify_cookies(GOOD, timeout=1.0)

    assert not ok
    assert "rejected" in reason


def test_the_probe_asks_about_a_free_problem(monkeypatch):
    seen = patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "ac"}}))

    verify_cookies(GOOD, timeout=1.0)

    assert seen == ["two-sum"]


def test_a_verified_pair_is_written_and_loads_back(tmp_path: Path, monkeypatch):
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "ac"}}))
    path = tmp_path / "nested" / "cookies.json"

    assert login(path, timeout=1.0, reader=reader_for("sess\n", "tok\n"))

    assert json.loads(path.read_text()) == {SESSION_KEY: "sess", CSRF_KEY: "tok"}
    loaded = load_cookies(path)
    assert loaded.cookies == GOOD


def test_the_cookie_file_is_readable_only_by_its_owner(tmp_path: Path, monkeypatch):
    """It holds a live credential; another local user must not be able to read
    it, and a chmod after writing would leave a window where they could."""
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "ac"}}))
    path = tmp_path / "cookies.json"

    login(path, timeout=1.0, reader=reader_for("sess\n", "tok\n"))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_an_unverified_pair_never_reaches_the_disk(tmp_path: Path, monkeypatch):
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": None}}))
    path = tmp_path / "cookies.json"

    assert not login(path, timeout=1.0, reader=reader_for("sess\n", "tok\n"))

    assert not path.exists()


def test_a_refused_login_leaves_an_existing_file_untouched(tmp_path: Path, monkeypatch):
    """Failing this would make `--login` worse than not running it: a typo
    would destroy a session that was still working."""
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": None}}))
    path = tmp_path / "cookies.json"
    path.write_text(json.dumps({SESSION_KEY: "old", CSRF_KEY: "old"}))

    assert not login(path, timeout=1.0, reader=reader_for("new\n", "new\n"))

    assert json.loads(path.read_text())[SESSION_KEY] == "old"


def test_a_blank_value_is_rejected_without_asking_leetcode(tmp_path: Path, monkeypatch):
    seen = patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "ac"}}))
    path = tmp_path / "cookies.json"

    assert not login(path, timeout=1.0, reader=reader_for("\n", "tok\n"))

    assert seen == []
    assert not path.exists()


def test_a_blank_csrf_is_also_rejected(tmp_path: Path, monkeypatch):
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "ac"}}))
    path = tmp_path / "cookies.json"

    assert not login(path, timeout=1.0, reader=reader_for("sess\n", "   \n"))

    assert not path.exists()


def test_an_unwritable_path_is_reported_not_raised(tmp_path: Path, monkeypatch):
    patch_post(monkeypatch, GraphQLResult(data={"question": {"status": "ac"}}))
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")

    assert not login(
        blocker / "cookies.json", timeout=1.0, reader=reader_for("s\n", "t\n")
    )


def test_write_cookies_reports_failure_rather_than_raising(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")

    assert not write_cookies(blocker / "cookies.json", GOOD)
