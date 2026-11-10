/// The Coach tab's guided-session controls: the "Guided session" card
/// (PC status, the live session and Resume) and each problem's Start.
///
/// No words (textgate): the live session is its problem's name (content),
/// the open step's mark and a five-dot track; a finished one its end glyph.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/coach/controller.dart';
import 'package:leetcode_guard/src/coach/requests.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/coach_state.dart';
import 'package:leetcode_guard/src/ui/coach_glyphs.dart';
import 'package:leetcode_guard/src/ui/coach_presence.dart';
import 'package:leetcode_guard/src/ui/coach_session_banners.dart';
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

/// The card's spoken title.
const kGuidedTitle = 'Guided session';

/// "Guided session": where the PC stands, and the live session if any. A
/// bare [SectionCard], so the phone chip shows its icon; the tab rebuilds
/// it on every controller change.
SectionCard liveSessionCard(CoachSessionLink link) => SectionCard(
  title: kGuidedTitle,
  leading: const Icon(Icons.route, semanticLabel: kGuidedTitle),
  children: [_Live(link)],
);

class _Live extends StatelessWidget {
  const new(this.link);

  final CoachSessionLink link;

  @override
  Widget build(BuildContext context) {
    final c = link.controller;
    final session = c.state?.session;
    final title = session?.title ?? show(session?.slug);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ...presenceLines(context, c),
        if (session != null) ...[
          Line(title, strong: true),
          if (session.live)
            _Track(c.state?.step, c.state?.steps ?? const [])
          else
            Align(
              alignment: Alignment.centerLeft,
              child: Icon(
                endIcon(session.endReason),
                key: const Key('last-session'),
                semanticLabel: 'Last: ${endedText(session.endReason)}',
              ),
            ),
        ],
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton(
            key: const Key('resume-session'),
            // Nothing to resume yet: each problem's own Start begins one.
            onPressed: session == null ? null : () => link.open(context),
            child: session == null || session.live
                ? const Icon(Icons.play_arrow, semanticLabel: 'Resume')
                // Not the eye: that one is Reveal.
                : const Icon(Icons.article_outlined, semanticLabel: 'View'),
          ),
        ),
      ],
    );
  }
}

/// The live session's five steps as dots, the open one as its mark.
class _Track extends StatelessWidget {
  const new(this.open, this.steps);

  final int? open;
  final List<CoachStep> steps;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ok = statusColors(context).success;
    final done = {
      for (final s in steps)
        if (s.status == StepStatus.passed || s.status == StepStatus.forced) s.n,
    };
    final spoken = 'Live: step ${show(open)} of ${kStepGlyphs.length}';
    return Semantics(
      label: spoken,
      child: ExcludeSemantics(
        child: Row(
          key: const Key('live-track'),
          children: [
            for (var n = 1; n <= kStepGlyphs.length; n++)
              Padding(
                padding: const EdgeInsets.only(right: AppSpacing.xs),
                child: n == open
                    ? StepMark(n, color: scheme.primary, size: 20)
                    : Icon(
                        done.contains(n) ? Icons.circle : Icons.circle_outlined,
                        size: 12,
                        color: done.contains(n) ? ok : scheme.onSurfaceVariant,
                      ),
              ),
          ],
        ),
      ),
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
    child: const Icon(Icons.play_arrow, semanticLabel: 'Start'),
  );
}
