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
| `heartbeat` | object `{"beat":{".sv":"timestamp"},"started":ms,"state_rev":n,"busy":rid?,"version":1}` (`busy` absent = idle) | relay, every 30 s and on every `state_rev` or `busy` change |
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
(`claude -p`) 240 s; grader 50 s on haiku, then 200 s on Ollama; whole request 280 s, then `model_error` (a coach turn
gets what is left of the 280 s, at most 240 s).

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
`locked -> open -> passed | forced`, derived from the log's `grade` events (`relay/steps.py`). `session_start` opens
step 1; passing or forcing step n opens n+1. A `partial` / `fail` keeps the step open and adds 1 to `attempts`; at
`attempts >= 3` with no pass `can_force` is true. A force is its own `grade` event: `forced:true`, `grade`/`via` of the
last try, `attempt` = tries so far, `feedback:""`. `next_step` = the step open after this request (`n` again after a
`partial`/`fail`, `null` once the session ended). **Step 4 is never graded or forced**: it passes only on a detected
Accepted (§3). A step-5 pass builds the cards and ends the session (`done`); forcing step 5 ends it `done` without
cards. An ended session stays in `state` (read-only, `ended` set, `step:null`) until the next `session_start`; every
other kind then answers `not_live`. One live session at a time. A `reveal` whose coach turn fails leaves it live.

**Grading.** Every graded try, any step, is one `grade` event (`at` in ms rides along on `grade` and `chat`).
1. Constraint: haiku -> Ollama, against `answer_key.json` `design_rule`.
2. Requirements: `fail` = the text (minus a `req:` prefix) reads as code (`regex_verdict`) or names a toolbox entry
   (`leak.leaked_names`): no model, `via:"toolbox"`, no `req_check`. Otherwise the relay prefixes `req:` if missing and
   runs `PhaseGate.screen` (logs `req` + `req_check` as the CLI does): `pass` -> pass; `incomplete` -> partial
   (feedback = missing properties); `unverified` -> pass, `via:"unverified"`. Attempts = `req_state().tries` + step-2
   `fail` grades, so CLI and app count one file alike; `phase.req_state` treats a forced step-2 `grade` as open.
3. Toolbox: mechanical, `via:"toolbox"`. Key entries `K`, alternatives `A` (`also_accepted`), picks `P`; a pick that is
   no toolbox name or alias is `bad_request`. A key entry counts when picked, or when it is a combined `x + y` entry
   and every part is picked (a part resolves by name/alias, ignoring case and a plural `s`: "prefix sum" -> "prefix
   sums"; a part naming no entry, like "merge", means only the combined entry counts). Each alternative picked stands
   in for one key entry not covered. pass = every key entry covered or stood in for, and at most one pick outside
   `K`, its parts and `A`; partial = some key entry, part or alternative picked; fail otherwise. Feedback = properties
   of the uncovered key entries no pick has (`phase.property_line`), never an entry name.
5. Postmortem: haiku -> Ollama, against `design_rule` + `key_requirements`. A pass builds the property cards for the
   key's entries in-process (`toolbox_cards` -> `card_rules` -> `make_cards.deliver`; the relay logs `postmortem`
   itself, since `make_cards.main` finds the log through `os.environ`); a card failure only fills `cards.error`.

Grader down -> `pass`, `via:"unverified"` (F shows "not checked"); `via` is `haiku|ollama|unverified|toolbox|accepted`.
Model feedback naming a toolbox entry kuhy has not (until the first `code`, `leak.leaked_names`) or repeating 5
words of the key becomes the plain missing-property line. The key never appears in `state`, `chat`, a result or a log.

