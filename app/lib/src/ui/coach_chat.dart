/// The coach's chat: the messages (newest at the bottom), "Run code" on a
/// pasted code message with its example lines, and the composer with Hint
/// and Reveal.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/ui/coach_chat_message.dart';
import 'package:leetcode_guard/src/ui/coach_step_inputs.dart';

/// The chat panel.
class ChatPanel extends StatelessWidget {
  /// Creates the panel; [onReveal] confirms and sends a reveal.
  const new({
    required this.controller,
    required this.input,
    required this.onReveal,
    super.key,
  });

  /// The session controller.
  final CoachController controller;

  /// The composer's draft.
  final TextEditingController input;

  /// Asks, then reveals.
  final Future<void> Function() onReveal;

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final pending = c.pending;
    final sending = pending != null && pending.kind == 'chat'
        ? pending.body['text']
        : null;
    // Reversed, so the list sticks to the newest message as it grows.
    final rows = <Widget>[
      if (sending is String) PendingBubble(sending),
      for (final m in c.messages.reversed) MessageBubble(m, controller: c),
    ];
    return Column(
      children: [
        Expanded(
          child: ListView(
            key: const Key('chat-list'),
            reverse: true,
            padding: const EdgeInsets.all(AppSpacing.md),
            children: rows,
          ),
        ),
        _Composer(controller: c, input: input, onReveal: onReveal),
      ],
    );
  }
}

class _Composer extends StatelessWidget {
  const new({
    required this.controller,
    required this.input,
    required this.onReveal,
  });

  final CoachController controller;
  final TextEditingController input;
  final Future<void> Function() onReveal;

  void _send() {
    final text = input.text;
    // Typed `reveal` IS a reveal on the relay: it gets the same question.
    if (text.trim() == 'reveal') {
      unawaited(onReveal());
      return;
    }
    if (controller.sendChat(text)) input.clear();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: input,
    builder: (context, _) {
      final c = controller;
      final live = c.sid != null;
      final act = live && c.canAct;
      final text = input.text;
      final canSend = act && text.trim().isNotEmpty && fitsLimit(text);
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            CallbackShortcuts(
              bindings: {
                const SingleActivator(
                  LogicalKeyboardKey.enter,
                  control: true,
                ): () {
                  if (canSend) _send();
                },
              },
              child: TextField(
                key: const Key('chat-input'),
                controller: input,
                enabled: live,
                minLines: 1,
                maxLines: 6,
                decoration: InputDecoration(
                  border: const OutlineInputBorder(),
                  hintText: live
                      ? 'Ask the coach, or paste JavaScript (Ctrl+Enter sends)'
                      : 'The session has ended',
                  errorText: limitError(text),
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                OutlinedButton(
                  key: const Key('hint'),
                  onPressed: act ? c.hint : null,
                  child: const Text('Hint'),
                ),
                const SizedBox(width: AppSpacing.sm),
                OutlinedButton(
                  key: const Key('reveal'),
                  onPressed: act ? onReveal : null,
                  child: const Text('Reveal'),
                ),
                const Spacer(),
                FilledButton(
                  key: const Key('chat-send'),
                  onPressed: canSend ? _send : null,
                  child: const Text('Send'),
                ),
              ],
            ),
          ],
        ),
      );
    },
  );
}
