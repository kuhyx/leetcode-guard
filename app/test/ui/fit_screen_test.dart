import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';

import '../support/coach_rig.dart';
import '../support/pump.dart';

/// The Pixel 6a: 1080x2400 at 2.625, status bar and gesture inset included.
const _pixelSize = Size(1080, 2400);
const _pixelRatio = 2.625;
const _pixelInset = FakeViewPadding(top: 132, bottom: 63);

Future<void> _pump(WidgetTester tester, {String snapshot = 'snapshot_real'}) =>
    pumpApp(
      tester,
      answers: [snapshot],
      size: _pixelSize,
      devicePixelRatio: _pixelRatio,
      padding: _pixelInset,
    );

/// How far each vertical scrollable on screen could still move.
List<double> _overflow(WidgetTester tester) => [
  for (final element in find.byType(Scrollable).evaluate())
    if ((element as StatefulElement).state case final ScrollableState s
        when s.axisDirection == AxisDirection.down)
      s.position.maxScrollExtent,
];

/// Whether every tappable thing in the section is on screen and reachable.
bool _actionsHittable() {
  final content = find.byKey(const Key('tab-content'));
  return [
    find.descendant(of: content, matching: find.byType(InkWell)),
    find.descendant(of: content, matching: find.byType(ButtonStyleButton)),
  ].every((f) => f.hitTestable().evaluate().length == f.evaluate().length);
}

/// Taps every chip and reports each section that scrolls or hides an action.
Future<void> _everyChip(
  WidgetTester tester,
  String tab, {
  Set<String> exempt = const {},
}) async {
  final chips = find.byType(ChoiceChip);
  final count = chips.evaluate().length;
  expect(count, greaterThan(1), reason: '$tab has chips');
  final problems = <String>[];
  for (var i = 0; i < count; i++) {
    await tester.ensureVisible(chips.at(i));
    await tester.tap(chips.at(i));
    await tester.pumpAndSettle();
    final label = (tester.widget<ChoiceChip>(chips.at(i)).label as Text).data!;
    if (exempt.contains(label)) continue;
    if (_overflow(tester).any((extent) => extent > 0)) {
      problems.add('$tab / $label scrolls by ${_overflow(tester)}');
    }
    if (!_actionsHittable()) problems.add('$tab / $label hides an action');
  }
  expect(problems, isEmpty);
}

void main() {
  testWidgets('Status: every section fits one Pixel 6a screen', (tester) async {
    await _pump(tester);
    await _everyChip(tester, 'Status');
  });

  testWidgets('Profile: every section fits one Pixel 6a screen', (
    tester,
  ) async {
    await _pump(tester);
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await _everyChip(tester, 'Profile');
  });

  testWidgets('Coach: the landing fits one Pixel 6a screen', (tester) async {
    await _pump(tester);
    await tester.tap(find.text('Coach'));
    await tester.pumpAndSettle();
    await _everyChip(tester, 'Coach');
  });

  testWidgets('Coach with a live relay: Start buttons still fit', (
    tester,
  ) async {
    await pumpCoach(
      tester,
      snapshot: 'snapshot_real',
      size: _pixelSize,
      devicePixelRatio: _pixelRatio,
      padding: _pixelInset,
      phone: true,
    );
    await tester.tap(find.text('Coach'));
    await tester.pumpAndSettle();
    await _everyChip(tester, 'Coach (relay)');
  });

  testWidgets('a tall window still lists every section at once', (
    tester,
  ) async {
    await pumpApp(tester, size: const Size(412, 3000));
    expect(find.byType(ChoiceChip), findsNothing);
    expect(gridColumns(412), 1);
  });
}
