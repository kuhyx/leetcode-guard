"""The offline path's exit -- the network-incident form.

These are the tests for the worst bug this repo has had: LOCAL_OFFLINE plus a
spent escape budget held the keyboard while the screen promised a way out that
did not exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard.tests._blind_fixtures import blind_offline

if TYPE_CHECKING:
    from pathlib import Path


def test_a_local_outage_captures_the_incident_policy(tmp_path: Path, hmac_key: Path):
    """A LOCAL_OFFLINE diagnosis stores a form-requiring policy and stays locked."""
    guard = blind_offline(tmp_path, hmac_key)

    assert guard.outage.policy is not None
    assert guard.outage.policy.require_form
    assert guard.decision().locked
