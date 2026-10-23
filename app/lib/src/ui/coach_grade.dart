/// A step's grade: the badge, "not checked" when the grader was down, the
/// feedback, the failed-try count, "Continue anyway" and step 5's cards.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The grade badge: a filled pill with `on-fill` text (never near-white on
/// a status fill, which fails contrast).
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
      child: Text(grade.name, style: TextStyle(color: colors.onStatus)),
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
                const Muted('not checked'),
              ],
              const Spacer(),
              Muted('Failed tries: ${show(step.attempts)}'),
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
              child: const Text('Continue anyway'),
            ),
          ),
        if (cards != null) Line(_cardsText(cards)),
      ],
    );
  }

  static String _cardsText(Json cards) {
    final error = readString(cards['error']);
    final built = show(readInt(cards['built']));
    final deck = readString(cards['deck']) ?? kUnknown;
    return error == null
        ? 'Built $built Anki cards in $deck.'
        : 'Built $built Anki cards; the rest failed: $error';
  }
}
