/// The Coach tab.
///
/// Three states, and only the last one is "unknown":
///
/// * **no sessions yet** (an empty problem list): a known state. Shows how to
///   start, from the coach's own `how_to` block, then every cluster at zero;
/// * **sessions**: the per-problem history (the latest session's four grades
///   and the highest hint rung), the re-tests due with their command, and
///   cluster progress;
/// * **a null section**: the PC published nothing (or the coach failed), so
///   the word "unknown" and one line on why.
///
/// With a coach relay ([CoachTab.session]) every cluster problem and each
/// "Next" gets a Start that opens a guided session, and a "Guided session"
/// card leads. That writes coaching logs on the PC and never anything that
/// decides, credits or unlocks (spec decision 2).
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/coach_clusters.dart';
import 'package:leetcode_guard/src/ui/coach_history.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/coach_live_card.dart';
import 'package:leetcode_guard/src/ui/coach_visible.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Why the whole tab can be unknown, and what to check.
const kCoachWhy =
    "The PC hasn't published coach data; is the harvester running?";

/// The coach's session logs and, with a relay, the guided sessions.
class CoachTab extends StatelessWidget {
  /// Creates the tab over [coach] (null: unknown); [openUrl] opens a
  /// problem page; [session] adds the guided-session controls.
  const new({
    required this.coach,
    required this.openUrl,
    this.session,
    super.key,
  });

  /// The coach section, or null when unknown.
  final CoachData? coach;

  /// Opens a problem's URL.
  final UrlOpener openUrl;

  /// The guided session, or null where no relay is wired.
  final CoachSessionLink? session;

  @override
  Widget build(BuildContext context) {
    final link = session;
    if (link == null) return _grid();
    return CoachVisible(controller: link.controller, builder: (_) => _grid());
  }

  Widget _grid() {
    final link = session;
    final live = [if (link != null) LiveSessionCard(link)];
    return switch (coach) {
      null => CardGrid(
        cards: [
          ...live,
          const SectionCard(
            title: 'Coach',
            children: [Muted(kUnknown), Muted(kCoachWhy)],
          ),
        ],
      ),
      final CoachData c when c.problems?.isEmpty ?? false => CardGrid(
        cards: [
          ...live,
          HowToCard(c.howTo),
          ...clusterCards(c.clusters, openUrl, link),
        ],
        footer: _footer(c),
      ),
      final CoachData c => CardGrid(
        cards: [
          ...live,
          SectionCard(
            title: 'Problems',
            children: listRows(c.problems, ProblemHistoryTile.new),
          ),
          SectionCard(
            title: 'Re-tests due',
            children: listRows(c.retestsDue, _RetestRow.new),
          ),
          ...clusterCards(c.clusters, openUrl, link),
        ],
        footer: _footer(c),
      ),
    };
  }

  static List<Widget> _footer(CoachData c) => [
    if (c.howTo?.nextNote case final String note) Muted(note),
  ];
}

class _RetestRow extends StatelessWidget {
  const new(this.r);

  final Retest r;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      InfoRow(show(r.slug), 'due ${show(r.due)}', key: ObjectKey(r)),
      if (r.command case final String command)
        SelectableText(command, style: monoStyle(context)),
    ],
  );
}
