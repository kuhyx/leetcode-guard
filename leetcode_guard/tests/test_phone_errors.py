"""Tests for the phone's reported errors: parsing, the local mirror, --status.

2026-10-24 the status app's banner showed a raw exception (with the RTDB
``?auth=`` token) on the phone and nobody at the desk knew. The phone now
writes its last few sanitised errors to ``leetcode-guard/app_errors/<device>``;
these modules read them back. Display only: nothing here gates or credits.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING

from leetcode_guard import _cli, _phone_errors
from leetcode_guard._phone_errors import (
    PhoneError,
    parse_phone_errors,
    read_mirror,
    status_lines,
    write_mirror,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DEVICE = "0b7e3c1a-1111-4222-8333-444455556666"
NOW = datetime(2026, 10, 24, 11, 30, tzinfo=UTC)


def entry(message: str = "Offline: can't reach Firebase", **extra: object) -> dict:
    """One error as the app writes it."""
    return {
        "message": message,
        "first_seen": "2026-10-24T11:05:00.000Z",
        "last_seen": "2026-10-24T11:20:00.000Z",
        "count": 4,
        **extra,
    }


def node(*errors: dict, device: str = DEVICE) -> dict[str, object]:
    """``app_errors`` as RTDB returns it: one JSON string leaf per device."""
    return {device: json.dumps({"device": device, "errors": list(errors)})}


def test_a_string_leaf_per_device_parses():
    [error] = parse_phone_errors(node(entry()))

    assert error == PhoneError(
        device=DEVICE,
        message="Offline: can't reach Firebase",
        first_seen="2026-10-24T11:05:00.000Z",
        last_seen="2026-10-24T11:20:00.000Z",
        count=4,
    )
    assert error.key == f"{DEVICE}|2026-10-24T11:05:00.000Z"


def test_junk_is_skipped_not_fatal():
    raw = {
        "a": "not json",
        "b": json.dumps({"errors": "nope"}),
        "c": json.dumps(
            {"errors": [1, entry(count="x"), entry(message=3), entry("ok")]}
        ),
        "d": 7,
        "e": {"errors": [entry("as an object")]},
    }

    messages = [e.message for e in parse_phone_errors(raw)]

    assert messages == ["ok", "as an object"]
    assert parse_phone_errors(None) == []
    assert parse_phone_errors([1, 2]) == []


def test_a_secret_from_the_phone_is_scrubbed_anyway():
    [error] = parse_phone_errors(
        node(entry("boom https://db.example/x.json?auth=SECRET auth=TOKEN2"))
    )

    assert "SECRET" not in error.message
    assert "TOKEN2" not in error.message
    assert "http" not in error.message


def test_the_mirror_round_trips(tmp_path: Path):
    path = tmp_path / "phone_errors.json"
    errors = parse_phone_errors(node(entry()))

    assert write_mirror(errors, {"k"}, path=path)

    assert read_mirror(path) == (errors, {"k"})


def test_a_missing_or_corrupt_mirror_reads_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "phone_errors.json"
    assert read_mirror(path) == ([], set())
    path.write_text("{not json", encoding="utf-8")
    assert read_mirror(path) == ([], set())
    path.write_text('{"errors": {}, "notified": 3}', encoding="utf-8")
    assert read_mirror(path) == ([], set())
    assert "unreadable" in caplog.text


def test_an_unwritable_mirror_is_false(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")

    assert not write_mirror([], set(), path=blocker / "phone_errors.json")
    assert "cannot write" in caplog.text


def test_status_lines_show_recent_errors_newest_first(tmp_path: Path):
    path = tmp_path / "phone_errors.json"
    old = entry("stale one", last_seen="2026-10-01T09:00:00.000Z")
    newer = entry("newer", last_seen="2026-10-24T11:25:00.000Z")
    write_mirror(parse_phone_errors(node(entry(), old, newer)), set(), path=path)

    lines = status_lines(path=path, now=NOW)

    assert lines[0] == "phone errors (last 7 days):"
    assert "newer" in lines[1]
    assert "Offline: can't reach Firebase" in lines[2]
    assert "x4" in lines[2]
    assert DEVICE[:8] in lines[2]
    assert not any("stale one" in line for line in lines)


def test_status_lines_are_empty_with_nothing_recent(tmp_path: Path):
    path = tmp_path / "phone_errors.json"
    assert status_lines(path=path, now=NOW) == []
    bad_time = entry(last_seen="yesterday")
    write_mirror(parse_phone_errors(node(bad_time)), set(), path=path)
    assert status_lines(path=path, now=NOW + timedelta(days=30)) == []


def test_status_prints_the_phone_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    write_mirror(parse_phone_errors(node(entry())), set())
    monkeypatch.setattr(_phone_errors, "_now", lambda: NOW)

    _cli.main(["--status"])

    out = capsys.readouterr().out
    assert "phone errors (last 7 days):" in out
    assert "Offline: can't reach Firebase" in out
