import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/coach_tab.dart';

import '../support/coach_labels.dart';
import '../support/coach_pump.dart';
import '../support/pump.dart';

Finder _inTab(Finder f) =>
    find.descendant(of: find.byType(CoachTab), matching: f);

void main() {
  group('with sessions', () {
    testWidgets('problems, re-tests with their command, cluster progress', (
      tester,
    ) async {
      await pumpApp(tester, size: kTallCoach);
      await openCoach(tester);
      expect(byLabel(kHowToTitle), findsNothing);
      expect(find.text('missing-number'), findsNWidgets(2));
      expect(byLabel('bit-cancellation'), findsWidgets);
      expect(find.text('2026-10-23'), findsOneWidget);
      expect(numeralIn('req-first-missing-number', '✓'), findsOneWidget);
      expect(numeralIn('rung-single-number-iii', 'H3'), findsOneWidget);
      expect(byLabel('Hint rung, revealed'), findsOneWidget);
      expect(byLabel('Requirements check: incomplete'), findsOneWidget);
      expect(find.text('2026-10-26'), findsOneWidget);
      expect(find.text('leetcode --retest missing-number'), findsOneWidget);
      expect(find.text('1 / 4'), findsOneWidget);
      expect(
        numeralIn('next-bit-cancellation', 'Majority Element'),
        findsOneWidget,
      );
    });

    testWidgets('a re-test row without a command shows none', (tester) async {
      await pumpApp(
        tester,
        size: kTallCoach,
        answers: [
          snapshotWith(
            '{"problems": [{"slug": "a"}], '
            '"retests_due": [{"slug": "a", "due": "2026-10-26"}], '
            '"clusters": null}',
          ),
        ],
      );
      await openCoach(tester);
      expect(find.text('2026-10-26'), findsOneWidget);
      expect(find.textContaining('leetcode --retest'), findsNothing);
      expect(find.text(kUnknown), findsWidgets);
    });

    testWidgets(
      'clusters: unknown ones stay unknown, order falls back to name',
      (tester) async {
        await pumpApp(tester, size: kTallCoach);
        await openCoach(tester);
        final ys = [
          for (final n in const [
            'bit-cancellation',
            'two-pointers',
            'intervals',
            'sliding-window',
          ])
            tester.getTopLeft(find.byKey(Key('row-$n'))).dy,
        ];
        expect(ys, [...ys]..sort());
        expect(ys.toSet(), hasLength(4));
        expect(
          find.descendant(
            of: find.byKey(const Key('row-sliding-window')),
            matching: find.text(kUnknown),
          ),
          findsOneWidget,
        );
        expect(find.text('0 / 2'), findsOneWidget);
      },
    );

    testWidgets('only a LeetCode problem page is tappable', (tester) async {
      final opened = <Uri>[];
      await pumpApp(tester, size: kTallCoach, opened: opened);
      await openCoach(tester);
      await tester.tap(find.byKey(const Key('problem-missing-number')));
      await tester.tap(
        find.byKey(const Key('problem-container-with-most-water')),
      );
      await tester.pumpAndSettle();
      expect(opened, [
        Uri.parse('https://leetcode.com/problems/missing-number/'),
      ]);
      // An untitled problem falls back to its slug.
      expect(find.text('container-with-most-water'), findsOneWidget);
    });

    testWidgets('read-only: no control other than copy and links', (
      tester,
    ) async {
      await pumpApp(tester, size: kTallCoach);
      await openCoach(tester);
      expect(find.byType(ElevatedButton), findsNothing);
      expect(find.byType(FilledButton), findsNothing);
      expect(find.byType(TextButton), findsNothing);
      expect(find.byKey(const Key('copy-command')), findsNothing);
    });
  });

  group('unknown is for a coach section that is really null', () {
    testWidgets('null coach: unknown plus why, nothing else', (tester) async {
      await pumpApp(tester, size: kTallCoach, answers: ['snapshot_nulls']);
      await openCoach(tester);
      expect(_inTab(find.text(kUnknown)), findsOneWidget);
      expect(byLabel(kCoachWhy), findsOneWidget);
      expect(find.byIcon(Icons.sync_problem), findsOneWidget);
      expect(find.text('0'), findsNothing);
      expect(byLabel(kHowToTitle), findsNothing);
    });

    testWidgets('no snapshot at all reads as unknown too', (tester) async {
      await pumpApp(tester, size: kTallCoach, answers: [null]);
      await openCoach(tester);
      expect(_inTab(find.text(kUnknown)), findsOneWidget);
    });
  });
}
