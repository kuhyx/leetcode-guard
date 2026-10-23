/// A 52-week submission heatmap: one column per week, oldest on the left.
library;

import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';

/// The heatmap, sized to whatever width it is given.
class Heatmap extends StatelessWidget {
  /// Creates a heatmap of [counts] for the 364 days ending on [today].
  const new({required this.counts, required this.today, super.key});

  /// Submissions per UTC day.
  final Map<DateTime, int> counts;

  /// The last day shown (UTC midnight).
  final DateTime today;

  /// Weeks shown.
  static const weeks = 52;

  /// Gap between cells.
  static const gap = 2.0;

  /// The first day shown.
  static DateTime start(DateTime today) =>
      today.subtract(const Duration(days: weeks * 7 - 1));

  /// Submissions inside the window ending on [today].
  static int total(Map<DateTime, int> counts, DateTime today) {
    final first = start(today);
    return counts.entries
        .where((e) => !e.key.isBefore(first) && !e.key.isAfter(today))
        .fold(0, (sum, e) => sum + e.value);
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final cell = math.min(14, constraints.maxWidth / weeks - gap).toDouble();
      final scheme = Theme.of(context).colorScheme;
      return Semantics(
        label: '${total(counts, today)} submissions in the last 52 weeks',
        child: SizedBox(
          key: const Key('heatmap'),
          width: weeks * (cell + gap),
          height: 7 * (cell + gap),
          child: CustomPaint(
            painter: HeatmapPainter(
              counts: counts,
              start: start(today),
              cell: cell,
              empty: scheme.surfaceContainerHighest,
              ink: AppPalette.accent,
            ),
          ),
        ),
      );
    },
  );
}

/// Paints the cells. Intensity steps at 1, 3 and 6 submissions a day.
class HeatmapPainter extends CustomPainter {
  /// Creates the painter.
  new({
    required this.counts,
    required this.start,
    required this.cell,
    required this.empty,
    required this.ink,
  });

  /// Submissions per UTC day.
  final Map<DateTime, int> counts;

  /// The first day (top-left cell).
  final DateTime start;

  /// Cell edge length.
  final double cell;

  /// Colour of a day with no submissions.
  final Color empty;

  /// The accent the busier days are drawn in.
  final Color ink;

  /// Opacity for [count] submissions; 0 means "use [empty]".
  static double level(int count) => switch (count) {
    <= 0 => 0,
    < 3 => 0.4,
    < 6 => 0.7,
    _ => 1,
  };

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint();
    for (var i = 0; i < Heatmap.weeks * 7; i++) {
      final day = start.add(Duration(days: i));
      final alpha = level(counts[day] ?? 0);
      paint.color = alpha == 0 ? empty : ink.withValues(alpha: alpha);
      final rect = Rect.fromLTWH(
        (i ~/ 7) * (cell + Heatmap.gap),
        (i % 7) * (cell + Heatmap.gap),
        cell,
        cell,
      );
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect, const Radius.circular(2)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(HeatmapPainter oldDelegate) =>
      oldDelegate.counts != counts ||
      oldDelegate.start != start ||
      oldDelegate.cell != cell;
}
