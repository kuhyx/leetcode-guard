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
gates. Marking the whole feed already-seen does leave a gate satisfiable only by
a solve that has not happened yet — the state that armed on 2026-08-05 — so the
run that *creates* the ledger returns without arming (`cmd_lock`).

**A gate deferral must never be ledger state.** Settling the day was tried and
reverted: it wrote `charge:<today>`, the exact key `decide` unlocks on, so
`rm ledger.json` bought an unlocked day, repeatably. Deferring the *run* leaves
nothing behind — delete the ledger and you skip one run, you do not earn a day.
`test_the_run_that_creates_the_ledger_does_not_arm` pins it.

**The lock must always offer a way to do the thing it demands.** This is the
2026-08-05 rule and it outranks the strength of the lock. Three things
implement it and none may be quietly removed: an `Open` button per problem, the
escape hatch offered from t=0, and the break-glass command printed on the
surface. `test_scenarios.py::test_a_freshly_seeded_lock_offers_a_way_out_at_t0`
is the executable form; it failed against the code that shipped that morning.

**Study mode genuinely unlocks the machine, on purpose.** `_study.py` releases
the X global grab so a browser can receive keystrokes — hiding surfaces is not
enough, the grab is on the root and blocks every other client. There is no
timeout: press Open and walk away and the machine stays open until a solve lands
or "Back to lock" is pressed. That trade was made deliberately (a lock that
cannot be satisfied is worse than one that can be walked away from) and it is
logged at warning on both transitions. `verify_study_grab.py` is what proves the
grab actually drops; no unit test can, because a mocked root reports success
either way.

**Never exit because another lock is running.** `_queue.wait_for_turn` waits
with no window. Standing down permanently would make "start the workout lock" a
way to skip the grind. The deadline arms anyway rather than leaving the machine
unlocked.

## Traps that have already cost time

**`questionList` caps a page at 100 rows** regardless of the `limit` you send —
no error, no indication. `fetch_pool` advances `skip` by rows *actually
returned*. An earlier version advanced by the requested size and collected 657
of 4003 problems while reporting success.

**`status` has three values and `null` means two different things.** Measured
against a live session on 2026-08-14: `"ac"` = solved, `"notac"` = attempted and
failed, **`null` = never attempted**. A dead session also returns `null`, for
everything. So a null is *not* a reliable signal of being signed out — a
signed-in user browsing ten problems they have never opened produces an
all-null sweep too. Inferring "expired session" from it made the lock announce
"could not check solved-state" while holding a freshly verified cookie, **and**
trip the early exit that abandons the rest of the sweep, so a solved problem
further down would have survived. `_live_solved` therefore splits `checked`
(the request returned a readable `question` envelope) from `recognised` (the
status was non-null): a null inside a valid envelope is an *answer*, a missing
envelope is silence. Only silence means "could not check". Detecting a dead
cookie is `--login`'s job, and it probes a slug chosen to be non-null.

The pool query is public, so expired cookies return HTTP 200 with a complete,
healthy-looking problem list of nulls — not an error, not an empty payload.
Filtering on `status == "ac"` needs no auth flag guarding it: an
unauthenticated null simply does not match. An `exclude_solved` flag wired to
"cookies loaded" once did guard it, and in the signed-out branch it *discarded*
the genuine `"ac"` rows a partly-authenticated fetch had returned.

**Solved-state is checked live, but only for what is displayed.** Re-paging the
whole authenticated pool is 41 requests before the window exists, and LeetCode
answers a rate limit with the same null payload as an expired session — so an
exhaustive check manufactures the failure it is looking for. Rank first, verify
the top N, backfill from the next candidates. `recentAcSubmissionList` is hard
capped at **20 rows** regardless of `limit` (verified against an account with
thousands of solves), so it can never enumerate a full solved set; do not raise
`RECENT_AC_LIMIT` to try — it feeds the harvest path, where every unseen
submission id mints a credit.

**The demo deletes its ledger every run**, so anything derived from ledger state
is empty there. That put two already-solved problems back at the top of the demo
surface after the filter was fixed everywhere else, and **only the screenshot
caught it** — the unit tests all passed. Screenshot the demo after any change to
the suggestion list.

**Ruff runs with `--unsafe-fixes` and `T201` is auto-fixable.** Without the
per-file ignore, the fixer deleted every `print` in `cmd_probe` and replaced the
loops with `pass`. It still exited 0. Assert on stdout, not on exit codes.

**With `overrideredirect=True` the root is a backdrop behind the surfaces.** A
widget placed on the root is invisible and unclickable. The demo close button
goes on the surface. Only a screenshot caught this — screenshot the demo.

**`EscapeTracker.validate` rejects a blank `onset`.** A form without that field
can never be submitted; the hatch was present, clickable and permanently
refused.

**A `from scripts.x import y` breaks mypy, and only in CI.** `scripts/` is not
a package and must not become one, so importing one script from another makes
mypy see that file under two module names ("Source file found twice") and exit
2. Locally a warm `.mypy_cache` hides it, so this passes every pre-commit run
on the machine that wrote it and fails the first clean checkout. Scripts share
code by duplicating the few lines they need, or by importing from
`leetcode_guard/`. Reproduce a CI mypy failure with `rm -rf .mypy_cache` first.

**`# noqa` and `# type: ignore` are banned by a pygrep hook** — including
inside docstrings. Mentioning the literal string trips it.

