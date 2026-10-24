"""The one RTDB write the snapshot push makes, without the echo.

crdt_sync's ``put_file_text`` stores exactly the text leaf the snapshot wants,
but cannot ask for ``print=silent``, so RTDB answers every write by sending
the whole ~32 KB body straight back. At a push a minute that is ~1.4 GB a
month of the Spark plan's download quota -- shared by every kuhy app -- spent
on a response nobody reads. This is that write with the echo switched off:
same leaf, same auth (the signed-in client's own token provider), a 204.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Final, Protocol

from crdt_sync import CONFIG_FILE, FirebaseConfig, FirebaseSyncError
import requests

if TYPE_CHECKING:
    from collections.abc import Callable

    from crdt_sync import FirebaseSyncClient

_SILENT: Final = "silent"


class TextStore(Protocol):
    """The one capability a push needs; crdt_sync's clients have it too."""

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Store ``text`` at ``path``."""


@dataclass(frozen=True)
class SilentStore:
    """Writes text leaves to RTDB and asks for an empty reply.

    Attributes:
        database_url: The database's HTTPS origin.
        id_token: Returns a currently valid ID token.
        timeout_seconds: Per-request network timeout.
    """

    database_url: str
    id_token: Callable[[], str]
    timeout_seconds: float

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Store ``text`` at ``path`` as a JSON string leaf.

        ``message`` is ignored, as in crdt_sync: RTDB keeps no commit log.

        Raises:
            FirebaseSyncError: On any non-2xx response or network error.
        """
        del message
        url = f"{self.database_url.rstrip('/')}/{path}.json"
        try:
            response = requests.put(
                url,
                params={"auth": self.id_token(), "print": _SILENT},
                json=text,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            # The type only: requests puts the URL, ``?auth=<token>`` and
            # all, into the message, and this one reaches the journal.
            failure = f"network error writing {path}: {type(exc).__name__}"
            raise FirebaseSyncError(failure) from exc
        if not response.ok:
            failure = (
                f"writing {path} failed: HTTP {response.status_code} "
                f"{response.text.strip()}"
            )
            raise FirebaseSyncError(failure)

    def get_json(self, path: str) -> object:
        """The decoded JSON at ``path`` (``None`` when the node is empty).

        Raises:
            FirebaseSyncError: On any non-2xx response or network error.
        """
        url = f"{self.database_url.rstrip('/')}/{path}.json"
        try:
            response = requests.get(
                url, params={"auth": self.id_token()}, timeout=self.timeout_seconds
            )
        except requests.RequestException as exc:
            failure = f"network error reading {path}: {type(exc).__name__}"
            raise FirebaseSyncError(failure) from exc
        if not response.ok:
            failure = f"reading {path} failed: HTTP {response.status_code}"
            raise FirebaseSyncError(failure)
        return json.loads(response.text)


def silent_store_for(
    client: FirebaseSyncClient, *, timeout_seconds: float
) -> SilentStore:
    """Wrap a signed-in crdt_sync client's token provider."""
    config = FirebaseConfig.load(CONFIG_FILE)
    return SilentStore(config.database_url, client.auth.id_token, timeout_seconds)
