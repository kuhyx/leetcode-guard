import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/coach_pump.dart';
import '../support/pump.dart';

void main() {
  group('no sessions yet is a known state', () {
    testWidgets('How to start: method, first command, clusters at zero', (
      tester,
    ) async {
      await pumpApp(
        tester,
        size: kTallCoach,
        answers: ['snapshot_coach_empty'],
      );
      await openCoach(tester);
      expect(find.text('How to start'), findsOneWidget);
      expect(find.text('1. Constraint'), findsOneWidget);
      expect(
        find.text('Turn the hard constraint into a rule for the design.'),
        findsOneWidget,
      );
      expect(find.text('4. Post-mortem'), findsOneWidget);
      expect(find.byKey(const Key('command-box')), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(const Key('command-box')),
          matching: find.text('leetcode --cluster bit-cancellation'),
        ),
        findsOneWidget,
      );
      expect(find.text('leetcode report'), findsOneWidget);
      expect(find.text('0 / 4'), findsNWidgets(6));
      expect(find.text('Next: Missing Number'), findsOneWidget);
      expect(find.text('Missing Number'), findsOneWidget);
      expect(find.text('#268'), findsOneWidget);
      expect(find.text('unknown'), findsNothing);
      expect(find.text('Problems'), findsNothing);
      expect(find.text('Re-tests due'), findsNothing);
      expect(find.textContaining("hasn't published"), findsNothing);
    });

    testWidgets('the copy button puts the first command on the clipboard', (
      tester,
    ) async {
      final copied = recordClipboard(tester);
      await pumpApp(
        tester,
        size: kPhoneCoach,
        answers: ['snapshot_coach_empty'],
      );
      await openCoach(tester);
      await tester.tap(find.byKey(const Key('copy-command')));
      await tester.pumpAndSettle();
      expect(copied, ['leetcode --cluster bit-cancellation']);
      expect(find.text('Copied'), findsOneWidget);
    });

    testWidgets('clusters come in curriculum order, not key order', (
      tester,
    ) async {
      await pumpApp(
        tester,
        size: kTallCoach,
        answers: ['snapshot_coach_empty'],
      );
      await openCoach(tester);
      final names = [
        for (final name in const [
          'bit-cancellation',
          'two-pointers',
          'sliding-window',
          'prefix-sum-hash',
          'monotonic-stack',
          'intervals',
        ])
          tester.getTopLeft(find.byKey(Key('row-$name'))).dy,
      ];
      expect(names, [...names]..sort());
    });

    testWidgets('a problem opens its LeetCode page', (tester) async {
      final opened = <Uri>[];
      await pumpApp(
        tester,
        size: kTallCoach,
        answers: ['snapshot_coach_empty'],
        opened: opened,
      );
      await openCoach(tester);
      await tester.tap(find.byKey(const Key('problem-3sum')));
      await tester.pumpAndSettle();
      expect(opened, [Uri.parse('https://leetcode.com/problems/3sum/')]);
    });

    testWidgets('fits a 412 px phone without overflow', (tester) async {
      await pumpApp(
        tester,
        size: kPhoneCoach,
        answers: ['snapshot_coach_empty'],
      );
      await openCoach(tester);
      expect(tester.takeException(), isNull);
    });

    for (final (width, columns) in [(1400.0, 2), (2400.0, 3)]) {
      testWidgets('lays out in $columns columns at ${width.toInt()} px', (
        tester,
      ) async {
        await pumpApp(
          tester,
          size: Size(width, 2400),
          answers: ['snapshot_coach_empty'],
        );
        await openCoach(tester);
        final lefts = {
          for (final key in const [
            Key('row-bit-cancellation'),
            Key('row-two-pointers'),
            Key('row-sliding-window'),
          ])
            tester.getTopLeft(find.byKey(key)).dx,
        };
        expect(lefts, hasLength(columns));
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('an old exporter without how_to shows it as unknown', (
      tester,
    ) async {
      await pumpApp(
        tester,
        size: kTallCoach,
        answers: [
          snapshotWith('{"problems": [], "retests_due": [], "clusters": {}}'),
        ],
      );
      await openCoach(tester);
      expect(find.text('How to start'), findsOneWidget);
      expect(find.text('unknown'), findsOneWidget);
      expect(find.byKey(const Key('command-box')), findsNothing);
      expect(find.text('None recorded'), findsOneWidget);
    });

    testWidgets('how_to without a first command still lists the commands', (
      tester,
    ) async {
      await pumpApp(
        tester,
        size: kTallCoach,
        answers: [
          snapshotWith(
            '{"problems": [], "retests_due": [], "clusters": {}, '
            '"how_to": {"commands": [{"command": "leetcode due", '
            '"meaning": "List them."}], "steps": null, '
            '"first_command": null}}',
          ),
        ],
      );
      await openCoach(tester);
      expect(find.text('leetcode due'), findsOneWidget);
      expect(find.text('List them.'), findsOneWidget);
      expect(find.byKey(const Key('command-box')), findsNothing);
    });
  });
}
