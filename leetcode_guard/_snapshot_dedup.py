"""Remember what was last pushed, so unchanged content is not pushed again.

The full snapshot is ~32 KB, and one a minute was ~46 MB/day of upload. Its
content changes far less often than that: a solve, a settled day, the date
rolling over, a cache aging by a tenth of a day, a profile refetch. So the
push hashes everything except ``generated_at`` and writes the full node only
when that hash differs from the last *successful* write; the per-minute
freshness signal is the tiny heartbeat node instead.

The state file is display plumbing like ``progress_cache.json``: deleting it
costs one redundant write, nothing more. It also records *where* the write
went: a hash recorded for another path (the pre-E2E ``leetcode-guard/status``)
forces a write, so a moved node is never left empty behind a fresh heartbeat.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._atomic_json import write_json
from leetcode_guard._constants import DATA_DIR

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

PUSH_STATE_FILE: Final = DATA_DIR / "snapshot_push_state.json"
"""Here rather than in ``_constants``, which is at the line cap."""

VOLATILE_KEY: Final = "generated_at"


def content_hash(snapshot: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of everything but ``generated_at``."""
    content = {key: value for key, value in snapshot.items() if key != VOLATILE_KEY}
    text = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_pushed_hash(*, target: str, path: Path | None = None) -> str | None:
    """The hash of the last full write to ``target``, or ``None`` to force one."""
    source = PUSH_STATE_FILE if path is None else path
    if not source.exists():
        return None
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("snapshot push state at %s is unreadable: %s", source, exc)
        return None
    pushed = raw.get("hash") if isinstance(raw, dict) else None
    if not isinstance(pushed, str):
        _logger.warning("snapshot push state at %s holds no hash", source)
        return None
    if raw.get("target") != target:
        _logger.info("snapshot push state is for another node; pushing in full")
        return None
    return pushed


def write_pushed_hash(pushed: str, *, target: str, path: Path | None = None) -> bool:
    """Record a successful full write to ``target``. Never raises."""
    state = PUSH_STATE_FILE if path is None else path
    try:
        write_json(state, {"hash": pushed, "target": target})
    except OSError as exc:
        _logger.warning("could not record the pushed snapshot at %s: %s", state, exc)
        return False
    return True
