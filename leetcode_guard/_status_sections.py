"""Turn a :class:`FullStatus` into rows of labels.

Split from ``status_view.py`` for the 400-line cap, and because it keeps the
window file about *windowing* and this file about *content*.

Colour discipline: status colours are load-bearing here, not decoration.
Red means the gate is holding you, amber means something needs attention,
green means clear. Nothing is coloured merely to look lively.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from leetcode_guard._status_full import explain_not_triggered

if TYPE_CHECKING:
    from gatelock import LockConfig

    from leetcode_guard._status_full import FullStatus

_HEADING_SIZE = 15
_BODY_SIZE = 13
_SMALL_SIZE = 11


def _heading(parent: tk.Misc, config: LockConfig, text: str) -> None:
    """A section title."""
    tk.Label(
        parent,
        text=text,
        font=(config.font_family, _HEADING_SIZE, "bold"),
        fg=config.accent,
        bg=config.bg,
        anchor="w",
    ).pack(fill="x", padx=24, pady=(14, 2))


DEFAULT_WRAP = 880
"""Fallback wrap width, matching the window's default geometry.

Passed in rather than hardcoded because the first version wrapped at a fixed
900px inside a 720px window, so every long explanation ran off the right edge
-- in the one panel whose entire job is explaining things.
"""

_wrap_state = {"width": DEFAULT_WRAP}


def _row(
    parent: tk.Misc,
    config: LockConfig,
    text: str,
    *,
    color: str | None = None,
    size: int = _BODY_SIZE,
) -> None:
    """One line of body text, wrapped to the current window width."""
    tk.Label(
        parent,
        text=text,
        font=(config.font_family, size),
        fg=color if color is not None else config.fg,
        bg=config.bg,
        anchor="w",
        justify="left",
        wraplength=_wrap_state["width"],
    ).pack(fill="x", padx=36, pady=1)


def _verdict_color(config: LockConfig, full: FullStatus) -> str:
    """Red when held, amber when nothing is banked, green when clear."""
    if full.gate.locked:
        return config.danger
    if full.gate.available <= 0:
        return config.warning
    return config.success


def _section_verdict(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """The answer to "am I locked, and why".

    First because it is the only thing most openings of this window are about.
    """
    gate = full.gate
    _heading(parent, config, "Right now")
    headline = (
        f"LOCKED -- solve {gate.needed} more"
        if gate.locked
        else f"Unlocked ({gate.state})"
    )
    tk.Label(
        parent,
        text=headline,
        font=(config.font_family, 22, "bold"),
        fg=_verdict_color(config, full),
        bg=config.bg,
        anchor="w",
    ).pack(fill="x", padx=24, pady=(2, 6))
    _row(
        parent,
        config,
        f"{gate.day} ({gate.weekday}), which costs {gate.cost} credit(s)",
    )
    _row(parent, config, gate.reason)

    _heading(parent, config, "Why the lock did not trigger")
    reasons = explain_not_triggered(full)
    if not reasons:
        _row(parent, config, "No blocking condition recorded.", color=config.muted)
    for index, line in enumerate(reasons, start=1):
        _row(parent, config, f"{index}. {line}")


def _section_credits(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """Tokens: what you have, earned, and spent."""
    gate, ledger = full.gate, full.ledger
    _heading(parent, config, "Credits (tokens)")
    tk.Label(
        parent,
        text=f"{gate.available} available",
        font=(config.font_family, 20, "bold"),
        fg=config.success if gate.available > 0 else config.warning,
        bg=config.bg,
        anchor="w",
    ).pack(fill="x", padx=24, pady=(2, 4))
    _row(parent, config, f"Earned all-time: {ledger.credits_earned}")
    _row(parent, config, f"Spent all-time:  {ledger.charges_spent}")
    _row(parent, config, f"Needed today:    {gate.needed}")
    _row(
        parent,
        config,
        "A weekday costs 1, Saturday and Sunday cost 2. Credits never expire "
        "and are not capped.",
        color=config.muted,
        size=_SMALL_SIZE,
    )


def _section_solves(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """What you actually solved."""
    ledger = full.ledger
    _heading(parent, config, "Solves")
    _row(parent, config, f"Today: {ledger.solves_today}")
    _row(parent, config, f"Last 7 days: {ledger.solves_last_7_days}")
    _row(parent, config, f"Total credited submissions: {ledger.credits_earned}")
    if not ledger.recent_solves:
        _row(parent, config, "(none recorded yet)", color=config.muted)
        return
    _row(parent, config, "Most recent:", color=config.muted, size=_SMALL_SIZE)
    for solve in ledger.recent_solves:
        lang = f" [{solve.lang}]" if solve.lang else ""
        _row(
            parent, config, f"  {solve.day}  {solve.title_slug}{lang}", size=_SMALL_SIZE
        )


def _section_days(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """Which days have been settled."""
    ledger = full.ledger
    _heading(parent, config, "Days settled")
    if not ledger.charged_days:
        _row(parent, config, "(none yet)", color=config.muted)
    else:
        _row(parent, config, ", ".join(ledger.charged_days), size=_SMALL_SIZE)
    _row(parent, config, f"Gate in force from {full.start_date}: {full.in_force}")


def _section_budgets(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
    """Escape hatch and network-incident allowances."""
    _heading(parent, config, "Escape budgets")
    for budget in (full.escape, full.incidents):
        color = config.danger if budget.exhausted else config.fg
        _row(parent, config, budget.summary, color=color)
        _row(
            parent,
            config,
            f"  next use waits {budget.next_wait_seconds // 60} min"
            + ("  -- EXHAUSTED" if budget.exhausted else ""),
            color=config.muted,
            size=_SMALL_SIZE,
        )


def _section_integrity(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
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
        size=_SMALL_SIZE,
    )


def _section_environment(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
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
        _row(parent, config, f"  {note}", color=config.muted, size=_SMALL_SIZE)


def _section_suggestions(parent: tk.Misc, config: LockConfig, full: FullStatus) -> None:
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
            size=_SMALL_SIZE,
        )
        _row(parent, config, f"     {item.url}", color=config.muted, size=_SMALL_SIZE)


def render_sections(
    parent: tk.Misc, config: LockConfig, full: FullStatus, *, wrap: int = DEFAULT_WRAP
) -> None:
    """Render every section, in the order a person reads them."""
    _wrap_state["width"] = max(320, wrap)
    _section_verdict(parent, config, full)
    _section_credits(parent, config, full)
    _section_solves(parent, config, full)
    _section_days(parent, config, full)
    _section_budgets(parent, config, full)
    _section_integrity(parent, config, full)
    _section_environment(parent, config, full)
    _section_suggestions(parent, config, full)
