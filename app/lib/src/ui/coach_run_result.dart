/// A `run` chat line as values, not words: the relay writes one line per
/// example in the contract's fixed form `example N: got X, expected Y`
/// (`DOCS-coach-relay.md` §2, decision 8). Each becomes `N ✓ X` or
/// `N ✗ X ≠ Y`; X and Y are the program's own output (data). Any other line
/// (the run's error) is a red glyph with the line spoken.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

final _example = RegExp(r'^example (\d+): got (.*), expected (.*)$');

/// The examples of one run line.
class RunResults extends StatelessWidget {
  /// Creates the rows for the relay's [line].
  const new(this.line, {super.key});

  /// The `run` message text.
  final String line;

  @override
  Widget build(BuildContext context) {
    final colors = statusColors(context);
    final mono = monoStyle(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final row in line.split('\n'))
          if (_example.firstMatch(row.trim()) case final RegExpMatch m)
            Semantics(
              label: row,
              child: ExcludeSemantics(
                child: Wrap(
                  key: Key('example-${m[1]}'),
                  spacing: AppSpacing.sm,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text('${m[1]}', style: mono),
                    if (m[2] == m[3])
                      Icon(Icons.check, size: 18, color: colors.success)
                    else
                      Icon(Icons.close, size: 18, color: colors.danger),
                    Text(m[2]!, style: mono),
                    if (m[2] != m[3]) ...[
                      Text('≠', style: mono),
                      Text(m[3]!, style: mono),
                    ],
                  ],
                ),
              ),
            )
          else if (row.trim().isNotEmpty)
            Icon(
              Icons.error_outline,
              size: 18,
              color: colors.danger,
              semanticLabel: row,
            ),
      ],
    );
  }
}
