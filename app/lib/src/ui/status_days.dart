/// The ledger-history sections of the Status tab: solves, settled days and
/// the escape budgets. Icons and numbers only (textgate); the words they
/// replaced are spoken.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/more_sheet.dart';
import 'package:leetcode_guard/src/ui/status_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The spoken name of the full list of recent solves.
const _recentSolves = 'Recent solves';

/// "Solves": what you actually solved.
Widget solvesSection(BuildContext context, StatusData? s) {
  const title = 'Solves';
  final leading = sectionIcon(Icons.task_alt, title);
  final solves = s?.solves;
  if (solves == null) {
    return SectionCard.unknown(title: title, leading: leading);
  }
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      ...iconPairs([
        InfoRow('Today', show(solves.today), icon: Icons.today),
        InfoRow('Last 7 days', show(solves.last7Days), icon: Icons.date_range),
        InfoRow(
          'Total credited',
          show(solves.totalCredited),
          icon: Icons.functions,
        ),
      ]),
      ...limitedRows(context, solves.recent, 3, (solve) {
        // The slug and the language are LeetCode's own words: content.
        final lang = solve.lang == null ? '' : ' [${solve.lang}]';
        return DatedRow(
          show(solve.day),
          '${show(solve.titleSlug)}$lang',
          key: ObjectKey(solve),
        );
        // Never painted: showAllButton speaks it and keys the sheet with it.
      }, title: _recentSolves),
    ],
  );
}

/// "Days settled": which days were charged, and since when.
Widget daysSection(StatusData? s) {
  const title = 'Days settled';
  final leading = sectionIcon(Icons.event_available, title);
  final days = s?.days;
  if (days == null) return SectionCard.unknown(title: title, leading: leading);
  final charged = days.charged;
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      InfoRow(
        'Gate in force from ${show(days.startDate)}',
        '${show(days.gateInForce)} ${show(days.startDate)}',
        icon: Icons.play_circle_outline,
        key: const Key('row-Gate in force'),
      ),
      InfoRow('Days charged', show(charged?.length), icon: Icons.paid),
      if (charged == null)
        const Muted(kUnknown)
      else if (charged.isEmpty)
        const Muted(kNoneRecorded)
      else
        Muted(charged.join(', ')),
    ],
  );
}

/// "Escape budgets": the escape hatch and network-incident allowances.
Widget budgetsSection(BuildContext context, StatusData? s) {
  const title = 'Escape budgets';
  final leading = sectionIcon(Icons.emergency_share, title);
  final budgets = s?.budgets;
  if (budgets == null) {
    return SectionCard.unknown(title: title, leading: leading);
  }
  final danger = Theme.of(context).colorScheme.error;
  return SectionCard(
    title: title,
    leading: leading,
    children: [
      if (budgets.isEmpty) const Muted(kNoneRecorded),
      for (final MapEntry(:key, :value) in budgets.entries)
        _budgetLine(key, value, danger),
    ],
  );
}

/// The icon of each budget Python publishes; any other is a generic one.
IconData budgetIcon(String name) => switch (name) {
  'escape' => Icons.directions_run,
  'incidents' => Icons.wifi_off,
  _ => Icons.savings_outlined,
};

/// The rolling windows Python counts a budget over, in days.
const _windows = [7, 30, 90];

/// `used / limit (7d)` for each window the budget publishes; without any,
/// its other counters as plain numbers.
String budgetCounts(Budget b) {
  final windows = [
    for (final w in _windows)
      if (b.extra.containsKey('used_$w') || b.extra.containsKey('limit_$w'))
        '${show(b.extra['used_$w'])} / ${show(b.extra['limit_$w'])} (${w}d)',
  ];
  if (windows.isNotEmpty) return windows.join('   ');
  return [for (final v in b.extra.values) show(v)].join(' · ');
}

Widget _budgetLine(String name, Budget? b, Color danger) {
  if (b == null) {
    return GlyphLine(
      budgetIcon(name),
      kUnknown,
      spoken: '$name: $kUnknown',
      key: Key('budget-$name'),
    );
  }
  final wait = b.nextWaitSeconds;
  final exhausted = b.exhausted ?? false;
  final spoken = [
    b.summary ?? b.label ?? name,
    if (wait != null) 'next use waits ${wait ~/ 60} min',
    if (exhausted) 'EXHAUSTED',
    if (b.summary == null)
      for (final MapEntry(:key, :value) in b.extra.entries)
        '$key: ${show(value)}',
  ].join(', ');
  return GlyphLine(
    budgetIcon(name),
    budgetCounts(b),
    spoken: spoken,
    color: exhausted ? danger : null,
    key: Key('budget-$name'),
    glyphs: [
      if (wait != null) ...[
        const Icon(Icons.hourglass_bottom, size: 20),
        Text('${wait ~/ 60}m'),
      ],
      if (exhausted)
        Icon(Icons.block, color: danger, key: const Key('exhausted')),
    ],
  );
}
