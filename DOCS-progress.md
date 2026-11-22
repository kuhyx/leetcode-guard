# Progress row (2026-11-22)

kuhy decided every gate pays its shutdown bonus in proportion to progress.
`earned_time` cannot know this guard's price, so the guard signs the fact:
"done N of target M" for a day it still holds. The reader ships in a later
`earned_time` release; until then the row is inert.

## The row

`kind: progress`, `entry_id: progress:<day>:<done>:<target>`, `amount: 0`,
`detail: {source: leetcode, for_day, done, target}` (all strings), signed with
the ledger's own `sign`, so `earned_time.verified(row, key)` accepts it. The
key is read stripped, as gatelock reads it; a test key with whitespace at an
end must be stripped too.

## The numbers

One pure function, `_gate_progress.progress_counts(ledger, decision, weights)`:

- `earned` = weighted value of the trusted credits dated today (theory is 1).
- `done` = max(earned, `balance.available`, 0). Credit banked on earlier days
  is work done ahead; a negative carried balance never shrinks today's own.
- `target` = `done` + `decision.needed`.

The writer and the study strip's dots both call it: filled dots are `done`,
hollow are `target - done`. They cannot disagree. It lives in a decider-side
module so deciders never import display code (`test_display_only_imports.py`);
`_earned_today.strip_counts` is the display wrapper.

## When it is written (`apply_progress`, `_gate_progress.py`)

Only for `LOCKED_INSUFFICIENT` (a gated, uncharged, short day on a trusted
clock) with `done >= 1`. A charged day, a free, sick, focus or not-started day,
and an untrusted clock write nothing. The same id is never written twice, and a
row that cannot be signed (key unreadable) is not written: it would be worthless
and its id would block the signed one.

Call sites, both after the credit or charge is saved:

- `_harvest_run._harvest_once`: only in a run that minted a credit (a theory
  credit counts), never while a lock is up, never when `gate_deferred` (morning
  session, tonight's lockdown), never in the run that has no ledger yet.
- `_lock_progress.record_progress`, from `_lock_poll.on_poll_result`, while the
  lock is up; not in the demo, not when the lock may not write.

`_cli` writes none: its `apply_decision` spot is the already-unlocked branch, and
the seeding run returns before arming.

## Failure modes

Writing is best effort. A failure (unreadable key, unwritable ledger, a bug)
costs the row only: the credit and the decision are already saved, it is logged
at warning or above, and nothing is raised. `rm ledger.json` earns nothing: the
next run seeds and arms nothing, and no row exists until a credit is minted.
