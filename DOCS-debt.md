# Debt — missed days raise the daily quota by one until repaid

Design record for the rule added on 2026-09-11. Decided in a planning session
after an eight-day vacation (2026-09-03 → 09-10) that, under the old policy,
cost nothing.

## The rule

- Every past day from `DEBT_START_DATE` (= the gate start, 2026-08-04) that
  carries **no charge** and was **not a declared free day** is *owed* at the
  price it would have cost on that date: from 2026-09-21, 2 on Tue-Thu and 4 on
  Mon/Fri/Sat/Sun; before that, 1 on a weekday and 2 on Saturday or Sunday.
- While anything is outstanding, every gated day costs **one extra credit**;
  that credit is the repayment. Tue-Thu 2 → 3, doubled day 4 → 5.
- Repayment is one per day. No cap on the debt, permanent rule.
- Free days pause the debt: no charge, no repayment.
- An escape-hatch or outage settlement charges the *base* cost: that day is
  settled (not owed) but repays nothing.

On the day it shipped the live ledger owed **22 credits over 18 missed days**
(the 08-05..08-11 lockout-incident week, 08-13, 08-27 and the vacation).

## Why derived, never stored

`_debt.compute_debt` walks the calendar `[epoch, today)` against the set of
charged days and the free-day pool, and sums `amount - day_cost(day)` over
charges as repayment. Nothing is written.

- `rm ledger.json` makes every day since the epoch uncharged and *grows* the
  debt. A stored `debt:` entry would have the opposite property — the same
  mistake as the reverted `charge:<today>` bookkeeping in the 2026-08-05
  incident.
- Back-filling `charge:<past-date>` for missed days is off the table: that is
  the exact key `decide` unlocks on, and it feeds `latest_charged_day` in the
  clock guard.
- The free-day pool is consulted only for uncharged days, so the lookup cost
  scales with days actually missed, not with the calendar.

## Why repayment follows the credit rule

The HMAC covers `amount` and `detail`, but charges count even when their
signature fails (discarding one would be a refund). If repayment counted the
same way, appending `{"kind": "charge", "amount": 99}` unsigned would clear the
debt. So the surcharge component is read only from *trusted* charges (valid
signature, or this device's own entry when the key is unreadable — the same
rule credits use, `_balance.is_trusted`). An untrusted charge still counts as
spent in full: inflating one costs balance and buys nothing.

## The bug this uncovered

`apply_decision` had exactly one call site, inside the poll loop. The timer
path (`_cli._run_lock`) returned on any non-locked decision — including
`UNLOCKED_CHARGED_NOW` — without writing the charge. A day paid from banked
credit therefore left no charge behind, which under this rule would read as a
missed day. It had never bitten because the balance had been zero at every day
boundary since install (every charge in the live ledger shares a timestamp
with its credit). Fixed in its own commit, test first:
`test_production_persists_the_charge_when_banked_credit_pays_for_today`.

## Test plumbing

`tests/_debt_fixtures.py` (a pytest plugin, because `conftest.py` sits at the
250-line cap) moves `DEBT_START_DATE` to `date.max` in every module for every
test, so the suite defaults to zero debt. `debt_starts(MONDAY)` switches it on.
The demo passes `demo=True` to `decide_today` and shows no debt, because it
deletes its ledger every run.
