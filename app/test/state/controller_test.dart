import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/state/controller.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

void main() {
  StatusController make(
    List<Object?> answers, {
    MemoryCache? cache,
    int minutes = 1,
  }) => StatusController(
    source: FakeSource(answers),
    cache: cache ?? MemoryCache(),
    clock: clockAfter(minutes),
  );

  test('a fetched snapshot is shown, cached and fresh', () async {
    final cache = MemoryCache();
    final c = make([fixtureText('snapshot_full')], cache: cache);
    await c.refresh();
    expect(c.snapshot!.status!.credits, 41);
    expect(c.error, isNull);
    expect(c.stale, isFalse);
    expect(cache.value, fixtureText('snapshot_full'));
    c.dispose();
  });

  test('older than ten minutes is stale', () async {
    final c = make([fixtureText('snapshot_full')], minutes: 11);
    await c.refresh();
    expect(c.stale, isTrue);
    c.dispose();
  });

  test('a failed fetch keeps the last good snapshot and goes stale', () async {
    final c = make([
      fixtureText('snapshot_full'),
      const SnapshotUnavailable('network down'),
    ]);
    await c.refresh();
    await c.refresh();
    expect(c.snapshot!.status!.credits, 41);
    expect(c.error, 'network down');
    expect(c.stale, isTrue);
    c.dispose();
  });

  test('nothing ever fetched is stale with no snapshot', () async {
    final c = make([const SnapshotUnavailable('not signed in')]);
    await c.load();
    expect(c.snapshot, isNull);
    expect(c.stale, isTrue);
    expect(c.error, 'not signed in');
    c.dispose();
  });

  test('an unexpected exception is reported by type, not thrown', () async {
    final c = make([const FormatException('boom ?auth=SECRET')]);
    await c.refresh();
    expect(c.error, 'Refresh failed (FormatException)');
    c.dispose();
  });

  group('error reporter', () {
    StatusController reporting(List<Object?> answers, FakeReporter r) =>
        StatusController(
          source: FakeSource(answers),
          cache: MemoryCache(),
          clock: clockAfter(1),
          reporter: r,
        );

    test('a failed refresh is kept; a working one sends', () async {
      final r = FakeReporter();
      final c = reporting([
        const SnapshotUnavailable('offline'),
        const FormatException('x'),
        fixtureText('snapshot_full'),
      ], r);
      await c.refresh();
      expect(r.failures, ['offline']);
      expect(r.reaches, 0);
      await c.refresh();
      expect(r.failures, ['offline', 'Refresh failed (FormatException)']);
      await c.refresh();
      expect(r.reaches, 1);
      c.dispose();
    });

    test('nothing published is a contact, not a failure', () async {
      final r = FakeReporter();
      final c = reporting([null], r);
      await c.refresh();
      expect(r.failures, isEmpty);
      expect(r.reaches, 1);
      c.dispose();
    });
  });

  test('nothing published yet is an error, not an empty snapshot', () async {
    final c = make([null]);
    await c.refresh();
    expect(c.snapshot, isNull);
    expect(c.error, contains('No snapshot'));
    c.dispose();
  });

  test('an unreadable body is an error and does not replace data', () async {
    final cache = MemoryCache(fixtureText('snapshot_full'));
    final c = make(['[]'], cache: cache);
    await c.load();
    expect(c.snapshot!.status!.credits, 41);
    expect(c.error, contains('unreadable'));
    expect(cache.value, fixtureText('snapshot_full'));
    c.dispose();
  });

  test('load shows the cached copy before the network answers', () async {
    final cache = MemoryCache(fixtureText('snapshot_stale'));
    final c = make([const SnapshotUnavailable('offline')], cache: cache);
    await c.load();
    expect(c.snapshot!.status!.locked, isTrue);
    expect(c.stale, isTrue);
    c.dispose();
  });

  test('a corrupt cache is ignored', () async {
    final c = make([
      fixtureText('snapshot_full'),
    ], cache: MemoryCache('garbage'));
    await c.load();
    expect(c.snapshot!.status!.credits, 41);
    c.dispose();
  });

  group('heartbeat', () {
    StatusController beat(List<Object?> heartbeats, {int minutes = 25}) =>
        StatusController(
          source: FakeSource([
            fixtureText('snapshot_full'),
          ], heartbeats: heartbeats),
          cache: MemoryCache(),
          clock: clockAfter(minutes),
        );

    test('a recent heartbeat keeps an unchanged snapshot fresh', () async {
      final c = beat(['"2026-10-23T14:29:00+02:00"']);
      await c.refresh();
      expect(c.stale, isFalse);
      expect(c.freshAt, DateTime.parse('2026-10-23T14:29:00+02:00'));
    });

    test('an old heartbeat is stale', () async {
      final c = beat(['"2026-10-23T14:10:00+02:00"']);
      await c.refresh();
      expect(c.stale, isTrue);
      expect(c.freshAt, DateTime.parse('2026-10-23T14:10:00+02:00'));
    });

    test('no heartbeat falls back to generated_at', () async {
      final c = beat([null], minutes: 3);
      await c.refresh();
      expect(c.freshAt, kGeneratedAt);
      expect(c.stale, isFalse);
    });

    test('a heartbeat older than the snapshot does not age it', () async {
      final c = beat(['"2026-10-23T13:00:00+02:00"'], minutes: 3);
      await c.refresh();
      expect(c.freshAt, kGeneratedAt);
    });

    test('a failed heartbeat read is an error like any other', () async {
      final c = beat([const SnapshotUnavailable('beat lost')], minutes: 3);
      await c.refresh();
      expect(c.snapshot, isNotNull);
      expect(c.error, 'beat lost');
      expect(c.stale, isTrue);
    });
  });

  test('now follows the injected clock', () {
    final c = make([null], minutes: 3);
    expect(c.now(), kGeneratedAt.add(const Duration(minutes: 3)));
    c.dispose();
  });
}
