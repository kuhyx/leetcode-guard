/// The tabs' card layout: one list on a phone, columns on a wide window.
///
/// The desktop app is a Chrome window on a 4K screen; one 720 px column
/// there left two thirds of the window empty. Below [kGridBreakpoint] the
/// layout is exactly the phone's list, so the primary platform never moves.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// A column never stretches wider than this, so a wide window keeps a
/// readable line length inside each card.
const kMaxContentWidth = 720.0;

/// Window width (logical px) from which cards go side by side.
const kGridBreakpoint = 1200.0;

/// Window width from which there are three columns.
const kThreeColumnBreakpoint = 1800.0;

/// Card columns for a window [width] logical pixels wide.
int gridColumns(double width) => width >= kThreeColumnBreakpoint
    ? 3
    : width >= kGridBreakpoint
    ? 2
    : 1;

/// The widest the tab content gets with [columns] columns: one column is
/// the old 720 px cap, each further one adds a column and the gap before it.
double contentMaxWidth(int columns) =>
    columns * kMaxContentWidth + (columns - 1) * AppSpacing.md;

/// A tab's cards: a list in one column, else [gridColumns] columns filled in
/// reading order (card `i` goes to column `i % n`, of n columns).
class CardGrid extends StatelessWidget {
  /// Creates the layout; [header] and [footer] always span the full width.
  const new({
    required this.cards,
    this.header = const [],
    this.footer = const [],
    this.listKey,
    super.key,
  });

  /// The cards, in reading order.
  final List<Widget> cards;

  /// Full-width rows above the cards.
  final List<Widget> header;

  /// Full-width rows below the cards.
  final List<Widget> footer;

  /// Key of the scrollable, for tests that find it.
  final Key? listKey;

  @override
  Widget build(BuildContext context) {
    final columns = gridColumns(MediaQuery.sizeOf(context).width);
    return ListView(
      key: listKey,
      padding: kGutter,
      children: [
        ...header,
        if (columns == 1)
          ...cards
        else
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var c = 0; c < columns; c++) ...[
                if (c > 0) const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      for (var i = c; i < cards.length; i += columns) cards[i],
                    ],
                  ),
                ),
              ],
            ],
          ),
        ...footer,
      ],
    );
  }
}
