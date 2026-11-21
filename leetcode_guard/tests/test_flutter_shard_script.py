"""Tests for scripts/flutter_test_shard.sh, the ci-mirror-flutter-test-N hooks.

A bare ``flutter test`` on the shared /tmp held a build slot over 60 s under
the build queue (perf.heavybuild, 2026-11-21) while the app suite takes ~8 s
alone. ``flutter`` here is a fake on ``PATH`` that logs its TMPDIR and args
and fails when ``FAKE_FLUTTER_FAIL`` is set; the repo is a throwaway in tmp.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "flutter_test_shard.sh"
GIT = shutil.which("git") or "/usr/bin/git"
BASH = shutil.which("bash") or "/usr/bin/bash"
TESTS = ("a_test.dart", "b/c_test.dart", "d_test.dart")
_FAKE_FLUTTER = """#!/bin/bash
printf '%s|%s\\n' "${TMPDIR:-}" "$*" >> "$FAKE_LOG"
if [[ "$1" == pub ]]; then
  [[ -n "${FAKE_PUB_FAIL:-}" ]] && exit 1
  [[ -n "${FAKE_OFFLINE_FAIL:-}" && "$*" == *--offline* ]] && exit 1
  exit 0
fi
[[ -z "${FAKE_FLUTTER_FAIL:-}" ]]
"""
_HOOKS = "".join(f"      - id: ci-mirror-flutter-test-{i}\n" for i in (1, 2))


@dataclass(frozen=True)
class Sandbox:
    """A throwaway repo with an app/ and a fake flutter."""

    repo: Path
    env: dict[str, str]
    log: Path

    def run(self, shard: str, **extra: str) -> subprocess.CompletedProcess[str]:
        """Run one shard and return the finished process."""
        return subprocess.run(
            [BASH, str(self.repo / "scripts" / "flutter_test_shard.sh"), shard],
            cwd=self.repo,
            env={**self.env, **extra},
            capture_output=True,
            text=True,
            check=False,
        )

    def calls(self) -> list[tuple[str, str]]:
        """Every (TMPDIR, args) the fake flutter saw."""
        if not self.log.exists():
            return []
        rows = self.log.read_text(encoding="utf-8").splitlines()
        return [(row.partition("|")[0], row.partition("|")[2]) for row in rows]

    def test_calls(self) -> list[tuple[str, str]]:
        """The `flutter test` calls only, without package resolution."""
        return [call for call in self.calls() if call[1].startswith("test ")]

    def pub_calls(self) -> list[str]:
        """The args of every `flutter pub` call."""
        return [args for _, args in self.calls() if args.startswith("pub ")]


def _sandbox(tmp_path: Path) -> Sandbox:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts")
    (repo / ".pre-commit-config.yaml").write_text(_HOOKS, encoding="utf-8")
    for name in TESTS:
        path = repo / "app" / "test" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("void main() {}\n", encoding="utf-8")
    (repo / "app" / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
    subprocess.run([GIT, "init", "-q"], cwd=repo, check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "flutter"
    fake.write_text(_FAKE_FLUTTER, encoding="utf-8")
    fake.chmod(0o755)
    shared = tmp_path / "shared-tmp"
    shared.mkdir()
    log = tmp_path / "flutter.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "TMPDIR": str(shared),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }
    return Sandbox(repo, env, log)


def test_each_shard_runs_with_a_private_tmpdir_and_two_isolates(tmp_path: Path) -> None:
    """Never the shared TMPDIR, removed after; two isolates; no implicit pub."""
    box = _sandbox(tmp_path)
    assert box.run("0/2").returncode == 0
    ((tmpdir, args),) = box.test_calls()
    assert tmpdir not in {"", box.env["TMPDIR"]}
    assert not Path(tmpdir).exists()
    assert "--concurrency=2" in args
    assert "--no-pub" in args


def test_packages_resolve_offline_only_when_the_pubspec_is_newer(
    tmp_path: Path,
) -> None:
    """A fresh package config skips the resolve entirely."""
    box = _sandbox(tmp_path)
    assert box.run("0/2").returncode == 0
    assert box.pub_calls() == ["pub get --offline"]
    config = box.repo / "app" / ".dart_tool" / "package_config.json"
    config.parent.mkdir()
    config.write_text("{}", encoding="utf-8")
    assert box.run("1/2").returncode == 0
    assert box.pub_calls() == ["pub get --offline"]


def test_a_failed_offline_resolve_falls_back_to_online(tmp_path: Path) -> None:
    """A dependency missing from the pub cache still resolves."""
    box = _sandbox(tmp_path)
    assert box.run("0/2", FAKE_OFFLINE_FAIL="1").returncode == 0
    assert box.pub_calls() == ["pub get --offline", "pub get"]


def test_an_unresolvable_pubspec_fails_the_shard(tmp_path: Path) -> None:
    """No tests run against packages that did not resolve."""
    box = _sandbox(tmp_path)
    result = box.run("0/2", FAKE_PUB_FAIL="1")
    assert result.returncode != 0
    assert "pub get" in result.stderr
    assert box.test_calls() == []


def test_the_shards_cover_every_test_file_exactly_once(tmp_path: Path) -> None:
    """Round-robin over the sorted files: none skipped, none twice."""
    box = _sandbox(tmp_path)
    assert box.run("0/2").returncode == 0
    assert box.run("1/2").returncode == 0
    ran = [
        arg
        for _, args in box.test_calls()
        for arg in args.split()
        if arg.endswith("_test.dart")
    ]
    assert sorted(ran) == sorted(f"test/{name}" for name in TESTS)


def test_an_unchanged_green_shard_is_not_run_again(tmp_path: Path) -> None:
    """The second run on the same tree returns from the stamp."""
    box = _sandbox(tmp_path)
    assert box.run("0/2").returncode == 0
    second = box.run("0/2")
    assert second.returncode == 0
    assert "cached green" in second.stderr
    assert len(box.test_calls()) == 1


def test_an_edit_reruns_the_shard(tmp_path: Path) -> None:
    """Any edit under app/test changes the key."""
    box = _sandbox(tmp_path)
    assert box.run("0/2").returncode == 0
    (box.repo / "app" / "test" / "a_test.dart").write_text(
        "// edited\n", encoding="utf-8"
    )
    assert box.run("0/2").returncode == 0
    assert len(box.test_calls()) == 2


def test_a_red_shard_is_never_cached(tmp_path: Path) -> None:
    """A failure writes no stamp, so it fails again."""
    box = _sandbox(tmp_path)
    assert box.run("0/2", FAKE_FLUTTER_FAIL="1").returncode != 0
    assert box.run("0/2", FAKE_FLUTTER_FAIL="1").returncode != 0
    assert len(box.test_calls()) == 2


def test_a_shard_count_that_does_not_match_the_hooks_fails(tmp_path: Path) -> None:
    """N must equal the hook count, or files would be dropped."""
    box = _sandbox(tmp_path)
    result = box.run("0/3")
    assert result.returncode != 0
    assert "does not match" in result.stderr
    assert box.test_calls() == []


def test_a_malformed_shard_fails(tmp_path: Path) -> None:
    """Anything but I/N is refused."""
    result = _sandbox(tmp_path).run("x")
    assert result.returncode != 0
    assert "I/N" in result.stderr
