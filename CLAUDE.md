# CLAUDE.md — leetcode-guard

Read this before changing anything. Most of it is a record of something that
already went wrong once.

## The deployment path is system python

`/usr/bin/python3` plus user site-packages. **Not** a venv, no
`WorkingDirectory`, no `PYTHONPATH`. `install.sh` verifies imports with that
exact interpreter, because testing in a dev venv and shipping to
`/usr/bin/python3` is how diet_guard was silently dead for three days.

The venv under `~/.venvs/leetcode-guard-mcp` exists only for the MCP server, so
the MCP SDK never has to be importable on the systemd path.

## Never break these

**"Cannot check" is not "not solved".** LeetCode answers an expired session and
several other failures with **HTTP 200 and a null payload**, not an error.
`_submissions.fetch_recent_ac` returns a three-valued `ProbeStatus` for exactly
this reason. Collapsing it into a boolean gives a lock whose unlock condition
can never be satisfied and which does not know it.

**Credits must verify; charges must not have to.** The table in `_balance.py`
is deliberately asymmetric and inverts gatelock's own rule for credits. An
unverified credit is a bypass (append JSON, get a day). An unverified charge
being discarded would be a refund. Read the module docstring before touching
it.

**The MCP server is read-only.** No `grant_credit`, no `mark_solved`, no
`unlock`, ever. A credit exists only because LeetCode confirmed an accepted
submission. `test_mcp.py` asserts the absence.

**Seeding is not optional.** Without it the first run harvests ~20 recent
submissions as credits — three weeks of free unlocks — and the gate never once
gates.

**Never exit because another lock is running.** `_queue.wait_for_turn` waits
with no window. Standing down permanently would make "start the workout lock" a
way to skip the grind. The deadline arms anyway rather than leaving the machine
unlocked.

## Traps that have already cost time

**`questionList` caps a page at 100 rows** regardless of the `limit` you send —
no error, no indication. `fetch_pool` advances `skip` by rows *actually
returned*. An earlier version advanced by the requested size and collected 657
of 4003 problems while reporting success.

**Ruff runs with `--unsafe-fixes` and `T201` is auto-fixable.** Without the
per-file ignore, the fixer deleted every `print` in `cmd_probe` and replaced the
loops with `pass`. It still exited 0. Assert on stdout, not on exit codes.

**With `overrideredirect=True` the root is a backdrop behind the surfaces.** A
widget placed on the root is invisible and unclickable. The demo close button
goes on the surface. Only a screenshot caught this — screenshot the demo.

**`EscapeTracker.validate` rejects a blank `onset`.** A form without that field
can never be submitted; the hatch was present, clickable and permanently
refused.

**`# noqa` and `# type: ignore` are banned by a pygrep hook** — including
inside docstrings. Mentioning the literal string trips it.

**Any module that does `import tkinter as tk` must be added to `_TK_MODULES` in
`conftest.py` in the same commit.** Miss one and the suite does not fail — it
opens a real fullscreen window, or hangs holding a grab.

**`install.sh` will clobber the editable gatelock if you let it.** `pip install
-e .` resolves the pinned `gatelock @ git+...` and installs it *non*-editably
over the top of `~/utils/gatelock`, breaking live editing across all four
lockers — invisibly. `preserve_editable_gatelock` puts it back; do not remove
it.

**The status view is the fourth thing ruff's `--unsafe-fixes` has silently
gutted.** `status_view.py` and `_cli.py` both need the `T201` per-file ignore
or the fixer deletes the prints that *are* their interface.

## Verifying

Tests and lint are necessary but not sufficient. The demo lock must be run and
**screenshotted**:

```bash
Xvfb :81 -screen 0 1600x1200x24 &
DISPLAY=:81 python3 -m leetcode_guard
DISPLAY=:81 import -window root /tmp/lock.png
```

Never `pkill -f leetcode_guard` — the pattern matches the shell running it.
Kill by recorded PID.

If a window must appear on the real display, put it on a **non-primary output**
(`HDMI-0`), never DP-0, and never by moving the mouse.

## Conventions

400-line file cap, 100% branch coverage, `ruff select = ["ALL"]`, `mypy
strict`, `pylint enable = "all"`. Every `except` must re-raise or log at
warning or above. Commit to `main`; never create a feature branch — these repos
deploy from the working tree.
