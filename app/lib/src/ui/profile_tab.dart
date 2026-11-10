/// The Profile tab: difficulty split, streaks, acceptance rate and the
/// 52-week submission heatmap.
///
/// No words (textgate, 2026-11-08): every section paints its icon, the
/// titles and row labels are spoken only.
library;

import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/card_grid.dart';
import 'package:leetcode_guard/src/ui/difficulty_mark.dart';
import 'package:leetcode_guard/src/ui/heatmap.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

// Section titles: spoken only. SectionCard speaks its title and paints
// `leading`; the phone's section chip shows the icon, which speaks it too.
const _split = 'Difficulty split';
const _streaks = 'Streaks';
const _acceptance = 'Acceptance rate';
const _calendar = 'Submission calendar';

const _splitIcon = Icon(
  Icons.pie_chart_outline,
  semanticLabel: _split,
  key: Key('section-difficulty-split'),
);
const _streaksIcon = Icon(
  Icons.local_fire_department,
  semanticLabel: _streaks,
  key: Key('profile-section-streaks'),
);
const _acceptanceIcon = Icon(
  Icons.percent,
  semanticLabel: _acceptance,
  key: Key('section-acceptance-rate'),
);
const _calendarIcon = Icon(
  Icons.calendar_month,
  semanticLabel: _calendar,
  key: Key('section-submission-calendar'),
);

/// The LeetCode profile view.
class ProfileTab extends StatelessWidget {
  /// Creates the tab over [profile]; [today] ends the heatmap window.
  const new({
    required this.profile,
    required this.today,
    required this.now,
    super.key,
  });

  /// The profile section, or null when unknown.
  final ProfileData? profile;

  /// The current time, to date a profile mirror that is not from today.
  final DateTime now;

  /// The UTC day the heatmap ends on.
  final DateTime today;

  /// Profile keys by the [kLevels] key they paint as.
  static const _levels = {'Easy': 'easy', 'Medium': 'medium', 'Hard': 'hard'};

  @override
  Widget build(BuildContext context) {
    final p = profile;
    if (p == null) {
      return const CardGrid(
        cards: [
          SectionCard.unknown(title: _split, leading: _splitIcon),
          SectionCard.unknown(title: _streaks, leading: _streaksIcon),
          SectionCard.unknown(title: _acceptance, leading: _acceptanceIcon),
        ],
        footer: [SectionCard.unknown(title: _calendar, leading: _calendarIcon)],
      );
    }
    final calendar = p.calendar;
    return CardGrid(
      // The PC serves a dated mirror when a refresh fails, so say how old.
      header: [_FetchedAt(asOfDated(p.fetchedAt, now))],
      cards: [
        SectionCard(
          title: _split,
          leading: _splitIcon,
          children: [
            for (final MapEntry(:key, :value) in _levels.entries)
              LevelRow(
                key,
                fraction(
                  p.difficulty?[value]?.solved,
                  p.difficulty?[value]?.total,
                ),
              ),
          ],
        ),
        SectionCard(
          title: _streaks,
          leading: _streaksIcon,
          children: [
            InfoRow(
              'Current streak in days',
              show(p.streakCurrent),
              icon: Icons.local_fire_department_outlined,
            ),
            InfoRow(
              'Longest streak in days',
              show(p.streakLongest),
              icon: Icons.emoji_events_outlined,
            ),
          ],
        ),
        SectionCard(
          title: _acceptance,
          leading: _acceptanceIcon,
          children: [
            InfoRow(
              'Accepted',
              percent(p.acceptanceRate),
              icon: Icons.check_circle_outline,
            ),
          ],
        ),
      ],
      // The heatmap is 52 weeks wide: it gets the whole row, not a column.
      footer: [
        if (calendar == null)
          const SectionCard.unknown(title: _calendar, leading: _calendarIcon)
        else
          SectionCard(
            title: _calendar,
            leading: _calendarIcon,
            children: [
              Heatmap(counts: calendar, today: today),
              InfoRow(
                'Submissions in the last 52 weeks',
                '${Heatmap.total(calendar, today)}',
                icon: Icons.functions,
              ),
            ],
          ),
      ],
    );
  }
}

/// When the profile was read: the person glyph tells it apart from the app
/// bar's snapshot time.
class _FetchedAt extends StatelessWidget {
  const new(this.at);

  final String at;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Row(
      key: const Key('profile-fetched-at'),
      children: [
        Icon(
          Icons.person_outline,
          color: muted,
          size: AppSpacing.lg,
          semanticLabel: 'Profile read at',
        ),
        const SizedBox(width: AppSpacing.xs),
        Muted(at),
      ],
    );
  }
}
