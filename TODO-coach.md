# Human sign-off for the coach and its app UI

## what
The coach (`leetcode_coach/`, spec `DOCS-coach-spec.md`) and the Coach tab with
its relay (spec `DOCS-coach-ui-spec.md`) are built and tested. Three checks
only kuhy can make remain.

## done
1. kuhy has reviewed `leetcode_coach/toolbox.json` and
   `leetcode_coach/answer_key.json` (both LLM-generated; never displayed).
2. Over at least 2 days kuhy solves >=3 of 268/260/169/137 with no hint above
   H1 and the req list before the first code line; `leetcode report` shows it
   for each problem and `leetcode_no_solution_stop.py` never fires.
3. One live run of the guided Coach tab, on desktop and on the phone.

## verify
`leetcode report` for item 2; the Coach tab history for item 3.

## read first
- DOCS-coach-spec.md, DOCS-coach-ui-spec.md, DOCS-coach-relay.md

REMOVE ME AFTER FINISH
