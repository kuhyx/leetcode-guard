"""kuhy's shared credit logo on every lock surface and in ``--help``.

kuhy, 2026-11-21: "put my logo everywhere ... every single app, desktop
program". The logo comes from ``kuhy_credit`` (kuhyx/utils), never a copy.
Tk is mocked here, so the widget class is too; the pixels are checked by the
Xvfb screenshot of the demo lock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from kuhy_credit import credit_line

from leetcode_guard import _view_credit
from leetcode_guard._cli_args import build_parser
from leetcode_guard._view import build_guard_view
from leetcode_guard.tests._view_fixtures import CONFIG, model

if TYPE_CHECKING:
    import pytest


def test_every_surface_gets_the_credit_logo_bottom_right(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each surface builds one dark logo in its bottom-right corner."""
    widget = MagicMock()
    monkeypatch.setattr(_view_credit, "KuhyCredit", widget)
    surface = MagicMock()

    view = build_guard_view(surface, CONFIG, model(), output_name="DP-0")

    # On the surface's container, so a rebuilt surface never keeps a stale logo.
    widget.assert_called_once_with(
        view.container, theme="dark", size=CONFIG.type_px("display")
    )
    place = widget.return_value.place.call_args.kwargs
    assert (place["relx"], place["rely"], place["anchor"]) == (1, 1, "se")


def test_help_ends_with_the_credit_line() -> None:
    """``--help`` names who made it, from the shared credit text."""
    assert build_parser().format_help().rstrip().endswith(credit_line())
