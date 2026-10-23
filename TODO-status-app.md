REMOVE ME AFTER FINISH

# TODO: Flutter status app replaces the tkinter status window

Spec agreed 2026-10-23 (round 2 `override`, so every recommendation is the
decision).

## Goal

The tkinter status window (`leetcode_guard/status_view.py` + `_status_*`
sections) becomes a mobile-friendly Flutter app with three tabs:
**Status** (all 9 current sections: verdict, credits, progress/projection with
date control, solves, days, budgets, integrity, environment, suggestions),
**Coach** (from TODO-coach.md session logs: req-before-code, hint rungs,
re-tests due, cluster progress) and **Profile** (LeetCode difficulty split
solved/total, current + longest streak, 52-week submission heatmap,
acceptance rate).

## Decisions

1. **Data path.** PC pushes ONE display-only JSON snapshot to Firebase RTDB at
   `leetcode-guard/status`, using the shared credential in
   `~/.config/crdt-sync/` (see how other kuhy apps authenticate). The app only
   reads it. Nothing that decides, charges or credits may ever read the snapshot
   (same rule as `progress_cache.json`). No GitHub transport.
2. **Push cadence.** On every ledger change and from the one-minute harvester
   (`_harvest_run`). A push failure logs a warning and never affects the gate.
3. **Staleness.** App shows "as of HH:MM"; >10 min old shows a stale banner.
   Missing or unknown values render "unknown", NEVER `0`.
4. **Read-only app.** No unlock/credit/solve actions, ever. Tapping a
   suggestion opens its URL in the browser.
5. **Projection without porting rules to Dart.** The exporter precomputes the
   projection for every day of the next 90 days plus each month-end for 12
   months. The date control picks among those keys. Rules stay in Python only.
6. **Desktop.** Flutter web served on localhost in a Chrome `--app` window per
   the `flutter-desktop-to-chrome` skill (no `linux/` target). tkinter
   `status_view.py` and its tk-only section modules are DELETED. Remove them
   from `TK_MODULES` in `leetcode_guard/tests/_tk_stub.py` in the same commit.
   During a lock, the lock surface is the only status view.
7. **Tray.** `--summary` / `--state` CLIs stay in Python. Tray click opens the
   new app.
8. **Location/stack.** `app/` in this repo, id `com.kuhy.leetcode_guard`,
   newest stable Flutter pinned in `.fvmrc`, exact-pinned deps (dependency
   freshness rule). Shared icon family (`app-icon` skill). UI from
   `unified-design-system` tokens.
9. **Done/verify.** Installed on phone 23181JEGR08034 (`phone-deploy` skill);
   desktop screenshotted in Xephyr. Numbers match
   `python3 -m leetcode_guard._status --summary` at the same moment. Network
   off → stale banner, never `0`. `flutter test` with 100% coverage of `lib/`
   except platform glue. Python side: 100% branch coverage, ruff/mypy/pylint.

## Snapshot schema v1 (the contract both sides build against)

Built by `leetcode_guard/_snapshot*.py` (exporter landed 2026-10-23); the
example below is trimmed from a real read-back of the RTDB node.

