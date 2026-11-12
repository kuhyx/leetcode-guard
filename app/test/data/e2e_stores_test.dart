import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/data/e2e_stores.dart';
import 'package:leetcode_guard/src/data/firebase_snapshot_source.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';

import '../support/fake_rtdb.dart';

const _status = '{"schema":1,"balance":{"credits":7}}';
const _beat = '2026-11-12T10:00:00+01:00';

Matcher _unavailable(Object message) => throwsA(
  isA<SnapshotUnavailable>().having((e) => e.message, 'message', message),
);

void main() {
  late FakeRtdb db;

  setUp(() async {
    db = FakeRtdb();
    await db.seal(kStatusPath, _status);
    await db.seal(kHeartbeatNode, _beat);
    await db.seal(kStatusHashNode, 'h1');
  });

  test('paths match the PC side (leetcode_guard/_e2e.py)', () {
    expect(kStatusPath, 'leetcode-guard/snapshot-e2e/status');
    expect(kHeartbeatNode, 'leetcode-guard/snapshot-e2e/heartbeat');
    expect(kStatusHashNode, 'leetcode-guard/snapshot-e2e/status_hash');
    expect(kSnapshotLayout.e2ePath, 'leetcode-guard/e2e');
    expect(kAppErrorsLayout.e2ePath, kSnapshotLayout.e2ePath);
    expect(kAppErrorsLayout.prefix, 'leetcode-guard/app_errors-e2e');
  });

  test('the RTDB holds ciphertext; the source reads it opened', () async {
    for (final path in [kStatusPath, kHeartbeatNode, kStatusHashNode]) {
      expect(db.leaves[path], isNot(contains('balance')));
      expect(db.leaves[path], isNot(contains('2026-11-12')));
    }
    final source = FirebaseSnapshotSource(stores: db.stores());
    final body = await source.fetch();
    expect(body, jsonEncode(_status));
    expect(Snapshot.tryParse(body!), isNotNull);
    expect(
      parseHeartbeat(await source.heartbeat()),
      DateTime.parse(_beat),
    );
    expect(await source.statusHash(), jsonEncode('h1'));
  });

  test('one unlock per run: later reads only GET the leaf', () async {
    final source = FirebaseSnapshotSource(stores: db.stores());
    await source.fetch();
    db.asked.clear();
    await source.heartbeat();
    expect(db.asked, [kHeartbeatNode]);
  });

  test('an unpublished leaf reads as null', () async {
    db.leaves.remove(kStatusPath);
    final source = FirebaseSnapshotSource(stores: db.stores());
    expect(await source.fetch(), isNull);
  });

  test('a locked phone reads nothing and says so, then unlocks', () async {
    final stores = db.stores(passphrase: null);
    final source = FirebaseSnapshotSource(stores: stores);
    db.asked.clear();
    await expectLater(source.fetch(), _unavailable(kE2eLockedText));
    expect(stores.locked.value, isTrue);
    expect(db.asked, isNot(contains(kStatusPath)));

    final unlocked = db.stores();
    expect(await FirebaseSnapshotSource(stores: unlocked).fetch(), isNotNull);
    expect(unlocked.locked.value, isFalse);
  });

  test('a wrong passphrase is locked too', () async {
    final source = FirebaseSnapshotSource(
      stores: db.stores(passphrase: 'not it'),
    );
    await expectLater(source.fetch(), _unavailable(kE2eLockedText));
  });

  test('reset forgets the store, so a saved passphrase takes effect', () async {
    var opens = 0;
    final stores = db.stores(
      open: () {
        opens++;
        return db.client();
      },
    );
    await stores.snapshot();
    await stores.snapshot();
    expect(opens, 1);
    stores.reset();
    await stores.snapshot();
    expect(opens, 2);
  });

  test('not signed in is unavailable with a hint', () async {
    final source = FirebaseSnapshotSource(
      stores: SealedStores(open: () async => null),
    );
    await expectLater(source.fetch(), _unavailable(contains('Sync account')));
    expect(await SealedStores(open: () async => null).appErrors(), isNull);
  });

  test('rejected, offline and sign-in failures are unavailable', () async {
    final source = FirebaseSnapshotSource(stores: db.stores());
    await source.fetch();
    db.failures[kStatusPath] = 401;
    await expectLater(
      source.fetch(),
      _unavailable('Firebase answered HTTP 401'),
    );
    db
      ..failures.clear()
      ..throws[kStatusPath] = http.ClientException('offline');
    await expectLater(
      source.fetch(),
      _unavailable('Network error (ClientException)'),
    );
    for (final (error, text) in [
      (RemoteSyncError('refresh failed'), contains('sign-in failed')),
      (http.ClientException('offline'), 'Network error (ClientException)'),
    ]) {
      final failing = FirebaseSnapshotSource(
        stores: SealedStores(open: () async => throw error),
      );
      await expectLater(failing.fetch(), _unavailable(text));
    }
  });
}
