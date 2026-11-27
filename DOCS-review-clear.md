# A cleared review pays 1 credit (2026-11-27)

kuhy, 2026-11-24: he cleared every due prefix-sums card while the lock was up and got nothing.
His six review minutes were half of the 12-minute theory credit, and clearing the queue paid
nothing by itself. From 2026-11-27 clearing every due card of the current unit pays 1 credit.
Review minutes still pay 12 minutes = 1 credit with no daily cap, so reviews alone can pay a day.

## The row

`review-clear:<day>:<unit>`, `kind: credit`, `amount: 1`, `detail.source: "tutor-theory"`
(it prices at 1 and counts in `theory_credits`), `detail.unit`, `detail.cards` (the unit's
queue size). The repair adds `detail.repair: "true"`. Once per unit per day.

## The rule (`_review_clear.due_review_clear`)

For the current unit (THEORY or SOLVE; `none` has no unit), all of these must hold:

- the tutor's signed `ledger.json` has review-minute rows (`activity == "review"`) on the unit's
  modules that ended on the day;
- the tutor's signed `review_due.json`, read strict (one bad row means "cannot check"), has a row
  for every module of the unit, written on the day (local date of `at`, Unix seconds), with no
  card due (`due_ms`, Unix ms) at the poll's moment;
- the ledger has no `review-clear:<day>:<unit>` row yet.

It runs inside `_theory_credit`'s fenced poll, so the lock's poll and the one-minute harvester
both mint it, even when the minute pool cannot be read. "Cannot check" mints nothing and logs a
warning.

## Why no "newer than the last review minute" check

Due times are absolute. An older signed file put back lists the same or earlier due times, so it
reads more cards due, never fewer, and "written on the day" stops yesterday's clear paying today.
A check that the due row is newer than the day's last review minute would refuse real clears: on
2026-11-24 the last graded card was 18:31:07 UTC and the last minute row ended 18:34:38 UTC.

## Isolation

`_review_due` (which lock rows to show) stays display-only and banned from deciders. The parser
both use is `_review_due_rows`; `_review_clear` and `_review_clear_repair` are listed deciders in
`test_display_only_imports.py`, whose closure must never reach `_review_due`.

## The 2026-11-24 repair (`--repair-review-clear`)

Hard-wired to 2026-11-24 and `prefix-sums`. It mints through the same entry builder only when:
the day's signed review rows of the unit exist, `charge:2026-11-24` exists, and the unit's newest
signed due row was written after the day ended with every card due after it. A rerun prints
`already minted` and writes nothing; a refusal exits 1. Days after the fix use only the live rule.
