import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';

import '../support/fixtures.dart';

void main() {
  group('Snapshot.tryParse', () {
    test('parses the gate fields of the full fixture', () {
      final snap = fixture('snapshot_full');
      expect(snap.schema, 1);
      expect(snap.generatedAt, kGeneratedAt);
      expect(snap.projectionPrice, 2);
      final s = snap.status!;
      expect(s.day, '2026-10-23');
      expect(s.weekday, 'Thursday');
      expect(s.state, 'settled');
      expect(s.locked, isFalse);
      expect(s.reason, 'today is already paid for');
      expect(s.explanation, ['Today was already settled by an earlier run.']);
      expect(s.cost, 2);
      expect(s.surcharge, 0);
      expect(s.credits, 41);
      expect(s.charged, 39);
      expect(s.available, 2);
      expect(s.needed, 0);
      expect(s.chargedToday, isTrue);
      expect(s.earnedAllTime, 43);
      expect(s.spentAllTime, 39);
      expect(s.pricingNote, startsWith('Tue/Wed/Thu'));
      expect(s.debt!.owed, 3);
      expect(s.debt!.repaid, 1);
      expect(s.debt!.outstanding, 2);
      expect(s.debt!.missedDays, 1);
      expect(s.debt!.summary, startsWith('2 credits'));
      expect(s.solves!.today, 1);
      expect(s.solves!.last7Days, 9);
      expect(s.solves!.totalCredited, 41);
      expect(s.solves!.recent![1].lang, isNull);
      expect(s.solves!.recent!.first.titleSlug, 'two-sum');
      expect(s.solves!.recent!.first.day, '2026-10-22');
      expect(s.days!.charged, ['2026-10-22', '2026-10-21']);
      expect(s.days!.startDate, '2026-08-04');
      expect(s.days!.gateInForce, isTrue);
      expect(s.budgets!['incidents']!.exhausted, isTrue);
      expect(s.budgets!['escape']!.label, 'Escape hatch');
      expect(s.budgets!['escape']!.nextWaitSeconds, 600);
      expect(s.budgets!['escape']!.extra, {'used_7': 1, 'limit_7': 3});
      expect(s.suggestions!.first.title, 'Missing Number');
      expect(s.suggestions!.first.difficulty, 'Easy');
      expect(s.suggestions!.first.url, contains('missing-number'));
      // Python may send an integral ac_rate: still a rate, not dropped.
      expect(s.suggestions![1].acRate, 52.0);
    });

    test('parses the health sections of the full fixture', () {
      final s = fixture('snapshot_full').status!;
      final i = s.integrity!;
      expect(i.ok, isTrue);
      expect(i.tampered, 0);
      expect(i.discounted, 1);
      expect(i.unparsable, 0);
      expect(i.clockTrusted, isTrue);
      expect(i.totalEntries, 206);
      expect(i.bootstrapped, isTrue);
      expect(i.ledgerPath, endsWith('ledger.json'));
      final e = s.environment!;
      expect(e.clockTrusted, isTrue);
      expect(e.authPresent, isTrue);
      expect(e.authNote, contains('cookie'));
      expect(e.poolSource, contains('live pool'));
      expect(e.poolNotes, ['statement cache warm']);
      expect(e.cookiesConfigured, isTrue);
      expect(e.syncConfigured, isFalse);
      expect(e.timer!.enabled, isTrue);
      expect(e.timer!.nextFire, startsWith('Sat'));
      expect(e.timer!.detail, 'enabled');
      expect(e.poolCacheSummary, startsWith('Problem pool'));
      expect(e.statementCacheSummary, startsWith('Offline statements'));
    });

    test('parses progress, projections, profile and coach', () {
      final snap = fixture('snapshot_full');
      final progress = snap.progress!;
      expect(progress.solved, {'Easy': 120, 'Medium': 150, 'Hard': 42});
      expect(progress.total!['Medium'], 2300);
      expect(progress.solvedAll, 312);
      expect(progress.totalAll, 4055);
      expect(progress.fetchedAt, DateTime.parse('2026-10-23T14:01:37+02:00'));
      final proj = snap.projections!['2026-10-31']!;
      expect(proj.target, '2026-10-31');
      expect(proj.firstDay, '2026-10-24');
      expect(proj.gatedDays, 8);
      expect(proj.freeDays, 0);
      expect(proj.baseCost, 21);
      expect(proj.debt, 2);
      expect(proj.available, 2);
      expect(proj.required, 21);
      expect(proj.rulesDemand, 23);
      expect(proj.debtLeftByRules, 0);
      expect(proj.sickDays, 0);
      expect(proj.projected!['Easy'], 141);
      expect(proj.projectedTotal, 333);
      final profile = snap.profile!;
      expect(profile.difficulty!['medium']!.solved, 150);
      expect(profile.difficulty!['hard']!.total, 850);
      expect(profile.streakCurrent, 5);
      expect(profile.streakLongest, 30);
      expect(profile.acceptanceRate, 61.2);
      expect(profile.fetchedAt, DateTime.parse('2026-10-23T14:01:37+02:00'));
      expect(profile.calendar![DateTime.utc(2026, 10, 22)], 2);
      // Epoch-second keys (LeetCode's own calendar format) are dates too.
      expect(profile.calendar![DateTime.utc(2025, 10, 20)], 4);
    });

    test('the real exporter snapshot parses end to end', () {
      final snap = fixture('snapshot_real');
      expect(snap.status!.state, 'already-charged');
      expect(snap.status!.solves!.recent, isNotEmpty);
      expect(snap.progress!.totalAll, 4087);
      expect(snap.projections, hasLength(99));
      expect(snap.projections!['2026-10-24']!.projectedTotal, 147);
      expect(snap.profile!.calendar, isNotEmpty);
    });

    test('null sections stay null, never zero-filled', () {
      final snap = fixture('snapshot_nulls');
      expect(snap.status, isNull);
      expect(snap.progress, isNull);
      expect(snap.projections, isNull);
      expect(snap.profile, isNull);
      expect(snap.coach, isNull);
    });

    test('missing and wrong-typed fields read as unknown', () {
      final snap = fixture('snapshot_sparse');
      final status = snap.status!;
      expect(status.available, isNull);
      expect(status.debt, isNull);
      expect(status.explanation, isNull);
      expect(status.integrity!.ok, isFalse);
      expect(status.integrity!.tampered, isNull);
      expect(status.environment!.poolNotes, isNull);
      expect(status.environment!.timer, isNull);
      expect(status.environment!.poolCacheSummary, isNull);
      expect(status.suggestions, isEmpty);
      expect(status.solves!.today, isNull);
      expect(status.solves!.recent, isEmpty);
      expect(status.days!.charged, isEmpty);
      expect(status.budgets!['escape']!.summary, isNull);
      expect(status.budgets!['escape']!.extra, {'used': 1});
      expect(status.budgets!['incidents'], isNull);
      expect(snap.progress!.solved, isNull);
      expect(snap.progress!.solvedAll, isNull);
      expect(snap.projections, isEmpty);
      expect(snap.profile!.difficulty!['easy']!.solved, isNull);
      expect(snap.profile!.difficulty!['medium'], isNull);
      expect(snap.profile!.calendar, isNull);
      expect(snap.coach!.retestsDue, isNull);
      expect(snap.coach!.howTo, isNull);
    });

    test('a projection total is unknown unless every count is known', () {
      Projection p(Object? projected) =>
          Projection.fromJson({'projected': projected});
      expect(p(null).projectedTotal, isNull);
      expect(p(<String, Object?>{}).projectedTotal, isNull);
      expect(p({'Easy': 1, 'Hard': null}).projectedTotal, isNull);
      expect(p({'Easy': 1, 'Hard': 2}).projectedTotal, 3);
    });

    test('accepts the snapshot stored as a JSON string leaf', () {
      final wrapped = jsonEncode(fixtureText('snapshot_full'));
      expect(Snapshot.tryParse(wrapped)!.status!.credits, 41);
    });

    test('rejects bodies that are not a snapshot', () {
      expect(Snapshot.tryParse('null'), isNull);
      expect(Snapshot.tryParse('[1, 2]'), isNull);
      expect(Snapshot.tryParse('not json'), isNull);
      expect(Snapshot.tryParse(jsonEncode('still not json')), isNull);
    });

    test('a bad generated_at is unknown, not now', () {
      final snap = Snapshot.tryParse('{"generated_at": "yesterday-ish"}')!;
      expect(snap.generatedAt, isNull);
      expect(snap.schema, isNull);
    });

    test('integral doubles count as ints; fractional ones do not', () {
      final snap = Snapshot.tryParse(
        '{"status": {"credits": 41.0, "charged": 2.5}}',
      )!;
      expect(snap.status!.credits, 41);
      expect(snap.status!.charged, isNull);
    });

    test('calendar skips unreadable keys and non-integer counts', () {
      final snap = Snapshot.tryParse(
        '{"profile": {"calendar": {"x": 1, "2026-10-01": "2", '
        '"2026-10-02": 3}}}',
      )!;
      expect(snap.profile!.calendar, {DateTime.utc(2026, 10, 2): 3});
    });

    test('list entries that are not objects are skipped', () {
      final snap = Snapshot.tryParse(
        '{"status": {"solves": {"recent": [1, {"day": "2026-10-01"}]}, '
        '"environment": {"pool_notes": ["a", 2]}}}',
      )!;
      expect(snap.status!.solves!.recent!.single.day, '2026-10-01');
      expect(snap.status!.environment!.poolNotes, ['a']);
    });
  });

  group('parseHeartbeat', () {
    test('reads the JSON string leaf', () {
      expect(
        parseHeartbeat('"2026-10-23T14:05:00+02:00"'),
        DateTime.parse('2026-10-23T14:05:00+02:00'),
      );
    });

    test('anything else is unknown', () {
      expect(parseHeartbeat(null), isNull);
      expect(parseHeartbeat('null'), isNull);
      expect(parseHeartbeat('"soon"'), isNull);
      expect(parseHeartbeat('{"a": 1}'), isNull);
      expect(parseHeartbeat('not json'), isNull);
    });
  });
}
