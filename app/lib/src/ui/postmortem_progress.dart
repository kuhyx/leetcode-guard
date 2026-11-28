/// The running post-mortem, live: its stage, a progress bar, elapsed time
/// and the ETA; once it ends, how it ended and what it changed.
///
/// No words before a tap (textgate): stages are glyphs with one-word
/// tooltips, times are numerals behind a glyph. A tap reveals the unit and,
/// for a failure, its error (content). The bar is elapsed over the tutor's
/// estimate (the median of its last runs), held under full until the run
/// really ends; past the estimate the bar turns warning and an overrun shows.
/// Display-only, from the snapshot's `postmortem_progress`
/// (DOCS-postmortem.md).
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:design_system/design_system.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/postmortem.dart';
import 'package:leetcode_guard/src/ui/postmortem_chips.dart';
import 'package:leetcode_guard/src/ui/postmortem_reveal.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';
import 'package:material_ui/material_ui.dart';

/// The section's spoken title.
const kProgressTitle = 'Post-mortem progress';

/// How long a finished run's card stays up.
const kShowDoneFor = Duration(hours: 6);

/// The glyph before an elapsed time.
const kElapsed = '⏱';

/// Each stage's glyph and its tooltip word, in order.
const Map<PostmortemStage, (IconData, String)> kStageGlyphs = {
  PostmortemStage.analysing: (Icons.psychology_outlined, 'Analysing'),
  PostmortemStage.applying: (Icons.edit_note, 'Applying'),
  PostmortemStage.saving: (Icons.save_outlined, 'Saving'),
};

/// The glyph of an un-taught card in the summary (it must be passed again).
const (IconData, String) kUntaughtGlyph = (Icons.replay, 'Untaught');

/// Whether [p] deserves a card at [now]: a run, a failure, or a recent end.
bool showProgress(PostmortemProgress? p, DateTime now) => switch (p?.state) {
  PostmortemState.running || PostmortemState.failed => true,
  PostmortemState.done => switch (p?.finishedAt) {
    final DateTime at => now.difference(at) < kShowDoneFor,
    null => false,
  },
  null => false,
};

/// `m:ss` (or `h:mm:ss`) of [d]; negative reads as zero.
String clockOf(Duration d) {
  final s = math.max(0, d.inSeconds);
  final h = s ~/ 3600;
  final m = (s % 3600) ~/ 60;
  final sec = (s % 60).toString().padLeft(2, '0');
  return h > 0 ? '$h:${m.toString().padLeft(2, '0')}:$sec' : '$m:$sec';
}

/// The card; it repaints itself every second while the run is live.
class PostmortemProgressCard extends StatefulWidget {
  /// Creates the card over [progress], with [now] as the clock.
  const new({required this.progress, required this.now, super.key});

  /// The snapshot's section.
  final PostmortemProgress progress;

  /// The app's clock (tests freeze it).
  final DateTime Function() now;

  @override
  State<PostmortemProgressCard> createState() => _CardState();
}

class _CardState extends State<PostmortemProgressCard> {
  Timer? _tick;
  bool _open = false;

  bool get _running => widget.progress.state == PostmortemState.running;

  @override
  void initState() {
    super.initState();
    _arm();
  }

  @override
  void didUpdateWidget(PostmortemProgressCard old) {
    super.didUpdateWidget(old);
    _arm();
  }

  void _arm() {
    if (_running) {
      _tick ??= Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) setState(() {});
      });
    } else {
      _tick?.cancel();
      _tick = null;
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.progress;
    final now = widget.now();
    final (icon, colour) = switch (p.state) {
      PostmortemState.running => (Icons.hourglass_top, AppPalette.accent),
      PostmortemState.failed => (Icons.error_outline, AppPalette.danger),
      _ => (Icons.task_alt, AppPalette.success),
    };
    return SectionCard(
      key: const Key('pm-progress'),
      title: kProgressTitle,
      leading: Icon(
        icon,
        color: colour,
        key: const Key('pm-progress-state'),
        semanticLabel: p.state?.name ?? kUnknown,
      ),
      children: [
        InkWell(
          key: const Key('pm-progress-tap'),
          onTap: () => setState(() => _open = !_open),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Stages(p),
              const SizedBox(height: AppSpacing.sm),
              _Bar(p, now),
              const SizedBox(height: AppSpacing.xs),
              _Times(p, now),
              if (p.state == PostmortemState.done) _Summary(p.summary),
            ],
          ),
        ),
        if (_open)
          Reveal(
            key: const Key('pm-progress-reveal'),
            title: p.unit,
            body: p.error,
          ),
      ],
    );
  }
}

