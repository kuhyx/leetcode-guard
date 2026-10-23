/// The Coach tab's guided-session controls: the "Guided session" card
/// (PC status, the live session and Resume) and each problem's Start.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/ui/coach_presence.dart';
import 'package:leetcode_guard/src/ui/coach_session_screen.dart';
import 'package:leetcode_guard/src/ui/status_health.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

/// The coach's session plus the link opener every session screen needs.
class CoachSessionLink {
  /// Bundles [controller] with [openUrl].
  const new(this.controller, this.openUrl);

  /// The session controller.
  final CoachController controller;

  /// Opens a problem page.
  final UrlOpener openUrl;

  /// Whether a new session may start now.
  bool get canStart => controller.canAct && !(controller.state?.live ?? false);

  /// Pushes the session screen.
  Future<void> open(BuildContext context) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) =>
          CoachSessionScreen(controller: controller, openUrl: openUrl),
    ),
  );

  /// Starts [slug] and shows its session screen.
  Future<void> start(BuildContext context, String slug) async {
    if (!controller.startSession(slug)) return;
    await open(context);
  }
}

/// "Guided session": where the PC stands, and the live session if any.
class LiveSessionCard extends StatelessWidget {
  /// Creates the card for [link].
  const new(this.link, {super.key});

  /// The session and opener.
  final CoachSessionLink link;

  @override
  Widget build(BuildContext context) {
    final c = link.controller;
    final session = c.state?.session;
    final title = session?.title ?? show(session?.slug);
    return SectionCard(
      title: 'Guided session',
      children: [
        ...presenceLines(context, c),
        if (session == null)
          const Muted(
            'Press Start on a problem to be walked through it, '
            'graded at each step, with the coach in a chat beside it.',
          )
        else ...[
          Line(
            session.live
                ? 'Live: $title, step ${show(c.state?.step)} of 5'
                : 'Last: $title (${show(session.endReason)})',
          ),
          if (session.live)
            const Muted('End it before starting another problem.'),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton(
              key: const Key('resume-session'),
              onPressed: () => link.open(context),
              child: Text(session.live ? 'Resume' : 'View'),
            ),
          ),
        ],
      ],
    );
  }
}

/// A problem's Start button.
class StartButton extends StatelessWidget {
  /// Creates Start for [slug].
  const new(this.link, this.slug, {this.keyName, super.key});

  /// The session and opener.
  final CoachSessionLink link;

  /// The problem to start.
  final String slug;

  /// The widget key, default `start-<slug>`.
  final String? keyName;

  @override
  Widget build(BuildContext context) => OutlinedButton(
    key: Key(keyName ?? 'start-$slug'),
    onPressed: link.canStart ? () => link.start(context, slug) : null,
    child: const Text('Start'),
  );
}
