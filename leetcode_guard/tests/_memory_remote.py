"""An in-memory crdt_sync ``RemoteStore``: real sync and E2E code runs over it.

RTDB-shaped: ``list_directory`` returns the next path segment under a node,
``get_string_map`` the string leaves directly under it.
"""

from __future__ import annotations


class MemoryRemote:
    """Text leaves keyed by full path; ``writes`` records every put in order."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.writes: list[str] = []

    def list_directory(self, path: str) -> list[str]:
        """The distinct next segments under ``path``."""
        start = f"{path}/"
        names = {
            key[len(start) :].split("/")[0]
            for key in self.data
            if key.startswith(start)
        }
        return sorted(names)

    def get_file_text(self, path: str) -> str | None:
        """The leaf at ``path``, or ``None``."""
        return self.data.get(path)

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        """Store ``text`` at ``path``."""
        del message
        self.data[path] = text
        self.writes.append(path)

    def get_string_map(self, path: str) -> dict[str, str]:
        """The leaves one level below ``path``."""
        start = f"{path}/"
        return {
            key[len(start) :]: value
            for key, value in self.data.items()
            if key.startswith(start) and "/" not in key[len(start) :]
        }

    def delete_file(self, path: str, *, message: str = "") -> None:
        """Drop the leaf at ``path``."""
        del message
        self.data.pop(path, None)

    def can_access_remote(self) -> bool:
        """Always reachable."""
        return True
