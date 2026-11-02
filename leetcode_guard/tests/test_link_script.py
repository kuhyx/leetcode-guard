"""Tests for scripts/link_leetcode_coach.sh, the install step for the coach.

Run against a throwaway HOME: the script must never be pointed at the real
~/.claude from a test. The coach package dir is a fake one in tmp
(``LEETCODE_COACH_DIR``), except in the test of the real lookup.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "link_leetcode_coach.sh"
SYSTEM_PYTHON = "/usr/bin/python3"
PROBE = "import leetcode_coach, os; print(os.path.dirname(leetcode_coach.__file__))"


def _run(home: Path, coach: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    if coach is None:
        env["PYTHONUSERBASE"] = str(Path.home() / ".local")
    else:
        env["LEETCODE_COACH_DIR"] = str(coach)
    return subprocess.run(
        [str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


@pytest.fixture
def coach(tmp_path: Path) -> Path:
    """A stand-in for the installed package dir: the skill body and the launcher."""
    root = tmp_path.parent / f"{tmp_path.name}-coach"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: leetcode\n---\n", encoding="utf-8")
    launcher = root / "leetcode"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    return root.resolve()


def _old_skill(home: Path) -> Path:
    old = home / ".claude" / "skills" / "leetcode"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text("---\nname: leetcode\n---\n", encoding="utf-8")
    (old / "leetcode_repl.py").write_text("", encoding="utf-8")
    return old


def test_fresh_home_gets_both_links(tmp_path: Path, coach: Path) -> None:
    proc = _run(tmp_path, coach)
    assert proc.returncode == 0, proc.stderr
    skill = tmp_path / ".claude" / "skills" / "leetcode"
    assert skill.is_symlink()
    assert skill.resolve() == coach
    assert (tmp_path / ".local" / "bin" / "leetcode").resolve() == coach / "leetcode"
    assert _run(tmp_path, coach).returncode == 0  # idempotent


def test_old_skill_dir_is_backed_up_outside_skills(tmp_path: Path, coach: Path) -> None:
    _old_skill(tmp_path)
    bin_link = tmp_path / ".local" / "bin" / "leetcode"
    bin_link.parent.mkdir(parents=True)
    bin_link.symlink_to(tmp_path / ".claude" / "skills" / "leetcode" / "leetcode")
    proc = _run(tmp_path, coach)
    assert proc.returncode == 0, proc.stderr
    backups = list((tmp_path / ".claude" / "backups").glob("skill-leetcode-*"))
    assert len(backups) == 1
    assert (backups[0] / "leetcode_repl.py").is_file()
    assert sorted(p.name for p in (tmp_path / ".claude" / "skills").iterdir()) == [
        "leetcode"
    ]
    assert (tmp_path / ".claude" / "skills" / "leetcode").resolve() == coach
    assert bin_link.resolve() == coach / "leetcode"


def test_existing_symlink_is_repointed(tmp_path: Path, coach: Path) -> None:
    skills = tmp_path / ".claude" / "skills"
    skills.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (skills / "leetcode").symlink_to(elsewhere)
    assert _run(tmp_path, coach).returncode == 0
    assert (skills / "leetcode").resolve() == coach
    assert list(elsewhere.iterdir()) == []


def test_unknown_directory_is_refused(tmp_path: Path, coach: Path) -> None:
    other = tmp_path / ".claude" / "skills" / "leetcode"
    other.mkdir(parents=True)
    (other / "notes.txt").write_text("mine", encoding="utf-8")
    proc = _run(tmp_path, coach)
    assert proc.returncode == 1
    assert "not replacing it" in proc.stderr
    assert (other / "notes.txt").is_file()
    assert not other.is_symlink()


def test_regular_file_at_the_command_is_refused(tmp_path: Path, coach: Path) -> None:
    bin_file = tmp_path / ".local" / "bin" / "leetcode"
    bin_file.parent.mkdir(parents=True)
    bin_file.write_text("#!/bin/sh\n", encoding="utf-8")
    proc = _run(tmp_path, coach)
    assert proc.returncode == 1
    assert not bin_file.is_symlink()


def test_without_an_override_it_links_what_the_system_python_imports(
    tmp_path: Path,
) -> None:
    user_base = {"PYTHONUSERBASE": str(Path.home() / ".local")}
    probe = subprocess.run(
        [SYSTEM_PYTHON, "-P", "-c", PROBE],
        env=user_base,
        capture_output=True,
        text=True,
        check=False,
        cwd="/",
    )
    if probe.returncode != 0:
        pytest.skip("the system python has no leetcode_coach (CI)")
    installed = Path(probe.stdout.strip()).resolve()
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / ".claude" / "skills" / "leetcode").resolve() == installed
    assert os.access(installed / "leetcode", os.X_OK)