class _Stages extends StatelessWidget {
  const new(this.p);

  final PostmortemProgress p;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final at = p.stage?.index;
    final finished = p.state == PostmortemState.done;
    return Row(
      children: [
        for (final MapEntry(key: stage, value: (glyph, word))
            in kStageGlyphs.entries)
          Padding(
            padding: const EdgeInsets.only(right: AppSpacing.md),
            child: Tooltip(
              message: word,
              child: Icon(
                glyph,
                key: Key('pm-stage-${stage.name}'),
                semanticLabel: word,
                color: finished || (at != null && stage.index < at)
                    ? AppPalette.success
                    : stage.index == at
                    ? AppPalette.accent
                    : muted,
              ),
            ),
          ),
      ],
    );
  }
}

class _Bar extends StatelessWidget {
  const new(this.p, this.now);

  final PostmortemProgress p;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final start = p.startedAt;
    final guess = p.estimate;
    final (double? value, Color colour) = switch (p.state) {
      PostmortemState.done => (1.0, AppPalette.success),
      PostmortemState.failed => (1.0, AppPalette.danger),
      _ when start == null || guess == null || guess == Duration.zero => (
        null,
        AppPalette.accent,
      ),
      _ => _running(now.difference(start), guess),
    };
    return LinearProgressIndicator(
      key: const Key('pm-progress-bar'),
      value: value,
      color: colour,
      minHeight: AppSpacing.sm,
      borderRadius: BorderRadius.circular(AppRadius.sm),
      semanticsValue: value == null ? kUnknown : '${(value * 100).round()}%',
    );
  }

  static (double, Color) _running(Duration spent, Duration guess) {
    final share = spent.inMilliseconds / guess.inMilliseconds;
    return share >= 1
        ? (0.99, AppPalette.warning)
        : (math.max(0, share), AppPalette.accent);
  }
}

class _Times extends StatelessWidget {
  const new(this.p, this.now);

  final PostmortemProgress p;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final start = p.startedAt;
    final end = p.finishedAt ?? now;
    final eta = p.eta;
    final running = p.state == PostmortemState.running;
    final over = running && eta != null && now.isAfter(eta)
        ? now.difference(eta)
        : null;
    return Row(
      children: [
        Text(
          start == null
              ? '$kElapsed $kUnknown'
              : '$kElapsed ${clockOf(end.difference(start))}',
          key: const Key('pm-progress-elapsed'),
        ),
        if (over != null) ...[
          const SizedBox(width: AppSpacing.sm),
          Text(
            '+${clockOf(over)}',
            key: const Key('pm-progress-over'),
            style: const TextStyle(color: AppPalette.warning),
          ),
        ],
        const Spacer(),
        Text(
          asOf(running ? eta : p.finishedAt),
          key: const Key('pm-progress-eta'),
        ),
      ],
    );
  }
}

class _Summary extends StatelessWidget {
  const new(this.counts);

  final Map<String, int?>? counts;

  @override
  Widget build(BuildContext context) {
    final got = counts ?? const {};
    final rows = [
      ('added', kChangeGlyphs[CardChange.added]!),
      ('edited', kChangeGlyphs[CardChange.edited]!),
      ('untaught', kUntaughtGlyph),
      ('suspended', kChangeGlyphs[CardChange.suspended]!),
    ];
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: Wrap(
        spacing: AppSpacing.md,
        children: [
          for (final (name, (glyph, word)) in rows)
            Tooltip(
              message: word,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(glyph, size: AppSpacing.md + 2, semanticLabel: word),
                  const SizedBox(width: AppSpacing.xs),
                  Text(show(got[name]), key: Key('pm-progress-$name')),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
