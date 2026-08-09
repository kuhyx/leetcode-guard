"""Every path, threshold and tunable in one place.

Grouped by what breaks when you change it, not alphabetically. Anything with a
comment attached earned that comment by being non-obvious or by having a
failure mode; the bare ones are genuinely arbitrary.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Final

# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

APP_NAME: Final = "leetcode_guard"

DEVICE_ID: Final = "pc"
"""Which device wrote a ledger entry. Only entries from this device are
trusted when HMAC verification is unavailable -- see the integrity table in
:mod:`leetcode_guard._balance`."""

RANK_LEETCODE_GUARD: Final = 150
"""Arbiter priority: below screen_locker (200), above diet_guard (100).

A literal rather than a ``gatelock.RANK_*`` constant on purpose. Adding it
upstream would bump gatelock's version and force a re-pin across three live
consumers (screen-locker, diet-guard, wake-alarm) for a number only this repo
uses. ``Arbiter`` takes a bare int, so nothing is lost.

The ladder this slots into is gatelock's own: wake up, then work out, then
grind, then eat.
"""

GATE_START_DATE: Final = date(2026, 8, 4)
"""The first day the gate is allowed to lock. Before this it exits instantly.

systemd's ``OnCalendar`` has no "not before this date" form, so a start date
cannot live in the timer. Putting it in the gate decision instead makes it
visible to ``--status``, ``--check`` and the MCP server, keeps it testable, and
means reloading or re-enabling the timer cannot accidentally bring the gate
forward.

Checked *after* the rolled-back-clock guard, never before: otherwise setting
the system date back to before this day would re-enter the not-started state
and disable the gate permanently.
"""

DEFAULT_USERNAME: Final = "kuchy"
"""Verified to exist against the live API. A wrong username is indistinguishable
from an outage at the HTTP layer but *is* distinguishable at the GraphQL layer
("That user does not exist."), which is why that error is logged at ERROR."""

# --------------------------------------------------------------------------
# Filesystem
# --------------------------------------------------------------------------

CONFIG_DIR: Final = Path.home() / ".config" / APP_NAME
DATA_DIR: Final = Path.home() / ".local" / "share" / APP_NAME

LEDGER_FILE: Final = DATA_DIR / "ledger.json"

# Revision cache for cross-device sync. Beside the ledger it describes and
# cleared with it: skipping an unchanged peer is only sound because that
# peer's records are already merged into the local log, so state that outlived
# its ledger would skip peers whose data had been lost.
SYNC_STATE_FILE: Final = DATA_DIR / "sync_state.json"
DEMO_LEDGER_FILE: Final = DATA_DIR / "ledger_demo.json"
"""Wiped and re-seeded on every demo run. Never the real ledger: a demo must
not be able to mint a credit, and must not be able to spend one either."""

POOL_CACHE_FILE: Final = DATA_DIR / "pool_cache.json"
STATEMENTS_CACHE_FILE: Final = DATA_DIR / "statements_cache.json"

ESCAPE_HISTORY_FILE: Final = DATA_DIR / "escape_history.json"
DEMO_ESCAPE_HISTORY_FILE: Final = DATA_DIR / "escape_history_demo.json"
NETWORK_INCIDENTS_FILE: Final = DATA_DIR / "network_incidents.json"
DEMO_NETWORK_INCIDENTS_FILE: Final = DATA_DIR / "network_incidents_demo.json"

USERNAME_FILE: Final = CONFIG_DIR / "username"
COOKIES_FILE: Final = CONFIG_DIR / "cookies.json"
"""Optional. ``{"LEETCODE_SESSION": "...", "csrftoken": "..."}``.

Its absence, its expiry and its corruption are all non-events: cookies only
ever *improve* the suggestion list by hiding already-solved problems. Solve
detection never reads them, so a dead session can never prevent an unlock."""

SYNC_TOKEN_FILE: Final = CONFIG_DIR / "sync_token"

INSTANCE_LOCK_FILE: Final = DATA_DIR / "instance.lock"
"""Held for the process lifetime so the afternoon retry cannot stack a second
waiter behind the morning run."""

# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

GRAPHQL_URL: Final = "https://leetcode.com/graphql/"
LEETCODE_HOME_URL: Final = "https://leetcode.com/"
PROBLEM_URL_TEMPLATE: Final = "https://leetcode.com/problems/{slug}/"

USER_AGENT: Final = "Mozilla/5.0 (X11; Linux x86_64) leetcode-guard/1.0"
REFERER: Final = "https://leetcode.com/problemset/all/"

NETWORK_TIMEOUT_SECONDS: Final = 15.0

THROTTLE_MIN_INTERVAL_SECONDS: Final = 0.5
"""Community-derived limiters for this endpoint sit at 20 requests / 10 s, and
LeetCode publishes no rate-limit headers -- there is no warning before a block,
so the interval is defensive rather than reactive. 0.5 s is a quarter of that
budget, and the heaviest operation (a full pool refresh) is 9 requests."""

POOL_PAGE_SIZE: Final = 100
"""``questionList`` silently caps a page at 100 rows.

