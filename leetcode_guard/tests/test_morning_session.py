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


class TestBinding:
    """The verdict rules are gatelock's; this checks leetcode-guard's wiring."""

    def test_completed_defers_until_the_signed_instant(self) -> None:
        _write(_entry())
        assert defer_for_morning_session(NOW) == (
            "morning session completed, no gate until 11:00"
        )

    def test_expired_or_unsigned_defers_nothing(self) -> None:
        _write(_entry())
        assert defer_for_morning_session(NOW + timedelta(hours=3)) is None
        _write(_entry(), sign=False)
        assert defer_for_morning_session(NOW) is None

    def test_the_retry_budget_is_leetcode_guards_own(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        naps: list[float] = []
        assert defer_for_morning_session(NOW, wait=True, sleep=naps.append) is None
        assert naps == []
        monkeypatch.setattr(_morning_session, "MORNING_RETRY_SECONDS", 10.0)
        assert defer_for_morning_session(NOW, wait=True, sleep=naps.append) is None
        assert naps


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
