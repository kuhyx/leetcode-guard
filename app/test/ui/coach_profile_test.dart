import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/format.dart';

import '../support/pump.dart';

Future<void> _open(WidgetTester tester, String tab) async {
  await tester.tap(find.text(tab));
  await tester.pumpAndSettle();
}

void main() {
  const tall = Size(390, 4000);

  testWidgets('profile: split, streaks, acceptance, heatmap', (tester) async {
    await pumpApp(tester, size: tall);
    await _open(tester, 'Profile');
    expect(find.text('120 / 900'), findsOneWidget);
    expect(find.text('150 / 1900'), findsOneWidget);
    expect(find.text('42 / 850'), findsOneWidget);
    expect(find.text('5 days'), findsOneWidget);
    expect(find.text('30 days'), findsOneWidget);
    expect(find.text('61.2%'), findsOneWidget);
    expect(find.byKey(const Key('heatmap')), findsOneWidget);
    expect(find.text('3 submissions in the last 52 weeks'), findsOneWidget);
    final fetched = DateTime.parse('2026-10-23T14:01:37+02:00');
    expect(find.text('Profile ${asOf(fetched)}'), findsOneWidget);
  });

  testWidgets('the real exporter snapshot renders every tab', (tester) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_real']);
    expect(find.text('Unlocked (already-charged)'), findsOneWidget);
    await _open(tester, 'Coach');
    expect(find.text('How to start'), findsOneWidget);
    expect(find.text('0 / 4'), findsNWidgets(6));
    expect(find.text('unknown'), findsNothing);
    await _open(tester, 'Profile');
    expect(find.byKey(const Key('heatmap')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('profile heatmap fits the phone width', (tester) async {
    await pumpApp(tester);
    await _open(tester, 'Profile');
    final size = tester.getSize(find.byKey(const Key('heatmap')));
    expect(size.width, lessThanOrEqualTo(390));
    expect(tester.takeException(), isNull);
  });

  testWidgets('profile null: unknown, never 0', (tester) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_nulls']);
    await _open(tester, 'Profile');
    expect(find.text('unknown'), findsNWidgets(4));
    expect(find.text('0'), findsNothing);
    expect(find.byKey(const Key('heatmap')), findsNothing);
  });

  testWidgets('profile sparse: partial split and unknown calendar', (
    tester,
  ) async {
    await pumpApp(tester, size: tall, answers: ['snapshot_sparse']);
    await _open(tester, 'Profile');
    expect(find.text('unknown'), findsWidgets);
    expect(find.text('Easy'), findsOneWidget);
    expect(find.text('Medium'), findsOneWidget);
    expect(find.byKey(const Key('heatmap')), findsNothing);
  });
}
