"""The MCP server reports the unit and phase, and still writes nothing.

The scenario is ``_theory_scenario``'s: unit ``a`` (module ``a``, Easy ``a1``)
then unit ``b`` (modules ``b1``/``b2``, Easy ``b1-easy``).
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from leetcode_guard import _mcp, _phase_file, _status
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard.tests._theory_scenario import began, states, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO
from leetcode_guard.tests.test_status_unit import minted
from leetcode_guard.tests.test_unit_view import NOW, display_files, solved

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def seam(monkeypatch: pytest.MonkeyPatch, data_dir: Path, key: Path) -> None:
    """Every tool reads the scratch ledger with the test key, at :data:`NOW`."""
    monkeypatch.setattr(
        _mcp,
        "gather_status",
        partial(
            _status.gather_status,
            now=NOW,
            ledger_path=data_dir / "ledger.json",
            key_file=key,
        ),
    )


def test_get_status_and_explain_lock_lead_with_theory_in_theory(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a): the unit, the phase, the learn route and why it leads."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 30))
    display_files("a-1")
    seam(monkeypatch, data_dir, hmac_key)
    c3 = _phase_file.PHASE_FILE.read_bytes()

    unit = _mcp.get_status()["unit"]
    why = _mcp.explain_lock()

    assert (unit["unit"], unit["phase"], unit["leads_with"]) == (
        "a",
        "theory",
        "theory",
    )
    assert unit["learn_route"] == f"/learn/{ALGO}/a"
    assert unit["theory_minutes_today"] == 30
    assert (why["unit"], why["phase"], why["leads_with"]) == ("a", "theory", "theory")
    assert "theory is not done" in why["lead_reason"]
    assert _phase_file.PHASE_FILE.read_bytes() == c3


def test_explain_lock_leads_with_problems_in_solve(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a): problems lead, and the reason says how many are left."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    seam(monkeypatch, data_dir, hmac_key)

    why = _mcp.explain_lock()

    assert (why["unit"], why["phase"], why["leads_with"]) == ("a", "solve", "problems")
    assert "1 of 1 Easy" in why["lead_reason"]
    assert why["learn_route"] is None


def test_explain_lock_in_none_and_when_it_cannot_check(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Every unit finished: today's list. Nothing readable: says so, never "none"."""
    seam(monkeypatch, data_dir, hmac_key)
    blind = _mcp.explain_lock()
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    solved(data_dir, hmac_key, "a1", "b1-easy")

    done = _mcp.explain_lock()

    assert (blind["phase"], blind["source"]) == ("none", "unknown")
    assert "could not check" in blind["lead_reason"]
    assert (done["unit"], done["phase"], done["source"]) == ("", "none", "live")
    assert "every unit is finished" in done["lead_reason"]


def test_get_credits_tells_theory_credits_from_solve_credits(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """One solve plus two theory credits today and one yesterday."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    solved(data_dir, hmac_key, "a1")
    minted(data_dir, hmac_key, (0, "a"), (0, "a"), (1, "a"))
    seam(monkeypatch, data_dir, hmac_key)

    got = _mcp.get_credits()

    assert got["credits"] == 4
    assert (got["theory_credits"], got["theory_credits_today"]) == (3, 2)
    assert got["solve_credits"] == 1


def test_get_suggested_problems_lead_with_the_current_unit(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a) with b's cards taught: the old key serves taught b first; the
    lock's ``focus_key`` (and so this list) leads with a's Easy problem."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    cards = {f"{m}-1": {"module": m, "suspended": False} for m in ("b1", "b2")}
    display_files(*cards, cards=cards)
    seam(monkeypatch, data_dir, hmac_key)

    rows = _mcp.get_suggested_problems()

    assert [row["unit"] for row in rows] == ["a", "b"]
    assert (rows[0]["theory"], rows[1]["theory"]) == ("pending", "done")


def test_no_tool_wrote_the_ledger(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Every tool, 36 minutes taught: no theory credit appears, C3 untouched."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 36))
    seam(monkeypatch, data_dir, hmac_key)
    c3 = _phase_file.PHASE_FILE.read_bytes()

    for tool in (
        _mcp.get_status,
        _mcp.get_credits,
        _mcp.get_suggested_problems,
        _mcp.explain_lock,
    ):
        tool()

    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    assert not any(e.startswith("theory:") for e in ledger.entries)
    assert _phase_file.PHASE_FILE.read_bytes() == c3
