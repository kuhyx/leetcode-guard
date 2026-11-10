import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/status_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

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

/// The card whose (spoken) title is [title]. The outermost one: the
/// projection section wraps a SectionCard of the same title.
Finder _card(String title) => find
    .byWidgetPredicate((w) => w is Titled && (w as Titled).cardTitle == title)
    .first;

/// The painted value of the row spoken as [label].
String _value(WidgetTester tester, String label) => tester
    .widget<Text>(
      find.descendant(
        of: find.byKey(Key('row-$label')),
        matching: find.byKey(const Key('value')),
      ),
    )
    .data!;

/// What the line under [key] says to a screen reader.
String _spoken(WidgetTester tester, Key key) => tester
    .widget<GlyphLine>(
      find.descendant(
        of: find.byKey(key),
        matching: find.byType(GlyphLine),
        matchRoot: true,
      ),
    )
    .spoken;

void main() {
  testWidgets('all nine sections render, in reading order', (tester) async {
    await pumpApp(tester, size: const Size(390, 9000));
    final tops = [for (final h in _headings) tester.getTopLeft(_card(h)).dy];
    expect(tops, orderedEquals([...tops]..sort()));
  });

  testWidgets('verdict and credits from the full fixture', (tester) async {
    await pumpApp(tester, size: const Size(390, 9000));
    expect(
      _spoken(tester, const Key('verdict')),
      'Unlocked (settled). today is already paid for',
    );
    expect(find.byIcon(Icons.lock_open), findsOneWidget);
    expect(_value(tester, 'Day'), '2026-10-23');
    expect(_value(tester, 'Cost'), '2');
    expect(_spoken(tester, const Key('available')), '2 available');
    expect(_value(tester, 'Earned all-time'), '43');
    expect(_value(tester, 'Debt outstanding'), '2');
    expect(find.text('two-sum [javascript]'), findsOneWidget);
    expect(find.text('valid-anagram'), findsOneWidget);
    expect(
      _spoken(tester, const Key('budget-escape')),
      'Escape hatch: 1 of 3 used this week, next use waits 10 min',
    );
    expect(find.text('1 / 3 (7d)'), findsOneWidget);
    expect(
      _spoken(tester, const Key('budget-incidents')),
      'Network incidents: 3 of 3 used, next use waits 60 min, EXHAUSTED',
    );
    expect(find.byKey(const Key('exhausted')), findsOneWidget);
    expect(find.text('60m'), findsOneWidget);
    expect(find.text('2026-10-22, 2026-10-21'), findsOneWidget);
    expect(_value(tester, 'Next fire'), '2026-10-24 09:00:00');
    expect(_value(tester, 'Gate in force'), '✓ 2026-08-04');
  });

  testWidgets('a long list shows a few rows, the rest in a sheet', (
    tester,
  ) async {
    await pumpApp(
      tester,
      answers: ['snapshot_real'],
      size: const Size(390, 9000),
    );
    expect(find.byKey(const Key('show-all-Recent solves')), findsOneWidget);
    await tester.tap(find.byKey(const Key('show-all-Recent solves')));
    await tester.pumpAndSettle();
    final sheet = find.byKey(const Key('sheet-Recent solves'));
    expect(
      find.descendant(of: sheet, matching: find.byType(DatedRow)),
      findsNWidgets(15),
    );
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('show-all-Suggested problems')));
    await tester.pumpAndSettle();
    final suggestions = find.byKey(const Key('sheet-Suggested problems'));
    expect(
      find.descendant(of: suggestions, matching: find.byType(InkWell)),
      findsNWidgets(14),
    );
  });

  testWidgets('the long text sits behind buttons, spoken, nothing dropped', (
    tester,
  ) async {
    await pumpApp(tester, size: const Size(390, 9000));
    await tester.tap(find.byKey(const Key('show-all-Right now')));
    await tester.pumpAndSettle();
    final why = tester.widget<GlyphLine>(find.byType(GlyphLine).last);
    expect(why.spoken, '1. Today was already settled by an earlier run.');
    expect(why.value, '1');
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('show-all-Environment')));
    await tester.pumpAndSettle();
    final notes = [
      for (final line in tester.widgetList<GlyphLine>(
        find.descendant(
          of: find.byKey(const Key('sheet-Environment')),
          matching: find.byType(GlyphLine),
        ),
      ))
        (line.spoken, line.value),
    ];
    expect(notes, contains(('statement cache warm', '')));
    expect(
      notes,
      contains(('Problem pool: 4087 entries, 2.2 days old', '4087 · 2.2')),
    );
    expect(notes, contains(('cookie valid until 2026-11-02', '2026-11-02')));
  });

  testWidgets('locked verdict: a red lock and how many to solve', (
    tester,
  ) async {
    await pumpApp(
      tester,
      answers: ['snapshot_stale'],
      minutes: -20,
      size: const Size(390, 9000),
    );
    expect(
      _spoken(tester, const Key('verdict')),
      'LOCKED: solve 2 more. no credit banked for today',
    );
    final lock = tester.widget<Icon>(find.byIcon(Icons.lock));
    expect(
      lock.color,
      Theme.of(tester.element(_card('Right now'))).colorScheme.error,
    );
    expect(
      find.descendant(
        of: find.byKey(const Key('verdict')),
        matching: find.text('2'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('null sections render unknown, never 0', (tester) async {
    await pumpApp(
      tester,
      answers: ['snapshot_nulls'],
      size: const Size(390, 9000),
    );
    for (final h in _headings) {
      expect(_card(h), findsOneWidget);
    }
    expect(find.text('0'), findsNothing);
    // Every status section but the projection (area B) is one '?'.
    expect(find.text(kUnknown), findsAtLeastNWidgets(_headings.length - 1));
  });

  testWidgets('sparse status: unknown values and generic budget rows', (
    tester,
  ) async {
    await pumpApp(
      tester,
      answers: ['snapshot_sparse'],
      size: const Size(390, 9000),
    );
    expect(
      _spoken(tester, const Key('verdict')),
      'LOCKED: solve $kUnknown more. Reason $kUnknown',
    );
    expect(_spoken(tester, const Key('available')), '$kUnknown available');
    expect(_spoken(tester, const Key('budget-escape')), 'escape, used: 1');
    expect(_spoken(tester, const Key('budget-incidents')), 'incidents: ?');
    expect(find.text(kNoneRecorded), findsAtLeastNWidgets(3));
    expect(_value(tester, 'HMAC checking'), show(false));
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
      find.descendant(of: _card('Days settled'), matching: find.text(kUnknown)),
      findsWidgets,
    );
    expect(find.text(kNoneRecorded), findsNothing);
    expect(find.byIcon(Icons.key_off), findsNothing);
    expect(_value(tester, 'HMAC checking'), kUnknown);
    expect(_value(tester, 'Tampered'), '2');
  });
}
