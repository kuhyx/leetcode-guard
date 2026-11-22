#!/usr/bin/env python3
r"""Measure the longest Tk-loop wait of an idle lock while its memory is reclaimed.

2026-11-22: the production lock filed ``perf.slow: slow wait: tk.mainloop`` at
up to 1.7 s. Its own work per tick is 20-30 ms; the rest was swap-in. The idle
lock had 57 MB in swap, zram was full, so every tick faulted its pages back
from the disk swapfiles under build load. ``leetcode-guard.service`` therefore
pins ``MemorySwapMax=0``. This harness is the red/green check for that line:

* a working set of ``--working-set-mb`` of heap pages stands in for the lock's
  anon memory (Tk, the pool, the model), and every tick touches all of it, the
  way a repaint walks the rows;
* a ``tk.after`` tick every ``--tick-ms`` measures how late it fired, which is
  what gatelock's stall watch reports as a wait;
* a second thread writes ``"<N>M swappiness=200"`` to this process's own
  cgroup ``memory.reclaim``, which pushes anon pages to swap on purpose. It is
  not the Tk thread, so the write itself never blocks the loop.

Run it in its own transient scope, with and without the unit's directive::

    xvfb-run -a systemd-run --user --scope -p MemorySwapMax=0 \
        python3 scripts/verify_stall_swap.py --expect-swap-max 0

Red needs swap that is slow to read: disk, not zram (the host's zram keeps it
at 0.1 s). The recipe that went red, in a vmbox guest whose only swap is a
swapfile on ``/dev/vda``, as a root scope because the user manager delegates
no io controller (2026-11-22: 2.219 s without the limit, 0.002 s with it)::

    sudo env DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY systemd-run --scope \
        -p "IOReadBandwidthMax=/dev/vda 32M" [-p MemorySwapMax=0] \
        python3 verify_stall_swap.py [--expect-swap-max 0]

The bandwidth cap stands in for the disk contention of a build; swap-in reads
are charged to the faulting cgroup, so it slows exactly the refaults.
Prints ``max_wait_s=<seconds>``; exits 1 at ``--budget`` or more, and 2 when
the cgroup's ``memory.swap.max`` is not what ``--expect-swap-max`` says (a
green run under an undelegated memory controller proves nothing).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk

_logger = logging.getLogger("verify_stall_swap")
PAGE = 4096
CGROUP_ROOT = Path("/sys/fs/cgroup")


@dataclass
class Waits:
    """Tick lateness, written by the Tk thread only."""

    expected_s: float
    last: float = field(default_factory=time.monotonic)
    worst_s: float = 0.0
    ticks: int = 0

    def tick(self) -> None:
        """Record how much later than ``expected_s`` this tick fired."""
        now = time.monotonic()
        self.worst_s = max(self.worst_s, now - self.last - self.expected_s)
        self.last = now
        self.ticks += 1


def own_cgroup() -> Path:
    """This process's cgroup v2 directory."""
    line = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip()
    return CGROUP_ROOT / line.split("::", 1)[1].lstrip("/")


def read_knob(cgroup: Path, name: str) -> str:
    """One cgroup file, stripped; ``"absent"`` when the controller is off."""
    try:
        return (cgroup / name).read_text(encoding="utf-8").strip()
    except OSError as exc:
        _logger.warning("cannot read %s: %s", cgroup / name, exc)
        return "absent"


def make_working_set(megabytes: int) -> list[bytearray]:
    """Distinct heap pages, each dirtied once so it is real anon memory."""
    blocks = [bytearray(PAGE) for _ in range(megabytes * 1024 * 1024 // PAGE)]
    for index, block in enumerate(blocks):
        block[0] = index % 251 + 1
    return blocks


def touch(blocks: list[bytearray]) -> int:
    """Read one byte of every page: a swapped-out page faults back in here."""
    return sum(block[0] for block in blocks)


def reclaim_forever(
    cgroup: Path, megabytes: int, every_s: float, stop: threading.Event
) -> None:
    """Push the cgroup's anon pages toward swap until ``stop`` is set."""
    request = f"{megabytes}M swappiness=200".encode()
    knob = cgroup / "memory.reclaim"
    while not stop.wait(every_s):
        try:
            fd = os.open(knob, os.O_WRONLY)
            try:
                os.write(fd, request)
            finally:
                os.close(fd)
        except OSError as exc:
            # EAGAIN is the kernel saying it could not reclaim that much, which
            # is the expected answer when swap is forbidden. Anything else is
            # worth seeing too, so both are logged rather than raised.
            _logger.warning("memory.reclaim refused %s: %s", request.decode(), exc)


@dataclass(frozen=True)
class Options:
    """Parsed command line."""

    seconds: float
    tick_ms: int
    working_set_mb: int
    reclaim_mb: int
    reclaim_every_s: float
    budget_s: float
    expect_swap_max: str | None


def parse(argv: list[str]) -> Options:
    """The command line, with defaults sized to stay well under 60 s."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--tick-ms", type=int, default=1500)
    parser.add_argument("--working-set-mb", type=int, default=64)
    parser.add_argument("--reclaim-mb", type=int, default=128)
    parser.add_argument("--reclaim-every-s", type=float, default=1.0)
    parser.add_argument("--budget", type=float, default=1.0)
    parser.add_argument("--expect-swap-max", default=None)
    args = parser.parse_args(argv)
    return Options(
        seconds=args.seconds,
        tick_ms=args.tick_ms,
        working_set_mb=args.working_set_mb,
        reclaim_mb=args.reclaim_mb,
        reclaim_every_s=args.reclaim_every_s,
        budget_s=args.budget,
        expect_swap_max=args.expect_swap_max,
    )


def measure(options: Options, cgroup: Path) -> Waits:
    """Run the Tk loop for ``options.seconds`` with reclaim in the background."""
    blocks = make_working_set(options.working_set_mb)
    root = tk.Tk()
    root.withdraw()
    waits = Waits(expected_s=options.tick_ms / 1000)
    stop = threading.Event()
    reclaimer = threading.Thread(
        target=reclaim_forever,
        args=(cgroup, options.reclaim_mb, options.reclaim_every_s, stop),
        daemon=True,
    )

    def tick() -> None:
        touch(blocks)
        waits.tick()
        root.after(options.tick_ms, tick)

    root.after(options.tick_ms, tick)
    root.after(int(options.seconds * 1000), root.quit)
    reclaimer.start()
    waits.last = time.monotonic()
    root.mainloop()
    stop.set()
    reclaimer.join()
    root.destroy()
    return waits


def say(line: str) -> None:
    """One verdict line on stdout: the output a caller parses."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    """Print the verdict lines; exit 0 green, 1 over budget, 2 wrong cgroup."""
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    options = parse(argv)
    cgroup = own_cgroup()
    swap_max = read_knob(cgroup, "memory.swap.max")
    say(f"cgroup={cgroup} memory.swap.max={swap_max}")
    if options.expect_swap_max is not None and swap_max != options.expect_swap_max:
        say(f"FAIL: memory.swap.max={swap_max}, expected {options.expect_swap_max}")
        return 2
    started = time.monotonic()
    waits = measure(options, cgroup)
    say(f"ticks={waits.ticks} swap_peak={read_knob(cgroup, 'memory.swap.peak')}")
    say(f"max_wait_s={waits.worst_s:.3f} run_s={time.monotonic() - started:.1f}")
    return 1 if waits.worst_s >= options.budget_s else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
