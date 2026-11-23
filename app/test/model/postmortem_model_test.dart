import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';

import '../support/fixtures.dart';

void main() {
  test('the exporter fixture parses, oldest unit first', () {
    final units = fixture('snapshot_postmortem').postmortems!;
    expect(units.map((u) => u.unit), ['two-pointers', 'prefix-sums']);
    final latest = units.last;
    expect((latest.post!.k, latest.post!.n), (0, 3));
    expect(latest.post!.fraction, 0);
    expect((latest.pre!.k, latest.pre!.n), (1, 7));
    final problems = latest.problems!;
    expect(problems, hasLength(10));
    expect(problems.first.slug, 'left-and-right-sum-differences');
    expect(problems.first.minutes, isNull);
    expect(problems.first.tries, 11);
    expect(problems.first.afterTheory, isFalse);
    expect(problems.last.afterTheory, isTrue);
    expect(problems[3].oneShot, isTrue);
    final cards = latest.cards!;
    expect(cards.map((c) => c.change).toSet(), CardChange.values.toSet());
    expect(cards.last.change, CardChange.kept);
    expect(cards.last.usedBy, contains('running-sum-of-1d-array'));
  });

  test('a snapshot without the section reads as unknown', () {
    expect(fixture('snapshot_full').postmortems, isNull);
  });

  test('malformed rows read as unknown, unknown kinds are dropped', () {
    final snap = Snapshot.fromJson(
      jsonDecode('''
      {"postmortems": [{"unit": 3, "post": [1], "pre": [1, "x"],
        "problems": "x",
        "cards": [{"kind": "weird"}, {"kind": "new"}]},
       {"unit": "u", "post": [0, 0], "problems": [{"phase": "mid"}],
        "cards": "x"}]}
      ''') as Map<String, Object?>,
    );
    final [first, second] = snap.postmortems!;
    expect(first.unit, '');
    expect(first.post, isNull);
    expect(first.pre, isNull);
    expect(first.problems, isNull);
    expect(first.cards!.single.change, CardChange.added);
    expect(first.cards!.single.usedBy, isEmpty);
    expect(second.post!.fraction, isNull);
    final problem = second.problems!.single;
    expect(problem.afterTheory, isNull);
    expect(problem.oneShot, isFalse);
    expect(problem.slug, '');
    expect(second.cards, isNull);
  });
}
