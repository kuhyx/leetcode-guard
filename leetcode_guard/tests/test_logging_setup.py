"""Tests for logging configuration."""

from __future__ import annotations

import logging

import pytest

from leetcode_guard import _logging_setup


@pytest.fixture(autouse=True)
def _reset():
    _logging_setup.reset_logging_for_tests()
    yield
    _logging_setup.reset_logging_for_tests()


def test_configures_once(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        _logging_setup.logging, "basicConfig", lambda **kwargs: calls.append(kwargs)
    )

    _logging_setup.configure_logging()
    _logging_setup.configure_logging()

    assert len(calls) == 1


def test_logs_to_stderr_never_stdout(monkeypatch: pytest.MonkeyPatch):
    """stdout is the MCP server's JSON-RPC channel; a handler there corrupts
    the protocol."""
    captured: dict = {}
    monkeypatch.setattr(_logging_setup.logging, "basicConfig", captured.update)

    _logging_setup.configure_logging()

    assert captured["stream"] is _logging_setup.sys.stderr


def test_verbose_selects_debug(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}
    monkeypatch.setattr(_logging_setup.logging, "basicConfig", captured.update)

    _logging_setup.configure_logging(verbose=True)

    assert captured["level"] == logging.DEBUG


def test_default_selects_warning(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}
    monkeypatch.setattr(_logging_setup.logging, "basicConfig", captured.update)

    _logging_setup.configure_logging()

    assert captured["level"] == logging.WARNING
