"""The status app's errors, as reported by the phone: parse, mirror, show.

The phone keeps its last few sanitised errors (message, first-seen,
last-seen, count) and writes them, on its next successful Firebase contact,
to ``leetcode-guard/app_errors/<device id>`` as one JSON string leaf. The
one-minute harvester reads that node (``_phone_errors_sync``) and mirrors it
here, so ``--status`` can list recent errors without touching the network.

**Display only.** Nothing that decides, charges or credits may read this:
the phone can write it, so it proves nothing. The phone sanitises at the
source; messages are scrubbed once more on the way in, because they end up
in a desktop notification and the journal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._atomic_json import write_json
from leetcode_guard._constants import DATA_DIR

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

PHONE_ERRORS_FILE: Final = DATA_DIR / "phone_errors.json"
"""The last fetched errors plus the keys already notified about."""

RECENT: Final = timedelta(days=7)
"""How far back ``--status`` looks."""

_SECRETS: Final = re.compile(
    r"[a-z][a-z0-9+.-]*://\S+|\?\S*|\b(?:auth|key|token)=\S*", re.IGNORECASE
)


@dataclass(frozen=True)
class PhoneError:
    """One distinct error one install showed."""

    device: str
    message: str
    first_seen: str
    last_seen: str
    count: int

    @property
    def key(self) -> str:
        """Device plus first-seen: the notification dedupe key."""
        return f"{self.device}|{self.first_seen}"


def _entry(device: str, raw: object) -> PhoneError | None:
    if not isinstance(raw, dict):
        return None
    message, first, last, count = (
        raw.get(name) for name in ("message", "first_seen", "last_seen", "count")
    )
    if not (isinstance(message, str) and isinstance(count, int)):
        return None
    clean = _SECRETS.sub("...", message)
    return PhoneError(device, clean, str(first), str(last), count)


def _leaf(raw: object) -> object:
    """A device's value: a JSON string leaf, or an object taken as it is."""
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.warning("phone error leaf is not JSON; skipped: %s", exc)
        return None


def parse_phone_errors(raw: object) -> list[PhoneError]:
    """Every well-formed error under ``app_errors``; junk is skipped."""
    if not isinstance(raw, dict):
        return []
    errors: list[PhoneError] = []
    for device, value in raw.items():
        doc = _leaf(value)
        listed = doc.get("errors") if isinstance(doc, dict) else None
        if not isinstance(listed, list):
            continue
        found = (_entry(str(device), item) for item in listed)
        errors.extend(error for error in found if error is not None)
    return errors


def read_mirror(path: Path | None = None) -> tuple[list[PhoneError], set[str]]:
    """The mirrored errors and notified keys; empty when missing or unreadable."""
    source = PHONE_ERRORS_FILE if path is None else path
    if not source.exists():
        return [], set()
    try:
        doc: Any = json.loads(source.read_text(encoding="utf-8"))
        errors = [PhoneError(**item) for item in doc["errors"]]
        notified = {str(key) for key in doc["notified"]}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        _logger.warning("phone error mirror %s unreadable: %s", source, exc)
        return [], set()
    return errors, notified


def write_mirror(
    errors: list[PhoneError], notified: set[str], *, path: Path | None = None
) -> bool:
    """Replace the mirror; False (logged) when it cannot be written."""
    target = PHONE_ERRORS_FILE if path is None else path
    doc = {"errors": [asdict(e) for e in errors], "notified": sorted(notified)}
    try:
        write_json(target, doc)
    except OSError as exc:
        _logger.warning("cannot write phone error mirror %s: %s", target, exc)
        return False
    return True


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _seen(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        _logger.warning("phone error has an unreadable last-seen: %s", exc)
        return None


def status_lines(*, path: Path | None = None, now: datetime | None = None) -> list[str]:
    """``--status``'s phone section; empty when nothing was seen lately."""
    cutoff = (_now() if now is None else now) - RECENT
    dated = [(_seen(e.last_seen), e) for e in read_mirror(path)[0]]
    recent = sorted(
        ((seen, e) for seen, e in dated if seen is not None and seen >= cutoff),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not recent:
        return []
    lines = ["phone errors (last 7 days):"]
    for seen, error in recent:
        when = seen.astimezone().strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {when}  {error.message}  x{error.count}  [{error.device[:8]}]")
    return lines
