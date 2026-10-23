"""Tests for the ledger-change push trigger and the read-only boundary.

The trigger runs inside ``save_ledger``, i.e. inside the gate, so it must
never wait, never raise and never import the snapshot. The boundary test is
the executable form of "nothing that decides, charges or credits may read the
snapshot": it walks the *transitive* import graph, because a direct-import
grep passes while a violation arrives through ``_ledger_io``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from leetcode_guard import _push_trigger
from leetcode_guard._ledger_io import Ledger, save_ledger

if TYPE_CHECKING:
    import pytest

PACKAGE = Path(_push_trigger.__file__).resolve().parent

DECIDING = (
    "_balance",
    "_clock_guard",
    "_daycost",
    "_debt",
    "_gate",
    "_gate_today",
    "_harvest",
    "_ledger",
    "_ledger_entries",
    "_ledger_io",
    "_lock_poll",
    "_sick",
    "_submissions",
    "_workday_penalty",
)
"""Every module that decides, charges or credits."""

SNAPSHOT_SIDE = (
    "_coach_log",
    "_profile",
    "_profile_cache",
    "_profile_query",
    "_snapshot",
    "_snapshot_auth",
    "_snapshot_projection",
    "_snapshot_push",
    "_snapshot_status",
)


def _imports(name: str) -> set[str]:
    """Every ``leetcode_guard`` module ``name`` imports, TYPE_CHECKING included."""
    tree = ast.parse((PACKAGE / f"{name}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            if module == "leetcode_guard":
                found.update(alias.name for alias in node.names)
            elif module.startswith("leetcode_guard."):
                found.add(module.split(".")[1])
        elif isinstance(node, ast.Import):
            found.update(
                alias.name.split(".")[1]
                for alias in node.names
                if alias.name.startswith("leetcode_guard.")
            )
    return {item for item in found if (PACKAGE / f"{item}.py").exists()}


def _closure(roots: tuple[str, ...]) -> set[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(_imports(name))
    return seen


def test_no_deciding_module_can_reach_the_snapshot():
    reached = _closure(DECIDING)

    assert _push_trigger.__name__.rsplit(".", 1)[1] in reached
    assert reached.isdisjoint(SNAPSHOT_SIDE), reached & set(SNAPSHOT_SIDE)


def test_every_snapshot_module_is_named_in_the_boundary():
    on_disk = {
        path.stem
        for path in PACKAGE.glob("*.py")
        if path.stem.startswith(("_snapshot", "_profile", "_coach"))
    }

    assert on_disk == set(SNAPSHOT_SIDE)


def test_the_trigger_imports_only_constants():
    assert _imports("_push_trigger") == {"_constants"}


def test_a_production_save_requests_a_push(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path
):
    spawned: list[list[str]] = []
    monkeypatch.setattr(_push_trigger, "_spawn", spawned.append)

    assert save_ledger(data_dir / "ledger.json", Ledger())

    assert len(spawned) == 1
    assert spawned[0][-3:] == ["-m", "leetcode_guard", "--push-snapshot"]


def test_a_demo_or_other_ledger_never_publishes(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path
):
    spawned: list[list[str]] = []
    monkeypatch.setattr(_push_trigger, "_spawn", spawned.append)

    save_ledger(data_dir / "ledger_demo.json", Ledger())

    assert spawned == []


def test_a_failed_save_requests_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    spawned: list[list[str]] = []
    monkeypatch.setattr(_push_trigger, "_spawn", spawned.append)
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(_push_trigger, "LEDGER_FILE", blocker / "ledger.json")

    assert not save_ledger(blocker / "ledger.json", Ledger())
    assert spawned == []


def test_the_push_outlives_a_oneshot_via_systemd_run(monkeypatch: pytest.MonkeyPatch):
    """A plain child dies with the lock unit's cgroup; a transient unit does not."""
    monkeypatch.setattr(_push_trigger.shutil, "which", lambda _name: "/x/systemd-run")

    command = _push_trigger.push_command()

    assert command[:5] == [
        "/x/systemd-run",
        "--user",
        "--no-block",
        "--collect",
        "--quiet",
    ]


def test_without_systemd_run_the_child_is_spawned_directly(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(_push_trigger.shutil, "which", lambda _name: None)

    assert _push_trigger.push_command()[1:] == [
        "-m",
        "leetcode_guard",
        "--push-snapshot",
    ]


def test_a_spawn_failure_is_a_warning_not_a_raise(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, caplog: pytest.LogCaptureFixture
):
    def refuse(_command: list[str]) -> None:
        message = "no such file"
        raise OSError(message)

    monkeypatch.setattr(_push_trigger, "_spawn", refuse)

    assert not _push_trigger.request_push(data_dir / "ledger.json")
    assert "could not request a snapshot push" in caplog.text


def test_the_real_spawn_detaches(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    class FakePopen:
        def __init__(self, command: list[str], **kwargs: object) -> None:
            seen["command"] = command
            seen.update(kwargs)

    monkeypatch.setattr(_push_trigger.subprocess, "Popen", FakePopen)

    _push_trigger.real_spawn(["true"])

    assert seen["command"] == ["true"]
    assert seen["start_new_session"] is True
