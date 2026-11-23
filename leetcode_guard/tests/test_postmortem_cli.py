"""``--postmortem-dry-run UNIT``: sign the request, relay the tutor's answer."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

from leetcode_guard import _postmortem_cli, _unit_finish
from leetcode_guard._cli_args import build_parser, chosen_command
from leetcode_guard.tests._theory_scenario import world

if TYPE_CHECKING:
    import pytest


def test_the_tutor_command_defaults_to_the_live_release(monkeypatch):
    """The live tutor's interpreter in its release dir; both can be overridden."""
    monkeypatch.delenv(_postmortem_cli.TUTOR_PYTHON_ENV, raising=False)
    monkeypatch.delenv(_postmortem_cli.TUTOR_CWD_ENV, raising=False)
    argv, cwd = _postmortem_cli.tutor_command("prefix-sums")
    home = Path.home()

    assert argv == [
        str(home / "src/tutor/.venv/bin/python"),
        "-m",
        "tutor",
        "postmortem",
        "prefix-sums",
        "--dry-run",
    ]
    assert cwd == home / ".local/lib/tutor-live/current"

    monkeypatch.setenv(_postmortem_cli.TUTOR_PYTHON_ENV, "/x/python")
    monkeypatch.setenv(_postmortem_cli.TUTOR_CWD_ENV, "/x")
    assert _postmortem_cli.tutor_command("u") == (
        ["/x/python", "-m", "tutor", "postmortem", "u", "--dry-run"],
        Path("/x"),
    )


def test_the_runner_relays_output_and_survives_a_dead_tutor(tmp_path, monkeypatch):
    """stdout plus stderr's tail and the exit code; no binary or a hang is a failure."""
    script = [sys.executable, "-c", "import sys; print('pending'); sys.exit(75)"]
    assert _postmortem_cli.run_tutor(script, tmp_path) == (75, "pending")

    code, out = _postmortem_cli.run_tutor([str(tmp_path / "none")], tmp_path)
    assert code == 1
    assert out.startswith("failed: the tutor did not answer")

    monkeypatch.setattr(_postmortem_cli, "TIMEOUT_S", 0.01)
    slow = [sys.executable, "-c", "import time; time.sleep(5)"]
    assert _postmortem_cli.run_tutor(slow, tmp_path)[0] == 1


def test_a_dry_run_signs_the_request_and_returns_the_tutors_code(
    tmp_path, monkeypatch, hmac_key: Path, capsys: pytest.CaptureFixture[str]
):
    """The request row lands first; the tutor's text and exit code pass through."""
    del hmac_key
    world(tmp_path, monkeypatch)
    seen: list[tuple[list[str], Path]] = []

    def tutor(argv: list[str], cwd: Path) -> tuple[int, str]:
        seen.append((argv, cwd))
        assert _unit_finish.PREVIEW_FILE.exists()
        return 75, "pending: started"

    assert _postmortem_cli.cmd_postmortem_dry_run("a", runner=tutor) == 75
    assert capsys.readouterr().out == "pending: started\n"
    assert seen[0][0][-3:] == ["postmortem", "a", "--dry-run"]


def test_a_unit_without_theory_is_refused(
    tmp_path, monkeypatch, capsys: pytest.CaptureFixture[str]
):
    """No tutor mapping: exit 2, the tutor is never asked, nothing is written."""
    world(tmp_path, monkeypatch)

    def tutor(argv: list[str], cwd: Path) -> tuple[int, str]:
        raise AssertionError((argv, cwd))

    assert _postmortem_cli.cmd_postmortem_dry_run("free", runner=tutor) == 2
    assert capsys.readouterr().out.startswith("refused: free has no tutor theory")
    assert not _unit_finish.PREVIEW_FILE.exists()


def test_the_flag_selects_the_command(monkeypatch):
    """``--postmortem-dry-run UNIT`` is the chosen command, with UNIT passed on."""
    got: list[str] = []

    def fake(unit: str) -> int:
        got.append(unit)
        return 0

    monkeypatch.setattr("leetcode_guard._cli_args.cmd_postmortem_dry_run", fake)
    args = build_parser().parse_args(["--postmortem-dry-run", "prefix-sums"])
    run = chosen_command(args)

    assert run is not None
    assert run() == 0
    assert got == ["prefix-sums"]
