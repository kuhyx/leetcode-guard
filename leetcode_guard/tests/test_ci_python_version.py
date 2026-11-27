"""CI's test jobs run the Python the deploy runs, not whatever ``3.x`` is today.

``3.x`` moved to 3.15 on the runners, where pylint's ``--jobs`` pickling dies
(pyproject's ``[tool.pylint.main]`` note), so ``test_pylint_dup_memo`` went red
on every push from 2026-11-22 while the machine, on system Python 3.14, stayed
green. Pinning the test jobs to pyproject's ``py-version`` keeps the two equal.
"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_the_test_jobs_pin_the_deploy_python() -> None:
    """Every ``python-version`` in python-tests.yml equals pylint's py-version."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        wanted = tomllib.load(handle)["tool"]["pylint"]["main"]["py-version"]
    workflow = (ROOT / ".github" / "workflows" / "python-tests.yml").read_text(
        encoding="utf-8"
    )
    pins = re.findall(r'python-version:\s*"([^"]+)"', workflow)
    assert pins, "no python-version pin found in python-tests.yml"
    assert set(pins) == {wanted}
