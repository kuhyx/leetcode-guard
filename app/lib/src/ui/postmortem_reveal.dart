/// What a tap on a post-mortem bar, row or chip shows: the only words on the
/// tab, all of them content (a slug, a card front, the model's finding).
library;

import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';

/// The one-shot mark, shared by the grid and a kept card's solves.
const IconData kOneShotIcon = Icons.bolt;

/// A tapped item's text on a slightly raised panel.
class Reveal extends StatelessWidget {
  /// Creates the panel: [title] strong, then [body], then [solves], each
  /// prefixed with the one-shot mark.
  const new({
    required this.title,
    this.body = '',
    this.solves = const [],
    super.key,
  });

  /// A slug, a unit or a card front.
  final String title;

  /// The finding; empty paints nothing.
  final String body;

  /// The one-shot solves that used a kept card's idea.
  final List<String> solves;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: theme.textTheme.titleSmall),
          if (body.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(body),
          ],
          for (final slug in solves)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Row(
                children: [
                  const Icon(
                    kOneShotIcon,
                    size: AppSpacing.md,
                    color: AppPalette.accent,
                    semanticLabel: 'One-shot solve',
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Expanded(child: Text(slug)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
