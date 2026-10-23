"""The snapshot's ``status`` block: the old tkinter window's sections as data.

One function per section, in the order the (now deleted) window drew them,
each lifting exactly what its sections showed. Wording that encodes a
rule -- why the lock did not trigger, the debt summary, the pricing caption --
is rendered *here*, by the Python that owns the rule, and shipped as text, so
the app never re-derives a rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_guard._daycost import CURRENT_PRICING, INTERIM_PRICING, REPRICE_DATE
from leetcode_guard._debt import debt_summary
from leetcode_guard._status_full import explain_not_triggered

if TYPE_CHECKING:
    from leetcode_guard._status_extra import BudgetStatus, CacheStatus
    from leetcode_guard._status_full import FullStatus


def pricing_note() -> str:
    """The credits section's caption, word for word."""
    return (
        f"{CURRENT_PRICING.describe()}, plus 1 on Mon/Fri/Sat/Sun while any debt "
        f"is outstanding (before {REPRICE_DATE:%d.%m.%Y}: "
        f"{INTERIM_PRICING.describe()}). A missed "
        "day is owed at its price. Credits never expire and are not capped."
    )


def _verdict_and_credits(full: FullStatus) -> dict[str, Any]:
    gate, debt = full.gate, full.gate.debt
    return {
        "day": gate.day,
        "weekday": gate.weekday,
        "state": gate.state,
        "locked": gate.locked,
        "reason": gate.reason,
        "explanation": explain_not_triggered(full),
        "cost": gate.cost,
        "surcharge": gate.surcharge,
        "credits": gate.credits,
        "charged": gate.charged,
        "available": gate.available,
        "needed": gate.needed,
        "charged_today": gate.charged_today,
        "earned_all_time": full.ledger.credits_earned,
        "spent_all_time": full.ledger.charges_spent,
        "debt": {
            "owed": debt.owed,
            "repaid": debt.repaid,
            # A property, so asdict() would drop it -- spelled out on purpose.
            "outstanding": debt.outstanding,
            "missed_days": debt.missed_days,
            "summary": debt_summary(debt),
        },
        "pricing_note": pricing_note(),
    }


def _solves_and_days(full: FullStatus) -> dict[str, Any]:
    ledger = full.ledger
    return {
        "solves": {
            "today": ledger.solves_today,
            "last_7_days": ledger.solves_last_7_days,
            "total_credited": ledger.credits_earned,
            "recent": [
                {"day": solve.day, "title_slug": solve.title_slug, "lang": solve.lang}
                for solve in ledger.recent_solves
            ],
        },
        "days": {
            "charged": list(ledger.charged_days),
            "start_date": full.start_date,
            "in_force": full.in_force,
        },
    }


def _budget(budget: BudgetStatus) -> dict[str, Any]:
    return {
        "label": budget.label,
        "used_7": budget.used_7,
        "used_30": budget.used_30,
        "used_90": budget.used_90,
        "limit_7": budget.limit_7,
        "limit_30": budget.limit_30,
        "limit_90": budget.limit_90,
        "exhausted": budget.exhausted,
        "next_wait_seconds": budget.next_wait_seconds,
        "summary": budget.summary,
    }


def _cache(cache: CacheStatus) -> dict[str, Any]:
    return {
        "name": cache.name,
        "exists": cache.exists,
        "entries": cache.entries,
        # Rounded to what the window shows: the raw float changes every
        # minute, which would defeat the push's unchanged-content check.
        "age_days": None if cache.age_days is None else round(cache.age_days, 1),
        "summary": cache.summary,
    }


def _health(full: FullStatus) -> dict[str, Any]:
    gate = full.gate
    return {
        "integrity": {
            "ok": gate.integrity_ok,
            "tampered": gate.tampered,
            "discounted": gate.discounted,
            "unparsable": gate.unparsable,
            "clock_trusted": gate.clock_trusted,
            "total_entries": full.ledger.total_entries,
            "bootstrapped": full.ledger.bootstrapped,
            "ledger_path": full.ledger_path,
        },
        "environment": {
            "clock_trusted": gate.clock_trusted,
            "auth_present": gate.auth_present,
            "auth_note": gate.auth_note,
            "pool_source": gate.pool_source,
            "pool_notes": list(gate.pool_notes),
            "cookies_configured": full.cookies_configured,
            "sync_configured": full.sync_configured,
            "timer": {
                "enabled": full.timer.enabled,
                "next_fire": full.timer.next_fire,
                "detail": full.timer.detail,
            },
            "pool_cache": _cache(full.pool_cache),
            "statement_cache": _cache(full.statement_cache),
        },
    }


def status_section(full: FullStatus) -> dict[str, Any]:
    """Every tkinter section but progress, which has its own top-level keys."""
    return {
        **_verdict_and_credits(full),
        **_solves_and_days(full),
        "budgets": {
            "escape": _budget(full.escape),
            "incidents": _budget(full.incidents),
        },
        **_health(full),
        "suggestions": [
            {
                "title": item.title,
                "difficulty": item.difficulty,
                "ac_rate": item.ac_rate,
                "url": item.url,
            }
            for item in full.gate.suggestions
        ],
    }
