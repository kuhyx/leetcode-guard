"""Tests for scripts/deploy.sh, the `- deploy:` line in CLAUDE.md.

The sandbox (fake systemctl, curl, python; throwaway clone) lives in
``_deploy_fixtures``.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from leetcode_guard.tests._deploy_fixtures import (
    REPO,
    SCRIPT,
    Env,
    git,
    make_sandbox,
    push_new_commit,
    run_deploy,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="sandbox")
def fixture_sandbox(tmp_path: Path) -> Env:
    """A bare origin, a clean live clone of it, and the fakes."""
    return make_sandbox(tmp_path)


def test_pulls_installs_restarts_and_passes(sandbox: Env, tmp_path: Path) -> None:
    """C1: a clean clone behind origin is fast-forwarded and deployed."""
    head = push_new_commit(sandbox, tmp_path)
    proc = run_deploy(sandbox)
    assert proc.returncode == 0, proc.stderr
    assert git(sandbox.live, "rev-parse", "HEAD").strip() == head
    calls = sandbox.log.read_text(encoding="utf-8")
    assert "install.sh" in calls
    assert (
        "systemctl --user restart leetcode-guard-web.service"
        " leetcode-coach-relay.service" in calls
    )
    assert "health OK" in proc.stderr


def test_force_reaches_install(sandbox: Env) -> None:
    """`deploy.sh --force` is the full-reinstall path; a plain run passes nothing."""
    assert run_deploy(sandbox).returncode == 0
    assert "install.sh --force" not in sandbox.log.read_text(encoding="utf-8")
    proc = subprocess.run([str(SCRIPT), "--force"], env=sandbox.env, check=False)
    assert proc.returncode == 0
    assert "install.sh --force" in sandbox.log.read_text(encoding="utf-8")


def test_never_starts_the_lock_service(sandbox: Env) -> None:
    """C8: leetcode-guard.service would pop a lock on the live display."""
    proc = run_deploy(sandbox)
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
    proc = run_deploy(sandbox)
    assert proc.returncode != 0
    assert "dirty" in proc.stderr
    assert "# mine" in edit.read_text(encoding="utf-8")
    assert "install.sh" not in sandbox.log.read_text(encoding="utf-8")


def test_an_app_edit_does_not_block_the_deploy(sandbox: Env, tmp_path: Path) -> None:
    """The Flutter app under app/ is not deployed here; another session's
    uncommitted edit there is pulled past and kept (2026-11-21 red deploy)."""
    head = push_new_commit(sandbox, tmp_path)
    edit = sandbox.live / "app" / "pubspec.yaml"
    edit.write_text("name: mine\n", encoding="utf-8")
    proc = run_deploy(sandbox)
    assert proc.returncode == 0, proc.stderr
    assert git(sandbox.live, "rev-parse", "HEAD").strip() == head
    assert edit.read_text(encoding="utf-8") == "name: mine\n"


def test_an_app_edit_the_pull_would_overwrite_refuses(
    sandbox: Env, tmp_path: Path
) -> None:
    """git refuses to overwrite it; the deploy stops before any install."""
    push_new_commit(sandbox, tmp_path, "app/pubspec.yaml")
    edit = sandbox.live / "app" / "pubspec.yaml"
    edit.write_text("name: mine\n", encoding="utf-8")
    proc = run_deploy(sandbox)
    assert proc.returncode != 0
    assert edit.read_text(encoding="utf-8") == "name: mine\n"
    assert "install.sh" not in sandbox.log.read_text(encoding="utf-8")


def test_diverged_clone_refuses(sandbox: Env, tmp_path: Path) -> None:
    """A local commit the origin lacks is not a fast-forward: fail, no reset."""
    push_new_commit(sandbox, tmp_path)
    (sandbox.live / "local.txt").write_text("y", encoding="utf-8")
    git(sandbox.live, "add", ".")
    git(sandbox.live, "commit", "-qm", "local")
    local = git(sandbox.live, "rev-parse", "HEAD").strip()
    proc = run_deploy(sandbox)
    assert proc.returncode != 0
    assert "fast-forward" in proc.stderr
    assert git(sandbox.live, "rev-parse", "HEAD").strip() == local


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
    proc = run_deploy(sandbox, **extra)
    assert proc.returncode != 0
    assert named in proc.stderr


def test_rerun_is_idempotent(sandbox: Env) -> None:
    """C7: two runs in a row both pass; the second moves nothing in git."""
    first = run_deploy(sandbox)
    before = git(sandbox.live, "rev-parse", "HEAD")
    second = run_deploy(sandbox)
    assert (first.returncode, second.returncode) == (0, 0), second.stderr
    assert git(sandbox.live, "rev-parse", "HEAD") == before
    assert not git(sandbox.live, "status", "--porcelain")


def test_claude_md_names_the_script() -> None:
    """C10: Ship runs exactly this line."""
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "- deploy: `scripts/deploy.sh`" in text
    assert os.access(SCRIPT, os.X_OK)
