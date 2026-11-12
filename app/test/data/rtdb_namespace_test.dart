import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/coach/rtdb_transport.dart';

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

/// Every request path the coach transport, the one own-URL RTDB client,
/// sends. The sealed snapshot and error reports go through crdt_sync's
/// FirebaseRestClient, which applies the namespace itself.
Future<List<String>> _paths({String? namespace}) async {
  final seen = <http.Request>[];
  final http_ = MockClient((r) async {
    seen.add(r);
    return http.Response('null', 200);
  });
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
  return seen.map((r) => r.url.path).toList();
}

void main() {
  test('empty namespace keeps every path byte-identical', () async {
    expect(await _paths(namespace: ''), [
      '/leetcode-guard/coach/requests/$_rid/req.json',
      '/leetcode-guard/coach/requests/$_rid/result.json',
      '/leetcode-guard/coach/heartbeat.json',
      '/leetcode-guard/coach/state.json',
      '/leetcode-guard/coach/chat.json',
    ]);
  });

  test('a sandbox namespace prefixes every request path', () async {
    final paths = await _paths(namespace: 'sandbox/slot3');
    expect(paths, hasLength(5));
    expect(paths, everyElement(startsWith('/sandbox/slot3/leetcode-guard/')));
  });

  test('an invalid namespace fails closed at construction', () {
    for (final bad in ['slot3', 'sandbox/', 'sandbox/Slot', '/x', 'a\n']) {
      expect(
        () => RtdbCoachTransport(
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
    final coach = RtdbCoachTransport(
      open: _open,
      databaseUrl: 'https://db.example',
      httpClient: MockClient((r) async {
        seen.add(r.url.path);
        return http.Response('null', 200);
      }),
    );
    await coach.state();
    expect(seen, ['/leetcode-guard/coach/state.json']);
  });
}
