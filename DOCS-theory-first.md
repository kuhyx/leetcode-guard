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
  The tutor's unsigned `log.jsonl`/`cards.json` never decide (`_theory` is
  banned from every decider, `test_display_only_imports.py`).
- **Solved**: trusted `credit` and `seen` rows in the guard ledger.
- **A unit's Easy set**: the pool cache split by `claim_order`, premium
  problems left out (a premium Easy can never be opened, so the unit could
  never finish). The pool is unsigned: editing it can move the phase (for
  example empty a unit so the machine moves on), but it can never mint a
  credit: that still needs signed tutor minutes or LeetCode's accepted feed.
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
  theory became done (its modules' latest `at`) do not count.
- The k-th credit for a unit on a day is minted at 12*k minutes:
  `kind: credit`, `amount: 1`, `entry_id: theory:<day>:<n>` (n runs over the
  day), `detail: {source: tutor-theory, unit, minutes}`. It prices at 1 and is
  never revoked. A deleted ledger re-mints at most today's.
- Callers: the one-minute harvester (whatever LeetCode answered; not before
  the ledger is seeded; never while a lock is up) and the lock's own poll. A
  theory credit settles the day exactly like a solve.

## C3: `theory_phase.json`

`<DATA_DIR>/theory_phase.json`, one signed row (`_phase_file.py`), rewritten
only when unit, phase or `teachable` changes. Unsignable (key unreadable):
not written, logged; the tutor then fails closed.

## Known limits

- The phase reads the pool cache. A stale cache shifts a unit's Easy set
  until the next refresh.
- A theory credit is a `credit` row with no `submitted_at`. `solved_today`
  counts it as one of today's solves (by its `day`), and earned_time's
  `leetcode_match` counts it on a gate-off day (sick, focus), where credit
  rows pay the rung. Not changed here: a consumer decision for kuhy.
