/// The Coach tab's cluster cards: one per cluster, with progress, the next
/// problem and every problem as a link to its LeetCode page; with a coach
/// relay, each problem and the next one also get a Start.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/problem_url.dart';
import 'package:leetcode_guard/src/ui/coach_live_card.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Curriculum order; clusters without one sort after, by name.
List<MapEntry<String, ClusterProgress?>> _ordered(
  Map<String, ClusterProgress?> clusters,
) => clusters.entries.toList()
  ..sort((a, b) {
    final byOrder = (a.value?.order ?? 1 << 30).compareTo(
      b.value?.order ?? 1 << 30,
    );
    return byOrder != 0 ? byOrder : a.key.compareTo(b.key);
  });

/// One card per cluster (so the grid balances them across columns), each
/// with its problems as links; or one card saying why there are none.
List<Widget> clusterCards(
  Map<String, ClusterProgress?>? clusters,
  UrlOpener openUrl, [
  CoachSessionLink? link,
]) {
  if (clusters == null) return const [SectionCard.unknown(title: 'Clusters')];
  if (clusters.isEmpty) {
    return const [
      SectionCard(title: 'Clusters', children: [Muted(kNoneRecorded)]),
    ];
  }
  return [
    for (final e in _ordered(clusters)) _Cluster(e.key, e.value, openUrl, link),
  ];
}

class _Cluster extends StatelessWidget {
  const new(this.name, this.progress, this.openUrl, this.link);

  final String name;
  final ClusterProgress? progress;
  final UrlOpener openUrl;
  final CoachSessionLink? link;

  /// The title of the problem the coach would serve next.
  String? get _next {
    final slug = progress?.next;
    if (slug == null) return null;
    for (final p in progress?.problems ?? const <ClusterProblem>[]) {
      if (p.slug == slug) return p.title ?? slug;
    }
    return slug;
  }

  @override
  Widget build(BuildContext context) {
    final p = progress;
    final next = _next;
    final nextSlug = p?.next;
    final link = this.link;
    return SectionCard(
      title: name,
      children: [
        InfoRow('Solved', fraction(p?.solved, p?.total), key: Key('row-$name')),
        if (next != null)
          Row(
            children: [
              Expanded(child: Muted('Next: $next')),
              if (link != null && nextSlug != null)
                StartButton(link, nextSlug, keyName: 'start-next-$name'),
            ],
          ),
        for (final problem in p?.problems ?? const <ClusterProblem>[])
          _ClusterProblemTile(problem, openUrl, link),
      ],
    );
  }
}

class _ClusterProblemTile extends StatelessWidget {
  const new(this.problem, this.openUrl, this.link);

  final ClusterProblem problem;
  final UrlOpener openUrl;
  final CoachSessionLink? link;

  /// Only a LeetCode problem page opens: the desktop wrapper refuses
  /// anything else, and the URL arrives over the network.
  Uri? get _target {
    final url = problem.url;
    return url != null && isProblemUrl(url) ? Uri.parse(url) : null;
  }

  @override
  Widget build(BuildContext context) {
    final target = _target;
    final scheme = Theme.of(context).colorScheme;
    final link = this.link;
    final slug = problem.slug;
    final tile = InkWell(
      key: Key('problem-${problem.slug}'),
      borderRadius: BorderRadius.circular(AppRadius.sm),
      onTap: target == null ? null : () => openUrl(target),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          children: [
            Expanded(
              child: Text(
                problem.title ?? show(problem.slug),
                style: TextStyle(color: target == null ? null : scheme.primary),
              ),
            ),
            if (problem.number case final int number)
              Text(
                '#$number',
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
            if (target != null) ...[
              const SizedBox(width: AppSpacing.sm),
              Icon(Icons.open_in_new, size: 20, color: scheme.onSurfaceVariant),
            ],
          ],
        ),
      ),
    );
    if (link == null || slug == null) return tile;
    return Row(
      children: [
        Expanded(child: tile),
        const SizedBox(width: AppSpacing.sm),
        StartButton(link, slug),
      ],
    );
  }
}
