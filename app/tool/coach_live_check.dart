/// Dev only: drives the REAL coach relay through the app's own desktop path
/// (the wrapper's `/coach/*` proxy and [WrapperCoachTransport]), so the
/// client is checked against `leetcode_coach/relay/`, not against a fake
/// written by the same hand.
///
/// Run by `tool/coach_live_check.sh`, which starts the relay on a spare
/// loopback port with claude, Firebase, LeetCode and Anki faked. `flow` is
/// a whole session up to step 4; `slow` is one 35 s coach turn, polled the
/// way the app polls, through a wrapper with the 30 s per-call timeout.
///
/// Usage: `dart run tool/coach_live_check.dart PORT flow|slow [FIXTURES]`
/// (FIXTURES: a directory the relay's raw answers are written to).
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:leetcode_guard/desktop/sources.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/coach/wrapper_transport.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';

const _code =
    'var missingNumber = function(nums) {\n'
    '  let x = nums.length;\n'
    '  nums.forEach((v, i) => { x ^= i ^ v; });\n'
    '  return x;\n'
    '};';

class _Live {
  new(this.base, this.fixtures) : t = WrapperCoachTransport(base: base);

  final Uri base;
  final Directory? fixtures;
  final WrapperCoachTransport t;
  final UlidGenerator _ulid = UlidGenerator();
  final String _dev = uuid4(Random.secure());
  int failures = 0;
  String sid = '';

  void check(String what, {required bool ok}) {
    stdout.writeln('${ok ? 'ok  ' : 'FAIL'} $what');
    if (!ok) failures++;
  }

  void _write(String name, Object? json) {
    final dir = fixtures;
    if (dir == null) return;
    final text = const JsonEncoder.withIndent('  ').convert(json);
    File('${dir.path}/$name.json').writeAsStringSync('$text\n');
  }

  /// GETs [path] raw (the fixture is the relay's own bytes, decoded).
  Future<void> save(String name, String path) async =>
      _write(name, jsonDecode((await http.get(base.resolve(path))).body));

  Future<CoachState> state([String? fixture]) async {
    if (fixture != null) await save(fixture, '/coach/state');
    return (await t.state())!;
  }

  /// Sends one request and polls for its result, as the controller does.
  Future<RelayResult> send(
    String kind,
    Map<String, Object?> body, {
    String? fixture,
    Future<void> Function(String rid)? meanwhile,
  }) async {
    final rid = _ulid.next();
    final full = kind == 'session_start' ? body : {'session': sid, ...body};
    var r = await t.submit(rid, {'kind': kind, 'dev': _dev, 'body': full});
    while (r == null) {
      await Future<void>.delayed(const Duration(milliseconds: 250));
      await meanwhile?.call(rid);
      r = await t.result(rid);
    }
    if (fixture != null) _write(fixture, r.raw);
    return r;
  }

  Future<void> start() async {
    final r = await send('session_start', {
      'slug': 'missing-number',
    }, fixture: 'result_session_start');
    check('session_start ok: ${r.raw}', ok: r.ok);
    sid = r.data['session']! as String;
  }
}

