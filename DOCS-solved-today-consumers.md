# Who consumes `solved_today`, and what it buys

The cross-repo contract is `leetcode_guard.solved_today` (the ledger read)
and the loopback endpoint in `leetcode_guard._web_server`. Both publish a
*fact* -- never a number of hours; the hour values belong to the consumers.

Two programs consume the same fact. `screen-locker` moves the nightly shutdown
**+1h** later on a day with an accepted submission (flat, once per day, on top
of its base -- 20:00, 19:00 from 2026-10-01 -- and the workout bonuses,
capped at 23:00). It reads
`ledger.json` directly in `screen_locker/_leetcode_bonus.py` and fails closed;
leetcode-guard never writes the shutdown config itself.

`steam-backlog-enforcer` adds **+1h** to the daily gaming budget on a day with
an accepted submission (5h floor, +2h for a workout, +1h for a solve, so a day
is worth 5–8h). It reads `ledger.json` directly and falls back to a read-only
loopback endpoint served by `leetcode-guard-web.service`:

```bash
curl -s http://127.0.0.1:8771/api/status | jq .leetcode
# {"solved_today": true, "solves_today": 2, "checked": true,
#  "settled_by_credit": true, "reason": "..."}
```

**A day paid ahead earns too** (2026-10-23). `settled_by_credit` is true when
today's charge is signed and sourced `leetcode`, which `_gate.decide` writes
only when verified credits cover the day; escape and outage charges carry
other sources. Every consumer pays the bonus on `solved_today` *or*
`settled_by_credit` (`earned_time` >= 0.17.0 reads the charge row itself).

Read-only, loopback-only, and it publishes a *fact* — never a number of hours.
The enforcer owns the hour values, the same split `screen-locker` uses for the
workout flag, so the two repos cannot disagree about what an earned day is.

`checked: false` means the ledger could not be read, which is **not**
`solved_today: false`. The enforcer fails closed on it (no bonus) *and* raises a
desktop notification, because a silently missing hour looks exactly like an
unearned one.

Staleness: credits are minted by the lock window's poll loop **and**, since
2026-10-17, by `leetcode-guard-harvest.timer`, which runs `_harvest_run` every
minute with no window up. A solve made on a sick day, a settled day or after the
last slot is therefore credited within about a minute (an extra solve on a
settled day now banks). While a lock is up the harvester stands aside, since the
lock's own loop harvests.
