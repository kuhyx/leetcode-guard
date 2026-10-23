/// "Progress & projection": solved/total plus the projection for a date.
///
/// The date control only picks among the keys the exporter precomputed (next
/// 90 days plus 12 month-ends). Nothing is projected here: the rules live in
/// Python, and a Dart port would drift from them.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The section, with its own selected-date state.
class ProjectionSection extends StatefulWidget {
  /// Creates the section over [progress] and [projections].
  const new({
    required this.progress,
    required this.projections,
    this.price,
    super.key,
  });

  /// Solved/total, or null when unknown.
  final Progress? progress;

  /// Precomputed projections by `YYYY-MM-DD`, or null when unknown.
  final Map<String, Projection>? projections;

  /// The Tue-Thu price the projections were computed at.
  final int? price;

  @override
  State<ProjectionSection> createState() => _ProjectionSectionState();
}

class _ProjectionSectionState extends State<ProjectionSection> {
  static const _title = 'Progress & projection';
  String? _chosen;

  List<String> get _keys => (widget.projections?.keys.toList() ?? [])..sort();

  /// The chosen key while it is still published, else the earliest.
  String get _selected {
    final keys = _keys;
    return keys.contains(_chosen) ? _chosen! : keys.first;
  }

  @override
  Widget build(BuildContext context) {
    final progress = widget.progress;
    final projections = widget.projections;
    if (progress == null && projections == null) {
      return const SectionCard.unknown(title: _title);
    }
    return SectionCard(
      title: _title,
      children: [
        InfoRow('Solved', fraction(progress?.solvedAll, progress?.totalAll)),
        if (progress != null)
          for (final level in kLevels)
            InfoRow(
              level,
              fraction(progress.solved?[level], progress.total?[level]),
            ),
        if (projections == null)
          InfoRow('Projection', kUnknown)
        else if (projections.isEmpty)
          const Muted('No projection dates published')
        else ...[
          _dateControl(context),
          ..._rows(projections[_selected]!),
          if (widget.price case final int price)
            Muted('Computed at a Tue-Thu price of $price credit(s)'),
        ],
      ],
    );
  }

  Widget _dateControl(BuildContext context) {
    final keys = _keys;
    final index = keys.indexOf(_selected);
    final date = DateTime.tryParse(_selected);
    return Row(
      children: [
        IconButton(
          tooltip: 'Earlier date',
          icon: const Icon(Icons.chevron_left),
          onPressed: index > 0
              ? () => setState(() => _chosen = keys[index - 1])
              : null,
        ),
        Expanded(
          child: TextButton.icon(
            key: const Key('projection-date'),
            icon: const Icon(Icons.event),
            label: Text(_selected),
            onPressed: date == null ? null : () => _pick(context, date, keys),
          ),
        ),
        IconButton(
          tooltip: 'Later date',
          icon: const Icon(Icons.chevron_right),
          onPressed: index < keys.length - 1
              ? () => setState(() => _chosen = keys[index + 1])
              : null,
        ),
      ],
    );
  }

  Future<void> _pick(
    BuildContext context,
    DateTime current,
    List<String> keys,
  ) async {
    final dates = [for (final k in keys) ?DateTime.tryParse(k)];
    final picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: dates.first,
      lastDate: dates.last,
      selectableDayPredicate: (day) => keys.contains(isoDate(day)),
    );
    if (picked != null) setState(() => _chosen = isoDate(picked));
  }

  List<Widget> _rows(Projection p) => [
    InfoRow('Projected solved', show(p.projectedTotal)),
    for (final level in kLevels)
      InfoRow('Projected $level', show(p.projected?[level])),
    InfoRow('First day counted', show(p.firstDay)),
    InfoRow('Gated days', show(p.gatedDays)),
    InfoRow('Free days', show(p.freeDays)),
    InfoRow('Sick days', show(p.sickDays)),
    InfoRow('Base cost', show(p.baseCost)),
    InfoRow('Debt', show(p.debt)),
    InfoRow('Available now', show(p.available)),
    InfoRow('Required', show(p.required)),
    InfoRow('Rules demand', show(p.rulesDemand)),
    InfoRow('Debt left by rules', show(p.debtLeftByRules)),
  ];
}