Future<void> _flow(_Live l) async {
  await l.save('heartbeat_idle', '/coach/heartbeat');
  final empty = await l.state('state_none');
  l.check('no session: nulls', ok: empty.session == null && empty.step == null);
  final ghost = UlidGenerator().next();
  try {
    await l.t.result(ghost);
    l.check('unknown rid should 404', ok: false);
  } on CoachUnavailable catch (e) {
    l.check('unknown rid -> forgotten', ok: e.outage == CoachOutage.forgotten);
  }
  await l.start();
  await l.state('state_step1');
  var r = await l.send('grade_step', {
    'step': 3,
    'picks': ['XOR'],
  });
  l.check('step 3 locked: ${r.code}', ok: r.raw['code'] == 'step_locked');
  r = await l.send('grade_step', {
    'step': 1,
    'answer': 'loop and count',
  }, fixture: 'result_step1_partial');
  l.check('partial keeps step 1 open: ${r.data}', ok: r.data['next_step'] == 1);
  r = await l.send('grade_step', {'step': 1, 'answer': 'O(1) space, one pass'});
  l.check('pass opens step 2: ${r.data}', ok: r.data['next_step'] == 2);
  r = await l.send('chat', {
    'text': 'Why would folding help here',
  }, fixture: 'result_chat');
  l.check('chat reply ${r.data}', ok: r.ok && r.data['msg'] is String);
  r = await l.send('chat', {'text': _code}, fixture: 'result_phase_locked');
  l.check(
    'code before step 2 refused: ${r.code}',
    ok: r.code == 'phase_locked',
  );
  for (var i = 1; i <= 3; i++) {
    r = await l.send('grade_step', {
      'step': 2,
      'answer': 'use XOR\nevery index appears once',
    }, fixture: i == 3 ? 'result_step2_fail' : null);
    l.check('step-2 fail via toolbox (try $i)', ok: r.data['via'] == 'toolbox');
  }
  l.check('can_force after 3 fails', ok: r.data['can_force'] == true);
  r = await l.send('grade_step', {
    'step': 2,
    'force': true,
  }, fixture: 'result_force');
  l.check('force opens step 3: ${r.data}', ok: r.data['next_step'] == 3);
  final s2 = (await l.state('state_step3')).stepAt(2)!;
  l.check('forced, 3', ok: s2.attempts == 3 && s2.status == StepStatus.forced);
  r = await l.send('grade_step', {
    'step': 3,
    'picks': ['not a tool'],
  }, fixture: 'result_bad_pick');
  l.check('unknown pick -> bad_request: ${r.raw}', ok: r.code == 'bad_request');
  r = await l.send('grade_step', {
    'step': 3,
    'picks': ['x' * 65],
  });
  l.check(
    'over-long pick -> bad_request (HTTP 200)',
    ok: r.code == 'bad_request',
  );
  r = await l.send('grade_step', {
    'step': 3,
    'picks': ['sum / difference', 'hash set', 'sorting'],
  }, fixture: 'result_step3_partial');
  l.check('two extras -> partial: ${r.data}', ok: r.data['grade'] == 'partial');
  r = await l.send('grade_step', {
    'step': 3,
    'picks': ['sum / difference'],
  });
  l
    ..check('also_accepted alone -> pass', ok: r.data['grade'] == 'pass')
    ..check('step 4 open: ${r.data}', ok: r.data['next_step'] == 4);
  r = await l.send('run_code', {'code': _code}, fixture: 'result_run_code');
  l.check('run_code ran: ${r.data}', ok: r.ok && r.data['error'] == null);
  await l.save('chat_all', '/coach/chat');
  final runs = (await l.t.chat()).where((m) => m.kind == 'run').toList();
  l.check(
    'one run line in chat: ${runs.map((m) => m.text)}',
    ok: runs.length == 1,
  );
  r = await l.send('session_end', {});
  final ended = await l.state('state_ended');
  l.check('ended: step null, not live', ok: ended.step == null && !ended.live);
  r = await l.send('chat', {'text': 'still there'});
  l.check('after the end: not_live', ok: r.code == 'not_live');
}

Future<void> _slow(_Live l) async {
  await l.start();
  var slowest = Duration.zero;
  var sawBusy = false;
  final r = await l.send(
    'chat',
    {'text': 'Why would folding help here'},
    meanwhile: (rid) async {
      final watch = Stopwatch()..start();
      final hb = await l.t.heartbeat();
      await l.t.state();
      await l.t.chat();
      if (watch.elapsed > slowest) slowest = watch.elapsed;
      if (hb?.busy == rid) sawBusy = true;
    },
  );
  l
    ..check('35 s turn answered through a 30 s proxy: ${r.raw}', ok: r.ok)
    ..check('heartbeat.busy named the rid while the turn ran', ok: sawBusy)
    ..check('slowest poll $slowest', ok: slowest < const Duration(seconds: 2));
}

Future<void> main(List<String> args) async {
  final port = int.parse(args[0]);
  final fixtures = args.length > 2 && args[2].isNotEmpty
      ? Directory(args[2])
      : null;
  final wrapper = WrapperServer(
    webRoot: Directory.systemTemp.path,
    source: FileSnapshotSource(File('test/fixtures/snapshot_full.json')),
    relay: Uri.parse('http://127.0.0.1:$port'),
    // Far under the 35 s turn: passing proves no route waits on a turn.
    relayTimeout: const Duration(seconds: 30),
  );
  final own = await wrapper.start(port: 0);
  final live = _Live(Uri.parse('http://127.0.0.1:$own'), fixtures);
  await (args[1] == 'slow' ? _slow(live) : _flow(live));
  await wrapper.close();
  stdout.writeln(live.failures == 0 ? 'ALL OK' : '${live.failures} FAILED');
  exit(live.failures == 0 ? 0 : 1);
}
