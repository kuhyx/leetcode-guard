/// The fake relay's script: its texts, toolbox and grading rules.
library;

/// The fake's only sid.
const kSid = '20261023-170448-5b71';

const kOpener =
    "Let's start with the constraint. What does the problem rule out, "
    'and what rule does that give you?';
const kReply = 'Good question. Which property lets two equal values vanish?';
const kRefused =
    'Code is refused until the requirements are passed or forced (step 2).';
const kHint = 'think about what x ^ x is.';
const kReveal = 'Solution: XOR every index and every value together.';

/// The `run_code` data: one example passes, one does not.
const kRunData = <String, Object?>{
  'examples': [
    {'n': 1, 'ok': true, 'got': '2', 'expected': '2'},
    {'n': 2, 'ok': false, 'got': '1', 'expected': '2'},
  ],
  'error': null,
};

/// Every toolbox entry offered at step 3.
const kFakeToolbox = <Map<String, Object?>>[
  {
    'name': 'XOR self-cancellation',
    'properties': ['x ^ x = 0', 'x ^ 0 = x', 'order does not matter'],
  },
  {
    'name': 'Gauss sum',
    'properties': ['sum of 0..n in closed form', 'overflows fixed-width ints'],
  },
  {
    'name': 'Hash set',
    'properties': ['O(1) membership test', 'O(n) extra space'],
  },
  {
    'name': 'Sorting',
    'properties': ['equal values end up adjacent', 'O(n log n) time'],
  },
];

/// The answer key's entries (never shown).
const kFakeKey = {'XOR self-cancellation'};

const _names = [
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
      'name': _names[n - 1],
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

/// (grade, feedback) for step [n] of [body].
(String, String) gradeFor(int n, Map<String, Object?> body) {
  final answer = body['answer'] as String? ?? '';
  switch (n) {
    case 1:
      if (answer.contains('O(1)')) return ('pass', 'The rule is clear.');
      if (answer.contains('O(n)')) {
        return ('partial', 'Missing: the bound on extra space.');
      }
      return ('fail', 'Missing: what the constraint forbids.');
    case 2:
      if (looksLikeCode(answer)) return ('fail', 'That reads as code.');
      final lines = answer.split('\n').where((l) => l.trim().isNotEmpty);
      return lines.length >= 2
          ? ('pass', 'Both properties named.')
          : ('partial', 'Missing: a property that pairs values off.');
    case 3:
      final picks = {...(body['picks'] as List? ?? const []).cast<String>()};
      if (picks.containsAll(kFakeKey) &&
          picks.difference(kFakeKey).length <= 1) {
        return ('pass', 'That toolbox covers it.');
      }
      return picks.intersection(kFakeKey).isNotEmpty
          ? ('partial', 'Too many tools picked.')
          : ('fail', 'Missing: something where x ^ x = 0.');
    default:
      return answer.length >= 20
          ? ('pass', 'A clear post-mortem.')
          : ('partial', 'Missing: why the trick works.');
  }
}
