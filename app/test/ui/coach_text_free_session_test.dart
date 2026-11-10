// The session screen paints no words (textgate, 2026-11-08), walked
// through all five steps, the chat, both confirmations and the banners.
// Allowed letters: what the coach model wrote (the fake script's replies
// and grader feedback), the problem's title, the toolbox entries (the
// curriculum kuhy reviewed) and what this test typed.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/ui/coach_session_screen.dart';

import '../support/coach_rig.dart';
import '../support/fake_relay.dart';
import '../support/text_scan.dart';

const _code = 'function missingNumber(nums) { return 0; }';

const Set<String> _typed = {
  'loop over it',
  'still a loop',
  'O(n) time',
  'x ^ x = 0 cancels pairs',
  'every index 0..n appears once',
  'XOR pairs each index with its value',
  'why xor?',
  _code,
};

/// The coach model's words in the fake script (`gradeFor`'s feedback, the
/// replies). The relay's own lines (grade lines, refusals) are not here.
const Set<String> _coachWords = {
  kOpener,
  kReply,
  'Hint H0: $kHint',
  kReveal,
  'Missing: what the constraint forbids.',
  'Missing: the bound on extra space.',
  'A clear post-mortem.',
};

final Set<String> _allowed = {
  ..._typed,
  ..._coachWords,
  'Missing Number',
  'missing-number',
  for (final e in kFakeToolbox) ...[
    e['name']! as String,
    ...(e['properties']! as List).cast<String>(),
  ],
};

void _expectScreen(String where, [Set<String> extra = const {}]) {
  expect(find.byType(CoachSessionScreen), findsOneWidget, reason: where);
  expectNoWords(
    [find.byType(CoachSessionScreen), ...overlays()],
    {..._allowed, ...extra},
    where: where,
  );
}

Future<void> _say(WidgetTester tester, CoachRig rig, String text) async {
  await typeInto(tester, 'chat-input', text);
  await tapKey(tester, 'chat-send');
  await settle(tester, rig);
}

void main() {
  testWidgets('five steps, chat, run, confirmations, end', (tester) async {
    // Tall, so every chat line and step is built (lists build lazily).
    final rig = await pumpCoach(tester, size: const Size(1920, 4000));
    await startMissingNumber(tester, rig);
    expect(find.byKey(const Key('answer-1')), findsOneWidget);
    _expectScreen('step 1 open');

    await typeInto(tester, 'answer-1', 'x' * 8193);
    _expectScreen('too long', {'x' * 8193});
    await gradeText(tester, rig, 1, 'loop over it');
    await gradeText(tester, rig, 1, 'still a loop');
    await gradeText(tester, rig, 1, 'O(n) time');
    expect(find.byKey(const Key('force-1')), findsOneWidget);
    _expectScreen('graded three times');
    await tapKey(tester, 'force-1');
    await settle(tester, rig);
    _expectScreen('forced');

    await typeInto(tester, 'property-0', 'x ^ x = 0 cancels pairs');
    await tapKey(tester, 'add-property');
    await typeInto(tester, 'property-1', 'every index 0..n appears once');
    _expectScreen('step 2');
    await tapKey(tester, 'submit-2');
    await settle(tester, rig);
    expect(find.byKey(const Key('pick-XOR')), findsOneWidget);
    _expectScreen('step 3');
    await tapKey(tester, 'pick-XOR');
    await tapKey(tester, 'submit-3');
    await settle(tester, rig);

    expect(find.byKey(const Key('open-leetcode')), findsOneWidget);
    _expectScreen('step 4 waiting');
    rig.transport.relay.probe('unknown');
    await wait(tester, rig, 5);
    _expectScreen('step 4 could not check');

    await _say(tester, rig, 'why xor?');
    await tapKey(tester, 'hint');
    await settle(tester, rig);
    await _say(tester, rig, _code);
    final run = find.byWidgetPredicate(
      (w) =>
          w.key is ValueKey<String> &&
          (w.key! as ValueKey<String>).value.startsWith('run-'),
    );
    expect(run, findsOneWidget);
    await tapKey(tester, (tester.widget(run).key! as ValueKey<String>).value);
    await settle(tester, rig);
    _expectScreen('chat, hint, run');

    for (final (button, confirm) in const [
      ('reveal', 'confirm-reveal'),
      ('end-session', 'confirm-end'),
    ]) {
      await tapKey(tester, button);
      expect(find.byKey(Key(confirm)), findsOneWidget);
      _expectScreen('$button dialog');
      await tester.tap(find.byKey(Key('cancel-${button.split('-').first}')));
      await tester.pumpAndSettle();
    }

    rig.transport.relay.probe('accepted');
    await wait(tester, rig, 5);
    expect(find.byKey(const Key('answer-5')), findsOneWidget);
    _expectScreen('step 5');
    rig.transport.relay.cardsError = 'AnkiConnect down';
    await gradeText(tester, rig, 5, 'XOR pairs each index with its value');
    expect(find.byKey(const Key('answer-5')), findsNothing);
    _expectScreen('ended with cards');
  });

  testWidgets('phone panes; refusals and the stalled request', (tester) async {
    final rig = await pumpCoach(tester, size: kPhoneSession, phone: true);
    await startMissingNumber(tester, rig);
    _expectScreen('phone steps');
    await tester.tap(find.byKey(const Key('chat')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('chat-input')), findsOneWidget);
    _expectScreen('phone chat');

    await _say(tester, rig, _code);
    expect(find.byKey(const Key('failure')), findsOneWidget);
    _expectScreen('code refused');

    rig.transport.relay.rateLimitNext = true;
    await tapKey(tester, 'hint');
    await settle(tester, rig);
    expect(find.byKey(const Key('retry-new')), findsOneWidget);
    _expectScreen('rate limited');

    rig.transport.silent = true;
    await tapKey(tester, 'retry-new');
    await wait(tester, rig, 301);
    expect(find.byKey(const Key('send-again')), findsOneWidget);
    _expectScreen('no reply');

    rig.transport.relay.beatAge = const Duration(minutes: 3).inMilliseconds;
    rig.transport.silent = false;
    await wait(tester, rig, 5);
    _expectScreen('PC offline');
  });

  testWidgets('a start the relay refuses', (tester) async {
    final rig = await pumpCoach(tester);
    await openCoachTab(tester);
    await tapKey(tester, 'start-single-number-iii');
    await settle(tester, rig);
    expect(find.byKey(const Key('failure')), findsOneWidget);
    _expectScreen('no answer key');
  });
}
