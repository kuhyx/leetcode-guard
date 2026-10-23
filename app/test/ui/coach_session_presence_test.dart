import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/transport.dart';

import '../support/coach_rig.dart';

const _down = CoachUnavailable(
  CoachOutage.relayDown,
  'coach service not running',
);

void main() {
  testWidgets('phone: a heartbeat older than 2 min is "PC offline" and '
      'greys the session controls', (tester) async {
    final rig = await pumpCoach(tester, size: kPhoneSession, phone: true);
    await startMissingNumber(tester, rig);
    expect(find.textContaining('PC offline'), findsNothing);
    expect(await enabled(tester, 'submit-1'), isFalse, reason: 'empty answer');
    await typeInto(tester, 'answer-1', 'O(1) space');
    expect(await enabled(tester, 'submit-1'), isTrue);

    rig.transport.relay.beatAge = const Duration(
      minutes: 2,
      seconds: 1,
    ).inMilliseconds;
    await wait(tester, rig, 5);
    expect(find.textContaining('PC offline'), findsOneWidget);
    expect(await enabled(tester, 'submit-1'), isFalse);
    // The last state stays on screen.
    expect(find.byKey(const Key('answer-1')), findsOneWidget);

    rig.transport.relay.beatAge = 0;
    await wait(tester, rig, 5);
    expect(find.textContaining('PC offline'), findsNothing);
    expect(await enabled(tester, 'submit-1'), isTrue);
  });

  testWidgets('phone: the Coach tab shows PC offline before any session', (
    tester,
  ) async {
    await pumpCoach(
      tester,
      size: kPhoneSession,
      phone: true,
      before: (t) =>
          t.relay.beatAge = const Duration(minutes: 5).inMilliseconds,
    );
    await openCoachTab(tester);
    expect(find.textContaining('PC offline'), findsOneWidget);
    expect(await enabled(tester, 'start-missing-number'), isFalse);
  });

  testWidgets('desktop: relay down names the service and how to start it', (
    tester,
  ) async {
    final rig = await pumpCoach(tester, before: (t) => t.outage = _down);
    await openCoachTab(tester);
    expect(find.text('Coach service not running'), findsOneWidget);
    expect(
      find.text('systemctl --user start leetcode-coach-relay'),
      findsOneWidget,
    );
    expect(await enabled(tester, 'start-missing-number'), isFalse);

    rig.transport.outage = null;
    await wait(tester, rig, 30);
    expect(find.text('Coach service not running'), findsNothing);
    expect(await enabled(tester, 'start-missing-number'), isTrue);
  });

  testWidgets('desktop: relay down mid-session keeps the session on screen', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    rig.transport.outage = _down;
    await wait(tester, rig, 5);
    expect(find.text('Coach service not running'), findsOneWidget);
    expect(find.byKey(const Key('answer-1')), findsOneWidget);
  });

  testWidgets('no reply in 300 s: "send again" resends the same rid', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    rig.transport.silent = true;
    await typeInto(tester, 'answer-1', 'O(1) space');
    await tapKey(tester, 'submit-1');
    await wait(tester, rig, 299);
    expect(find.textContaining('No reply from PC'), findsNothing);
    await wait(tester, rig, 2);
    expect(find.textContaining('No reply from PC'), findsOneWidget);
    rig.transport.silent = false;
    await tapKey(tester, 'send-again');
    await settle(tester, rig);
    final sent = rig.transport.sent;
    expect(sent[sent.length - 1].$1, sent[sent.length - 2].$1);
    expect(find.text('passed'), findsOneWidget);
    expect(
      rig.transport.relay.ran.where((r) => r.$1 == 'grade_step'),
      hasLength(1),
    );
  });
}
