/// The session screen's status rows: the request in flight (with "send
/// again"), the relay's last refusal and the end of the session.
///
/// No words (textgate): each row is a glyph picked from machine data (the
/// request phase, the relay's error code, the end reason) in its hue; the
/// sentence the row used to paint is its spoken label.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/pending.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Spoken for each `end_reason`.
String endedText(String? reason) => switch (reason) {
  'done' => 'Session ended: all five steps done.',
  'reveal' => 'Session ended: the solution was revealed.',
  _ => 'Session ended.',
};

/// Every status row that applies to [controller] right now.
class SessionBanners extends StatelessWidget {
  /// Creates the rows.
  const new(this.controller, {super.key});

  /// The session controller.
  final CoachController controller;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final pending = c.pending;
    final failure = c.failure;
    final session = c.state?.session;
    final colors = statusColors(context);
    return Column(
      children: [
        if (pending != null)
          _Row(
            key: const Key('request-status'),
            icon: phaseIcon(pending.phase),
            spoken: pending.text,
            // Stalled or unsent turns amber beside its resend button.
            color: pending.resendable ? colors.warning : null,
            action: pending.resendable
                ? TextButton(
                    key: const Key('send-again'),
                    onPressed: () => unawaited(c.resend()),
                    child: const Icon(
                      Icons.refresh,
                      semanticLabel: 'Send again',
                    ),
                  )
                : null,
          ),
        if (failure != null)
          _Row(
            key: const Key('failure'),
            icon: failureIcon(failure.code),
            spoken: failure.text,
            color: colors.danger,
            trailing: _resets(failure),
            action: failure.retry
                ? TextButton(
                    key: const Key('retry-new'),
                    onPressed: c.canAct ? c.retryFailure : null,
                    child: const Icon(
                      Icons.refresh,
                      semanticLabel: 'Send again',
                    ),
                  )
                : null,
          ),
        if (session != null && !session.live)
          _Row(
            key: const Key('ended'),
            icon: endIcon(session.endReason),
            spoken: endedText(session.endReason),
          ),
      ],
    );
  }

  /// When Claude is back, as `◷ HH:MM` (only a unix-ms `resets_at`; a
  /// preformatted one is words, so it stays in the spoken text).
  static String? _resets(RelayFailure failure) {
    final ms = readInt(failure.result.raw['resets_at']);
    return ms == null ? null : asOf(DateTime.fromMillisecondsSinceEpoch(ms));
  }
}

class _Row extends StatelessWidget {
  const new({
    required this.icon,
    required this.spoken,
    this.action,
    this.color,
    this.trailing,
    super.key,
  });

  final IconData icon;
  final String spoken;
  final Widget? action;
  final Color? color;
  final String? trailing;

  @override
  Widget build(BuildContext context) {
    final trailing = this.trailing;
    return Container(
      width: double.infinity,
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          Icon(icon, color: color, semanticLabel: spoken),
          if (trailing != null) ...[
            const SizedBox(width: AppSpacing.sm),
            Muted(trailing),
          ],
          const Spacer(),
          ?action,
        ],
      ),
    );
  }
}
