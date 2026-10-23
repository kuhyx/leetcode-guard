import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/format.dart';

import '../support/fixtures.dart';
import '../support/pump.dart';

void main() {
  testWidgets('phone: bottom navigation, as-of time, no banner when fresh', (
    tester,
  ) async {
    await pumpApp(tester);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(NavigationRail), findsNothing);
    expect(find.text(asOf(kGeneratedAt)), findsOneWidget);
    expect(find.byKey(const Key('stale-banner')), findsNothing);
    expect(find.text('Right now'), findsOneWidget);
  });

  testWidgets('desktop: navigation rail and capped content width', (
    tester,
  ) async {
    await pumpApp(tester, size: kDesktop);
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    final list = tester.getSize(find.byKey(const Key('status-list')));
    expect(list.width, lessThanOrEqualTo(720));
  });

  testWidgets('tabs switch on both layouts', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Coach'));
    await tester.pumpAndSettle();
    expect(find.text('Re-tests due'), findsOneWidget);
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    expect(find.text('Difficulty split'), findsOneWidget);
  });

  testWidgets('rail destinations switch tabs', (tester) async {
    await pumpApp(tester, size: kDesktop);
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    expect(find.text('Streaks'), findsOneWidget);
  });

  testWidgets('older than ten minutes shows the stale banner', (tester) async {
    await pumpApp(tester, minutes: 25);
    expect(find.byKey(const Key('stale-banner')), findsOneWidget);
    expect(find.textContaining('25 min old'), findsOneWidget);
  });

  testWidgets('a failed refresh keeps data and says why', (tester) async {
    final c = await pumpApp(
      tester,
      answers: ['snapshot_full', const SnapshotUnavailable('network down')],
    );
    await c.refresh();
    await tester.pumpAndSettle();
    expect(find.textContaining('network down'), findsOneWidget);
    expect(find.text('2 available'), findsOneWidget);
  });

  testWidgets('no snapshot at all: banner and unknown, never 0', (
    tester,
  ) async {
    await pumpApp(tester, answers: [const SnapshotUnavailable('offline')]);
    expect(find.textContaining('No snapshot yet'), findsOneWidget);
    expect(find.text('as of unknown'), findsOneWidget);
    expect(find.text('0'), findsNothing);
    expect(find.text('unknown'), findsWidgets);
  });

  testWidgets('polls again every minute', (tester) async {
    final c = await pumpApp(
      tester,
      answers: ['snapshot_full', const SnapshotUnavailable('later failure')],
    );
    await tester.pump(const Duration(seconds: 61));
    await tester.pumpAndSettle();
    expect(c.error, 'later failure');
  });

  testWidgets('settings opens the sign-in page and refreshes after', (
    tester,
  ) async {
    final c = await pumpApp(
      tester,
      answers: ['snapshot_full', const SnapshotUnavailable('after settings')],
      settingsBuilder: (_) =>
          Scaffold(appBar: AppBar(), body: const Text('sign-in page')),
    );
    await tester.tap(find.byTooltip('Sync account'));
    await tester.pumpAndSettle();
    expect(find.text('sign-in page'), findsOneWidget);
    expect(c.error, isNull);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(c.error, 'after settings');
  });

  testWidgets('no settings button on desktop', (tester) async {
    await pumpApp(tester);
    expect(find.byTooltip('Sync account'), findsNothing);
  });
}
