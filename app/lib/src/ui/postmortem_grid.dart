/// One row per problem of the selected unit: a one-shot mark, a pre/post
/// theory mark, tries and minutes. The header is icons, each with a
/// one-word tooltip; a tapped row reveals its slug and finding.
library;

import 'package:design_system/design_system.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/postmortem.dart';
import 'package:leetcode_guard/src/ui/postmortem_reveal.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';
import 'package:material_ui/material_ui.dart';

/// The grid's columns after the row number: icon and its tooltip word.
const List<(IconData, String)> kGridColumns = [
  (kOneShotIcon, 'One-shot'),
  (Icons.school_outlined, 'Phase'),
  (Icons.replay, 'Tries'),
  (Icons.timer_outlined, 'Minutes'),
];

const _numberWidth = 32.0;

/// The grid's rows for [problems]; [selected] is the revealed row.
List<Widget> problemGrid(
  BuildContext context,
  List<PostmortemProblem>? problems, {
  required int? selected,
  required ValueChanged<int> onTap,
}) {
  if (problems == null) return const [Muted(kUnknown)];
  if (problems.isEmpty) return const [Muted(kNoneRecorded)];
  final muted = Theme.of(context).colorScheme.onSurfaceVariant;
  return [
    _cells(const SizedBox(width: _numberWidth), [
      for (final (icon, word) in kGridColumns)
        Tooltip(
          message: word,
          child: Icon(icon, color: muted, size: AppSpacing.md + 2),
        ),
    ]),
    for (final (i, p) in problems.indexed) ...[
      InkWell(
        key: Key('pm-problem-$i'),
        onTap: () => onTap(i),
        child: Container(
          color: i == selected
              ? Theme.of(context).colorScheme.surfaceContainerHighest
              : null,
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
          child: _cells(
            SizedBox(
              width: _numberWidth,
              child: Text('${i + 1}', style: TextStyle(color: muted)),
            ),
            [
              _oneShot(p.oneShot, muted),
              _phase(p.afterTheory, muted),
              Text(show(p.tries)),
              Text(show(p.minutes)),
            ],
          ),
        ),
      ),
      if (i == selected)
        Reveal(
          key: const Key('pm-reveal-problem'),
          title: p.slug,
          body: p.finding,
        ),
    ],
  ];
}

Widget _cells(Widget first, List<Widget> cells) => Row(
  children: [
    first,
    for (final cell in cells) Expanded(child: Center(child: cell)),
  ],
);

Widget _oneShot(bool oneShot, Color muted) => oneShot
    ? const Icon(
        kOneShotIcon,
        color: AppPalette.accent,
        semanticLabel: 'One-shot',
      )
    : Icon(Icons.remove, color: muted, semanticLabel: 'Not one-shot');

Widget _phase(bool? afterTheory, Color muted) => switch (afterTheory) {
  true => const Icon(Icons.school, semanticLabel: 'After the theory'),
  false => Icon(
    Icons.history,
    color: muted,
    semanticLabel: 'Before the theory',
  ),
  null => const Text(kUnknown),
};
