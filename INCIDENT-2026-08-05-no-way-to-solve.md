# Incident 2026-08-05 — lock offered no way to solve the problem it demanded

**Severity: high.** The guard locked the entire PC and left no route to the one
action that unlocks it. User was fully stuck and had to have the services killed
from an already-running terminal session. Without that session, the only exits
would have been a TTY switch or a hard reboot.

Written by a Claude session that killed the lock, not the session that will fix
it. Everything below is observed, not inferred from the code alone.

## What happened

| Time (CEST) | Event |
|---|---|
| 09:00:00 | `leetcode-guard.service` started by `leetcode-guard.timer` |
| 09:00:29 | `_harvest` seeded a NEW ledger with 12 pre-existing submissions, all marked already-seen |
| 09:00–09:06 | Full-screen lock displayed a list of problems, with no way to open any of them |
| 09:06:24 | Service stopped manually; PC released |

The 09:00:29 line is the trigger:

```
WARNING leetcode_guard._harvest: seeded a new ledger with 12 pre-existing
submissions -- they are recorded as already-seen and grant no credit, so the
first unlock requires a fresh solve
```

So the gate demanded a **fresh** solve, at the same moment the lock removed
access to the browser needed to produce one.

## Root cause: two correct-in-isolation decisions that deadlock together

**1. The lock is total by design.** `_lock.py:11` — *"and no window is itself the
bypass"* — and `_pool_resolve.py:10` repeats it. There is no allowlist, no
exempt application, and confirmed by grep:

```
$ grep -rlnE "webbrowser|xdg-open" leetcode_guard/*.py
(no matches)
```

The package **cannot open a browser at all**. The lock names problems it will
accept but offers no way to reach `leetcode.com/problems/<slug>`.

**2. The escape hatch is time-gated, so it is absent exactly when needed.**
`_lock.py:280 _should_offer_escape()` returns True only if
`_incident_form_due()` (offline path) or `is_offerable(...)` passes, and the
latter is a function of `elapsed_seconds` and `unverifiable_seconds`. Network
was fine, so the offline path never applied, and at ~6 minutes elapsed the
budgeted hatch had not yet appeared.

Net effect: a gate whose only exit is an action it has itself made impossible.
The code comment at `_should_offer_escape` — *"refusing it is what made the lock
a trap"* — shows this failure mode was already known for the offline path. The
online path has the same hole.

## Suggested fixes (for the session that picks this up)

Ranked. (1) alone closes the trap.

1. **Ship a browser affordance inside the lock.** A button per listed problem
   that launches `xdg-open https://leetcode.com/problems/<slug>`, raised above
   the lock surface. The gate's purpose is to force the solve, not to prevent
   it. Without this the lock is unsatisfiable whenever a fresh solve is required.
2. **Never require a fresh solve on the very first armed run.** When `_harvest`
   seeds a new ledger, either credit the most recent pre-existing submission or
   defer arming until the next window. Right now the ledger-seeding path
   guarantees an immediately-unsatisfiable gate — the exact case that fired here.
3. **Make the escape hatch reachable from t=0 at reduced value.** A hatch that
   only appears after N minutes is not a safety valve during the first N minutes.
4. **Add a documented break-glass.** A file sentinel or `systemctl --user stop`
   path stated *on the lock screen itself*, so the user is not dependent on a
   pre-existing terminal session.
5. **Regression test:** assert that a lock built from a freshly-seeded ledger
   exposes at least one actionable control (problem-opening button OR escape
   hatch) at t=0. That test fails against today's code.

## What was changed on this machine (needs deliberate re-enable)

Stopped and **disabled** — these will NOT come back on reboot:

```
systemctl --user stop    leetcode-guard.service workout-locker.service
systemctl --user disable leetcode-guard.timer early-bird-workout-check.timer \
                         claude-workout-autoscan.timer
```

`claude-workout-autoscan.timer` was disabled too because it was armed to fire
at 09:15 and could have re-triggered a lock.

Nothing in this repo's source was modified. No ledger, key, or state file was
touched — the ledger seeded at 09:00:29 is intact, so the "12 already-seen
submissions" state is still there and will behave the same way on next arm.

**Re-enable only after fix (1) or (2) lands**, or the same lockout recurs:

```
systemctl --user enable --now leetcode-guard.timer
systemctl --user enable --now early-bird-workout-check.timer
systemctl --user enable --now claude-workout-autoscan.timer
```

## Fixed 2026-08-09

All five suggestions landed, plus two defects found while implementing them.

**1. Study mode (the browser affordance).** Each listed problem now has an
`Open` button. Pressing it does **not** just launch a browser — that alone would
have shipped the same trap with a button on it, because the production lock
holds an X *global* grab (`XGrabPointer` + `XGrabKeyboard`) and no other client
receives a keystroke while it is held. `_study.py` stands the lock down: it stops
gatelock's `RecoveryLoop` (first, or the grab is re-taken within a tick),
releases the grab, restores VT switching and withdraws the surfaces. A small
always-on-top strip stays up with elapsed time, solves still owed, and
`Back to lock`.

**Study mode genuinely unlocks the machine, and that was chosen knowingly.**
There is no timeout: press Open and walk away and it stays open until a solve
lands or `Back to lock` is pressed. A lock that cannot be satisfied is worse
than one that can be walked away from. Both transitions log at warning with
elapsed time, so the journal always says how long the machine was unguarded.

