"""The e2e ``began`` role: back-date when the stored C3's THEORY began.

Minutes that ended before C3's ``theory_since`` never pay (red-team R2), and
the harvest that first writes C3 stamps it "now". A case that teaches rows
ended N minutes ago first says THEORY began earlier, the way a real day has
the phase written long before kuhy teaches.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path

import earned_time

from leetcode_guard import _phase_file


def began(ago: str) -> None:
    """``<minutes ago>``: re-sign the stored C3 with that ``theory_since``."""
    path = _phase_file.PHASE_FILE
    row = json.loads(path.read_text(encoding="utf-8"))
    del row["hmac"]
    since = datetime.now().astimezone() - timedelta(minutes=float(ago))
    row["detail"]["theory_since"] = since.timestamp()
    key = Path(os.environ["E2E_KEY"]).read_bytes().strip()
    row["hmac"] = earned_time.entry_signature(row, key)
    path.write_text(json.dumps(row), encoding="utf-8")
