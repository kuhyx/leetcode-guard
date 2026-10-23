/// The few building blocks every tab is made of.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';

/// Outer gutter of every tab.
const kGutter = EdgeInsets.all(AppSpacing.md);

/// One titled group of rows on a raised surface. No shadow: this is a dark
/// UI, where depth comes from the lighter surface alone.
class SectionCard extends StatelessWidget {
  /// Creates a section titled [title] holding [children].
  const new({required this.title, required this.children, super.key});

  /// A section whose data is unknown: the title and the word, nothing else.
  const new unknown({required this.title, super.key})
    : children = const [Muted(kUnknown)];

  /// The heading.
  final String title;

  /// The rows.
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(AppRadius.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHeader(title),
          const SizedBox(height: AppSpacing.sm),
          ...children,
        ],
      ),
    );
  }
}

/// A label on the left, its value on the right. An unknown value is muted
/// so it never reads as a measured number.
class InfoRow extends StatelessWidget {
  /// Creates a row; the key `row-<label>` lets tests find its value. Rows
  /// in a list whose labels can repeat (two solves on one day) pass their
  /// own [key] instead.
  new(this.label, this.value, {this.color, this.detail, Key? key})
    : super(key: key ?? Key('row-$label'));

  /// What the value is.
  final String label;

  /// The value, already formatted.
  final String value;

  /// Status colour for the value, if any.
  final Color? color;

  /// A secondary note after the value.
  final String? detail;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(label, style: TextStyle(color: muted)),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              value,
              key: const Key('value'),
              textAlign: TextAlign.end,
              style: TextStyle(color: value == kUnknown ? muted : color),
            ),
          ),
          if (detail case final String d) ...[
            const SizedBox(width: AppSpacing.sm),
            Text(d, style: TextStyle(color: muted)),
          ],
        ],
      ),
    );
  }
}

/// Muted secondary text.
class Muted extends StatelessWidget {
  /// Creates muted [text].
  const new(this.text, {super.key});

  /// The text.
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
    child: Text(
      text,
      style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
    ),
  );
}

/// Plain body text with the row rhythm.
class Line extends StatelessWidget {
  /// Creates a line of [text], optionally in [color] and bold.
  const new(this.text, {this.color, this.strong = false, super.key});

  /// The text.
  final String text;

  /// Status colour, if any.
  final Color? color;

  /// Headline weight and size.
  final bool strong;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
    child: Text(
      text,
      style: strong
          ? Theme.of(context).textTheme.titleMedium
                ?.copyWith(color: color, fontWeight: FontWeight.w600)
          : TextStyle(color: color),
    ),
  );
}

/// The words for an empty list: known to be empty, unlike null.
const kNoneRecorded = 'None recorded';

/// Rows for a list that may be unknown (null) or empty.
List<Widget> listRows<T>(List<T>? items, Widget Function(T) row) {
  if (items == null) return const [Muted(kUnknown)];
  if (items.isEmpty) return const [Muted(kNoneRecorded)];
  return [for (final item in items) row(item)];
}

/// The theme's status colours.
AppStatusColors statusColors(BuildContext context) =>
    Theme.of(context).extension<AppStatusColors>()!;