**2. Seeding no longer arms an unsatisfiable gate.** The run that *creates* the
ledger now returns without arming; the next one gates normally. Seeding itself
writes no charge and no credit.

The first attempt at this settled the day in the ledger instead, and code review
caught that it wrote `charge:<today>` — the exact key `decide` unlocks on — so
`rm ledger.json` produced an unlocked day, repeatably (clean HEAD: locked 4/4;
that version: unlocked 4/4). A gate deferral expressible as ledger state is a
bypass; deferring the run is not.

*This does not repair the existing ledger*: the one seeded at 09:00:29 already
has its bootstrap entry, so `needs_seeding` is False and it is never rewritten.
Fix (1) is what makes that ledger's next arm satisfiable.

**3. The hatch is offered from t=0.** `ESCAPE_OFFER_AFTER_SECONDS` 600 → 0. The
budget (1 per 7 days, 120 characters of justification) is what makes the hatch
expensive; the clock only made it absent when it was needed most.

**4. Break-glass on the surface,** permanently, and worded honestly: production
says VT switching *has been disabled by this lock and will not work*, then gives
`systemctl --user stop leetcode-guard.service`. Telling a trapped user to press
Ctrl+Alt+F2 when this process turned it off would have made the incident worse.

**5. The regression test** is
`test_scenarios.py::test_a_freshly_seeded_lock_offers_a_way_out_at_t0`. It was
written first and observed **red** against the code that shipped that morning,
failing on both the missing `Open` button and the hidden hatch.

### Two defects found while fixing, not in the original report

**A raising probe was worse than what happened here.** `_lock.py:300` returned
early when `_check` *raised* (which `SolvePoller` reports as `None`), skipping
both `state.record()` and the repaint. `consecutive_unverifiable` therefore
never advanced, so the blind-time route to the hatch could never fire and the
status line froze at its startup text — a lock with no exit at all, at any
elapsed time, that looked identical to a healthy one. A crash is now counted as
the unverifiable probe it is.

**The fit harness had never measured the real screen.** `verify_screen_fits`
built 5 problems where production showed 10, and passed no `on_escape`, so the
escape button was never measured once. Measured on Xvfb: the screen the user
actually saw was **723px of a 768px budget** — 45px from clipping, and a
`place`-centred surface shears at *both* edges, so overflow costs the headline
and the hatch together. The surface now shows 8 problems with the redundant URL
line dropped, and measures **627px** with the break-glass block included.

### Found by code review, after the first version was written

The fix got a five-lens review before it landed. Five defects it caught, all
reproduced before being fixed:

- **A free-unlock bypass in the first seeding fix** (above). The most serious:
  it was a new hole in the exact mechanism the credit/charge asymmetry exists
  to protect.
- **Every exit after a study session left VT switching disabled.** Suspend
  cleared gatelock's `_vt_disabled` flag; nothing set it back, and
  `LockWindow.close()` skips its restore when that flag is falsy. So one
  Open → Back-to-lock cycle meant the machine exited with Ctrl+Alt+F1..F6 dead
  — on a screen whose own break-glass text had told the user those keys would
  not work. The marker is bidirectional now, and stores
  `disable_vt_switching()`'s return the way gatelock does.
- **A NUL byte in a problem slug stranded the machine unlocked.**
  `_browser.launch` documented "never raises" but caught only `OSError`;
  `Popen` rejects an embedded NUL with `ValueError`, which escaped *after* the
  grab was released, so the rollback never ran. The promise is true now, and
  `_spawn` guards it anyway — a lock should not bet the screen on another
  module keeping its word.
- **Malformed titles could clip the screen or kill the process.** Titles are
  rendered in a non-wrapping label, so an embedded newline adds a rendered row
  (eight of them overflow 768px, clipping the headline and hatch together) and
  a multi-thousand-character title asks X for a pixmap it cannot allocate,
  which exits the process in C while it holds the global grab. Titles are now
  flattened and bounded at the parse boundary.
- **A dead constant and a false timing claim.** `REGRAB_RETRY_MS` was unused
  after the retry loop was simplified, and its docstring still claimed "two
  seconds of attempts" — measured: 20ms, eight back-to-back calls. Restoring
  the sleep would have been wrong (that path runs from a button callback and
  would freeze the surface), so the attempts stay immediate and the docstring
  now says so.

### Verified

- 675 tests, **100% branch coverage**; `pre-commit run --all-files` clean.
- `scripts/verify_study_grab.py` — a new pre-push harness that proves the grab
  really drops, on a real X server. No unit test can: over a mocked root a
  released grab and a held one are indistinguishable, which is exactly what let
  this trap look healthy. It asserts the grab is held, released after `Open`,
  **still released after a recovery tick** (a grab that comes back a second
  later is the original bug wearing the fix as a disguise), and re-taken on
  `Back to lock`. 6/6 pass.
- Screenshotted under production config: the lock with 8 Open buttons, the hatch
  and the break-glass text; study mode with the surfaces down and the strip up;
  and the re-locked screen.

### Still to do

**The timers are still disabled.** Re-enable them only after a watched run on
the real display with a real browser — `holds_grab() is False` is strong
evidence, but a human typing into LeetCode's editor is the proof, and that is
the one thing no harness covers. Commands are in the section above.

## Reproduce

1. Remove/rename the ledger so `_harvest` seeds a fresh one with prior
   submissions present.
2. Start `leetcode-guard.service --production` inside the armed window.
3. Observe: problems listed, no control opens any of them, and
   `_should_offer_escape()` is False for the first several minutes.
