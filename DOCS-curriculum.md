# Curriculum order and the tutor reader

The lock's suggestion list is served in theory order, not acceptance order.
Rows of a block the tutor has not taught carry a pencil mark and sit below the
taught blocks. Both are display-only.

## Why

Acceptance order shuffled topics: on 2026-11-21, 7 of 19 coached problems
stalled on a missing idea. The list now walks 14 units, each a set of LeetCode
topic tags (`leetcode_guard/curriculum.json`, read by `_curriculum.py`).

## Order

`rank_pool(..., block=...)` in `_problem.py` sorts by difficulty, then block,
then acceptance (highest first). Within a block the old acceptance order holds.

- **Teaching order and claim order are two lists (stage 4, 2026-11-22).**
  `units` is the teaching order, smallest unit first by Easy problems
  (`prefix-sums` ... `scans`, kuhy's list). `claim_order` settles membership
  and keeps the 2026-11-21 order the counts were measured with. Applying
  "latest unit" to the teaching order instead put 664 Easy problems in
  `scans` and none in `prefix-sums`. Without `claim_order` the teaching order
  is used for both; a `claim_order` that does not list every id once refuses
  the whole file.
- **A problem belongs to the LATEST unit among its tags** (latest in `claim_order`). An `array` problem
  that also carries `bit-manipulation` waits for the bits block, so every idea
  it needs comes first.
- A tag no unit claims is ignored when another tag maps. A problem with no
  mapped tag sorts after every unit. Advanced tags (`rolling-hash`) stay
  unclaimed on purpose: an Easy with that tag is solvable without it.
- A problem with no tags (the JavaScript and pandas sets) goes to the unit
  marked `"untagged": true`.
- Taught blocks first, then waiting ones, each in curriculum order. Nothing is
  dropped: the lock must always offer something.

## Mapping a unit to the tutor

Add this to the unit's row in `curriculum.json`:

```json
"tutor": {"subject": "algo", "modules": ["bits"]}
```

The shipped file maps all 14 units (2026-11-21):

- the 12 algorithm units each map the same-named module of subject
  `leetcode-easy-algorithms-in-typescript`;
- `js-pandas` maps all four modules (`js-closures-timers`, `js-promises-arrays`,
  `pandas-select-filter-group`, `pandas-clean-reshape`) of
  `javascript-and-pandas-for-leetcode-easy`;
- `sql` maps all four modules (`sql-lessons`, `select-group-basics`,
  `clause-order-where-vs-having-and-left-join`, `date-format-codes-decimal-division-and`)
  of `mysql-8-for-timed-sql-coding-tests-joins-and`.

The two new subjects were still draft plans with no cards when mapped, so
every unit that uses them reads pending. A mapping needs a subject
and a non-empty module list, else the whole file is refused (see Failure).

## What "done" means

`_theory.py` only reads `<tutor dir>/subjects/<subject>/cards.json` and
`<tutor dir>/log.jsonl` (`TUTOR_DATA_DIR`, default `~/.local/share/tutor`).
A unit is done when every live (not suspended) card of each mapped module has a
`taught` event in the log. That is kuhy's choice (2026-11-21) over the tutor's
"mastered", which needs a Good review days later; it is why the reader uses the
event log, not the stored status. A module with no cards yet is pending.
An `untaught` row (the tutor appends one when kuhy un-ticks a card; measured 2026-11-21 in `tutor/fold.py` and `tutor/source.py`) takes that card back out until a later `taught` row, so rows apply in file order.

States: `NONE` (no mapping), `DONE`, `PENDING`, `UNKNOWN`. A pending or unknown
block gets the pencil glyph (`_glyphs.problem_mark`) ahead of the difficulty
mark, and the lower sort slot. `PoolResolution.blocks` carries the states to
`_viewmodel.build_problem_lines`; the status snapshot and MCP
`get_suggested_problems` return `unit` and `theory` per problem.

## Display-only, and what decides since stage 4

`_theory` reads files anyone can edit (`log.jsonl`, `cards.json`), so nothing
that decides may read it: editing JSON would steer a lock or a credit (the
`progress_cache.json` rule again). `tests/test_display_only_imports.py` bans
the gate, balance, debt, difficulty, ledger, harvest, phase and theory-credit
modules from reaching `_theory`, through any import chain. `_harvest_run`
pushes the status snapshot, so it gets the direct ban only. The `_lock*`,
`_cli*` and `_study*` modules get the direct ban too.

Since 2026-11-22 the ORDER and MAPPING are decider input: the theory-first
phase machine (`_phase.py`, `DOCS-theory-first.md`) walks the units in
teaching order and asks which modules each maps. `_curriculum` and the bounded
reader `_tutor_read` left the ban for that reason. "Theory done" there comes
only from the tutor's signed `module_state.json`, never from `_theory`.

## Failure

Every path fails open to the old acceptance order or to `UNKNOWN`, with a
WARNING, and none raises. `resolve_pool` runs with the instance lock held and
before any window opens, so a raise here is a lock that never arms.

- `curriculum.json` missing: the old acceptance order, silently.
- `curriculum.json` unreadable or malformed (bad shape, a tag or id claimed
  twice): the old order and a WARNING.
- A tutor file (log or cards) that is missing, unreadable (`PermissionError`),
  not a regular file (FIFO, socket, device, directory), over `MAX_TUTOR_FILE_BYTES`
  (32 MiB; the real log was 181 KB), not UTF-8, nested past the JSON recursion
  limit, not an object, or holding a card without a module: that subject reads
  `UNKNOWN`, shown as pending, never as taught. A file that is not regular or is
  too big is never opened (`_tutor_read.py`: `stat` first, then an `O_NONBLOCK`
  bounded read), so a FIFO cannot hang the arming run.
- A torn log line (a write cut mid-append, a split multibyte character, a stray
  byte, a line nested too deep) is skipped like malformed JSON and costs only
  itself: the other lines still count, with ONE warning per read.
- Anything else the theory reader does wrong: `_pool_resolve._blocks_or_none`
  catches `Exception` (not `BaseException`), logs one WARNING naming its type,
  and ranks in the old acceptance order.

The mark fails closed; the list fails open.

## Known limits

Theory state is read once per resolve. The pencil mark and the order refresh
at the next arm or `--status` call, not while a lock is up: teaching a module
in the tutor mid-lock changes nothing on the open window.

## Verify

1. Tests: `pytest leetcode_guard/tests/test_{curriculum,theory,theory_surface,theory_hostile,theory_files,display_only_imports}.py`.
2. Live shape of the tutor files: `python3 -m scripts.verify_theory_shape`. The
   tests build their tutor dir by hand, so a renamed event or moved file would
   leave them green while every block reads `UNKNOWN`. It skips loudly at exit 0
   when the tutor has no data.
3. Screenshots on a private `Xvfb :81` with `scripts/screenshot_lock.sh`, never
   on `:0`, with a scratch `HOME` and `XDG_RUNTIME_DIR`. The demo shows the
   curriculum order (`prefix-sums` first). The mark needs a scratch curriculum with a
   tutor mapping and a scratch tutor dir: point `_curriculum.CURRICULUM_FILE`
   and `_theory.TUTOR_DATA_DIR` at them (both are read at call time). Trim the
   scratch pool so pending rows fit in the 14 slots: with the full pool, taught
   Easy rows fill every slot and a pushed-down block never shows. That is the
   design, not a bug. `scripts/screenshot_states.py` ranks without a block, so
   it does not show the curriculum order.
