"""Shared by the install.sh and setup_mcp.sh stamp tests: one damaged-stamp check."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path
    import subprocess


class StampedBox(Protocol):
    """What both sandboxes offer: run the script, find its stamp, count installs."""

    @property
    def stamp(self) -> Path:
        """Where the script records its last good install."""

    def run(self) -> subprocess.CompletedProcess[str]:
        """Run the script once."""

    def installs(self) -> int:
        """How many pip installs the fake python saw."""


def assert_damaged_stamp_reinstalls(box: StampedBox, damage: str) -> None:
    """Fail closed: anything but a readable, matching stamp means pip runs."""
    assert box.run().returncode == 0
    if damage == "delete":
        box.stamp.unlink()
    elif damage == "unreadable":
        box.stamp.chmod(0)
    else:
        text = "" if damage == "empty" else "not-a-hash\n"
        box.stamp.write_text(text, encoding="utf-8")
    assert box.run().returncode == 0
    assert box.installs() == 2
