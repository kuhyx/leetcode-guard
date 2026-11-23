/// The Post-mortem tab: what the tutor learned from each finished unit.
///
/// No words before a tap (textgate): a bar per unit (post-theory one-shot
/// rate), the selected unit's problem grid and its card-change chips. A tap
/// on a bar, row or chip reveals content: the unit, the problem's finding,
/// the card's front and finding. Display-only, read from the snapshot on
/// the phone and on the desktop alike (DOCS-postmortem.md).
library;

import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:leetcode_guard/src/model/postmortem.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/postmortem_chart.dart';
import 'package:leetcode_guard/src/ui/postmortem_chips.dart';
import 'package:leetcode_guard/src/ui/postmortem_grid.dart';
import 'package:leetcode_guard/src/ui/postmortem_reveal.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';
import 'package:material_ui/material_ui.dart';

// Section titles: spoken only (SectionCard paints the icon).
const _chart = 'One-shot rate after the theory';
const _grid = 'Problems';
const _cards = 'Card changes';

const _chartIcon = Icon(
  Icons.bar_chart,
  semanticLabel: _chart,
  key: Key('pm-section-chart'),
);
const _gridIcon = Icon(
  Icons.grid_on,
  semanticLabel: _grid,
  key: Key('pm-section-grid'),
);
const _cardsIcon = Icon(
  Icons.style_outlined,
  semanticLabel: _cards,
  key: Key('pm-section-cards'),
);

/// The tab over the snapshot's `postmortems`.
class PostmortemTab extends StatefulWidget {
  /// Creates the tab; null [units] is unknown, empty is "none yet".
  const new({required this.units, super.key});

  /// Every unit, oldest first.
  final List<PostmortemUnit>? units;

  @override
  State<PostmortemTab> createState() => _PostmortemTabState();
}

class _PostmortemTabState extends State<PostmortemTab> {
  /// The tapped bar; null shows the newest unit, unnamed.
  int? _unit;
  int? _problem;
  int? _card;

  void _selectUnit(int i) => setState(() {
    _unit = _unit == i ? null : i;
    _problem = _card = null;
  });

  void _toggleProblem(int i) =>
      setState(() => _problem = _problem == i ? null : i);

  void _toggleCard(int i) => setState(() => _card = _card == i ? null : i);

  @override
  Widget build(BuildContext context) {
    final units = widget.units;
    if (units == null) {
      return const CardGrid(
        cards: [
          SectionCard.unknown(title: _chart, leading: _chartIcon),
          SectionCard.unknown(title: _grid, leading: _gridIcon),
          SectionCard.unknown(title: _cards, leading: _cardsIcon),
        ],
      );
    }
    if (units.isEmpty) return const _NoneYet();
    final tapped = _unit;
    final index = math.min(tapped ?? units.length - 1, units.length - 1);
    final unit = units[index];
    return CardGrid(
      listKey: const Key('postmortem-list'),
      cards: [
        SectionCard(
          title: _chart,
          leading: _chartIcon,
          children: [
            OneShotBars(units: units, selected: index, onTap: _selectUnit),
            if (tapped != null)
              Reveal(key: const Key('pm-reveal-unit'), title: unit.unit),
          ],
        ),
        SectionCard(
          title: _grid,
          leading: _gridIcon,
          children: problemGrid(
            context,
            unit.problems,
            selected: _problem,
            onTap: _toggleProblem,
          ),
        ),
        SectionCard(
          title: _cards,
          leading: _cardsIcon,
          children: cardChips(unit.cards, selected: _card, onTap: _toggleCard),
        ),
      ],
    );
  }
}

/// No post-mortem yet: the tab's glyph, large and muted, and no sentence.
class _NoneYet extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) => Center(
    child: Icon(
      Icons.fact_check_outlined,
      key: const Key('pm-empty'),
      size: AppSpacing.xxl,
      color: Theme.of(context).colorScheme.onSurfaceVariant,
      semanticLabel: 'No post-mortem yet',
    ),
  );
}
