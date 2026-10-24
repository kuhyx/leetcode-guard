import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/app_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/fakes.dart';

void main() {
  var now = DateTime.utc(2026, 10, 24, 11, 5);
  DateTime clock() => now;

  setUp(() => now = DateTime.utc(2026, 10, 24, 11, 5));

  test('a repeat bumps count and last-seen, keeps first-seen', () async {
    final log = AppErrorLog(slot: MemorySlot(), clock: clock);
    await log.record("Offline: can't reach Firebase");
    now = now.add(const Duration(minutes: 1));
    await log.record("Offline: can't reach Firebase");
    final [only] = await log.entries();
    expect(only.message, "Offline: can't reach Firebase");
    expect(only.firstSeen, DateTime.utc(2026, 10, 24, 11, 5));
    expect(only.lastSeen, DateTime.utc(2026, 10, 24, 11, 6));
    expect(only.count, 2);
  });

  test('keeps only the newest few, newest first', () async {
    final log = AppErrorLog(slot: MemorySlot(), clock: clock, keep: 2);
    for (final m in ['a', 'b', 'c']) {
      now = now.add(const Duration(minutes: 1));
      await log.record(m);
    }
    expect((await log.entries()).map((e) => e.message), ['c', 'b']);
  });

  test('a secret that slipped through is scrubbed before it is kept', () async {
    final slot = MemorySlot();
    final log = AppErrorLog(slot: slot, clock: clock);
    await log.record('boom https://db.example/x.json?auth=SECRET');
    expect(slot.value, isNot(contains('SECRET')));
    expect((await log.entries()).single.message, isNot(contains('auth=')));
  });

  test('pending is null until something is recorded, then once', () async {
    final slot = MemorySlot();
    final log = AppErrorLog(slot: slot, clock: clock);
    expect(await log.pending('dev-1'), isNull);
    await log.record('x');
    final batch = (await log.pending('dev-1'))!;
    final body = jsonDecode(batch.body) as Map<String, Object?>;
    expect(body['device'], 'dev-1');
    expect(body['sent_at'], '2026-10-24T11:05:00.000Z');
    expect(body['errors'], [
      {
        'message': 'x',
        'first_seen': '2026-10-24T11:05:00.000Z',
        'last_seen': '2026-10-24T11:05:00.000Z',
        'count': 1,
      },
    ]);
    await log.markSent(batch);
    expect(await log.pending('dev-1'), isNull);
    // Survives a restart: a fresh log over the same slot agrees.
    expect(await AppErrorLog(slot: slot, clock: clock).pending('d'), isNull);
  });

  test('an error recorded mid-upload stays pending', () async {
    final log = AppErrorLog(slot: MemorySlot(), clock: clock);
    await log.record('x');
    final batch = (await log.pending('d'))!;
    await log.record('y');
    await log.markSent(batch);
    expect(await log.pending('d'), isNotNull);
  });

  test('an unreadable slot starts empty instead of crashing', () async {
    for (final junk in ['not json', '[]', '{"errors": [1, {}], "rev": "x"}']) {
      final slot = MemorySlot()..value = junk;
      final log = AppErrorLog(slot: slot, clock: clock);
      expect(await log.entries(), isEmpty);
      expect(await log.pending('d'), isNull);
    }
  });

  test('PrefsTextSlot round-trips', () async {
    SharedPreferences.setMockInitialValues({});
    const slot = PrefsTextSlot('k');
    expect(await slot.read(), isNull);
    await slot.write('v');
    expect(await slot.read(), 'v');
  });

  test('defaults to the wall clock and a prefs slot', () async {
    SharedPreferences.setMockInitialValues({});
    final log = AppErrorLog();
    await log.record('x');
    expect((await log.entries()).single.count, 1);
  });
}
