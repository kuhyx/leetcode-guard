"""``--evening``: the gate as one rung of the evening chain.

The contract (``evening-chain/CONTRACT.md``): decide = "is the leetcode rung
paid today" (a verified ``charge`` row with ``source=leetcode``); paid exits 0
with no window; the morning-session and night-lockdown deferrals are ignored;
X is waited for at most 10 s (exit 3); the window ends by itself when the
charge lands, or by the end-evening control (exit 10).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar

from gatelock import log_integrity
import pytest

from leetcode_guard import _cli, _evening
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_entries import charge_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import add_charge
from leetcode_guard.tests._net_fixtures import pool_result, recent_ac_result
from leetcode_guard.tests.test_cli import _seeded_ledger, patch_cli, stub_client

if TYPE_CHECKING:
    from pathlib import Path

EVENING = ["--production", "--evening"]


class _Guard:
    """Records how the CLI built and ran the guard."""

    built: ClassVar[list[dict]] = []
    exit_code = 0

    def __init__(self, *, demo_mode, deps):
        self.demo_mode = demo_mode
        self.deps = deps
        _Guard.built.append({"demo_mode": demo_mode, "deps": deps})

    def run(self):
        """Return at once instead of entering the lock loop."""


@pytest.fixture(autouse=True)
def _evening_env(monkeypatch: pytest.MonkeyPatch, hmac_key: Path) -> None:
    """The shared signing key is the test key; the guard is a recorder."""
    monkeypatch.setattr(log_integrity, "DEFAULT_HMAC_KEY_FILE", hmac_key)
    _Guard.built = []
    _Guard.exit_code = 0
    patch_cli(monkeypatch, "EveningGuard", _Guard)
    patch_cli(monkeypatch, "LeetcodeGuard", lambda **_kw: pytest.fail("ordinary guard"))
    monkeypatch.setattr(_evening, "wait_for_x_server", lambda **_kw: True)
    stub_client(monkeypatch, recent_ac_result([]), pool_result([], total=0))


def _pay_today(data_dir: Path, key: Path) -> None:
    ledger = Ledger()
    add_charge(ledger, local_today(), key_file=key, now=datetime.now().astimezone())
    save_ledger(data_dir / "ledger.json", ledger)


def test_paid_exits_zero_with_no_window_and_no_x_wait(
    monkeypatch, data_dir: Path, hmac_key: Path
) -> None:
    """Rung paid: exit 0 before X is even waited for."""
    _pay_today(data_dir, hmac_key)
    monkeypatch.setattr(
        _evening, "wait_for_x_server", lambda **_kw: pytest.fail("waited for X")
    )

    assert _cli.main(EVENING) == 0
    assert not _Guard.built


def test_unpaid_arms_even_when_morning_and_night_lockdown_defer(
    monkeypatch, data_dir: Path
) -> None:
    """Both deferrals are ignored in evening mode; the lock is built once."""
    _seeded_ledger(data_dir)
    patch_cli(monkeypatch, "defer_for_morning_session", lambda *_a, **_k: "morning")
    patch_cli(monkeypatch, "defer_for_evening_lockdown", lambda _now: "locked 21:05")

    assert _cli.main(EVENING) == 0
    assert len(_Guard.built) == 1
    assert _Guard.built[0]["demo_mode"] is False


def test_the_ordinary_run_still_honours_the_deferrals(
    monkeypatch, data_dir: Path
) -> None:
    """Without --evening nothing changed: the same deferrals stop the lock."""
    _seeded_ledger(data_dir)
    patch_cli(monkeypatch, "defer_for_morning_session", lambda *_a, **_k: "morning")

    assert _cli.main(["--production"]) == 0
    assert not _Guard.built


def test_a_brand_new_ledger_is_armed_not_skipped(data_dir: Path) -> None:
    """The seeding deferral would exit 0 on an unpaid rung and loop the chain."""
    assert not (data_dir / "ledger.json").exists()

    assert _cli.main(EVENING) == 0
    assert len(_Guard.built) == 1


def test_unpaid_is_not_settled_by_a_non_leetcode_charge(
    data_dir: Path, hmac_key: Path
) -> None:
    """An escape-hatch charge settles the day but does not pay the rung."""
    ledger = Ledger()
    append(
        ledger,
        [
            charge_entry(
                local_today(),
                now=datetime.now().astimezone(),
                source="escape",
                key_file=hmac_key,
            )
        ],
    )
    save_ledger(data_dir / "ledger.json", ledger)

    assert _cli.main(EVENING) == 0
    assert len(_Guard.built) == 1
    # Evening mode never rewrites the ledger on its own say-so.
    assert not load_ledger(data_dir / "ledger.json", key_file=hmac_key).of_kind(
        "credit"
    )


def test_no_x_within_ten_seconds_exits_three(monkeypatch, data_dir: Path) -> None:
    """A bounded wait: no display means exit 3 and no window."""
    _seeded_ledger(data_dir)
    seen: list[float | None] = []

    def no_x(*, timeout_s: float | None = None, probe: object = None) -> bool:
        seen.append(timeout_s)
        assert probe is not None, "the evening wait must use the quiet probe"
        return False

    monkeypatch.setattr(_evening, "wait_for_x_server", no_x)

    assert _cli.main(EVENING) == 3
    assert not _Guard.built
    assert seen
    assert seen[0] is not None
    assert seen[0] <= 10


def test_the_guards_exit_code_is_the_processs(data_dir: Path) -> None:
    """End-evening (exit 10) reaches the orchestrator through ``main``."""
    _seeded_ledger(data_dir)
    _Guard.exit_code = 10

    assert _cli.main(EVENING) == 10


def test_evening_without_production_is_refused(capsys) -> None:
    """Demo mode has no ledger of record to be paid against."""
    with pytest.raises(SystemExit) as exc:
        _cli.main(["--evening"])
    assert exc.value.code == 2
    assert capsys.readouterr().err


def test_an_unreadable_ledger_counts_as_unpaid(
    monkeypatch, data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """None from earned_time is "could not check": logged, rung stays unpaid."""
    monkeypatch.setattr(_evening.earned_time, "done_today", lambda *_a, **_k: None)

    assert _evening.evening_paid(data_dir / "ledger.json", key_file=None) is False
    assert "could not check" in caplog.text


def test_a_raising_ledger_read_counts_as_unpaid(
    monkeypatch, data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An OSError from the reader is logged and means unpaid, never a crash."""

    def boom(*_a, **_k):
        raise OSError

    monkeypatch.setattr(_evening.earned_time, "done_today", boom)

    assert _evening.evening_paid(data_dir / "ledger.json", key_file=None) is False
    assert "could not check" in caplog.text


