# A restart keeps study mode (2026-11-22)

Follow-up to `DOCS-incident-2026-08-05.md` (study mode).

kuhy's rule: restarting the unit changes nothing. Before this, SIGTERM ran
`on_close`, which ended study and re-locked, and the new process armed fully
LOCKED with the grab, so a restart mid-solve took the browser's keyboard away.

`_study_restart.py` keeps one runtime file, `$XDG_RUNTIME_DIR/leetcode-guard/study.json`
(`{"day": "<date>"}`). **Never ledger state, never under `~/.local/share`**: a
study flag in the ledger is the deferral shape that bought free days.

| Event | Marker |
|---|---|
| Open or learn succeeds (`StudyMixin.enter_study`, after the spawn) | written |
| "Back to lock", or a solve that clears the day (`_end_study`) | removed |
| `on_close` / SIGTERM (`wind_down_study`) | kept; nothing is re-locked or grabbed on the way out |
| failed spawn rollback, demo lock, evening lock | never written |

`_cli._run_lock` reads it last: after `decide_today`, the morning-session, X-wait,
queue and lockdown deferrals and seeding, only for a production non-evening
run. A valid marker arms the lock WITHOUT the grab (`GuardSeams.resume_study`,
`arm_input`: surfaces built, step-back watch started via the adapter) and
`resume_study` enters study through the ordinary `enter_study` (strip, polling,
VT as usual; the spawn is a no-op). If study cannot be entered, `grab_input()`
is called: the fallback is the full LOCKED lock. The grab is never taken on a
resume: 0 of 123 50 ms samples (SIGTERM to 3 s after the successor is up).

Fail closed: no marker, an unreadable or malformed one, one for another day, or
no absolute `XDG_RUNTIME_DIR` means the lock stays LOCKED (a warning says why,
except for "no marker"). A forged marker gains nothing: study is one click away
at t=0, and nothing here decides, charges, credits or settles a day. The elapsed
clock restarts at 0 after a resume.

Proof: `leetcode_guard/tests/test_study_marker.py`, `test_study_restart.py`,
`test_cli_restart.py`, and on a real X server `python3 -m scripts.verify_restart_study`
(four lock processes, SIGTERM like systemd, `holds_grab()` after the restart and
after a recovery tick; control without a marker holds the grab).
