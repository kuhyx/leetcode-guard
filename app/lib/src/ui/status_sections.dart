/// The gate sections of the Status tab: verdict, credits, solves, days,
/// budgets. The diagnostic ones live in `status_health.dart`.
///
/// Colour is load-bearing, as in the tkinter window it replaces: red means
/// the gate is holding you, amber needs attention, green is clear. Every
/// sentence of rules (pricing, "why it did not trigger") is Python's own
/// text from the snapshot: nothing here re-derives a rule.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// "Right now": am I locked, and why.
Widget verdictSection(BuildContext context, StatusData? s) {
  const title = 'Right now';
  if (s == null) return const SectionCard.unknown(title: title);
  final colors = statusColors(context);
  final danger = Theme.of(context).colorScheme.error;
  final (headline, color) = switch (s.locked) {
    true => ('LOCKED: solve ${show(s.needed)} more', danger),
    false => (
      'Unlocked (${show(s.state)})',
      (s.available ?? 0) > 0 ? colors.success : colors.warning,
    ),
    null => ('Lock state $kUnknown', null),
  };
  final explanation = s.explanation;
  return SectionCard(
    title: title,
    children: [
      Line(headline, color: color, strong: true),
      Line(
        '${show(s.day)} (${show(s.weekday)}), costs ${show(s.cost)} credit(s)',
      ),
      Muted(s.reason ?? 'Reason $kUnknown'),
      InfoRow('Surcharge', show(s.surcharge)),
      InfoRow('Paid today', show(s.chargedToday)),
      if (explanation != null && explanation.isNotEmpty) ...[
        const Line('Why the lock did not trigger'),
        for (final (i, line) in explanation.indexed) Muted('${i + 1}. $line'),
      ],
    ],
  );
}

/// "Credits (tokens)": what you have, earned and spent.
Widget creditsSection(BuildContext context, StatusData? s) {
  const title = 'Credits (tokens)';
  if (s == null) return const SectionCard.unknown(title: title);
  final colors = statusColors(context);
  final debt = s.debt;
  return SectionCard(
    title: title,
    children: [
      Line(
        '${show(s.available)} available',
        color: (s.available ?? 0) > 0 ? colors.success : colors.warning,
        strong: true,
      ),
      InfoRow('Earned all-time', show(s.earnedAllTime)),
      InfoRow('Spent all-time', show(s.spentAllTime)),
      InfoRow('Needed today', show(s.needed)),
      if (debt == null)
        InfoRow('Debt', kUnknown)
      else ...[
        InfoRow(
          'Debt outstanding',
          show(debt.outstanding),
          color: (debt.outstanding ?? 0) > 0 ? colors.warning : null,
        ),
        InfoRow('Debt owed', show(debt.owed)),
        InfoRow('Debt repaid', show(debt.repaid)),
        InfoRow('Missed days', show(debt.missedDays)),
      ],
      if (s.pricingNote case final String note) Muted(note),
    ],
  );
}

/// "Solves": what you actually solved.
Widget solvesSection(StatusData? s) {
  const title = 'Solves';
  final solves = s?.solves;
  if (solves == null) return const SectionCard.unknown(title: title);
  return SectionCard(
    title: title,
    children: [
      InfoRow('Today', show(solves.today)),
      InfoRow('Last 7 days', show(solves.last7Days)),
      InfoRow('Total credited', show(solves.totalCredited)),
      ...listRows(solves.recent, (solve) {
        final lang = solve.lang == null ? '' : ' [${solve.lang}]';
        return InfoRow(
          show(solve.day),
          '${show(solve.titleSlug)}$lang',
          key: ObjectKey(solve),
        );
      }),
    ],
  );
}

/// "Days settled": which days were charged, and since when.
Widget daysSection(StatusData? s) {
  const title = 'Days settled';
  final days = s?.days;
  if (days == null) return const SectionCard.unknown(title: title);
  final charged = days.charged;
  return SectionCard(
    title: title,
    children: [
      InfoRow(
        'Gate in force from ${show(days.startDate)}',
        show(days.gateInForce),
      ),
      InfoRow('Days charged', show(charged?.length)),
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
  final budgets = s?.budgets;
  if (budgets == null) return const SectionCard.unknown(title: title);
  final danger = Theme.of(context).colorScheme.error;
  return SectionCard(
    title: title,
    children: [
      if (budgets.isEmpty) const Muted(kNoneRecorded),
      for (final MapEntry(:key, :value) in budgets.entries)
        ..._budgetRows(key, value, danger),
    ],
  );
}

List<Widget> _budgetRows(String name, Budget? b, Color danger) {
  if (b == null) return [Muted('$name: $kUnknown')];
  final wait = b.nextWaitSeconds;
  final summary = b.summary;
  return [
    Line(
      summary ?? b.label ?? name,
      color: b.exhausted ?? false ? danger : null,
    ),
    if (wait != null || (b.exhausted ?? false))
      Muted(
        [
          if (wait != null) 'next use waits ${wait ~/ 60} min',
          if (b.exhausted ?? false) 'EXHAUSTED',
        ].join(', '),
      ),
    // Python's summary already words the counters; without it, show them.
    if (summary == null)
      for (final MapEntry(:key, :value) in b.extra.entries)
        Muted('$key: ${show(value)}'),
  ];
}
