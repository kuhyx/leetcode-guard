# Guided coaching UI + chat in the status app (shipped spec)

Spec agreed 2026-10-23 (kuhy: Q1 b, Q2 yes, Q5 a, rest as recommended; relay
modelled on ~/src/tutor, see its DOCS-relay.md).

## Goal

In the app's Coach tab kuhy picks a problem and is walked through it, graded at
each step, while chatting with the coach session:

1. **Constraint** (free text) → graded.
2. **Requirements** (property list) → graded by the existing toolbox checker
   (`leetcode_coach/req_check.py`).
3. **Toolbox** (pick entries from `toolbox.json`) → graded against the answer key.
4. **Implement** on LeetCode (Open button). The step completes when the
   harvester / live check sees an Accepted for the slug (≤ 1 min).
5. **Post-mortem** (free text) → graded, then property Anki cards are built
   (existing card builder).

## Decisions

1. **Platforms:** desktop app talks to its local wrapper; phone talks to the PC
   through Firebase RTDB, relayed by an always-on PC user service
   (`leetcode-coach-relay.service`, started at login) built the way tutor's
   relay is. PC heartbeat older than 2 min → phone shows "PC offline".
2. **Not read-only any more** (it never should have been): the app writes
   coaching session logs (answers, grades, hints, chat). It NEVER writes the
   gate ledger, credits, charges or unlocks; a credit still only comes from a
   LeetCode Accepted. A test proves no relay/wrapper route reaches ledger code.
3. **Gating:** a step must pass before the next opens; unlimited retries; after
   the 3rd failed try kuhy may continue, logged `forced`.
4. **Grade:** `pass` / `partial` / `fail` plus feedback that names what is
   missing as *properties*, never the answer. All grades stored per session and
   shown in Coach-tab history.
5. **Answer key:** `leetcode_coach/answer_key.json`, one entry per cluster
   problem (24): design rule, correct toolbox entries, key requirement(s).
   Generated once by LLM, reviewed by kuhy like the toolbox. Never displayed;
   grader feedback goes through the same leak check as coach replies.
6. **Chat = the coaching session** the CLI runs (sonnet, SKILL.md rules,
   no-solution Stop gate, haiku→Ollama fallbacks), one session per problem,
   visible during all 5 steps. Step grades are posted into it so the coach
   knows where kuhy is. A **Hint** button sends "hint" (rung logged, H0–H3);
   a **Reveal** button = typing `reveal` (ends the exercise, logged).
7. **Relay accepts only:** start session, end session, chat turn, grade step,
   hint, reveal, run code. Text ≤ 8 KB, ≤ 1 request / 3 s. Never runs a shell
   command from a request; anything else dropped with a warning.
8. **Pasted code:** JavaScript, run on the PC with `node` against the
   statement's examples; reply shows only "example N: got X, expected Y".
9. **CLI stays.** `leetcode` REPL and the app write the same session log, so
   `leetcode report` and the Coach tab see both.

## Done

Scripted E2E against a fake grader/claude: start Missing Number on desktop,
each graded step returns pass/partial/fail with feedback, the next step is
blocked until pass or the 3rd try, chat round-trips, Hint logs a rung, a
simulated Accepted unlocks the post-mortem within one poll, Coach history shows
the 4 grades and highest rung. Same flow through the RTDB relay with a fake
RTDB. Plus one live run by kuhy on desktop and phone. Python 100% branch
coverage, Flutter 100% of `lib/`, all linters clean.
