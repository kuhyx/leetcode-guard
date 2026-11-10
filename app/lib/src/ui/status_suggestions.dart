/// The suggested problems: the Status tab's one action. A title is
/// LeetCode's own (content); its difficulty is a coloured bar count and its
/// acceptance a mark and a percentage (textgate).
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/more_sheet.dart';
import 'package:leetcode_guard/src/ui/status_glyphs.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// Opens [uri] outside the app.
typedef UrlOpener = Future<bool> Function(Uri uri);

/// "Suggested problems": tap one to open it in the browser.
Widget suggestionsSection(
  BuildContext context,
  StatusData? s,
  UrlOpener openUrl,
) {
  const title = 'Suggested problems';
  final leading = sectionIcon(Icons.lightbulb_outline, title);
  if (s == null) return SectionCard.unknown(title: title, leading: leading);
  return SectionCard(
    title: title,
    leading: leading,
    children: limitedRows(
      context,
      s.suggestions,
      3,
      (item) => _SuggestionTile(item: item, openUrl: openUrl),
      title: title,
    ),
  );
}

/// The bars and colour of a LeetCode difficulty: one green bar for Easy,
/// two amber for Medium, three red for Hard, a question mark otherwise.
(IconData, Color?) difficultyGlyph(BuildContext context, String? level) {
  final colors = statusColors(context);
  return switch (level) {
    'Easy' => (Icons.signal_cellular_alt_1_bar, colors.success),
    'Medium' => (Icons.signal_cellular_alt_2_bar, colors.warning),
    'Hard' => (Icons.signal_cellular_alt, Theme.of(context).colorScheme.error),
    _ => (Icons.help_outline, null),
  };
}

class _SuggestionTile extends StatelessWidget {
  const new({required this.item, required this.openUrl});

  final Suggestion item;
  final UrlOpener openUrl;

  /// Only https opens: the URL arrives over the network, and a
  /// `javascript:` or `intent:` link must never be launched.
  Uri? get _target {
    final uri = Uri.tryParse(item.url ?? '');
    return uri != null && uri.scheme == 'https' ? uri : null;
  }

  @override
  Widget build(BuildContext context) {
    final target = _target;
    final scheme = Theme.of(context).colorScheme;
    final muted = scheme.onSurfaceVariant;
    final (bars, barColor) = difficultyGlyph(context, item.difficulty);
    final spoken = '${show(item.difficulty)}, ${percent(item.acRate)} accepted';
    return InkWell(
      borderRadius: BorderRadius.circular(AppRadius.sm),
      onTap: target == null ? null : () => openUrl(target),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    show(item.title),
                    style: TextStyle(
                      color: target == null ? null : scheme.primary,
                    ),
                  ),
                  Semantics(
                    label: spoken,
                    excludeSemantics: true,
                    child: Row(
                      key: const Key('suggestion-meta'),
                      children: [
                        Icon(bars, size: 20, color: barColor ?? muted),
                        const SizedBox(width: AppSpacing.md),
                        Icon(Icons.check, size: 16, color: muted),
                        Text(
                          percent(item.acRate),
                          style: TextStyle(color: muted),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (target != null) Icon(Icons.open_in_new, size: 20, color: muted),
          ],
        ),
      ),
    );
  }
}
