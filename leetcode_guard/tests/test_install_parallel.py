"""install.sh runs its two pip phases side by side, and ``--force`` reinstalls.

Sequential, the system-python phase (~31 s) and the MCP venv phase (~28 s)
plus the rest put ``scripts/deploy.sh`` over the 60 s action cap (68 s,
2026-11-21). The sandbox is test_install_stamp's: real ``main`` from a copy of
install.sh, a fake system python, and a stub ``setup_mcp.sh`` per test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard.tests.test_install_stamp import Sandbox, _sandbox

if TYPE_CHECKING:
    from pathlib import Path

# Meets the fake system pip (see test_install_stamp._FAKE_PYTHON): pip leaves
# pip_saw_mcp only when the MCP setup had started while pip was running.
_MCP_MEETS_PIP = """#!/bin/bash
touch "$RDV/mcp_started"
sleep 0.3
echo "mcp-line-1"
echo "mcp-line-2"
"""


def _mcp_stub(box: Sandbox, body: str) -> None:
    step = box.repo / "scripts" / "setup_mcp.sh"
    step.write_text(body, encoding="utf-8")
    step.chmod(0o755)


def test_the_mcp_setup_runs_beside_the_system_pip(tmp_path: Path) -> None:
    """The pip phase sees the MCP setup running: that is what keeps a deploy under 60 s."""
    box = _sandbox(tmp_path)
    _mcp_stub(box, _MCP_MEETS_PIP)
    proc = box.run(extra_env={"RDV": str(tmp_path)})
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "pip_saw_mcp").exists()


def test_the_mcp_output_is_replayed_whole_not_interleaved(tmp_path: Path) -> None:
    """Two writers on one stderr would braid their lines; the MCP one is buffered."""
    box = _sandbox(tmp_path)
    _mcp_stub(box, _MCP_MEETS_PIP)
    lines = box.run(extra_env={"RDV": str(tmp_path)}).stderr.splitlines()
    assert lines.index("mcp-line-2") == lines.index("mcp-line-1") + 1


def test_a_failed_mcp_setup_fails_the_install(tmp_path: Path) -> None:
    """The other phase succeeding does not make the install succeed."""
    box = _sandbox(tmp_path)
    _mcp_stub(box, '#!/bin/bash\necho "mcp-boom" >&2\nexit 3\n')
    proc = box.run()
    assert proc.returncode != 0
    assert "mcp-boom" in proc.stderr
    assert "exited 3" in proc.stderr


def test_a_failed_system_install_still_waits_for_and_shows_the_mcp_setup(
    tmp_path: Path,
) -> None:
    """Both exit codes are collected; the scratch dir outlives the MCP pip."""
    box = _sandbox(tmp_path)
    _mcp_stub(
        box,
        '#!/bin/bash\nsleep 0.5\ntest -d "$TMPDIR" && echo "mcp-tmp-alive"\nexit 4\n',
    )
    proc = box.run(pip_fail=True)
    assert proc.returncode != 0
    assert "mcp-tmp-alive" in proc.stderr
    assert "exit 4" in proc.stderr


def test_force_reinstalls_despite_a_matching_stamp(tmp_path: Path) -> None:
    """`install.sh --force` re-asserts the pins even when nothing changed."""
    box = _sandbox(tmp_path)
    assert box.run().returncode == 0
    assert box.run().returncode == 0
    assert box.installs() == 1
    assert box.run("--force").returncode == 0
    assert box.installs() == 2


def test_force_reaches_the_mcp_setup(tmp_path: Path) -> None:
    """The MCP phase has its own stamp; it must hear about --force too."""
    box = _sandbox(tmp_path)
    _mcp_stub(box, f'#!/bin/bash\necho "${{INSTALL_FORCE:-0}}" > "{tmp_path}/forced"\n')
    assert box.run().returncode == 0
    assert (tmp_path / "forced").read_text(encoding="utf-8").strip() == "0"
    assert box.run("--force").returncode == 0
    assert (tmp_path / "forced").read_text(encoding="utf-8").strip() == "1"


def test_an_unknown_argument_is_refused_before_anything_runs(tmp_path: Path) -> None:
    """A typo like --forse must not silently run the skipping path."""
    box = _sandbox(tmp_path)
    proc = box.run("--forse")
    assert proc.returncode != 0
    assert "--forse" in proc.stderr
    assert box.installs() == 0
