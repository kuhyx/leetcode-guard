import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';

RelayFailure _failure(Map<String, Object?> json) =>
    RelayFailure('chat', const {}, RelayResult.fromJson(json));

void main() {
  test('state parses tolerantly; unknown values stay unknown', () {
    final s = CoachState.tryParse({
      'rev': 2,
      'steps': [
        {
          'n': 1,
          'status': 'weird',
          'last': {'grade': 'meh'},
        },
        {'n': 2, 'status': 'forced'},
      ],
    })!;
    expect(s.stepAt(1)!.status, StepStatus.unknown);
    expect(s.stepAt(1)!.last!.grade, isNull);
    expect(s.stepAt(1)!.canForce, isFalse);
    expect(s.stepAt(9), isNull);
    expect(s.codeOpen, isTrue);
    expect(s.live, isFalse);
    expect(CoachState.tryParse('nope'), isNull);
    expect(StepStatus.locked.done, isFalse);
  });

  test('a session is live until it ends', () {
    final live = SessionInfo.fromJson({'id': 'x'});
    expect(live.live, isTrue);
    expect(SessionInfo.fromJson({'id': 'x', 'ended': 1}).live, isFalse);
    expect(SessionInfo.fromJson({}).live, isFalse);
    expect(ToolboxEntry.fromJson({}).name, '');
  });

  test('heartbeat and result reject non-objects', () {
    expect(Heartbeat.tryParse([1]), isNull);
    expect(RelayResult.tryParse('x'), isNull);
    final r = RelayResult.tryParse({'ok': true, 'state_rev': 3})!;
    expect(r.stateRev, 3);
    expect(r.data, isEmpty);
  });

  test('a pending request words each phase', () {
    final p = PendingRequest('r', 'chat', const {}, sentAt: DateTime(2026));
    expect(p.text, contains('Queued'));
    expect(p.resendable, isFalse);
    p.phase = RequestPhase.working;
    expect(p.text, contains('working'));
    p.phase = RequestPhase.stalled;
    expect(p.text, 'No reply from PC, send again');
    expect(p.resendable, isTrue);
    p.phase = RequestPhase.notSent;
    expect(p.text, 'Not sent: network error');
    p.error = 'offline';
    expect(p.text, 'Not sent: offline');
  });

  test("a failure shows the relay's words plus its extras", () {
    expect(_failure({'code': 'x'}).text, 'The relay refused it (x)');
    expect(_failure({}).text, 'The relay refused it (error)');
    expect(
      _failure({'error': 'locked', 'note': 'write requirements first'}).text,
      'locked\nwrite requirements first',
    );
    expect(_failure({'error': 'same', 'note': 'same'}).text, 'same');
    final at = DateTime(2026, 10, 23, 18, 5);
    expect(
      _failure({
        'error': 'Claude is out',
        'resets_at': at.millisecondsSinceEpoch,
      }).text,
      'Claude is out\nClaude is back at 18:05',
    );
    expect(
      _failure({'error': 'out', 'resets_at': 'tomorrow 9am'}).text,
      'out\nClaude is back at tomorrow 9am',
    );
    expect(_failure({'retry': true}).retry, isTrue);
  });

  test('timeOfMs drops the date only on the same day', () {
    final now = DateTime(2026, 10, 23, 20);
    final today = DateTime(2026, 10, 23, 9, 7).millisecondsSinceEpoch;
    final before = DateTime(2026, 10, 22, 9, 7).millisecondsSinceEpoch;
    expect(timeOfMs(today, now), '09:07');
    expect(timeOfMs(before, now), '2026-10-22 09:07');
  });
}
