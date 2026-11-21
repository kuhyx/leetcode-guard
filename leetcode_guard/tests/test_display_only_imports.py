"""The curriculum and the tutor reader order rows; they never decide.

Both read files anyone can edit (``curriculum.json``, the tutor's data dir). The
moment the gate, the balance or the harvester consulted either, editing JSON
would steer a lock or a credit -- the ``progress_cache.json`` rule again.
"""

from __future__ import annotations

import pytest

from leetcode_guard.tests.test_push_trigger import PACKAGE, _closure, _imports

DISPLAY_ONLY = {"_curriculum", "_theory"}
DECIDER_PREFIXES = (
    "_balance",
    "_daycost",
    "_debt",
    "_difficulty",
    "_gate",
    "_harvest",
    "_ledger",
)
ORCHESTRATOR = "_harvest_run"
"""Mints through ``_harvest`` and then pushes the display snapshot, so its
import closure reaches the status code on purpose. It gets the direct ban."""
DECIDERS = sorted(
    path.stem
    for path in PACKAGE.glob("_*.py")
    if path.stem.startswith(DECIDER_PREFIXES) and path.stem != ORCHESTRATOR
)


def test_the_decider_list_is_not_empty():
    """A renamed package would otherwise make the ban below vacuous."""
    assert {"_gate", "_balance", "_harvest", "_debt"} <= set(DECIDERS)


@pytest.mark.parametrize("name", DECIDERS)
def test_nothing_that_decides_can_reach_the_display_only_modules(name: str):
    """Transitively: not even through a helper two imports away."""
    assert not _closure((name,)) & DISPLAY_ONLY


def test_the_harvester_never_reads_them_itself():
    """Its own code may hand the snapshot off, never consult the curriculum."""
    assert not _imports(ORCHESTRATOR) & DISPLAY_ONLY
