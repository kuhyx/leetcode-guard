/// The post-theory one-shot rate per unit: one bar each, oldest on the left.
///
/// One series, so no legend; each bar carries its `k/n` above it. A 0 % bar
/// is a thin stub, an unknown one (no `[k, n]`, or n == 0) an outline and
/// `?`, so the two never look alike. Tapping a bar selects its unit.
library;

import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/postmortem.dart';
import 'package:material_ui/material_ui.dart';

/// Height of a 100 % bar.
const kBarMaxHeight = 120.0;

/// A bar's slot never gets narrower than this; past it the chart scrolls.
const kMinSlot = 28.0;

/// Nor wider than this, so two units do not fill a 4K window.
const kMaxSlot = 64.0;

/// The bar chart.
class OneShotBars extends StatelessWidget {
  /// Creates bars for [units], [selected] highlighted, [onTap] per bar.
  const new({
    required this.units,
    required this.selected,
    required this.onTap,
    super.key,
  });

  /// Every unit, oldest first.
  final List<PostmortemUnit> units;

  /// The index of the unit the grid and chips show.
  final int selected;

  /// Called with a bar's index.
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final slot = (constraints.maxWidth / units.length).clamp(
        kMinSlot,
        kMaxSlot,
      );
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (final (i, unit) in units.indexed)
              _Bar(
                key: Key('pm-bar-$i'),
                unit: unit,
                width: slot,
                selected: i == selected,
                onTap: () => onTap(i),
              ),
          ],
        ),
      );
    },
  );
}

class _Bar extends StatelessWidget {
  const new({
    required this.unit,
    required this.width,
    required this.selected,
    required this.onTap,
    super.key,
  });

  final PostmortemUnit unit;
  final double width;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final rate = unit.post;
    final fraction = rate?.fraction;
    final ink = AppPalette.accent.withValues(alpha: selected ? 1 : 0.45);
    final label = rate == null ? kUnknown : '${rate.k}/${rate.n}';
    final spoken = rate == null
        ? '${unit.unit}: one-shot rate unknown'
        : '${unit.unit}: ${rate.k} of ${rate.n} one-shot after the theory';
    return Semantics(
      button: true,
      selected: selected,
      label: spoken,
      child: ExcludeSemantics(
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadius.sm),
          child: SizedBox(
            width: width,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  label,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: selected ? null : scheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: AppSpacing.xs),
                Container(
                  width: width * 0.6,
                  height: fraction == null
                      ? AppSpacing.xs
                      : math.max(2, fraction * kBarMaxHeight),
                  decoration: BoxDecoration(
                    color: fraction == null ? null : ink,
                    border: fraction == null
                        ? Border.all(color: scheme.onSurfaceVariant)
                        : null,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(4),
                    ),
                  ),
                ),
                // The shared baseline, with a 2 px gap between slots.
                Container(
                  width: width - 2,
                  height: 1,
                  color: scheme.outlineVariant,
                ),
                const SizedBox(height: AppSpacing.xs),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
