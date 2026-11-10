/// A step's grade: the badge, a mark when the grader was down, the
/// feedback, the failed-try count, "continue anyway" and step 5's cards.
///
/// No words (textgate): the grade is a shape on a status fill, the tries a
/// number by a retry glyph; the old words are spoken only. The feedback is
/// the grader's own, about kuhy's answer: content, shown as is.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The grade badge: a filled pill holding the grade's shape in `on-fill`
/// (never near-white on a status fill, which fails contrast).
class GradeBadge extends StatelessWidget {
  /// Creates the badge for [grade].
  const new(this.grade, {super.key});

  /// The grade.
  final Grade grade;

  @override
  Widget build(BuildContext context) {
    final colors = statusColors(context);
    final fill = switch (grade) {
      Grade.pass => colors.success,
      Grade.partial => colors.warning,
      Grade.fail => colors.danger,
    };
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Icon(
        gradeIcon(grade),
        size: 18,
        color: colors.onStatus,
        semanticLabel: grade.name,
      ),
    );
  }
}

/// Spoken for a grade the grader did not check (it was down).
const kNotChecked = 'not checked';

/// A count beside its glyph: `↻ 2`.
class GlyphCount extends StatelessWidget {
  /// Creates [count] beside [icon]; [semanticLabel] names the count.
  const new(
    this.icon,
    this.count, {
    required this.semanticLabel,
    this.color,
    super.key,
  });

  /// What is counted.
  final IconData icon;

  /// The number, already formatted.
  final String count;

  /// What it counts, spoken.
  final String semanticLabel;

  /// Tint, default muted.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tint = color ?? Theme.of(context).colorScheme.onSurfaceVariant;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: tint, semanticLabel: semanticLabel),
        const SizedBox(width: AppSpacing.xs),
        Text(
          count,
          key: const Key('count'),
          style: TextStyle(color: tint),
        ),
      ],
    );
  }
}

/// Step [n]'s last grade and what can be done about it.
class GradeView extends StatelessWidget {
  /// Creates the view.
  const new({
    required this.n,
    required this.step,
    required this.controller,
    super.key,
  });

  /// 1, 2, 3 or 5.
  final int n;

  /// The relay's view of the step.
  final CoachStep step;

  /// The session controller.
  final CoachController controller;

  @override
  Widget build(BuildContext context) {
    final last = step.last;
    final grade = last?.grade;
    final cards = readMap(controller.gradeData(n)?['cards']);
    final warning = statusColors(context).warning;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (last != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              if (grade != null)
                GradeBadge(grade, key: Key('grade-$n'))
              else
                const Muted(kUnknown),
              if (last.unverified) ...[
                const SizedBox(width: AppSpacing.sm),
                Icon(
                  Icons.help_outline,
                  color: warning,
                  semanticLabel: kNotChecked,
                ),
              ],
              const Spacer(),
              GlyphCount(
                Icons.replay,
                show(step.attempts),
                semanticLabel: 'Failed tries',
                key: Key('tries-$n'),
              ),
            ],
          ),
          if (last.feedback case final String feedback) Line(feedback),
        ],
        if (step.status == StepStatus.open && step.canForce)
          Align(
            alignment: Alignment.centerLeft,
            child: OutlinedButton(
              key: Key('force-$n'),
              onPressed: controller.canAct ? () => controller.force(n) : null,
              child: const Icon(
                Icons.skip_next,
                semanticLabel: 'Continue anyway',
              ),
            ),
          ),
        if (cards != null) _Cards(cards),
      ],
    );
  }
}

/// Step 5's Anki cards: how many were built, and a red mark if some failed
/// (the card builder's error is spoken; the journal has the rest).
class _Cards extends StatelessWidget {
  const new(this.cards);

  final Json cards;

  @override
  Widget build(BuildContext context) {
    final error = readString(cards['error']);
    final built = show(readInt(cards['built']));
    final deck = readString(cards['deck']) ?? kUnknown;
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Row(
        key: const Key('cards'),
        children: [
          GlyphCount(
            Icons.style,
            built,
            semanticLabel: 'Anki cards built in $deck',
          ),
          if (error != null) ...[
            const SizedBox(width: AppSpacing.sm),
            Icon(
              Icons.error_outline,
              color: statusColors(context).danger,
              semanticLabel: 'The rest failed: $error',
            ),
          ],
        ],
      ),
    );
  }
}
