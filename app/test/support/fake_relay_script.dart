/// The fake relay's script: its texts, toolbox and grading rules.
///
/// Every text the relay itself words (grade lines, refusals, run lines) is
/// copied from `leetcode_coach/relay/` and the live answers in
/// `test/fixtures/coach_relay/` (captured 2026-10-23 by
/// `tool/coach_live_check.sh flow`), so a test that passes here passes on
/// the relay's real words. Only the model's own replies are invented.
library;

/// The fake's only sid.
const kSid = '20261023-170448-5b71';

const kOpener =
    "Let's start with the constraint. What does the problem rule out, "
    'and what rule does that give you?';
const kReply = 'Good question. Which property lets two equal values vanish?';

/// `turns.LOCKED`: the error of a `phase_locked` answer.
const kLocked = 'Code waits until step 2 (requirements) is passed or forced.';

/// The phase gate's `note` on a refusal (`PhaseGate.refusal_note`).
const kRefusedNote =
    '[code held back: write the requirement list first -- one message '
    'starting with req: that lists the properties the operation must have, '
    'without naming an operation or structure]';
const kHint = 'think about what x ^ x is.';
const kReveal = 'Solution: XOR every index and every value together.';

/// `session.grade_line` for step 4's Accepted.
const kAcceptedLine =
    'Step 4 (implement): LeetCode shows an Accepted. Step 5 open.';

/// `grading.NAMES_A_TOOL`: a step-2 list that names an operation fails.
const kNamesATool =
    'This names an operation or a structure. List the properties it must '
    'have instead, without naming it.';

/// `toolbox_grade.TOO_MANY`.
const kTooMany = 'Fewer picks: more than one of these is not needed.';

/// The `run_code` data: one example passes, one does not.
const kRunData = <String, Object?>{
  'examples': [
    {'n': 1, 'ok': true, 'expected': '2', 'got': '2'},
    {'n': 2, 'ok': false, 'expected': '2', 'got': '1'},
  ],
  'error': null,
};

/// The `system` / `run` chat line the relay writes for [data]
/// (`turns.run_code`): one line per example, then the error's words.
String runLine(Map<String, Object?> data) => [
  for (final e in (data['examples']! as List).cast<Map<String, Object?>>())
    'example ${e['n']}: got ${e['got']}, expected ${e['expected']}',
].join('\n');

/// Toolbox entries offered at step 3: real names and properties
/// (`leetcode_coach/toolbox.json`), a subset of the twenty.
const kFakeToolbox = <Map<String, Object?>>[
  {
    'name': 'XOR',
    'properties': ['self-inverse', 'invertible', 'commutative', 'associative'],
  },
  {
    'name': 'sum / difference',
    'properties': ['invertible', 'commutative', 'carries between bits'],
  },
  {
    'name': 'hash set',
    'properties': ['O(1) lookup', 'presence only', 'arbitrary keys'],
  },
  {
    'name': 'sorting',
    'properties': ['O(n log n) time', 'makes equal values adjacent'],
  },
];

/// `answer_key.json` for missing-number: `entries` and `also_accepted`.
const kFakeKey = {'XOR'};
const kFakeAlso = {'sum / difference'};

const kStepNames = [
  'constraint',
  'requirements',
  'toolbox',
  'implement',
  'postmortem',
];

Map<String, Object?> newSession(int now) => {
  'id': kSid,
  'slug': 'missing-number',
  'title': 'Missing Number',
  'cluster': 'bit-cancellation',
  'url': 'https://leetcode.com/problems/missing-number/',
  'started': now,
  'ended': null,
  'end_reason': null,
};

List<Map<String, Object?>> newSteps() => [
  for (var n = 1; n <= 5; n++)
    {
      'n': n,
      'name': kStepNames[n - 1],
      'status': n == 1 ? 'open' : 'locked',
      if (n == 4) ...{
        'probe': null,
        'probed_at': null,
      } else ...{
        'attempts': 0,
        'can_force': false,
        'last': null,
      },
    },
];

String nextRung(String? rung) => switch (rung) {
  null => 'H0',
  'H0' => 'H1',
  'H1' => 'H2',
  _ => 'H3',
};

/// The fake's code detector: braces or semicolons.
bool looksLikeCode(String text) => text.contains('{') || text.contains(';');

/// `session.grade_line`: the `system` chat line of a grade.
String gradeLine(int n, String grade, int attempt, String feedback) =>
    'Step $n (${kStepNames[n - 1]}): $grade on try $attempt.\n$feedback'.trim();

/// Step 3 as `toolbox_grade.grade` rules it, for this key: an
/// alternative stands in for the key entry, and is not an extra.
(String, String) _toolbox(Set<String> picks) {
  final right = picks.intersection({...kFakeKey, ...kFakeAlso});
  final extras = picks.difference({...kFakeKey, ...kFakeAlso});
  if (right.isNotEmpty && extras.length <= 1) return ('pass', '');
  if (right.isNotEmpty) return ('partial', kTooMany);
  return (
    'fail',
    'The operation you need also has these properties, which no pick has:\n'
        '- self-inverse: applying the same value twice undoes it',
  );
}

/// (grade, feedback, via) for step [n] of [body]. Steps 1 and 5 go to a
/// model (`haiku`), step 2 to the phase gate unless it names a tool or
/// reads as code (then `fail`, `toolbox`), step 3 is mechanical.
(String, String, String) gradeFor(int n, Map<String, Object?> body) {
  final answer = body['answer'] as String? ?? '';
  switch (n) {
    case 1:
      if (answer.contains('O(1)')) {
        return ('pass', 'The rule is clear.', 'haiku');
      }
      if (answer.contains('O(n)')) {
        return ('partial', 'Missing: the bound on extra space.', 'haiku');
      }
      return ('fail', 'Missing: what the constraint forbids.', 'haiku');
    case 2:
      if (looksLikeCode(answer) || answer.contains('XOR')) {
        return ('fail', kNamesATool, 'toolbox');
      }
      final lines = answer.split('\n').where((l) => l.trim().isNotEmpty);
      return lines.length >= 2
          ? ('pass', '', 'haiku')
          : ('partial', 'It does not yet say:\n- self-inverse', 'haiku');
    case 3:
      final picks = {...(body['picks'] as List? ?? const []).cast<String>()};
      final (grade, feedback) = _toolbox(picks);
      return (grade, feedback, 'toolbox');
    default:
      return answer.length >= 20
          ? ('pass', 'A clear post-mortem.', 'haiku')
          : ('partial', 'Missing: why the trick works.', 'haiku');
  }
}
