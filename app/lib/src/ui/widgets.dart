/// The few building blocks every tab is made of.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';

/// Outer gutter of every tab.
const kGutter = EdgeInsets.all(AppSpacing.md);

/// A section that names itself, so the phone layout can label its chip.
abstract interface class Titled {
  /// The chip label.
  String get cardTitle;
}

/// A section that names its chip with an icon (textgate: chips carry no
/// words). [SectionCard] gets this from its `leading`; other sections
/// implement it directly.
abstract interface class Iconic {
  /// The chip's icon.
  Widget get cardIcon;
}

/// One titled group of rows on a raised surface. No shadow: this is a dark
/// UI, where depth comes from the lighter surface alone.
class SectionCard extends StatelessWidget implements Titled {
  /// Creates a section titled [title] holding [children].
  const new({
    required this.title,
    required this.children,
    this.leading,
    super.key,
  });

  /// A section whose data is unknown: the title and the word, nothing else.
  const new unknown({required this.title, this.leading, super.key})
    : children = const [Muted(kUnknown)];

  /// The heading.
  final String title;

  /// Optional leading icon for text-free headers.
  final Widget? leading;

  @override
  String get cardTitle => title;

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
          // The title is spoken only (textgate): the header paints the icon.
          Semantics(
            header: true,
            label: title,
            child: ExcludeSemantics(child: Row(children: [?leading])),
          ),
          const SizedBox(height: AppSpacing.sm),
          ...children,
        ],
      ),
    );
  }
}

/// An icon on the left, its value on the right. An unknown value is muted
/// so it never reads as a measured number.
///
/// No words (textgate): [label] is spoken only (the icon's semantic label);
/// what is painted is [icon]. Every caller passes an icon that says what the
/// value is; the fallback dot exists only so a forgotten one is visible.
class InfoRow extends StatelessWidget {
  /// Creates a row; the key `row-<label>` lets tests find its value. Rows
  /// in a list whose labels can repeat (two solves on one day) pass their
  /// own [key] instead.
  new(this.label, this.value, {this.icon, this.color, Key? key})
    : super(key: key ?? Key('row-$label'));

  /// What the value is, for screen readers and tests. Never painted.
  final String label;

  /// What the value is, painted.
  final IconData? icon;

  /// The value, already formatted.
  final String value;

  /// Status colour for the value, if any.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Fixed width, not Expanded: a label used to need half the row,
          // an icon does not, and the value (an ISO date) wrapped without it.
          Icon(
            icon ?? Icons.circle_outlined,
            color: muted,
            size: AppSpacing.lg,
            semanticLabel: label,
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

/// An empty list, known to be empty (unlike null, which is [kUnknown]).
const kNoneRecorded = '∅';

/// Rows for a list that may be unknown (null) or empty.
List<Widget> listRows<T>(List<T>? items, Widget Function(T) row) {
  if (items == null) return const [Muted(kUnknown)];
  if (items.isEmpty) return const [Muted(kNoneRecorded)];
  return [for (final item in items) row(item)];
}

/// The theme's status colours.
AppStatusColors statusColors(BuildContext context) =>
    Theme.of(context).extension<AppStatusColors>()!;
