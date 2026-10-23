import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../support/coach_rig.dart';
import '../support/fake_relay.dart';

void main() {
  testWidgets('missing-number end to end: gating, forced continue, '
      'Accepted, post-mortem', (tester) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    expect(find.text('Missing Number'), findsWidgets);
    expect(find.byKey(const Key('answer-1')), findsOneWidget);

    // Locked steps cannot be opened.
    await tester.tap(find.byKey(const Key('step-3')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('answer-1')), findsOneWidget);
    expect(find.byKey(const Key('pick-Gauss sum')), findsNothing);

    // Two fails and a partial: then, and only then, "Continue anyway".
    await typeInto(tester, 'answer-1', 'loop over it');
    await tapKey(tester, 'submit-1');
    expect(await enabled(tester, 'submit-1'), isFalse, reason: 'in flight');
    expect(find.byKey(const Key('request-status')), findsOneWidget);
    await wait(tester, rig, 2);
    expect(find.text('fail'), findsOneWidget);
    expect(find.text('Missing: what the constraint forbids.'), findsOneWidget);
    expect(find.text('Failed tries: 1'), findsOneWidget);
    expect(await enabled(tester, 'submit-1'), isFalse, reason: '3 s pause');
    await settle(tester, rig);
    expect(await enabled(tester, 'submit-1'), isTrue);
    expect(find.byKey(const Key('force-1')), findsNothing);
    await gradeText(tester, rig, 1, 'still a loop');
    await gradeText(tester, rig, 1, 'O(n) time');
    expect(find.text('partial'), findsOneWidget);
    expect(find.text('Failed tries: 3'), findsOneWidget);
    await tapKey(tester, 'force-1');
    await settle(tester, rig);
    expect(find.text('forced'), findsOneWidget);

    // Step 2: a property list.
    await typeInto(tester, 'property-0', 'x ^ x = 0 cancels pairs');
    await tapKey(tester, 'add-property');
    await typeInto(tester, 'property-1', 'every index 0..n appears once');
    await tapKey(tester, 'submit-2');
    await settle(tester, rig);
    expect(
      rig.transport.relay.ran.last.$2['answer'],
      'x ^ x = 0 cancels pairs\nevery index 0..n appears once',
    );

    // Step 3: pick from the toolbox, which shows each entry's properties.
    expect(find.text('x ^ 0 = x'), findsOneWidget);
    await tapKey(tester, 'pick-XOR self-cancellation');
    await tapKey(tester, 'submit-3');
    await settle(tester, rig);
    expect(rig.transport.relay.ran.last.$2['picks'], ['XOR self-cancellation']);

    // Step 4: open the problem, then wait for an Accepted.
    await tapKey(tester, 'open-leetcode');
    expect(rig.opened, [
      Uri.parse('https://leetcode.com/problems/missing-number/'),
    ]);
    expect(find.textContaining('Waiting for Accepted'), findsOneWidget);
    expect(find.byKey(const Key('submit-4')), findsNothing);
    expect(find.byKey(const Key('force-4')), findsNothing);
    rig.transport.relay.probe('unknown');
    await wait(tester, rig, 5);
    expect(find.textContaining('Could not check'), findsOneWidget);
    expect(find.textContaining('Waiting for Accepted'), findsNothing);
    rig.transport.relay.probe('accepted');
    await wait(tester, rig, 5);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('answer-5')), findsOneWidget);
    expect(
      find.text('LeetCode shows an Accepted: step 5 is open'),
      findsOneWidget,
    );

    // Step 5: the post-mortem ends the session and builds the cards.
    await gradeText(tester, rig, 5, 'XOR pairs each index with its value');
    expect(find.textContaining('Built 3 Anki cards'), findsOneWidget);
    expect(find.textContaining('Session ended'), findsOneWidget);
    expect(find.byKey(const Key('answer-5')), findsNothing);
    expect(rig.transport.relay.ran.map((r) => r.$1).toList(), [
      'session_start',
      for (var i = 0; i < 4; i++) 'grade_step',
      'grade_step',
      'grade_step',
      'grade_step',
    ]);
  });

  testWidgets('a wide window shows the chat beside the steps', (tester) async {
    final rig = await pumpCoach(tester);
    await startMissingNumber(tester, rig);
    expect(find.byKey(const Key('chat-input')), findsOneWidget);
    expect(find.byKey(const Key('answer-1')), findsOneWidget);
    expect(find.text(kOpener), findsOneWidget);
    expect(
      tester.getTopLeft(find.byKey(const Key('chat-input'))).dx,
      greaterThan(tester.getTopLeft(find.byKey(const Key('answer-1'))).dx),
    );
  });
}
