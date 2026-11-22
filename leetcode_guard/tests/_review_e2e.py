"""One scratch world for ``scripts/verify_review_first``: HOME, key, Xvfb, fakes.

Each scenario gets its own world: a scratch ``$HOME`` and ``XDG_RUNTIME_DIR``,
a scratch HMAC key, a private Xvfb (``-displayfd``, never ``:0``) and a
``fakebin`` first on ``PATH`` that holds the tutor stub, a recording
``xdg-open`` and a ``systemd-run`` shim. The shim stands in for ``systemd-run
--user --scope``, which would create a unit in the live user manager; it runs
the command in place. The lock (``scripts.verify_review_first_child``, ``-m``)
appends what its widgets show to ``obs.jsonl``. Everything is killed by PID.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)
ROOT: Final = Path(__file__).resolve().parents[2]
CHILD: Final = "scripts.verify_review_first_child"
ALGO: Final = "leetcode-easy-algorithms-in-typescript"
MODULE: Final = "prefix-sums"
ROUTE: Final = f"/review/{ALGO}/{MODULE}"
SCREEN: Final = "1600x1200x24"
STOP_SECONDS: Final = 8
X_READY_SECONDS: Final = 5.0
X_TRIES: Final = 3

State = dict[str, Any]


@dataclass
class World:
    """A scenario's scratch dir, key, display and children."""

    dir: Path
    display: str = ""
    procs: list[subprocess.Popen[bytes]] = field(default_factory=list)
    lock: subprocess.Popen[bytes] | None = None

    def __post_init__(self) -> None:
        """A fresh scratch HOME, runtime dir and key."""
        (self.home / ".local/share/leetcode_guard").mkdir(parents=True)
        self.tutor.mkdir(parents=True)
        (self.home / "run").mkdir(mode=0o700)
        (self.dir / "key").write_bytes(secrets.token_hex(32).encode())

    @property
    def home(self) -> Path:
        """The scratch ``$HOME``."""
        return self.dir / "home"

    @property
    def tutor(self) -> Path:
        """The tutor's scratch data dir."""
        return self.home / ".local/share/tutor"

    @property
    def log(self) -> Path:
        """The lock's stdout and stderr."""
        return self.dir / "lock.log"

    def start_x(self) -> None:
        """A private display that answers a client; a server that does not is retried.

        ``-displayfd`` picks a free number without a race. 2026-11-22: once in
        a run of eight, the lock was refused on the display it was handed.
        Xvfb's stderr is kept in ``xvfb.err`` for that case.
        """
        for _ in range(X_TRIES):
            pipe_out, pipe_in = os.pipe()
            argv = ["Xvfb", "-displayfd", str(pipe_in), "-screen", "0", SCREEN]
            with (self.dir / "xvfb.err").open("ab") as err:
                xvfb = subprocess.Popen(  # pylint: disable=consider-using-with
                    [*argv, "-nolisten", "tcp"],
                    pass_fds=(pipe_in,),
                    stdout=subprocess.DEVNULL,
                    stderr=err,
                )
            self.procs.append(xvfb)
            os.close(pipe_in)
            self.display = f":{os.read(pipe_out, 16).decode().strip()}"
            os.close(pipe_out)
            probe = ["xdpyinfo", "-display", self.display]
            deadline = time.monotonic() + X_READY_SECONDS
            while time.monotonic() < deadline:
                if not subprocess.run(
                    probe, check=False, capture_output=True
                ).returncode:
                    return
                time.sleep(0.05)
            _logger.warning(
                "%s never answered (Xvfb %s); retrying", self.display, xvfb.poll()
            )
            xvfb.kill()

    def fakebin(self, script: str = "exit 0", *, scope_shebang: str = "") -> None:
        """Tutor stub (argv, then ``script``), xdg-open, systemd-run shim.

        A ``scope_shebang`` naming a missing interpreter makes ``Popen`` raise.
        """
        fake = self.dir / "fakebin"
        fake.mkdir()
        rec = self.dir
        (fake / "tutor").write_text(
            f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{rec}/tutor.argv"\n{script}\n'
        )
        (fake / "xdg-open").write_text(
            f'#!/bin/bash\nprintf "%s\\n" "$*" >> "{rec}/browser.log"\n'
        )
        (fake / "systemd-run").write_text(
            f"{scope_shebang or '#!/bin/bash'}\n"
            f'printf "%s\\n" "$*" >> "{rec}/scope.log"\n'
            'while [[ "${1:-}" == --* ]]; do shift; done\nexec "$@"\n'
        )
        for path in fake.iterdir():
            path.chmod(0o755)

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Scratch everything, the private display, ``fakebin`` first."""
        drop = {"DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"}
        env = {k: v for k, v in os.environ.items() if k not in drop}
        return env | {
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.home / "run"),
            # HOME moves the user site; the editable gatelock lives in the real one.
            "PYTHONUSERBASE": str(Path.home() / ".local"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": f"{self.dir / 'fakebin'}:/usr/local/bin:/usr/bin",
            "E2E_KEY": str(self.dir / "key"),
            "E2E_OBS": str(self.dir / "obs.jsonl"),
            "DISPLAY": self.display,
            **(extra or {}),
        }

    def start_lock(self, *args: str, extra: dict[str, str] | None = None) -> None:
        """The real lock (``_cli.main``) under this world, observed."""
        with self.log.open("wb") as sink:
            self.lock = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, "-m", CHILD, *args],
                cwd=ROOT,
                env=self.env(extra),
                stdout=sink,
                stderr=subprocess.STDOUT,
            )
        self.procs.append(self.lock)

    def states(self) -> list[State]:
        """Every state the observer recorded, in order."""
        path = self.dir / "obs.jsonl"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        # Only up to the last newline: the observer may be mid-write.
        return [json.loads(line) for line in text[: text.rfind("\n") + 1].splitlines()]

    def last(self) -> State | None:
        """The newest recorded state."""
        states = self.states()
        return states[-1] if states else None

    def wait(
        self, want: Callable[[State], bool], *, after: float = 0.0, timeout: float = 20
    ) -> State | None:
        """The first state at or after ``after`` that ``want``s; ``None`` on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hit = next((s for s in self.states() if s["t"] >= after and want(s)), None)
            if hit is not None or (
                self.lock is not None and self.lock.poll() is not None
            ):
                return hit
            time.sleep(0.02)
        return None

    def click(self, xywh: list[int]) -> float:
        """A real pointer click in the middle of ``xywh``; the click's time."""
        x, y, w, h = xywh
        env = {**os.environ, "DISPLAY": self.display}
        move = ["xdotool", "mousemove", str(x + w // 2), str(y + h // 2)]
        subprocess.run(move, env=env, check=True, timeout=10)
        time.sleep(0.3)  # Tk must see the pointer enter the button first
        stamp = time.time()
        subprocess.run(["xdotool", "click", "1"], env=env, check=True, timeout=10)
        return stamp

    def grab_held(self) -> bool:
        """An independent X client: can it take the keyboard grab right now?"""
        x = importlib.import_module("Xlib.X")
        dpy = importlib.import_module("Xlib.display").Display(self.display)
        try:
            owner_events = True
            got = dpy.screen().root.grab_keyboard(
                owner_events, x.GrabModeAsync, x.GrabModeAsync, x.CurrentTime
            )
            dpy.sync()
            if got == x.GrabSuccess:
                dpy.ungrab_keyboard(x.CurrentTime)
                dpy.sync()
                return False
            return True
        finally:
            dpy.close()

    def lines(self, pattern: str) -> list[str]:
        """Log lines of the lock containing ``pattern``."""
        return [ln for ln in self.recorded("lock.log") if pattern in ln]

    def recorded(self, name: str) -> list[str]:
        """What a fake recorded (``tutor.argv``, ``scope.log``, ``browser.log``)."""
        path = self.dir / name
        return path.read_text(errors="replace").splitlines() if path.exists() else []

    def close(self) -> None:
        """SIGTERM every child by PID (lock first), kill what ignores it."""
        for proc in reversed(self.procs):
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=STOP_SECONDS)
                except subprocess.TimeoutExpired:
                    _logger.warning("pid %d ignored SIGTERM; killing it", proc.pid)
                    proc.kill()
                    proc.wait()
