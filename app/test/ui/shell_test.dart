import 'package:crdt_sync_flutter/crdt_sync_flutter.dart'
    show E2ePassphraseButton;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/data/snapshot_source.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/stale_banner.dart';

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
    // One chip per Status section, the first one selected.
    expect(find.byType(ChoiceChip), findsNWidgets(9));
    expect(
      tester.widget<ChoiceChip>(find.byType(ChoiceChip).first).selected,
      isTrue,
    );
  });

  testWidgets('the bar paints icons only and never a tooltip', (tester) async {
    await pumpApp(tester);
    final bar = tester.widget<NavigationBar>(find.byType(NavigationBar));
    expect(bar.labelBehavior, NavigationDestinationLabelBehavior.alwaysHide);
    for (final d in bar.destinations.cast<NavigationDestination>()) {
      expect(d.tooltip, isEmpty, reason: d.label);
    }
    // The selected tab is the filled icon, the others outlined.
    Finder inBar(IconData icon) => find.descendant(
      of: find.byType(NavigationBar),
      matching: find.byIcon(icon),
    );
    expect(inBar(Icons.shield), findsOneWidget);
    expect(inBar(kCoachTab), findsOneWidget);
    await openTab(tester, kProfileTab);
    expect(inBar(Icons.person), findsOneWidget);
    expect(inBar(kStatusTab), findsOneWidget);
  });

  testWidgets('narrow desktop: navigation rail and capped content width', (
    tester,
  ) async {
    // Rail, but below the grid breakpoint: one column, still capped.
    await pumpApp(tester, size: const Size(1000, 900));
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    final rail = tester.widget<NavigationRail>(find.byType(NavigationRail));
    expect(rail.labelType, NavigationRailLabelType.none);
    final list = tester.getSize(find.byKey(const Key('status-list')));
    expect(list.width, lessThanOrEqualTo(720));
  });

  testWidgets('tabs switch on both layouts', (tester) async {
    await pumpApp(tester);
    await openTab(tester, kCoachTab);
    expect(
      find.byWidgetPredicate(
        (w) => w is Icon && w.semanticLabel == 'Re-tests due',
      ),
      findsWidgets,
    );
    await openTab(tester, kProfileTab);
    expect(find.byKey(const Key('section-difficulty-split')), findsWidgets);
  });

  testWidgets('rail destinations switch tabs', (tester) async {
    await pumpApp(tester, size: kDesktop);
    await openTab(tester, kProfileTab);
    expect(find.byKey(const Key('profile-section-streaks')), findsWidgets);
  });

  testWidgets('older than ten minutes shows the stale banner', (tester) async {
    await pumpApp(tester, minutes: 25);
    expect(find.byKey(const Key('stale-banner')), findsOneWidget);
  });

  testWidgets('a failed refresh keeps data and says why', (tester) async {
    final c = await pumpApp(
      tester,
      size: const Size(390, 4000),
      answers: ['snapshot_full', const SnapshotUnavailable('network down')],
    );
    await c.refresh();
    await tester.pumpAndSettle();
    // The banner marks the failure by kind; the reason itself is spoken.
    final banner = tester.widget<StaleBanner>(find.byType(StaleBanner));
    expect(banner.spoken, contains('network down'));
    expect(find.byKey(const Key('failure-other')), findsOneWidget);
    expect(find.text('312 / 4055'), findsOneWidget);
  });

  testWidgets('no snapshot at all: banner and unknown, never 0', (
    tester,
  ) async {
    await pumpApp(tester, answers: [const SnapshotUnavailable('offline')]);
    expect(find.byKey(const Key('stale-banner')), findsOneWidget);
    expect(find.text(asOf(null)), findsOneWidget);
    expect(find.text('0'), findsNothing);
    expect(find.text(kUnknown), findsWidgets);
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
    await tester.tap(find.bySemanticsLabel('Sync account'));
    await tester.pumpAndSettle();
    expect(find.text('sign-in page'), findsOneWidget);
    expect(c.error, isNull);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(c.error, 'after settings');
  });

  testWidgets('no settings button on desktop', (tester) async {
    await pumpApp(tester);
    expect(find.bySemanticsLabel('Sync account'), findsNothing);
  });

  testWidgets('the E2E lock sits in the app bar, icon only', (tester) async {
    await pumpApp(
      tester,
      lockAction: const E2ePassphraseButton(locked: true),
    );
    final lock = find.descendant(
      of: find.byType(AppBar),
      matching: find.byIcon(Icons.lock),
    );
    expect(lock, findsOneWidget);
    expect(
      find.descendant(of: find.byType(AppBar), matching: find.byType(Text)),
      findsOneWidget, // the as-of age only
    );
  });

  testWidgets('no lock where the wrapper holds every secret', (tester) async {
    await pumpApp(tester);
    expect(find.byIcon(Icons.lock), findsNothing);
  });
}
