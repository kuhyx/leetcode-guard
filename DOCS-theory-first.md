# Theory-first flow (stage 4, 2026-11-22)

kuhy: "first we learn as much theory and how to approach those problems on an
abstract level and then we can solve it". The guard owns one state machine
over the curriculum units; the tutor teaches only what it allows.

## The machine (`_phase.py`, pure)

Units are walked in teaching order (`curriculum.json` `units`). The current
unit is the first one not finished; a unit is finished when its theory is
done AND every free Easy problem of it is solved.

| phase | when | teachable | what pays |
|---|---|---|---|
| `theory` | u's theory not done | u's modules | solves, and teaching minutes on u's modules |
| `solve` | theory done, Easy left | nothing | solves (and minutes taught before the flip) |
| `none` | every unit finished | nothing | solves |

Rework needs no code: a module whose latest signed row says not done puts its
unit back in `theory`.

## Inputs, and why each is trusted

- **Theory done**: verified rows of the tutor's `module_state.json` (C2), the
  latest per (subject, module) by `at`, then file order. No row = not done.
  One row that fails its signature makes the whole file "cannot check":
  dropping it could only un-do a module and pay theory again (e2e,
  2026-11-22). The tutor's `DOCS-contract-module-state.md` "Reader rules"
  states the same rule. While it holds, the last signed phase stays, no
  theory credit mints, solves still pay, and the lock keeps its Open rows,
  hatch and break-glass. The tutor never writes an unsigned row, so the fix
  is to delete the bad row by hand. Unverified C1 rows are just dropped:
  that only pays less.
  The tutor's unsigned `log.jsonl`/`cards.json` never decide (`_theory` is
  banned from every decider, `test_display_only_imports.py`).
- **Solved**: trusted `credit` and `seen` rows in the guard ledger.
- **A unit's Easy set**: the pool cache split by `claim_order`, premium
  problems left out (a premium Easy can never be opened, so the unit could
  never finish). The guard signs `pool_cache.json` (HMAC, the ledger's key
  and scheme) when it writes it after a live fetch, and only a signed,
  `complete` pool decides: an unsigned, edited or half-fetched one is "cannot
  check" below, so a text editor or a fetch that stopped early cannot move
  the phase. Display (suggestions, ranking) still reads an unverified pool.
  The refresher treats such a pool as stale and rewrites it signed on the
  next arming run or `--probe`; an incomplete one is retried after an hour.
  A refresh that comes back incomplete never replaces a signed, complete pool:
  the file stays as it was (so it stays stale and the next run retries), and
  an incomplete pool is written only when there is no better one to keep.
- **Order and mapping**: `curriculum.json`, shipped in the package.

