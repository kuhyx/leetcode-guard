"""Tests for optional cookie loading.

The invariant under test throughout: every failure mode produces an
:class:`AuthState`, never an exception. This runs on the lock's startup path,
where an exception means no window.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._auth import load_cookies, rejected_state

if TYPE_CHECKING:
    from pathlib import Path


def write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_cookies_load(tmp_path: Path):
    path = write(tmp_path / "c.json", {"LEETCODE_SESSION": "sess", "csrftoken": "tok"})

    state = load_cookies(path)

    assert state.present
    assert state.cookies is not None
    assert state.cookies.session == "sess"
    assert state.cookies.csrf == "tok"
    # Loading cookies is not the same as LeetCode accepting them, so the note
    # must not promise that solved problems are being filtered. It said
    # "already-solved problems are hidden from this list" for a fortnight while
    # the session was dead and every `status` came back null.
    assert "accepts them" in state.note
    assert "hidden" not in state.note


def test_missing_file_is_normal_not_an_error(tmp_path: Path):
    state = load_cookies(tmp_path / "absent.json")

    assert not state.present
    assert "NOT filtered out" in state.note


def test_unreadable_file_degrades(tmp_path: Path):
    path = tmp_path / "c.json"
    path.mkdir()

    state = load_cookies(path)

    assert not state.present
    assert "unreadable" in state.note


def test_invalid_json_degrades(tmp_path: Path):
    path = tmp_path / "c.json"
    path.write_text("{not json", encoding="utf-8")

    state = load_cookies(path)

    assert not state.present
    assert "unreadable" in state.note


def test_non_object_json_degrades(tmp_path: Path):
    state = load_cookies(write(tmp_path / "c.json", ["a", "b"]))

    assert not state.present
    assert "not a JSON object" in state.note


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"LEETCODE_SESSION": "sess"},
        {"csrftoken": "tok"},
        {"LEETCODE_SESSION": "", "csrftoken": "tok"},
        {"LEETCODE_SESSION": "sess", "csrftoken": ""},
        {"LEETCODE_SESSION": 7, "csrftoken": "tok"},
        {"LEETCODE_SESSION": "sess", "csrftoken": 7},
    ],
)
def test_incomplete_cookies_degrade(tmp_path: Path, payload: dict):
    state = load_cookies(write(tmp_path / "c.json", payload))

    assert not state.present
    assert "missing" in state.note


def test_rejected_state_names_the_fix():
    state = rejected_state()

    assert not state.present
    assert "expires" in state.note
    assert "LEETCODE_SESSION" in state.note
