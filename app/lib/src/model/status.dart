/// The `status` section: the gate's own answer, mirrored for display.
library;

import 'package:leetcode_guard/src/model/json_read.dart';
import 'package:leetcode_guard/src/model/status_lists.dart';
import 'package:leetcode_guard/src/model/status_parts.dart';

export 'package:leetcode_guard/src/model/status_lists.dart';
export 'package:leetcode_guard/src/model/status_parts.dart';

/// Today's gate verdict plus the sections derived from the ledger.
class StatusData {
  /// Parses the `status` object.
  new fromJson(Json json)
    : day = readString(json['day']),
      weekday = readString(json['weekday']),
      state = readString(json['state']),
      locked = readBool(json['locked']),
      reason = readString(json['reason']),
      explanation = readStrings(json['explanation']),
      cost = readInt(json['cost']),
      surcharge = readInt(json['surcharge']),
      credits = readInt(json['credits']),
      charged = readInt(json['charged']),
      available = readInt(json['available']),
      needed = readInt(json['needed']),
      chargedToday = readBool(json['charged_today']),
      earnedAllTime = readInt(json['earned_all_time']),
      spentAllTime = readInt(json['spent_all_time']),
      pricingNote = readString(json['pricing_note']),
      debt = readSection(json['debt'], Debt.fromJson),
      integrity = readSection(json['integrity'], Integrity.fromJson),
      environment = readSection(json['environment'], Environment.fromJson),
      suggestions = readObjects(json['suggestions'], Suggestion.fromJson),
      solves = readSection(json['solves'], SolvesData.fromJson),
      days = readSection(json['days'], DaysData.fromJson),
      budgets = readObjectMap(json['budgets'], Budget.fromJson);

  /// The gate's day (`YYYY-MM-DD`).
  final String? day;

  /// Its weekday name.
  final String? weekday;

  /// The gate state (open/already-charged/...).
  final String? state;

  /// Whether the gate is holding the machine today.
  final bool? locked;

  /// The gate's own one-line reason.
  final String? reason;

  /// Why the lock did not trigger, as Python words it.
  final List<String>? explanation;

  /// What today costs.
  final int? cost;

  /// The debt surcharge on top.
  final int? surcharge;

  /// Credits counted by the gate.
  final int? credits;

  /// Charges counted by the gate.
  final int? charged;

  /// Credits banked now.
  final int? available;

  /// Credits still needed today.
  final int? needed;

  /// Whether today has already been paid for.
  final bool? chargedToday;

  /// Ledger total of credits earned (differs from [credits] when refused).
  final int? earnedAllTime;

  /// Ledger total of charges spent.
  final int? spentAllTime;

  /// The pricing rules, rendered by Python (never re-derived here).
  final String? pricingNote;

  /// Derived debt.
  final Debt? debt;

  /// HMAC verification counts.
  final Integrity? integrity;

  /// Clock/auth/pool health.
  final Environment? environment;

  /// Suggested problems. Lists: null is unknown, empty is "none".
  final List<Suggestion>? suggestions;

  /// Solve counts and the recent list.
  final SolvesData? solves;

  /// Charged days and when the gate came into force.
  final DaysData? days;

  /// Escape-hatch and incident allowances by name.
  final Map<String, Budget?>? budgets;
}
