// The debug-only error trigger: a way to make the app throw on purpose, so
// the app-errors path (board report with the build) can be checked on the
// phone. Absent unless the build asks for it.
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';
import 'package:material_ui/material_ui.dart';

import '../support/fakes.dart';
import '../support/fixtures.dart';

Future<void> _pump(WidgetTester tester, {required bool debugThrow}) async {
  await tester.pumpWidget(
    LeetGuardApp(
      controller: StatusController(
        source: FakeSource([fixtureText('snapshot_full')]),
        cache: MemoryCache(),
        clock: clockAfter(1),
      ),
      openUrl: (_) async => true,
      debugThrow: debugThrow,
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  final trigger = find.byKey(const Key('debug-throw'));

  testWidgets('a normal build has no debug trigger', (tester) async {
    await _pump(tester, debugThrow: false);
    expect(trigger, findsNothing);
  });

  testWidgets('a debug build throws an uncaught StateError on tap', (
    tester,
  ) async {
    await _pump(tester, debugThrow: true);
    expect(trigger, findsOneWidget);
    await tester.tap(trigger);
    await tester.pump();
    expect(tester.takeException(), isA<StateError>());
    // The app stays up: the shell is still there after the throw.
    expect(trigger, findsOneWidget);
  });
}
