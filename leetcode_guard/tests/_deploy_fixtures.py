"""The throwaway deployment that ``scripts/deploy.sh`` tests run against.

Never touches the real deployment: the live clone is a throwaway git clone in
tmp (``DEPLOY_LIVE_DIR``), and ``systemctl``, ``curl`` and the system python
are fakes on ``PATH`` that log every call. The fake ``install.sh`` inside the
clone only records that it ran. The lock's cgroup is a directory in tmp
(``DEPLOY_CGROUP_ROOT``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy.sh"
GIT = shutil.which("git") or "/usr/bin/git"

# systemctl: logs args; `show ... ActiveEnterTimestamp` answers "now" so the
# freshness check passes unless FAKE_STALE is set; `is-active` fails for the
# unit named in FAKE_DEAD; timers report a next elapse. The lock unit's
# MemorySwapMax reads FAKE_SWAP_MAX (default 0) and its cgroup is /lock.
_FAKE_SYSTEMCTL = """#!/bin/bash
echo "systemctl $*" >> "$FAKE_LOG"
case "$*" in
  *is-active*) [[ -n "${FAKE_DEAD:-}" && "$*" == *"$FAKE_DEAD"* ]] && exit 3; echo active ;;
  *ActiveEnterTimestamp*) if [[ -n "${FAKE_STALE:-}" ]]; then echo @1; else echo "@$(date +%s)"; fi ;;
  *NextElapse*) echo "NextElapseUSecRealtime="; echo "NextElapseUSecMonotonic=1min" ;;
  *MemorySwapMax*) echo "${FAKE_SWAP_MAX-0}" ;;
  *ControlGroup*) echo /lock ;;
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


def git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd`` and return its stdout."""
    return subprocess.run(
        [GIT, "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def make_sandbox(tmp_path: Path) -> Env:
    """A bare origin, a clean live clone of it, and the fakes."""
    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init", "-q", "-b", "main")
    git(seed, "config", "user.email", "t@t")
    git(seed, "config", "user.name", "t")
    _exe(seed / "install.sh", '#!/bin/bash\necho "install.sh $*" >> "$FAKE_LOG"\n')
    (seed / "app").mkdir()
    (seed / "app" / "pubspec.yaml").write_text("name: app\n", encoding="utf-8")
    git(seed, "add", ".")
    git(seed, "commit", "-qm", "one")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    live = tmp_path / "live"
    git(tmp_path, "clone", "-q", str(origin), str(live))
    git(live, "config", "user.email", "t@t")
    git(live, "config", "user.name", "t")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _exe(fake_bin / "systemctl", _FAKE_SYSTEMCTL)
    _exe(fake_bin / "curl", _FAKE_CURL)
    _exe(fake_bin / "fakepython", _FAKE_PYTHON)
    cgroup = tmp_path / "cgroup" / "lock"
    cgroup.mkdir(parents=True)
    (cgroup / "memory.swap.max").write_text("0\n", encoding="utf-8")
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
        "DEPLOY_CGROUP_ROOT": str(tmp_path / "cgroup"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return Env(origin=origin, live=live, log=log, env=env)


def push_new_commit(sandbox: Env, tmp_path: Path, name: str = "new.txt") -> str:
    """Push one new commit to the origin; return its hash."""
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(sandbox.origin), str(work))
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    (work / name).write_text("x", encoding="utf-8")
    git(work, "add", ".")
    git(work, "commit", "-qm", "two")
    git(work, "push", "-q", "origin", "main")
    return git(work, "rev-parse", "HEAD").strip()


def run_deploy(sandbox: Env, **extra: str) -> subprocess.CompletedProcess[str]:
    """Run deploy.sh in the sandbox, with ``extra`` env on top."""
    return subprocess.run(
        [str(SCRIPT)],
        env={**sandbox.env, **extra},
        capture_output=True,
        text=True,
        check=False,
    )
