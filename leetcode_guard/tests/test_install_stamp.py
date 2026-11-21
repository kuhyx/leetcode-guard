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

    def run(self, *, import_fail: bool = False) -> subprocess.CompletedProcess[str]:
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
        return subprocess.run(
            [
                "/bin/bash",
                "-c",
                f'source "$1"; {_STUBS}; main',
                "bash",
                str(self.repo / "install.sh"),
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
