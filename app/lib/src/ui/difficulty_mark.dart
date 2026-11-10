/// Difficulty without the word (textgate): one, two or four diamonds in
/// LeetCode's green, amber and red.
///
/// The count is the credit an accepted submission is worth (Easy 1 /
/// Medium 2 / Hard 4, `_difficulty.py`), the same `◆` scale the PC lock
/// draws (`_glyphs.weight_mark`), so the mark says how hard and how much.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Credit weight per difficulty key; an unknown key weighs 1.
const kLevelWeight = {'Easy': 1, 'Medium': 2, 'Hard': 4};

/// The diamonds for [level], spoken as [semanticLabel] (default: the level).
class DifficultyMark extends StatelessWidget {
  /// Creates the mark.
  const new(this.level, {this.semanticLabel, super.key});

  /// A [kLevels] key.
  final String level;

  /// What a screen reader says instead of the diamonds.
  final String? semanticLabel;

  /// The level's colour: a fill, never text on the page.
  static Color color(BuildContext context, String level) {
    final s = statusColors(context);
    return switch (level) {
      'Easy' => s.success,
      'Medium' => s.warning,
      'Hard' => s.danger,
      _ => Theme.of(context).colorScheme.onSurfaceVariant,
    };
  }

  @override
  Widget build(BuildContext context) => Semantics(
    label: semanticLabel ?? level,
    child: ExcludeSemantics(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < (kLevelWeight[level] ?? 1); i++)
            Icon(
              Icons.diamond,
              size: AppSpacing.md,
              color: color(context, level),
            ),
        ],
      ),
    ),
  );
}

/// An [InfoRow] whose painted label is [level]'s [DifficultyMark].
class LevelRow extends InfoRow {
  /// Creates the row. [semanticLabel] (default: [level]) is what a screen
  /// reader says; it becomes [label], which keys the row (`row-<label>`) and
  /// is never painted.
  new(this.level, String value, {String? semanticLabel, super.key})
    : super(semanticLabel ?? level, value);

  /// A [kLevels] key.
  final String level;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Expanded(
            child: Align(
              alignment: Alignment.centerLeft,
              child: DifficultyMark(level, semanticLabel: label),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              value,
              key: const Key('value'),
              textAlign: TextAlign.end,
              style: TextStyle(color: value == kUnknown ? muted : null),
            ),
          ),
        ],
      ),
    );
  }
}
