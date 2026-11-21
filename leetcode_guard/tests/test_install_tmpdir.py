"""install.sh keeps pip's scratch space off the shared /tmp tmpfs.

pip clones the whole kuhyx/utils monorepo (~125 MB checked out) once per pinned
``git+`` dependency, seven times per install. On 2026-11-21 the seventh clone
hit a full /tmp ("unable to write file", ``install: FAILED -- pip install``)
and the deploy went red. These tests run the real ``main`` from a sandbox copy
of install.sh: every other step is a no-op and the "python" only records the
TMPDIR it was given.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
_STEPS = (
    "link_leetcode_coach.sh",
    "install_nudge_extension.sh",
    "setup_mcp.sh",
)
_FAKE_PYTHON = '#!/bin/bash\nprintf "%s\\n" "$TMPDIR" >> "$TMP_LOG"\n'


def _run_main(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "install.sh", repo / "install.sh")
    shutil.copy(REPO / "scripts/install_mcp_phase.sh", repo / "scripts")
    for name in _STEPS:
        step = repo / "scripts" / name
        step.write_text('#!/bin/bash\nprintf "%s\\n" "$TMPDIR" >> "$TMP_LOG"\n')
        step.chmod(0o755)
    python = tmp_path / "python3"
    python.write_text(_FAKE_PYTHON)
    python.chmod(0o755)
    log = tmp_path / "tmpdirs.log"
    shared_tmp = tmp_path / "shared-tmp"
    shared_tmp.mkdir()
    stubs = "; ".join(
        f"{fn}() {{ :; }}"
        for fn in (
            "preserve_editable",
            "verify_imports",
            "ensure_hmac_key",
            "install_units",
            "install_coach_relay",
            "install_tray",
        )
    )
    proc = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f'source "$1"; {stubs}; main',
            "bash",
            str(repo / "install.sh"),
        ],
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(shared_tmp),  # stands in for the /tmp tmpfs
            "TMP_LOG": str(log),
            "INSTALL_PYTHON": str(python),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, log.read_text().splitlines() if log.exists() else []


def test_pip_and_every_step_get_a_disk_tmpdir(tmp_path: Path) -> None:
    """Not /tmp: the tmpfs other jobs fill until a utils clone no longer fits."""
    proc, seen = _run_main(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert seen
    cache = str(tmp_path / ".cache")
    assert all(d.startswith(cache) for d in seen), seen


def test_the_scratch_dir_is_removed_afterwards(tmp_path: Path) -> None:
    """Seven utils clones per run must not pile up in ~/.cache either."""
    proc, seen = _run_main(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert not any(Path(d).exists() for d in seen), seen
