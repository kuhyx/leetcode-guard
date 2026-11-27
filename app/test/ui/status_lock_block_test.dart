// The lock block: the PC lock's unit and rows, on top of the Status tab
// while today is unpaid.
import 'dart:convert';

import 'package:design_system/design_system.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/difficulty_mark.dart';
import 'package:leetcode_guard/src/ui/status_lock_block.dart';
import 'package:material_ui/material_ui.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';
import '../support/text_scan.dart';

/// The solve fixture with its lock section replaced by [lock].
String _withLock(Object? lock) {
  final json = jsonDecode(fixtureText('snapshot_lock_solve')) as Map;
  (json['status'] as Map)['lock'] = lock;
  return jsonEncode(json);
}

Map<String, Object?> _problem(int i) => {
  'kind': 'problem',
  'title': 'Problem $i',
  'difficulty': 'Medium',
  'url': 'https://leetcode.com/problems/problem-$i/',
};

void main() {
  testWidgets('an unpaid SOLVE lock lists its problems in order', (
    tester,
  ) async {
    final opened = <Uri>[];
    await pumpApp(tester, answers: ['snapshot_lock_solve'], opened: opened);
    final block = find.byType(StatusLockBlock);
    expect(block, findsOneWidget);
    expect(
      find.descendant(of: block, matching: find.text('Prefix sums')),
      findsOneWidget,
    );
    final titles = [
      'Range Sum Query - Immutable',
      'Subarray Sum Equals K',
      'Count of Range Sum',
    ];
    final ys = [for (final t in titles) tester.getCenter(find.text(t)).dy];
    expect(ys, orderedEquals([...ys]..sort()));
    final marks = find.descendant(
      of: block,
      matching: find.byType(DifficultyMark),
    );
    expect(
      [for (final e in marks.evaluate()) (e.widget as DifficultyMark).level],
      ['Easy', 'Medium', 'Hard'],
    );
    await tester.tap(find.text('Subarray Sum Equals K'));
    await tester.tap(find.byKey(kLockLearnKey));
    expect(opened, [
      Uri.parse('https://leetcode.com/problems/subarray-sum-equals-k/'),
      Uri.parse('kuhytutor://learn/arrays/prefix-sums'),
    ]);
    expectNoWords([block], {'Prefix sums', ...titles}, where: 'lock block');
  });

  testWidgets('a review row shows the count and opens the tutor review', (
    tester,
  ) async {
    final opened = <Uri>[];
    await pumpApp(tester, answers: ['snapshot_lock_review'], opened: opened);
    expect(find.byKey(kLockLearnKey), findsNothing);
    final review = find.byKey(const Key('lock-row-0'));
    expect(
      find.descendant(of: review, matching: find.byIcon(Icons.refresh)),
      findsOneWidget,
    );
    expect(
      find.descendant(of: review, matching: find.text('3')),
      findsOneWidget,
    );
    await tester.tap(review);
    expect(opened, [Uri.parse('kuhytutor://review/arrays/prefix-sums')]);
  });

  for (final (name, answer) in [
    ('paid today', _withLock({'unpaid': false, 'unit': 'Prefix sums'})),
    ('no lock section', fixtureText('snapshot_full')),
    ('a malformed lock', _withLock(['unpaid'])),
  ]) {
    testWidgets('$name: no block', (tester) async {
      await pumpApp(tester, answers: [answer]);
      expect(find.byType(StatusLockBlock), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('a link no app takes marks its row, never a silent no-op', (
    tester,
  ) async {
    final opened = <Uri>[];
    await pumpApp(
      tester,
      answers: ['snapshot_lock_solve'],
      opened: opened,
      opens: false,
    );
    final row = find.byKey(const Key('lock-row-1'));
    expect(
      find.descendant(of: row, matching: find.byIcon(Icons.link_off)),
      findsNothing,
    );
    await tester.tap(row);
    await tester.pump();
    expect(opened, hasLength(1));
    expect(
      find.descendant(of: row, matching: find.byIcon(Icons.link_off)),
      findsOneWidget,
    );
    expect(
      find.descendant(of: row, matching: find.byIcon(Icons.open_in_new)),
      findsNothing,
    );
    await tester.tap(find.byKey(kLockLearnKey));
    await tester.pump();
    expect(
      find.descendant(
        of: find.byKey(kLockLearnKey),
        matching: find.byIcon(Icons.link_off),
      ),
      findsOneWidget,
    );
  });

  testWidgets('unsafe targets are not tappable', (tester) async {
    final opened = <Uri>[];
    await pumpApp(
      tester,
      opened: opened,
      answers: [
        _withLock({
          'unpaid': true,
          'unit': '',
          'learn_route': '/settings',
          'rows': [
            {
              'kind': 'problem',
              'title': 'Odd',
              'difficulty': 'Easy',
              'url': 'javascript:x',
            },
            {'kind': 'review', 'count': 2, 'route': '//evil'},
          ],
        }),
      ],
    );
    expect(find.byKey(kLockLearnKey), findsNothing);
    await tester.tap(find.text('Odd'));
    await tester.tap(find.byKey(const Key('lock-row-1')));
    expect(opened, isEmpty);
  });

  testWidgets('many rows at a large text scale never squeeze the tab', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final rows = [for (var i = 0; i < 8; i++) _problem(i)];
    await pumpApp(
      tester,
      answers: [
        _withLock({'unpaid': true, 'unit': 'Prefix sums', 'rows': rows}),
      ],
    );
    expect(tester.takeException(), isNull);
    final block = tester.getSize(find.byType(StatusLockBlock));
    // The card itself is capped; its bottom margin sits outside the cap.
    expect(
      block.height,
      lessThanOrEqualTo(kPhone.height * kLockMaxHeightShare + AppSpacing.md),
    );
    // The section below keeps room for its chips and content.
    expect(find.byType(ChoiceChip).first.hitTestable(), findsOneWidget);
    expect(
      tester.getSize(find.byKey(const Key('tab-content'))).height,
      greaterThan(kPhone.height * 0.3),
    );
  });
}
