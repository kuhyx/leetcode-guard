"""install.sh skips the user-site ``pip install -e`` when nothing it reads changed.

The install is editable, so only pyproject.toml (deps, pins) or a moved repo
needs it redone; running it every deploy re-cloned the utils monorepo per git
pin. The real ``install_package``/``verify_imports``/``main`` run from a
sandbox copy; the "python" logs its args and fails imports on request.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

import pytest

from leetcode_guard.tests._stamp_fixtures import assert_damaged_stamp_reinstalls

REPO = Path(__file__).resolve().parents[2]
_STEPS = ("link_leetcode_coach.sh", "install_nudge_extension.sh", "setup_mcp.sh")
_STUBS = "; ".join(
    f"{fn}() {{ :; }}"
    for fn in (
        "preserve_editable",
        "ensure_hmac_key",
        "install_units",
        "install_coach_relay",
        "install_tray",
    )
)
_FAKE_PYTHON = """#!/bin/bash
echo "$*" >> "$PY_LOG"
[[ "$*" == "-m pip list"* ]] && cat "$SITE_LISTING" 2>/dev/null
[[ "$1" == -c && -n "${FAKE_IMPORT_FAIL:-}" ]] && exit 1
if [[ "$*" == "-m pip install --user"*"/repo" ]]; then
  [[ -n "${FAKE_PIP_FAIL:-}" ]] && exit 1
  if [[ -n "${RDV:-}" ]]; then  # meet the MCP setup: only side by side do both see the other
    touch "$RDV/pip_started"
    for _ in {1..60}; do [[ -e "$RDV/mcp_started" ]] && touch "$RDV/pip_saw_mcp" && break; sleep 0.05; done
  fi
fi
exit 0
"""


@dataclass(frozen=True)
class Sandbox:
    """A copy of install.sh with a pyproject and a fake system python."""

    root: Path

    @property
    def repo(self) -> Path:
        """The sandbox checkout."""
        return self.root / "repo"

    @property
    def stamp(self) -> Path:
        """Where install.sh records the last verified install."""
        return self.root / ".local/state/leetcode-guard/install.sha256"

    def run(
        self,
        *args: str,
        import_fail: bool = False,
        pip_fail: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run install.sh's main with every unrelated step stubbed."""
        env = {
            "HOME": str(self.root),
            "PATH": "/usr/bin:/bin",
            "PY_LOG": str(self.root / "py.log"),
            "INSTALL_PYTHON": str(self.root / "python3"),
            "SITE_LISTING": str(self.root / "site.txt"),
        }
        if import_fail:
            env["FAKE_IMPORT_FAIL"] = "1"
        if pip_fail:
            env["FAKE_PIP_FAIL"] = "1"
        env.update(extra_env or {})
        return subprocess.run(
            [
                "/bin/bash",
                "-c",
                f'source "$1"; shift; {_STUBS}; main "$@"',
                "bash",
                str(self.repo / "install.sh"),
                *args,
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def installs(self) -> int:
        """How many editable installs of the repo the fake python saw."""
        log = self.root / "py.log"
        rows = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return sum(
            1
            for row in rows
            if row.startswith("-m pip install --user") and row.endswith(str(self.repo))
        )


def _sandbox(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path)
    (box.repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "install.sh", box.repo / "install.sh")
    shutil.copy(REPO / "scripts/install_mcp_phase.sh", box.repo / "scripts")
    (box.repo / "pyproject.toml").write_text(
        "[project]\nname = 'x'\n", encoding="utf-8"
    )
    for name in _STEPS:
        step = box.repo / "scripts" / name
        step.write_text("#!/bin/bash\n", encoding="utf-8")
        step.chmod(0o755)
    python = tmp_path / "python3"
    python.write_text(_FAKE_PYTHON, encoding="utf-8")
    python.chmod(0o755)
    return box


def test_an_unchanged_pyproject_skips_the_pip_install(tmp_path: Path) -> None:
    """The second deploy of the same pyproject goes straight to verifying."""
    box = _sandbox(tmp_path)
    assert box.run().returncode == 0
    second = box.run()
    assert second.returncode == 0, second.stderr
    assert "unchanged" in second.stderr
    assert box.installs() == 1


def test_a_pyproject_change_reinstalls(tmp_path: Path) -> None:
    """A pin bump must reach the system python."""
    box = _sandbox(tmp_path)
    assert box.run().returncode == 0
    (box.repo / "pyproject.toml").write_text(
        "[project]\nname = 'y'\n", encoding="utf-8"
    )
    assert box.run().returncode == 0
    assert box.installs() == 2


def test_failed_imports_reinstall_and_never_stamp(tmp_path: Path) -> None:
    """A stamp never vouches for a site whose imports fail."""
    box = _sandbox(tmp_path)
    assert box.run(import_fail=True).returncode != 0
    assert box.run().returncode == 0
    assert box.run(import_fail=True).returncode != 0
    assert box.installs() == 3


def test_another_install_changing_the_user_site_reinstalls(tmp_path: Path) -> None:
    """Another locker swapping a shared dependency puts our pins back."""
    box = _sandbox(tmp_path)
    assert box.run().returncode == 0
    (tmp_path / "site.txt").write_text("sickdays==0.5.5\n", encoding="utf-8")
    assert box.run().returncode == 0
    assert box.installs() == 2


def test_a_failed_pip_install_leaves_no_stamp(tmp_path: Path) -> None:
    """The stamp goes before pip starts, so a failed install is never vouched for."""
    box = _sandbox(tmp_path)
    assert box.run().returncode == 0
    assert box.stamp.exists()
    (box.repo / "pyproject.toml").write_text(
        "[project]\nname = 'y'\n", encoding="utf-8"
    )
    assert box.run(pip_fail=True).returncode != 0
    assert not box.stamp.exists()
    assert box.run().returncode == 0
    assert box.installs() == 3


def test_the_import_check_runs_when_pip_is_skipped(tmp_path: Path) -> None:
    """A skipped pip phase still ends in the verifying import."""
    box = _sandbox(tmp_path)
    assert box.run().returncode == 0
    (tmp_path / "py.log").unlink()
    assert box.run().returncode == 0
    assert box.installs() == 0
    log = (tmp_path / "py.log").read_text(encoding="utf-8")
    assert "imports OK" in log


@pytest.mark.parametrize("damage", ["delete", "garbage", "empty", "unreadable"])
def test_a_missing_or_unreadable_stamp_reinstalls(tmp_path: Path, damage: str) -> None:
    """Fail closed: anything but a readable, matching stamp means pip runs."""
    assert_damaged_stamp_reinstalls(_sandbox(tmp_path), damage)
