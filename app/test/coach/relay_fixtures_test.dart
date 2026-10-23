// The models against the REAL relay's answers, not against beliefs about
// them: `test/fixtures/coach_relay/` is what `leetcode_coach/relay/` sent
// on 2026-10-23 to `tool/coach_live_check.sh flow` (re-run it to refresh).
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';

import '../support/fixtures.dart';

Object? _live(String name) => jsonDecode(fixtureText('coach_relay/$name'));

CoachState _state(String name) => CoachState.tryParse(_live(name))!;

RelayResult _result(String name) => RelayResult.tryParse(_live(name))!;

void main() {
  test('no session: nulls and no steps, never a default', () {
    final s = _state('state_none');
    expect(s.session, isNull);
    expect(s.step, isNull);
    expect(s.steps, isEmpty);
    expect(s.live, isFalse);
    expect(s.toolbox, isNull);
  });

  test('a fresh session: step 1 open, step 4 shaped as a probe', () {
    final s = _state('state_step1');
    expect(s.live, isTrue);
    expect(s.step, 1);
    expect(s.stepAt(1)!.status, StepStatus.open);
    expect(s.stepAt(1)!.attempts, 0);
    expect(s.stepAt(1)!.last, isNull);
    expect(s.stepAt(4)!.probe, isNull);
    expect(s.stepAt(4)!.attempts, isNull);
    expect(s.codeOpen, isFalse);
  });

  test('a forced step 2: its tries exclude the force, step 3 offers the '
      'toolbox', () {
    final s = _state('state_step3');
    final two = s.stepAt(2)!;
    expect(two.status, StepStatus.forced);
    expect(two.attempts, 3);
    expect(two.canForce, isFalse);
    expect(two.last!.grade, Grade.fail);
    expect(two.last!.via, 'toolbox');
    expect(s.codeOpen, isTrue);
    expect(s.step, 3);
    final names = s.toolbox!.map((e) => e.name);
    expect(names, containsAll(['XOR', 'sum / difference', 'hash set']));
    expect(s.toolbox!.first.properties, isNotEmpty);
  });

  test('an ended session stays, read-only: step null, not live', () {
    final s = _state('state_ended');
    expect(s.step, isNull);
    expect(s.live, isFalse);
    expect(s.session!.endReason, 'ended');
    expect(s.stepAt(3)!.status, StepStatus.passed);
  });

  test('the heartbeat while idle carries no busy', () {
    final hb = Heartbeat.tryParse(_live('heartbeat_idle'))!;
    expect(hb.beat, isNotNull);
    expect(hb.stateRev, isNotNull);
    expect(hb.busy, isNull);
  });

  test('results: grades, a force, and the next step', () {
    final start = _result('result_session_start');
    expect(start.ok, isTrue);
    expect(start.data['msg'], 'm0001');
    final partial = _result('result_step1_partial').data;
    expect(partial['next_step'], 1, reason: 'still open after a partial');
    expect(_result('result_step2_fail').data['via'], 'toolbox');
    expect(_result('result_force').data, {
      'step': 2,
      'forced': true,
      'next_step': 3,
    });
    expect(_result('result_step3_partial').data['grade'], 'partial');
  });

  test('refusals read as the relay words them', () {
    final pick = RelayFailure(
      'grade_step',
      const {},
      _result('result_bad_pick'),
    );
    expect(pick.code, 'bad_request');
    expect(pick.retry, isFalse);
    expect(pick.text, 'Not in the toolbox: not a tool');
    final locked = RelayFailure(
      'chat',
      const {},
      _result('result_phase_locked'),
    );
    expect(locked.code, 'phase_locked');
    expect(locked.text, startsWith('Code waits until step 2'));
    expect(locked.text, contains('[code held back'));
  });

  test("chat: every kind the relay writes, and run_code's line in it", () {
    final chat = chatFrom(_live('chat_all'));
    expect(chat.first.key, 'm0001');
    expect(chat.map((m) => m.kind).toSet(), {
      'chat',
      'grade',
      'refused',
      'run',
    });
    expect(chat.map((m) => m.role).toSet(), {'coach', 'kuhy', 'system'});
    final run = chat.singleWhere((m) => m.kind == 'run');
    expect(run.role, 'system');
    expect(run.text, startsWith('example 1: got 2, expected 2'));
    final ran = _result('result_run_code').data['examples']! as List;
    expect(run.text.split('\n'), hasLength(ran.length));
  });
}
