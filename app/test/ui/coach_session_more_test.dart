import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/coach_chat_message.dart';
import 'package:leetcode_guard/src/ui/coach_grade.dart';

import '../support/coach_labels.dart';
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
    expect(numeralIn('tries-1', '0'), findsOneWidget);
    await tapKey(tester, 'step-4');
    expect(byLabel('Accepted on LeetCode.'), findsOneWidget);
    expect(find.byKey(const Key('checked')), findsOneWidget);
  });

  testWidgets('End session asks first, then ends it', (tester) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await tapKey(tester, 'end-session');
    await tester.tap(find.byKey(const Key('cancel-end')));
    await tester.pumpAndSettle();
    expect(rig.transport.relay.ran, hasLength(1));
    await tapKey(tester, 'end-session');
    await tester.tap(find.byKey(const Key('confirm-end')));
    await tester.pumpAndSettle();
    await settle(tester, rig);
    expect(rig.transport.relay.ran.last.$1, 'session_end');
    expect(byLabel('Session ended.'), findsOneWidget);
    expect(find.byKey(const Key('end-session')), findsNothing);

    // Back on the Coach tab, the last session can be viewed.
    await leaveSession(tester);
    expect(find.text('Missing Number'), findsWidgets);
    expect(byLabel('Last: Session ended.'), findsOneWidget);
    await tapKey(tester, 'resume-session');
    expect(byLabel('Session ended.'), findsOneWidget);
  });

  testWidgets('Resume reopens a live session from the Coach tab', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await leaveSession(tester);
    expect(byLabel('Live: step 1 of 5'), findsOneWidget);
    expect(find.text('Missing Number'), findsWidgets);
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
    expect(find.byKey(const Key('confirm-reveal')), findsOneWidget);
    await tester.tap(find.byKey(const Key('cancel-reveal')));
    await tester.pumpAndSettle();

    await typeInto(tester, 'chat-input', 'why xor?');
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pump();
    expect(byLabel(kSendingLabel), findsOneWidget);
    expect(find.text('why xor?'), findsOneWidget);
    await settle(tester, rig);
    expect(find.text(kReply), findsOneWidget);
  });

  testWidgets('limits, removing a property, unknown grades, card errors', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    await typeInto(tester, 'answer-1', 'x' * 8193);
    // The live counter: numerals, red, plus the field's red outline.
    expect(byLabel('Too long: 8193 of 8192 bytes'), findsOneWidget);
    expect(find.text('8193/8192'), findsOneWidget);
    final field = tester.widget<TextField>(find.byKey(const Key('answer-1')));
    expect(field.decoration?.error, isNotNull);
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
    expect(find.byKey(const Key('grade-2')), findsNothing);
    expect(find.text(kUnknown), findsOneWidget);
    expect(byLabel(kNotChecked), findsOneWidget);
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
    expect(numeralIn('cards', '3'), findsOneWidget);
    expect(byLabel('The rest failed: AnkiConnect down'), findsOneWidget);
  });

  testWidgets('rate limited: "send again" goes out as a new request', (
    tester,
  ) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    rig.transport.relay.rateLimitNext = true;
    await tapKey(tester, 'hint');
    await settle(tester, rig);
    expect(byLabel('Too many requests: wait a moment'), findsOneWidget);
    expect(find.byIcon(Icons.timer), findsOneWidget);
    final first = rig.transport.sent.last.$1;
    await tapKey(tester, 'retry-new');
    await settle(tester, rig);
    expect(rig.transport.sent.last.$1, isNot(first));
    expect(rig.transport.relay.ran.last.$1, 'hint');
    expect(find.byKey(const Key('failure')), findsNothing);
  });

  testWidgets('Start beside "Next" starts the next problem', (tester) async {
    final rig = await pumpCoach(tester);
    await openCoachTab(tester);
    await tapKey(tester, 'start-next-bit-cancellation');
    await settle(tester, rig);
    expect(rig.transport.relay.done.values.single['code'], 'no_answer_key');
    expect(rig.transport.sent.single.$2['body'], {'slug': 'majority-element'});
    expect(byLabel('No answer key for that problem'), findsOneWidget);
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
    expect(
      byLabel('Cannot reach the coach: Network error: offline'),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.wifi_off), findsOneWidget);
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
    expect(find.byKey(const Key('resume-session')), findsOneWidget);
  });
}
