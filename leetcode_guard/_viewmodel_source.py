"""What the suggestion list is drawn from, as one value.

Split from ``_viewmodel.py`` for the 250-line cap and to keep
``build_viewmodel`` inside the lint profile's argument limit: these four travel
together from the lock to the model on every tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leetcode_guard._auth import AuthState
    from leetcode_guard._pool_resolve import PoolResolution


@dataclass(frozen=True)
class ViewSource:
    """The pool, who may filter it, and how much of it to show."""

    pool: PoolResolution
    """The resolved suggestion list, including its provenance notes."""

    auth: AuthState
    """Whether solved problems could be filtered out."""

    limit: int
    """How many problems to list."""

    solved_slugs: frozenset[str] = frozenset()
    """Everything now known to be solved. Unlike ``pool``, which is resolved
    once before the window opens, this is recomputed every tick, so a problem
    solved *during* the lock stops being suggested."""
