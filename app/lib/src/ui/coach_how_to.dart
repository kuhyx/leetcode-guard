/// The Coach tab's "How to start" card: the method as a row of step glyphs,
/// the first command in a monospace box with a copy button, and the other
/// commands in a sheet.
///
/// No words (textgate): the commands are what kuhy types (content); the
/// coach's step names and explanations and each command's meaning are
/// spoken only.
library;

import 'dart:async';

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/ui/coach_dialogs.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The card's spoken title (a [SectionCard] title is never painted).
const kHowToTitle = 'How to start';

/// The card's painted mark, also its phone chip.
const kHowToIcon = Icon(
  Icons.rocket_launch_outlined,
  semanticLabel: kHowToTitle,
);

/// "How to start" over [howTo]; unknown when it is null. A bare
/// [SectionCard], so the phone chip shows its icon.
SectionCard howToCard(HowTo? howTo) {
  if (howTo == null) {
    return const SectionCard.unknown(title: kHowToTitle, leading: kHowToIcon);
  }
  final first = howTo.firstCommand;
  return SectionCard(
    title: kHowToTitle,
    leading: kHowToIcon,
    children: [
      _Method(howTo.steps ?? const []),
      if (first != null) ...[
        const SizedBox(height: AppSpacing.sm),
        _CommandBox(first),
      ],
      Align(
        alignment: Alignment.centerLeft,
        child: _CommandsButton(howTo.commands ?? const []),
      ),
    ],
  );
}

/// The method's steps as glyphs in order, arrows between them.
class _Method extends StatelessWidget {
  const new(this.steps);

  final List<HowToStep> steps;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Wrap(
      key: const Key('method'),
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: AppSpacing.xs,
      children: [
        for (final (i, step) in steps.indexed) ...[
          if (i > 0) Icon(Icons.arrow_forward, size: 16, color: muted),
          Icon(
            switch (stepNumberOf(step.name)) {
              final int n => stepGlyph(n).icon,
              null => Icons.circle_outlined,
            },
            key: Key('method-$i'),
            semanticLabel: '${i + 1}. ${show(step.name)}: ${show(step.text)}',
          ),
        ],
      ],
    );
  }
}

/// Opens the sheet of every command.
class _CommandsButton extends StatelessWidget {
  const new(this.commands);

  final List<HowToCommand> commands;

  @override
  Widget build(BuildContext context) => IconButton(
    key: const Key('show-commands'),
    icon: const Icon(Icons.list, semanticLabel: 'All commands'),
    onPressed: () => unawaited(
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (_) => SafeArea(
          child: ListView(
            key: const Key('sheet'),
            padding: kGutter,
            shrinkWrap: true,
            children: [for (final c in commands) _CommandRow(c)],
          ),
        ),
      ),
    ),
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
    if (context.mounted) {
      showIconSnack(context, Icons.check, semanticLabel: 'Copied');
    }
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
        const Icon(Icons.terminal, semanticLabel: 'First session'),
        const SizedBox(width: AppSpacing.sm),
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
          icon: const Icon(Icons.copy, semanticLabel: 'Copy command'),
          onPressed: () => _copy(context),
        ),
      ],
    ),
  );
}

/// A command, its meaning spoken.
class _CommandRow extends StatelessWidget {
  const new(this.entry);

  final HowToCommand entry;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
    child: Row(
      children: [
        Icon(Icons.terminal, size: 18, semanticLabel: show(entry.meaning)),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: SelectableText(show(entry.command), style: monoStyle(context)),
        ),
      ],
    ),
  );
}
