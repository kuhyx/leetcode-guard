"""run.sh reuses install.sh's dependency steps by sourcing them.

It called ``preserve_editable_gatelock``, which install.sh stopped defining
when the restore became ``preserve_editable <module> <src>`` (f7edb52): the
call died with "command not found" and, because the pip step before it had
already run, ``./run.sh`` stopped half-way. The fake python logs its args.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
_FAKE_PYTHON = '#!/bin/bash\necho "$*" >> "$PY_LOG"\nexit 0\n'


def _run(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for name in ("run.sh", "install.sh", "scripts/install_mcp_phase.sh"):
        shutil.copy(REPO / name, repo / name)
    python = tmp_path / "python3"
    python.write_text(_FAKE_PYTHON, encoding="utf-8")
    python.chmod(0o755)
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    for name in ("gatelock", "leetcode_coach"):
        (tmp_path / "src/utils" / name).mkdir(parents=True)
    log = tmp_path / "py.log"
    proc = subprocess.run(
        ["/bin/bash", str(repo / "run.sh")],
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "PY_LOG": str(log),
            "INSTALL_PYTHON": str(python),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_run_sh_restores_both_editable_installs_then_shows_the_status(
    tmp_path: Path,
) -> None:
    """The dependency step ends in the restore of gatelock and leetcode_coach."""
    proc, calls = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    for name in ("gatelock", "leetcode_coach"):
        src = f"{tmp_path}/src/utils/{name}"
        restore = f"-m pip install --user --break-system-packages -q --no-deps -e {src}"
        assert restore in calls
    assert calls[-1].startswith("-m leetcode_guard --status")


def test_the_docs_name_the_function_install_sh_defines() -> None:
    """AGENTS.md pointed at a function that no longer exists."""
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "preserve_editable_gatelock" not in text
    assert "`preserve_editable`" in text
