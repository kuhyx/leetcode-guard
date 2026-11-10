/// The Coach tab's history: one row per coached problem with its latest
/// session's four grades, the Accepted and the highest hint rung.
///
/// No words (textgate): the slug and the day are data; the cluster is its
/// glyph; each graded step is its mark plus the grade pill, a forced or an
/// unchecked mark and the try count; the rest are glyphs with ✓ / ✗ / the
/// rung code. The old sentences are the spoken labels.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/coach_grade.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The graded steps: the snapshot's key and the session step number.
const kGradedSteps = <(String, int)>[
  ('constraint', 1),
  ('requirements', 2),
  ('toolbox', 3),
  ('postmortem', 5),
];

/// Spoken: "Constraint: pass, forced, not checked, 2 tries"; an ungraded
/// step says so, an unknown field says "?", and nothing turns into a zero.
String gradeLine(String label, StepGradeSummary? g) {
  if (g == null) return '$label: not graded';
  final attempts = g.attempts;
  return [
    '$label: ${show(g.grade)}',
    if (g.forced ?? false) 'forced',
    if (g.via == 'unverified') kNotChecked,
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
    final cluster = p.cluster;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Line(show(p.slug), strong: true),
        Row(
          children: [
            Icon(
              cluster == null ? Icons.help_outline : clusterIcon(cluster),
              size: 18,
              semanticLabel: show(cluster),
            ),
            const SizedBox(width: AppSpacing.sm),
            Muted(show(p.day)),
          ],
        ),
        // A CLI-only session has neither grades nor an Accepted watch: one
        // mark says so, rather than two rows of "?".
        if (grades == null)
          InfoRow('Grades', kUnknown, icon: Icons.grading)
        else ...[
          for (final (key, n) in kGradedSteps)
            _GradeRow(n, grades[key], key: Key('grades-${p.slug}-$n')),
          InfoRow(
            'Accepted on LeetCode',
            show(p.accepted),
            icon: Icons.verified,
            key: Key('accepted-${p.slug}'),
          ),
        ],
        InfoRow(
          'Hint rung${p.revealed ?? false ? ', revealed' : ''}',
          show(p.maxRung),
          icon: p.revealed ?? false
              ? Icons.visibility
              : Icons.lightbulb_outline,
          key: Key('rung-${p.slug}'),
        ),
        InfoRow(
          'Requirements before code',
          show(p.reqBeforeCode),
          icon: Icons.checklist,
          key: Key('req-first-${p.slug}'),
        ),
        _ReqCheck(p.reqCheck, key: Key('req-check-${p.slug}')),
        // Separates one problem from the next inside the shared card.
        const SizedBox(height: AppSpacing.sm),
      ],
    );
  }
}

/// One graded step: its mark, then the grade pill (or `–` when it was
/// never graded, `?` when unreadable), forced / unchecked marks, tries.
class _GradeRow extends StatelessWidget {
  const new(this.n, this.g, {super.key});

  final int n;
  final StepGradeSummary? g;

  @override
  Widget build(BuildContext context) {
    final g = this.g;
    final grade = Grade.parse(g?.grade);
    final warning = statusColors(context).warning;
    final attempts = g?.attempts;
    final spoken = gradeLine(stepGlyph(n).name, g);
    return Semantics(
      label: spoken,
      child: ExcludeSemantics(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          child: Row(
            children: [
              StepMark(n, size: 20),
              const SizedBox(width: AppSpacing.md),
              if (g == null)
                const Muted('–')
              else if (grade != null)
                GradeBadge(grade)
              else
                const Muted(kUnknown),
              if (g?.forced ?? false) Icon(Icons.redo, color: warning),
              if (g?.via == 'unverified')
                Icon(Icons.help_outline, color: warning),
              const Spacer(),
              if (attempts != null)
                GlyphCount(Icons.replay, '$attempts', semanticLabel: 'tries'),
            ],
          ),
        ),
      ),
    );
  }
}

/// The requirement check's verdict as a status glyph; a verdict this build
/// does not know shows as "?" with the verdict spoken.
class _ReqCheck extends StatelessWidget {
  const new(this.verdict, {super.key});

  final String? verdict;

  @override
  Widget build(BuildContext context) {
    final colors = statusColors(context);
    final (icon, color) = switch (verdict) {
      'pass' => (Icons.check_circle, colors.success),
      'incomplete' => (Icons.contrast, colors.warning),
      'unverified' => (Icons.help_outline, colors.warning),
      _ => (null, null),
    };
    return Row(
      children: [
        Icon(
          Icons.fact_check_outlined,
          size: AppSpacing.lg,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
          semanticLabel: 'Requirements check: ${show(verdict)}',
        ),
        const Spacer(),
        if (icon != null) Icon(icon, color: color) else const Muted(kUnknown),
      ],
    );
  }
}
