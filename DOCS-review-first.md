# Review first: due tutor cards hide the SOLVE rows (2026-11-22)

kuhy's rule: while at least one tutor card of the current unit's modules is due, the lock offers
the review before any problem. A VIEW rule: `decide`, charges, credits, debt, the harvester and
the unlock condition never read it, and a solve that lands while the review row shows is credited
and clears the lock as ever (`test_review_first_lock.py`). Clearing those cards earns a credit
since 2026-11-27, through a separate decider over the same signed file (`DOCS-review-clear.md`);
the row choice described here still decides nothing.

## Input
The tutor's signed `review_due.json` (contract `DOCS-contract-review-due.md` in the tutor repo),
read by `_review_due.py` through `_tutor_signed.signed_rows(strict=True, quiet=True)`:
- a missing or unreadable file, bad JSON, no `entries` array, an unreadable key, any entry that is
  not a dict, fails its HMAC or makes the check raise (a planted non-ASCII `hmac` does): cannot
  check for the whole file (no row is skipped). The raise is caught in `_tutor_signed._verified`,
  so every `signed_rows` caller (module state, tutor ledger) sees a planted row as unverified;
- verified rows of another kind or with a malformed `detail` are skipped (a non-finite `at`
  counts as malformed: NaN or infinity could never be superseded);
- per (subject, module) the greatest `at` wins (the later row on a tie); no row: cannot check;
- due at T (ms) = count of `due_ms <= T`. Result is `DueStatus` DUE / CLEAR / UNKNOWN.
A unit with several modules (`js-pandas`, `sql`): the first module with a card due is the target;
any module without a row, and none due, is cannot check.

## Where and what
Only SOLVE of a known unit (`PhaseView.review_targets`, set by `_unit_view`). Every other phase and
the no-curriculum case are unchanged. Due: `build_phase_screen(view, review)` gives the screen a
`ReviewRow`; `build_viewmodel` replaces the problem lines by one `ProblemLine` (label `↻ <count>`,
`url` = the tutor route, no slug); the rework `?` is blank; the unit bar and the `dropped` solve
acknowledgement stay. `StudyMixin.open_problem` sends a `/review/` URL down the learn path
(`open_learn`: study mode, grab released, `tutor --route`), never the browser.

## Repaint and failure
`PhaseReader.refresh` (`_lock_phase.py`) asks on every poll with T = the lock's clock, so the row
swaps both ways without a restart; leaving review makes the poll verify the returning rows like a
unit change. Two things bring a poll: the 30 s interval (`POLL_INTERVAL_MS_PRODUCTION`) and the
file watch below. A card passing its `due_ms` on the clock alone still waits for the interval.

## File watch: the tutor's rewrite shows within about 1 s
`DueFileWatch` (`_review_file_watch.py`) is one extra step in the poller's existing 20 ms `_watch`
loop (`PollerSettings.on_watch`, wired in `_lock.py` to `PhaseReader.file_watch`): no timer, thread
or process. At most once per second (monotonic clock) it does one `os.stat` of
`_tutor_signed.TUTOR_DIR / review_due.json` (resolved at call time) and compares
`(st_ino, st_mtime_ns, st_size)` with the last one seen. A change, including the file appearing or
disappearing, makes the poller call its `check_now()`. That is the poll's own path: the same read,
verify and repaint, never a second reader. `check_now` sets the poke event, so a request while a
probe is in flight fires once after it lands and never stacks a second probe
(`test_poller_watch.py`).
- Latency: about 1 s from the tutor's rename to the early poll starting, plus that poll's own
  duration (one `recentAcSubmissionList` round trip, then the repaint).
- Idle cost: one `stat` per second, 60 a minute, on SOLVE with a mapped module only. In the demo,
  in every other phase and after the review fell open there is no `stat` at all.
- The first observation (and the first after the watch was off) only records the signature: the
  poll that enabled it has just read the file.
- Absent or a failing `stat` (any `OSError`) is the signature "absent", never an exception. A
  missing file is silent; another failure (permissions) is one warning per lock run, not per second.
  Any other exception is caught in `DueFileWatch.__call__`: one logged line with the traceback per
  lock run, and the watch loop keeps going.
- Study mode: `_watch` runs there too. Study mode withdraws the windows and releases the grab but
  leaves the Tk root and its `after` loop running (the poller "still runs", `_lock_study.py`), and
  that loop is the one that carries `_watch`. Nothing in the study or grab path changed.

Every failure path is fail-open: SOLVE rows, and the lock still arms and polls.
- Cannot check: one warning per lock run carrying the reason (`ReviewWatch`; the reader itself
  logs nothing, later ticks are quiet).
- Any exception in the review read (`PhaseReader._read_review`, like the phase read): cannot
  check, one warning with the traceback, never into arming or the poll.
- Due but no tutor launcher: SOLVE rows and one warning (the 2026-08-05 rule: Open must open).
- Due, launcher found, but it cannot be STARTED (the spawn raises: bad shebang, not executable):
  the first failed press makes this lock run fall open (`PhaseReader.fall_open`, one warning). The
  SOLVE rows come back at once through the poll's repaint (`RevealMixin.repaint`) and stay for the
  run, also while the file still says due. A launch that works keeps the rule.
- Launcher starts, then exits non-zero (tutor down: its `run.sh` exits 1 after waiting 20 s or more
  for the server, and opens its window last, so no window): detected since 2026-11-22.
  `_launch_watch.watch_exit` polls the detached process every 250 ms on the Tk loop (no thread, no
  deadline). If the session that press opened is still running, study mode ends like Back to lock
  (strip down, grab back, restart marker gone), with the failure on the status line and the
  no-entry glyph on the learn button; otherwise only the status line. A review also falls open
  (SOLVE rows). An exit 0 ends the watch, however slow.
- Still NOT detected: a launcher that exits 0 on a route the app does not know. Study mode stays
  on with the grab released; the way out is study mode itself (the machine is unlocked).
- Demo mode never reads the tutor's file: the demo fixture says nothing is due.

## The check
`xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_review_first` (manual-stage
hook `verify_review_first`, so `check_gate_stamp.sh full` runs it). Each scenario is the real
`_cli.main` lock on its own Xvfb with a scratch HOME and key (`leetcode_guard/tests/_review_e2e*.py`):
row shown with the grab held; the swap both ways after the tutor's rename; a planted file; a
launcher that cannot be started; a working launcher (route, study mode, grab still released after
a recovery tick); the demo (0 reads); a review and a learn launcher that exit 1 (study ends,
grab back, marker gone; SOLVE rows / the no-entry glyph); a launcher that exits 0 after 3 s (kept). A fake `systemd-run` first on `PATH` runs the command in
place, so no unit ever reaches the live user manager. The swap bound is 1.5 s, not 1 s: a rename
just after the watch's `stat` waits the whole second, then the poll (measured 0.18 to 1.06 s).
