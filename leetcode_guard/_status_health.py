"""The diagnostic half of the status window: integrity, environment, pool.

Split from ``_status_sections.py`` for the 250-line cap, along the seam that
was already there: the first four sections answer "am I locked and what do I
owe", these three answer "is the machinery underneath actually working".

Colour discipline matches its sibling -- red and amber are load-bearing here,
never decoration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._status_rows import section_heading as _heading
from leetcode_guard._status_rows import section_row as _row

if TYPE_CHECKING:
    import tkinter as tk

    from gatelock import LockConfig

    from leetcode_guard._status_full import FullStatus


__all__ = ["section_environment", "section_integrity", "section_suggestions"]


def section_integrity(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """Signature, clock and parse health."""
    gate = full.gate
    _heading(parent, config, "Ledger integrity")
    _row(
        parent,
        config,
        f"HMAC checking: {'on' if gate.integrity_ok else 'OFF (key unreadable)'}",
        color=config.fg if gate.integrity_ok else config.danger,
    )
    for label, count in (
        ("Entries failing their signature", gate.tampered),
        ("Credits refused", gate.discounted),
        ("Unreadable rows", gate.unparsable),
    ):
        _row(
            parent,
            config,
            f"{label}: {count}",
            color=config.danger if count else config.fg,
        )
    _row(
        parent,
        config,
        f"Clock trusted: {gate.clock_trusted}",
        color=config.fg if gate.clock_trusted else config.danger,
    )
    _row(parent, config, f"Ledger entries: {full.ledger.total_entries}")
    _row(parent, config, f"Seeded: {full.ledger.bootstrapped}")
    _row(
        parent,
        config,
        f"File: {full.ledger_path}",
        color=config.muted,
        role="caption",
    )


def section_environment(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """Timer, caches, auth and sync."""
    _heading(parent, config, "Scheduling and caches")
    _row(
        parent,
        config,
        f"Timer enabled: {full.timer.enabled} ({full.timer.detail})",
        color=config.fg if full.timer.enabled else config.warning,
    )
    _row(parent, config, f"Next fire: {full.timer.next_fire}")
    _row(parent, config, full.pool_cache.summary)
    _row(parent, config, full.statement_cache.summary)
    _row(parent, config, f"Suggestions from: {full.gate.pool_source}")
    _row(parent, config, f"LeetCode cookies configured: {full.cookies_configured}")
    _row(parent, config, f"Sync token configured: {full.sync_configured}")
    for note in full.gate.pool_notes:
        _row(parent, config, f"  {note}", color=config.muted, role="caption")


def section_suggestions(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """What the lock would offer."""
    _heading(parent, config, "Suggested problems")
    if not full.gate.suggestions:
        _row(parent, config, "(no cached pool)", color=config.muted)
        return
    for index, item in enumerate(full.gate.suggestions, start=1):
        _row(
            parent,
            config,
            f"{index:2d}. {item.title} -- {item.difficulty}, {item.ac_rate:.1f}%",
            role="caption",
        )
        _row(parent, config, f"     {item.url}", color=config.muted, role="caption")
