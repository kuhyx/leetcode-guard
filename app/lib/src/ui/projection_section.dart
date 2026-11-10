/// "Progress & projection": solved/total plus the projection for a date.
///
/// The date control only picks among the keys the exporter precomputed (next
/// 90 days plus 12 month-ends). Nothing is projected here: the rules live in
/// Python, and a Dart port would drift from them.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/difficulty_mark.dart';
import 'package:leetcode_guard/src/ui/more_sheet.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

// Spoken only (textgate): SectionCard speaks its title and paints _leading.
const _title = 'Progress & projection';
const _leading = Icon(Icons.insights, semanticLabel: _title);
const _noDates = 'No projection dates published';
const _price = 'Tue-Thu price in credits';

/// The section, with its own selected-date state.
class ProjectionSection extends StatefulWidget implements Titled, Iconic {
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
  String get cardTitle => _title;

  @override
  Widget get cardIcon => _leading;

  @override
  State<ProjectionSection> createState() => _ProjectionSectionState();
}

class _ProjectionSectionState extends State<ProjectionSection> {
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
      return const SectionCard.unknown(title: _title, leading: _leading);
    }
    return SectionCard(
      title: _title,
      leading: _leading,
      children: [
        ...pairRows([
          InfoRow(
            'Solved',
            fraction(progress?.solvedAll, progress?.totalAll),
            icon: Icons.check_circle_outline,
          ),
          if (progress != null)
            for (final level in kLevels)
              LevelRow(
                level,
                fraction(progress.solved?[level], progress.total?[level]),
              ),
        ]),
        if (projections == null)
          InfoRow('Projection', kUnknown, icon: Icons.trending_up)
        else if (projections.isEmpty)
          const Row(
            children: [
              Icon(Icons.event_busy, semanticLabel: _noDates),
              Muted(kNoneRecorded),
            ],
          )
        else ...[
          _dateControl(context),
          ...pairRows(_rows(projections[_selected]!)),
          showAllButton(
            context,
            label: '',
            icon: Icons.info_outline,
            title: _title,
            rows: [
              ..._detailRows(projections[_selected]!),
              if (widget.price case final int price)
                InfoRow(_price, '$price', icon: Icons.sell_outlined),
            ],
          ),
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
          icon: const Icon(Icons.chevron_left, semanticLabel: 'Earlier date'),
          onPressed: index > 0
              ? () => setState(() => _chosen = keys[index - 1])
              : null,
        ),
        Expanded(
          child: TextButton.icon(
            key: const Key('projection-date'),
            icon: const Icon(Icons.event, semanticLabel: 'Projection date'),
            label: Text(_selected),
            onPressed: date == null ? null : () => _pick(context, date, keys),
          ),
        ),
        IconButton(
          icon: const Icon(Icons.chevron_right, semanticLabel: 'Later date'),
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

  List<InfoRow> _rows(Projection p) => [
    InfoRow(
      'Projected solved',
      show(p.projectedTotal),
      icon: Icons.trending_up,
    ),
    for (final level in kLevels)
      LevelRow(
        level,
        show(p.projected?[level]),
        semanticLabel: 'Projected $level',
      ),
    InfoRow('Available now', show(p.available), icon: Icons.savings_outlined),
  ];

  // Labels are spoken only (InfoRow paints the icon).
  List<Widget> _detailRows(Projection p) => [
    InfoRow('First day counted', show(p.firstDay), icon: Icons.first_page),
    InfoRow('Gated days', show(p.gatedDays), icon: Icons.lock_outline),
    InfoRow('Free days', show(p.freeDays), icon: Icons.lock_open),
    InfoRow('Sick days', show(p.sickDays), icon: Icons.sick_outlined),
    InfoRow('Base cost', show(p.baseCost), icon: Icons.toll_outlined),
    InfoRow('Debt', show(p.debt), icon: Icons.money_off),
    InfoRow('Required', show(p.required), icon: Icons.flag_outlined),
    InfoRow('Rules demand', show(p.rulesDemand), icon: Icons.gavel),
    InfoRow(
      'Debt left by rules',
      show(p.debtLeftByRules),
      icon: Icons.running_with_errors,
    ),
  ];
}
