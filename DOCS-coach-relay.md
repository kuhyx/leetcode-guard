# Coach relay contract (v1): desktop + phone -> PC coach backend

Binding for **P** (Python relay + backend: `leetcode_coach/relay/`, unit, `install.sh`, `session_log` / `_coach_log` /
`phase` / snapshot changes) and **F** (Flutter: Coach tab UI, `coach.dart`, the RTDB client and the wrapper's `/coach/*`
proxy in `app/lib/desktop/`). Spec: `TODO-coach-ui.md`. Modelled on `~/src/tutor/DOCS-contract.md` §4-5; deviations in
§8. Change this file first, then code. Times are unix **ms**.

## 1. Transport

One process, `leetcode-coach-relay.service`, owns every coach session and feeds both inputs into **one serial queue**.
**Desktop:** browser -> wrapper `127.0.0.1:8776` (same origin as the web build) -> relay `127.0.0.1:8777`, a loopback
HTTP API on stdlib `ThreadingHTTPServer` (like `_web_server.py`). The wrapper forwards `/coach/*` verbatim (method,
path, query, body <= 16 KiB) and nothing else; relay unreachable -> it answers
`502 {"ok":false,"code":"relay_down","error":"coach service not running"}`. The browser never talks to 8777 itself.
**Phone:** Firebase RTDB REST under `leetcode-guard/coach/`; the phone PUTs requests, the relay watches them over SSE.

| RTDB node | Shape | Writer |
|---|---|---|
| `heartbeat` | object `{"beat":{".sv":"timestamp"},"started":ms,"state_rev":n,"busy":rid?,"version":1}` (`busy` absent = idle) | relay, every 30 s and on every `state_rev` move |
| `state` | JSON **string** leaf: the §3 state | relay, on change |
| `chat/{m0001}` | object `{"role","kind","text","at"}`, no empty fields | relay, append-only; cleared at `session_start` |
| `requests/{rid}/req` | object (below) | phone only |
| `requests/{rid}/result` | JSON **string** leaf: the §2 result | relay only |

`state` and `result` are string leaves for the same reason `leetcode-guard/status` is: RTDB drops `null`, `[]` and `{}`.
The relay serves the desktop API below, and the wrapper proxies it under the same paths.

| Method, path | Answer |
|---|---|
| `POST /coach/requests` `{"rid","kind","dev","body"}` | `202 {"rid"}`; `200 <result>` if the rid is already done; `400` bad rid/JSON; `413` > 16 KiB; `415` not `application/json` |
| `GET /coach/requests/{rid}` | `200 {"result": <result> \| null}`; `404` unknown rid |
| `GET /coach/heartbeat` · `GET /coach/state` | the heartbeat object (`beat` resolved to ms) · the §3 state |
| `GET /coach/chat?after=m0012` | `{"m0013":{...},...}` (no `after` = all) |

**Requests.** `rid` = ULID (26 Crockford chars) made by the client. Phone `req`:
`{"kind":"chat","dev":"<uuid4>","created":{".sv":"timestamp"},"body":{...}}`; the desktop omits `created` (the relay
stamps receipt). `dev` = the app's persisted per-install uuid4. After a network error, re-PUT the same `req` under the
same rid. **Ordering:** FIFO by arrival (an RTDB batch, at startup or rescan, in rid key order); one request runs at a
time and none overtakes an earlier one.

**Rate (<= 1 request / 3 s), global across both paths.** The relay *starts* at most one request every 3 s; the rest
wait in the queue. A request arriving while 5 are already queued is answered `rate_limited` and never runs. F disables
Send / Grade / Hint / Reveal / Run while its request is in flight and for 3 s after.

**Awaiting a reply: both paths poll** (F needs no streaming code). Phone: GET `requests/{rid}/result` every 2 s;
desktop: GET `/coach/requests/{rid}` every 1 s. `heartbeat.busy == rid` = "working", else "queued". No result after
**300 s** -> "No reply from PC, send again", which resends the SAME rid (the done-map re-answers a finished rid, never
re-runs it). `retry:true` errors are resent by the user as a NEW rid.

