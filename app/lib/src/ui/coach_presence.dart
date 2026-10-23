/// The words for where the PC's coach relay stands, shared by the Coach
/// tab and the session screen.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/wrapper_transport.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/coach_how_to.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The command that starts the relay (desktop, relay down).
const kStartRelayCommand = 'systemctl --user start leetcode-coach-relay';

/// Lines describing [c]'s presence, or empty when it is online.
List<Widget> presenceLines(BuildContext context, CoachController c) {
  final danger = Theme.of(context).colorScheme.error;
  switch (c.presence) {
    case CoachPresence.online:
      return const [];
    case CoachPresence.checking:
      return const [Muted('Checking the PC...')];
    case CoachPresence.relayDown:
      return [
        Line(kRelayDownText, color: danger, strong: true),
        const Muted('Start it on this PC:'),
        SelectableText(kStartRelayCommand, style: monoStyle(context)),
      ];
    case CoachPresence.pcOffline:
      final beat = c.heartbeat?.beat;
      final seen = beat == null
          ? 'The relay has never checked in.'
          : 'Last heard from ${timeOfMs(beat, c.now())}.';
      return [
        Line('PC offline', color: danger, strong: true),
        Muted('No heartbeat for over 2 minutes. $seen'),
      ];
    case CoachPresence.unreachable:
      return [
        Line('Cannot reach the coach', color: danger, strong: true),
        Muted(c.outage?.message ?? kUnknown),
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
