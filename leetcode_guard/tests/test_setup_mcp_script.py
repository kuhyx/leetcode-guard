"""Tests for scripts/setup_mcp.sh, the MCP venv step of every deploy.

``pip install -e .[mcp]`` re-clones the git dependencies on every call, ~25 s
of an ~80 s deploy (2026-11-21), though an editable install only needs
redoing when pyproject.toml changes. The venv python here is a fake under a
throwaway HOME that logs its args and fails the import probe on request.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") or "/usr/bin/bash"
_FAKE_PYTHON = """#!/bin/bash
echo "$*" >> "$FAKE_LOG"
[[ "$1" == -c && -n "${FAKE_IMPORT_FAIL:-}" ]] && exit 1
exit 0
"""


@dataclass(frozen=True)
class Sandbox:
    """A repo copy with a pyproject and a fake venv python."""

    repo: Path
    env: dict[str, str]
    log: Path

    def run(self, **extra: str) -> subprocess.CompletedProcess[str]:
        """Run setup_mcp.sh and return the finished process."""
        return subprocess.run(
            [BASH, str(self.repo / "scripts" / "setup_mcp.sh")],
            env={**self.env, **extra},
            capture_output=True,
            text=True,
            check=False,
        )

    def installs(self) -> int:
        """How many editable installs the fake python saw."""
        rows = (
            self.log.read_text(encoding="utf-8").splitlines()
            if self.log.exists()
            else []
        )
        return sum(1 for row in rows if row.startswith("-m pip install --quiet -e"))


def _sandbox(tmp_path: Path) -> Sandbox:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "setup_mcp.sh", repo / "scripts")
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    home = tmp_path / "home"
    bin_dir = home / ".venvs" / "leetcode-guard-mcp" / "bin"
    bin_dir.mkdir(parents=True)
    fake = bin_dir / "python"
    fake.write_text(_FAKE_PYTHON, encoding="utf-8")
    fake.chmod(0o755)
    log = tmp_path / "python.log"
    env = {**os.environ, "HOME": str(home), "FAKE_LOG": str(log)}
    return Sandbox(repo, env, log)


def test_the_install_runs_only_when_its_inputs_change(tmp_path: Path) -> None:
    """Install once, skip on the same pyproject, redo on a bump."""
    box = _sandbox(tmp_path)
    runs = [box.run()]
    runs.append(box.run())
    assert "unchanged" in runs[-1].stderr
    pyproject = box.repo / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8") + "# bump\n", encoding="utf-8"
    )
    runs.append(box.run())
    assert [run.returncode for run in runs] == [0, 0, 0]
    assert box.installs() == 2


def test_a_broken_venv_is_reinstalled_not_vouched_for(tmp_path: Path) -> None:
    """A matching stamp with a failing import probe still reinstalls."""
    box = _sandbox(tmp_path)
    box.run()
    broken = box.run(FAKE_IMPORT_FAIL="1")
    assert (broken.returncode, box.installs()) == (1, 2)
