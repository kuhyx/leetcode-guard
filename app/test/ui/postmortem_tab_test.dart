import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/card_pages.dart';
import 'package:leetcode_guard/src/ui/postmortem_chart.dart';
import 'package:leetcode_guard/src/ui/postmortem_tab.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';
import 'package:material_ui/material_ui.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';

/// Tall enough that every section is listed, none behind a chip.
const kTall = Size(390, 4000);

/// The full fixture with its `postmortems` replaced by [rows].
String withPostmortems(Object? rows) {
  final json = jsonDecode(fixtureText('snapshot_full')) as Map<String, Object?>;
  return jsonEncode({...json, 'postmortems': rows});
}

Future<void> openPostmortems(
  WidgetTester tester, {
  Object answer = 'snapshot_postmortem',
  Size size = kTall,
}) async {
  await pumpApp(tester, answers: [answer], size: size);
  await openTab(tester, kPostmortemTab);
}

Finder key(String k) => find.byKey(Key(k));

Future<void> tapKey(WidgetTester tester, String k) async {
  await tester.ensureVisible(key(k));
  await tester.tap(key(k));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('bars, the newest unit grid and its chips, no reveal yet', (
    tester,
  ) async {
    await openPostmortems(tester);
    expect(find.byType(PostmortemTab), findsOneWidget);
    expect(key('pm-bar-0'), findsOneWidget);
    expect(key('pm-bar-1'), findsOneWidget);
    expect(find.text('2/3'), findsOneWidget);
    expect(find.text('0/3'), findsOneWidget);
    expect(key('pm-problem-9'), findsOneWidget);
    expect(key('pm-card-9'), findsOneWidget);
    expect(find.byIcon(Icons.push_pin_outlined), findsOneWidget);
    expect(find.byIcon(Icons.pause_circle_outline), findsOneWidget);
    expect(find.byIcon(Icons.edit_outlined), findsNWidgets(3));
    expect(find.byIcon(Icons.add_circle_outline), findsNWidgets(5));
    for (final k in ['unit', 'problem', 'card']) {
      expect(key('pm-reveal-$k'), findsNothing);
    }
  });

  testWidgets('a 0 % bar is a stub, taller than nothing', (tester) async {
    await openPostmortems(tester);
    final bars = find.descendant(
      of: key('pm-bar-1'),
      matching: find.byType(Container),
    );
    final heights = bars.evaluate().map((e) => e.size!.height);
    expect(heights, contains(2));
  });

  testWidgets('a problem row reveals its finding, a second tap hides it', (
    tester,
  ) async {
    await openPostmortems(tester);
    await tapKey(tester, 'pm-problem-7');
    expect(key('pm-reveal-problem'), findsOneWidget);
    expect(find.text('find-the-pivot-integer'), findsOneWidget);
    expect(find.textContaining('Post-theory miss, 11 minutes'), findsOneWidget);
    await tapKey(tester, 'pm-problem-7');
    expect(key('pm-reveal-problem'), findsNothing);
  });

  testWidgets('unknown minutes show ?, one-shot and phase marks differ', (
    tester,
  ) async {
    await openPostmortems(tester);
    Finder inRow(int i, Finder f) =>
        find.descendant(of: key('pm-problem-$i'), matching: f);
    expect(inRow(0, find.text(kUnknown)), findsOneWidget);
    expect(inRow(0, find.byIcon(Icons.history)), findsOneWidget);
    expect(inRow(3, find.byIcon(Icons.bolt)), findsOneWidget);
    expect(inRow(9, find.byIcon(Icons.school)), findsOneWidget);
    expect(inRow(9, find.text('18')), findsOneWidget);
  });

  testWidgets('a kept chip lists the one-shot solves that used it', (
    tester,
  ) async {
    await openPostmortems(tester);
    await tapKey(tester, 'pm-card-9');
    expect(key('pm-reveal-card'), findsOneWidget);
    expect(find.text('running-sum-of-1d-array'), findsOneWidget);
    expect(find.text('ant-on-the-boundary'), findsOneWidget);
    await tapKey(tester, 'pm-card-8');
    expect(find.textContaining('Recited without a miss'), findsOneWidget);
    expect(find.text('running-sum-of-1d-array'), findsNothing);
  });

  testWidgets('a bar selects its unit and names it; again shows the newest', (
    tester,
  ) async {
    await openPostmortems(tester);
    await tapKey(tester, 'pm-problem-0');
    await tapKey(tester, 'pm-bar-0');
    expect(find.text('two-pointers'), findsOneWidget);
    expect(key('pm-problem-3'), findsOneWidget);
    expect(key('pm-problem-4'), findsNothing);
    expect(key('pm-reveal-problem'), findsNothing);
    expect(find.byIcon(Icons.push_pin_outlined), findsOneWidget);
    await tapKey(tester, 'pm-bar-0');
    expect(key('pm-reveal-unit'), findsNothing);
    expect(key('pm-problem-9'), findsOneWidget);
  });

  testWidgets('no report yet is the glyph alone', (tester) async {
    await openPostmortems(tester, answer: withPostmortems(const <Object>[]));
    expect(key('pm-empty'), findsOneWidget);
    expect(find.byType(OneShotBars), findsNothing);
  });

  testWidgets('an unknown section shows ? in every card', (tester) async {
    await openPostmortems(tester, answer: 'snapshot_full');
    expect(find.text(kUnknown), findsNWidgets(3));
  });

  testWidgets('dropped detail and empty lists read differently', (
    tester,
  ) async {
    await openPostmortems(
      tester,
      answer: withPostmortems([
        {'unit': 'a', 'post': null, 'problems': null, 'cards': <Object>[]},
        {
          'unit': 'b',
          'post': [1, 2],
          'problems': <Object>[],
          'cards': null,
        },
      ]),
    );
    // b: an empty grid, unknown chips; a's bar is unknown too.
    expect(find.text(kNoneRecorded), findsOneWidget);
    expect(find.text(kUnknown), findsNWidgets(2));
    await tapKey(tester, 'pm-bar-0');
    // a: the unknown bar's `?`, the grid's `?`, no chips yet.
    expect(find.text(kUnknown), findsNWidgets(2));
    expect(find.text(kNoneRecorded), findsOneWidget);
  });

  testWidgets('a problem with no phase marks it unknown', (tester) async {
    await openPostmortems(
      tester,
      answer: withPostmortems([
        {
          'unit': 'u',
          'post': [1, 1],
          'problems': [
            {'slug': 's', 'tries': 0, 'minutes': 3, 'one_shot': true},
          ],
        },
      ]),
    );
    final row = key('pm-problem-0');
    expect(
      find.descendant(of: row, matching: find.text(kUnknown)),
      findsOneWidget,
    );
  });

  testWidgets('phone: one section per chip, the grid behind its chip', (
    tester,
  ) async {
    await openPostmortems(tester, size: kPhone);
    expect(find.byType(CardPages), findsOneWidget);
    expect(key('pm-bar-0'), findsOneWidget);
    await tester.tap(find.byKey(const Key('pm-section-grid')));
    await tester.pumpAndSettle();
    expect(key('pm-problem-0'), findsOneWidget);
    expect(find.byType(SectionCard), findsOneWidget);
  });

  testWidgets('many units scroll sideways at the minimum slot', (tester) async {
    await openPostmortems(
      tester,
      answer: withPostmortems([
        for (var i = 0; i < 40; i++)
          {
            'unit': 'u$i',
            'post': [i % 4, 3],
          },
      ]),
    );
    expect(tester.getSize(key('pm-bar-0')).width, kMinSlot);
  });
}
