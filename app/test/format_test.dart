import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/format.dart';

void main() {
  test('null is unknown, never zero', () {
    expect(show(null), 'unknown');
    expect(show(0), '0');
    expect(show(52.0), '52.0');
    expect(show(61.25), '61.3');
    expect(show(true), 'yes');
    expect(show(false), 'no');
    expect(show('x'), 'x');
  });

  test('percent keeps unknown', () {
    expect(percent(null), 'unknown');
    expect(percent(61.2), '61.2%');
  });

  test('fraction is unknown when either side is', () {
    expect(fraction(312, 4055), '312 / 4055');
    expect(fraction(null, 4055), 'unknown');
    expect(fraction(312, null), 'unknown');
  });

  test('asOf shows local HH:MM', () {
    final t = DateTime(2026, 10, 23, 9, 5);
    expect(asOf(t), 'as of 09:05');
    expect(asOf(null), 'as of unknown');
  });

  test('asOfDated adds the date unless it is today', () {
    final now = DateTime(2026, 10, 23, 15);
    expect(asOfDated(DateTime(2026, 10, 23, 9, 5), now), 'as of 09:05');
    expect(
      asOfDated(DateTime(2026, 10, 21, 9, 5), now),
      'as of 2026-10-21 09:05',
    );
    expect(asOfDated(null, now), 'as of unknown');
  });

  test('stale after ten minutes, and when the time is unknown', () {
    final at = DateTime.utc(2026, 10, 23, 12);
    expect(isStale(at, at.add(const Duration(minutes: 10))), isFalse);
    expect(isStale(at, at.add(const Duration(minutes: 11))), isTrue);
    expect(isStale(null, at), isTrue);
  });

  test('ageText describes minutes and hours', () {
    final at = DateTime.utc(2026, 10, 23, 12);
    expect(ageText(at, at.add(const Duration(minutes: 25))), '25 min old');
    expect(ageText(at, at.add(const Duration(minutes: 150))), '2 h old');
    expect(ageText(null, at), 'age unknown');
  });

  test('isoDate is zero padded', () {
    expect(isoDate(DateTime.utc(2026, 3, 7)), '2026-03-07');
  });
}
