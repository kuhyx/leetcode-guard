import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/pump.dart';

const _headings = [
  'Right now',
  'Credits (tokens)',
  'Progress & projection',
  'Solves',
  'Days settled',
  'Escape budgets',
  'Ledger integrity',
  'Environment',
  'Suggested problems',
];

void main() {
  testWidgets('all nine sections render, in reading order', (tester) async {
    await pumpApp(tester, size: const Size(390, 9000));
    final tops = [
      for (final h in _headings) tester.getTopLeft(find.text(h)).dy,
    ];
    expect(tops, orderedEquals([...tops]..sort()));
  });

  testWidgets('verdict and credits from the full fixture', (tester) async {
    await pumpApp(tester, size: const Size(390, 9000));
    expect(find.text('Unlocked (settled)'), findsOneWidget);
    expect(find.text('2026-10-23 (Thursday), costs 2 credit(s)'), findsOne);
    expect(find.text('today is already paid for'), findsOneWidget);
    expect(find.text('2 available'), findsOneWidget);
    expect(find.text('Earned all-time'), findsOneWidget);
    expect(find.text('41'), findsOneWidget);
    expect(find.text('Debt outstanding'), findsOneWidget);
    expect(find.text('two-sum [javascript]'), findsOneWidget);
    expect(find.text('valid-anagram'), findsOneWidget);
    expect(find.text('Escape hatch: 1 of 3 used this week'), findsOneWidget);
    expect(find.text('next use waits 60 min, EXHAUSTED'), findsOneWidget);
    expect(find.text('statement cache warm'), findsOneWidget);
    expect(find.text('2026-10-22, 2026-10-21'), findsOneWidget);
    expect(
      find.text('1. Today was already settled by an earlier run.'),
      findsOneWidget,
    );
    expect(find.text('Problem pool: 4087 entries, 2.2 days old'), findsOne);
    expect(find.text('Sat 2026-10-24 09:00:00 CEST'), findsOneWidget);
  });

  testWidgets('locked verdict says how many to solve', (tester) async {
    await pumpApp(
      tester,
      answers: ['snapshot_stale'],
      minutes: -20,
      size: const Size(390, 9000),
    );
    expect(find.text('LOCKED: solve 2 more'), findsOneWidget);
  });

  testWidgets('null sections render unknown, never 0', (tester) async {
    await pumpApp(
      tester,
      answers: ['snapshot_nulls'],
      size: const Size(390, 9000),
    );
    for (final h in _headings) {
      expect(find.text(h), findsOneWidget);
    }
    expect(find.text('0'), findsNothing);
    expect(find.text('0 available'), findsNothing);
    expect(find.text('unknown'), findsNWidgets(_headings.length));
  });

  testWidgets('sparse status: unknown values and generic budget rows', (
    tester,
  ) async {
    await pumpApp(
      tester,
      answers: ['snapshot_sparse'],
      size: const Size(390, 9000),
    );
    expect(find.text('LOCKED: solve unknown more'), findsOneWidget);
    expect(find.text('unknown available'), findsOneWidget);
    expect(find.text('used: 1'), findsOneWidget);
    expect(find.text('None recorded'), findsNWidgets(3));
    expect(find.text('No projection dates published'), findsOneWidget);
    expect(find.text('Solved'), findsOneWidget);
  });

  testWidgets('an integrity object without "ok" is unknown, not off', (
    tester,
  ) async {
    await pumpApp(
      tester,
      size: const Size(390, 9000),
      answers: [
        jsonEncode({
          'generated_at': '2026-10-23T14:05:00+02:00',
          'status': {
            'integrity': {'tampered': 2},
            'days': <String, Object?>{},
          },
        }),
      ],
    );
    // No charged list at all is unknown, not "none".
    expect(
      find.descendant(
        of: find.ancestor(
          of: find.text('Days settled'),
          matching: find.byType(Column),
        ),
        matching: find.text('unknown'),
      ),
      findsWidgets,
    );
    expect(find.text('None recorded'), findsNothing);
    expect(find.text('OFF (key unreadable)'), findsNothing);
    expect(find.text('2'), findsOneWidget);
  });

  testWidgets('tapping a suggestion opens its URL', (tester) async {
    final opened = <Uri>[];
    await pumpApp(tester, opened: opened, size: const Size(390, 9000));
    await tester.tap(find.text('Single Number III'));
    expect(opened, [
      Uri.parse('https://leetcode.com/problems/single-number-iii/'),
    ]);
    expect(find.text('Medium, 52.0% accepted'), findsOneWidget);
  });

  testWidgets('a non-https suggestion is not tappable', (tester) async {
    final opened = <Uri>[];
    await pumpApp(
      tester,
      opened: opened,
      size: const Size(390, 9000),
      answers: [
        jsonEncode({
          'generated_at': '2026-10-23T14:05:00+02:00',
          'status': {
            'suggestions': [
              {'title': 'Odd', 'url': 'javascript:x'},
              {'title': 'None'},
            ],
          },
        }),
      ],
    );
    await tester.tap(find.text('Odd'));
    await tester.tap(find.text('None'));
    expect(opened, isEmpty);
  });
}
