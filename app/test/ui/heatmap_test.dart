import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/heatmap.dart';

HeatmapPainter _painter({double cell = 4, DateTime? start}) => HeatmapPainter(
  counts: const {},
  start: start ?? DateTime.utc(2026),
  cell: cell,
  empty: Colors.black,
  ink: Colors.white,
);

void main() {
  test('intensity steps at 1, 3 and 6 submissions', () {
    expect(HeatmapPainter.level(0), 0);
    expect(HeatmapPainter.level(2), 0.4);
    expect(HeatmapPainter.level(5), 0.7);
    expect(HeatmapPainter.level(9), 1);
  });

  test('repaints only when what it draws changes', () {
    final base = _painter();
    expect(_painter().shouldRepaint(base), isFalse);
    expect(_painter(cell: 5).shouldRepaint(base), isTrue);
    expect(_painter(start: DateTime.utc(2025)).shouldRepaint(base), isTrue);
  });

  test('the window is 364 days ending today, inclusive', () {
    final today = DateTime.utc(2026, 10, 23);
    expect(Heatmap.start(today), DateTime.utc(2025, 10, 25));
    final counts = {
      today: 1,
      Heatmap.start(today): 2,
      DateTime.utc(2025, 10, 24): 4,
      DateTime.utc(2026, 10, 24): 8,
    };
    expect(Heatmap.total(counts, today), 3);
  });
}
