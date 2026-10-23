import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/snapshot_cache.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/data/wrapper_snapshot_source.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

FirebaseSnapshotSource _source(
  http.Client httpClient, {
  InMemoryCredentialStore? store,
}) => FirebaseSnapshotSource(
  open: () async => FirebaseRestClient(
    databaseUrl: 'https://db.example',
    auth: FirebaseTokenProvider(apiKey: 'k', store: store ?? _signedIn()),
  ),
  databaseUrl: 'https://db.example/',
  httpClient: httpClient,
);

Matcher _unavailable(Object message) => throwsA(
  isA<SnapshotUnavailable>().having((e) => e.message, 'message', message),
);

void main() {
  group('WrapperSnapshotSource', () {
    final base = Uri.parse('http://localhost:8776/');

    test('reads /snapshot.json from the wrapper', () async {
      Uri? asked;
      final source = WrapperSnapshotSource(
        base: base,
        client: MockClient((r) async {
          asked = r.url;
          return http.Response('{"schema": 1}', 200);
        }),
      );
      expect(await source.fetch(), '{"schema": 1}');
      expect(asked, Uri.parse('http://localhost:8776/snapshot.json'));
    });

    test('404 means nothing published yet', () async {
      final source = WrapperSnapshotSource(
        base: base,
        client: MockClient((_) async => http.Response('', 404)),
      );
      expect(await source.fetch(), isNull);
    });

    test('other statuses carry the wrapper message', () async {
      final source = WrapperSnapshotSource(
        base: base,
        client: MockClient((_) async => http.Response('firebase down', 502)),
      );
      await expectLater(
        source.fetch(),
        _unavailable('Wrapper HTTP 502: firebase down'),
      );
    });

    test('defaults to a real HTTP client', () {
      expect(WrapperSnapshotSource(base: base).base, base);
    });

    test('a dead wrapper is unavailable, not a crash', () async {
      final source = WrapperSnapshotSource(
        base: base,
        client: MockClient((_) async => throw http.ClientException('refused')),
      );
      await expectLater(source.fetch(), _unavailable(contains('refused')));
    });
  });

  group('FirebaseSnapshotSource', () {
    test('GETs the status path with the ID token', () async {
      Uri? asked;
      final source = _source(
        MockClient((r) async {
          asked = r.url;
          return http.Response('{"schema": 1}', 200);
        }),
      );
      expect(await source.fetch(), '{"schema": 1}');
      expect(asked!.path, '/leetcode-guard/status.json');
      expect(asked!.queryParameters['auth'], 'tok');
      expect(asked!.host, 'db.example');
    });

    test('a JSON null body means nothing published', () async {
      final source = _source(
        MockClient((_) async => http.Response('null', 200)),
      );
      expect(await source.fetch(), isNull);
    });

    test('not signed in is unavailable with a hint', () async {
      final source = FirebaseSnapshotSource(
        open: () async => null,
        databaseUrl: 'https://db.example',
      );
      await expectLater(source.fetch(), _unavailable(contains('Sync account')));
    });

    test('a rejected read is unavailable', () async {
      final source = _source(
        MockClient((_) async => http.Response('denied', 401)),
      );
      await expectLater(source.fetch(), _unavailable('Firebase HTTP 401'));
    });

    test('network and auth failures are unavailable', () async {
      final offline = _source(
        MockClient((_) async => throw http.ClientException('offline')),
      );
      await expectLater(offline.fetch(), _unavailable(contains('offline')));
      final unauthenticated = _source(
        MockClient((_) async => http.Response('{}', 200)),
        store: InMemoryCredentialStore(),
      );
      await expectLater(
        unauthenticated.fetch(),
        _unavailable(contains('sign-in failed')),
      );
    });

    test('heartbeat reads its own tiny node', () async {
      Uri? asked;
      final source = _source(
        MockClient((r) async {
          asked = r.url;
          return http.Response('"2026-10-23T14:05:00+02:00"', 200);
        }),
      );
      expect(await source.heartbeat(), '"2026-10-23T14:05:00+02:00"');
      expect(asked!.path, '/leetcode-guard/heartbeat.json');
    });
  });

  test('wrapper heartbeat reads /heartbeat.json; 404 is none', () async {
    final asked = <String>[];
    final source = WrapperSnapshotSource(
      base: Uri.parse('http://localhost:8776/'),
      client: MockClient((r) async {
        asked.add(r.url.path);
        return http.Response('', 404);
      }),
    );
    expect(await source.heartbeat(), isNull);
    expect(asked, ['/heartbeat.json']);
  });

  test('SnapshotUnavailable prints its message', () {
    expect(const SnapshotUnavailable('x').toString(), 'x');
  });

  test('PrefsSnapshotCache round-trips', () async {
    SharedPreferences.setMockInitialValues({});
    final cache = PrefsSnapshotCache();
    expect(await cache.read(), isNull);
    await cache.write('{"schema": 1}');
    expect(await cache.read(), '{"schema": 1}');
  });
}
