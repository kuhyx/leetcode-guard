"""The harvesters price a credit before the gate decides, and a focus day still
records credits (kuhy 2026-11-02: "it should still count credits even if it's
turned off" -- only charges and locks stand down)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from leetcode_guard import _constants, _focus, _harvest_run, _lock_poll
from leetcode_guard._daycost import local_today
from leetcode_guard._difficulty import load_weights
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard._leetcode import GraphQLResult
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard.tests._guard_factories import probe_of
from leetcode_guard.tests._ledger_fixtures import NOW, submission
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    problem_row,
    recent_ac_result,
    submission_row,
)
from leetcode_guard.tests.test_harvest_run import seeded_ledger, stub_client

if TYPE_CHECKING:
    from pathlib import Path


def question_result(difficulty: str) -> GraphQLResult:
    """Wrap a question-difficulty reply as a GraphQL result."""
    return GraphQLResult(data={"question": {"difficulty": difficulty}})


def test_a_fresh_credit_is_priced_before_the_gate_decides(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """Else a Medium solve on a 2-credit day banks as 1 and waits a minute."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "median-of-two")]),
        question_result("Medium"),
    )
    seen: list[int] = []

    def decide(*_a, **_k):
        seen.append(load_weights(key_file=hmac_key).weight("median-of-two"))
        return SimpleNamespace(locked=True, charge=None)

    monkeypatch.setattr(_harvest_run, "decide_today", decide)

    _harvest_run.main(key_file=hmac_key)

    assert seen == [2]


def test_a_failed_pricing_still_records_the_credit(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """A pricing call that fails still banks the credit at the default weight of 1."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "median-of-two")]),
        GraphQLResult(transport_error="down"),
    )

    _harvest_run.main(key_file=hmac_key)

    assert load_ledger(data_dir / "ledger.json").has("ac:42")
    assert "credited 1" in capsys.readouterr().out
    assert load_weights(key_file=hmac_key).weight("median-of-two") == 1


def test_an_idle_tick_backfills_credited_problems_from_the_pool(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """A tick with no new solves backfills Hard weight for already credited problems."""
    path = data_dir / "ledger.json"
    seeded_ledger(path, hmac_key)
    ledger = load_ledger(path, key_file=hmac_key)
    append(
        ledger,
        [
            credit_entry(
                submission("7", "old-hard"), day=NOW.date(), now=NOW, key_file=hmac_key
            )
        ],
    )
    save_ledger(path, ledger)
    problems = (parse_problem(problem_row("old-hard", difficulty="Hard")),)
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=problems, fetched_at=1.0, complete=True),
    )
    stub_client(monkeypatch, recent_ac_result([]))

    _harvest_run.main(key_file=hmac_key)

    assert load_weights(key_file=hmac_key).weight("old-hard") == 4


def test_a_focus_day_still_records_credits_but_charges_nothing(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """The real ``decide_today`` on a focus day: credit yes, charge no."""
    today = local_today()
    monkeypatch.setattr(_focus, "stands_down", lambda _gate, day: day == today)
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "two-sum")]),
        question_result("Easy"),
    )

    _harvest_run.main(key_file=hmac_key)

    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    assert ledger.has("ac:42")
    assert not ledger.of_kind("charge")
    out = capsys.readouterr().out
    assert "credited 1" in out
    assert "settled today" not in out


def fake_lock(key_file: Path | None, *, write_ledger: bool) -> SimpleNamespace:
    """Just the ``deps`` the poll mixin's ``check`` reads; no window built."""
    deps = SimpleNamespace(
        post=fake_post(),
        username="k",
        key_file=key_file,
        write_ledger=write_ledger,
        moment=lambda: NOW,
    )
    return SimpleNamespace(deps=deps)


def test_the_lock_prices_new_submissions_on_the_executor(monkeypatch, hmac_key: Path):
    """The lock's check prices new submissions once, against its key file."""
    asked: list[dict[str, object]] = []
    monkeypatch.setattr(
        _lock_poll, "fetch_recent_ac", lambda _post, _user: probe_of("a")
    )
    monkeypatch.setattr(
        _lock_poll, "resolve_probe", lambda probe, **kw: asked.append(kw)
    )

    probe = _lock_poll.PollMixin.check(fake_lock(hmac_key, write_ledger=True))

    assert probe.submissions
    assert len(asked) == 1
    assert asked[0]["key_file"] == hmac_key


def test_the_demo_lock_never_writes_difficulty_rows(monkeypatch):
    """The demo lock checks submissions without ever writing difficulty rows."""
    monkeypatch.setattr(
        _lock_poll, "fetch_recent_ac", lambda _post, _user: probe_of("a")
    )
    monkeypatch.setattr(
        _lock_poll,
        "resolve_probe",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("demo wrote")),
    )

    probe = _lock_poll.PollMixin.check(fake_lock(None, write_ledger=False))

    assert probe.submissions
