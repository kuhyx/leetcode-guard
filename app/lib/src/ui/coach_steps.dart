/// The stepper: five step headers, the shown step's input under its own.
///
/// A locked step's header is disabled: it cannot be opened, because what it
/// asks for depends on the steps before it (spec decision 3).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/coach_session_screen.dart';
import 'package:leetcode_guard/src/ui/coach_step_body.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Each step's label and what it asks of kuhy.
const kSteps = <(String, String)>[
  (
    'Constraint',
    'What does the hard constraint rule out, and what rule does it give you?',
  ),
  (
    'Requirements',
    'List the properties a solution needs, one per field. '
        'No code and no tool names yet.',
  ),
  (
    'Toolbox',
    'Pick the toolbox entries whose properties cover your requirements.',
  ),
  (
    'Implement',
    'Solve it on LeetCode. This step completes on its own once LeetCode '
        'shows an Accepted for this problem.',
  ),
  (
    'Post-mortem',
    'Why did it work? Name the property that made the solution possible.',
  ),
];

/// The five steps.
class StepsPanel extends StatelessWidget {
  /// Creates the panel; [selected] is the step whose body shows.
  const new({
    required this.controller,
    required this.drafts,
    required this.selected,
    required this.onSelect,
    required this.openUrl,
    super.key,
  });

  /// The session controller.
  final CoachController controller;

  /// What kuhy has typed so far.
  final SessionDrafts drafts;

  /// The step shown, or null.
  final int? selected;

  /// Shows step n.
  final ValueChanged<int> onSelect;

  /// Opens the problem page.
  final UrlOpener openUrl;

  @override
  Widget build(BuildContext context) {
    final state = controller.state;
    if (state == null || state.steps.isEmpty) {
      return const Padding(
        padding: kGutter,
        child: Column(
          children: [Muted('Waiting for the PC to start the session...')],
        ),
      );
    }
    return ListView(
      key: const Key('steps-list'),
      padding: kGutter,
      children: [
        for (var n = 1; n <= kSteps.length; n++) ...[
          _StepHeader(n, state.stepAt(n), onSelect, selected: selected == n),
          if (selected == n)
            if (state.stepAt(n) case final CoachStep step)
              StepBody(
                n: n,
                step: step,
                controller: controller,
                drafts: drafts,
                openUrl: openUrl,
              ),
        ],
      ],
    );
  }
}

class _StepHeader extends StatelessWidget {
  const new(this.n, this.step, this.onSelect, {required this.selected});

  final int n;
  final CoachStep? step;
  final bool selected;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final status = step?.status ?? StepStatus.unknown;
    final locked = status == StepStatus.locked || step == null;
    final (icon, color) = switch (status) {
      StepStatus.passed => (Icons.check_circle, statusColors(context).success),
      StepStatus.forced => (Icons.redo, statusColors(context).warning),
      StepStatus.open => (Icons.radio_button_unchecked, scheme.primary),
      _ => (Icons.lock_outline, scheme.onSurfaceVariant),
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Material(
        color: selected ? scheme.surfaceContainerHigh : Colors.transparent,
        borderRadius: BorderRadius.circular(AppRadius.md),
        child: InkWell(
          key: Key('step-$n'),
          borderRadius: BorderRadius.circular(AppRadius.md),
          onTap: locked ? null : () => onSelect(n),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Text(
                    '$n. ${kSteps[n - 1].$1}',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: locked ? scheme.onSurfaceVariant : null,
                    ),
                  ),
                ),
                Text(
                  status.name,
                  style: TextStyle(color: scheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
