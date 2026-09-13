# Incident 2026-09-13 — the gate armed nothing on a Sunday morning boot

**Severity: medium.** Today cost 3 credits with 0 banked and 21 in debt, and
the PC came up unlocked and stayed that way. Nothing was bypassed by the user;
the timer and the unit between them simply never produced a window.

Everything below is from `journalctl --user`, two boots.

## What happened

| Time (CEST) | Boot | Event |
|---|---|---|
| 09:15:15 | A | Machine powered on |
| 09:15:18 | A | `leetcode-guard.timer` started; `Persistent=true` fired the missed 09:00 slot at once. systemd wrote `stamp-leetcode-guard.timer` **here**, when the timer elapsed |
| 09:15:19 | A | `leetcode-guard.service` started. No X server yet (`autorandr: Can't open display :0` at the same second), no DNS |
| 09:15:20 | A | Pool fetch failed on name resolution, fell back to a 7-day-old cache; every live solved-check failed |
| 09:15:21 | A | Queued behind `workout-locker` (`wait_for_turn`), which had armed via `graphical-session.target` |
| 09:16:49 | A | X server killed ("explicit kill or server shutdown"); the user session began exiting. `workout-locker` died with it |
| 09:16:50 | A | Our turn came; `RandrBackend.create` → `Can't connect to display ":0"` → **exit 1**. Session was already stopping, so `Restart=on-failure` never ran |
| 09:17:24 | A | Boot A ended (reboot). Why X was killed and the box rebooted is not in the journal; unattributed |
| 09:18:42 | B | Machine powered on again |
| 09:18:45 | B | `leetcode-guard.timer` started. The 09:00 slot was already stamped as fired → no catch-up. Next fire: 13:00 |
| 09:18:46 | B | `workout-locker` armed via `graphical-session.target` — the login path this unit did not have |

## Two defects, one symptom

1. **The timer is the only trigger, and its stamp records the *elapse*, not a
   successful run.** Any death between elapse and window — X not up yet, X
   dying, a reboot mid-wait — consumes the day's catch-up. Boot B had no
   trigger left at all.
2. **The unit had no idea whether X existed.** `After=graphical-session.target`
   orders nothing for a timer-started unit when that target is not in the same
   transaction. `ExecStartPre=/bin/sleep 1` was the only concession, and a
   crash loop under `Restart=on-failure` with `RestartSec=2s` would have hit
   the user manager's default start limit (5 in 10 s) within seconds anyway.

## Fix

- `gatelock.wait_for_x_server` waits **unbounded** (was 60 s), polling every
  second and re-stating itself at WARNING every five minutes. No X server means
  the user cannot use the machine either, so the wait is not a bypass; a
  deadline was the original defect with a different number.
- `_run_lock` calls it before `build_client()` in production. The first fetch
  therefore also lands after boot-time DNS is up, without any network wait —
  a network wait *would* be a bypass (unplug the cable) and
  `_netcheck`/`_network_incident` already cover a lock with nothing reachable.
- `leetcode-guard.service` gains `[Install] WantedBy=graphical-session.target`
  and loses the `sleep 1`. `install.sh` enables the service (not `--now`).
  The i3 config also starts it explicitly, next to `workout-locker`, because
  i3 does not always reach that target.
- The timer stays for a machine that was on all night.

Login arming is safe because the run is idempotent per day: a solve, banked
credit, the escape hatch and a classified outage all write `charge:<today>`,
which `decide` exits on without a window. The one run that cannot see today as
settled — the seeding run — defers by returning, never by writing state.
