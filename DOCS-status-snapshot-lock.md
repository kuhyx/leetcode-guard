# `status.lock`: the rows the PC lock shows

The phone's Status tab lists exactly what the lock lists. `status.suggestions`
is the plain ranked pool (no unit filter, no easy-only, no review row) and
stays only for older app builds; new code reads `status.lock`.

```json
"lock": {
  "unpaid": true,
  "unit": "prefix-sums",
  "phase": "solve",
  "learn_route": null,
  "rows": [
    {"kind": "problem", "title": "Running Sum of 1d Array", "difficulty": "Easy",
     "url": "https://leetcode.com/problems/running-sum-of-1d-array/"},
    {"kind": "review", "count": 3,
     "route": "/review/leetcode-easy-algorithms-in-typescript/prefix-sums"}
  ]
}
```

- `unpaid`: today still needs credits (`needed > 0` and not `charged_today`).
  A day the balance already covers, and a free, sick or not-started day, is
  `false`.
- `unit`: `""` with no unit. `phase`: `theory`, `solve` or `none`.
- `learn_route`: THEORY only, the route the lock's learn button opens:
  `/learn/<subject>/<module>`, or `/plan/<subject>` while the module has no
  lessons. `null` otherwise.
- `rows`: in the lock's order. A `review` row appears alone, in place of the
  SOLVE rows, when tutor cards of the unit are due (review first).

**One code path.** `_snapshot_lock` builds the block through
`_viewmodel.lock_rows`, the function `build_viewmodel` paints the lock from,
over the same `ViewSource` inputs: the phase from `_status_unit.gather_unit`,
due cards from `_review_due` (due with no tutor launcher counts as "cannot
check", as on the lock), the pool from the cache with `post=None`.
`test_snapshot_lock.py` holds both side by side.

**Two known gaps.** The snapshot has no LeetCode probe and never fetches, so
solved slugs come from the ledger only (the lock also adds its probe's recent
submissions), and the order is the cached ranking, not the one the lock
live-verified when it opened.

## Where a tap goes on the phone (2026-11-27)

- **Tutor rows** (learn, review) go to `com.kuhy.tutor` by explicit package
  through MainActivity's `com.kuhy.leetcode_guard/open` channel. A phone
  slot's test build of the tutor claims `kuhytutor://` too, and the plain
  scheme intent raised a chooser.
- **Problem rows** open `LeetcodeView`, a WebView inside the guard app. At home
  the focus policy hides every browser and Play, and the LeetCode app
  (`com.leetcode.android`, day-whitelisted) stops at its PairIP licence check
  without Play, the same failure as infakt (phone-focus-mode
  `docs/DOCS-policy-play-store.md`). The app also claims only `leetcode://`,
  never `https://leetcode.com`. kuhy chose the in-app view over showing Play at
  home. The page may move only to https `leetcode.com` and its subdomains
  (`isLeetcodePage`); frames load freely (Cloudflare's check). Google and
  GitHub sign-in leave leetcode.com, so sign in with a LeetCode password.
- A link nothing takes turns the row's open mark into a red `link_off`, never a
  silent no-op.