**Chat.** `session_start` sends `/leetcode <slug>` first, as the REPL does, so `stop_gate` arms; then
`claude -p --resume` on sonnet. Every call gets an explicit env `LEETCODE_COACH_LOG=<this session's log>`
(`claude_cli.ask` gains `env`); P builds `PhaseGate(log, ...)` directly, never `PhaseGate.open`. The statement is
fetched in-process (`fetch_problem.fetch`), never by a subprocess. Usage limit -> the session continues on the local
model with the history and stays there, as `run_claude` hands over. Grades reach the coach as a prefix on its next
turn (`[app: step 1 graded pass on try 2; step 2 open]`, no extra model call) and show in chat at once as a `system`
message; `reveal` goes out bare (the Stop gate lifts only on a message that is exactly `reveal`). Code in `chat` (or
`run_code`) is refused while the relay's own step-2 status is not `passed`/`forced`, checked BEFORE `PhaseGate.screen`
-> `phase_locked` + a `system` / `refused` chat line (kuhy's line still shows). Message kinds
`chat|hint|reveal|grade|accepted|refused|run`; roles `kuhy|coach|system`.

**Run code** (decision 8): allowed once step 2 is passed or forced; logs `code` with `via:"run"`. `node` with a fixed
argv, never a shell: `--permission --allow-fs-read=<tmp>` (its temp dir only), `--max-old-space-size=128`, one run of
5 s and 64 KiB for all examples, against the examples above the statement's first `## ` heading. `got` / `expected` are
canonical JSON; a throw shows `error: <ErrorName>`, never a message or stack trace.

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

**Accepted (step 4).** While step 4 is open the relay calls `fetch_recent_ac(client.post, client.username)` with
`client = _settings.build_client()` (the harvester's read-only probe) at most **once a minute**, since LeetCode answers
a rate limit like a dead session. `probe` is three-valued: `accepted` (a row for the slug with
`timestamp` (unix **seconds**) `* 1000 >= session.started`:
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
| `session_start` | `source:"app"`, `transport:"desktop"\|"phone"`, `dev`, `slug`, `at` | always |
| `grade` | `step` 1-5, `grade` pass/partial/fail, `attempt`, `forced`, `via`, `feedback` | `step` int in 1..5, `grade` in set |
| `chat` | `role` kuhy/coach, `kind` chat/hint/reveal, `text` | `role` in set |
| `session_end` | `reason` done/reveal/ended | `reason` in set |

Existing events are unchanged (no `sid`; sessions split at `session_start`): `req` + `req_check` (step 2, via `PhaseGate`), `code` (chat code,
`run_code`), `rung` (the coach's marker, incl. a Hint's reply), `reveal`, `postmortem` (the card builder). The file
stays `<date>-<slug>.jsonl`, dated at `session_start`, so one file can hold several sessions.

**Snapshot.** Each `coach.problems[]` row gains two optional fields (F parses missing or `null` as unknown, never 0):
`grades`, from the file's **latest** `session_start` onward, keyed `constraint`, `requirements`, `toolbox`,
`postmortem`, each `{"grade","attempts","forced","via"}|null` (last try's grade/via, tries, any forced); and
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

`install.sh` checks `/usr/bin/python3 -c 'import leetcode_coach.relay'`, then `enable` + `restart` (new code on reinstall). The
live-session pointer (sid, log path, claude session id) is `~/.local/share/leetcode-coach/relay/live.json`; a restart
rebuilds state from the log.

## 7. Test seams and ownership

Seams: `LEETCODE_CLAUDE_BIN`, `LEETCODE_COACH_RTDB_URL` (fake RTDB), `LEETCODE_COACH_RELAY_PORT` / `_DIR`,
`LEETCODE_NODE_BIN`, `LEETCODE_COACH_CARDS_DRY_RUN=1`, an injectable Accepted probe and clocks (`relay.coach.Deps`).
**P** owns `leetcode_coach/`, `leetcode_guard/_coach_log.py` + snapshot fields, the unit, `install.sh`. **F** owns
`app/lib/desktop/wrapper_server.dart` (the proxy) and in `app/lib/src/` the `coach.dart` grades, the coach client
(RTDB + wrapper), and the Coach tab session UI with its offline and stalled states.

## 8. Deviations from tutor

1. **Desktop uses loopback HTTP, not RTDB**: it never holds a Firebase credential (`sources.dart`). 2. **No claims,
leases or ETags**: one relay per account settles no race; "working" is `heartbeat.busy`. 3. **One paced lane**, capped
at 5 queued, not two lanes. 4. **Clients poll** (no SSE code in the app; a result poll costs ~4 bytes). 5. **`state`
and `result` are string leaves**, this repo's null-safe convention. 6. **PC offline = phone clock minus `beat` > 2 min**
(the spec's rule; the status heartbeat does the same at 10 min; tutor uses 75 s of monotonic silence). 7. **Unknown
kinds get `bad_request`**: "dropped" means never run, but the client is told, so it stops waiting.
