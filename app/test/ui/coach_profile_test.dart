import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/coach_tab.dart';
import 'package:leetcode_guard/src/ui/difficulty_mark.dart';
import 'package:leetcode_guard/src/ui/profile_tab.dart';
import 'package:leetcode_guard/src/ui/projection_section.dart';

import '../support/coach_labels.dart';
import '../support/pump.dart';

Finder _value(String label) => find.descendant(
  of: find.byKey(Key('row-$label')),
  matching: find.byKey(const Key('value')),
);

String _text(WidgetTester tester, String label) =>
    tester.widget<Text>(_value(label)).data!;

void main() {
  const tall = Size(390, 4000);

  testWidgets('profile: split, streaks, acceptance, heatmap', (tester) async {
    await pumpApp(tester, size: tall);
    await openTab(tester, kProfileTab);
    expect(_text(tester, 'Easy'), '120 / 900');
    expect(_text(tester, 'Medium'), '150 / 1900');
    expect(_text(tester, 'Hard'), '42 / 850');
    expect(_text(tester, 'Current streak in days'), '5');
    expect(_text(tester, 'Longest streak in days'), '30');
    expect(_text(tester, 'Accepted'), '61.2%');
    expect(find.byKey(const Key('heatmap')), findsOneWidget);
    expect(_text(tester, 'Submissions in the last 52 weeks'), '3');
    final fetched = DateTime.parse('2026-10-23T14:01:37+02:00');
    expect(
      find.descendant(
        of: find.byKey(const Key('profile-fetched-at')),
        matching: find.text(asOf(fetched)),
      ),
      findsOneWidget,
    );
  });

  testWidgets('difficulty rows paint diamonds by credit weight', (
    tester,
  ) async {
    await pumpApp(tester, size: tall);
    await openTab(tester, kProfileTab);
    final tab = find.byType(ProfileTab);
    for (final (level, weight) in [('Easy', 1), ('Medium', 2), ('Hard', 4)]) {
      final row = find.byKey(Key('row-$level'));
      expect(
        find.descendant(of: row, matching: find.byIcon(Icons.diamond)),
        findsNWidgets(weight),
        reason: level,
      );
      expect(
        find.descendant(of: tab, matching: find.text(level)),
        findsNothing,
      );
    }
    final mark = tester.widget<DifficultyMark>(
      find.descendant(
        of: find.byKey(const Key('row-Hard')),
        matching: find.byType(DifficultyMark),
      ),
    );
    final colour = tester
        .widget<Icon>(
          find
              .descendant(
                of: find.byKey(const Key('row-Hard')),
                matching: find.byIcon(Icons.diamond),
              )
              .first,
        )
        .color;
    expect(mark.semanticLabel, 'Hard');
    expect(
      colour,
      DifficultyMark.color(tester.element(find.byType(ProfileTab)), 'Hard'),
    );
  });

  testWidgets('the real exporter snapshot renders every tab', (tester) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_real']);
    expect(find.byType(ProjectionSection), findsOneWidget);
    expect(tester.takeException(), isNull);
    await openTab(tester, kCoachTab);
    expect(byLabel(kHowToTitle), findsWidgets);
    expect(find.text('0 / 4'), findsNWidgets(6));
    expect(
      find.descendant(of: find.byType(CoachTab), matching: find.text(kUnknown)),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
    await openTab(tester, kProfileTab);
    expect(find.byKey(const Key('heatmap')), findsOneWidget);
    // The real export has every profile field: nothing unknown.
    expect(
      find.descendant(
        of: find.byType(ProfileTab),
        matching: find.text(kUnknown),
      ),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('profile heatmap fits the phone width', (tester) async {
    await pumpApp(tester);
    await openTab(tester, kProfileTab);
    final chip = find.descendant(
      of: find.byType(ChoiceChip),
      matching: find.byKey(const Key('section-submission-calendar')),
    );
    await tester.ensureVisible(chip);
    await tester.tap(chip);
    await tester.pumpAndSettle();
    final size = tester.getSize(find.byKey(const Key('heatmap')));
    expect(size.width, lessThanOrEqualTo(390));
    expect(tester.takeException(), isNull);
  });

  testWidgets('profile null: unknown, never 0', (tester) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_nulls']);
    await openTab(tester, kProfileTab);
    final tab = find.byType(ProfileTab);
    expect(
      find.descendant(of: tab, matching: find.text(kUnknown)),
      findsNWidgets(4),
    );
    expect(find.descendant(of: tab, matching: find.text('0')), findsNothing);
    expect(find.byKey(const Key('heatmap')), findsNothing);
  });

  testWidgets('profile sparse: partial split and unknown calendar', (
    tester,
  ) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_sparse']);
    await openTab(tester, kProfileTab);
    expect(_text(tester, 'Easy'), kUnknown);
    expect(_text(tester, 'Medium'), kUnknown);
    expect(_text(tester, 'Current streak in days'), kUnknown);
    expect(find.byKey(const Key('heatmap')), findsNothing);
  });
}
