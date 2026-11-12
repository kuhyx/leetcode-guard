import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/snapshot_cache.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/data/wrapper_snapshot_source.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
