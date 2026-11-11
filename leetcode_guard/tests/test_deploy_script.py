"""Tests for scripts/deploy.sh, the `- deploy:` line in CLAUDE.md.

Never touches the real deployment: the live clone is a throwaway git clone in
tmp (``DEPLOY_LIVE_DIR``), and ``systemctl``, ``curl`` and the system python
are fakes on ``PATH`` that log every call. The fake ``install.sh`` inside the
clone only records that it ran.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy.sh"
GIT = shutil.which("git") or "/usr/bin/git"

# systemctl: logs args; `show ... ActiveEnterTimestamp` answers "now" so the
# freshness check passes unless FAKE_STALE is set; `is-active` fails for the
# unit named in FAKE_DEAD; timers report a next elapse.
_FAKE_SYSTEMCTL = """#!/bin/bash
echo "systemctl $*" >> "$FAKE_LOG"
case "$*" in
  *is-active*) [[ -n "${FAKE_DEAD:-}" && "$*" == *"$FAKE_DEAD"* ]] && exit 3; echo active ;;
  *ActiveEnterTimestamp*) if [[ -n "${FAKE_STALE:-}" ]]; then echo @1; else echo "@$(date +%s)"; fi ;;
  *NextElapse*) echo "NextElapseUSecRealtime="; echo "NextElapseUSecMonotonic=1min" ;;
esac
"""
_FAKE_CURL = """#!/bin/bash
echo "curl $*" >> "$FAKE_LOG"
[[ -n "${FAKE_CURL_FAIL:-}" && "$*" == *"$FAKE_CURL_FAIL"* ]] && exit 7
case "$*" in
  *8771*) echo '{"ok": true, "service": "leetcode-guard-web"}' ;;
  *) echo '{"beat": 1}' ;;
esac
"""
_FAKE_PYTHON = """#!/bin/bash
echo "python $*" >> "$FAKE_LOG"
echo "$FAKE_IMPORT_FILE"
"""


@dataclass(frozen=True)
class Env:
    """One sandbox: origin repo, live clone, fake bin dir and call log."""

    origin: Path
    live: Path
    log: Path
    env: dict[str, str]


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        [GIT, "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture(name="sandbox")
def fixture_sandbox(tmp_path: Path) -> Env:
    """A bare origin, a clean live clone of it, and the fakes."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "config", "user.email", "t@t")
    _git(seed, "config", "user.name", "t")
    _exe(seed / "install.sh", '#!/bin/bash\necho "install.sh" >> "$FAKE_LOG"\n')
    _git(seed, "add", ".")
    _git(seed, "commit", "-qm", "one")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    live = tmp_path / "live"
    _git(tmp_path, "clone", "-q", str(origin), str(live))
    _git(live, "config", "user.email", "t@t")
    _git(live, "config", "user.name", "t")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _exe(fake_bin / "systemctl", _FAKE_SYSTEMCTL)
    _exe(fake_bin / "curl", _FAKE_CURL)
    _exe(fake_bin / "fakepython", _FAKE_PYTHON)
    log = tmp_path / "calls.log"
    log.touch()
    env = {
        "HOME": str(tmp_path),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "FAKE_LOG": str(log),
        "FAKE_IMPORT_FILE": str(live / "leetcode_guard" / "__init__.py"),
        "DEPLOY_LIVE_DIR": str(live),
        "DEPLOY_PYTHON": str(fake_bin / "fakepython"),
        "DEPLOY_HEALTH_TIMEOUT": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return Env(origin=origin, live=live, log=log, env=env)


def _push_new_commit(sandbox: Env, tmp_path: Path) -> str:
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(sandbox.origin), str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "new.txt").write_text("x", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-qm", "two")
    _git(work, "push", "-q", "origin", "main")
    return _git(work, "rev-parse", "HEAD").strip()


def _run(sandbox: Env, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT)],
        env={**sandbox.env, **extra},
        capture_output=True,
        text=True,
        check=False,
    )


def test_pulls_installs_restarts_and_passes(sandbox: Env, tmp_path: Path) -> None:
    """C1: a clean clone behind origin is fast-forwarded and deployed."""
    head = _push_new_commit(sandbox, tmp_path)
    proc = _run(sandbox)
    assert proc.returncode == 0, proc.stderr
    assert _git(sandbox.live, "rev-parse", "HEAD").strip() == head
    calls = sandbox.log.read_text(encoding="utf-8")
    assert "install.sh" in calls
    assert (
        "systemctl --user restart leetcode-guard-web.service"
        " leetcode-coach-relay.service" in calls
    )
    assert "health OK" in proc.stderr


def test_never_starts_the_lock_service(sandbox: Env) -> None:
    """C8: leetcode-guard.service would pop a lock on the live display."""
    proc = _run(sandbox)
    assert proc.returncode == 0, proc.stderr
    for line in sandbox.log.read_text(encoding="utf-8").splitlines():
        if line.startswith("systemctl") and any(
            verb in line for verb in (" start", " restart")
        ):
            assert " leetcode-guard.service" not in line, line


def test_dirty_clone_refuses_and_keeps_the_edit(sandbox: Env) -> None:
    """C5: an uncommitted edit stops the deploy before any install."""
    edit = sandbox.live / "install.sh"
    edit.write_text(edit.read_text(encoding="utf-8") + "# mine\n", encoding="utf-8")
    proc = _run(sandbox)
    assert proc.returncode != 0
    assert "dirty" in proc.stderr
    assert "# mine" in edit.read_text(encoding="utf-8")
    assert "install.sh" not in sandbox.log.read_text(encoding="utf-8")


def test_diverged_clone_refuses(sandbox: Env, tmp_path: Path) -> None:
    """A local commit the origin lacks is not a fast-forward: fail, no reset."""
    _push_new_commit(sandbox, tmp_path)
    (sandbox.live / "local.txt").write_text("y", encoding="utf-8")
    _git(sandbox.live, "add", ".")
    _git(sandbox.live, "commit", "-qm", "local")
    local = _git(sandbox.live, "rev-parse", "HEAD").strip()
    proc = _run(sandbox)
    assert proc.returncode != 0
    assert "fast-forward" in proc.stderr
    assert _git(sandbox.live, "rev-parse", "HEAD").strip() == local


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        ({"FAKE_CURL_FAIL": "8771"}, "web"),
        ({"FAKE_CURL_FAIL": "8777"}, "relay"),
        ({"FAKE_DEAD": "leetcode-guard-harvest.timer"}, "harvest.timer"),
        ({"FAKE_STALE": "1"}, "not restarted"),
        ({"FAKE_IMPORT_FILE": "/elsewhere/leetcode_guard/__init__.py"}, "imports"),
    ],
)
def test_failing_health_check_is_named(
    sandbox: Env, extra: dict[str, str], named: str
) -> None:
    """C6: any failed health check exits non-zero and says which one."""
    proc = _run(sandbox, **extra)
    assert proc.returncode != 0
    assert named in proc.stderr


def test_rerun_is_idempotent(sandbox: Env) -> None:
    """C7: two runs in a row both pass; the second moves nothing in git."""
    first = _run(sandbox)
    before = _git(sandbox.live, "rev-parse", "HEAD")
    second = _run(sandbox)
    assert (first.returncode, second.returncode) == (0, 0), second.stderr
    assert _git(sandbox.live, "rev-parse", "HEAD") == before
    assert not _git(sandbox.live, "status", "--porcelain")


def test_claude_md_names_the_script() -> None:
    """C10: Ship runs exactly this line."""
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "- deploy: `scripts/deploy.sh`" in text
    assert os.access(SCRIPT, os.X_OK)