@pytest.mark.parametrize(
    ("spec", "module", "expected"),
    [
        (None, None, 10),
        (object(), SimpleNamespace(EXIT_END_EVENING=77), 77),
        (object(), SimpleNamespace(), 10),
    ],
)
def test_the_end_code_follows_the_orchestrator_when_it_exists(
    monkeypatch, spec, module, expected: int
) -> None:
    """gatelock.evening_chain ships separately: absent or silent, the contract's
    10 stands; present, its own constant wins."""
    monkeypatch.setattr(_evening.importlib.util, "find_spec", lambda _name: spec)
    monkeypatch.setattr(_evening.importlib, "import_module", lambda _name: module)

    assert _evening.end_evening_code() == expected


def test_a_held_instance_lock_never_exits_zero_on_an_unpaid_rung(
    monkeypatch, data_dir: Path, capsys
) -> None:
    """The daytime lock still up: exit 0 would relaunch the gate in a tight loop."""
    _seeded_ledger(data_dir)
    patch_cli(monkeypatch, "acquire_instance", lambda _path: None)

    assert _cli.main(EVENING) == _evening.EXIT_NO_X
    assert not _Guard.built
    assert "instance lock" in capsys.readouterr().err


def test_a_held_instance_lock_is_zero_when_the_rung_got_paid(
    monkeypatch, data_dir: Path
) -> None:
    """Paid between the preflight and the lock: nothing left to do."""
    _seeded_ledger(data_dir)
    patch_cli(monkeypatch, "acquire_instance", lambda _path: None)
    paid = iter([False, True])
    monkeypatch.setattr(_evening, "evening_paid", lambda *_a, **_k: next(paid))

    assert _cli.main(EVENING) == 0
