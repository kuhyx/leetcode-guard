/// One chat message: kuhy on the right, the coach on the left, the relay's
/// own lines (grades, Accepted, refusals) as muted notes.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The label above a message.
String roleLabel(ChatMessage m) {
  final who = switch (m.role) {
    'kuhy' => 'You',
    'coach' => 'Coach',
    _ => 'PC',
  };
  return m.kind == 'chat' ? who : '$who, ${m.kind}';
}

/// Whether [m] gets "Run code": kuhy's own message that reads as code.
bool runnable(ChatMessage m) => m.role == 'kuhy' && looksLikeCode(m.text);

/// A message bubble.
class MessageBubble extends StatelessWidget {
  /// Creates the bubble for [message].
  const new(this.message, {required this.controller, super.key});

  /// The message.
  final ChatMessage message;

  /// The session controller (for "Run code").
  final CoachController controller;

  @override
  Widget build(BuildContext context) {
    final m = message;
    final scheme = Theme.of(context).colorScheme;
    if (m.role == 'system') {
      return Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Muted(m.text),
      );
    }
    final mine = m.role == 'kuhy';
    final code = looksLikeCode(m.text);
    final c = controller;
    final canRun = c.canAct && c.sid != null && (c.state?.codeOpen ?? false);
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: AppSpacing.md),
        padding: const EdgeInsets.all(AppSpacing.md),
        constraints: const BoxConstraints(maxWidth: 600),
        decoration: BoxDecoration(
          color: mine
              ? scheme.surfaceContainerHighest
              : scheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(roleLabel(m), style: Theme.of(context).textTheme.labelMedium),
            const SizedBox(height: AppSpacing.xs),
            SelectableText(m.text, style: code ? monoStyle(context) : null),
            if (runnable(m)) ...[
              const SizedBox(height: AppSpacing.sm),
              TextButton.icon(
                key: Key('run-${m.key}'),
                onPressed: canRun ? () => c.runCode(m.text) : null,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Run code'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// kuhy's message on its way to the relay.
class PendingBubble extends StatelessWidget {
  /// Creates the bubble for [text].
  const new(this.text, {super.key});

  /// What is being sent.
  final String text;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerRight,
    child: Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      constraints: const BoxConstraints(maxWidth: 600),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).colorScheme.outline),
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'You (sending...)',
            style: Theme.of(context).textTheme.labelMedium,
          ),
          Text(text),
        ],
      ),
    ),
  );
}
