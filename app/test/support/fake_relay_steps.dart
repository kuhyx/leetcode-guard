part of 'fake_relay.dart';

/// Grading, forcing and the step-4 probe, in `relay/grading.py`'s order:
/// step 4 never graded, then locked, then done, then force, then a grade.
extension FakeRelaySteps on FakeRelay {
  Json _grade(Json body) {
    final n = body['step']! as int;
    final step = _step(n);
    if (n == 4) {
      return body['force'] == true
          ? err('cannot_force', 'Step 4 passes only on an Accepted.')
          : err('bad_request', 'step 4 is never graded');
    }
    if (step['status'] == 'locked') return err('step_locked', 'Locked');
    if (step['status'] != 'open') return err('step_done', 'Already done');
    if (body['force'] == true) return _force(n, step);
    if (n == 3) {
      final names = {for (final e in kFakeToolbox) e['name']};
      final unknown = [
        for (final p in (body['picks']! as List).cast<String>())
          if (!names.contains(p)) p,
      ];
      if (unknown.isNotEmpty) {
        return err('bad_request', 'Not in the toolbox: ${unknown.join(', ')}');
      }
    }
    final (grade, feedback, via) = gradeFor(n, body);
    final passed = grade == 'pass';
    final attempt = (step['attempts']! as int) + 1;
    // A pass is no failed try; partial and fail are.
    final failed = attempt - (passed ? 1 : 0);
    final canForce = !passed && failed >= 3;
    steps[n - 1] = {
      ...step,
      'status': passed ? 'passed' : 'open',
      'attempts': failed,
      'can_force': canForce,
      'last': {'grade': grade, 'feedback': feedback, 'via': via, 'at': now()},
    };
    say('system', 'grade', gradeLine(n, grade, attempt, feedback));
    if (passed && n < 5) _open(n + 1);
    final data = <String, Object?>{
      'step': n,
      'grade': grade,
      'feedback': feedback,
      'attempt': attempt,
      'can_force': canForce,
      'via': via,
      // The step open now: n again after partial / fail, null once ended.
      'next_step': passed ? (n < 5 ? n + 1 : null) : n,
    };
    if (passed && n == 5) {
      data['cards'] = {'built': 3, 'deck': 'LeetCode', 'error': cardsError};
      return _end('done', data);
    }
    _bump();
    return ok(data);
  }

  /// A force is its own grade event: the last try's grade and via stay,
  /// `attempts` does not move (`steps.derive` skips forced events).
  Json _force(int n, Json step) {
    if (step['can_force'] != true) {
      return err('cannot_force', 'You can continue after 3 tries.');
    }
    steps[n - 1] = {...step, 'status': 'forced', 'can_force': false};
    final tries = step['attempts'];
    say(
      'system',
      'grade',
      'Step $n (${kStepNames[n - 1]}): '
          'continued after $tries tries.',
    );
    if (n == 5) {
      return _end('done', {'step': n, 'forced': true, 'next_step': null});
    }
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
      say('system', 'accepted', kAcceptedLine);
      _open(5);
    } else {
      steps[3] = {...step, 'probe': result, 'probed_at': now()};
    }
    _bump();
  }
}
