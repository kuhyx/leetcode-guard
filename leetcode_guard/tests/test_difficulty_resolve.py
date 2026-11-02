"""Writing signed difficulty rows: pool cache first, then LeetCode, bounded."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _constants, _difficulty_resolve
from leetcode_guard._difficulty import load_weights
from leetcode_guard._difficulty_resolve import (
    ResolveResult,
    resolve_difficulties,
    resolve_probe,
)
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard.tests._difficulty_fixtures import (
    question_result,
    seed_pool,
    write_rows,
)
from leetcode_guard.tests._guard_factories import UNVERIFIABLE, probe_of
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests._net_fixtures import fake_post

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_resolve_prefers_the_pool_cache_and_needs_no_network(
    data_dir: Path, hmac_key: Path
):
    seed_pool({"a": "Medium", "b": "Hard"})
    post = fake_post()

    result = resolve_difficulties(["a", "b"], post=post, now=NOW, key_file=hmac_key)

    assert (result.resolved, result.fetched, result.failed) == (2, 0, 0)
    assert not post.calls
    table = load_weights(key_file=hmac_key)
    assert [table.weight("a"), table.weight("b")] == [2, 4]


def test_resolve_asks_leetcode_for_what_the_pool_lacks(data_dir: Path, hmac_key: Path):
    post = fake_post(question_result("Hard"))

    result = resolve_difficulties(["new-one"], post=post, now=NOW, key_file=hmac_key)

    assert (result.resolved, result.fetched, result.failed) == (1, 1, 0)
    assert post.calls[0][1] == {"titleSlug": "new-one"}
    assert load_weights(key_file=hmac_key).weight("new-one") == 4


def test_resolve_skips_what_is_already_cached(data_dir: Path, hmac_key: Path):
    write_rows(_constants.DIFFICULTY_FILE, hmac_key, {"a": "Medium"})
    post = fake_post()

    result = resolve_difficulties(["a"], post=post, now=NOW, key_file=hmac_key)

    assert (result.resolved, result.already) == (0, 1)
    assert not post.calls


def test_resolve_replaces_an_untrusted_row(data_dir: Path, hmac_key: Path):
    path = _constants.DIFFICULTY_FILE
    write_rows(path, hmac_key, {"a": "Easy"})
    path.write_text(path.read_text().replace("Easy", "Hard"), encoding="utf-8")
    post = fake_post(question_result("Medium"))

    resolve_difficulties(["a"], post=post, now=NOW, key_file=hmac_key)

    assert load_weights(key_file=hmac_key).weight("a") == 2


def test_a_failed_lookup_is_logged_and_leaves_no_row(
    data_dir: Path, hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    post = fake_post(GraphQLResult(transport_error="boom"))
    with caplog.at_level(logging.WARNING):
        result = resolve_difficulties(["x"], post=post, now=NOW, key_file=hmac_key)

    assert (result.resolved, result.failed) == (0, 1)
    assert not _constants.DIFFICULTY_FILE.exists()
    assert "x" in caplog.text


def test_a_payload_without_a_known_difficulty_fails(data_dir: Path, hmac_key: Path):
    post = fake_post(GraphQLResult(data={"question": None}))

    result = resolve_difficulties(["x"], post=post, now=NOW, key_file=hmac_key)

    assert result.failed == 1


def test_max_fetch_bounds_the_network_per_call(data_dir: Path, hmac_key: Path):
    post = fake_post(question_result("Medium"))

    result = resolve_difficulties(
        ["a", "b", "c"], post=post, now=NOW, key_file=hmac_key, max_fetch=2
    )

    assert (result.fetched, result.deferred) == (2, 1)
    assert len(post.calls) == 2


def test_rows_persist_atomically_and_reload_signed(data_dir: Path, hmac_key: Path):
    seed_pool({"a": "Medium"})
    resolve_difficulties(["a"], post=fake_post(), now=NOW, key_file=hmac_key)

    ledger = load_ledger(_constants.DIFFICULTY_FILE, key_file=hmac_key)

    assert ledger.tampered == 0
    assert ledger.entries["difficulty:a"].detail["difficulty"] == "Medium"


def test_a_failed_save_reports_the_rows_as_failed(
    data_dir: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
):
    seed_pool({"a": "Medium"})
    monkeypatch.setattr(_difficulty_resolve, "save_ledger", lambda *_a, **_k: False)

    result = resolve_difficulties(["a"], post=fake_post(), now=NOW, key_file=hmac_key)

    assert (result.resolved, result.failed) == (0, 1)


def test_resolve_probe_prices_what_the_probe_will_credit(
    data_dir: Path, hmac_key: Path
):
    probe = probe_of("a", "b")
    post = fake_post(question_result("Medium"))

    result = resolve_probe(probe, post=post, now=NOW, key_file=hmac_key)

    assert result.resolved == 1  # both submissions are of the same problem
    assert load_weights(key_file=hmac_key).weight("two-sum") == 2


def test_resolve_probe_ignores_an_unusable_probe(data_dir: Path, hmac_key: Path):
    post = fake_post()

    result = resolve_probe(UNVERIFIABLE, post=post, now=NOW, key_file=hmac_key)

    assert result == ResolveResult()
    assert not post.calls
