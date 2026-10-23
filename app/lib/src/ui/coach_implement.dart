/// Step 4: the problem link and the Accepted watch. Never graded or forced:
/// it passes only when the relay sees an Accepted (`DOCS-coach-relay.md` §3).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/problem_url.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Step 4: open the problem, then wait for LeetCode's Accepted.
class ImplementStatus extends StatelessWidget {
  /// Creates the step-4 view.
  const new({
    required this.step,
    required this.url,
    required this.openUrl,
    required this.now,
    super.key,
  });

  /// The clock's now, for the last-checked time.
  final DateTime now;

  /// The relay's view of step 4.
  final CoachStep step;

  /// The problem page, from the session.
  final String? url;

  /// Opens it.
  final UrlOpener openUrl;

  @override
  Widget build(BuildContext context) {
    final target = url;
    final valid = target != null && isProblemUrl(target);
    final checked = step.probedAt;
    // Status hues are fills, not text colours: they mark the icon only.
    final colors = statusColors(context);
    final (text, icon, color) = switch ((step.status, step.probe)) {
      (StepStatus.passed, _) => (
        'Accepted on LeetCode.',
        Icons.check_circle,
        colors.success,
      ),
      (_, 'unknown') => (
        'Could not check LeetCode just now; the PC tries again within a '
            'minute.',
        Icons.help_outline,
        colors.warning,
      ),
      _ => (
        'Waiting for Accepted: the PC checks LeetCode once a minute.',
        Icons.hourglass_empty,
        Theme.of(context).colorScheme.onSurfaceVariant,
      ),
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FilledButton.icon(
          key: const Key('open-leetcode'),
          onPressed: valid ? () => openUrl(Uri.parse(target)) : null,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Open on LeetCode'),
        ),
        const SizedBox(height: AppSpacing.sm),
        Row(
          children: [
            Icon(icon, color: color),
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: Line(text)),
          ],
        ),
        if (checked != null) Muted('Last checked ${timeOfMs(checked, now)}'),
      ],
    );
  }
}
