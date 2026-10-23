"""Tests for the profile mirror and its refresh policy.

The policy exists to protect the gate: the push runs every minute and the
endpoint answers a rate limit with the same null payload as an expired
session, so a profile fetch per push could starve the harvest's own probe.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _profile_cache
from leetcode_guard._auth import AuthState
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._profile import Profile
from leetcode_guard._profile_cache import (
    PROFILE_TTL_SECONDS,
    read_profile_cache,
    refresh_profile,
    write_profile_cache,
)
from leetcode_guard._progress import read_progress_cache
from leetcode_guard._settings import Client
from leetcode_guard.tests._net_fixtures import fake_post
from leetcode_guard.tests._profile_fixtures import profile_result

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard.tests._net_fixtures import FakePost

NOW = 1_800_000_000.0


def a_profile(*, fetched_at: float = NOW, credit_count: int = 3) -> Profile:
    return Profile(
        solved={"Easy": 1, "Medium": 2, "Hard": 3},
        total={"Easy": 10, "Medium": 20, "Hard": 30},
        calendar={"2026-10-22": 4},
        acceptance_rate=50.0,
        fetched_at=fetched_at,
        credit_count=credit_count,
    )


def builder(post: FakePost):
    return lambda: Client(
        post=post, auth=AuthState(cookies=None, note="signed out"), username="k"
    )


def test_the_cache_round_trips(tmp_path: Path):
    path = tmp_path / "profile.json"

    assert write_profile_cache(path, a_profile())
    assert read_profile_cache(path) == a_profile()


def test_a_cache_without_a_calendar_round_trips(tmp_path: Path):
    path = tmp_path / "profile.json"
    profile = Profile(
        solved={"Easy": 1, "Medium": 2, "Hard": 3},
        total={"Easy": 10, "Medium": 20, "Hard": 30},
        calendar=None,
        acceptance_rate=None,
        fetched_at=NOW,
        credit_count=0,
    )
    write_profile_cache(path, profile)

    assert read_profile_cache(path) == profile


def test_an_unwritable_cache_is_reported_not_raised(tmp_path: Path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    assert not write_profile_cache(blocker / "profile.json", a_profile())


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"version": 2}',
        '{"version": 1, "fetched_at": "x"}',
        '{"version": 1, "fetched_at": 1, "credits": 0, "solved": {}, "total": {}}',
        '{"version": 1, "fetched_at": 1, "credits": "0", '
        '"solved": {"Easy": 1, "Medium": 1, "Hard": 1}, '
        '"total": {"Easy": 1, "Medium": 1, "Hard": 1}}',
        '{"version": 1, "fetched_at": 1, "credits": 0, '
        '"solved": {"Easy": 1, "Medium": 1, "Hard": 1}, '
        '"total": {"Easy": 1, "Medium": 1, "Hard": 1}, "calendar": [], '
        '"acceptance_rate": null}',
        '{"version": 1, "fetched_at": 1, "credits": 0, '
        '"solved": {"Easy": 1, "Medium": 1, "Hard": 1}, '
        '"total": {"Easy": 1, "Medium": 1, "Hard": 1}, "calendar": null, '
        '"acceptance_rate": "50"}',
    ],
)
def test_an_unusable_cache_is_none(tmp_path: Path, text: str):
    path = tmp_path / "profile.json"
    path.write_text(text, encoding="utf-8")

    assert read_profile_cache(path) is None


def test_a_missing_cache_is_none(tmp_path: Path):
    assert read_profile_cache(tmp_path / "absent.json") is None


def test_a_fresh_cache_is_served_without_a_request(tmp_path: Path):
    path = tmp_path / "profile.json"
    write_profile_cache(path, a_profile(fetched_at=NOW - 60))
    post = fake_post(profile_result())

    profile = refresh_profile(
        now=NOW, credit_count=3, build=builder(post), cache_path=path
    )

    assert profile == a_profile(fetched_at=NOW - 60)
    assert post.calls == []


def test_a_new_credit_refetches_at_once(tmp_path: Path, data_dir: Path):
    """A solve should reach the Profile tab within the minute, not the TTL."""
    path = tmp_path / "profile.json"
    write_profile_cache(path, a_profile(fetched_at=NOW - 60, credit_count=3))
    post = fake_post(profile_result())

    profile = refresh_profile(
        now=NOW, credit_count=4, build=builder(post), cache_path=path
    )

    assert profile is not None
    assert profile.credit_count == 4
    assert len(post.calls) == 1


def test_a_stale_cache_refetches_and_mirrors_progress(tmp_path: Path, data_dir: Path):
    path = tmp_path / "profile.json"
    write_profile_cache(path, a_profile(fetched_at=NOW - PROFILE_TTL_SECONDS))
    post = fake_post(profile_result())

    profile = refresh_profile(
        now=NOW, credit_count=3, build=builder(post), cache_path=path
    )

    assert profile is not None
    assert profile.solved["Easy"] == 142
    assert read_profile_cache(path) == profile
    progress = read_progress_cache(data_dir / "progress_cache.json")
    assert progress is not None
    assert progress.solved["Easy"] == 142


def test_a_cache_from_the_future_is_not_trusted(tmp_path: Path, data_dir: Path):
    path = tmp_path / "profile.json"
    write_profile_cache(path, a_profile(fetched_at=NOW + 600))
    post = fake_post(profile_result())

    refresh_profile(now=NOW, credit_count=3, build=builder(post), cache_path=path)

    assert len(post.calls) == 1


def test_a_failed_fetch_serves_the_dated_cache(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "profile.json"
    stale = a_profile(fetched_at=NOW - 2 * PROFILE_TTL_SECONDS)
    write_profile_cache(path, stale)
    post = fake_post(GraphQLResult(errors=("That user does not exist.",)))

    assert refresh_profile(
        now=NOW, credit_count=3, build=builder(post), cache_path=path
    ) == (stale)
    assert "could not refresh the LeetCode profile" in caplog.text


def test_a_failed_fetch_with_no_cache_is_none(tmp_path: Path):
    post = fake_post(GraphQLResult())

    assert (
        refresh_profile(
            now=NOW, credit_count=0, build=builder(post), cache_path=tmp_path / "p.json"
        )
        is None
    )


def test_defaults_resolve_to_the_redirected_paths(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path
):
    post = fake_post(profile_result())
    monkeypatch.setattr(_profile_cache, "build_client", builder(post))

    refresh_profile(now=NOW, credit_count=0)

    cached = json.loads(_profile_cache.PROFILE_CACHE_FILE.read_text(encoding="utf-8"))
    assert cached["credits"] == 0
    assert _profile_cache.PROFILE_CACHE_FILE.parent == data_dir
