/// A scripted coach relay for Missing Number, following
/// `DOCS-coach-relay.md` §2-3: the state machine, the step gating, the
/// forced continue, chat, hints, reveal, run code and the step-4 Accepted.
///
/// Pure Dart (no Flutter) so `tool/coach_screenshot_server.dart` can serve
/// the very same relay over HTTP behind the real wrapper. The grading
/// rules are the fake's own, chosen so a test reads plainly.
library;

import 'fake_relay_script.dart';

export 'fake_relay_script.dart';

part 'fake_relay_steps.dart';

/// A JSON object.
typedef Json = Map<String, Object?>;

/// The relay's state machine, answering one request at a time.
class FakeRelay {
  new({required this.now});

  /// The clock, unix ms.
  final int Function() now;

  int rev = 0;
  Json? session;
  List<Json> steps = [];
  final Map<String, Json> chat = {};
  String? rung;
  bool revealed = false;

  /// rid -> result: a done rid is re-answered, never re-run.
  final Map<String, Json> done = {};

  /// Every request run, in order, as (kind, body).
  final List<(String, Json)> ran = [];

  /// The rid running now (heartbeat `busy`).
  String? busy;

  /// How old the heartbeat is, ms (0 = beating now).
  int beatAge = 0;

  /// Answer the next request `rate_limited` (retry:true) without running it.
  bool rateLimitNext = false;

  /// The card builder's error on a step-5 pass.
  String? cardsError;

  bool get live => session != null && session!['ended'] == null;

  Json get state => {
    'schema': 1,
    'rev': rev,
    'step': live ? _openStep : null,
    'rung': rung,
    'revealed': revealed,
    'chat_count': chat.length,
    'session': session,
    'steps': steps,
    if (live && _openStep == 3) 'toolbox': kFakeToolbox,
  };

  Json get heartbeat => {
    'beat': now() - beatAge,
    'started': 0,
    'state_rev': rev,
    'busy': ?busy,
    'version': 1,
  };

  int? get _openStep {
    for (final s in steps) {
      if (s['status'] == 'open') return s['n']! as int;
    }
    return null;
  }

  Json _step(int n) => steps[n - 1];

  void _bump() => rev++;

  String say(String role, String kind, String text) {
    final key = 'm${(chat.length + 1).toString().padLeft(4, '0')}';
    chat[key] = {'role': role, 'kind': kind, 'text': text, 'at': now()};
    return key;
  }

  Json ok(Json data) => {
    'ok': true,
    'at': now(),
    'state_rev': rev,
    'data': data,
  };

  Json err(
    String code,
    String error, {
    bool retry = false,
    Json extra = const {},
  }) => {
    'ok': false,
    'at': now(),
    'code': code,
    'error': error,
    'retry': retry,
    ...extra,
  };

  /// Runs request [rid] (or re-answers it) and returns its result.
  Json handle(String rid, String kind, Json body) {
    final known = done[rid];
    if (known != null) return known;
    final Json result;
    if (rateLimitNext) {
      rateLimitNext = false;
      result = err(
        'rate_limited',
        'Too many requests: wait a moment',
        retry: true,
        extra: {'retry_after_ms': 3000},
      );
    } else {
      ran.add((kind, body));
      result = _run(kind, body);
    }
    done[rid] = result;
    return result;
  }

  Json _run(String kind, Json body) {
    if (kind == 'session_start') return _start(body);
    if (!live || body['session'] != session!['id']) {
      return err('not_live', 'That session is not the live one');
    }
    return switch (kind) {
      'session_end' => _end('ended', {}),
      'chat' => _chat(body['text']! as String),
      'grade_step' => _grade(body),
      'hint' => _hint(),
      'reveal' => _reveal(),
      'run_code' => _runCode(),
      _ => err('bad_request', 'Unknown request kind'),
    };
  }

  Json _start(Json body) {
    if (live) return err('session_live', 'A session is live: end it first');
    if (body['slug'] != 'missing-number') {
      return err('no_answer_key', 'No answer key for that problem');
    }
    chat.clear();
    rung = null;
    revealed = false;
    session = newSession(now());
    steps = newSteps();
    final msg = say('coach', 'chat', kOpener);
    _bump();
    return ok({'session': kSid, 'msg': msg});
  }

  Json _end(String reason, Json data) {
    session = {...session!, 'ended': now(), 'end_reason': reason};
    _bump();
    return ok(data);
  }

  Json _chat(String text) {
    if (text == 'hint') return _hint();
    if (text == 'reveal') return _reveal();
    say('kuhy', 'chat', text);
    if (looksLikeCode(text) && !_codeOpen) return _phaseLocked();
    final msg = say('coach', 'chat', kReply);
    _bump();
    return ok({'msg': msg});
  }

  bool get _codeOpen =>
      _step(2)['status'] == 'passed' || _step(2)['status'] == 'forced';

  Json _phaseLocked() {
    say('system', 'refused', kRefused);
    _bump();
    return err('phase_locked', kRefused, extra: {'note': kRefused});
  }

  Json _hint() {
    rung = nextRung(rung);
    final msg = say('coach', 'hint', 'Hint $rung: $kHint');
    _bump();
    return ok({'msg': msg, 'rung': rung});
  }

  Json _reveal() {
    revealed = true;
    final msg = say('coach', 'reveal', kReveal);
    return _end('reveal', {'msg': msg});
  }

  Json _runCode() {
    if (!_codeOpen) return _phaseLocked();
    say('system', 'run', 'Ran 2 examples: 1 passed');
    _bump();
    return ok(kRunData);
  }
}
