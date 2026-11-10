/// What lets a section fit one phone screen without dropping anything: rows
/// in pairs, and the long tail behind a "Show all" tap.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/difficulty_mark.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// [rows] as two tiles to a line, the icon above its value: half the height
/// of the same rows one per line.
List<Widget> pairRows(List<InfoRow> rows) => [
  for (var i = 0; i < rows.length; i += 2)
    Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: _Tile(rows[i])),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: i + 1 < rows.length
              ? _Tile(rows[i + 1])
              : const SizedBox.shrink(),
        ),
      ],
    ),
];

class _Tile extends StatelessWidget {
  const new(this.row);

  final InfoRow row;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      key: row.key,
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // The label is spoken only (textgate); the row's icon is painted.
          if (row case final LevelRow level)
            DifficultyMark(level.level, semanticLabel: level.label)
          else
            Icon(
              row.icon ?? Icons.circle_outlined,
              color: muted,
              size: AppSpacing.lg,
              semanticLabel: row.label,
            ),
          Text(
            row.value,
            key: const Key('value'),
            style: TextStyle(color: row.value == kUnknown ? muted : row.color),
          ),
        ],
      ),
    );
  }
}

/// A button that opens [rows] in a bottom sheet for the section [title].
///
/// No words (textgate): it paints [icon] and [label], which is a count or
/// empty; [title] is spoken ("Show all <title>") and keys the button and
/// the sheet.
Widget showAllButton(
  BuildContext context, {
  required String label,
  required String title,
  required List<Widget> rows,
  IconData? icon,
}) => Align(
  alignment: Alignment.centerLeft,
  widthFactor: 1,
  child: TextButton(
    key: Key('show-all-$title'),
    onPressed: () => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => SafeArea(
        child: ListView(
          key: Key('sheet-$title'),
          padding: kGutter,
          shrinkWrap: true,
          children: rows,
        ),
      ),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon ?? Icons.expand_more, semanticLabel: 'Show all $title'),
        if (label.isNotEmpty) ...[
          const SizedBox(width: AppSpacing.xs),
          Text(label),
        ],
      ],
    ),
  ),
);

/// The first [limit] of [items] as rows, then a "Show all" button when there
/// are more. Null and empty read as in [listRows].
List<Widget> limitedRows<T>(
  BuildContext context,
  List<T>? items,
  int limit,
  Widget Function(T) row, {
  required String title,
  Widget? leading,
}) {
  if (items == null || items.length <= limit) return listRows(items, row);
  return [
    for (final item in items.take(limit)) row(item),
    showAllButton(
      context,
      label: '${items.length}',
      title: title,
      rows: [for (final item in items) row(item)],
      icon: leading is Icon ? leading.icon : Icons.expand_more,
    ),
  ];
}
