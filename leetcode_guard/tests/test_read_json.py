"""The shared cache opener: absent and unreadable both read as MISSING."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_LOGGER = logging.getLogger("leetcode_guard.tests.read_json")


def test_absent_file_is_missing_and_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No file yet means nothing cached, so nothing is logged."""
    assert read_json(tmp_path / "none.json", _LOGGER, "x %s") is MISSING
    assert caplog.records == []


def test_unparsable_file_warns_on_the_callers_logger(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A corrupt file reads as MISSING; the error is the format's last arg."""
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_json(path, _LOGGER, "cache at %s is unreadable: %s", path) is MISSING
    (record,) = caplog.records
    assert record.name == _LOGGER.name
    assert record.levelno == logging.WARNING
    assert record.args[0] == path
    assert isinstance(record.args[1], ValueError)


def test_unreadable_path_warns_with_the_oserror(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A path that exists but cannot be read (a directory) is an OSError."""
    assert read_json(tmp_path, _LOGGER, "marks: %s") is MISSING
    (record,) = caplog.records
    assert isinstance(record.args[0], OSError)


def test_valid_document_is_returned_as_parsed(tmp_path: Path) -> None:
    """Any JSON value comes back as ``json.loads`` gave it, ``null`` included."""
    path = tmp_path / "ok.json"
    for value in ({"version": 1}, [1, 2], None):
        path.write_text(json.dumps(value), encoding="utf-8")
        assert read_json(path, _LOGGER, "x %s") == value
