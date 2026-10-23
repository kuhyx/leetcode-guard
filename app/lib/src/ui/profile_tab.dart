/// The Profile tab: difficulty split, streaks, acceptance rate and the
/// 52-week submission heatmap.
library;

import 'package:flutter/material.dart';
import 'package:leetcode_guard/src/format.dart';
import 'package:leetcode_guard/src/model/snapshot.dart';
import 'package:leetcode_guard/src/ui/heatmap.dart';
import 'package:leetcode_guard/src/ui/widgets.dart';

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

  static const _levels = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'};

  @override
  Widget build(BuildContext context) {
    final p = profile;
    if (p == null) {
      return ListView(
        padding: kGutter,
        children: const [
          SectionCard.unknown(title: 'Difficulty split'),
          SectionCard.unknown(title: 'Streaks'),
          SectionCard.unknown(title: 'Acceptance rate'),
          SectionCard.unknown(title: 'Submission calendar'),
        ],
      );
    }
    final calendar = p.calendar;
    return ListView(
      padding: kGutter,
      children: [
        // The PC serves a dated mirror when a refresh fails, so say how old.
        Muted('Profile ${asOfDated(p.fetchedAt, now)}'),
        SectionCard(
          title: 'Difficulty split',
          children: [
            for (final MapEntry(:key, :value) in _levels.entries)
              InfoRow(
                value,
                fraction(p.difficulty?[key]?.solved, p.difficulty?[key]?.total),
              ),
          ],
        ),
        SectionCard(
          title: 'Streaks',
          children: [
            InfoRow('Current', _days(p.streakCurrent)),
            InfoRow('Longest', _days(p.streakLongest)),
          ],
        ),
        SectionCard(
          title: 'Acceptance rate',
          children: [InfoRow('Accepted', percent(p.acceptanceRate))],
        ),
        if (calendar == null)
          const SectionCard.unknown(title: 'Submission calendar')
        else
          SectionCard(
            title: 'Submission calendar',
            children: [
              Heatmap(counts: calendar, today: today),
              Muted(
                '${Heatmap.total(calendar, today)} submissions in the last '
                '52 weeks',
              ),
            ],
          ),
      ],
    );
  }

  static String _days(int? n) => n == null ? kUnknown : '$n days';
}
