/// One chat message: kuhy on the right, the coach on the left, the relay's
/// own lines (grades, Accepted, refusals, run results) as muted notes.
///
/// No words (textgate): who wrote a message is a glyph (and its side); the
/// relay's lines are a glyph per kind with the line spoken, except a run
/// line's values, which are data. What kuhy and the coach wrote is content.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/model/coach_relay.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/coach_run_result.dart';

/// Who wrote [m], spoken: "You", "Coach", "PC", plus a kind other than chat.
String roleLabel(ChatMessage m) {
  final who = switch (m.role) {
    'kuhy' => 'You',
    'coach' => 'Coach',
    _ => 'PC',
  };
  return m.kind == 'chat' ? who : '$who, ${m.kind}';
}

/// The glyph of who wrote [m] and how (a hint or a reveal).
IconData roleIcon(ChatMessage m) => switch ((m.role, m.kind)) {
  (_, 'hint') => Icons.lightbulb_outline,
  (_, 'reveal') => Icons.visibility,
  ('kuhy', _) => Icons.person,
  ('coach', _) => Icons.school,
  _ => Icons.computer,
};

/// Whether [m] gets "Run code": kuhy's own message that reads as code.
bool runnable(ChatMessage m) => m.role == 'kuhy' && looksLikeCode(m.text);

/// kuhy's Hint / Reveal button presses arrive as his own message holding
/// just the request word: the glyph says it, the word is not painted.
bool _isRequestWord(ChatMessage m) =>
    m.role == 'kuhy' && m.kind != 'chat' && m.text.trim() == m.kind;

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
    if (m.role == 'system') return SystemNote(m);
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
            Icon(
              roleIcon(m),
              size: 18,
              color: scheme.onSurfaceVariant,
              semanticLabel: roleLabel(m),
            ),
            if (!_isRequestWord(m)) ...[
              const SizedBox(height: AppSpacing.xs),
              SelectableText(m.text, style: code ? monoStyle(context) : null),
            ],
            if (runnable(m)) ...[
              const SizedBox(height: AppSpacing.sm),
              TextButton.icon(
                key: Key('run-${m.key}'),
                onPressed: canRun ? () => c.runCode(m.text) : null,
                icon: const Icon(Icons.play_arrow, semanticLabel: 'Run code'),
                label: const Icon(Icons.code),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A relay line: its kind's glyph, the line spoken; a run line also shows
/// each example's values.
class SystemNote extends StatelessWidget {
  /// Creates the note for [message].
  const new(this.message, {super.key});

  /// The relay's line.
  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final m = message;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            systemIcon(m.kind),
            key: Key('note-${m.kind}'),
            size: 18,
            color: scheme.onSurfaceVariant,
            semanticLabel: m.text,
          ),
          if (m.kind == 'run') ...[
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: RunResults(m.text)),
          ],
        ],
      ),
    );
  }
}

/// kuhy's message on its way to the relay: his glyph and a send glyph in
/// an outlined (not yet filled) bubble.
class PendingBubble extends StatelessWidget {
  /// Creates the bubble for [text].
  const new(this.text, {super.key});

  /// What is being sent.
  final String text;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        key: const Key('pending-bubble'),
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
            Semantics(
              label: kSendingLabel,
              child: ExcludeSemantics(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.person, size: 18, color: muted),
                    Icon(Icons.schedule_send, size: 18, color: muted),
                  ],
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(text),
          ],
        ),
      ),
    );
  }
}

/// Spoken over a message still being sent.
const kSendingLabel = 'You (sending...)';
