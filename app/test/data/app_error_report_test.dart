import 'dart:async';
import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:leetcode_guard/src/coach/device_id.dart';
import 'package:leetcode_guard/src/data/app_error_report.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:leetcode_guard/src/data/e2e_stores.dart';

import '../support/fake_rtdb.dart';
import '../support/fakes.dart';

const _device = '0b7e3c1a-1111-4222-8333-444455556666';
const _leaf = 'leetcode-guard/app_errors-e2e/$_device';

class _Dev implements DeviceIdStore {
  @override
  Future<String> deviceId() async => _device;
}

void main() {
  late FakeRtdb db;
  late AppErrorLog log;

  RtdbErrorReporter reporter({SealedStores? stores}) => RtdbErrorReporter(
    log: log,
    devices: _Dev(),
    stores: stores ?? db.stores(),
  );

  setUp(() {
    db = FakeRtdb();
    log = AppErrorLog(
      slot: MemorySlot(),
      clock: () => DateTime.utc(2026, 10, 24, 11, 5),
    );
  });

  test('nothing recorded: reaching Firebase writes nothing', () async {
    final r = reporter();
    expect(await r.reached(), isFalse);
    expect(db.leaves, isEmpty);
  });

  test('a recorded error is sent once, sealed, for the PC to open', () async {
    final r = reporter();
    await r.failed("Offline: can't reach Firebase");
    expect(await r.reached(), isTrue);
    final stored = db.leaves[_leaf]!;
    expect(stored, isNot(contains('errors')));
    expect(stored, isNot(contains('Offline')));
    final opened = await db.open(_leaf, layout: kAppErrorsLayout);
    final body = jsonDecode(opened!) as Map<String, Object?>;
    expect((body['errors']! as List).single, containsPair('count', 1));
    // Sent: the next contact has nothing to say.
    final writes = db.leaves.length;
    expect(await r.reached(), isFalse);
    expect(db.leaves, hasLength(writes));
  });

  test('a locked phone sends nothing and keeps the errors', () async {
    await log.record('x');
    final stores = db.stores(passphrase: null);
    expect(await reporter(stores: stores).reached(), isFalse);
    expect(db.leaves.keys, isNot(contains(_leaf)));
    expect(stores.locked.value, isTrue);
    expect(await log.pending('d'), isNotNull);
  });

  test(
    'a failed upload keeps the errors pending and records nothing',
    () async {
      await log.record('x');
      await db.stores().snapshot(); // the header exists; only the PUT fails
      for (final fail in <void Function()>[
        () => db.failures[_leaf] = 401,
        () => db.throws[_leaf] = http.ClientException('offline'),
      ]) {
        db.failures.clear();
        db.throws.clear();
        fail();
        expect(await reporter().reached(), isFalse);
        expect((await log.entries()).single.count, 1);
        expect(await log.pending('d'), isNotNull);
      }
      final signedOut = reporter(stores: SealedStores(open: () async => null));
      expect(await signedOut.reached(), isFalse);
      expect((await log.entries()).single.count, 1);
    },
  );

  test('sign-in and network failures are a give-up, not a crash', () async {
    await log.record('x');
    for (final error in <Exception>[
      RemoteSyncError('token refresh failed'),
      http.ClientException('offline'),
    ]) {
      final stores = SealedStores(open: () async => throw error);
      expect(await reporter(stores: stores).reached(), isFalse);
    }
  });

  test('two contacts at once upload once', () async {
    final gate = Completer<RemoteStore?>();
    final r = reporter(stores: db.stores(open: () => gate.future));
    await r.failed('x');
    final first = r.reached();
    expect(await r.reached(), isFalse);
    gate.complete(await db.client());
    expect(await first, isTrue);
    expect(db.leaves.keys.where((k) => k == _leaf), hasLength(1));
  });
}
