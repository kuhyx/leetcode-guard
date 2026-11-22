"""``open_cli`` opens the lock's FIRST ACTION: the tutor in THEORY, else a problem.

The tutor is a fake ``tutor`` on a scratch ``PATH`` (``HOME`` is scratch too, so
the ``~/.local/bin`` fallback can never find the real one) and ``Popen`` is
recorded, never run: nothing here starts a window.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from leetcode_guard import _browser, open_cli
from leetcode_guard.tests._tutor_fixtures import ALGO
from leetcode_guard.tests.test_open_cli import FIRST, NONE_VIEW, _cache, _launcher

if TYPE_CHECKING:
    import pytest

THEORY = replace(
    NONE_VIEW, unit="a", phase="theory", lessons_ready=True, learn_target=(ALGO, "a")
)
SOLVE = replace(NONE_VIEW, unit="a", phase="solve", total=1)


def fake_tutor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, present: bool = True
) -> Path:
    """A scratch PATH and HOME; with ``present``, an executable ``tutor`` on it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tutor = bin_dir / "tutor"
    if present:
        tutor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tutor.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    return tutor


def spawns(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> list[object]:
    """Record every command ``_browser`` would start; ``fail`` makes it raise."""
    seen: list[object] = []

    def popen(command: object, **_kwargs: object) -> None:
        seen.append(command)
        if fail:
            raise OSError(2, "gone")

    monkeypatch.setattr(_browser.subprocess, "Popen", popen)
    return seen


def test_theory_opens_the_tutor_on_the_learn_route_and_no_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The same ``tutor --route`` call the lock's learn button makes."""
    _cache(monkeypatch, FIRST, view=THEORY)
    opened = _launcher(monkeypatch, ok=True)
    tutor = fake_tutor(monkeypatch, tmp_path)
    seen = spawns(monkeypatch)

    assert open_cli.main() == open_cli.EXIT_OPENED
    assert seen == [(str(tutor), "--route", f"/learn/{ALGO}/a")]
    assert opened == []


def test_theory_without_lessons_opens_the_plan_screen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Lessons not made yet: the plan screen, exactly like the learn button."""
    _cache(monkeypatch, FIRST, view=replace(THEORY, lessons_ready=False))
    _launcher(monkeypatch, ok=True)
    tutor = fake_tutor(monkeypatch, tmp_path)
    seen = spawns(monkeypatch)

    assert open_cli.main() == open_cli.EXIT_OPENED
    assert seen == [(str(tutor), "--route", f"/plan/{ALGO}")]


def test_solve_opens_the_first_problem_and_never_the_tutor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """SOLVE: no theory anywhere, so the first action is the first problem."""
    _cache(monkeypatch, FIRST, view=SOLVE)
    opened = _launcher(monkeypatch, ok=True)
    fake_tutor(monkeypatch, tmp_path)
    seen = spawns(monkeypatch)

    assert open_cli.main() == open_cli.EXIT_OPENED
    assert opened == [FIRST]
    assert seen == []


def test_a_missing_tutor_falls_back_to_the_first_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """No launcher: a warning, and the row still opens something."""
    _cache(monkeypatch, FIRST, view=THEORY)
    opened = _launcher(monkeypatch, ok=True)
    fake_tutor(monkeypatch, tmp_path, present=False)
    seen = spawns(monkeypatch)

    with caplog.at_level(logging.WARNING):
        assert open_cli.main() == open_cli.EXIT_OPENED
    assert opened == [FIRST]
    assert seen == []
    assert "opening the first problem instead" in caplog.text


def test_a_tutor_that_cannot_start_falls_back_to_the_first_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """The spawn raises: logged at warning, then the first problem."""
    _cache(monkeypatch, FIRST, view=THEORY)
    opened = _launcher(monkeypatch, ok=True)
    fake_tutor(monkeypatch, tmp_path)
    spawns(monkeypatch, fail=True)

    with caplog.at_level(logging.WARNING):
        assert open_cli.main() == open_cli.EXIT_OPENED
    assert opened == [FIRST]
    assert "opening the first problem instead" in caplog.text
