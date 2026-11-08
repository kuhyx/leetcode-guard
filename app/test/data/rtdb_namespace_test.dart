import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/coach/rtdb_transport.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';

import '../support/fakes.dart';

class _Dev implements DeviceIdStore {
  @override
  Future<String> deviceId() async => 'dev1';
}

const _rid = '01JB2Z3Y4X5W6V7T8S9R0QPNMK';

Future<FirebaseRestClient?> _open() async {
  final store = InMemoryCredentialStore();
  await store.save(
    FirebaseCredentials(
      idToken: 'tok',
      refreshToken: 'r',
      expiresAt: DateTime.now().add(const Duration(hours: 1)),
    ),
  );
  return FirebaseRestClient(
    databaseUrl: 'https://db.example',
    auth: FirebaseTokenProvider(apiKey: 'k', store: store),
  );
}

/// Every request path the three own-URL RTDB clients send.
Future<List<String>> _paths({String? namespace}) async {
  final seen = <http.Request>[];
  final http_ = MockClient((r) async {
    seen.add(r);
    return http.Response('null', 200);
  });
  final source = FirebaseSnapshotSource(
    open: _open,
    databaseUrl: 'https://db.example/',
    httpClient: http_,
    namespace: namespace,
  );
  await source.fetch();
  await source.heartbeat();
  await source.statusHash();
  final coach = RtdbCoachTransport(
    open: _open,
    databaseUrl: 'https://db.example/',
    httpClient: http_,
    namespace: namespace,
  );
  await coach.submit(_rid, {'kind': 'chat', 'dev': 'd', 'body': 'x'});
  await coach.result(_rid);
  await coach.heartbeat();
  await coach.state();
  await coach.chat(after: 'a');
  final log = AppErrorLog(slot: MemorySlot());
  await log.record('boom');
  final reporter = RtdbErrorReporter(
    log: log,
    devices: _Dev(),
    open: _open,
    databaseUrl: 'https://db.example/',
    httpClient: http_,
    namespace: namespace,
  );
  expect(await reporter.reached(), isTrue);
  return seen.map((r) => r.url.path).toList();
}

void main() {
  test('empty namespace keeps every path byte-identical', () async {
    expect(await _paths(namespace: ''), [
      '/leetcode-guard/status.json',
      '/leetcode-guard/heartbeat.json',
      '/leetcode-guard/status_hash.json',
      '/leetcode-guard/coach/requests/$_rid/req.json',
      '/leetcode-guard/coach/requests/$_rid/result.json',
      '/leetcode-guard/coach/heartbeat.json',
      '/leetcode-guard/coach/state.json',
      '/leetcode-guard/coach/chat.json',
      '/leetcode-guard/app_errors/dev1.json',
    ]);
  });

  test('a sandbox namespace prefixes every request path', () async {
    final paths = await _paths(namespace: 'sandbox/slot3');
    expect(paths, hasLength(9));
    expect(paths, everyElement(startsWith('/sandbox/slot3/leetcode-guard/')));
  });

  test('an invalid namespace fails closed at construction', () {
    for (final bad in ['slot3', 'sandbox/', 'sandbox/Slot', '/x', 'a\n']) {
      expect(
        () => FirebaseSnapshotSource(
          open: _open,
          databaseUrl: 'https://db',
          namespace: bad,
        ),
        throwsException,
        reason: bad,
      );
      expect(
        () => RtdbCoachTransport(
          open: _open,
          databaseUrl: 'https://db',
          namespace: bad,
        ),
        throwsException,
        reason: bad,
      );
      expect(
        () => RtdbErrorReporter(
          log: AppErrorLog(slot: MemorySlot()),
          devices: _Dev(),
          open: _open,
          databaseUrl: 'https://db',
          namespace: bad,
        ),
        throwsException,
        reason: bad,
      );
    }
  });

  test('the compiled define defaults to empty (production paths)', () async {
    final seen = <String>[];
    final source = FirebaseSnapshotSource(
      open: _open,
      databaseUrl: 'https://db.example',
      httpClient: MockClient((r) async {
        seen.add(r.url.path);
        return http.Response('null', 200);
      }),
    );
    await source.fetch();
    expect(seen, ['/leetcode-guard/status.json']);
  });
}
