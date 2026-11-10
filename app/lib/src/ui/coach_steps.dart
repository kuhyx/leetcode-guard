/// The stepper: five step headers, the shown step's input under its own.
///
/// A locked step's header is disabled: it cannot be opened, because what it
/// asks for depends on the steps before it (spec decision 3).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/coach_session_screen.dart';
import 'package:leetcode_guard/src/ui/coach_step_body.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Spoken while the PC starts the session.
const kStartingSession = 'Waiting for the PC to start the session...';

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
      // The PC is starting the session: a glyph, no sentence (no spinner:
      // an endless animation would never let the screen settle).
      return const Padding(
        padding: kGutter,
        child: Center(
          child: Icon(
            Icons.hourglass_top,
            size: 48,
            semanticLabel: kStartingSession,
          ),
        ),
      );
    }
    return ListView(
      key: const Key('steps-list'),
      padding: kGutter,
      children: [
        for (var n = 1; n <= kStepGlyphs.length; n++) ...[
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
            // Number + step glyph name the step; the status glyph and its
            // hue say where it stands (the old words are spoken only).
            child: Row(
              children: [
                Icon(icon, color: color, semanticLabel: status.name),
                const SizedBox(width: AppSpacing.md),
                StepMark(n, color: locked ? scheme.onSurfaceVariant : null),
                const Spacer(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