Any input that cannot be read makes `gather_phase` answer `None` ("cannot
check"): nothing mints, `theory_phase.json` is not rewritten, and the display
holds the last signed phase.

## The theory credit (`_theory_credit.py`)

`poll_theory(ledger, ledger_path, *, day, now, key_file=None)` decides the
phase, rewrites C3 on change, mints and saves. It never raises.

- Minutes: verified C1 rows (`ledger.json`, `detail.subject` +
  `detail.module`) on the current unit's modules whose `ended_at` falls on
  today; earned_time's rules (positive-int `minutes`, a repeated `entry_id`
  pays its smallest count). Review, drill, leftover and carry rows have no
  `module` and never count. In `solve`, rows that ended after the unit's
  theory became done (its modules' latest `at`) do not count; a row that
  ended up to 2 s after it still does (`UNTIL_SLACK_S`: the tutor stamps
  C2 after the turn that finished the module). Rows that ended before
  THEORY(u) began (C3 `theory_since`) never count: the tutor does not gate
  SQL, so morning SQL minutes would otherwise pay when THEORY(sql) begins
  (red-team R2, `e2e_theory i`). No C3 agreeing with the live phase pays 0.
- The k-th credit for a unit on a day is minted at 12*k minutes:
  `kind: credit`, `amount: 1`, `entry_id: theory:<day>:<n>` (n runs over the
  day), `detail: {source: tutor-theory, unit, minutes}`. It prices at 1 and is
  never revoked. A deleted ledger re-mints at most today's.
- **The finish credit** (`_theory_finish.py`, kuhy 2026-11-22): finishing a
  module pays +1 on top of the minute credits (9 min + finish = 1, 24 min +
  finish = 3), so a module finished in under 12 minutes is not worth nothing.
  `kind: credit`, `amount: 1`, `entry_id: theory-done:<subject>:<module>`,
  `detail: {source: tutor-theory, unit, subject, module, finish: "1"}`.
  - Done = the module's latest verified C2 row says `done: true` (the phase
    machine's strict read: one bad row is "cannot check" and mints nothing).
  - **Once per module ever**: the id has no day, so `done` flipping back (a
    card added or suspended) and true again never pays twice. Per module, not
    per unit (`js-pandas` and `sql` have four modules: up to four credits).
  - **Only the day it becomes done**: the latest done row's `day` must be
    today. A module done on an earlier day never pays (no back-pay), so a
    deleted ledger re-mints at most today's finish, like the minute credits.
  - **Only the current unit**: modules of the unit current when the poll
    starts (the last signed C3) or when it ends (the phase just decided), so
    the poll that flips THEORY into SOLVE, or moves on to the next unit, still
    pays the unit it leaves. The tutor backfilled all 25 C2 rows on
    2026-11-22 (15:09) and `sql-lessons` reads done today, though nobody
    taught it and `sql` is not current: it pays nothing
    (`test_theory_finish.py`, `e2e_theory j`).
  - It is not a minute credit: the id has no `theory:<day>:` prefix, so
    `due_credits` and `minutes_into_credit` never see it. It does count in
    `theory_credits` / `credits_today` (by the row's `day`) and settles the
    day like any theory credit. Like the minute credits it needs C1 readable
    in the same poll: any unreadable input mints nothing.
- Callers: the one-minute harvester (whatever LeetCode answered; not before
  the ledger is seeded; never while a lock is up) and the lock's own poll. A
  theory credit settles the day exactly like a solve.
- The harvester polls before it credits solves, and once more in a run that
  credited one: a solve that finishes the unit rewrites C3 to the next unit
  in that run, not a minute later (`e2e_theory e`). If the second poll cannot
  check, C3 stays on the old phase and nothing mints (fails closed).

## C3: `theory_phase.json`

`<DATA_DIR>/theory_phase.json`, one signed row (`_phase_file.py`), rewritten
only when unit, phase or `teachable` changes. Unsignable (key unreadable):
not written, logged; the tutor then fails closed. `detail.theory_since` is
when THEORY(u) began: "now" when THEORY(u) is entered from anything else
(SOLVE(u) too, so a re-entry starts over), carried into SOLVE(u); a row
without it (an older guard) uses its `at`. Deleting C3 restamps it "now", so
it can only pay less. The tutor ignores the key.

## What the lock shows, and in which order

- `_unit_view.unit_view(ledger_path, *, key_file=None, today=local_today)`
  returns the `Callable[[], PhaseView]` the window calls on every repaint
  (`GuardSeams.phase`). Read-only: it never polls or mints. The minutes and
  the 12 come from `_theory_credit`; the cards bar reads the tutor's unsigned
  files, so `_unit_view` is display-only (banned from every decider, allowed
  in the windows). Cannot check or a bug: the last signed phase, no cards.
- Ranking (`_unit_rank.focus_key`, used by `resolve_pool`): in THEORY(u) and
  SOLVE(u) u's Easy problems lead; in `none` the order is the old one. The
  phase is decided from the pool being ranked plus signed C2, else C3, so
  the rows match the header (up to a solve not harvested yet). Only the key changes; the top N are still the
  only rows verified live.

## The read-only surfaces (part F)

`_status_unit.gather_unit` wraps `_unit_view.read_unit` (the lock's view plus
its source: `live`, `held` = the last signed C3 phase, `unknown`) and counts
today's trusted `theory:<day>:` credits. It never polls, mints or writes C3,
and it shows "cannot check" as unknown where the lock shows 0.

- `--status`: `unit`, `theory` (today's minutes, the rate, credits minted
  today) and, in THEORY, `learn` lines. The status snapshot gets the same as
  data in `status.unit` (`unit_dict`, no prose): `unit`, `phase`, `source`,
  `leads_with` (`theory`/`problems`), `solved`/`total` (`null` unless
  `live`), `theory_minutes_today` (`null` = cannot check),
  `minutes_per_credit`, `theory_credits_today`, `cards_taught`/`cards_total`
  (`null` = tutor files unreadable), `lessons_ready`, `learn_target`,
  `learn_route`.
- MCP: `get_status.unit` and `explain_lock` carry the unit, phase,
  `leads_with` and `lead_reason`; `get_credits` splits `theory_credits` /
  `theory_credits_today` from `solve_credits`; `get_suggested_problems` is
  `resolve_pool`'s order, the lock's unit-first ranking.
- `open_cli` (the daily-limits row) opens the lock's first action: in THEORY
  `tutor --route` on `learn_route` (the learn button's own code), else the
  first problem; a missing or failing tutor logs a warning and opens the first
  problem.

## `GET /api/theory` (display mirror, `_web_theory.py`)

The tutor server fetches it over loopback (port 8771, beside `/api/status`)
for its lesson bar and only displays it. One `theory` object: `checked`,
`day`, `unit`, `phase`, `minutes_today`, `minutes_into_credit` (towards the
next credit, `0..minutes_per_credit`; a full 12 means a mint is pending, from
`_theory_credit.minutes_into_credit`, the read side of `due_credits`),
`minutes_per_credit`, `credits_today` (trusted rows, `theory_credits`) and
`needed` (the gate's `verdict.needed`).

- Signed inputs only (guard ledger, gate decision, tutor C1/C2, the phase
  machine); it must not import `_theory` or `_status_unit`
  (`test_display_only_imports.py`). Read-only: no write, mint, seed or lock.
- `null` = cannot check, never 0; `checked` is true only when nothing is
  `null`. In `none` the unit is `""`. A bug inside answers `null` and logs a
  warning (HTTP 200).

## Known limits

- "Solved" is the guard ledger only, while `rank_pool` also hides problems
  LeetCode marks `ac`. An Easy solved before the guard existed is NOT a gap:
  `_phase_inputs.trusted_solved_slugs` counts `credit` AND `seen` rows, and
  measured on 2026-11-22 the ledger's 187 credited slugs plus the 9 slugs
  seeded on 2026-08-05 equal the profile's 196 solved exactly (gap 0). What is
  still open: a solve that neither the seed nor the harvester ever recorded
  would count as unsolved for the machine and never show on the lock, so
  SOLVE(u) could wait on a problem it does not offer. The harvester reads the
  20 most recent accepted submissions every minute, so that needs more than 20
  accepted submissions between two harvests (or a harvester outage that long).

- The phase reads the pool cache. A stale cache shifts a unit's Easy set
  until the next refresh.
- A theory credit is a `credit` row with no `submitted_at`. `solved_today`
  counts it as one of today's solves (by its `day`), and earned_time's
  `leetcode_match` counts it on a gate-off day (sick, focus), where credit
  rows pay the rung. Not changed here: a consumer decision for kuhy.
