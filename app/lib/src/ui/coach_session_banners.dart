/// The session screen's status rows: the request in flight (with "send
/// again"), the relay's last refusal and the end of the session.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';

/// Words for each `end_reason`.
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
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        if (pending != null)
          _Row(
            key: const Key('request-status'),
            text: pending.text,
            action: pending.resendable
                ? TextButton(
                    key: const Key('send-again'),
                    onPressed: () => unawaited(c.resend()),
                    child: const Text('Send again'),
                  )
                : null,
          ),
        if (failure != null)
          _Row(
            key: const Key('failure'),
            text: failure.text,
            color: scheme.error,
            action: failure.retry
                ? TextButton(
                    key: const Key('retry-new'),
                    onPressed: c.canAct ? c.retryFailure : null,
                    child: const Text('Send again'),
                  )
                : null,
          ),
        if (session != null && !session.live)
          _Row(key: const Key('ended'), text: endedText(session.endReason)),
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const new({required this.text, this.action, this.color, super.key});

  final String text;
  final Widget? action;
  final Color? color;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    color: Theme.of(context).colorScheme.surfaceContainerHigh,
    padding: const EdgeInsets.symmetric(
      horizontal: AppSpacing.md,
      vertical: AppSpacing.sm,
    ),
    child: Row(
      children: [
        Expanded(
          child: Text(text, style: TextStyle(color: color)),
        ),
        ?action,
      ],
    ),
  );
}
