/// The "stale / could not refresh" strip above every tab.
///
/// 2026-10-24: an unbounded Text holding a raw exception overflowed the
/// Pixel 6a by 140 px. Two lines with an ellipsis now; a tap shows the whole
/// (already sanitised) reason, capped at a third of the screen and scrolled.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/data/failure_text.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/state/controller.dart';

/// Lines shown before a tap.
const kBannerLines = 2;

/// The banner over [c]'s age and last error.
class StaleBanner extends StatefulWidget {
  /// Creates the banner.
  const new(this.c, {super.key});

  /// The status controller.
  final StatusController c;

  @override
  State<StaleBanner> createState() => _StaleBannerState();
}

class _StaleBannerState extends State<StaleBanner> {
  bool _open = false;

  String get _text {
    final c = widget.c;
    final error = c.error;
    final text = c.snapshot == null
        ? 'No snapshot yet${error == null ? '' : ': $error'}'
        : 'Stale: ${ageText(c.freshAt, c.now())}'
              '${error == null ? '' : '. Could not refresh: $error'}';
    // Sanitised at the source; scrubbed again because this is on screen.
    return scrubSecrets(text);
  }

  @override
  Widget build(BuildContext context) {
    final text = Text(
      _text,
      maxLines: _open ? null : kBannerLines,
      overflow: _open ? null : TextOverflow.ellipsis,
      style: const TextStyle(color: AppPalette.onFill),
    );
    return Material(
      key: const Key('stale-banner'),
      color: AppPalette.warning,
      child: InkWell(
        onTap: () => setState(() => _open = !_open),
        child: Container(
          width: double.infinity,
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height / 3,
          ),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          child: _open ? SingleChildScrollView(child: text) : text,
        ),
      ),
    );
  }
}
