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

import 'package:design_system/design_system.dart';
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
    final live = [if (link != null) liveSessionCard(link)];
    return switch (coach) {
      // Unknown: the mark and a sync-trouble glyph (the why is spoken).
      null => CardGrid(
        cards: [
          ...live,
          const SectionCard(
            title: kCoachTitle,
            leading: _unknownIcon,
            children: [
              Muted(kUnknown),
              Icon(Icons.sync_problem, semanticLabel: kCoachWhy),
            ],
          ),
        ],
      ),
      final CoachData c when c.problems?.isEmpty ?? false => CardGrid(
        cards: [
          ...live,
          howToCard(c.howTo),
          ...clusterCards(c.clusters, openUrl, link),
        ],
        footer: _footer(c),
      ),
      final CoachData c => CardGrid(
        cards: [
          ...live,
          SectionCard(
            title: kProblemsTitle,
            leading: const Icon(Icons.history, semanticLabel: kProblemsTitle),
            children: listRows(c.problems, ProblemHistoryTile.new),
          ),
          SectionCard(
            title: kRetestsTitle,
            leading: const Icon(
              Icons.event_repeat,
              semanticLabel: kRetestsTitle,
            ),
            children: listRows(c.retestsDue, _RetestRow.new),
          ),
          ...clusterCards(c.clusters, openUrl, link),
        ],
        footer: _footer(c),
      ),
    };
  }

  // The coach's note on what `--cluster` serves is spoken only.
  static List<Widget> _footer(CoachData c) => [
    if (c.howTo?.nextNote case final String note)
      Semantics(label: note, child: const SizedBox.shrink()),
  ];
}

/// Spoken section titles (a [SectionCard] title is never painted).
const kCoachTitle = 'Coach';

/// See [kCoachTitle].
const kProblemsTitle = 'Problems';

/// See [kCoachTitle].
const kRetestsTitle = 'Re-tests due';

const _unknownIcon = Icon(Icons.school_outlined, semanticLabel: kCoachTitle);

/// A re-test: the slug, a calendar glyph and the due date (data), then the
/// command that runs it (code).
class _RetestRow extends StatelessWidget {
  const new(this.r);

  final Retest r;

  @override
  Widget build(BuildContext context) => Column(
    key: ObjectKey(r),
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Row(
        children: [
          Expanded(child: Line(show(r.slug))),
          const Icon(Icons.event, size: 18, semanticLabel: 'due'),
          const SizedBox(width: AppSpacing.xs),
          Text(show(r.due), key: const Key('due')),
        ],
      ),
      if (r.command case final String command)
        SelectableText(command, style: monoStyle(context)),
    ],
  );
}
