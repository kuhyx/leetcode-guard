"""Tests for username loading and client assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard._constants import DEFAULT_USERNAME
from leetcode_guard._settings import build_client, load_username

if TYPE_CHECKING:
    from pathlib import Path


def test_reads_the_configured_username(tmp_path: Path):
    path = tmp_path / "username"
    path.write_text("  someone  \n", encoding="utf-8")

    assert load_username(path) == "someone"


def test_only_the_first_line_is_used(tmp_path: Path):
    path = tmp_path / "username"
    path.write_text("first\nsecond\n", encoding="utf-8")

    assert load_username(path) == "first"


def test_missing_file_falls_back_to_the_default(tmp_path: Path):
    assert load_username(tmp_path / "absent") == DEFAULT_USERNAME


def test_empty_file_falls_back_to_the_default(tmp_path: Path):
    path = tmp_path / "username"
    path.write_text("   \n", encoding="utf-8")

    assert load_username(path) == DEFAULT_USERNAME


def test_unreadable_file_falls_back_to_the_default(tmp_path: Path):
    path = tmp_path / "username"
    path.mkdir()

    assert load_username(path) == DEFAULT_USERNAME


def test_default_path_is_resolved_at_call_time(config_dir: Path):
    """If the default were baked into the signature, the isolation fixture
    could not redirect it and this would read the real config directory."""
    (config_dir / "username").write_text("from-isolated-config", encoding="utf-8")

    assert load_username() == "from-isolated-config"


def test_build_client_wires_username_and_auth(tmp_path: Path):
    username_file = tmp_path / "username"
    username_file.write_text("configured", encoding="utf-8")

    client = build_client(
        username_file=username_file, cookies_file=tmp_path / "absent.json"
    )

    assert client.username == "configured"
    assert not client.auth.present
    assert callable(client.post)


def test_build_client_uses_the_isolated_defaults(config_dir: Path):
    client = build_client()

    assert client.username == DEFAULT_USERNAME
    assert not client.auth.present
