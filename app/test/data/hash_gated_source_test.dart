import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/hash_gated_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

/// RTDB text leaves holding two different snapshots.
final String _v1 = jsonEncode('{"schema": 1}');
final String _v2 = jsonEncode('{"schema": 2}');

/// A fake RTDB: answers each node from a mutable map and records every GET.
class _Rtdb {
  final nodes = <String, Object?>{
    'status': _v1,
    'status_hash': '"h1"',
    'heartbeat': '"2026-10-23T14:05:00+02:00"',
  };
  final asked = <String>[];

  late final source = FirebaseSnapshotSource(
    open: () async {
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
    },
    databaseUrl: 'https://db.example',
    httpClient: MockClient((r) async {
      final node = r.url.path
          .replaceFirst('/leetcode-guard/', '')
          .replaceFirst('.json', '');
      asked.add(node);
      final answer = nodes[node];
      if (answer is Exception) throw answer;
      if (answer is int) return http.Response('err', answer);
      return http.Response((answer as String?) ?? 'null', 200);
    }),
  );
}

void main() {
  late _Rtdb db;
  late DateTime now;
  late HashGatedSource gated;

  setUp(() {
    db = _Rtdb();
    now = kGeneratedAt;
    gated = HashGatedSource(db.source, clock: () => now);
  });

  /// One poll the way the controller does it: snapshot, then heartbeat.
  /// Returns the nodes read.
  Future<List<String>> tick({int minutes = 1}) async {
    now = now.add(Duration(minutes: minutes));
    db.asked.clear();
    await gated.fetch();
    await gated.heartbeat();
    return List.of(db.asked);
  }

  test('first load downloads the status', () async {
    expect(await tick(), ['status_hash', 'status', 'heartbeat']);
  });

  test('an unchanged hash costs only the two tiny nodes', () async {
    await tick();
    expect(await tick(), ['status_hash', 'heartbeat']);
    // ...and still answers the body it already has.
    expect(await gated.fetch(), _v1);
  });

  test('a changed hash downloads the status again', () async {
    await tick();
    db.nodes['status_hash'] = '"h2"';
    db.nodes['status'] = _v2;
    expect(await tick(), ['status_hash', 'status', 'heartbeat']);
    expect(await gated.fetch(), _v2);
    expect(await tick(), ['status_hash', 'heartbeat']);
  });

  group('no hash node', () {
    setUp(() => db.nodes['status_hash'] = null);

    test('falls back to a full fetch every ten minutes', () async {
      expect(await tick(), ['status_hash', 'status', 'heartbeat']);
      for (var minute = 1; minute < 10; minute++) {
        expect(await tick(), ['status_hash', 'heartbeat'], reason: '$minute');
      }
      expect(await tick(), ['status_hash', 'status', 'heartbeat']);
      expect(await tick(), ['status_hash', 'heartbeat']);
    });

    test('a hash appearing downloads at once', () async {
      await tick();
      db.nodes['status_hash'] = '"h1"';
      expect(await tick(), ['status_hash', 'status', 'heartbeat']);
      expect(await tick(), ['status_hash', 'heartbeat']);
    });

    test('a hash disappearing waits out the ten minutes', () async {
      db.nodes['status_hash'] = '"h1"';
      await tick();
      db.nodes['status_hash'] = null;
      expect(await tick(minutes: 9), ['status_hash', 'heartbeat']);
      expect(await tick(), ['status_hash', 'status', 'heartbeat']);
    });
  });

  test('a failed download is retried on the next tick', () async {
    await tick();
    db.nodes['status_hash'] = '"h2"';
    db.nodes['status'] = 502;
    await expectLater(gated.fetch(), throwsA(isA<SnapshotUnavailable>()));
    db.nodes['status'] = _v2;
    expect(await tick(), ['status_hash', 'status', 'heartbeat']);
    expect(await gated.fetch(), _v2);
  });

  test('nothing published is retried, not remembered', () async {
    db.nodes['status'] = null;
    expect(await gated.fetch(), isNull);
    db.nodes['status'] = _v1;
    expect(await tick(), ['status_hash', 'status', 'heartbeat']);
  });

  test('a failed hash read is unavailable and reads nothing else', () async {
    db.nodes['status_hash'] = 503;
    await expectLater(gated.fetch(), throwsA(isA<SnapshotUnavailable>()));
    expect(db.asked, ['status_hash']);
  });

  test('defaults to the wall clock', () {
    expect(HashGatedSource(db.source).inner, same(db.source));
  });

  test('the controller polls through it', () async {
    // The RTDB leaf is the snapshot as ONE JSON string.
    db.nodes['status'] = jsonEncode(fixtureText('snapshot_full'));
    final controller = StatusController(
      source: gated,
      cache: MemoryCache(),
      clock: () => now,
    );
    await controller.refresh();
    await controller.refresh();
    expect(controller.snapshot!.status!.credits, 41);
    expect(db.asked, [
      'status_hash',
      'status',
      'heartbeat',
      'status_hash',
      'heartbeat',
    ]);
    controller.dispose();
  });
}