**Relay side.** Streams `requests` over SSE like tutor's `sse.py` (`Accept: text/event-stream`, reconnect with 1-30 s
backoff, fresh token on `auth_revoked`, `cancel` fatal); rescans every 60 s and at startup. Done-map
`~/.local/share/leetcode-coach/relay/requests_done.jsonl` (30 d): a rid found there gets its stored result re-PUT.
Cleanup: DELETE `requests/{rid}` 24 h after its result (desktop results: forgotten after 24 h). Caps: coach turn
(`claude -p`) 240 s; grader 50 s on haiku, then Ollama; whole request 280 s, then `model_error`.

**PC offline.** The phone polls `heartbeat` every 5 s while the Coach tab is visible with a live session, every 30 s
while visible otherwise, never in the background. Offline = `phone_now - beat > 120 s` (spec: 2 min): F greys the
session controls and keeps the last `state`. Desktop offline = `relay_down`; F shows
`systemctl --user start leetcode-coach-relay`. RTDB / Firebase down: the relay logs why, keeps serving the desktop and
retries with backoff; it never exits over the network.

## 2. Request kinds (the only seven; spec decision 7)

Result (both paths): `{"ok":true,"at":ms,"state_rev":n,"data":{...}}` or
`{"ok":false,"at":ms,"code":"...","error":"<shown to kuhy>","retry":bool,...extra}`. `session` is a sid
`YYYYMMDD-HHMMSS-xxxx` (4 hex). Every kind except `session_start` needs the live sid.

