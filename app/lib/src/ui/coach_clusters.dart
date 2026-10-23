/// The Coach tab's cluster cards: one per cluster, with progress, the next
/// problem and every problem as a link to its LeetCode page.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach.dart';
import 'package:leetcode_guard/src/problem_url.dart';
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
  UrlOpener openUrl,
) {
  if (clusters == null) return const [SectionCard.unknown(title: 'Clusters')];
  if (clusters.isEmpty) {
    return const [
      SectionCard(title: 'Clusters', children: [Muted(kNoneRecorded)]),
    ];
  }
  return [
    for (final e in _ordered(clusters)) _Cluster(e.key, e.value, openUrl),
  ];
}

class _Cluster extends StatelessWidget {
  const new(this.name, this.progress, this.openUrl);

  final String name;
  final ClusterProgress? progress;
  final UrlOpener openUrl;

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
    return SectionCard(
      title: name,
      children: [
        InfoRow('Solved', fraction(p?.solved, p?.total), key: Key('row-$name')),
        if (next != null) Muted('Next: $next'),
        for (final problem in p?.problems ?? const <ClusterProblem>[])
          _ClusterProblemTile(problem, openUrl),
      ],
    );
  }
}

class _ClusterProblemTile extends StatelessWidget {
  const new(this.problem, this.openUrl);

  final ClusterProblem problem;
  final UrlOpener openUrl;

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
    return InkWell(
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
  }
}
