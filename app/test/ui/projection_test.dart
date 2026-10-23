import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/pump.dart';

Finder _value(String label) => find.descendant(
  of: find.byKey(Key('row-$label')),
  matching: find.byKey(const Key('value')),
);

/// The date control's label (the same date can also be a row value).
Finder _date(String key) => find.descendant(
  of: find.byKey(const Key('projection-date')),
  matching: find.text(key),
);

String _text(WidgetTester tester, String label) =>
    tester.widget<Text>(_value(label)).data!;

void main() {
  const tall = Size(390, 9000);

  testWidgets('defaults to the earliest precomputed date', (tester) async {
    await pumpApp(tester, size: tall);
    expect(find.text('312 / 4055'), findsOneWidget);
    expect(_date('2026-10-24'), findsOneWidget);
    expect(_text(tester, 'Projected solved'), '313');
    expect(_text(tester, 'Gated days'), '1');
    expect(_text(tester, 'Rules demand'), '2');
  });

  testWidgets('arrows step through the published keys', (tester) async {
    await pumpApp(tester, size: tall);
    await tester.tap(find.byTooltip('Later date'));
    await tester.pumpAndSettle();
    expect(_date('2026-10-31'), findsOneWidget);
    expect(_text(tester, 'Projected solved'), '333');
    expect(_text(tester, 'Debt'), '2');
    await tester.tap(find.byTooltip('Later date'));
    await tester.pumpAndSettle();
    expect(_text(tester, 'Free days'), '1');
    // The last key: "later" is disabled rather than wrapping around.
    await tester.tap(find.byTooltip('Later date'));
    await tester.pumpAndSettle();
    expect(_date('2026-11-30'), findsOneWidget);
    await tester.tap(find.byTooltip('Earlier date'));
    await tester.pumpAndSettle();
    expect(_date('2026-10-31'), findsOneWidget);
  });

  testWidgets('the date picker only offers published dates', (tester) async {
    await pumpApp(tester, size: tall);
    await tester.tap(_date('2026-10-24'));
    await tester.pumpAndSettle();
    expect(find.byType(DatePickerDialog), findsOneWidget);
    // 25 Oct has no projection: not selectable.
    await tester.tap(find.text('25'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('31'));
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(_text(tester, 'Projected solved'), '333');
  });

  testWidgets('cancelling the picker keeps the date', (tester) async {
    await pumpApp(tester, size: tall);
    await tester.tap(_date('2026-10-24'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(_text(tester, 'Projected solved'), '313');
  });

  testWidgets('a new snapshot without the chosen key falls back', (
    tester,
  ) async {
    final c = await pumpApp(
      tester,
      size: tall,
      answers: [
        'snapshot_full',
        jsonEncode({
          'generated_at': '2026-10-23T14:05:00+02:00',
          'projections': {
            '2026-12-31': {
              'projected': {'Easy': 500},
            },
          },
          'progress': {'solved_all': 1},
        }),
      ],
    );
    await tester.tap(find.byTooltip('Later date'));
    await tester.pumpAndSettle();
    await c.refresh();
    await tester.pumpAndSettle();
    expect(_date('2026-12-31'), findsOneWidget);
    expect(_text(tester, 'Projected solved'), '500');
    expect(_text(tester, 'Gated days'), 'unknown');
    expect(find.text('unknown'), findsWidgets);
  });

  testWidgets('a key that is not a date still shows, picker disabled', (
    tester,
  ) async {
    await pumpApp(
      tester,
      size: tall,
      answers: [
        jsonEncode({
          'generated_at': '2026-10-23T14:05:00+02:00',
          'projections': {
            'someday': {'projected': null},
          },
        }),
      ],
    );
    expect(_date('someday'), findsOneWidget);
    await tester.tap(_date('someday'));
    await tester.pumpAndSettle();
    expect(find.byType(DatePickerDialog), findsNothing);
    expect(_text(tester, 'Projected solved'), 'unknown');
  });
}
