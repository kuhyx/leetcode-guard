/// The Status tab.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/projection_section.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/status_sections.dart';

/// All nine sections of the old status window, in the order it read them.
class StatusTab extends StatelessWidget {
  /// Creates the tab over [snapshot] (null: nothing read yet).
  const new({required this.snapshot, required this.openUrl, super.key});

  /// The snapshot on screen.
  final Snapshot? snapshot;

  /// Opens a suggestion's URL.
  final UrlOpener openUrl;

  @override
  Widget build(BuildContext context) {
    final s = snapshot?.status;
    return CardGrid(
      listKey: const Key('status-list'),
      cards: [
        verdictSection(context, s),
        creditsSection(context, s),
        ProjectionSection(
          progress: snapshot?.progress,
          projections: snapshot?.projections,
          price: snapshot?.projectionPrice,
        ),
        solvesSection(s),
        daysSection(s),
        budgetsSection(context, s),
        integritySection(context, s),
        environmentSection(context, s),
        suggestionsSection(s, openUrl),
      ],
    );
  }
}
