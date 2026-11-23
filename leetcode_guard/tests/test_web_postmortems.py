"""``GET /api/postmortems``: the post-mortem view over loopback, read-only."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from leetcode_guard import _web_postmortems
from leetcode_guard._web_postmortems import build_postmortems_payload
from leetcode_guard.tests._postmortem_fixtures import write_all
from leetcode_guard.tests.test_web_theory_route import _fetch

if TYPE_CHECKING:
    import pytest


def test_no_reports_answers_an_empty_list():
    """No post-mortem yet is a known empty state."""
    assert build_postmortems_payload() == {"postmortems": []}


def test_the_route_serves_every_unit_as_json():
    """200, JSON, one ``postmortems`` list with both fixture units."""
    write_all()

    status, ctype, body = _fetch("/api/postmortems")

    assert (status, ctype) == (200, "application/json; charset=utf-8")
    rows = json.loads(body)["postmortems"]
    assert [row["unit"] for row in rows] == ["two-pointers", "prefix-sums"]
    assert rows[1]["post"] == [0, 3]


def test_a_failing_read_answers_null(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A bug inside is ``null`` and a warning, never a 500."""

    def explode() -> list[dict[str, object]]:
        raise RuntimeError

    monkeypatch.setattr(_web_postmortems, "read_postmortems", explode)

    assert build_postmortems_payload() == {"postmortems": None}
    assert "post-mortem route failed" in caplog.text


def test_the_404_names_the_postmortems_route():
    """The not-found text stays truthful."""
    status, _, body = _fetch("/api/nope")

    assert status == 404
    assert b"/api/postmortems" in body
