/// The Coach tab's history: one row per coached problem with its latest
/// session's four grades, the Accepted and the highest hint rung.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The graded steps, keyed as the snapshot keys them.
const kGradedSteps = <(String, String)>[
  ('constraint', 'Constraint'),
  ('requirements', 'Requirements'),
  ('toolbox', 'Toolbox'),
  ('postmortem', 'Post-mortem'),
];

/// "Constraint: pass, forced, not checked, 2 tries"; an ungraded step says
/// so, an unknown field says "unknown", and nothing turns into a zero.
String gradeLine(String label, StepGradeSummary? g) {
  if (g == null) return '$label: not graded';
  final attempts = g.attempts;
  return [
    '$label: ${show(g.grade)}',
    if (g.forced ?? false) 'forced',
    if (g.via == 'unverified') 'not checked',
    if (attempts != null) '$attempts ${attempts == 1 ? 'try' : 'tries'}',
  ].join(', ');
}

/// One coached problem.
class ProblemHistoryTile extends StatelessWidget {
  /// Creates the row.
  const new(this.p, {super.key});

  /// The problem.
  final CoachProblem p;

  @override
  Widget build(BuildContext context) {
    final grades = p.grades;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Line(show(p.slug), strong: true),
        Muted('${show(p.cluster)}, ${show(p.day)}'),
        // A CLI-only session has neither grades nor an Accepted watch: one
        // line says so, rather than two rows of "unknown".
        if (grades == null)
          const Line('Grades: $kUnknown')
        else ...[
          for (final (key, label) in kGradedSteps)
            Line(gradeLine(label, grades[key])),
          Line('Accepted on LeetCode: ${show(p.accepted)}'),
        ],
        Line(
          'Hint rung: ${show(p.maxRung)}'
          '${p.revealed ?? false ? ', revealed' : ''}',
        ),
        Line('Requirements before code: ${show(p.reqBeforeCode)}'),
        Line('Requirements check: ${show(p.reqCheck)}'),
        // Separates one problem from the next inside the shared card.
        const SizedBox(height: AppSpacing.sm),
      ],
    );
  }
}
