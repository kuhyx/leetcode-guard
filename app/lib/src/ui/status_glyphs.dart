/// The text-free pieces the Status tab is drawn from (textgate, 2026-11-08):
/// a section's icon, an icon-plus-number line, rows two to a line, and a
/// sentence from Python reduced to its icon and its dates and numbers.
///
/// Every piece keeps the words it replaced as its spoken label, so a screen
/// reader and the tests still hear "LOCKED: solve 2 more".
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The header icon of the section titled [title]: painted in the card's
/// header and as the phone layout's chip, spoken as [title]. Keyed
/// `section-<slug>` ("Credits (tokens)" is `section-credits-tokens`).
Icon sectionIcon(IconData icon, String title) {
  final words = RegExp('[a-z]+').allMatches(title.toLowerCase());
  return Icon(
    icon,
    semanticLabel: title,
    key: Key('section-${words.map((m) => m[0]).join('-')}'),
  );
}

/// An icon and a value on one line, spoken as [spoken] alone.
class GlyphLine extends StatelessWidget {
  /// Creates the line; [glyphs] follow the value (marks such as "exhausted").
  const new(
    this.icon,
    this.value, {
    required this.spoken,
    this.color,
    this.strong = false,
    this.glyphs = const [],
    super.key,
  });

  /// What the value is.
  final IconData icon;

  /// The value: a number, a date, [kUnknown], or empty.
  final String value;

  /// The words this line replaced.
  final String spoken;

  /// Status colour of the icon and the value.
  final Color? color;

  /// Headline size.
  final bool strong;

  /// Further marks after the value.
  final List<Widget> glyphs;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final style = strong
        ? Theme.of(context).textTheme.titleMedium
              ?.copyWith(color: color, fontWeight: FontWeight.w600)
        : TextStyle(color: value == kUnknown ? muted : color);
    return Semantics(
      label: spoken,
      excludeSemantics: true,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: Wrap(
          spacing: AppSpacing.sm,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Icon(icon, color: color ?? muted, size: strong ? 28 : 20),
            if (value.isNotEmpty) Text(value, style: style),
            ...glyphs,
          ],
        ),
      ),
    );
  }
}

/// [rows] two to a line. `more_sheet.pairRows` paints each row's label as
/// text, so the Status tab pairs the rows itself and keeps them icon-only.
List<Widget> iconPairs(List<InfoRow> rows) => [
  for (var i = 0; i < rows.length; i += 2)
    Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: rows[i]),
        const SizedBox(width: AppSpacing.lg),
        Expanded(
          child: i + 1 < rows.length ? rows[i + 1] : const SizedBox.shrink(),
        ),
      ],
    ),
];

/// ISO dates (with an optional time) and numbers, in the order they occur.
final _facts = RegExp(
  r'\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?|\d+(?:\.\d+)?%?',
);

/// The dates and numbers inside [sentence], joined by a middle dot.
String factsOf(String sentence) =>
    _facts.allMatches(sentence).map((m) => m[0]).join(' · ');

/// A sentence Python wrote, painted as [icon] and its own dates and numbers
/// ([kUnknown] when the sentence is missing); the sentence is spoken.
Widget spokenNote(IconData icon, String? sentence, {String? unknownSpoken}) =>
    GlyphLine(
      icon,
      sentence == null ? kUnknown : factsOf(sentence),
      spoken: sentence ?? '${unknownSpoken ?? ''} $kUnknown'.trim(),
    );

/// A dated row: the ISO [date] muted on the left, [value] on the right.
class DatedRow extends StatelessWidget {
  /// Creates the row.
  const new(this.date, this.value, {super.key});

  /// `YYYY-MM-DD` or [kUnknown].
  final String date;

  /// What happened that day (content: a problem slug).
  final String value;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(Icons.check_circle_outline, size: 20, color: muted),
          const SizedBox(width: AppSpacing.sm),
          Text(date, style: TextStyle(color: muted)),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              value,
              key: const Key('value'),
              textAlign: TextAlign.end,
            ),
          ),
        ],
      ),
    );
  }
}
