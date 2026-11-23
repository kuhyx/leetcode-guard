/// The selected unit's card changes as chips: new, edited, suspended and
/// kept, each its own glyph (and one-word tooltip). A tapped chip reveals
/// the card's front and the finding; a kept chip also lists the one-shot
/// solves that used its idea.
library;

import 'package:design_system/design_system.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/postmortem.dart';
import 'package:leetcode_guard/src/ui/postmortem_reveal.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';
import 'package:material_ui/material_ui.dart';

/// Each change's glyph and its tooltip word.
const Map<CardChange, (IconData, String)> kChangeGlyphs = {
  CardChange.added: (Icons.add_circle_outline, 'New'),
  CardChange.edited: (Icons.edit_outlined, 'Edited'),
  CardChange.suspended: (Icons.pause_circle_outline, 'Suspended'),
  CardChange.kept: (Icons.push_pin_outlined, 'Kept'),
};

/// The chips for [cards]; [selected] is the revealed chip.
List<Widget> cardChips(
  List<PostmortemCard>? cards, {
  required int? selected,
  required ValueChanged<int> onTap,
}) {
  if (cards == null) return const [Muted(kUnknown)];
  if (cards.isEmpty) return const [Muted(kNoneRecorded)];
  final picked = selected == null ? null : cards[selected];
  return [
    Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final (i, card) in cards.indexed)
          ChoiceChip(
            key: Key('pm-card-$i'),
            tooltip: kChangeGlyphs[card.change]!.$2,
            showCheckmark: false,
            label: Icon(
              kChangeGlyphs[card.change]!.$1,
              size: AppSpacing.md + 2,
              semanticLabel: kChangeGlyphs[card.change]!.$2,
            ),
            selected: i == selected,
            onSelected: (_) => onTap(i),
          ),
      ],
    ),
    if (picked != null)
      Reveal(
        key: const Key('pm-reveal-card'),
        title: picked.front,
        body: picked.finding,
        solves: picked.usedBy,
      ),
  ];
}