| kind | body | data |
|---|---|---|
| `session_start` | `{"slug":"missing-number"}` | `{"session":sid,"msg":"m0001"}` (the coach's opener) |
| `session_end` | `{"session"}` | `{}`; logs `session_end` reason `ended` |
| `chat` | `{"session","text"}` | `{"msg":"m0007"}` (the coach reply's key) |
| `grade_step` | `{"session","step":1\|2\|3\|5,"answer":str}`; step 3: `{"session","step":3,"picks":[entry names]}`; force: `{"session","step":n,"force":true}` | `{"step","grade":"pass"\|"partial"\|"fail","feedback","attempt":n,"can_force":bool,"via","next_step":n\|null}`; force -> `{"step","forced":true,"next_step"}`; a step-5 pass adds `"cards":{"built":n,"deck":"LeetCode","error":str\|null}` |
| `hint` | `{"session"}` | `{"msg","rung":"H0".."H3"\|null}` |
| `reveal` | `{"session"}` | `{"msg"}`; ends the session, reason `reveal` |
| `run_code` | `{"session","code"}` (JavaScript) | `{"examples":[{"n":1,"ok":bool,"got":"3","expected":"3"}],"error":null\|"timeout"\|"node_missing"\|"no_examples"\|"syntax"}` |

**Errors:** `bad_request` (unknown kind, bad id, type or size); `rate_limited` (`retry:true`, `retry_after_ms`);
`session_live` (end it first); `not_live` (sid is not the live one); `no_answer_key` (slug not in `answer_key.json`);
`step_locked`; `step_done`; `cannot_force` (< 3 failed tries, or step 4); `phase_locked` (code before step 2 is passed
or forced; `note` = the phase gate's line); `model_error` (`retry:true`); `claude_unavailable` (`reason`,
`resets_at`); `worker_error` (traceback in the journal only). `chat` text exactly `reveal` / `hint` is that kind.

**State machine.** Steps 1 constraint, 2 requirements, 3 toolbox, 4 implement, 5 postmortem; each
`locked -> open -> passed | forced`. `session_start` opens step 1; passing or forcing step n opens n+1. A `partial` /
`fail` keeps the step open and adds 1 to `attempts` (retries unlimited); at `attempts >= 3` with no pass `can_force`
is true, and forcing logs `grade` with `forced:true`. **Step 4 is never graded or forced**: it passes only on a
detected Accepted (§3); its other exits are `reveal` and `session_end`. A step-5 pass builds the cards and ends the
session (`done`). An ended session stays in `state` (read-only, `ended` set) until the next `session_start`; every
other kind then answers `not_live`. One live session at a time.

**Grading.**
1. Constraint: haiku -> Ollama, against `answer_key.json` `design_rule`.
2. Requirements: the relay prefixes `req:` if missing and runs `PhaseGate.screen`, which logs `req` + `req_check` as
   the CLI does. `pass` -> pass; `incomplete` -> partial (feedback = missing properties); `unverified` -> pass,
   `via:"unverified"` (fail open, as `req_state`). `fail` = the text reads as code (`regex_verdict`) or names a toolbox
   entry (`leak.leaked_names`), logged as `grade` only, never `req_check`. Attempts = `req_state().tries` + step-2
   `fail` grades, so CLI and app count one file alike. `phase.req_state` must treat a step-2 `grade` with
   `forced:true` as open, or a forced step 2 still refuses code.
3. Toolbox: mechanical, no model. Key entries `K`, picks `P`: pass = `K ⊆ P` and `|P \ K| <= 1`; partial = `P ∩ K`
   non-empty; fail otherwise. Feedback = properties of `K` no pick has, never an entry name.
5. Postmortem: haiku -> Ollama, against `design_rule` + `key_requirements`. A pass runs the existing card builder
   (logs `postmortem`); a card failure only fills `cards.error`.

Grader down -> `pass`, `via:"unverified"` (F shows "not checked"); `via` is `haiku|ollama|unverified|toolbox|accepted`.
Until the first `code` event (the coach replies' rule), feedback passes `leak.leaked_names(feedback, kuhy's texts,
toolbox)`; a leaking one becomes the plain missing-property list. The answer key never appears in `state`, `chat`, a
result or the log.

**Chat.** `session_start` sends `/leetcode <slug>` first, as the REPL does, so `stop_gate` arms; then
`claude -p --resume` on sonnet. Every call gets an explicit env `LEETCODE_COACH_LOG=<this session's log>`
(`claude_cli.ask` gains `env`); P builds `PhaseGate(log, ...)` directly, never `PhaseGate.open` (it writes global
`os.environ`). Usage limit -> continue per turn on the local model with the history, as `run_claude` hands over. Grades
reach the coach as a prefix on its next turn (`[app: step 1 graded pass on try 2; step 2 open]`, no extra model call)
and show in chat at once as a `system` message. Code in `chat` before step 2 is passed or forced is refused by
`PhaseGate.screen` -> `phase_locked` + a `system` / `refused` chat line. Message kinds
`chat|hint|reveal|grade|accepted|refused|run`; roles `kuhy|coach|system`.

**Run code** (decision 8): allowed once step 2 is passed or forced; logs `code` with `via:"run"`. `node` with a fixed
argv, never a shell: `--permission` (read access to its temp dir only), `--max-old-space-size=128`, 5 s and 64 KiB
output per run, against the statement's examples. `got` / `expected` are printed values, never stack traces.

## 3. State (`GET /coach/state` = decoded RTDB `state`)

```json
{"schema":1,"rev":12,"step":2,"rung":"H1","revealed":false,"chat_count":9,
 "session":{"id":"20261023-170448-5b71","slug":"missing-number","title":"Missing Number","cluster":"bit-cancellation",
   "url":"https://leetcode.com/problems/missing-number/","started":1792771488000,"ended":null,"end_reason":null},
 "steps":[{"n":1,"name":"constraint","status":"passed","attempts":2,"can_force":false,
           "last":{"grade":"pass","feedback":"...","via":"haiku","at":1792771600000}},
          {"n":2,"name":"requirements","status":"open","attempts":1,"can_force":false,"last":{"...":"..."}},
          {"n":3,"name":"toolbox","status":"locked","attempts":0,"can_force":false,"last":null},
          {"n":4,"name":"implement","status":"locked","probe":null,"probed_at":null},
          {"n":5,"name":"postmortem","status":"locked","attempts":0,"can_force":false,"last":null}],
 "toolbox":[{"name":"...","properties":["..."]}]}
```

No session yet: `session` and `step` are `null`, `steps` is `[]`. `end_reason`: `done|reveal|ended`. `toolbox` is
present only while step 3 is open (every entry's name + properties, never which are correct). `rev` (=
`heartbeat.state_rev`) moves on every change; F then refetches `state`, and `chat` after its last key.

**Accepted (step 4).** While step 4 is open the relay calls `_submissions.fetch_recent_ac` (`post` from
`_settings.build_client`: the harvester's read-only probe) at most **once a minute**, since LeetCode answers a rate
limit like a dead session. `probe` is three-valued: `accepted` (a row for the slug with timestamp >= `session.started`:
log a step-4 `grade` `pass` `via:"accepted"`, add a `system` / `accepted` chat line, open step 5, bump `rev`; the UI sees
it within one heartbeat poll), `not_yet`, or `unknown` (probe unusable: F shows "could not check", never "not yet").
The probe mints nothing; crediting stays the harvester's job.

## 4. Limits and auth

**Limits.** Each text field (`text`, `answer`, `code`) <= **8192 UTF-8 bytes**; `picks` <= 30 names of <= 64 chars; a
whole `req` <= 16 KiB; slug `[a-z0-9]+(-[a-z0-9]+)*` <= 100 chars. Ids are regex-checked before any path is built from
them; unknown fields are dropped. A kind outside the seven is never run: warning logged, answered `bad_request`. An
invalid rid gets no result.

**No path to the ledger.** From `leetcode_guard`, `leetcode_coach.relay` imports only `_submissions`, `_queries`,
`_settings` (+ `_auth`, `_constants`, `_leetcode`, `_throttle`) and `_snapshot_auth`. `test_relay_boundary.py` walks
the import closure (AST) and fails on `_ledger*`, `_balance`, `_debt`, `_harvest*`, `_gate*`, `_sync*`, `_lock*`,
`_breakglass`, `_escape*`, `_snapshot_push`. The E2E asserts `~/.local/share/leetcode_guard/` is byte-identical after
a full session. No route takes a path, command or URL; the only subprocesses are `claude` and `node` with fixed argv
(Ollama is HTTP).

**Desktop auth: loopback only.** The relay binds `127.0.0.1`, refuses a `Host` other than `127.0.0.1:8777` /
`localhost:8777` (DNS rebinding) and requires `application/json` on POST, so a cross-origin POST needs a preflight
that is never granted (`/open`'s rule). The wrapper refuses an `Origin` other than its own.

**Phone auth.** RTDB rules give read/write only to the shared sync uid; the app's `expectedUid` guard (`kSyncUid`)
keeps the phone on that account. The relay cannot see who wrote a node: trust = "only that uid can write here". The
relay signs in as crdt_sync app `leetcode_coach_relay` (own `~/.config/leetcode_coach_relay/firebase_auth.json`) via
`_snapshot_auth.connect`, which heals from a sibling's session; never the snapshot pusher's cache (two refreshers on
one token file is what per-app caches prevent).

## 5. Session log (extends `session_log.py` / `_coach_log.py`; renames nothing)

Four new event names land in **one commit**, in `session_log.EVENTS`, `_coach_log.EVENTS` and
`_coach_log._well_formed` (shape rules below). Otherwise the every-minute push counts them as "skipped" and warns. The
same commit rewrites the `session_log` docstring's "never as a new event name" to "new names only together with the
reader".

| event | fields (all also carry `sid`; `cluster` passed explicitly, never via `os.environ`) | well-formed when |
|---|---|---|
| `session_start` | `source:"app"`, `transport:"desktop"\|"phone"`, `dev` | always |
| `grade` | `step` 1-5, `grade` pass/partial/fail, `attempt`, `forced`, `via`, `feedback` | `step` int in 1..5, `grade` in set |
| `chat` | `role` kuhy/coach, `kind` chat/hint/reveal, `text` | `role` in set |
| `session_end` | `reason` done/reveal/ended | `reason` in set |

Existing events are unchanged, plus `sid`: `req` + `req_check` (step 2, via `PhaseGate`), `code` (chat code,
`run_code`), `rung` (the coach's marker, incl. a Hint's reply), `reveal`, `postmortem` (the card builder). The file
stays `<date>-<slug>.jsonl`, dated at `session_start`, so one file can hold several sessions.

**Snapshot.** Each `coach.problems[]` row gains two optional fields (F parses missing or `null` as unknown, never 0):
`grades`, from the file's **latest** `session_start` onward, keyed `constraint`, `requirements`, `toolbox`,
`postmortem`, each `{"grade","attempts","forced","via"}|null` (last grade event of that step, count, any forced); and
`accepted` (step 4 passed in that session). A CLI-only file (no `session_start`) has `grades: null`,
`accepted: null`. `max_rung`, `revealed`, `req_check` keep their meaning for the history.

## 6. Systemd unit (`leetcode-coach-relay.service`, repo root, enabled by `install.sh`)

```ini
[Unit]
Description=LeetCode coach relay: app desktop (loopback :8777) + phone (RTDB)
Documentation=file://%h/src/leetcode-guard/DOCS-coach-relay.md

[Service]
Type=simple
# System python + user site-packages; no WorkingDirectory/PYTHONPATH/venv (CLAUDE.md).
# A user unit's PATH lacks ~/.local/bin: without it `claude` is missing, every turn an "outage".
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin
ExecStart=/usr/bin/python3 -m leetcode_coach.relay
# SIGTERM to the relay only (it drains the running request); spares the claude child (tutor).
KillMode=mixed
Restart=always
RestartSec=5s

[Install]
# Up from login (from boot under linger), like leetcode-guard-web.service; needs no X.
WantedBy=default.target
```

`install.sh` checks `/usr/bin/python3 -c 'import leetcode_coach.relay'`, then `systemctl --user enable --now`. The
live-session pointer (sid, log path, claude session id) is `~/.local/share/leetcode-coach/relay/live.json`; a restart
rebuilds state from the log.

## 7. Test seams and ownership

Seams: `LEETCODE_CLAUDE_BIN` (fake claude), `LEETCODE_COACH_RTDB_URL` (in-process fake RTDB, REST + SSE),
`LEETCODE_COACH_RELAY_PORT`, an injectable Accepted probe and clock: enough for the spec's scripted E2E on both paths.
**P** owns `leetcode_coach/`, `leetcode_guard/_coach_log.py` + snapshot fields, the unit, `install.sh`. **F** owns
`app/lib/desktop/wrapper_server.dart` (the proxy) and in `app/lib/src/` the `coach.dart` grades, the coach client
(RTDB + wrapper), and the Coach tab session UI with its offline and stalled states.

## 8. Deviations from tutor

1. **Desktop uses loopback HTTP, not RTDB.** The desktop never holds a Firebase credential (`sources.dart`).
2. **No claims, leases or ETags.** One relay per account means no race to settle; "working" comes from
   `heartbeat.busy`.
3. **One paced lane**, capped at 5 queued, instead of tutor's two lanes.
4. **Clients poll instead of streaming.** This app has no SSE code, and a result poll costs about 4 bytes.
5. **`state` and `result` are string leaves**, this repo's null-safe convention.
6. **PC offline compares `beat` with the phone clock at 2 min.** That is the spec's rule, and the status heartbeat
   already does the same at 10 min. Tutor uses 75 s of monotonic silence.
7. **Unknown kinds get `bad_request`.** "Dropped" means never run; the client is still told, so it stops waiting.
