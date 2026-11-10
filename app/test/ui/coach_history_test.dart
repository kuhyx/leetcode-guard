import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/ui/coach_grade.dart';

import '../support/coach_labels.dart';
import '../support/coach_pump.dart';
import '../support/pump.dart';

const _coach = '''
{"problems": [
  {"slug": "missing-number", "cluster": "bit-cancellation", "day": "2026-10-23",
   "max_rung": "H2", "revealed": false, "req_before_code": true,
   "req_check": "pass", "accepted": true,
   "grades": {
     "constraint": {"grade": "pass", "attempts": 2, "forced": false, "via": "haiku"},
     "requirements": {"grade": "partial", "attempts": 3, "forced": true, "via": "haiku"},
     "toolbox": null,
     "postmortem": {"grade": "pass", "attempts": 1, "forced": false, "via": "unverified"}}},
  {"slug": "two-sum", "cluster": "two-pointers", "day": "2026-10-22",
   "max_rung": null, "grades": null, "accepted": null}],
 "retests_due": [], "clusters": {}}
''';

void main() {
  testWidgets('history: the four grades and the highest rung per session', (
    tester,
  ) async {
    await pumpApp(tester, size: kTallCoach, answers: [snapshotWith(_coach)]);
    await openCoach(tester);
    // Each graded step: spoken as before, painted as mark + pill + count.
    expect(byLabel('Constraint: pass, 2 tries'), findsOneWidget);
    expect(byLabel('Requirements: partial, forced, 3 tries'), findsOneWidget);
    expect(byLabel('Toolbox: not graded'), findsOneWidget);
    expect(byLabel('Post-mortem: pass, not checked, 1 try'), findsOneWidget);
    Finder inRow(int n, Finder f) => find.descendant(
      of: find.byKey(Key('grades-missing-number-$n')),
      matching: f,
    );
    expect(inRow(1, find.byType(GradeBadge)), findsOneWidget);
    expect(inRow(1, find.text('2')), findsOneWidget);
    expect(inRow(2, find.byIcon(Icons.redo)), findsOneWidget);
    expect(inRow(3, find.byType(GradeBadge)), findsNothing);
    expect(inRow(3, find.text('–')), findsOneWidget);
    expect(inRow(5, find.byIcon(Icons.help_outline)), findsOneWidget);
    expect(numeralIn('accepted-missing-number', '✓'), findsOneWidget);
    expect(numeralIn('rung-missing-number', 'H2'), findsOneWidget);
    // A CLI-only session: grades unknown, never zero.
    expect(numeralIn('row-Grades', kUnknown), findsOneWidget);
    expect(byLabel('Accepted on LeetCode'), findsOneWidget);
    expect(byLabelContaining('0 tries'), findsNothing);
  });

  test('grades parse tolerantly: missing is unknown, not zero', () {
    final p = CoachProblem.fromJson({
      'grades': {
        'constraint': {'grade': 'bogus', 'attempts': 'x'},
        'toolbox': 7,
      },
      'accepted': 'yes',
    });
    expect(p.accepted, isNull);
    expect(p.grades!['constraint']!.grade, isNull);
    expect(p.grades!['constraint']!.attempts, isNull);
    expect(p.grades!['toolbox'], isNull);
    expect(CoachProblem.fromJson({}).grades, isNull);
  });

  testWidgets('a grade with unknown fields still renders', (tester) async {
    await pumpApp(
      tester,
      size: kTallCoach,
      answers: [
        snapshotWith(
          '{"problems": [{"slug": "a", "grades": '
          '{"constraint": {"grade": null}}}], "clusters": {}}',
        ),
      ],
    );
    await openCoach(tester);
    expect(byLabel('Constraint: $kUnknown'), findsOneWidget);
    expect(find.byType(Scrollable), findsWidgets);
  });
}
