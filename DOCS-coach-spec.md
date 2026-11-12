# Requirements-first LeetCode coach (shipped spec)

Spec agreed 2026-10-23 (kuhy typed `override` on round 2, so every ➡️ below is
the decision). Source note: todo backlog "leetcode: build a tool that coaches me
to derive solutions myself (requirements-first)".

## Goal

Drive the 4-step method instead of ad-hoc hints: (1) read the constraint as a
design rule, (2) write the requirement list as *properties* before naming any
operation/structure, (3) search a toolbox of operations by those properties,
(4) post-mortem: write the requirement list (not code), reverse-engineer each
hint, turn toolbox entries into Anki property cards.

## Decisions

1. **Location.** Move `~/.claude/skills/leetcode/` into this repo as top-level
   package `leetcode_coach/` (SKILL.md lives inside it). `~/.claude/skills/leetcode`
   becomes a symlink to it (canary 2026-10-23: symlinked skill dirs DO load).
   `~/.local/bin/leetcode` repointed. `install.sh` creates both symlinks.
2. **Hooks.** Detector logic of `~/.claude/hooks/leetcode_no_solution_stop.py`
   (+ model gate, URL hook logic where Python) moves into `leetcode_coach/`;
   the files in `~/.claude/hooks` become ≤3-line shims so `settings.json` is
   unchanged. Fix every other `skills/leetcode` reference
   (`status_tag_stop.py`, `~/.claude/scripts/tests/test_leetcode_url_hooks.py`,
   `test_status_tag_stop.py`).
3. **Repo standards apply** to moved code: 250-line cap, 100% branch coverage,
   ruff ALL, mypy strict, pylint all, no `noqa`/`type: ignore`. Add
   `leetcode_coach*` to setuptools include and coverage source. Every
   print-driven module gets a `T201` per-file ignore IN THE SAME COMMIT, and
   its tests assert on stdout.
4. **Phase gate is mechanical, in the REPL** (Claude path and `--local` path).
   Requirement list is a message starting `req:`. While no accepted req list
   exists, a block classified as code is refused locally and never reaches the
   coach model. TUI: prompt-only (SKILL.md rule).
5. **Classifier + toolbox check = haiku**, separate `claude -p --model haiku`
   call; coaching stays sonnet. Haiku unavailable / usage limit → Ollama
   (`qwen3:30b-a3b-instruct-2507`, existing local backend). Neither answers →
   **fail OPEN** (kuhy continues), logged `req_check: unverified`.
   The checker names only *missing properties* from the toolbox property
   vocabulary, never an entry name.
6. **Incomplete req list blocks code** until it passes; after the 3rd revision
   code is accepted anyway, logged `req_incomplete`.
7. **Leak bounce.** Stop-hook detector also bounces, before the first `code`
   event, any reply naming a toolbox entry (name or aliases, e.g. XOR, `^`,
   "hash map") — EXCEPT names kuhy has already typed in the session (else the
   reply to "is it XOR?" can never be rewritten and loops). Test that case.
8. **Session log.** JSONL per problem:
   `~/.local/share/leetcode-coach/sessions/<date>-<slug>.jsonl`, events
   `req`, `req_check`, `code`, `rung`, `reveal`, `postmortem`, `retest`.
   Coach emits a trailing `<!-- rung:H0|H1|H2|H3 -->` marker; REPL logs and
   strips it. `leetcode report` prints per problem: req-before-code y/n,
   highest rung, reveal y/n, req_check verdicts.
9. **Toolbox** `leetcode_coach/toolbox.json`: ~20 entries, each = name, aliases,
   properties (from a fixed vocabulary). Covers all seeded clusters. kuhy
   reviews it before the first real session (workflow step 5).
10. **Clusters** `leetcode_coach/clusters.json`, seeded:
    bit-cancellation [268, 260, 169, 137], two-pointers [167, 15, 11, 42],
    sliding-window [3, 424, 567, 76], prefix-sum-hash [560, 523, 974, 525],
    monotonic-stack [739, 496, 503, 84], intervals [56, 57, 435, 452].
    `leetcode --cluster <name>` serves due re-tests first, then the next
    problem without a `code` event, skipping problems Accepted on LeetCode via
    `leetcode_guard._live_solved` (fail open if silent). Progress persists.
11. **Post-mortem cards**: property→operation fronts only, via the existing
    card builder, deck "LeetCode". An operation kuhy names that is not in the
    toolbox is appended to `toolbox.json` only after kuhy confirms its
    properties.
12. **Cold re-test** at +3 and +10 days after solve: fresh session, no
    history, no old code, req-first as usual. Judged by running the
    statement's examples locally with `node` — coach tells kuhy NOT to submit
    (a resubmission mints a gate credit: `_harvest.py` dedupes by submission
    id). `leetcode due` lists them. Not shown in the lock's suggestion list.
13. **Never** print a solution or pasteable line before `reveal`.

## Build done (scripted)

E2E against a fake claude binary (`LEETCODE_CLAUDE_BIN`) + fake ollama:
code refused before `req:`; incomplete list refused, accepted on 3rd
revision; checker down → fail open + `unverified` logged; leaking reply
bounced, kuhy-typed name not bounced; log shows req→code order; `leetcode
report` rows correct; `leetcode due` lists a +3-day re-test; `--cluster`
skips an Accepted problem. Full suite, coverage 100%, ruff/mypy/pylint clean.
`~/.claude/scripts/tests` still green after the move.

## kuhy's done (human, ≥2 days)

Solves ≥3 of 268/260/169/137 with 0 hints above H1, req list before first code
line in every log; `leetcode_no_solution_stop.py` never fires.

Coach sign-off: done (kuhy confirmed 2026-11-12: toolbox.json and
answer_key.json reviewed, ≥3 of the four solved over ≥2 days within H1, live
Coach tab run on desktop and phone).
