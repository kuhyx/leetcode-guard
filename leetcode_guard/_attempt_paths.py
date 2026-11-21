"""Where ``attempts.json`` lives.

Its own module because ``_constants`` is at the shared line cap. Read it as
``_attempt_paths.ATTEMPTS_FILE`` (never ``from ... import``): the test
fixture rebinds the attribute, and a by-value copy would keep pointing at the
real file. The lock and the set-aside file are derived from this path at the
point of use, so one redirect covers all three.
"""

from __future__ import annotations

from typing import Final

from leetcode_guard import _constants

ATTEMPTS_FILE: Final = _constants.DATA_DIR / "attempts.json"
"""Heartbeats, submissions and theory snapshots. Display only: nothing that
decides, charges or credits may read it (``test_display_only_imports``)."""
