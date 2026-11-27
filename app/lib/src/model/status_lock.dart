/// The `status.lock` section: what the PC lock shows while today is unpaid,
/// so the phone can offer the same unit and the same rows.
///
/// Display only, like the rest of the snapshot: the PC decides, this mirrors.
/// An older snapshot has no `lock` at all, which parses as null (no block).
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// The lock's unit, phase and rows.
class LockData {
  /// Parses the `lock` object.
  new fromJson(Json json)
    : unpaid = readBool(json['unpaid']),
      unit = readString(json['unit']),
      phase = readString(json['phase']),
      learnRoute = readString(json['learn_route']),
      rows = readObjects(json['rows'], LockRow.tryParse)?.nonNulls.toList();

  /// Whether today is still owed; the block shows only when true.
  final bool? unpaid;

  /// The curriculum unit the lock is on (`""` when none).
  final String? unit;

  /// `theory`, `solve` or `none`.
  final String? phase;

  /// The tutor route of the unit's lesson (`/learn/<subject>/<module>`).
  final String? learnRoute;

  /// The rows in the PC lock's order; null when unknown.
  final List<LockRow>? rows;
}

/// One row of the lock: a problem to solve or the tutor review.
sealed class LockRow {
  const new();

  /// The row for [json] by its `kind`, or null for a kind this app does
  /// not know (a newer PC), which is skipped rather than drawn wrong.
  static LockRow? tryParse(Json json) => switch (json['kind']) {
    'problem' => LockProblem.fromJson(json),
    'review' => LockReview.fromJson(json),
    _ => null,
  };
}

/// A LeetCode problem the lock suggests.
class LockProblem extends LockRow {
  /// Parses a `problem` row.
  new fromJson(Json json)
    : title = readString(json['title']),
      difficulty = readString(json['difficulty']),
      url = readString(json['url']);

  /// LeetCode's title (content).
  final String? title;

  /// `Easy`, `Medium` or `Hard`.
  final String? difficulty;

  /// `https://leetcode.com/problems/<slug>/`.
  final String? url;
}

/// The tutor's due cards, shown instead of the problems.
class LockReview extends LockRow {
  /// Parses a `review` row.
  new fromJson(Json json)
    : count = readInt(json['count']),
      route = readString(json['route']);

  /// Cards due.
  final int? count;

  /// The tutor route (`/review/<subject>/<module>`).
  final String? route;
}
