/// The Coach tab's "How to start" card: the method, the first command in a
/// monospace box with a copy button, and the other commands.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// "How to start": the method, the first command and the other commands;
/// "unknown" when [howTo] is null.
class HowToCard extends StatelessWidget {
  /// Creates the card over [howTo].
  const new(this.howTo, {super.key});

  /// The coach's `how_to` block, or null when unknown.
  final HowTo? howTo;

  @override
  Widget build(BuildContext context) {
    const title = 'How to start';
    final h = howTo;
    if (h == null) return const SectionCard.unknown(title: title);
    final first = h.firstCommand;
    return SectionCard(
      title: title,
      children: [
        for (final (index, step) in (h.steps ?? const <HowToStep>[]).indexed)
          _Step(index + 1, step),
        if (first != null) ...[
          const SizedBox(height: AppSpacing.sm),
          const Muted('First session:'),
          _CommandBox(first),
        ],
        const SizedBox(height: AppSpacing.sm),
        const Muted('Commands:'),
        for (final c in h.commands ?? const <HowToCommand>[]) _CommandRow(c),
      ],
    );
  }
}

class _Step extends StatelessWidget {
  const new(this.number, this.step);

  final int number;
  final HowToStep step;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Line('$number. ${show(step.name)}', strong: true),
      Muted(show(step.text)),
    ],
  );
}

/// The monospace style for anything kuhy types.
TextStyle monoStyle(BuildContext context) => TextStyle(
  fontFamily: 'DejaVuSansMono',
  fontFamilyFallback: const ['monospace'],
  fontSize: AppTextSize.label,
  color: Theme.of(context).colorScheme.onSurface,
);

/// A command in a monospace box, with a button that copies it.
class _CommandBox extends StatelessWidget {
  const new(this.command);

  final String command;

  Future<void> _copy(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: command));
    if (context.mounted) showToast(context, 'Copied');
  }

  @override
  Widget build(BuildContext context) => Container(
    key: const Key('command-box'),
    padding: const EdgeInsets.only(left: AppSpacing.md),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainerLowest,
      borderRadius: BorderRadius.circular(AppRadius.sm),
    ),
    child: Row(
      children: [
        Expanded(
          // One line however narrow: a command broken at a hyphen reads as
          // two. It shrinks to fit only when it would not.
          child: FittedBox(
            alignment: Alignment.centerLeft,
            fit: BoxFit.scaleDown,
            child: SelectableText(command, style: monoStyle(context)),
          ),
        ),
        IconButton(
          key: const Key('copy-command'),
          tooltip: 'Copy command',
          icon: const Icon(Icons.copy),
          onPressed: () => _copy(context),
        ),
      ],
    ),
  );
}

class _CommandRow extends StatelessWidget {
  const new(this.entry);

  final HowToCommand entry;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectableText(show(entry.command), style: monoStyle(context)),
        Muted(show(entry.meaning)),
      ],
    ),
  );
}
