"""The morning-session carrot: read from wake-alarm's signed file, never re-derived."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac
import pytest

from leetcode_guard import _cli, _morning_session
from leetcode_guard._morning_session import defer_for_morning_session
from leetcode_guard.tests.test_cli import patch_cli

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 9, 19, 9, 0).astimezone()


@pytest.fixture(autouse=True)
def _signing_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    import gatelock.log_integrity

    monkeypatch.setattr(gatelock.log_integrity, "DEFAULT_HMAC_KEY_FILE", key)


def _entry(
    outcome: str = "completed",
    exempt_until: str | None = "11:00",
    date: str = "2026-09-19",
) -> dict[str, object]:
    entry: dict[str, object] = {"date": date, "outcome": outcome}
    if exempt_until is not None:
        entry["exempt_until"] = (
            datetime.fromisoformat(f"{date}T{exempt_until}").astimezone().isoformat()
        )
    return entry


def _write(entry: dict[str, object], *, sign: bool = True) -> Path:
    if sign:
        entry["hmac"] = compute_entry_hmac(entry)
    path = _morning_session.MORNING_SESSION_FILE
    path.write_text(json.dumps(entry))
    return path


def _today() -> str:
    return datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d")


class TestVerdict:
    def test_completed_defers_until_the_signed_instant(self) -> None:
        _write(_entry())
        assert defer_for_morning_session(NOW) == (
            "morning session completed, no gate until 11:00"
        )

    def test_expired_absent_or_unreadable_exemptions_defer_nothing(self) -> None:
        _write(_entry())
        assert defer_for_morning_session(NOW + timedelta(hours=3)) is None
        _write(_entry("failed", exempt_until=None))
        assert defer_for_morning_session(NOW) is None
        _write({**_entry(), "exempt_until": "later"})
        assert defer_for_morning_session(NOW) is None

    def test_yesterday_missing_tampered_and_broken_defer_nothing(self) -> None:
        _write(_entry(date="2026-09-18"))
        assert defer_for_morning_session(NOW) is None
        path = _write(_entry(), sign=False)
        assert defer_for_morning_session(NOW) is None
        path.write_text("[1]")
        assert defer_for_morning_session(NOW) is None
        path.write_text("{")
        assert defer_for_morning_session(NOW) is None
        path.unlink()
        assert defer_for_morning_session(NOW) is None
        path.mkdir()
        assert defer_for_morning_session(NOW) is None


class TestBootRetry:
    def test_waits_inside_the_window_then_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        naps: list[float] = []
        monkeypatch.setattr(_morning_session, "MORNING_RETRY_SECONDS", 10.0)
        # The window is re-checked against the real clock after each nap.
        monkeypatch.setattr(_morning_session, "MORNING_WINDOW", ((0, 0), (23, 59)))
        assert defer_for_morning_session(NOW, wait=True, sleep=naps.append) is None
        assert naps == [5.0, 5.0]
        assert "is wake-alarm-session.timer running" in caplog.text

    def test_a_file_landing_mid_wait_is_honoured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_morning_session, "MORNING_RETRY_SECONDS", 10.0)
        monkeypatch.setattr(_morning_session, "MORNING_WINDOW", ((0, 0), (23, 59)))

        def land(_seconds: float) -> None:
            _write(_entry(date=_today(), exempt_until="23:59"))

        assert defer_for_morning_session(NOW, wait=True, sleep=land) is not None

    def test_never_waits_outside_the_window_or_without_wait(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        naps: list[float] = []
        monkeypatch.setattr(_morning_session, "MORNING_RETRY_SECONDS", 10.0)
        afternoon = NOW.replace(hour=14)
        assert (
            defer_for_morning_session(afternoon, wait=True, sleep=naps.append) is None
        )
        assert defer_for_morning_session(NOW, sleep=naps.append) is None
        assert naps == []


class TestArmingRun:
    """A deferral costs no network and writes nothing; demo ignores it."""

    def test_production_defers_without_touching_the_network(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        data_dir: Path,
    ) -> None:
        _write(_entry(date=_today(), exempt_until="23:59"))
        monkeypatch.setattr(
            _cli, "build_client", lambda: pytest.fail("must not touch the network")
        )
        assert _cli.main(["--production"]) == 0
        assert "deferred: morning session completed" in capsys.readouterr().out
        assert not (data_dir / "ledger.json").exists()

    def test_demo_ignores_the_morning(
        self, monkeypatch: pytest.MonkeyPatch, data_dir: Path
    ) -> None:
        _write(_entry(date=_today(), exempt_until="23:59"))
        reached: dict[str, bool] = {}

        def stop() -> None:
            reached["client"] = True
            raise SystemExit(7)

        patch_cli(monkeypatch, "build_client", stop)
        with pytest.raises(SystemExit):
            _cli.main([])
        assert reached == {"client": True}
