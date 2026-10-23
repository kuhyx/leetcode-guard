/// The Status and Coach tabs.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/projection_section.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/status_sections.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

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

/// The coach's session logs: requirements before code, hint rungs,
/// re-tests due and cluster progress.
class CoachTab extends StatelessWidget {
  /// Creates the tab over [coach] (null: unknown).
  const new({required this.coach, super.key});

  /// The coach section, or null when unknown.
  final CoachData? coach;

  @override
  Widget build(BuildContext context) {
    final c = coach;
    return CardGrid(
      cards: c == null
          ? const [
              SectionCard.unknown(title: 'Problems'),
              SectionCard.unknown(title: 'Re-tests due'),
              SectionCard.unknown(title: 'Clusters'),
            ]
          : [
              SectionCard(
                title: 'Problems',
                children: listRows(c.problems, _ProblemTile.new),
              ),
              SectionCard(
                title: 'Re-tests due',
                children: listRows(
                  c.retestsDue,
                  (r) => InfoRow(
                    show(r.slug),
                    'due ${show(r.due)}',
                    key: ObjectKey(r),
                  ),
                ),
              ),
              SectionCard(
                title: 'Clusters',
                children: _clusterRows(c.clusters),
              ),
            ],
    );
  }

  static List<Widget> _clusterRows(Map<String, ClusterProgress?>? clusters) =>
      listRows(
        clusters?.entries.toList(),
        (e) => InfoRow(e.key, fraction(e.value?.done, e.value?.total)),
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
