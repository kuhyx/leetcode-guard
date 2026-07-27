# leetcode-guard

Locks the PC until you solve a LeetCode problem. Fourth sibling to
`screen-locker`, `diet-guard` and `wake-alarm`, built on the same shared
[`gatelock`](https://github.com/kuhyx/utils/tree/main/gatelock) lock-window
backend.

## How it decides

A **derived-balance ledger**, never a stored counter.

| | |
|---|---|
| One accepted LeetCode submission | **+1 credit** |
| A weekday | **costs 1 credit** |
| Saturday or Sunday | **costs 2 credits** |
| Balance | `sum(credits) - sum(charges)`, recomputed every time |

Credits are uncapped and fungible: solve three on Monday and Monday, Tuesday
and Wednesday are all clear; Thursday locks again. A credit earned midweek
spends fine on a Saturday, it just goes half as far.

Two properties fall out of keying credits on LeetCode's own **submission id**
rather than a time window:

* a problem solved *before* the lock appeared still counts;
* polling every 30 seconds is idempotent.

**Charge on use, never retroactively.** Only days the gate actually ran are
charged, so coming back from two weeks away costs nothing.

## What counts

**Any** accepted submission, on **any** problem, in **any** language —
including premium problems. The list the lock shows is a *suggestion*: every
non-premium problem, easiest first, then highest acceptance rate. Solve
something harder or entirely off-list and it still credits.

The suggestion list is derived from LeetCode's public API, needs no login, and
is cached for seven days so it still renders with the network down.

## Optional sign-in

Drop your browser cookies into `~/.config/leetcode_guard/cookies.json`:

```json
{"LEETCODE_SESSION": "...", "csrftoken": "..."}
```

That does exactly one thing: hides problems you have already solved from the
suggestion list. It is never consulted for solve detection, so an expired
session (they last about two weeks) can only make the suggestions worse — it
can never stop the gate unlocking. Without it the lock says so on screen.

## When LeetCode cannot be reached

The gate distinguishes three cases, because they deserve opposite answers.

| Situation | What happens |
|---|---|
| **LeetCode is down, your connection is fine** | Unlocks automatically, explains why, logs at ERROR. Not your fault, not yours to fix. |
| **Your machine has no internet** | Stays locked. After ~5 minutes a **mandatory network-incident form** appears; writing down what happened releases the day. It costs no escape budget, so a bad-wifi week cannot spend the allowance meant for "I could not face it today". The wait doubles per repeat incident, capped at 30 minutes. |
| **Everything else works but leetcode.com specifically does not** | Treated as the case above. Closes the one-line `/etc/hosts` bypass. |

That last row catches the cheap local blocks — an `/etc/hosts` line, a Pi-hole
rule, anything that makes the name resolve to loopback or a private address.

**Honest limit:** a block applied at your *router*, or a captive portal
answering from a public address, is indistinguishable here from a real LeetCode
outage and will unlock the day. Every verdict is logged loudly. This raises the
cost of that bypass; it does not make it impossible.

## Escape hatch

Separate from network incidents, with real budgets (1 per 7 days, 3 per 30, 10
per 90). Costs a 120-character written justification, shows your last ten back
to you, and the wait doubles with recent use. It appears after ten minutes of
an ordinary lock, or after three minutes if the gate has gone blind.

Using it still writes a full-cost charge, so the balance goes negative and the
debt carries. A forgiven day is not a free one.

## Layered with the other lockers

Ranks: `wake_alarm` (300) → `screen_locker` (200) → **`leetcode_guard` (150)** →
`diet_guard` (100).

If the workout lock is up, this one **waits with no window at all** and arms
when that one finishes. It never exits because another lock is running —
starting the workout lock is not a way to skip the grind.

## Install

```bash
./install.sh                 # system python + systemd user timer
bash scripts/setup_mcp.sh    # optional: the read-only MCP server
```

Fires at **09:00** with a **13:00** retry. The retry is free: a day already
settled exits in milliseconds and draws nothing.

**The gate does not come into force until 2026-08-04** (`GATE_START_DATE` in
`_constants.py`). Until then every scheduled run exits immediately without even
a network call — systemd has no "not before date X" for `OnCalendar`, so the
start date lives in the gate decision where `--status` and MCP can see it.
`--production` respects it; the demo ignores it so the lock can always be
shown.

## Status view

A tray icon in the i3 bar, mirroring screen-locker's workout-status:

* **left-click toggles** the window — click to open, click again to close;
* the icon is a red/amber/green **speech bubble** — deliberately a different
  silhouette from screen-locker's shields, because two shields side by side
  in the same tray are indistinguishable at 24px;
* the tooltip is a one-line summary, refreshed every 60s;
* right-click gives Refresh and "Quit tray icon".

The window shows everything the project knows: the verdict and **why the lock
did not trigger**, credits available/earned/spent, solves today and this week
with the recent list, which days are settled, both escape budgets, ledger
integrity and clock trust, timer state and next fire, cache freshness, and the
suggested problems.

It is read-only and offline — safe to open at any moment, including while the
lock is up. It closes four ways: the Close button, Escape, the window
manager's close box, and clicking the tray icon again.

```bash
leetcode-guard-status              # the window
leetcode-guard-status --summary    # one line (tray tooltip)
leetcode-guard-status --state      # ok | warn | lock (tray icon colour)
```

## Commands

```bash
python3 -m leetcode_guard              # demo lock (safe: local grab, close button)
python3 -m leetcode_guard --production # the real thing
python3 -m leetcode_guard --check      # today's full decision trace; writes nothing
python3 -m leetcode_guard --status     # ledger position from disk; no network
python3 -m leetcode_guard --probe      # live API data
python3 -m leetcode_guard --sync       # push/merge the ledger via crdt_sync
```

`--check` is the one to reach for. It does everything an armed gate would, right
up to persisting anything, so you can answer "would this lock me out?" without
finding out the hard way.

## Integrity

Ledger entries are HMAC-signed against `/etc/workout-locker/hmac.key`, shared
with the sibling lockers.

* A credit whose signature does not verify is **kept on disk and refused** —
  hand-editing the JSON cannot buy a day.
* A *charge* whose signature does not verify still counts — discarding one
  would refund a day.
* If the key becomes unreadable, this device's own credits keep counting
  (loudly), but credits arriving over sync do not. Otherwise a single `chmod`
  would brick the machine.

**Honest scope:** the key is world-readable, so this is tamper-*evident*, not
tamper-*proof*. It stops casual editing and leaves a record; it does not stop
someone who reads the key.

The gate also refuses to honour an existing charge when the system clock has
moved backwards past a settled day — otherwise setting the date back would be
the cheapest bypass of all.

## Development

```bash
python3 -m pytest              # 561 tests, 100% branch coverage enforced
pre-commit run --all-files     # ruff ALL / mypy strict / pylint all / bandit
```

`# noqa` and `# type: ignore` are banned repo-wide, files are capped at 400
lines, and every swallowed exception must log why.
