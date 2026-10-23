/// The list-bearing objects inside `status`: suggestions, solves, days and
/// budgets. Every field is null when unknown.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// One suggested problem.
class Suggestion {
  /// Parses a suggestion.
  new fromJson(Json json)
    : title = readString(json['title']),
      difficulty = readString(json['difficulty']),
      acRate = readDouble(json['ac_rate']),
      url = readString(json['url']);

  /// The problem title.
  final String? title;

  /// Easy/Medium/Hard.
  final String? difficulty;

  /// Acceptance rate in percent.
  final double? acRate;

  /// The problem page.
  final String? url;
}

/// One credited solve.
class Solve {
  /// Parses a solve.
  new fromJson(Json json)
    : day = readString(json['day']),
      titleSlug = readString(json['title_slug']),
      lang = readString(json['lang']);

  /// The day it was credited.
  final String? day;

  /// The problem slug.
  final String? titleSlug;

  /// The submission language.
  final String? lang;
}

/// `status.solves`: counts plus the most recent credited solves.
class SolvesData {
  /// Parses `solves`.
  new fromJson(Json json)
    : today = readInt(json['today']),
      last7Days = readInt(json['last_7_days']),
      totalCredited = readInt(json['total_credited']),
      recent = readObjects(json['recent'], Solve.fromJson);

  /// Solves credited today.
  final int? today;

  /// Solves credited in the last 7 days.
  final int? last7Days;

  /// Credited submissions all-time.
  final int? totalCredited;

  /// The most recent solves.
  final List<Solve>? recent;
}

/// `status.days`: which days were charged.
class DaysData {
  /// Parses `days`.
  new fromJson(Json json)
    : charged = readStrings(json['charged']),
      startDate = readString(json['start_date']),
      gateInForce = readBool(json['in_force']);

  /// Charged days, newest first.
  final List<String>? charged;

  /// When the gate came into force.
  final String? startDate;

  /// Whether it is in force today.
  final bool? gateInForce;
}

/// An escape or incident allowance. Rendered through its Python [summary];
/// when that is missing, every other field is shown from [extra] instead.
class Budget {
  /// Parses a budget.
  new fromJson(Json json)
    : label = readString(json['label']),
      summary = readString(json['summary']),
      exhausted = readBool(json['exhausted']),
      nextWaitSeconds = readInt(json['next_wait_seconds']),
      extra = {
        for (final e in json.entries)
          if (!_known.contains(e.key)) e.key: e.value,
      };

  static const _known = {'label', 'summary', 'exhausted', 'next_wait_seconds'};

  /// Its name.
  final String? label;

  /// One-line description.
  final String? summary;

  /// Whether it is used up.
  final bool? exhausted;

  /// How long the next use waits.
  final int? nextWaitSeconds;

  /// Every other field, by name.
  final Json extra;
}
