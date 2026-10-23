/// The Coach tab.
///
/// Three states, and only the last one is "unknown":
///
/// * **no sessions yet** (an empty problem list): a known state. Shows how to
///   start, from the coach's own `how_to` block, then every cluster at zero;
/// * **sessions**: the per-problem rows, the re-tests due with their command,
///   and cluster progress;
/// * **a null section**: the PC published nothing (or the coach failed), so
///   the word "unknown" and one line on why.
///
/// Read-only. The only controls are the copy button and problem links.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/coach_clusters.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Why the whole tab can be unknown, and what to check.
const kCoachWhy =
    "The PC hasn't published coach data; is the harvester running?";

/// The coach's session logs: requirements before code, hint rungs,
/// re-tests due and cluster progress, or how to start when there are none.
class CoachTab extends StatelessWidget {
  /// Creates the tab over [coach] (null: unknown); [openUrl] opens a
  /// problem page.
  const new({required this.coach, required this.openUrl, super.key});

  /// The coach section, or null when unknown.
  final CoachData? coach;

  /// Opens a problem's URL.
  final UrlOpener openUrl;

  @override
  Widget build(BuildContext context) => switch (coach) {
    null => const CardGrid(
      cards: [
        SectionCard(
          title: 'Coach',
          children: [Muted(kUnknown), Muted(kCoachWhy)],
        ),
      ],
    ),
    final CoachData c when c.problems?.isEmpty ?? false => CardGrid(
      cards: [HowToCard(c.howTo), ...clusterCards(c.clusters, openUrl)],
      footer: _footer(c),
    ),
    final CoachData c => CardGrid(
      cards: [
        SectionCard(
          title: 'Problems',
          children: listRows(c.problems, _ProblemTile.new),
        ),
        SectionCard(
          title: 'Re-tests due',
          children: listRows(c.retestsDue, _RetestRow.new),
        ),
        ...clusterCards(c.clusters, openUrl),
      ],
      footer: _footer(c),
    ),
  };

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

class _ProblemTile extends StatelessWidget {
  const new(this.p);

  final CoachProblem p;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Line(show(p.slug), strong: true),
      Muted('${show(p.cluster)}, ${show(p.day)}'),
      Line('Requirements before code: ${show(p.reqBeforeCode)}'),
      Line(
        'Hint rung: ${show(p.maxRung)}'
        '${p.revealed ?? false ? ', revealed' : ''}',
      ),
      Line('Requirements check: ${show(p.reqCheck)}'),
      // Separates one problem from the next inside the shared card.
      const SizedBox(height: AppSpacing.sm),
    ],
  );
}
