"""Tests for the MCP server.

The most important test here is the one that asserts what does *not* exist: no
tool may grant a credit, mark a problem solved, or unlock. A credit exists only
because LeetCode confirmed an accepted submission.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from leetcode_guard import _mcp
from leetcode_guard._ledger_io import save_ledger
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import parse_problem
from leetcode_guard.tests._ledger_fixtures import MONDAY, ledger_with_credits
from leetcode_guard.tests._net_fixtures import problem_row

_FORBIDDEN = (
    "grant",
    "unlock",
    "solve",
    "mark",
    "credit_add",
    "set_",
    "write",
    "record",
)


def tool_names() -> set[str]:
    """Every function decorated as an MCP tool in the module."""
    return {
        name
        for name, value in vars(_mcp).items()
        if callable(value) and not name.startswith("_") and inspect.isfunction(value)
    }


def test_no_tool_can_grant_a_credit_or_unlock():
    """A caller's claim is never evidence. An agent that could mint a credit
    would make the gate decorative, and silently so."""
    names = tool_names()

    assert "get_status" in names
    for name in names:
        assert not any(
            name.startswith(word) or f"_{word}" in name
            for word in ("grant", "unlock", "mark")
        ), f"{name} looks like a write tool"
    assert "grant_credit" not in names
    assert "mark_solved" not in names
    assert "unlock" not in names


@pytest.mark.parametrize("word", _FORBIDDEN)
def test_the_module_defines_no_write_shaped_tool(word: str):
    assert not any(name.startswith(word) for name in tool_names())


def test_logging_goes_to_stderr_never_stdout():
    """stdout is the JSON-RPC channel; a handler there corrupts the protocol
    and the server fails in a way that looks like a hang."""
    source = Path(_mcp.__file__).read_text(encoding="utf-8")

    assert "stream=sys.stderr" in source
    assert "print(" not in source


def test_the_server_never_imports_the_cli():
    """_cli prints, opens windows and calls sys.exit -- all fatal over stdio.

    Parsed rather than grepped: the module docstring names ``_cli`` while
    explaining why it must not be imported, and a substring check would fail on
    its own documentation.
    """
    tree = ast.parse(Path(_mcp.__file__).read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(name.endswith("_cli") for name in imported)
    assert not any(name.endswith("_lock") for name in imported)


def test_get_status_returns_plain_data(data_dir: Path, hmac_key: Path):
    save_ledger(
        data_dir / "ledger.json", ledger_with_credits(2, day=MONDAY, key_file=hmac_key)
    )

    status = _mcp.get_status()

    assert isinstance(status, dict)
    assert "day" in status
    assert "locked" in status


def test_get_credits_reports_the_position(data_dir: Path):
    credits_now = _mcp.get_credits()

    assert credits_now["available"] == 0
    assert credits_now["locked"]
    assert set(credits_now) == {
        "credits",
        "charged",
        "available",
        "today_cost",
        "needed",
        "locked",
        "integrity_ok",
    }


def test_suggestions_come_from_the_cache_and_never_fetch(data_dir: Path):
    """The suite blocks real HTTP, so this passing is the proof that an MCP
    call can never trigger a live fetch or count against the rate limit."""
    problems = tuple(
        p
        for p in (parse_problem(problem_row(slug)) for slug in ("two-sum", "add-two"))
        if p is not None
    )
    write_cache(
        data_dir / "pool_cache.json",
        CachedPool(problems=problems, fetched_at=2**31, complete=True),
    )

    suggestions = _mcp.get_suggested_problems()

    assert len(suggestions) == 2
    assert suggestions[0]["url"].startswith("https://leetcode.com/problems/")


def test_the_suggestion_limit_is_honoured(data_dir: Path):
    problems = tuple(
        p
        for p in (parse_problem(problem_row(slug)) for slug in ("a", "b", "c"))
        if p is not None
    )
    write_cache(
        data_dir / "pool_cache.json",
        CachedPool(problems=problems, fetched_at=2**31, complete=True),
    )

    assert len(_mcp.get_suggested_problems(limit=2)) == 2


def test_suggestions_are_empty_with_no_cache(data_dir: Path):
    assert _mcp.get_suggested_problems() == []


def test_explain_lock_carries_the_decision_chain(data_dir: Path):
    explanation = _mcp.explain_lock()

    assert explanation["locked"]
    assert explanation["state"] == "locked"
    assert "reason" in explanation
    assert explanation["clock_trusted"]
    assert isinstance(explanation["pool_notes"], list)


def test_no_tool_returns_a_secret(data_dir: Path, config_dir: Path):
    """Nothing may hand back the sync token, the cookies or an HMAC key."""
    (config_dir / "sync_token").write_text("ghp_supersecret", encoding="utf-8")
    (config_dir / "cookies.json").write_text(
        '{"LEETCODE_SESSION": "sess_secret", "csrftoken": "csrf_secret"}',
        encoding="utf-8",
    )

    blob = repr(
        [
            _mcp.get_status(),
            _mcp.get_credits(),
            _mcp.get_suggested_problems(),
            _mcp.explain_lock(),
        ]
    )

    assert "ghp_supersecret" not in blob
    assert "sess_secret" not in blob
    assert "csrf_secret" not in blob
