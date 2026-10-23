/// Dev only: the real wrapper over a scripted coach relay, for screenshots.
///
/// Serves `build/web` and a fixture snapshot on a free loopback port and
/// forwards `/coach/*` to an in-process fake relay (the tests' own
/// `FakeRelay`, spoken over the contract's HTTP API). The relay is seeded
/// mid-session on Missing Number: step 1 passed on the second try, step 2
/// passed, step 3 open with one partial grade, and a chat with a hint and a
/// pasted code message. Never touches 8776 / 8777 or any real data.
///
/// Usage: `dart run tool/coach_screenshot_server.dart [port-file]`
/// (prints, and writes to port-file, the wrapper port; serves until killed).
library;

import 'dart:convert';
import 'dart:io';

import 'package:leetcode_guard/desktop/sources.dart';
import 'package:leetcode_guard/desktop/wrapper_server.dart';

import '../test/support/fake_relay.dart';

const _code =
    'function missingNumber(nums) {\n'
    '  let x = nums.length;\n'
    '  nums.forEach((v, i) => { x ^= i ^ v; });\n'
    '  return x;\n'
    '}';

FakeRelay _seeded() {
  final relay = FakeRelay(now: () => DateTime.now().millisecondsSinceEpoch);
  var n = 0;
  void run(String kind, Map<String, Object?> body) =>
      relay.handle('seed${n++}', kind, {'session': kSid, ...body});
  run('session_start', {'slug': 'missing-number'});
  run('grade_step', {'step': 1, 'answer': 'loop and count'});
  run('grade_step', {'step': 1, 'answer': 'O(1) extra space, one pass'});
  run('chat', {'text': 'Why would XOR help here?'});
  run('hint', {});
  run('grade_step', {
    'step': 2,
    'answer': 'pairs of equal values cancel\nevery index 0..n appears once',
  });
  run('chat', {'text': _code});
  run('grade_step', {
    'step': 3,
    'picks': ['XOR self-cancellation', 'Gauss sum', 'Hash set'],
  });
  return relay;
}

Future<void> _answer(HttpRequest req, Object? body, {int status = 200}) async {
  req.response
    ..statusCode = status
    ..headers.contentType = ContentType.json
    ..write(jsonEncode(body));
  await req.response.close();
}

Future<HttpServer> _serveRelay(FakeRelay relay) async {
  final queued = <String, Map<String, Object?>>{};
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((req) async {
    final path = req.uri.path;
    if (req.method == 'POST' && path == '/coach/requests') {
      final r = jsonDecode(await utf8.decoder.bind(req).join()) as Map;
      final rid = r['rid'] as String;
      queued[rid] = r.cast<String, Object?>();
      return await _answer(req, {'rid': rid}, status: 202);
    }
    if (path.startsWith('/coach/requests/')) {
      final rid = path.substring('/coach/requests/'.length);
      final r = queued.remove(rid);
      final done = r == null
          ? relay.done[rid]
          : relay.handle(rid, r['kind']! as String, (r['body']! as Map).cast());
      return await _answer(req, {'result': done});
    }
    await switch (path) {
      '/coach/heartbeat' => _answer(req, relay.heartbeat),
      '/coach/state' => _answer(req, relay.state),
      '/coach/chat' => _answer(req, relay.chat),
      _ => _answer(req, {'ok': false}, status: 404),
    };
  });
  return server;
}

Future<void> main(List<String> args) async {
  final relay = await _serveRelay(_seeded());
  final wrapper = WrapperServer(
    webRoot: '${Directory.current.path}/build/web',
    source: FileSnapshotSource(File('test/fixtures/snapshot_full.json')),
    relay: Uri.parse('http://127.0.0.1:${relay.port}'),
  );
  final port = await wrapper.start(port: 0);
  if (args.isNotEmpty) File(args.first).writeAsStringSync('$port');
  stdout.writeln('wrapper on http://localhost:$port, relay on ${relay.port}');
}
