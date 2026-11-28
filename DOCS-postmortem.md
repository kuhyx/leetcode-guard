# Post-mortem view (display-only)

The status app's fourth tab shows what the tutor learned from each finished
unit. Nothing in it decides, charges or credits anything.

## Where the data comes from

The tutor writes one report per finished unit at
`~/.local/share/tutor/postmortems/<subject>/<unit>.json`. Each report is a
signed document (`kind: "postmortem_report"`, an `hmac` over the rest made
with the fleet key) whose `revisions` each hold:

- `one_shot.post` / `one_shot.pre`: `[k, n]` problems solved in one shot
  after and before the unit's theory;
- `problems`: one row per solve (`tries`, `minutes` or null, `one_shot`,
  `phase` "pre"/"post", the model's `finding`, plus fields the view drops);
- `cards` with a `change` of `same`/`kept`/`edit`/`suspend`, `new_cards`, and
  `applied` (what the tutor really changed, incl. suspension reasons).

`leetcode_guard/_postmortem_view.py` reads every `<subject>/<unit>.json`
(never `dry/`, `failed/`, `tasks/`, `lessons.json`, `revisions.json`) through
`_tutor_read`, keeps the **highest `rev`** of each, and shapes it in
`_postmortem_rows.py`:

| Model field | From |
|---|---|
| `post`, `pre` | `one_shot`, `null` if not a `[k, n]` pair |
| `problems[]` | `slug`, `tries`, `minutes`, `one_shot`, `phase`, `finding` (400 chars) |
| `cards[]` `kind: new` | `new_cards[]`; finding = its `why` |
| `kind: edited` | `change == "edit"`; front = `new_front` |
| `kind: suspended` | `change == "suspend"`; finding = `applied.suspended[].reason` |
| `kind: kept` | `change == "kept"`; `used_by` = the one-shot solves that used it |

Unchanged (`same`) cards are not shown. Units come oldest first (latest
revision's `at`). A broken file is skipped with a warning; a missing dir
is `[]`, a known "no post-mortem yet".

The signature is **not verified**: it is display data, and that is exactly
why it is banned from every decider (`test_display_only_imports.py`).

## Where it is shown

- `GET http://127.0.0.1:8771/api/postmortems` (`_web_postmortems.py`):
  `{"postmortems": [...]}`, uncapped; `null` if reading raised.
- The status snapshot's `postmortems` key (`DOCS-status-snapshot.md`), capped
  at 32 KB and 60 units: over the budget, the oldest units lose `problems`
  and `cards` (become `null`), their rates always ship. Both the desktop and
  the phone read the snapshot, so the desktop wrapper needs no proxy.
- The app's tab (`app/lib/src/ui/postmortem_*.dart`) paints no words before a
  tap: a bar per unit (post-theory one-shot rate), a problem grid (tries,
  minutes, one-shot mark, pre/post mark) and card chips (new / edited /
  suspended / kept, each its own glyph). Tapping a bar, row or chip shows the
  unit, the problem's finding or the card's front and finding; a kept chip also
  lists `used_by`.

Fixture: `leetcode_guard/tests/postmortem_reports_2026-11-23.json` (built from
the tutor's real `prefix-sums` dry run); `app/test/fixtures/snapshot_postmortem.json`
is the exporter's output for it, pinned by `test_postmortem_view.py`.

## The running post-mortem (progress card)

A post-mortem is one ~11-minute model call, then card writes; nothing
showed it until the approval task was filed. The tutor now writes
`~/.local/share/tutor/postmortems/progress.json` at each stage
(`tutor/postmortem/progress.py`, tutor `DOCS-contract-postmortem.md`):
`state` running/done/failed, `stage` analysing → applying → saving,
`started_at`/`stage_at`/`finished_at` (unix s), `estimate_s` (median of the
last 5 runs, 660 s before the first), `summary` (applied counts) and `error`
(200 chars). With `TUTOR_NOTIFY=on` (set in `tutor.service`) start, end and
failure are also desktop bubbles.

`leetcode_guard/_postmortem_progress.py` shapes it into the snapshot's
`postmortem_progress` key: every key always present, `null` for a missing or
mistyped field, `null` section when there is no file or it is unreadable. It
holds no clock, so the per-minute push still deduplicates between stages; the
app computes elapsed time and the ETA (`started_at + estimate_s`). Unsigned,
so it is banned from every decider like the view.

The tab's top card (`app/lib/src/ui/postmortem_progress.dart`) shows while
running or failed, and for 6 h after done (`kShowDoneFor`): stage dots, an
elapsed/ETA bar ticking each second; a tap reveals the unit, the summary or
the error.
