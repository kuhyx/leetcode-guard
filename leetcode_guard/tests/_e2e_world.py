"""One scratch world for the theory-first e2e scripts (``scripts/e2e_theory*``).

A scratch ``$HOME`` (data, tutor files, runtime dir), a scratch HMAC key, and
a private Xvfb started with ``-displayfd`` (never ``:0``). Every process runs
``scripts.e2e_theory_roles`` with ``-m`` from :data:`ROOT`, so it imports this
checkout, never the editable install (the role checks ``__file__``). Children
are killed by PID; :meth:`World.close` proves no window and no child is left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Final

from gatelock.log_integrity import verify_entry_hmac

ROOT: Final = Path(__file__).resolve().parents[2]
OUT: Final = Path.home() / "data/claude-scratch/lc-stage4/e2e"
ROLES: Final = "scripts.e2e_theory_roles"
ALGO: Final = "leetcode-easy-algorithms-in-typescript"
SCREEN: Final = "1600x1200x24"
PAINTED_BYTES: Final = 10_000


@dataclass
class World:
    """A case's scratch dir, key, display and children."""

    case: str
    dir: Path = field(init=False)
    display: str = ""
    xvfb: subprocess.Popen[bytes] | None = None
    shots: list[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        """A fresh scratch HOME and key for this case."""
        self.dir = OUT / self.case
        shutil.rmtree(self.dir, ignore_errors=True)
        (self.home / ".local/share/leetcode_guard").mkdir(parents=True)
        (self.home / "run").mkdir(mode=0o700)
        (self.dir / "key").write_bytes(secrets.token_bytes(32))

    @property
    def home(self) -> Path:
        """The scratch ``$HOME``."""
        return self.dir / "home"

    @property
    def data(self) -> Path:
        """The guard's scratch data dir."""
        return self.home / ".local/share/leetcode_guard"

    @property
    def tutor(self) -> Path:
        """The tutor's scratch data dir."""
        return self.home / ".local/share/tutor"

    def env(self, ac: str = "") -> dict[str, str]:
        """The child environment: scratch everything, the private display."""
        env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}
        env |= {
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.home / "run"),
            "PYTHONUSERBASE": str(Path.home() / ".local"),
            "TMPDIR": "/var/disktmp",
            "E2E_KEY": str(self.dir / "key"),
            "E2E_ROOT": str(ROOT),
            "E2E_MODEL": str(self.dir / "model.json"),
            "E2E_AC": ac,
        }
        if self.display:
            env["DISPLAY"] = self.display
        return env

    def role(self, *args: str, ac: str = "") -> tuple[int, str]:
        """Run one role to completion: exit code and stdout+stderr."""
        done = subprocess.run(
            [sys.executable, "-m", ROLES, *args],
            cwd=ROOT,
            env=self.env(ac),
            capture_output=True,
            text=True,
            check=False,
            timeout=40,
        )
        return done.returncode, done.stdout + done.stderr

    def start_x(self) -> None:
        """A private display (once per world); ``-displayfd`` picks a free number."""
        if self.xvfb is not None:
            return
        pipe_out, pipe_in = os.pipe()
        argv = ["Xvfb", "-displayfd", str(pipe_in), "-screen", "0", SCREEN]
        self.xvfb = subprocess.Popen(  # pylint: disable=consider-using-with
            [*argv, "-nolisten", "tcp"],
            pass_fds=(pipe_in,),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.close(pipe_in)
        number = os.read(pipe_out, 16).decode().strip()
        os.close(pipe_out)
        self.display = f":{number}"

    def windows(self) -> int:
        """Top-level windows bigger than 1x1 on the private display.

        The X wait's probe connection owns an unnamed 1x1 window; it is not a
        lock surface, so it does not count.
        """
        tree = subprocess.run(
            ["xwininfo", "-root", "-children", "-display", self.display],
            check=False,
            text=True,
            capture_output=True,
        ).stdout.splitlines()
        surfaces = [row for row in tree if row.startswith("     0x")]
        return len([row for row in surfaces if not re.search(r"\b1x1\+", row)])

    def x_state(self) -> str:
        """The private display's health, for a failure line."""
        exited = self.xvfb.poll() if self.xvfb is not None else "never started"
        argv = ["xwininfo", "-root", "-display", self.display]
        answers = subprocess.run(argv, check=False, capture_output=True).returncode == 0
        server = "alive" if exited is None else f"exited {exited}"
        return f"X {self.display or '-'}: Xvfb {server}, answers={answers}"

    def shoot(self, name: str) -> Path:
        """The largest of a few root captures (an early one is the bare backdrop)."""
        out = self.dir / f"{name}.png"
        best = 0
        for _ in range(6):
            try_path = self.dir / "try.png"
            subprocess.run(
                ["import", "-display", self.display, "-window", "root", str(try_path)],
                check=False,
                capture_output=True,
            )
            size = try_path.stat().st_size if try_path.exists() else 0
            if size > best:
                best = size
                shutil.copy(try_path, out)
            time.sleep(0.5)
        self.shots.append(out)
        return out if best >= PAINTED_BYTES else Path()

    def lock(
        self, *, seconds: float, ac: str = "", until: str = "", shot: str = ""
    ) -> tuple[int | None, str, int]:
        """Run the real lock for up to ``seconds``: (exit code or None, output, max windows).

        Stops early once the process exits, or once ``until`` names a file in
        the case dir that exists after a window showed. ``shot`` names a screenshot taken then,
        while the lock is still up. A still-running lock is terminated by PID;
        one that never showed a window stalled, and dumps its stack to the log first.
        """
        log = self.dir / "lock.log"
        with log.open("w", encoding="utf-8") as sink:
            child = subprocess.Popen(  # pylint: disable=consider-using-with
                [sys.executable, "-m", ROLES, "lock"],
                cwd=ROOT,
                env=self.env(ac),
                stdout=sink,
                stderr=subprocess.STDOUT,
            )
            most = 0
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and child.poll() is None:
                most = max(most, self.windows())
                if until and most and (self.dir / until).exists():
                    break
                time.sleep(0.25)
            code = child.poll()
            if code is None and shot:
                self.shoot(shot)
            if code is None and not most:
                child.send_signal(signal.SIGUSR1)
                time.sleep(0.5)
            if code is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logging.getLogger(__name__).warning("lock ignored SIGTERM, killing")
                    child.kill()
                    child.wait()
        return code, log.read_text(encoding="utf-8"), most

    def model(self) -> dict[str, Any] | None:
        """The last view model the lock built, as the role recorded it."""
        path = self.dir / "model.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def phase_file(self) -> dict[str, Any] | None:
        """``theory_phase.json``'s row if present AND verified under the scratch key."""
        path = self.data / "theory_phase.json"
        if not path.exists():
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        ok = isinstance(row, dict) and verify_entry_hmac(row, key_file=self.dir / "key")
        return row if ok else {"unverified": row}

    def entry_ids(self, prefix: str) -> list[str]:
        """Guard ledger entry ids starting with ``prefix``, in file order."""
        path = self.data / "ledger.json"
        if not path.exists():
            return []
        doc = json.loads(path.read_text(encoding="utf-8"))
        entries = doc.get("entries", []) if isinstance(doc, dict) else doc
        ids = [str(e.get("entry_id", "")) for e in entries if isinstance(e, dict)]
        return [i for i in ids if i.startswith(prefix)]

    def close(self) -> list[str]:
        """Stop Xvfb; what was left behind (windows, role processes)."""
        left: list[str] = []
        if self.xvfb is not None:
            if self.windows():
                left.append(f"{self.windows()} windows on {self.display}")
            self.xvfb.terminate()
            self.xvfb.wait(timeout=5)
        procs = subprocess.run(
            ["pgrep", "-f", f"-m {ROLES}"], capture_output=True, text=True, check=False
        )
        left += [f"process {pid}" for pid in procs.stdout.split()]
        return left
