// The Coach tab paints no words (textgate, 2026-11-08): every state of the
// tab, its sheets and its snack bar, at desktop and phone sizes. Only named
// content may hold letters: LeetCode slugs and titles and the commands kuhy
// types, taken from the fixture itself.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/ui/coach_tab.dart';

import '../support/coach_pump.dart';
import '../support/coach_rig.dart';
import '../support/pump.dart';
import '../support/text_scan.dart';

const _tallDesktop = Size(1920, 4000);

final Set<String> _full = fixtureContent('snapshot_full');
final Set<String> _empty = fixtureContent('snapshot_coach_empty');

void _expectTab(Set<String> allowed, String where) {
  expect(find.byType(CoachTab), findsOneWidget, reason: where);
  expectNoWords([find.byType(CoachTab), ...overlays()], allowed, where: where);
}

/// Opens every phone section chip in turn and scans each.
Future<void> _everyChip(WidgetTester tester, Set<String> allowed) async {
  final chips = find.descendant(
    of: find.byType(CoachTab),
    matching: find.byType(ChoiceChip),
  );
  final count = chips.evaluate().length;
  expect(count, greaterThan(1), reason: 'phone sections');
  for (var i = 0; i < count; i++) {
    await tester.ensureVisible(chips.at(i));
    await tester.tap(chips.at(i));
    await tester.pumpAndSettle();
    _expectTab(allowed, 'phone section ${i + 1}');
  }
}

/// A relay outage or a stale heartbeat, set before the app starts.
const _presence = <String, (bool, CoachUnavailable?)>{
  'relay down': (
    false,
    CoachUnavailable(CoachOutage.relayDown, 'coach service not running'),
  ),
  'no network': (
    false,
    CoachUnavailable(CoachOutage.network, 'Network error: offline'),
  ),
  'signed out': (
    true,
    CoachUnavailable(CoachOutage.signedOut, 'Not signed in'),
  ),
  'PC offline': (true, null),
};

void main() {
  testWidgets('with sessions, read-only', (tester) async {
    await pumpApp(tester, size: _tallDesktop);
    await openCoach(tester);
    expect(find.byKey(const Key('row-bit-cancellation')), findsOneWidget);
    _expectTab(_full, 'sessions, read-only');
  });

  testWidgets('with sessions and a relay', (tester) async {
    await pumpCoach(tester, size: _tallDesktop);
    await openCoachTab(tester);
    expect(find.byKey(const Key('start-missing-number')), findsOneWidget);
    _expectTab(_full, 'sessions, relay');
  });

  testWidgets('phone: every section chip', (tester) async {
    await pumpCoach(tester, size: kPhoneSession);
    await openCoachTab(tester);
    await _everyChip(tester, _full);
  });

  testWidgets('no sessions yet: how to start, the commands sheet, copy', (
    tester,
  ) async {
    final copied = recordClipboard(tester);
    await pumpApp(
      tester,
      size: _tallDesktop,
      answers: ['snapshot_coach_empty'],
    );
    await openCoach(tester);
    expect(find.byKey(const Key('command-box')), findsOneWidget);
    _expectTab(_empty, 'how to start');

    await openSheet(tester, const Key('show-commands'));
    expect(find.byKey(const Key('sheet')), findsOneWidget);
    _expectTab(_empty, 'commands sheet');
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('copy-command')));
    await tester.pump();
    expect(copied, isNotEmpty);
    expect(find.byType(SnackBar), findsOneWidget);
    _expectTab(_empty, 'copied');
  });

  for (final answer in const ['snapshot_nulls', null]) {
    testWidgets('unknown: $answer', (tester) async {
      await pumpApp(tester, size: _tallDesktop, answers: [answer]);
      await openCoach(tester);
      _expectTab(const {}, 'unknown: $answer');
    });
  }

  for (final MapEntry(key: where, value: (phone, outage))
      in _presence.entries) {
    testWidgets('presence: $where', (tester) async {
      await pumpCoach(
        tester,
        size: _tallDesktop,
        phone: phone,
        before: (t) {
          t.outage = outage;
          t.relay.beatAge = const Duration(minutes: 5).inMilliseconds;
        },
      );
      await openCoachTab(tester);
      expect(find.byKey(const Key('presence')), findsOneWidget);
      _expectTab({
        ..._full,
        'systemctl --user start leetcode-coach-relay',
      }, where);
    });
  }

  testWidgets('the live and the last session', (tester) async {
    final rig = await pumpCoach(tester, size: _tallDesktop);
    await startMissingNumber(tester, rig);
    await leaveSession(tester);
    expect(find.byKey(const Key('live-track')), findsOneWidget);
    _expectTab({..._full, 'Missing Number'}, 'live session');

    await tapKey(tester, 'resume-session');
    await tapKey(tester, 'end-session');
    await tapKey(tester, 'confirm-end');
    await settle(tester, rig);
    await leaveSession(tester);
    expect(find.byKey(const Key('last-session')), findsOneWidget);
    _expectTab({..._full, 'Missing Number'}, 'last session');
  });
}
