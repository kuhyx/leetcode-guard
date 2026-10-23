import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/ids.dart';
import 'package:leetcode_guard/src/state/controller.dart';
import 'package:leetcode_guard/src/ui/app.dart';

import 'fake_coach_transport.dart';
import 'fakes.dart';
import 'fixtures.dart';

/// A desktop window at 4K with scale 2 (logical 1920x1080).
const kDesktopCoach = Size(1920, 1080);

/// The phone the session screen is designed for.
const kPhoneSession = Size(412, 915);

/// The app over a fake relay client, plus the handles a test drives.
class CoachRig {
  new(this.clock, this.transport, this.controller, this.opened);

  final TestClock clock;
  final FakeCoachTransport transport;
  final CoachController controller;
  final List<Uri> opened;
}

Future<CoachRig> pumpCoach(
  WidgetTester tester, {
  Size size = kDesktopCoach,
  bool phone = false,
  String snapshot = 'snapshot_full',
  void Function(FakeCoachTransport)? before,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final clock = TestClock();
  final transport = FakeCoachTransport(clock, phone: phone);
  before?.call(transport);
  final coach = CoachController(
    transport: transport,
    devices: FixedDeviceId(),
    ulid: UlidGenerator(now: () => clock.ms),
    clock: clock.call,
  );
  final opened = <Uri>[];
  await tester.pumpWidget(
    LeetGuardApp(
      controller: StatusController(
        source: FakeSource([fixtureText(snapshot)]),
        cache: MemoryCache(),
        clock: clockAfter(1),
      ),
      coach: coach,
      openUrl: (uri) async {
        opened.add(uri);
        return true;
      },
    ),
  );
  await tester.pumpAndSettle();
  return CoachRig(clock, transport, coach, opened);
}

/// Lets [seconds] pass on both the fake clock and the test's timers.
Future<void> wait(WidgetTester tester, CoachRig rig, int seconds) async {
  for (var i = 0; i < seconds; i++) {
    rig.clock.advance(const Duration(seconds: 1));
    await tester.pump(const Duration(seconds: 1));
  }
  await tester.pump();
}

/// Waits until no request is in flight and the 3 s pause is over.
Future<void> settle(WidgetTester tester, CoachRig rig) async {
  for (var i = 0; i < 12 && rig.controller.busy; i++) {
    await wait(tester, rig, 1);
  }
  await tester.pumpAndSettle();
}

/// Scrolls the first downward list until [finder] is built, then into view.
Future<void> bring(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty) {
    await tester.scrollUntilVisible(
      finder,
      300,
      scrollable: find
          .byWidgetPredicate(
            (w) => w is Scrollable && w.axisDirection == AxisDirection.down,
          )
          .first,
    );
  }
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

Future<void> tapKey(WidgetTester tester, String key) async {
  final finder = find.byKey(Key(key));
  await bring(tester, finder);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> typeInto(WidgetTester tester, String key, String text) async {
  final finder = find.byKey(Key(key));
  await bring(tester, finder);
  await tester.enterText(finder, text);
  await tester.pump();
}

/// Whether the button keyed [key] can be pressed.
Future<bool> enabled(WidgetTester tester, String key) async {
  final finder = find.byKey(Key(key));
  await bring(tester, finder);
  return tester.widget<ButtonStyleButton>(finder).onPressed != null;
}

Future<void> openCoachTab(WidgetTester tester) async {
  await tester.tap(find.text('Coach').first);
  await tester.pumpAndSettle();
}

/// Starts Missing Number from the Coach tab and lets the relay answer.
Future<void> startMissingNumber(WidgetTester tester, CoachRig rig) async {
  await openCoachTab(tester);
  await tapKey(tester, 'start-missing-number');
  await settle(tester, rig);
}

/// Grades step [n] with [answer] and waits for the result.
Future<void> gradeText(
  WidgetTester tester,
  CoachRig rig,
  int n,
  String answer,
) async {
  await typeInto(tester, 'answer-$n', answer);
  await tapKey(tester, 'submit-$n');
  await settle(tester, rig);
}

/// Passes steps 1-3 the quick way, leaving step 4 open.
Future<void> passToStep4(WidgetTester tester, CoachRig rig) async {
  await gradeText(tester, rig, 1, 'O(1) extra space');
  await typeInto(tester, 'property-0', 'x ^ x = 0');
  await tapKey(tester, 'add-property');
  await typeInto(tester, 'property-1', 'indices 0..n');
  await tapKey(tester, 'submit-2');
  await settle(tester, rig);
  await tapKey(tester, 'pick-XOR self-cancellation');
  await tapKey(tester, 'submit-3');
  await settle(tester, rig);
}
