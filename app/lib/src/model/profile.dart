/// The `profile` section: the LeetCode profile view.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// A solved/total pair (`[120, 900]`).
class Split {
  /// Parses a two-element list.
  new fromList(List<Object?> list)
    : solved = list.isNotEmpty ? readInt(list[0]) : null,
      total = list.length > 1 ? readInt(list[1]) : null;

  /// Problems solved.
  final int? solved;

  /// Problems available.
  final int? total;
}

/// The LeetCode profile view. A failed refresh on the PC serves a dated
/// mirror, so [fetchedAt] can be older than the snapshot.
class ProfileData {
  /// Parses `profile`.
  new fromJson(Json json)
    : difficulty = _splits(json['difficulty']),
      streakCurrent = readInt(json['streak_current']),
      streakLongest = readInt(json['streak_longest']),
      calendar = _calendar(json['calendar']),
      acceptanceRate = readDouble(json['acceptance_rate']),
      fetchedAt = readTime(json['fetched_at']);

  /// Per difficulty (easy/medium/hard); a malformed entry is null.
  final Map<String, Split?>? difficulty;

  /// Current streak in days.
  final int? streakCurrent;

  /// Longest streak in days.
  final int? streakLongest;

  /// Submissions per UTC day.
  final Map<DateTime, int>? calendar;

  /// Overall acceptance rate in percent.
  final double? acceptanceRate;

  /// When LeetCode was last read for this profile.
  final DateTime? fetchedAt;

  static Map<String, Split?>? _splits(Object? value) {
    final map = readMap(value);
    if (map == null) return null;
    return {
      for (final MapEntry(:key, :value) in map.entries)
        key: value is List ? Split.fromList(value) : null,
    };
  }

  static Map<DateTime, int>? _calendar(Object? value) {
    final map = readMap(value);
    if (map == null) return null;
    final days = <DateTime, int>{};
    for (final e in map.entries) {
      final day = _day(e.key);
      final count = readInt(e.value);
      if (day != null && count != null) days[day] = count;
    }
    return days;
  }

  /// `2026-10-22`, or LeetCode's own epoch-second key.
  static DateTime? _day(String key) {
    final seconds = int.tryParse(key);
    final t = seconds != null
        ? DateTime.fromMillisecondsSinceEpoch(seconds * 1000, isUtc: true)
        : DateTime.tryParse(key);
    return t == null ? null : DateTime.utc(t.year, t.month, t.day);
  }
}
