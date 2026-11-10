/// The coach's chat: the messages (newest at the bottom), "Run code" on a
/// pasted code message (its example lines come back as the relay's own
/// `run` line), and the composer with Hint and Reveal.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/ui/coach_chat_message.dart';
import 'package:leetcode_guard/src/ui/coach_step_inputs.dart';

/// Ctrl+Enter as keycap symbols (no letters): the desktop send chord.
const kSendChord = '⌃⏎';

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
                // The field's glyph says what goes in (a lock once the
                // session ended); the desktop shows the send chord as keycap
                // symbols. The old hint sentences are spoken only.
                decoration: limitDecoration(
                  text,
                  prefixIcon: Icon(
                    live ? Icons.chat_bubble_outline : Icons.lock_outline,
                    semanticLabel: !live
                        ? 'The session has ended'
                        : 'Ask the coach, or paste JavaScript',
                  ),
                  // A phone has no Ctrl key to speak of.
                  suffix: live && !c.transport.phone
                      ? const Text(
                          kSendChord,
                          semanticsLabel: 'Ctrl+Enter sends',
                        )
                      : null,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                OutlinedButton(
                  key: const Key('hint'),
                  onPressed: act ? c.hint : null,
                  child: const Icon(
                    Icons.lightbulb_outline,
                    semanticLabel: 'Hint',
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                OutlinedButton(
                  key: const Key('reveal'),
                  onPressed: act ? onReveal : null,
                  child: const Icon(Icons.visibility, semanticLabel: 'Reveal'),
                ),
                const Spacer(),
                FilledButton(
                  key: const Key('chat-send'),
                  onPressed: canSend ? _send : null,
                  child: const Icon(Icons.send, semanticLabel: 'Send'),
                ),
              ],
            ),
          ],
        ),
      );
    },
  );
}
