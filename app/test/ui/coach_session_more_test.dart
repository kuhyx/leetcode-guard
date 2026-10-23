import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/transport.dart';

import '../support/coach_rig.dart';
import '../support/fake_relay.dart';

void main() {
  testWidgets('a done step can be reopened to read its grade', (tester) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await passToStep4(tester, rig);
    rig.transport.relay.probe('accepted');
    await wait(tester, rig, 5);
    expect(find.byKey(const Key('answer-5')), findsOneWidget);
    await tapKey(tester, 'step-1');
    expect(find.text('The rule is clear.'), findsOneWidget);
    expect(find.text('Failed tries: 0'), findsOneWidget);
    await tapKey(tester, 'step-4');
    expect(find.text('Accepted on LeetCode.'), findsOneWidget);
    expect(find.textContaining('Last checked'), findsOneWidget);
  });

  testWidgets('End session asks first, then ends it', (tester) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await tapKey(tester, 'end-session');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(rig.transport.relay.ran, hasLength(1));
    await tapKey(tester, 'end-session');
    await tester.tap(find.widgetWithText(TextButton, 'End session').last);
    await tester.pumpAndSettle();
    await settle(tester, rig);
    expect(rig.transport.relay.ran.last.$1, 'session_end');
    expect(find.text('Session ended.'), findsOneWidget);
    expect(find.byKey(const Key('end-session')), findsNothing);

    // Back on the Coach tab, the last session can be viewed.
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.textContaining('Last: Missing Number (ended)'), findsOneWidget);
    await tapKey(tester, 'resume-session');
    expect(find.text('Session ended.'), findsOneWidget);
  });

  testWidgets('Resume reopens a live session from the Coach tab', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Live: Missing Number, step 1 of 5'), findsOneWidget);
    expect(await enabled(tester, 'start-majority-element'), isFalse);
    await tapKey(tester, 'resume-session');
    expect(find.byKey(const Key('answer-1')), findsOneWidget);
  });

  testWidgets('typed "reveal" asks like the button; Ctrl+Enter sends', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await typeInto(tester, 'chat-input', 'reveal');
    await tapKey(tester, 'chat-send');
    expect(find.textContaining('ends the exercise'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    await typeInto(tester, 'chat-input', 'why xor?');
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pump();
    expect(find.text('You (sending...)'), findsOneWidget);
    await settle(tester, rig);
    expect(find.text(kReply), findsOneWidget);
  });

  testWidgets('limits, removing a property, unknown grades, card errors', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await typeInto(tester, 'answer-1', 'x' * 8193);
    expect(find.textContaining('Too long: 8193 of 8192 bytes'), findsOneWidget);
    expect(await enabled(tester, 'submit-1'), isFalse);
    await gradeText(tester, rig, 1, 'O(1) space');

    await tapKey(tester, 'add-property');
    expect(find.byKey(const Key('property-1')), findsOneWidget);
    await tapKey(tester, 'remove-property-1');
    expect(find.byKey(const Key('property-1')), findsNothing);

    // A grade this build cannot read shows as unknown, never as a pass.
    final relay = rig.transport.relay;
    relay.steps[1] = {
      ...relay.steps[1],
      'last': {'grade': 'excellent', 'via': 'unverified'},
    };
    relay.rev++;
    await wait(tester, rig, 5);
    expect(find.text('unknown'), findsOneWidget);
    expect(find.text('not checked'), findsOneWidget);
  });

  testWidgets('a card failure is shown with the post-mortem pass', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await passToStep4(tester, rig);
    rig.transport.relay
      ..probe('accepted')
      ..cardsError = 'AnkiConnect down';
    await wait(tester, rig, 5);
    await gradeText(tester, rig, 5, 'XOR pairs each index with its value');
    expect(
      find.text('Built 3 Anki cards; the rest failed: AnkiConnect down'),
      findsOneWidget,
    );
  });

  testWidgets('rate limited: "send again" goes out as a new request', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    rig.transport.relay.rateLimitNext = true;
    await tapKey(tester, 'hint');
    await settle(tester, rig);
    expect(find.text('Too many requests: wait a moment'), findsOneWidget);
    final first = rig.transport.sent.last.$1;
    await tapKey(tester, 'retry-new');
    await settle(tester, rig);
    expect(rig.transport.sent.last.$1, isNot(first));
    expect(rig.transport.relay.ran.last.$1, 'hint');
    expect(find.byKey(const Key('failure')), findsNothing);
  });

  testWidgets('no network: the Coach tab says so and why', (tester) async {
    await pumpCoach(
      tester,
      before: (t) => t.outage = const CoachUnavailable(
        CoachOutage.network,
        'Network error: offline',
      ),
    );
    await openCoachTab(tester);
    expect(find.text('Cannot reach the coach'), findsOneWidget);
    expect(find.text('Network error: offline'), findsOneWidget);
  });

  testWidgets('polling stops in the background and resumes', (tester) async {
    final rig = await pumpCoach(tester);
    await openCoachTab(tester);
    void go(List<AppLifecycleState> states) =>
        states.forEach(tester.binding.handleAppLifecycleStateChanged);

    go(const [AppLifecycleState.inactive, AppLifecycleState.hidden]);
    await tester.pump();
    final hidden = rig.transport.heartbeats;
    await wait(tester, rig, 61);
    expect(rig.transport.heartbeats, hidden, reason: 'never in the background');
    go(const [AppLifecycleState.inactive, AppLifecycleState.resumed]);
    await wait(tester, rig, 31);
    expect(rig.transport.heartbeats, greaterThan(hidden));
    expect(find.text('Guided session'), findsOneWidget);
  });
}
