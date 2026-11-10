/// The "stale / could not refresh" strip above every tab.
///
/// 2026-10-24: an unbounded Text holding a raw exception overflowed the
/// Pixel 6a by 140 px and put a Firebase token on screen. Since the textgate
/// rework (2026-11-08) the strip paints no words at all: what is wrong is an
/// icon, how old the data is a number. The (sanitised) reason is spoken,
/// and scrubbed again here because the accessibility tree is exposed too.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/state/controller.dart';

/// The icon of each [FailureKind].
IconData failureIcon(FailureKind kind) => switch (kind) {
  FailureKind.offline => Icons.cloud_off,
  FailureKind.timeout => Icons.timer_off_outlined,
  FailureKind.http => Icons.dns_outlined,
  FailureKind.signIn => Icons.no_accounts_outlined,
  FailureKind.other => Icons.error_outline,
};

/// The banner over [c]'s age and last error.
class StaleBanner extends StatelessWidget {
  /// Creates the banner.
  const new(this.c, {super.key});

  /// The status controller.
  final StatusController c;

  /// The words the strip used to paint, now its spoken label.
  String get spoken {
    final error = c.error;
    final text = c.snapshot == null
        ? 'No snapshot yet${error == null ? '' : ': $error'}'
        : 'Stale: ${ageText(c.freshAt, c.now())}'
              '${error == null ? '' : '. Could not refresh: $error'}';
    // Sanitised at the source; scrubbed again because a reader speaks it.
    return scrubSecrets(text);
  }

  @override
  Widget build(BuildContext context) {
    final error = c.error;
    final kind = error == null ? null : failureKind(error);
    final status = error == null ? null : httpStatusIn(error);
    const ink = AppPalette.onFill;
    return Material(
      key: const Key('stale-banner'),
      color: AppPalette.warning,
      child: Semantics(
        label: spoken,
        excludeSemantics: true,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              if (c.snapshot == null)
                const Icon(Icons.cloud_download_outlined, color: ink)
              else ...[
                const Icon(Icons.history, color: ink),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  ageText(c.freshAt, c.now()),
                  key: const Key('stale-age'),
                  style: const TextStyle(color: ink),
                ),
              ],
              if (kind != null) ...[
                const SizedBox(width: AppSpacing.md),
                Icon(
                  failureIcon(kind),
                  color: ink,
                  key: Key('failure-${kind.name}'),
                ),
              ],
              if (status != null) ...[
                const SizedBox(width: AppSpacing.xs),
                Text('$status', style: const TextStyle(color: ink)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
