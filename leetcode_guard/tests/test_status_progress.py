"""The projection section of the window, and the window state behind it."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from gatelock import LockConfig

from leetcode_guard import status_view
from leetcode_guard._progress import write_progress_cache
from leetcode_guard._status_progress import (
    FETCHING_NOTE,
    ProjectionControls,
    section_progress,
)
from leetcode_guard._status_projection import PAST_TARGET, build_report
from leetcode_guard._status_sections import render_sections
from leetcode_guard.tests.test_projection import progress
from leetcode_guard.tests.test_status_view_part3 import a_root, full_for

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = LockConfig()


def label_texts(tk_mock) -> list[str]:
    return [
        call.kwargs["text"]
        for call in tk_mock.Label.call_args_list
        if "text" in call.kwargs
    ]


def snapshot_for(data_dir: Path, hmac_key: Path):
    return full_for(data_dir, hmac_key).gate


def controls_for(snapshot, target="31.12.2999", **extra) -> ProjectionControls:
    return ProjectionControls(
        target_text=target,
        report=build_report(snapshot, progress(), target),
        on_project=extra.pop("on_project", lambda _text: None),
        **extra,
    )


def test_the_section_draws_counts_in_monospace_and_the_working_as_captions(
    data_dir: Path, hmac_key: Path, tk_mock
):
    snapshot = snapshot_for(data_dir, hmac_key)

    section_progress(a_root(tk_mock), CONFIG, controls_for(snapshot))

    texts = label_texts(tk_mock)
    assert any(text.startswith("Easy ") for text in texts)
    assert any(text.startswith("By 31.12.2999") for text in texts)
    assert FETCHING_NOTE not in texts
    mono_fonts = [
        call.kwargs["font"]
        for call in tk_mock.Label.call_args_list
        if call.kwargs.get("text", "").startswith("All ")
    ]
    assert mono_fonts
    assert all("monospace" in str(font) for font in mono_fonts)


def test_the_section_says_when_a_fetch_is_in_flight(data_dir, hmac_key, tk_mock):
    snapshot = snapshot_for(data_dir, hmac_key)

    section_progress(a_root(tk_mock), CONFIG, controls_for(snapshot, fetching=True))

    assert FETCHING_NOTE in label_texts(tk_mock)


def test_an_unusable_date_is_one_red_line_and_no_counts(data_dir, hmac_key, tk_mock):
    snapshot = snapshot_for(data_dir, hmac_key)

    section_progress(a_root(tk_mock), CONFIG, controls_for(snapshot, "01.01.2000"))

    red = [
        call.kwargs["text"]
        for call in tk_mock.Label.call_args_list
        if call.kwargs.get("fg") == CONFIG.palette.danger
    ]
    assert red == [PAST_TARGET]
    assert not any(t.startswith("By ") for t in label_texts(tk_mock))


def test_the_entry_hands_its_text_to_on_project_on_enter_and_on_the_button(
    data_dir, hmac_key, tk_mock
):
    snapshot = snapshot_for(data_dir, hmac_key)
    asked: list[str] = []
    entry = tk_mock.Entry.return_value
    entry.get.return_value = "26.09.2026"

    section_progress(
        a_root(tk_mock), CONFIG, controls_for(snapshot, on_project=asked.append)
    )

    entry.insert.assert_called_once_with(0, "31.12.2999")
    on_return = next(
        call.args[1] for call in entry.bind.call_args_list if call.args[0] == "<Return>"
    )
    on_return(MagicMock())
    project_button = next(
        call.kwargs["command"]
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == "Project"
    )
    project_button()

    assert asked == ["26.09.2026", "26.09.2026"]


def test_render_sections_skips_the_section_without_controls(
    data_dir, hmac_key, tk_mock
):
    render_sections(a_root(tk_mock), CONFIG, full_for(data_dir, hmac_key))

    assert "Progress & projection" not in label_texts(tk_mock)


def test_the_window_reprojects_for_a_new_date_and_keeps_it_across_refresh(
    data_dir: Path, hmac_key: Path, tk_mock
):
    window = status_view.StatusWindow(
        a_root(tk_mock),
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )
    assert window.target_text.startswith("31.12.")

    window.project("31.12.2999")
    assert any(t.startswith("By 31.12.2999") for t in label_texts(tk_mock))

    tk_mock.Label.reset_mock()
    window.render(full_for(data_dir, hmac_key))
    assert window.target_text == "31.12.2999"
    assert any(t.startswith("By 31.12.2999") for t in label_texts(tk_mock))


def test_the_window_shows_the_mirror_then_the_live_answer(
    data_dir: Path, hmac_key: Path, tk_mock
):
    write_progress_cache(data_dir / "progress_cache.json", progress(easy=10))
    window = status_view.StatusWindow(
        a_root(tk_mock),
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )
    assert any(t.startswith("Easy      10 /") for t in label_texts(tk_mock))

    tk_mock.Label.reset_mock()
    window.fetching = True
    window.set_progress(progress(easy=55))
    assert window.fetching is False
    assert any(t.startswith("Easy      55 /") for t in label_texts(tk_mock))

    # A failed fetch keeps what was there rather than blanking it.
    tk_mock.Label.reset_mock()
    window.set_progress(None)
    assert any(t.startswith("Easy      55 /") for t in label_texts(tk_mock))


def test_main_starts_the_fetch_and_close_cancels_it(monkeypatch, data_dir, tk_mock):
    root = a_root(tk_mock)
    monkeypatch.setattr(status_view.tk, "Tk", lambda: root)
    fetch = MagicMock()
    fetch.start.side_effect = [True, False]
    monkeypatch.setattr(status_view, "BackgroundFetch", lambda *_a, **_k: fetch)

    status_view.main([])

    fetch.start.assert_called_once()
    assert FETCHING_NOTE in label_texts(tk_mock)
    # Refresh while a fetch is running re-reads disk but does not double up.
    refresh = next(
        call.kwargs["command"]
        for call in tk_mock.Button.call_args_list
        if call.kwargs.get("text") == "Refresh"
    )
    refresh()
    assert fetch.start.call_count == 2
    close = next(
        call.args[1]
        for call in root.protocol.call_args_list
        if call.args[0] == "WM_DELETE_WINDOW"
    )
    close()
    fetch.cancel.assert_called_once()
    root.destroy.assert_called_once()
