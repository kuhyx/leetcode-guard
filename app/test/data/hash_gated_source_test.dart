import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/data/hash_gated_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

/// RTDB text leaves holding two different snapshots.
final String _v1 = jsonEncode('{"schema": 1}');
final String _v2 = jsonEncode('{"schema": 2}');

/// The decrypted leaves, as `FirebaseSnapshotSource` answers them (each
/// JSON-encoded, the shape of a raw RTDB GET); records every read. An int
/// is an HTTP failure. The real source's E2E reads are in e2e_stores_test.
class _Rtdb {
  final nodes = <String, Object?>{
    'status': _v1,
    'status_hash': '"h1"',
    'heartbeat': '"2026-10-23T14:05:00+02:00"',
  };
  final asked = <String>[];

  late final source = _Leaves(this);
}

class _Leaves implements HashedSnapshotSource {
  new(this.db);

  final _Rtdb db;

  Future<String?> _get(String node) async {
    db.asked.add(node);
    final answer = db.nodes[node];
    if (answer is int) throw SnapshotUnavailable(httpFailure(answer));
    return answer as String?;
  }

  @override
  Future<String?> fetch() => _get('status');

  @override
  Future<String?> heartbeat() => _get('heartbeat');

  @override
  Future<String?> statusHash() => _get('status_hash');
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
