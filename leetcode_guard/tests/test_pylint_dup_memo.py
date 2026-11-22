"""scripts/pylint_dup_memo.py must report exactly what plain pylint reports.

The pre-commit pylint gate runs through that wrapper to hash each file once for
duplicate-code instead of once per partner file (2026-11-22). The speed-up is
only allowed if no message changes, so this runs both on a throwaway tree with
a block copied into three files, an unused import and a clean file, and diffs
the output and the exit code, serial and with workers.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

WRAPPER = Path(__file__).resolve().parents[2] / "scripts" / "pylint_dup_memo.py"
_BLOCK = '''"""Module {name}."""


def spread(values: list[int]) -> int:
    """Seeded block, copied into several files."""
    total = 0
    for value in values:
        if value > 10:
            total += value * 2
        else:
            total -= value
    result = total * 7
    result += len(values) * 13
    return result - sum(values) // 3
'''
_OPTIONS = (
    "--disable=all",
    "--enable=duplicate-code,unused-import",
    "--persistent=n",
    "--score=n",
)


def _tree(root: Path) -> None:
    """Write three files sharing a block, one with an unused import, one clean."""
    for name in ("alpha", "beta", "gamma"):
        (root / f"{name}.py").write_text(_BLOCK.format(name=name), encoding="utf-8")
    (root / "gamma.py").write_text(
        "import json\n" + _BLOCK.format(name="gamma"), encoding="utf-8"
    )
    (root / "clean.py").write_text('"""Nothing to report."""\n', encoding="utf-8")


def _run(command: list[str], root: Path) -> tuple[int, list[str]]:
    """Return the exit code and the sorted output lines of one pylint run."""
    done = subprocess.run(
        [*command, *_OPTIONS, "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, sorted(done.stdout.splitlines())


@pytest.mark.parametrize("jobs", ["--jobs=1", "--jobs=2"])
def test_the_wrapper_reports_what_plain_pylint_reports(
    tmp_path: Path, jobs: str
) -> None:
    """Same exit code and same lines, and the seeded R0801 is really reported."""
    _tree(tmp_path)
    plain = _run([sys.executable, "-P", "-m", "pylint", jobs], tmp_path)
    wrapped = _run([sys.executable, "-P", str(WRAPPER), jobs], tmp_path)
    assert wrapped == plain
    assert any("R0801" in line for line in wrapped[1])
    assert any("W0611" in line for line in wrapped[1])
    assert wrapped[0] != 0
