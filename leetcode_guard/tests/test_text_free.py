"""The lock paints no words (kuhy's textgate rule, 2026-11-08).

Every widget the lock, the escape form and the study strip ask Tk for is
collected from the mocked ``tk`` module, and none may carry a run of two or
more letters -- except content: problem titles (LeetCode's, not ours), the
break-glass command and the key chords the user has to *type*, and URLs.

Built through the real ``build_viewmodel`` rather than hand-made models, so a
sentence the view model generates fails here even though no widget code
names it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from gatelock import GrabPolicy, LockConfig
import pytest

from leetcode_guard._debt import Debt
from leetcode_guard._escape_flow import EscapeHatch, build_tracker
from leetcode_guard._gate import DayContext, decide
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._study_strip import build_strip
from leetcode_guard._study_strip_text import StripText
from leetcode_guard._view import build_guard_view, install_demo_close_button
from leetcode_guard._view_types import ViewHooks
from leetcode_guard._view_update import apply_viewmodel
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    SATURDAY,
    forged_credit,
    ledger_with_credits,
)
from leetcode_guard.tests.test_viewmodel import (
    BLIND_PROBE,
    CHECKED_AT,
    OK_PROBE,
    SIGNED_OUT,
    pool_of,
)

if TYPE_CHECKING:
    from pathlib import Path

WORD = re.compile(r"[A-Za-z]{2,}")
URL = re.compile(r"https?://\S+")
TYPED = (
    "systemctl --user stop leetcode-guard.service",
    'setxkbmap -option ""',
    "Ctrl+Alt+F2",
    "Ctrl+Alt+F1",
)
"""What the user has to type to get out: content, by settled decision 2."""

SLUGS = ("two-sum", "add-two-numbers", "longest-substring")
TITLES = tuple(slug.replace("-", " ").title() for slug in SLUGS)
_WIDGETS = ("Label", "Button", "Message", "Checkbutton", "Radiobutton")


def painted(fake: MagicMock) -> list[str]:
    """Every ``text=`` handed to a widget, at construction or by configure."""
    texts: list[str] = []
    for name in _WIDGETS:
        cls = getattr(fake, name)
        widget = cls.return_value
        calls = [
            *cls.call_args_list,
            *widget.configure.call_args_list,
            *widget.config.call_args_list,
        ]
        texts.extend(str(c.kwargs["text"]) for c in calls if "text" in c.kwargs)
    canvas = fake.Canvas.return_value
    texts.extend(
        str(c.kwargs["text"])
        for c in canvas.create_text.call_args_list
        if "text" in c.kwargs
    )
    return texts


def words_in(text: str) -> list[str]:
    """Letters left once titles, typed commands and URLs are taken out."""
    rest = URL.sub(" ", text)
    for allowed in (*TYPED, *TITLES):
        rest = rest.replace(allowed, " ")
    return WORD.findall(rest)


def assert_text_free(fake: MagicMock) -> None:
    """Fail if any painted text holds a word outside the allowed set."""
    texts = painted(fake)
    assert texts, "nothing was painted: the guard would pass vacuously"
    offenders = {text: words_in(text) for text in texts if words_in(text)}
    assert offenders == {}


def _model(ledger: Ledger, key: Path, **kwargs: Any):
    """A view model for one lock state, with defaults for the rest."""
    day = kwargs.pop("day", MONDAY)
    context = kwargs.pop("context", DayContext())
    decision = decide(ledger, day=day, now=NOW, key_file=key, context=context)
    source = ViewSource(
        kwargs.pop("pool", pool_of(*SLUGS)),
        SIGNED_OUT,
        limit=10,
        solved_slugs=kwargs.pop("solved", frozenset()),
    )
    probe = kwargs.pop("probe", OK_PROBE)
    return build_viewmodel(decision, source, probe, checked_at=CHECKED_AT, **kwargs)


def _surfaces(key: Path, tmp: Path) -> list[Any]:
    """One model per state the lock can show."""
    refused = ledger_with_credits(1, day=MONDAY, key_file=key)
    append(refused, [forged_credit()])
    save_ledger(tmp / "ledger.json", refused)
    owing = DayContext(debt=Debt(owed=9, repaid=2, missed_days=7))
    return [
        _model(Ledger(), key, show_escape=True),
        _model(Ledger(), key, day=SATURDAY, probe=BLIND_PROBE),
        _model(Ledger(), key, solved=frozenset({SLUGS[0]})),
        _model(Ledger(), key, solved=frozenset(SLUGS)),
        _model(ledger_with_credits(3, day=MONDAY, key_file=key), key),
        _model(Ledger(), key, context=owing, pool=pool_of()),
        _model(Ledger(), key, context=DayContext(sick_day=True)),
        _model(Ledger(), key, context=DayContext(focus_day="thesis")),
        _model(load_ledger(tmp / "ledger.json", key_file=key), key),
        _model(Ledger(), tmp / "absent.key"),
    ]


@pytest.mark.parametrize("disable_vt", [True, False])
def test_no_surface_state_paints_a_word(
    tk_mock, tmp_path: Path, hmac_key: Path, disable_vt: bool
):
    """No lock-surface state paints a word, with or without VT switching."""
    config = LockConfig(
        mode="hard", grab=GrabPolicy(kind="local", disable_vt=disable_vt)
    )
    hooks = ViewHooks(on_escape=lambda: None, on_open=lambda _url: None)
    models = _surfaces(hmac_key, tmp_path)
    view = build_guard_view(
        MagicMock(), config, models[0], output_name="DP-0", hooks=hooks
    )
    for model in models:
        apply_viewmodel([view], model)
    install_demo_close_button(MagicMock(), config, lambda: None)

    assert_text_free(tk_mock)


def test_the_escape_form_paints_no_word(tk_mock, tmp_path: Path, hmac_key: Path):
    """The escape form, even after a refused submit, paints no word."""
    tracker = build_tracker(tmp_path / "escape.json", key_file=hmac_key)
    hatch = EscapeHatch(tracker, LockConfig(), on_granted=lambda _r: None)
    form = hatch.show(MagicMock())
    form.reason.get.return_value = ""
    form.onset.get.return_value = ""
    form.description.get.return_value = "short"

    hatch.submit()

    assert_text_free(tk_mock)


def test_the_study_strip_paints_no_word(tk_mock):
    """The study strip paints no word."""
    rect = MagicMock(x=0, y=0, width=1920, height=1080)
    strip = build_strip(
        MagicMock(),
        LockConfig(),
        StripText(elapsed_seconds=75.0, needed=2),
        rect=rect,
        on_back=lambda: None,
    )
    strip.tick(StripText(elapsed_seconds=80.0, needed=1, verifying=True))
    strip.tick(StripText(elapsed_seconds=81.0, needed=1, fast_path_down=True))

    assert_text_free(tk_mock)