**Transport.** RTDB path `leetcode-guard/status` holds ONE JSON **string**
leaf (crdt_sync's text-leaf convention, PUT with `print=silent`, ~32 KB),
not an object tree: a tree would
silently drop every `null` and `[]`, i.e. exactly the "unknown" sections.
The app reads the node and `jsonDecode`s the string once. Auth: the shared
`~/.config/crdt-sync/` account; the existing root rule already grants this
uid read/write, so no rule change. A push runs after every `_harvest_run`
minute and on every write of the production ledger.

**Heartbeat (staleness, decision 3).** `leetcode-guard/heartbeat` is a JSON
string leaf holding the ISO time of the last successful push (~27 bytes,
written every minute with `print=silent`). The full `status` node is written
only when the snapshot's content -- everything except `generated_at` --
differs from the last successful write (SHA-256 kept in
`~/.local/share/leetcode_guard/snapshot_push_state.json`), so its
`generated_at` is "when the content last changed", NOT "how fresh it is".
The app's "as of HH:MM" and the >10 min stale banner read the
**heartbeat**. A failed snapshot write skips the heartbeat, so a fresh
heartbeat never sits over stale content. Cache `age_days` are rounded to one
decimal (what the window shows) so they do not change every minute; a
profile refetch (`fetched_at`, at most every 15 min) still counts as a
change. Upload drops from ~46 MB/day to roughly 3-4 MB/day.

**Status hash (phone polling).** `leetcode-guard/status_hash` is a JSON
string leaf holding the SHA-256 hex digest of the snapshot's content (the
same hash `_snapshot_dedup.content_hash` dedups on: everything except
`generated_at`, canonical JSON). It is written in the same push as every full
`status` write, *after* it: status, then status_hash, then heartbeat, and the
push is recorded locally only once the hash landed, so a failed hash write
re-sends both next minute. The phone polls `heartbeat` + `status_hash` (well
under 100 bytes) every minute, keeps the hash it last downloaded beside the
decoded status, and GETs the ~49 KB `status` only when the hash differs. It
must not try to recompute the hash in Dart (no canonical JSON there); it
only compares strings. A missing (`null`) `status_hash` means "download
`status`": the node first appears with the first content change after the
exporter that writes it is deployed.

**Local file (desktop, no Firebase).** Every push attempt, offline ones
included, first writes the full snapshot (same schema, `generated_at`
included) atomically to `~/.local/share/leetcode_guard/snapshot.json`
(`_snapshot_local`, via `_atomic_json.write_json`). The desktop app reads
that file; since it is rewritten every minute even when the content is
unchanged, its own `generated_at` is the desktop's "as of" and stale signal
(no heartbeat locally). Display-only: no deciding module may read it
(`test_push_trigger.py::test_no_deciding_module_names_the_local_snapshot_file`).

```json
{
  "schema": 1,
  "generated_at": "2026-10-23T15:04:18+02:00",
  "status": {
    "day": "2026-10-23", "weekday": "Friday", "state": "already-charged",
    "locked": false, "reason": "today is already paid for",
    "explanation": ["Today was already settled by an earlier run, ..."],
    "cost": 4, "surcharge": 1, "credits": 133, "charged": 133,
    "available": 0, "needed": 0, "charged_today": true,
    "earned_all_time": 133, "spent_all_time": 133,
    "debt": {"owed": 28, "repaid": 27, "outstanding": 1, "missed_days": 21,
             "summary": "1 credits outstanding (21 missed days owed 28, 27 repaid)"},
    "pricing_note": "Tue/Wed/Thu cost 2, Mon/Fri cost 3, Sat/Sun cost 4, plus 1 ...",
    "solves": {"today": 0, "last_7_days": 22, "total_credited": 133,
               "recent": [{"day": "2026-10-22", "title_slug": "missing-number",
                           "lang": "typescript"}]},
    "days": {"charged": ["2026-10-23", "2026-10-22"], "start_date": "2026-08-04",
             "in_force": true},
    "budgets": {"escape": {"label": "Escape hatch", "used_7": 0, "used_30": 0,
                           "used_90": 0, "limit_7": 1, "limit_30": 3,
                           "limit_90": 10, "exhausted": false,
                           "next_wait_seconds": 120,
                           "summary": "Escape hatch: 0/1 per 7d, 0/3 per 30d, 0/10 per 90d"},
                "incidents": {"label": "Network incidents", "...": "same shape"}},
    "integrity": {"ok": true, "tampered": 0, "discounted": 0, "unparsable": 0,
                  "clock_trusted": true, "total_entries": 206,
                  "bootstrapped": true, "ledger_path": "/home/.../ledger.json"},
    "environment": {"clock_trusted": true, "auth_present": true,
                    "auth_note": "...", "pool_source": "cache", "pool_notes": [],
                    "cookies_configured": true, "sync_configured": true,
                    "timer": {"enabled": true, "next_fire": "Sat 2026-10-24 09:00:00 CEST",
                              "detail": "enabled"},
                    "pool_cache": {"name": "Problem pool", "exists": true,
                                   "entries": 4087, "age_days": 2.17,
                                   "summary": "Problem pool: 4087 entries, 2.2 days old"},
                    "statement_cache": {"...": "same shape as pool_cache"}},
    "suggestions": [{"title": "...", "difficulty": "Medium",
                     "ac_rate": 52.1, "url": "https://leetcode.com/problems/..."}]
  },
  "progress": {"solved": {"Easy": 142, "Medium": 0, "Hard": 0},
               "total": {"Easy": 972, "Medium": 2131, "Hard": 984},
               "solved_all": 142, "total_all": 4087,
               "fetched_at": "2026-10-23T15:01:37+02:00"},
  "projection_price": 2,
  "projections": {"2026-10-24": {"target": "2026-10-24", "first_day": "2026-10-24",
                  "gated_days": 1, "free_days": 0, "sick_days": 0,
                  "base_cost": 4, "debt": 1, "available": 0, "required": 5,
                  "rules_demand": 5, "debt_left_by_rules": 0,
                  "projected": {"Easy": 147, "Medium": 0, "Hard": 0}}},
  "profile": {"difficulty": {"easy": [142, 972], "medium": [0, 2131],
              "hard": [0, 984]}, "streak_current": 6, "streak_longest": 19,
              "calendar": {"2026-10-22": 31}, "acceptance_rate": 25.2,
              "fetched_at": "2026-10-23T15:01:37+02:00"},
  "coach": {"problems": [{"slug": "missing-number", "cluster": "bit-cancellation",
            "req_before_code": true, "max_rung": "H1", "revealed": false,
            "req_check": "pass|incomplete|unverified", "day": "2026-10-23"}],
            "retests_due": null,
            "clusters": null}
}
```

