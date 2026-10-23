import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/heatmap.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

import '../support/pump.dart';

/// How many columns the visible cards sit in: distinct left edges.
int _columns(WidgetTester tester) => {
  for (final e in find.byType(SectionCard).evaluate())
    tester.getTopLeft(find.byWidget(e.widget)).dx.round(),
}.length;

Future<void> _tab(WidgetTester tester, String name) async {
  await tester.tap(find.text(name));
  await tester.pumpAndSettle();
}

void main() {
  test('column count by window width', () {
    expect(gridColumns(412), 1);
    expect(gridColumns(1199), 1);
    expect(gridColumns(1200), 2);
    expect(gridColumns(1280), 2);
    expect(gridColumns(1920), 3);
    expect(gridColumns(3840), 3);
  });

  for (final (width, columns) in [
    (412.0, 1),
    (1280.0, 2),
    (1920.0, 3),
    (3840.0, 3),
  ]) {
    testWidgets('${width.toInt()} px: $columns column(s) on every tab', (
      tester,
    ) async {
      await pumpApp(tester, size: Size(width, 2000));
      expect(_columns(tester), columns, reason: 'Status');
      await _tab(tester, 'Coach');
      expect(_columns(tester), columns, reason: 'Coach');
      await _tab(tester, 'Profile');
      expect(_columns(tester), columns, reason: 'Profile');
    });
  }

  testWidgets('phone keeps one full-width list', (tester) async {
    await pumpApp(tester, size: const Size(412, 900));
    final list = tester.getSize(find.byKey(const Key('status-list')));
    expect(list.width, 412);
  });

  testWidgets('a wide window uses the width it has', (tester) async {
    await pumpApp(tester, size: const Size(1920, 1080));
    final list = tester.getSize(find.byKey(const Key('status-list')));
    // Everything right of the navigation rail, not a 720 px strip.
    expect(list.width, greaterThan(1700));
  });

  testWidgets('the heatmap card spans the grid on a wide window', (
    tester,
  ) async {
    await pumpApp(tester, size: const Size(1920, 2000));
    await _tab(tester, 'Profile');
    final heatmapCard = find.ancestor(
      of: find.byType(Heatmap),
      matching: find.byType(SectionCard),
    );
    final split = find.ancestor(
      of: find.text('Difficulty split'),
      matching: find.byType(SectionCard),
    );
    expect(
      tester.getSize(heatmapCard).width,
      greaterThan(2.5 * tester.getSize(split).width),
    );
  });
}
