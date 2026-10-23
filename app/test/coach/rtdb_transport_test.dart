import 'dart:async';
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/coach/rtdb_transport.dart';
import 'package:leetcode_guard/src/coach/transport.dart';

const _rid = '01JB2Z3Y4X5W6V7T8S9R0QPNMK';

InMemoryCredentialStore _signedIn() {
  final store = InMemoryCredentialStore();
  unawaited(
    store.save(
      FirebaseCredentials(
        idToken: 'tok',
        refreshToken: 'r',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      ),
    ),
  );
  return store;
}

RtdbCoachTransport _rtdb(
  Future<http.Response> Function(http.Request) handler, {
  InMemoryCredentialStore? store,
  bool signedOut = false,
}) => RtdbCoachTransport(
  open: () async => signedOut
      ? null
      : FirebaseRestClient(
          databaseUrl: 'https://db.example',
          auth: FirebaseTokenProvider(apiKey: 'k', store: store ?? _signedIn()),
        ),
  databaseUrl: 'https://db.example/',
  httpClient: MockClient(handler),
);

Matcher _outage(CoachOutage outage, [Object? message]) => throwsA(
  isA<CoachUnavailable>()
      .having((e) => e.outage, 'outage', outage)
      .having((e) => e.message, 'message', message ?? anything),
);

void main() {
  test('submit PUTs only req, with the server timestamp and no rid', () async {
    late http.Request seen;
    final t = _rtdb((r) async {
      seen = r;
      return http.Response('', 204);
    });
    expect(t.phone, isTrue);
    expect(t.resultPollEvery, const Duration(seconds: 2));
    final result = await t.submit(_rid, {
      'kind': 'chat',
      'dev': 'd',
      'body': {'session': 's', 'text': 'hi'},
    });
    expect(result, isNull);
    expect(seen.method, 'PUT');
    expect(seen.url.path, '/leetcode-guard/coach/requests/$_rid/req.json');
    expect(seen.url.queryParameters, {'print': 'silent', 'auth': 'tok'});
    expect(jsonDecode(seen.body), {
      'kind': 'chat',
      'dev': 'd',
      'created': {'.sv': 'timestamp'},
      'body': {'session': 's', 'text': 'hi'},
    });
    expect(() => t.submit('bad', const {}), throwsArgumentError);
  });

  test('result and state are string leaves, decoded twice', () async {
    final t = _rtdb((r) async {
      final path = r.url.path;
      if (path.endsWith('/result.json')) {
        return http.Response(jsonEncode(jsonEncode({'ok': true})), 200);
      }
      if (path.endsWith('/state.json')) {
        return http.Response(jsonEncode(jsonEncode({'rev': 4})), 200);
      }
      return http.Response('null', 200);
    });
    expect((await t.result(_rid))!.ok, isTrue);
    expect((await t.state())!.rev, 4);
    expect(await t.heartbeat(), isNull);
  });

  test('a missing result is null; an object leaf is taken as is', () async {
    var body = 'null';
    final t = _rtdb((_) async => http.Response(body, 200));
    expect(await t.result(_rid), isNull);
    body = '{"ok": false, "code": "x"}';
    expect((await t.result(_rid))!.code, 'x');
  });

  test('heartbeat is an object; chat pages from a key', () async {
    final asked = <Uri>[];
    final t = _rtdb((r) async {
      asked.add(r.url);
      if (r.url.path.endsWith('/heartbeat.json')) {
        return http.Response('{"beat": 5, "state_rev": 2}', 200);
      }
      return http.Response(
        '{"m0002": {"role": "kuhy", "text": "a"}, '
        '"m0003": {"role": "coach", "text": "b"}}',
        200,
      );
    });
    expect((await t.heartbeat())!.stateRev, 2);
    final chat = await t.chat(after: 'm0002');
    expect(chat.map((m) => m.key), ['m0003']);
    expect(asked.last.queryParameters, {
      'orderBy': r'"$key"',
      'startAt': '"m0002"',
      'auth': 'tok',
    });
    expect((await t.chat()).map((m) => m.key), ['m0002', 'm0003']);
    expect(asked.last.queryParameters, {'auth': 'tok'});
  });

  test('failures are outages the banner can name', () async {
    await expectLater(
      _rtdb((_) async => http.Response('', 200), signedOut: true).state(),
      _outage(CoachOutage.signedOut, contains('Sync account')),
    );
    await expectLater(
      _rtdb((_) async => http.Response('denied', 401)).state(),
      _outage(CoachOutage.network, 'Firebase HTTP 401'),
    );
    await expectLater(
      _rtdb((_) async => throw http.ClientException('offline')).state(),
      _outage(CoachOutage.network, contains('offline')),
    );
    await expectLater(
      _rtdb(
        (_) async => http.Response('{}', 200),
        store: InMemoryCredentialStore(),
      ).state(),
      _outage(CoachOutage.signedOut, contains('sign-in failed')),
    );
    await expectLater(
      _rtdb((_) async => http.Response('not json', 200)).heartbeat(),
      _outage(CoachOutage.network, contains('Unreadable')),
    );
    await expectLater(
      _rtdb((_) async => http.Response('"not json"', 200)).state(),
      _outage(CoachOutage.network, contains('Unreadable')),
    );
  });

  test('the database url may come without a trailing slash', () {
    final t = RtdbCoachTransport(
      open: () async => null,
      databaseUrl: 'https://db.example',
    );
    expect(t.databaseUrl, 'https://db.example');
  });
}
