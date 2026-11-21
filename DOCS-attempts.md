# Attempt log and the flag (stage 2)

The extension reports which problem tab is on screen. The log turns that into
"how long did this solve take"; a long solve of an already-taught unit is
**flagged** for review. All of it is display-only.

## Data flow

1. The extension (manifest 1.1.1) POSTs `{"slug", "tab"}` to
   `127.0.0.1:8782/beat` on load, on a route change, when the tab becomes
   visible, and once a minute while visible. A hidden tab sends nothing.
2. `leetcode-guard-web.service` (`_web_server`, status API on 8771) starts a
   second loopback listener, `_attempt_server`. It checks the origin (none, or
   `chrome-extension://`), the size (256 bytes), the slug (regex, and present in
   the cached pool) and the tab, then stores a beat stamped with the SERVER clock.
3. The one-minute harvester prints an `attempts:` line after `run_harvest`
   (`_attempt_line`). On the first sight of a solve it stores the unit's theory
   state. While a beat is under 2 minutes old it also fetches the public
   `recentSubmissionList` (20 rows, every status, no cookie) and merges the
   failed submissions. It never touches the ledger and cannot change the
   harvester's exit code.
4. `python3 -m leetcode_guard --flagged [--json]` and the read-only MCP tool
   `get_flagged` read the ledger and `attempts.json` and print the report.

Port 8782, not 8773: book-guard's desktop wrapper owns 8773.

## `attempts.json`

`<DATA_DIR>/attempts.json`, one record per local day and slug, kept 180 days:

```json
{"version": 1, "records": {"2026-11-21|two-sum": {
  "day": "2026-11-21", "slug": "two-sum",
  "beats": [[1795287000, "description"]],
  "submissions": {"123": {"status": "Wrong Answer", "at": 1795287100}},
  "theory_at_solve": "done"}}}
```

Two processes write it under an `flock` on `attempts.json.lock`: the web
service (beats) and the harvester (submissions, theory snapshot).

## Definitions

- **Solve**: the earliest credit of a slug. Its accept time is the credit's
  `submitted_at`. Later credits of the slug are repeats.
- **Active time**: the sum of the gaps of at most 5 minutes between beats of
  that slug, up to the accept time, across days.
- **Flagged**: active time over 20 minutes AND the unit's theory was `done` at
  solve time.
- **Unknown**: no beat before the accept. Never flagged, never in the share.

Flags are derived at read time. Only `theory_at_solve` is stored, once per
record, never overwritten ("a flag is fixed at solve time"). The report lists
flagged solves, measured solves of the last 28 days, unknown solves and the
share under 10 minutes (`null` with no data).

## How a flag clears (stage 3)

Only a finished review clears a flag. The coach (0.1.6, `/leetcode review`)
appends a `review` event to the problem's session log,
`~/.local/share/leetcode-coach/sessions/<date>-<slug>.jsonl`, once kuhy names
one cause: `statement`, `missing-idea`, `idea-to-code`, `debugging` or
`interruption`. A `missing-idea` review may also name the curriculum unit in
`module`; the guard ignores it.

`_coach_reviews.reviewed_slugs()` reads those logs and returns every slug with
such an event. `--flagged` and `get_flagged` pass that set as
`load_report(cleared=...)`, so a reviewed solve drops out of `flagged` and
stays in `measured`.

- A `review` with no cause, or a cause outside the five, clears nothing.
- A folder that cannot be listed means "could not check": a warning, nothing
  cleared, every flag stays. The command still prints and exits 0.
- A missing folder means no reviews yet: nothing cleared, no warning.
- An unreadable file or a torn line is skipped with a warning.

The log is plain unsigned JSONL, so editing it can only hide a row of a review
list; `_coach_reviews` is in the display-only import ban below.

A `skeleton` event (payload `unit`) means the coach showed kuhy a code
skeleton during that session. For the coach sign-off
(`scripts/verify_coach_signoff.py`) any `skeleton` event ranks above H1, so
the session does not count. The hint ladder itself stays H0-H3.

## Failure paths

| Failure | Result | Fails open? |
|---|---|---|
| Port 8782 taken | warning; status API keeps running | yes |
| Pool cache missing or unreadable | `/beat` answers 503, nothing stored | yes |
| Unknown slug, bad origin, bad body | 404 / 403 / 400 / 411 / 413 | yes, nothing stored |
| Lock not obtained in 2 s | write skipped, warning | yes |
| `attempts.json` corrupt | moved to `attempts.json.corrupt`, fresh file | yes |
| Fetch cannot check (HTTP 200, null payload) | `attempts: could not check`, nothing merged | yes |
| Theory reader or whole `attempts_line` raises | `unknown` snapshot / `unavailable (<type>)`, warning; harvest unaffected | yes |
| Coach log folder cannot be listed | warning, no flag cleared | no: flags stay |

Editing `attempts.json` can only add or remove a row in a review list.

## The import ban

The attempt modules (`_attempt_paths`, `_model`, `_store`, `_io`, `_server`,
`_queries`, plus `_attempts`, `_attempt_report` and `_coach_reviews`) must never be imported by
anything that decides, charges or credits; `tests/test_display_only_imports.py`
checks it transitively. `_attempt_line` is the one exception: `_harvest_run`
imports it lazily and fenced, and it never writes the ledger.

## Verify

```bash
python3 -m scripts.verify_heartbeat_extension   # real browser, mock leetcode.com, stub listener
python3 -m scripts.verify_flagged_replay        # real ledger credits, synthetic beats
python3 -m scripts.verify_recent_submissions    # live recentSubmissionList shape
```

The last check is also the `recent-submissions` hook (manual stage). It skips
loudly at exit 0 when LeetCode cannot be reached or answers "could not check".
A change to `extension/manifest.json` needs a Helium restart: a running browser
keeps the old manifest.
