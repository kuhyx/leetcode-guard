/// Where the PC's coach relay stands, shared by the Coach tab and the
/// session screen.
///
/// No words (textgate): one glyph in the danger hue per kind of trouble,
/// the old sentence as its spoken label. What stays painted is data: the
/// command that starts the relay (kuhy types it) and the time of the last
/// heartbeat.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/wrapper_transport.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The command that starts the relay (desktop, relay down).
const kStartRelayCommand = 'systemctl --user start leetcode-coach-relay';

/// Spoken while the first heartbeat is read.
const kCheckingPc = 'Checking the PC...';

/// The relay's state as rows, or empty when it is online.
List<Widget> presenceLines(BuildContext context, CoachController c) {
  final presence = c.presence;
  final danger = Theme.of(context).colorScheme.error;
  Widget glyph(String spoken, {Color? color}) => Icon(
    presenceIcon(presence, c.outage?.outage),
    key: const Key('presence'),
    color: color ?? danger,
    size: 32,
    semanticLabel: spoken,
  );
  switch (presence) {
    case CoachPresence.online:
      return const [];
    case CoachPresence.checking:
      return [
        glyph(
          kCheckingPc,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ];
    case CoachPresence.relayDown:
      return [
        glyph(kRelayDownText),
        Row(
          children: [
            const Icon(Icons.terminal, semanticLabel: 'Start it on this PC'),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: SelectableText(
                kStartRelayCommand,
                style: monoStyle(context),
              ),
            ),
          ],
        ),
      ];
    case CoachPresence.pcOffline:
      final beat = c.heartbeat?.beat;
      return [
        Row(
          children: [
            glyph(
              beat == null
                  ? 'PC offline. The relay has never checked in.'
                  : 'PC offline. No heartbeat for over 2 minutes.',
            ),
            const SizedBox(width: AppSpacing.md),
            // The last heartbeat's time, or the empty set for never.
            Muted(
              beat == null
                  ? kNoneRecorded
                  : '$kAsOf ${timeOfMs(beat, c.now())}',
              key: const Key('last-beat'),
            ),
          ],
        ),
      ];
    case CoachPresence.unreachable:
      return [
        glyph('Cannot reach the coach: ${c.outage?.message ?? kUnknown}'),
      ];
  }
}

/// [presenceLines] as a full-width banner, or nothing when online.
class PresenceBanner extends StatelessWidget {
  /// Creates the banner for [controller].
  const new(this.controller, {super.key});

  /// The session controller.
  final CoachController controller;

  @override
  Widget build(BuildContext context) {
    final lines = presenceLines(context, controller);
    if (lines.isEmpty) return const SizedBox.shrink();
    return Container(
      key: const Key('presence-banner'),
      width: double.infinity,
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: lines,
      ),
    );
  }
}
