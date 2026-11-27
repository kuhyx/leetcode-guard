import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';

import '../support/fixtures.dart';

void main() {
  test('parses an unpaid SOLVE lock with its problem rows in order', () {
    final lock = fixture('snapshot_lock_solve').status!.lock!;
    expect(lock.unpaid, isTrue);
    expect(lock.unit, 'Prefix sums');
    expect(lock.phase, 'solve');
    expect(lock.learnRoute, '/learn/arrays/prefix-sums');
    final rows = lock.rows!.cast<LockProblem>();
    expect([for (final r in rows) r.difficulty], ['Easy', 'Medium', 'Hard']);
    expect(rows.first.title, 'Range Sum Query - Immutable');
    expect(
      rows.first.url,
      'https://leetcode.com/problems/range-sum-query-immutable/',
    );
  });

  test('parses a review row', () {
    final lock = fixture('snapshot_lock_review').status!.lock!;
    expect(lock.learnRoute, isNull);
    final review = lock.rows!.single as LockReview;
    expect(review.count, 3);
    expect(review.route, '/review/arrays/prefix-sums');
  });

  test('an older snapshot has no lock', () {
    expect(fixture('snapshot_full').status!.lock, isNull);
  });

  test('malformed lock values read as unknown, never throw', () {
    final lock = LockData.fromJson({
      'unpaid': 'yes',
      'unit': 3,
      'phase': null,
      'learn_route': 7,
      'rows': [
        'not an object',
        {'kind': 'mystery', 'title': 'x'},
        {'kind': 'review', 'count': 'many'},
        {'title': 'no kind'},
      ],
    });
    expect(lock.unpaid, isNull);
    expect(lock.unit, isNull);
    expect(lock.phase, isNull);
    expect(lock.learnRoute, isNull);
    expect(lock.rows, hasLength(1));
    expect((lock.rows!.single as LockReview).count, isNull);
    expect(LockData.fromJson({'rows': 'nope'}).rows, isNull);
  });

  test('a non-object lock is no lock', () {
    final s = StatusData.fromJson({'lock': 'unpaid'});
    expect(s.lock, isNull);
  });
}
