"""Tests for solve detection and its three-valued answer.

The parametrised table below is the load-bearing test in the repo: every way
LeetCode can fail must land on UNVERIFIABLE, and only a genuinely empty list
may land on OK-with-nothing.
"""

from __future__ import annotations

import logging

import pytest

from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._submissions import ProbeStatus, fetch_recent_ac
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    null_data_result,
    recent_ac_result,
    submission_row,
)


@pytest.mark.parametrize(
    ("result", "fragment"),
    [
        (
            GraphQLResult(transport_error="network error: refused"),
            "cannot reach LeetCode",
        ),
        (GraphQLResult(errors=("Rate limited",)), "rejected the query"),
        (null_data_result(), "no data"),
        (GraphQLResult(data={"recentAcSubmissionList": None}), "no submission list"),
        (
            GraphQLResult(data={"recentAcSubmissionList": {}}),
            "where the submission list belongs",
        ),
        (GraphQLResult(data={}), "no submission list"),
    ],
)
def test_every_failure_mode_is_unverifiable(result: GraphQLResult, fragment: str):
    probe = fetch_recent_ac(fake_post(result), "kuchy")

    assert probe.status is ProbeStatus.UNVERIFIABLE
    assert probe.submissions == ()
    assert fragment in probe.reason


def test_empty_list_is_a_real_answer_not_an_outage():
    probe = fetch_recent_ac(fake_post(recent_ac_result([])), "kuchy")

    assert probe.status is ProbeStatus.OK
    assert probe.usable
    assert probe.submissions == ()
    assert "no accepted submissions" in probe.reason


def test_submissions_are_parsed():
    result = recent_ac_result(
        [
            submission_row("111", "two-sum", timestamp=1_700_000_000, lang="python3"),
            submission_row(
                "222", "add-two-numbers", timestamp=1_700_000_100, lang="rust"
            ),
        ]
    )

    probe = fetch_recent_ac(fake_post(result), "kuchy")

    assert probe.status is ProbeStatus.OK
    assert [item.submission_id for item in probe.submissions] == ["111", "222"]
    assert probe.submissions[0].timestamp == 1_700_000_000
    assert probe.submissions[1].lang == "rust"
    assert "2 recent accepted submissions" in probe.reason


def test_single_submission_reason_is_singular():
    probe = fetch_recent_ac(
        fake_post(recent_ac_result([submission_row("1", "two-sum")])), "k"
    )

    assert "1 recent accepted submission" in probe.reason
    assert "submissions" not in probe.reason


def test_nonexistent_username_is_unverifiable_and_logged_at_error(caplog):
    result = GraphQLResult(errors=("That user does not exist.",))

    with caplog.at_level(logging.ERROR):
        probe = fetch_recent_ac(fake_post(result), "nope")

    assert probe.status is ProbeStatus.UNVERIFIABLE
    assert "does not exist" in probe.reason
    assert any(record.levelno == logging.ERROR for record in caplog.records)


@pytest.mark.parametrize(
    "row",
    [
        "not-an-object",
        {"titleSlug": "two-sum"},
        {"id": "1"},
        {"id": "1", "titleSlug": ""},
        {"id": "1", "titleSlug": "s", "timestamp": "not-a-number"},
        {"id": "1", "titleSlug": "s", "timestamp": None},
        {"id": "1", "titleSlug": "s", "timestamp": True},
    ],
)
def test_malformed_rows_are_skipped_without_downgrading_the_probe(row: object):
    good = submission_row("999", "good-one")

    probe = fetch_recent_ac(fake_post(recent_ac_result([row, good])), "kuchy")

    assert probe.status is ProbeStatus.OK
    assert [item.submission_id for item in probe.submissions] == ["999"]


def test_integer_timestamp_is_accepted():
    row = {"id": "5", "titleSlug": "two-sum", "timestamp": 1_700_000_000}

    probe = fetch_recent_ac(fake_post(recent_ac_result([row])), "kuchy")

    assert probe.submissions[0].timestamp == 1_700_000_000


def test_title_defaults_to_the_slug_when_absent():
    row = {"id": "5", "titleSlug": "two-sum", "timestamp": "1"}

    probe = fetch_recent_ac(fake_post(recent_ac_result([row])), "kuchy")

    assert probe.submissions[0].title == "two-sum"
    assert probe.submissions[0].lang == ""


def test_all_rows_malformed_still_reports_ok_with_nothing():
    probe = fetch_recent_ac(fake_post(recent_ac_result(["junk"])), "kuchy")

    assert probe.status is ProbeStatus.OK
    assert probe.submissions == ()


def test_the_username_is_sent_in_the_variables():
    post = fake_post(recent_ac_result([]))

    fetch_recent_ac(post, "someone")

    assert post.calls[0][1]["username"] == "someone"
    assert post.calls[0][1]["limit"] == 20
