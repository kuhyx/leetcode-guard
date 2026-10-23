/// The `progress` and `projections` sections.
library;

import 'package:leetcode_guard/src/model/json_read.dart';

/// Profile solved/total counts, per difficulty and overall.
class Progress {
  /// Parses `progress`.
  new fromJson(Json json)
    : solved = readIntMap(json['solved']),
      total = readIntMap(json['total']),
      solvedAll = readInt(json['solved_all']),
      totalAll = readInt(json['total_all']),
      fetchedAt = readTime(json['fetched_at']);

  /// Solved per difficulty (`Easy`/`Medium`/`Hard`).
  final Map<String, int?>? solved;

  /// Problems per difficulty.
  final Map<String, int?>? total;

  /// Solved overall.
  final int? solvedAll;

  /// Problems overall.
  final int? totalAll;

  /// When LeetCode was last read for these counts.
  final DateTime? fetchedAt;
}

/// One precomputed projection. The rules live in Python only; this is just
/// the answer the exporter computed for [target].
class Projection {
  /// Parses one entry of `projections`.
  new fromJson(Json json)
    : target = readString(json['target']),
      firstDay = readString(json['first_day']),
      gatedDays = readInt(json['gated_days']),
      freeDays = readInt(json['free_days']),
      baseCost = readInt(json['base_cost']),
      debt = readInt(json['debt']),
      available = readInt(json['available']),
      required = readInt(json['required']),
      rulesDemand = readInt(json['rules_demand']),
      debtLeftByRules = readInt(json['debt_left_by_rules']),
      sickDays = readInt(json['sick_days']),
      projected = readIntMap(json['projected']);

  /// The date projected to.
  final String? target;

  /// The first day the projection counts.
  final String? firstDay;

  /// Gated days until then.
  final int? gatedDays;

  /// Free days until then.
  final int? freeDays;

  /// What those days cost.
  final int? baseCost;

  /// Debt counted in.
  final int? debt;

  /// Credits banked now.
  final int? available;

  /// Credits required.
  final int? required;

  /// What the rules demand.
  final int? rulesDemand;

  /// Debt the rules leave.
  final int? debtLeftByRules;

  /// Sick days until then.
  final int? sickDays;

  /// Solved per difficulty projected for the date; null when the exporter
  /// had no solved counts to project from.
  final Map<String, int?>? projected;

  /// The projected total, or null unless every difficulty is known.
  int? get projectedTotal {
    final counts = projected?.values.toList();
    if (counts == null || counts.isEmpty || counts.contains(null)) return null;
    return counts.fold<int>(0, (sum, n) => sum + n!);
  }
}