Measured, not assumed: asking for 500 returns exactly 100, with no error and no
indication the limit was clipped. An earlier draft of this file said 500 and
the pager advanced ``skip`` by the *requested* size, so it strode past 400
problems per page and collected 657 of 4003 while reporting success.

The page size is therefore only a hint. :func:`leetcode_guard._pool_fetch.fetch_pool`
advances by the number of rows actually returned, which is correct whatever the
server decides to cap at.
"""

POOL_MAX_PAGES: Final = 60
"""Runaway guard. ~4000 problems at 100 per page is ~41 requests, so 60 leaves
headroom for growth while still catching a pager that fails to advance."""

RECENT_AC_LIMIT: Final = 20
"""LeetCode hard-caps this server-side regardless of what we ask for (verified
2026-07-27 by requesting 100 and receiving 20). Raising it does nothing.

Consequence for the ledger: at most 20 uncredited solves can be harvested
between runs. Anything older has rolled out of the window and is invisible."""

# --------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------

POOL_TTL_SECONDS: Final = 7 * 24 * 60 * 60
"""Seven days, matching the offline-access requirement: the suggestion list
must still render when the gate fires with no network."""

SUGGESTION_COUNT: Final = 10
"""How many problems to resolve, report and cache. The list is advisory -- any
accepted submission on any problem counts, including premium ones."""

STUDY_STRIP_WIDTH_PX: Final = 320
STUDY_STRIP_HEIGHT_PX: Final = 130
STUDY_STRIP_TICK_MS: Final = 1_000
"""The strip shown while the lock is stood down for study.

It re-lifts itself on every tick, because gatelock's recovery loop -- which
would normally keep a lock window on top -- is stopped for the duration. One
second is fast enough that a browser raising over it is corrected before it is
annoying, and slow enough to cost nothing."""

REGRAB_MAX_ATTEMPTS: Final = 8
"""How many immediate attempts at re-taking the global grab when study mode
ends.

Immediate, not spaced: this runs from a button callback, and sleeping between
tries would freeze the surface the user just asked to have back. So these only
catch a grab that is already free -- which is fine, because they were never the
guarantee. gatelock's recovery loop is restarted whether or not they worked and
re-takes the grab within a tick of it becoming available."""

PROBLEM_DISPLAY_LIMIT: Final = 8
"""How many of those the *lock surface* shows.

Lower than :data:`SUGGESTION_COUNT` because the surface has a hard pixel budget
and nothing else does. Ten problems, the escape button and the break-glass
block measure 785px against a 768px panel, and a ``place``-centred frame clips
at both edges -- losing the headline and the hatch together. Eight fits in
627px with room for the note list to grow. The CLI, the MCP server and the
status view are not so constrained and still offer all ten."""

STATEMENT_CACHE_COUNT: Final = 50
"""How many problem statements to mirror for offline reading. This is the one
piece that meaningfully raises the API budget (one request each, on top of the
9 pool pages), so it is the first thing to cut if throttling appears."""

# --------------------------------------------------------------------------
# Polling
# --------------------------------------------------------------------------

POLL_INTERVAL_MS_PRODUCTION: Final = 30_000
POLL_INTERVAL_MS_DEMO: Final = 10_000

POLL_DRAIN_MS: Final = 200
"""How often the Tk thread checks whether the in-flight network future has
finished. Network work never runs on the Tk thread: a synchronous request
inside an ``after`` callback would freeze a globally-grabbed lock for the whole
timeout, which is indistinguishable from a hang."""

# --------------------------------------------------------------------------
# Failure policy
# --------------------------------------------------------------------------

UNVERIFIABLE_HATCH_SECONDS: Final = 180
"""After this long with every probe unverifiable, reveal the escape hatch
immediately instead of waiting out the usual offer delay. The user must always
have a visible way forward while the lock cannot see LeetCode."""

QUEUE_POLL_SECONDS: Final = 2.0
QUEUE_DEADLINE_SECONDS: Final = 6 * 60 * 60
"""Runaway backstop for the layered wait, not a policy. Reaching it arms anyway
and logs at ERROR -- it must never mean "give up and leave the PC unlocked"."""

NETWORK_INCIDENT_LOCKOUT_SECONDS: Final = 300
NETWORK_INCIDENT_LOCKOUT_CAP_SECONDS: Final = 1800
"""The incident lockout doubles per recent incident, which reaches ~2.7 hours
by the sixth -- a genuinely dead ISP would hit that inside a week. The cap
keeps the escalation a deterrent rather than a punishment schedule that
outruns real outages."""

NETWORK_INCIDENT_BUDGET: Final = 99
"""Effectively unlimited, deliberately. A multi-day ISP outage must not brick
the machine, so the deterrent here is the escalating wait plus the written
record shown back on screen -- never exhaustion."""

JUSTIFICATION_MIN_CHARS: Final = 120
HISTORY_REVIEW_COUNT: Final = 10

# --------------------------------------------------------------------------
# Sync
# --------------------------------------------------------------------------

SYNC_REPO_OWNER: Final = "kuhyx"
SYNC_REPO_NAME: Final = "syncs"
SYNC_PATH_PREFIX: Final = "leetcode-guard-sync/devices"
SYNC_TIMEOUT_SECONDS: Final = 15.0
