/// The phone layout of a tab: section chips and ONE section on screen.
///
/// A phone shows a tab's sections one at a time, chosen from a row of chips,
/// so no tab needs vertical scrolling at the phone's own height. Anything a
/// section has too many of (a growing list) sits behind a tap in the section
/// itself; nothing is dropped.
library;

import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Key of the area holding the selected section.
const kTabContentKey = Key('tab-content');

/// One section per chip. [cards] must not be empty; titled [footer] entries
/// become chips after them, the rest stays under the section.
class CardPages extends StatefulWidget {
  /// Creates the pages; [header] sits above the chips.
  const new({
    required this.cards,
    required this.header,
    required this.footer,
    this.listKey,
    super.key,
  });

  /// The sections, in reading order.
  final List<Widget> cards;

  /// Fixed rows above the chips.
  final List<Widget> header;

  /// Sections (titled) and notes (untitled) after the cards.
  final List<Widget> footer;

  /// Key of the selected section's scrollable, for tests that find it.
  final Key? listKey;

  @override
  State<CardPages> createState() => _CardPagesState();
}

class _CardPagesState extends State<CardPages> {
  var _selected = 0;

  @override
  Widget build(BuildContext context) {
    final pages = [
      ...widget.cards,
      for (final f in widget.footer)
        if (f is Titled) f,
    ];
    // The list can shrink between snapshots; stay on a section that exists.
    final index = math.min(_selected, pages.length - 1);
    return Padding(
      padding: kGutter,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ...widget.header,
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final (i, page) in pages.indexed) ...[
                  if (i > 0) const SizedBox(width: AppSpacing.sm),
                  ChoiceChip(
                    // A text-free section names its chip with its icon.
                    // Anything without an icon falls back to its number.
                    label: switch (page) {
                      SectionCard(:final leading?) => leading,
                      Iconic(:final cardIcon) => cardIcon,
                      _ => Text('${i + 1}'),
                    },
                    selected: i == index,
                    onSelected: (_) => setState(() => _selected = i),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Expanded(
            child: KeyedSubtree(
              key: kTabContentKey,
              child: SingleChildScrollView(
                key: widget.listKey,
                child: KeyedSubtree(key: ValueKey(index), child: pages[index]),
              ),
            ),
          ),
          for (final f in widget.footer)
            if (f is! Titled) f,
        ],
      ),
    );
  }
}

/// The chip label of [page], the [position]th section.
String pageTitle(Object page, int position) =>
    page is Titled ? page.cardTitle : 'Section ${position + 1}';
