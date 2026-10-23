import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/coach_rig.dart';
import '../support/fake_relay.dart';

const _code = 'function missingNumber(nums) { return 0; }';

Future<void> _openChat(WidgetTester tester) async {
  await tester.tap(find.text('Chat'));
  await tester.pumpAndSettle();
}

Future<void> _openSteps(WidgetTester tester) async {
  await tester.tap(find.text('Steps'));
  await tester.pumpAndSettle();
}

Future<void> _say(WidgetTester tester, CoachRig rig, String text) async {
  await typeInto(tester, 'chat-input', text);
  await tapKey(tester, 'chat-send');
  await settle(tester, rig);
}

void main() {
  testWidgets('phone: chat, hint, refused code, run code', (tester) async {
    final rig = await pumpCoach(tester, size: kPhoneSession, phone: true);
    await startMissingNumber(tester, rig);
    // The phone puts the chat on its own tab.
    expect(find.byKey(const Key('chat-input')), findsNothing);
    await _openChat(tester);
    expect(find.text(kOpener), findsOneWidget);

    await _say(tester, rig, 'why xor?');
    expect(find.text('why xor?'), findsOneWidget);
    expect(find.text(kReply), findsOneWidget);
    expect(rig.transport.sent.last.$2['kind'], 'chat');

    await tapKey(tester, 'hint');
    await settle(tester, rig);
    expect(find.text('Hint H0: $kHint'), findsOneWidget);
    expect(rig.transport.relay.ran.last.$1, 'hint');

    // Code before step 2: the relay refuses it and says why.
    await _say(tester, rig, _code);
    expect(find.text(kRefused), findsWidgets);
    final run = find.byKey(const Key('run-m0005'));
    expect(run, findsOneWidget);
    expect(tester.widget<ButtonStyleButton>(run).onPressed, isNull);

    // Pass steps 1 and 2, then the same message runs.
    await _openSteps(tester);
    await gradeText(tester, rig, 1, 'O(1) extra space');
    await typeInto(tester, 'property-0', 'x ^ x = 0');
    await tapKey(tester, 'add-property');
    await typeInto(tester, 'property-1', 'indices 0..n');
    await tapKey(tester, 'submit-2');
    await settle(tester, rig);
    await _openChat(tester);
    await tapKey(tester, 'run-m0005');
    await settle(tester, rig);
    expect(rig.transport.relay.ran.last.$1, 'run_code');
    expect(rig.transport.relay.ran.last.$2, {'session': kSid, 'code': _code});
    expect(find.text('example 1: got 2, expected 2'), findsOneWidget);
    expect(find.text('example 2: got 1, expected 2'), findsOneWidget);
  });

  testWidgets('Reveal asks first, and confirming ends the exercise', (
    tester,
  ) async {
    final rig = await pumpCoach(tester, size: kPhoneSession, phone: true);
    await startMissingNumber(tester, rig);
    await _openChat(tester);
    await tapKey(tester, 'reveal');
    expect(find.textContaining('ends the exercise'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(rig.transport.relay.ran.map((r) => r.$1), ['session_start']);

    await tapKey(tester, 'reveal');
    await tester.tap(find.widgetWithText(TextButton, 'Reveal'));
    await tester.pumpAndSettle();
    await settle(tester, rig);
    expect(rig.transport.relay.ran.last.$1, 'reveal');
    expect(find.text(kReveal), findsOneWidget);
    expect(find.textContaining('Session ended'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byKey(const Key('chat-input'))).enabled,
      isFalse,
    );
  });

  testWidgets("Start on a problem with no answer key shows the relay's "
      'error', (tester) async {
    final rig = await pumpCoach(tester, size: kPhoneSession);
    await openCoachTab(tester);
    await tapKey(tester, 'start-single-number-iii');
    await settle(tester, rig);
    expect(find.text('No answer key for that problem'), findsOneWidget);
  });
}
