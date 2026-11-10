/// The coach's one icon vocabulary (textgate, 2026-11-08: no painted
/// words). Each glyph keeps its old wording as the spoken label only: the
/// stepper, the step body, the Coach-tab history and the how-to card all
/// draw a step with the same shape, and a grade with the same pill.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/coach/transport.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';

/// A step's glyph, its spoken name and what it asks (spoken only).
typedef StepGlyph = ({IconData icon, String name, String asks});

/// The five steps, in order (`DOCS-coach-ui-spec.md`).
const kStepGlyphs = <StepGlyph>[
  (
    icon: Icons.fence,
    name: 'Constraint',
    asks:
        'What does the hard constraint rule out, and what rule does it '
        'give you?',
  ),
  (
    icon: Icons.checklist,
    name: 'Requirements',
    asks:
        'List the properties a solution needs, one per field. No code and '
        'no tool names yet.',
  ),
  (
    icon: Icons.handyman,
    name: 'Toolbox',
    asks: 'Pick the toolbox entries whose properties cover your requirements.',
  ),
  (
    icon: Icons.code,
    name: 'Implement',
    asks:
        'Solve it on LeetCode. This step completes on its own once LeetCode '
        'shows an Accepted for this problem.',
  ),
  (
    icon: Icons.history_edu,
    name: 'Post-mortem',
    asks: 'Why did it work? Name the property that made the solution possible.',
  ),
];

/// The glyph of step [n] (1..5).
StepGlyph stepGlyph(int n) => kStepGlyphs[n - 1];

/// The step a how-to or history name means (`Post-mortem`, `postmortem`,
/// `Constraint`...), or null for a name this build does not know.
int? stepNumberOf(String? name) {
  final key = name?.toLowerCase().replaceAll(RegExp('[^a-z]'), '');
  for (final (i, g) in kStepGlyphs.indexed) {
    if (g.name.toLowerCase().replaceAll('-', '') == key) return i + 1;
  }
  return null;
}

/// Grade shapes: a check, a half disc, a cross (the colour is the pill's).
IconData gradeIcon(Grade grade) => switch (grade) {
  Grade.pass => Icons.check,
  Grade.partial => Icons.contrast,
  Grade.fail => Icons.close,
};

/// How a session ended.
IconData endIcon(String? reason) => switch (reason) {
  'done' => Icons.flag,
  'reveal' => Icons.visibility,
  _ => Icons.stop_circle_outlined,
};

/// Why the PC cannot take a request.
IconData presenceIcon(CoachPresence presence, CoachOutage? outage) =>
    switch ((presence, outage)) {
      (CoachPresence.relayDown, _) => Icons.power_off,
      (CoachPresence.pcOffline, _) => Icons.desktop_access_disabled,
      (_, CoachOutage.signedOut) => Icons.no_accounts,
      (_, CoachOutage.rejected) => Icons.block,
      (_, CoachOutage.network) => Icons.wifi_off,
      (CoachPresence.checking, _) => Icons.computer,
      _ => Icons.cloud_off,
    };

/// Where a request in flight stands.
IconData phaseIcon(RequestPhase phase) => switch (phase) {
  RequestPhase.queued => Icons.schedule_send,
  RequestPhase.working => Icons.psychology,
  RequestPhase.stalled => Icons.hourglass_disabled,
  RequestPhase.notSent => Icons.cloud_off,
};

/// What the relay refused, by its error code (`DOCS-coach-relay.md` §2).
IconData failureIcon(String? code) => switch (code) {
  'phase_locked' => Icons.checklist,
  'step_locked' => Icons.lock_outline,
  'step_done' => Icons.done_all,
  'cannot_force' => Icons.block,
  'rate_limited' => Icons.timer,
  'claude_unavailable' => Icons.smart_toy,
  'model_error' => Icons.psychology_alt,
  'worker_error' => Icons.bug_report,
  'no_answer_key' => Icons.key_off,
  'session_live' => Icons.play_disabled,
  'not_live' => Icons.stop_circle_outlined,
  _ => Icons.error_outline,
};

/// The relay's own chat lines, by `kind`.
IconData systemIcon(String kind) => switch (kind) {
  'grade' => Icons.grading,
  'accepted' => Icons.verified,
  'refused' => Icons.block,
  'run' => Icons.play_arrow,
  _ => Icons.info_outline,
};

/// A cluster's shape, by its curriculum id; any other id gets a generic
/// one (its name stays spoken).
IconData clusterIcon(String name) => switch (name) {
  'bit-cancellation' => Icons.exposure,
  'two-pointers' => Icons.compare_arrows,
  'sliding-window' => Icons.view_week,
  'prefix-sum-hash' => Icons.functions,
  'monotonic-stack' => Icons.stacked_bar_chart,
  'intervals' => Icons.linear_scale,
  _ => Icons.category,
};

/// The step glyph with its number on it: the stepper's and history's mark.
class StepMark extends StatelessWidget {
  /// Creates the mark of step [n], tinted [color].
  const new(this.n, {this.color, this.size = 24, super.key});

  /// 1..5.
  final int n;

  /// Tint, default the theme's.
  final Color? color;

  /// Icon size.
  final double size;

  @override
  Widget build(BuildContext context) {
    final g = stepGlyph(n);
    final tint = color ?? Theme.of(context).colorScheme.onSurface;
    return Semantics(
      label: g.name,
      child: ExcludeSemantics(
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '$n',
              style: TextStyle(color: tint, fontSize: size * 0.7),
            ),
            const SizedBox(width: 2),
            Icon(g.icon, color: tint, size: size),
          ],
        ),
      ),
    );
  }
}
