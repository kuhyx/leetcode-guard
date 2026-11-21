"""Shared helpers for the ``attempts.json`` tests (not collected as tests)."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from typing import TYPE_CHECKING, Any

from leetcode_guard import _attempt_paths
from leetcode_guard._attempt_lock import LockTiming
from leetcode_guard._attempt_model import day_of

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

T0 = 1_795_287_000
"""2026-11-21 19:50 in the developer's zone; tests derive days via ``day_of``."""
DAY = day_of(T0)
SECONDS_PER_DAY = 86_400
KEY = f"{DAY}|two-sum"


def attempts_path() -> Path:
    """The (test-redirected) file location, read at call time."""
    return _attempt_paths.ATTEMPTS_FILE


def raw(path: Path) -> Any:
    """The file's parsed JSON, untyped on purpose."""
    return json.loads(path.read_text(encoding="utf-8"))


def seed(path: Path, records: dict[str, object]) -> None:
    """Write a version-1 document holding ``records``."""
    path.write_text(json.dumps({"version": 1, "records": records}), encoding="utf-8")


def record(day: str, slug: str = "two-sum", **extra: object) -> dict[str, object]:
    """A minimal valid record, overridable field by field."""
    return {"day": day, "slug": slug, "beats": [], "submissions": {}, **extra}


@contextmanager
def hold_lock(path: Path) -> Iterator[int]:
    """Hold the store's lock file the way a second process would."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        yield fd
    finally:
        os.close(fd)


def virtual_timing() -> tuple[LockTiming, list[float]]:
    """A timing whose sleeps advance a fake clock instead of waiting."""
    clock = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    return LockTiming(sleep=sleep, monotonic=lambda: clock[0]), slept