Any section may be `null` = unknown (fetch failed / coach not built yet); the
app renders "unknown" for a null section, never zeros. Inner nulls too:
`projected` (no solved counts yet), `streak_*`/`calendar` (calendar
unreadable), `acceptance_rate` (no submissions), `req_before_code` (no code
yet), `max_rung`/`req_check` (no such event yet). Field names mirror the
Python dataclasses (`StatusSnapshot`, `FullStatus`, `Projection`).

Deltas from the first draft of this block (exporter, 2026-10-23):

- `status.solves` and `status.days` are objects, not arrays: they carry what
  the tk sections render (today / last 7 days / total + recent list; charged
  days + start date + in force). Per-day `free|sick|owed` kinds were dropped
  -- deriving them outside `_debt` would be a second copy of the debt rules.
- `status.budgets.*` carry the full `BudgetStatus` plus its `summary` line.
- Added `status.explanation` ("why the lock did not trigger", rendered by
  Python), `earned_all_time`/`spent_all_time` (ledger totals, which differ
  from `credits`/`charged` when credits are refused), `debt.summary`,
  `pricing_note`, `integrity.{clock_trusted,total_entries,bootstrapped,ledger_path}`,
  `environment.{cookies_configured,sync_configured,timer,pool_cache,statement_cache}`.
- `progress` is per difficulty plus `solved_all`/`total_all`/`fetched_at`.
- `projected` is keyed by difficulty (Easy filled first, as the window does);
  each projection also has `first_day`. `projection_price` is the Tue-Thu
  price they were computed at. Keys: today + 89 days, plus the last day of
  this month and the 11 after it (99 keys when they overlap).
- `profile.fetched_at` added. The profile is refetched at most every 15 min
  (or at once when the credit count moves); a failed refresh serves the
  dated mirror, `null` only if no fetch ever succeeded. Calendar days are
  UTC (LeetCode's keys are UTC midnights); `streak_current` may end yesterday;
  `streak_longest` is over LeetCode's rolling year (matched its own `streak`
  field, 19, on 2026-10-23).
- `coach.retests_due` and `coach.clusters` are `null` until the coach exposes
  them: their rules (decisions 10, 12) belong to the coach, not the exporter.

## Commit

`main` only, no feature branches. Check `git status` against own files first;
concurrent sessions edit this tree.
