"""``--postmortem-dry-run UNIT``: the tutor's post-mortem of a unit, writing nothing.

Signs the unit's claimed solves into ``postmortem_dry_run.json``
(``_unit_finish.write_preview``) and runs ``python -m tutor postmortem UNIT
--dry-run`` with the live tutor's interpreter. The tutor's draft-tier call
outlives the 60 s action cap, so the tutor starts it as a ``systemd-run``
unit and answers 75 (pending) until the report is ready: call again (the
signed request keeps its ``at`` while the solves stay the same, so a poll
never starts a second call). Its
output lines are relayed as they are; its exit code is this command's.

Writes no ledger row and no tutor file: the tutor's dry run writes only its
own ``postmortems/dry/<unit>.json``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
import os
from pathlib import Path
import subprocess
from typing import Final

from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._unit_finish import write_preview

_logger: Final = logging.getLogger(__name__)
EXIT_REFUSED: Final = 2
TIMEOUT_S: Final = 50
TUTOR_PYTHON_ENV: Final = "LCG_TUTOR_PYTHON"
TUTOR_CWD_ENV: Final = "LCG_TUTOR_DIR"
"""Overrides; the defaults are what ``tutor.service`` runs (``ExecStart``, cwd)."""

Runner = Callable[[list[str], Path], tuple[int, str]]


def tutor_command(unit: str) -> tuple[list[str], Path]:
    """The tutor CLI call and its working directory."""
    home = Path.home()
    python = os.environ.get(TUTOR_PYTHON_ENV) or str(
        home / "src/tutor/.venv/bin/python"
    )
    cwd = os.environ.get(TUTOR_CWD_ENV) or str(home / ".local/lib/tutor-live/current")
    return [python, "-m", "tutor", "postmortem", unit, "--dry-run"], Path(cwd)


def run_tutor(argv: list[str], cwd: Path) -> tuple[int, str]:
    """Run the tutor CLI; (exit code, stdout plus stderr's tail)."""
    try:
        done = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _logger.warning("tutor dry run did not answer: %s", exc)
        return 1, f"failed: the tutor did not answer: {exc}"
    return done.returncode, (done.stdout + done.stderr[-2000:]).rstrip()


def cmd_postmortem_dry_run(unit: str, runner: Runner = run_tutor) -> int:
    """Sign the request, ask the tutor, print its answer; 75 = pending."""
    ledger = load_ledger(LEDGER_FILE)
    if write_preview(ledger, unit, now=datetime.now().astimezone()) is None:
        print(f"refused: {unit} has no tutor theory or the pool is not signed")
        return EXIT_REFUSED
    code, out = runner(*tutor_command(unit))
    print(out)
    return code
