# Scrolling suggestion list and the browser nudge

Both shipped 2026-10-03. Each has one rule that keeps it from becoming a bypass.

## The list scrolls through the whole unsolved pool

`_view_scroll.py`: a viewport exactly `PROBLEM_DISPLAY_LIMIT` (8) rows tall over
every unsolved, non-premium problem. Rows are built `ROW_BATCH` at a time as the
user nears the end (building ~3300 rows per monitor up front costs seconds).
`SUGGESTION_COUNT` (14) still sets how deep the pool is verified before the
window opens; rows past that are checked live as they are revealed
(`_lock_reveal.py`), one batch in flight, stopping for good on a blind answer.

**An old solve found by scrolling drops out silently.** It is removed from the
pool, never added to the solved set the status line reads -- "Accepted: X" means
a solve landed *during this lock*.

The canvas widens to its widest row and never narrows; left alone it sits at
Tk's default width and clips each long title together with its Open button.
Only the screenshot caught that.

## The browser nudge is a doorbell, never evidence

The lock polls every 30 s. `extension/` (Helium, loaded via
`--load-extension` in `~/.config/helium-browser-flags.conf` by
`scripts/install_nudge_extension.sh`) watches LeetCode's own
`/submissions/detail/<numeric id>/check/` responses and, on an Accepted verdict,
POSTs to `_nudge_server` on 127.0.0.1:8772. Runs (`runcode_` ids) never ring.

The lock then probes the recent-AC feed at once and at +0.25/0.5/1/2/4 s, in
case the feed lags the verdict (tightened 2026-10-10: at +1 s, a feed lagging by
50 ms pushed the credit past the one-second target). While the burst runs the
study strip's accent line reads "Accepted seen -- verifying"; the count does not
move until the feed confirms, and the note clears when the burst runs out. Rules, all enforced in code because the port is
unauthenticated:

- The request body is never read. A ring can only cause a probe; credits still
  come from the feed alone.
- Rings within 5 s of a burst are dropped; pokes during an in-flight check
  collapse into one.
- A failed *poked* probe is not blind time (`_lock_poll`). Blind seconds are
  counted in poll intervals, so counting them would let forged rings buy the
  escape hatch in seconds.
- The port is open only while a lock is up (`GuardDeps.nudge_port`, set by the
  CLI; tests leave it `None`).

## Why the nudge was dead until 2026-10-10

Two independent faults, each enough on its own; neither raised an error.

- **Port 8772 was taken** by plc-lab's tutor (moved to 8778). The lock only
  logged a warning, so it fell back to the 30 s poll in silence. A failed bind
  now titles the strip "instant check OFF".
- **The extension never loaded.** Chromium keeps only the *last*
  `--load-extension`. Helium's launcher puts `helium-browser-flags.conf` first
  and the caller's arguments after, and `/usr/local/bin/helium-browser` is
  `browser-preexec-wrapper`, whose exec line carried LeechBlock's flag twice.
  The conf entry is broken a second way too: the launcher's tilde-escaping
  turns `/home/kuhy/...` into a literal `~/...`. So
  `scripts/install_nudge_extension.sh` merges every flag on the wrapper's exec
  line into one that lists `extension/` (sudo), and digital-wellbeing's
  LeechBlock installer, rerun on every `pacman -S`, now joins that flag rather
  than appending a second one.

Live check without minting a credit: click **Run** on any problem; the page's
DevTools console logs `[leetcode-guard] verdict poll`. Run ids never ring.

Measured: the extension rings 2-7 ms after the verdict
(`scripts/verify_nudge_extension.py`, headless Helium against a mock); the lock
repaints ~4 ms after LeetCode answers (`scripts/verify_nudge_latency.py`), so
end to end is one LeetCode round trip, ~0.3 s, plus any feed lag.
`verify_nudge_latency.py --port 8799 --lag 0.5`: note ~5 ms, credit ~630 ms
(1.3 s under the old ladder).
