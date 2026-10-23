part of 'fake_relay.dart';

/// Grading, forcing and the step-4 probe.
extension FakeRelaySteps on FakeRelay {
  Json _grade(Json body) {
    final n = body['step']! as int;
    final step = _step(n);
    if (step['status'] == 'locked') return err('step_locked', 'Locked');
    if (step['status'] != 'open') return err('step_done', 'Already done');
    if (body['force'] == true) return _force(n, step);
    if (n == 4) return err('bad_request', 'Step 4 is never graded');
    final (grade, feedback) = gradeFor(n, body);
    final passed = grade == 'pass';
    final tries = (step['attempts']! as int) + 1;
    final failed = tries - (passed ? 1 : 0);
    final canForce = !passed && failed >= 3;
    steps[n - 1] = {
      ...step,
      'status': passed ? 'passed' : 'open',
      'attempts': failed,
      'can_force': canForce,
      'last': {
        'grade': grade,
        'feedback': feedback,
        'via': 'haiku',
        'at': now(),
      },
    };
    say('system', 'grade', 'Step $n graded $grade on try $tries');
    final data = <String, Object?>{
      'step': n,
      'grade': grade,
      'feedback': feedback,
      'attempt': tries,
      'can_force': canForce,
      'via': 'haiku',
      'next_step': passed ? (n < 5 ? n + 1 : null) : null,
    };
    if (passed && n < 5) _open(n + 1);
    if (passed && n == 5) {
      data['cards'] = {'built': 3, 'deck': 'LeetCode', 'error': cardsError};
      return _end('done', data);
    }
    _bump();
    return ok(data);
  }

  Json _force(int n, Json step) {
    if (n == 4 || step['can_force'] != true) {
      return err('cannot_force', 'Fewer than 3 failed tries');
    }
    steps[n - 1] = {...step, 'status': 'forced', 'can_force': false};
    _open(n + 1);
    _bump();
    return ok({'step': n, 'forced': true, 'next_step': n + 1});
  }

  void _open(int n) => steps[n - 1] = {..._step(n), 'status': 'open'};

  /// The relay's Accepted probe for step 4.
  void probe(String result) {
    final step = _step(4);
    if (result == 'accepted') {
      steps[3] = {
        ...step,
        'status': 'passed',
        'probe': 'accepted',
        'probed_at': now(),
      };
      say('system', 'accepted', 'LeetCode shows an Accepted: step 5 is open');
      _open(5);
    } else {
      steps[3] = {...step, 'probe': result, 'probed_at': now()};
    }
    _bump();
  }
}
