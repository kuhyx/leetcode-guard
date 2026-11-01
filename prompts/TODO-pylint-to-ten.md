# Take pylint from 9.95 to 10.00

## what
`pre-commit run pylint --all-files --verbose` (the hook env, 2026-11-01) rates
the tree 9.95/10. The 2026-08 docstring, protected-access-in-tests and
booleaness work is done; about 35 findings remain, all in `leetcode_guard/`,
`leetcode_coach/` and `scripts/`. Do not touch `--fail-under=8.0`, the
pylint `disable` list, or the crdt-sync/gatelock/freedays pins.

## remaining (counts from the 2026-11-01 run)
- design (R09xx), 18: too-many-instance-attributes `_lock`, `_view`,
  `_projection`, `_status_full`, `_lock_deps`, `relay/phone`; too-many-arguments
  `_view`, `_harvest`, `_gate` (x2), `_viewmodel`; too-many-locals `_view`,
  `_projection`, `_gate`, `solved_today`; too-many-return-statements
  `_submissions`, `_leetcode`, `_cli`. Fix with dataclasses / helper
  extraction. Ask kuhy first for `_status.py`'s dataclass: its fields mirror the
  snapshot schema the app reads (`DOCS-status-snapshot.md`), so it is a
  contract change, not a refactor.
- protected-access in `scripts/screenshot_states.py` (9) and
  `scripts/verify_study_grab.py` (6): deliberate harnesses (CLAUDE.md). Needs
  kuhy's call: file-scoped `pylint: disable=protected-access` with the reason.
- `scripts/leetcode_guard_tray.py`: wrong-import-position (gi version pin
  must precede the import), consider-using-with; `scripts/verify_nudge_extension.py`:
  consider-using-with; duplicate-code `_pool_cache` / `_profile_cache` (3).

## done
`pre-commit run pylint --all-files --verbose` prints `rated at 10.00/10`;
`python3 -m pytest -n auto -q` keeps 100% branch coverage (1712 tests today).
Every suppression listed in the commit message with its reason.

## verify
The two commands above.

REMOVE ME AFTER FINISH
