import 'package:flutter_test/flutter_test.dart';

import '../support/fixtures.dart';

void main() {
  group('coach section', () {
    test('parses problems, re-tests, clusters and how_to', () {
      final coach = fixture('snapshot_full').coach!;
      expect(coach.problems!.first.reqBeforeCode, isTrue);
      expect(coach.problems!.first.maxRung, 'H1');
      expect(coach.problems!.last.revealed, isTrue);
      expect(coach.problems!.last.reqCheck, 'incomplete');
      expect(coach.problems!.first.cluster, 'bit-cancellation');
      expect(coach.problems!.first.slug, 'missing-number');
      expect(coach.problems!.first.day, '2026-10-23');
      expect(coach.retestsDue!.single.due, '2026-10-26');
      expect(coach.retestsDue!.single.slug, 'missing-number');
      expect(
        coach.retestsDue!.single.command,
        'leetcode --retest missing-number',
      );
      final bit = coach.clusters!['bit-cancellation']!;
      expect(bit.solved, 1);
      expect(bit.started, 2);
      expect(bit.total, 4);
      expect(bit.order, 0);
      expect(bit.next, 'majority-element');
      expect(bit.problems!.first.slug, 'missing-number');
      expect(bit.problems!.first.number, 268);
      expect(bit.problems!.first.title, 'Missing Number');
      expect(bit.problems!.first.url, startsWith('https://leetcode.com/'));
      expect(coach.clusters!['intervals']!.problems, isNull);
      expect(coach.clusters!['sliding-window'], isNull);
      final howTo = coach.howTo!;
      expect(howTo.commands!.single.command, 'leetcode due');
      expect(howTo.commands!.single.meaning, startsWith('List'));
      expect(howTo.steps!.single.name, 'Constraint');
      expect(howTo.steps!.single.text, 'Turn it into a rule.');
      expect(howTo.nextNote, 'It may serve a later one.');
      expect(howTo.firstCommand, 'leetcode --cluster bit-cancellation');
    });

    test('the real exporter snapshot carries the known-empty coach', () {
      final coach = fixture('snapshot_real').coach!;
      expect(coach.problems, isEmpty);
      expect(coach.clusters!['bit-cancellation']!.problems, hasLength(4));
      expect(coach.howTo!.firstCommand, 'leetcode --cluster bit-cancellation');
    });

    test('an empty coach is known, not unknown', () {
      final coach = fixture('snapshot_coach_empty').coach!;
      expect(coach.problems, isEmpty);
      expect(coach.retestsDue, isEmpty);
      expect(coach.clusters, hasLength(6));
      expect(coach.clusters!.values.every((c) => c!.solved == 0), isTrue);
      expect(coach.howTo!.commands, hasLength(4));
      expect(coach.howTo!.steps, hasLength(4));
    });
  });
}
