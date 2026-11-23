"""Tutor post-mortem reports on disk, for the display-only view's tests.

``postmortem_reports_2026-11-23.json`` holds two signed-shape reports built
from the tutor's real dry run of ``prefix-sums`` (2026-11-23): ``prefix-sums``
with two revisions, the latest with ``applied`` and one card switched to
``kept``, and a small ``two-pointers`` unit. The ``hmac`` is a placeholder:
the view displays, it does not verify.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leetcode_guard import _tutor_signed

REPORTS_FILE = Path(__file__).with_name("postmortem_reports_2026-11-23.json")
APP_FIXTURE = (
    Path(__file__).parents[2] / "app" / "test" / "fixtures" / "snapshot_postmortem.json"
)


def reports() -> dict[str, dict[str, Any]]:
    """Every fixture report by unit, freshly parsed (safe to mutate)."""
    loaded: dict[str, dict[str, Any]] = json.loads(
        REPORTS_FILE.read_text(encoding="utf-8")
    )
    return loaded


def postmortems_dir() -> Path:
    """The redirected tutor's ``postmortems`` dir (read at call time)."""
    return _tutor_signed.TUTOR_DIR / "postmortems"


def write_report(report: dict[str, Any], *, name: str | None = None) -> Path:
    """Write one report where the tutor keeps it; returns its path."""
    path = postmortems_dir() / report["subject"] / f"{name or report['unit']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def write_all() -> None:
    """Both fixture reports."""
    for report in reports().values():
        write_report(report)