**Any module that does `import tkinter as tk` must be added to `_TK_MODULES` in
`conftest.py` in the same commit.** Miss one and the suite does not fail — it
opens a real fullscreen window, or hangs holding a grab. The list runs both
ways: a module that *stops* importing tkinter must come **out**, or patching an
attribute it no longer has raises at fixture time and fails the entire suite at
once. `_lock.py` left the list when its last widget call moved to
`_view.install_demo_close_button`. Verify with
`grep -l '^import tkinter as tk' leetcode_guard/*.py`.

**Shipped code reaches gatelock's privates from exactly one file.** `_recovery`,
`_detector`, `_surfaces` and `_vt_disabled` have no public equivalent, so every
read inside `leetcode_guard/` goes through `_gatelock_internals.py`.
`test_study.py::test_every_private_gatelock_read_goes_through_the_adapter`
parses `_study.py`, `_study_resume.py` and `_lock_study.py` as ASTs and fails if
one reaches past it.

The `scripts/` harnesses are exempt on purpose and are **not** covered by that
test: `verify_study_grab.py` checks that the adapter's own assumptions hold on a
real X server, so routing it through the adapter would be marking its own
homework. `screenshot_states.py` drives internals for the same reason the test
suite does. Both carry their own `SLF001` entry — so grep `pyproject.toml` for
the real list rather than trusting a count here.

**`install.sh` will clobber the editable gatelock if you let it.** `pip install
-e .` resolves the pinned `gatelock @ git+...` and installs it *non*-editably
over the top of `~/utils/gatelock`, breaking live editing across all four
lockers — invisibly. `preserve_editable_gatelock` puts it back; do not remove
it.

**The status view is the fourth thing ruff's `--unsafe-fixes` has silently
gutted.** `status_view.py` and `_cli.py` both need the `T201` per-file ignore
or the fixer deletes the prints that *are* their interface. `_login.py` is the
fifth, and the worst: it lost every print on the first pre-commit run after
being written, leaving a credential command that stores or refuses a cookie
without saying which. Its tests assert on behaviour, not stdout, so they stayed
green — add the `T201` entry in the same commit as any new print-driven module.

## Verifying

Tests and lint are necessary but not sufficient. The demo lock must be run and
**screenshotted**:

```bash
Xvfb :81 -screen 0 1600x1200x24 &
DISPLAY=:81 python3 -m leetcode_guard &
DISPLAY=:81 import -window root /tmp/lock.png
```

Never `pkill -f leetcode_guard` — the pattern matches the shell running it.
Kill by recorded PID.

**One `import -window root` is not a screenshot.** Fired before the surfaces
paint it returns the `overrideredirect` backdrop: a uniformly charcoal image
that looks exactly like a lock screen that rendered and happens to be empty,
which is indistinguishable from a real failure. Two of the three captures on
2026-08-09 were blank this way, and `-window <id>` does not help — the surface
reports its full 1600x1200 geometry before it has drawn anything. Sample for the
whole window and keep the largest file; the sizes are not close, so the check is
unambiguous:

```bash
DISPLAY=:81 python3 -m leetcode_guard & SHOT=$!
BEST=0
for _ in $(seq 1 30); do
  DISPLAY=:81 import -window root /tmp/try.png 2>/dev/null
  SZ=$(stat -c%s /tmp/try.png 2>/dev/null || echo 0)
  if [ "$SZ" -gt "$BEST" ]; then BEST=$SZ; cp /tmp/try.png /tmp/lock.png; fi
  kill -0 "$SHOT" 2>/dev/null || break
done
```

`if`, not `[ ... ] && { ...; }` — as the last command in the body the `&&` form
returns non-zero on every iteration that is not a new maximum, which under
`set -euo pipefail` kills the enclosing script. The `kill -0` break matters too:
without it the loop keeps shooting blanks for the full 30 iterations after the
render has already exited.

A blank frame is ~400 bytes; a painted one is ~90 KB. Anything in the hundreds
of bytes means you photographed the backdrop, whatever the window id said.

**Fixtures asserting LeetCode's behaviour need a live check.** A mock can only
repeat what its author believed, so a wrong belief produces a green suite and a
broken product — `status_result`'s docstring claimed a null status meant
"signed out", every solved-state test asserted against it, and the code shipped
the same error. `scripts/verify_solved_semantics.py` asks the real endpoint
whether `ac`/`notac`/`null` still mean what the fixtures say, and it fails
against the pre-fix code. It runs as a `pre-push` hook and **skips loudly at
exit 0 when the cookie is dead** — that is a precondition failure, not a
semantic one, and the cookie expires every two weeks, so failing there would
block unrelated pushes. Any fixture encoding external-system semantics should
cite the date it was measured, the way `_queries.py` does.

**The grab needs its own check.** A screenshot proves pixels, not input. Over a
mocked Tk root a released grab and a held one are indistinguishable — which is
what let the 2026-08-05 trap look healthy — so the suspend/resume cycle is
verified against a real X server instead:

```bash
xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_study_grab
```

It runs as a `pre-push` hook. The load-bearing assertion is that the grab is
*still* released after a recovery tick: a grab that comes back a second later is
the original bug wearing the fix as a disguise.

If a window must appear on the real display, put it on a **non-primary output**
(`HDMI-0`), never DP-0, and never by moving the mouse. That rule governs
*developer verification windows*. It does not apply to product UI: the study
strip belongs on the primary output, because that is where the user is looking.

## Conventions

400-line file cap, 100% branch coverage, `ruff select = ["ALL"]`, `mypy
strict`, `pylint enable = "all"`. Every `except` must re-raise or log at
warning or above. Commit to `main`; never create a feature branch — these repos
deploy from the working tree.
